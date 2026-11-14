//! Bounded JSONL transport. A timed-out write poisons the pipe: partial frames
//! must never be followed by another request. Calls are never replayed.
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex as StdMutex,
    },
    time::Duration,
};
use tokio::{
    io::{AsyncBufRead, AsyncBufReadExt, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    sync::{oneshot, Mutex, Semaphore},
};

pub const MAX_REQUEST: usize = 1_048_576;
pub const MAX_RESPONSE: usize = 16 * MAX_REQUEST;
pub type Reply = Result<Value, EngineError>;

#[derive(Debug, Clone, Serialize)]
pub struct EngineError {
    pub code: String,
    pub message: String,
    /// Eligible for a user-initiated retry after reconciling status, never replay.
    pub retryable: bool,
}
impl EngineError {
    pub fn new(code: &str, message: &str, retryable: bool) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            retryable,
        }
    }
}
impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for EngineError {}
fn disconnected() -> EngineError {
    EngineError::new(
        "disconnected",
        "Python engine disconnected. Restart Caelum; check recording status before retrying.",
        false,
    )
}
fn protocol() -> EngineError {
    EngineError::new(
        "protocol",
        "Invalid Python engine response. Restart Caelum.",
        false,
    )
}

pub enum Frame {
    Reply(u64, Reply),
    Event(String, Value),
}
pub fn parse(bytes: &[u8]) -> Result<Frame, EngineError> {
    let frame: Value = serde_json::from_slice(bytes).map_err(|_| protocol())?;
    let obj = frame.as_object().ok_or_else(protocol)?;
    if frame["v"] != 1 {
        return Err(protocol());
    }
    if let Some(id) = frame["id"].as_u64() {
        if obj.contains_key("event")
            || obj.contains_key("data")
            || obj.contains_key("result") == obj.contains_key("error")
        {
            return Err(protocol());
        }
        if obj
            .keys()
            .any(|key| !["v", "id", "result", "error", "error_info"].contains(&key.as_str()))
        {
            return Err(protocol());
        }
        if obj.contains_key("result") {
            if obj.contains_key("error_info") {
                return Err(protocol());
            }
            return Ok(Frame::Reply(id, Ok(frame["result"].clone())));
        }
        let legacy_message = frame["error"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 2048)
            .ok_or_else(protocol)?;
        if !obj.contains_key("error_info") {
            return Ok(Frame::Reply(
                id,
                Err(EngineError::new("operation_blocked", legacy_message, false)),
            ));
        }
        let error = &frame["error_info"];
        let code = error["code"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 64)
            .ok_or_else(protocol)?;
        let message = error["message"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 2048)
            .ok_or_else(protocol)?;
        if message != legacy_message {
            return Err(protocol());
        }
        let retryable = error["retryable"].as_bool().ok_or_else(protocol)?;
        return Ok(Frame::Reply(
            id,
            Err(EngineError::new(code, message, retryable)),
        ));
    }
    if obj.contains_key("id") || obj.contains_key("result") || obj.contains_key("error") {
        return Err(protocol());
    }
    if obj
        .keys()
        .any(|key| !["v", "event", "data"].contains(&key.as_str()))
    {
        return Err(protocol());
    }
    let event = frame["event"]
        .as_str()
        .filter(|s| ["status", "microphone", "status-error"].contains(s))
        .ok_or_else(protocol)?;
    if !frame["data"].is_object() {
        return Err(protocol());
    }
    let data = &frame["data"];
    match event {
        "microphone"
            if data["level"]
                .as_f64()
                .is_none_or(|value| !value.is_finite() || !(0.0..=1.0).contains(&value)) =>
        {
            return Err(protocol())
        }
        "status-error"
            if data["message"]
                .as_str()
                .is_none_or(|message| message.is_empty() || message.len() > 2048) =>
        {
            return Err(protocol())
        }
        _ => (),
    }
    Ok(Frame::Event(event.into(), data.clone()))
}

pub async fn read_frame<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    limit: usize,
) -> Result<Option<Vec<u8>>, EngineError> {
    let mut bytes = Vec::new();
    // Take bounds allocation even when a child never emits a newline.
    let count = (&mut *reader)
        .take((limit + 1) as u64)
        .read_until(b'\n', &mut bytes)
        .await
        .map_err(|_| disconnected())?;
    if count == 0 {
        return Ok(None);
    }
    if count > limit || bytes.last() != Some(&b'\n') {
        return Err(protocol());
    }
    Ok(Some(bytes))
}

