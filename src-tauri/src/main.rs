#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod graphics;
mod transport;
use transport::{EngineError, Frame, Reply, Requests};

use serde_json::{json, Value};
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};
use tauri::{Emitter, Manager};
use tokio::{
    io::BufReader,
    process::{Child, ChildStdin, Command},
    sync::Mutex,
};

struct Engine {
    requests: Arc<Requests<ChildStdin>>,
    child: Mutex<Child>,
    closed: AtomicBool,
    app: tauri::AppHandle,
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
        let app_handle = app.clone();
        let requests = Arc::new(Requests::new(input));
        let reader_requests = requests.clone();
        tauri::async_runtime::spawn(async move {
            let mut reader = BufReader::new(stdout);
            let failure = loop {
                let bytes = match transport::read_frame(&mut reader, transport::MAX_RESPONSE).await
                {
                    Ok(Some(bytes)) => bytes,
                    Ok(None) => {
                        break EngineError::new(
                            "disconnected",
                            "Python engine disconnected. Restart Caelum.",
                            false,
                        )
                    }
                    Err(error) => break error,
                };
                if !reader_requests.alive() {
                    break EngineError::new(
                        "disconnected",
                        "Python engine connection is unusable. Restart Caelum.",
                        false,
                    );
                }
                match transport::parse(&bytes) {
                    Ok(Frame::Reply(id, result)) => reader_requests.resolve(id, result),
                    Ok(Frame::Event(event, data)) => {
                        if event == "status" {
                            update_tray(&app, &data);
                        }
                        let _ = app.emit(&format!("engine:{event}"), data);
                    }
                    Err(error) => break error,
                }
            };
            reader_requests.fail(failure.clone());
            update_tray(
                &app,
                &json!({"state":"error", "title":"Caelum stopped", "running":false}),
            );
            let _ = app.emit("engine:disconnected", failure);
        });
        Ok(Self {
            requests,
            child: Mutex::new(child),
            closed: AtomicBool::new(false),
            app: app_handle,
        })
    }
    async fn call(&self, method: &str, params: Value) -> Reply {
        let result = self
            .requests
            .call(method, params, transport::deadline(method))
            .await;
        if !self.requests.alive() {
            if let Err(error) = &result {
                let _ = self.app.emit("engine:disconnected", error);
            }
        }
        result
    }
    async fn close(&self, shutdown_complete: bool) {
        if self.closed.swap(true, Ordering::SeqCst) {
            return;
        }
        // A completed shutdown has already stopped/reaped dictation and flushed
        // history. Read-only network workers can otherwise keep Python alive
        // until their socket timeout even after the window is ready to quit.
        let shutdown = tokio::time::timeout(Duration::from_secs(10), async {
            if !shutdown_complete {
                let _ = self.call("sample.cancel", json!({})).await;
                self.call("shutdown", json!({"discard":true})).await?;
            }
            Ok::<(), EngineError>(())
        })
        .await;
        transport::stop_child(
            &self.child,
            self.requests.finish_input(),
            if matches!(shutdown, Ok(Ok(()))) {
                Duration::from_millis(500)
            } else {
                Duration::from_secs(2)
            },
            Duration::from_secs(2),
        )
        .await;
        self.requests.fail(EngineError::new(
            "disconnected",
            "Caelum is shutting down",
            false,
        ));
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
    discard: Option<bool>,
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
) -> Result<(), EngineError> {
    let shutdown_complete = !discard.unwrap_or(false) && state.engine.requests.alive();
    if shutdown_complete {
        // The daemon atomically checks idle state and stops accepting captures.
        // Confirmed recovery may explicitly discard; ordinary update restarts may not.
        state
            .engine
            .call("shutdown", json!({"discard":false}))
            .await?;
    }
    state.quitting.store(true, Ordering::SeqCst);
    state.engine.close(shutdown_complete).await;
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
fn open_releases(version: Option<String>) -> Result<(), String> {
    std::process::Command::new("xdg-open")
        .arg(release_url(version.as_deref())?)
        .spawn()
        .map(|_| ())
        .map_err(|_| "Could not open your browser".into())
}
fn release_url(version: Option<&str>) -> Result<String, String> {
    let root = "https://github.com/Parth-Jadhav-2004/caelum/releases";
    match version {
        None => Ok(root.into()),
        Some(value)
            if value.len() <= 64
                && value.starts_with(|c: char| c.is_ascii_digit())
                && value
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-') =>
        {
            Ok(format!("{root}/tag/v{value}"))
        }
        _ => Err("Invalid release version".into()),
    }
}
#[tauri::command]
fn open_model_help() -> Result<(), String> {
    std::process::Command::new("xdg-open")
        .arg("https://github.com/Parth-Jadhav-2004/caelum#optional-whisper-component")
        .spawn()
        .map(|_| ())
        .map_err(|_| "Could not open your browser".into())
}
#[tauri::command]
async fn quit_app(
    discard: bool,
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
) -> Result<(), EngineError> {
    let shutdown_complete = !discard && state.engine.requests.alive();
    if shutdown_complete {
        state
            .engine
            .call("shutdown", json!({"discard":false}))
            .await?;
    }
    state.quitting.store(true, Ordering::SeqCst);
    state.engine.close(shutdown_complete).await;
    app.exit(0);
    Ok(())
}
struct TrayMenu {
    status: tauri::menu::MenuItem<tauri::Wry>,
    pause: tauri::menu::MenuItem<tauri::Wry>,
    start: tauri::menu::MenuItem<tauri::Wry>,
    paused: AtomicBool,
    last_status: std::sync::Mutex<String>,
}
fn update_tray(app: &tauri::AppHandle, data: &Value) {
    let paused = data["paused"].as_bool().unwrap_or(false);
    let running = data["running"].as_bool().unwrap_or(false);
    let state = data["state"].as_str().unwrap_or("hidden");
    let title = data["title"].as_str().unwrap_or("Ready");
    if let Some(menu) = app.try_state::<TrayMenu>() {
        // Audio level events do not change the tray. Avoid repeatedly rebuilding
        // its icon and menu over D-Bus while recording.
        let signature = json!([
            running,
            paused,
            state,
            title,
            data["hotkey"],
            data["pending_audio"]
        ])
        .to_string();
        if let Ok(mut last) = menu.last_status.lock() {
            if *last == signature {
                return;
            }
            *last = signature;
        }
        menu.paused.store(paused, Ordering::SeqCst);
        let status_line = data["hotkey"]
            .as_str()
            .map(|key| format!("{title} – {key}"))
            .unwrap_or_else(|| title.to_owned());
        let _ = menu.status.set_text(status_line);
        let _ = menu.pause.set_text(if paused {
            "Resume dictation"
        } else {
            "Pause dictation"
        });
        let _ = menu.pause.set_enabled(running);
        let _ = menu.start.set_enabled(
            running
                && !paused
                && !data["pending_audio"].as_bool().unwrap_or(false)
                && matches!(
                    state,
                    "hidden" | "success" | "unrefined" | "copied" | "cancelled" | "no_speech"
                ),
        );
    }
    if let Some(tray) = app.tray_by_id("caelum") {
        let _ = tray.set_tooltip(Some(format!("Caelum · {title}")));
        // A monochrome line mark changes shape; colour only signals an error.
        let mut pixels = include_bytes!("../icons/tray.rgba").to_vec();
        if state == "error" || paused || matches!(state, "starting" | "listening" | "recording") {
            pixels.fill(0);
            for y in 4usize..28 {
                for x in 4usize..28 {
                    let ink = if state == "error" {
                        (14..18).contains(&x) && ((6..19).contains(&y) || (23..26).contains(&y))
                    } else if paused {
                        ((9..13).contains(&x) || (19..23).contains(&x)) && (7..25).contains(&y)
                    } else if matches!(state, "starting" | "listening" | "recording") {
                        let height = [6, 12, 20, 12, 6][((x - 4) / 5).min(4)];
                        x % 5 < 2 && y.abs_diff(16) < height / 2
                    } else {
                        false
                    };
                    if ink {
                        let i = (y * 32 + x) * 4;
                        pixels[i..i + 4].copy_from_slice(if state == "error" {
                            &[242, 85, 90, 255]
                        } else {
                            &[237, 237, 239, 255]
                        });
                    }
                }
            }
        }
        let _ = tray.set_icon(Some(tauri::image::Image::new_owned(pixels, 32, 32)));
    }
}
#[tauri::command]
fn open_docs() -> Result<(), String> {
    std::process::Command::new("xdg-open")
        .arg("https://github.com/Parth-Jadhav-2004/caelum#readme")
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}
fn show(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}
#[tauri::command]
fn frontend_ready() {
    // Explicit opt-in test probe: no transcript, configuration or credential data.
    if std::env::var("CAELUM_SMOKE_TEST").as_deref() == Ok("1") {
        eprintln!("CAELUM_FRONTEND_READY_V1");
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
            open_releases,
            open_docs,
            open_model_help,
            restart_app,
            open_key_console,
            frontend_ready
        ])
        .setup(|app| {
            if std::env::var("CAELUM_SMOKE_TEST").as_deref() == Ok("1") {
                if let Some(window) = app.get_webview_window("main") {
                    let number = |name: &str, default: u32, minimum: u32, maximum: u32| {
                        std::env::var(name)
                            .ok()
                            .and_then(|value| value.parse::<u32>().ok())
                            .unwrap_or(default)
                            .clamp(minimum, maximum)
                    };
                    let _ = window.set_size(tauri::LogicalSize::new(
                        number("CAELUM_SMOKE_WIDTH", 1100, 480, 1600),
                        number("CAELUM_SMOKE_HEIGHT", 780, 480, 1200),
                    ));
                }
            }
            let handle = app.handle().clone();
            let engine = tauri::async_runtime::block_on(Engine::spawn(handle.clone()))?;
            app.manage(Desktop {
                engine,
                quitting: AtomicBool::new(false),
                tray_available: AtomicBool::new(false),
            });
            use tauri::menu::{Menu, MenuItem};
            let open = MenuItem::with_id(app, "open", "Open Caelum", true, None::<&str>)?;
            let pause = MenuItem::with_id(app, "pause", "Pause dictation", false, None::<&str>)?;
            let status = MenuItem::with_id(app, "status", "Connecting…", false, None::<&str>)?;
            let start = MenuItem::with_id(app, "start", "Start dictation", false, None::<&str>)?;
            let settings = MenuItem::with_id(app, "settings", "Settings…", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Caelum", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&status, &start, &pause, &open, &settings, &quit])?;
            app.manage(TrayMenu {
                status,
                start,
                pause,
                paused: AtomicBool::new(false),
                last_status: std::sync::Mutex::new(String::new()),
            });
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
                        "settings" => {
                            show(&app);
                            let _ = app.emit("desktop:settings", ());
                        }
                        "pause" | "start" => {
                            let action = if event.id.as_ref() == "start" {
                                "start"
                            } else if app.state::<TrayMenu>().paused.load(Ordering::SeqCst) {
                                "resume"
                            } else {
                                "pause"
                            };
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
                tauri::async_runtime::block_on(app.state::<Desktop>().engine.close(false));
            }
        });
}

#[cfg(test)]
mod release_link_tests {
    use super::release_url;

    #[test]
    fn release_links_stay_on_the_fixed_repository() {
        assert_eq!(
            release_url(Some("0.4.1-rc.2")).unwrap(),
            "https://github.com/Parth-Jadhav-2004/caelum/releases/tag/v0.4.1-rc.2"
        );
        assert_eq!(
            release_url(None).unwrap(),
            "https://github.com/Parth-Jadhav-2004/caelum/releases"
        );
        for value in [
            "",
            "../other",
            "https://example.com",
            "0.4.1?redirect=evil",
            "0.4.1/../../",
        ] {
            assert!(release_url(Some(value)).is_err());
        }
    }
}
