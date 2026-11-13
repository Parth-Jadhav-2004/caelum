#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod graphics;

use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc,
    },
    time::Duration,
};
use tauri::{Emitter, Manager};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, Command},
    sync::{oneshot, Mutex},
};

type Reply = Result<Value, String>;
struct Engine {
    input: Mutex<ChildStdin>,
    child: Mutex<Child>,
    pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Reply>>>>,
    sequence: AtomicU64,
    alive: Arc<AtomicBool>,
}
impl Engine {
    async fn spawn(app: tauri::AppHandle) -> Result<Self, Box<dyn std::error::Error>> {
        let executable = std::env::current_exe()?
            .parent()
            .unwrap()
            .join("caelum-engine");
        let mut command = if cfg!(debug_assertions) {
            let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap();
            let mut cmd = Command::new(root.join(".venv/bin/python"));
            cmd.args(["-m", "caelum.sidecar"]);
            cmd
        } else {
            Command::new(executable)
        };
        graphics::configure_sidecar(&mut command);
        let mut child = command
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit())
            .kill_on_drop(true)
            .spawn()?;
        let input = child.stdin.take().ok_or("Missing engine stdin")?;
        let stdout = child.stdout.take().ok_or("Missing engine stdout")?;
        let pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Reply>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let replies = pending.clone();
        let alive = Arc::new(AtomicBool::new(true));
        let reader_alive = alive.clone();
        tauri::async_runtime::spawn(async move {
            let mut lines = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                if line.len() > 16 * 1_048_576 {
                    break;
                }
                let Ok(frame) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                if frame["v"] != 1 {
                    continue;
                }
                if let Some(id) = frame["id"].as_u64() {
                    if let Some(sender) = replies.lock().await.remove(&id) {
                        let result = match frame["error"].as_str() {
                            Some(error) => Err(error.to_string()),
                            None => Ok(frame["result"].clone()),
                        };
                        let _ = sender.send(result);
                    }
                } else if let Some(event) = frame["event"].as_str() {
                    if event == "status" {
                        if let Some(tray) = app.tray_by_id("caelum") {
                            let title = frame["data"]["title"].as_str().unwrap_or("Connecting…");
                            let _ = tray.set_tooltip(Some(format!("Caelum · {title}")));
                        }
                    }
                    if ["status", "microphone", "status-error"].contains(&event) {
                        let _ = app.emit(&format!("engine:{event}"), &frame["data"]);
                    }
                }
            }
            reader_alive.store(false, Ordering::SeqCst);
            for (_, sender) in replies.lock().await.drain() {
                let _ = sender.send(Err("Python engine disconnected. Restart Caelum.".into()));
            }
            let _ = app.emit("engine:disconnected", ());
        });
        Ok(Self {
            input: Mutex::new(input),
            child: Mutex::new(child),
            pending,
            sequence: AtomicU64::new(1),
            alive,
        })
    }
    async fn call(&self, method: &str, params: Value) -> Reply {
        if !self.alive.load(Ordering::SeqCst) {
            return Err("Python engine unavailable. Restart Caelum.".into());
        }
        let id = self.sequence.fetch_add(1, Ordering::SeqCst);
        let (sender, receiver) = oneshot::channel();
        self.pending.lock().await.insert(id, sender);
        let frame = format!(
            "{}\n",
            json!({"v":1,"id":id,"method":method,"params":params})
        );
        if frame.len() > 1_048_576 {
            self.pending.lock().await.remove(&id);
            return Err("Request too large".into());
        }
        let written = self.input.lock().await.write_all(frame.as_bytes()).await;
        if written.is_err() {
            self.pending.lock().await.remove(&id);
            return Err("Python engine disconnected".into());
        }
        let reply = tokio::time::timeout(Duration::from_secs(180), receiver).await;
        self.pending.lock().await.remove(&id);
        match reply {
            Ok(Ok(result)) => result,
            _ => Err("Engine request timed out or disconnected".into()),
        }
    }
    async fn close(&self) {
        let _ = self.call("sample.cancel", json!({})).await;
        let _ = self.call("shutdown", json!({"discard":true})).await;
        let _ = self.input.lock().await.shutdown().await;
        let mut child = self.child.lock().await;
        if tokio::time::timeout(Duration::from_secs(12), child.wait())
            .await
            .is_err()
        {
            let _ = child.kill().await;
        }
    }
}
struct Desktop {
    engine: Engine,
    quitting: AtomicBool,
    tray_available: AtomicBool,
}
#[tauri::command]
async fn backend(method: String, params: Value, state: tauri::State<'_, Desktop>) -> Reply {
    state.engine.call(&method, params).await
}
#[tauri::command]
async fn restart_app(
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
) -> Result<(), String> {
    if state.engine.alive.load(Ordering::SeqCst) {
        state.engine.call("shutdown", json!({})).await?;
    }
    state.quitting.store(true, Ordering::SeqCst);
    state.engine.close().await;
    app.restart();
}
#[tauri::command]
fn open_key_console() -> Result<(), String> {
    std::process::Command::new("xdg-open")
        .arg("https://console.groq.com/keys")
        .spawn()
        .map(|_| ())
        .map_err(|_| "Could not open your browser".into())
}
#[tauri::command]
async fn quit_app(
    discard: bool,
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
) -> Result<(), String> {
    if state.engine.alive.load(Ordering::SeqCst) {
        state
            .engine
            .call("shutdown", json!({"discard":discard}))
            .await?;
    }
    state.quitting.store(true, Ordering::SeqCst);
    state.engine.close().await;
    app.exit(0);
    Ok(())
}
fn show(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}
fn main() {
    graphics::configure();
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show(app)))
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            backend,
            quit_app,
            restart_app,
            open_key_console
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let engine = tauri::async_runtime::block_on(Engine::spawn(handle.clone()))?;
            app.manage(Desktop {
                engine,
                quitting: AtomicBool::new(false),
                tray_available: AtomicBool::new(false),
            });
            use tauri::menu::{Menu, MenuItem};
            let open = MenuItem::with_id(app, "open", "Open Caelum", true, None::<&str>)?;
            let pause = MenuItem::with_id(app, "pause", "Pause dictation", true, None::<&str>)?;
            let resume = MenuItem::with_id(app, "resume", "Resume dictation", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Caelum", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &pause, &resume, &quit])?;
            let icon = tauri::image::Image::new_owned(
                include_bytes!("../icons/tray.rgba").to_vec(),
                32,
                32,
            );
            let tray = tauri::tray::TrayIconBuilder::with_id("caelum")
                .icon(icon)
                .tooltip("Caelum · dictation")
                .menu(&menu)
                .on_menu_event(|app, event| {
                    let app = app.clone();
                    match event.id.as_ref() {
                        "open" => show(&app),
                        "quit" => {
                            show(&app);
                            let _ = app.emit("desktop:quit", ());
                        }
                        "pause" | "resume" => {
                            let action = event.id.as_ref().to_string();
                            tauri::async_runtime::spawn(async move {
                                let result = app
                                    .state::<Desktop>()
                                    .engine
                                    .call("control", json!({"action":action}))
                                    .await;
                                if let Err(error) = result {
                                    show(&app);
                                    let _ = app.emit("desktop:error", error);
                                }
                            });
                        }
                        _ => (),
                    }
                })
                .build(app);
            if tray.is_ok() {
                // A successfully created icon does not imply a registered tray watcher.
                let app = handle.clone();
                std::thread::spawn(move || loop {
                    let available = std::process::Command::new("gdbus")
                        .args([
                            "call",
                            "--timeout",
                            "2",
                            "--session",
                            "--dest",
                            "org.freedesktop.DBus",
                            "--object-path",
                            "/org/freedesktop/DBus",
                            "--method",
                            "org.freedesktop.DBus.NameHasOwner",
                            "org.kde.StatusNotifierWatcher",
                        ])
                        .output()
                        .map(|o| {
                            o.status.success()
                                && String::from_utf8_lossy(&o.stdout).contains("true")
                        })
                        .unwrap_or(false);
                    let state = app.state::<Desktop>();
                    let previous = state.tray_available.swap(available, Ordering::SeqCst);
                    if previous && !available {
                        let app = app.clone();
                        let copy = app.clone();
                        let _ = app.run_on_main_thread(move || show(&copy));
                    }
                    std::thread::sleep(Duration::from_secs(2));
                });
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let state = window.state::<Desktop>();
                if !state.quitting.load(Ordering::SeqCst) {
                    api.prevent_close();
                    if state.tray_available.load(Ordering::SeqCst) {
                        let _ = window.hide();
                    } else {
                        let _ = window.emit("desktop:quit", ());
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Failed to initialize Caelum")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                tauri::async_runtime::block_on(app.state::<Desktop>().engine.close());
            }
        });
}