struct Shared {
    pending: StdMutex<HashMap<u64, oneshot::Sender<Reply>>>,
    alive: AtomicBool,
}
impl Shared {
    fn fail(&self, error: EngineError) {
        self.alive.store(false, Ordering::SeqCst);
        for (_, sender) in self.pending.lock().unwrap().drain() {
            let _ = sender.send(Err(error.clone()));
        }
    }
}
struct Pending {
    shared: Arc<Shared>,
    id: u64,
}
impl Drop for Pending {
    fn drop(&mut self) {
        self.shared.pending.lock().unwrap().remove(&self.id);
    }
}
struct Writing {
    shared: Arc<Shared>,
    complete: bool,
}
impl Drop for Writing {
    fn drop(&mut self) {
        if !self.complete {
            self.shared.fail(disconnected());
        }
    }
}

pub struct Requests<W> {
    input: Mutex<W>,
    shared: Arc<Shared>,
    slots: Semaphore,
    sequence: AtomicU64,
}
impl<W: AsyncWrite + Unpin> Requests<W> {
    pub fn new(input: W) -> Self {
        Self {
            input: Mutex::new(input),
            shared: Arc::new(Shared {
                pending: StdMutex::new(HashMap::new()),
                alive: AtomicBool::new(true),
            }),
            slots: Semaphore::new(64),
            sequence: AtomicU64::new(1),
        }
    }
    pub fn alive(&self) -> bool {
        self.shared.alive.load(Ordering::SeqCst)
    }
    pub fn fail(&self, error: EngineError) {
        self.shared.fail(error);
    }
    pub fn resolve(&self, id: u64, result: Reply) {
        if let Some(sender) = self.shared.pending.lock().unwrap().remove(&id) {
            let _ = sender.send(result);
        }
    }
    pub async fn finish_input(&self) {
        let _ = self.input.lock().await.shutdown().await;
    }
    pub async fn call(&self, method: &str, params: Value, budget: Duration) -> Reply {
        let _slot = self.slots.try_acquire().map_err(|_| {
            EngineError::new(
                "busy",
                "Too many pending requests. Wait for an operation to finish.",
                true,
            )
        })?;
        if !self.alive() {
            return Err(disconnected());
        }
        let id = self.sequence.fetch_add(1, Ordering::Relaxed);
        let frame = format!(
            "{}\n",
            json!({"v":1,"id":id,"method":method,"params":params})
        );
        if frame.len() > MAX_REQUEST {
            return Err(EngineError::new(
                "invalid_request",
                "Request too large",
                false,
            ));
        }
        let (sender, receiver) = oneshot::channel();
        self.shared.pending.lock().unwrap().insert(id, sender);
        let _pending = Pending {
            shared: self.shared.clone(),
            id,
        };
        // One deadline includes lock acquisition, writing and awaiting the reply.
        match tokio::time::timeout(budget, async {
            {
                let mut input = self.input.lock().await;
                if !self.alive() {
                    return Err(disconnected());
                }
                let mut writing = Writing {
                    shared: self.shared.clone(),
                    complete: false,
                };
                input
                    .write_all(frame.as_bytes())
                    .await
                    .map_err(|_| disconnected())?;
                writing.complete = true;
            }
            receiver.await.unwrap_or_else(|_| Err(disconnected()))
        })
        .await
        {
            Ok(reply) => reply,
            Err(_) => Err(EngineError::new(
                "timeout",
                "Engine request timed out. Its outcome is unknown; check status before retrying.",
                false,
            )),
        }
    }
}
/// The graceful budget covers protocol cleanup and waiting; forced reaping has
/// a separate small budget. No caller can accidentally stack 180-second calls.
pub async fn stop_child<F: std::future::Future<Output = ()>>(
    child: &Mutex<tokio::process::Child>,
    cleanup: F,
    grace: Duration,
    reap: Duration,
) {
    let _ = tokio::time::timeout(grace, async {
        cleanup.await;
        let _ = child.lock().await.wait().await;
    })
    .await;
    let mut child = child.lock().await;
    if child.try_wait().ok().flatten().is_none() {
        let _ = child.start_kill();
        let _ = tokio::time::timeout(reap, child.wait()).await;
    }
}

pub fn deadline(method: &str) -> Duration {
    Duration::from_secs(match method {
        "status" | "devices" | "history" | "summary" | "bootstrap" | "sample.cancel" => 10,
        "shutdown" | "service.stop" => 12,
        "service.start" | "settings.save" | "shortcut.check" => 20,
        "updates.stage" => 180,
        _ => 90,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{duplex, BufReader};
    #[tokio::test]
    async fn shutdown_bounds_stalled_cleanup_and_reaps_child() {
        let child = tokio::process::Command::new("sleep")
            .arg("60")
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let child = Mutex::new(child);
        let began = std::time::Instant::now();
        stop_child(
            &child,
            std::future::pending(),
            Duration::from_millis(20),
            Duration::from_millis(200),
        )
        .await;
        assert!(began.elapsed() < Duration::from_secs(1));
        assert!(child.lock().await.try_wait().unwrap().is_some());
    }
    #[tokio::test]
    async fn bounds_unterminated_frames_before_allocating_entire_stream() {
        let mut reader = BufReader::new(&b"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"[..]);
        assert!(read_frame(&mut reader, 8).await.is_err());
        assert_eq!(reader.buffer().len(), 23);
    }
    #[test]
    fn rejects_bad_versions_and_ambiguous_or_invalid_replies() {
        for frame in [
            r#"{"v":2,"id":1,"result":{}}"#,
            r#"{"v":1,"id":1}"#,
            r#"{"v":1,"id":1,"result":{},"error":"bad"}"#,
            r#"{"v":1,"id":1,"error":5}"#,
        ] {
            assert!(parse(frame.as_bytes()).is_err());
        }
        assert!(parse(br#"{"v":1,"id":1,"error":"Legacy failure"}"#).is_ok());
        assert!(parse(
            br#"{"v":1,"id":1,"error":"Denied","error_info":{"code":"permission","message":"Denied","retryable":false}}"#
        )
        .is_ok());
    }
    #[tokio::test]
    async fn stalled_write_is_bounded_and_pipe_is_poisoned() {
        let (input, _nonreading_child) = duplex(1);
        let requests = Requests::new(input);
        let result = requests
            .call("status", json!({}), Duration::from_millis(20))
            .await;
        assert_eq!(result.unwrap_err().code, "timeout");
        assert!(!requests.alive());
        assert!(requests.shared.pending.lock().unwrap().is_empty());
    }
    #[tokio::test]
    async fn timeout_after_complete_write_does_not_replay_or_poison() {
        let (input, mut child) = duplex(4096);
        let requests = Requests::new(input);
        assert_eq!(
            requests
                .call(
                    "control",
                    json!({"action":"start"}),
                    Duration::from_millis(20)
                )
                .await
                .unwrap_err()
                .code,
            "timeout"
        );
        assert!(requests.alive());
        let mut bytes = vec![0; 4096];
        let n = child.read(&mut bytes).await.unwrap();
        assert_eq!(bytes[..n].iter().filter(|b| **b == b'\n').count(), 1);
        assert!(requests.shared.pending.lock().unwrap().is_empty());
    }
    #[tokio::test]
    async fn abort_removes_pending_and_admission_is_bounded() {
        let (input, _child) = duplex(4096);
        let requests = Arc::new(Requests::new(input));
        let permits = requests.slots.acquire_many(64).await.unwrap();
        assert_eq!(
            requests
                .call("status", json!({}), Duration::from_secs(1))
                .await
                .unwrap_err()
                .code,
            "busy"
        );
        drop(permits);
        let copy = requests.clone();
        let task = tokio::spawn(async move {
            copy.call(
                "control",
                json!({"action":"start"}),
                Duration::from_secs(60),
            )
            .await
        });
        tokio::task::yield_now().await;
        assert_eq!(requests.shared.pending.lock().unwrap().len(), 1);
        task.abort();
        let _ = task.await;
        assert!(requests.shared.pending.lock().unwrap().is_empty());
    }
}
