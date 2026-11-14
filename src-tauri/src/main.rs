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
                            if let Some(tray) = app.tray_by_id("caelum") {
                                let title = data["title"].as_str().unwrap_or("Connecting…");
                                let _ = tray.set_tooltip(Some(format!("Caelum · {title}")));
                            }
                        }
                        let _ = app.emit(&format!("engine:{event}"), data);
                    }
                    Err(error) => break error,
                }
            };
            reader_requests.fail(failure.clone());
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
    async fn close(&self) {
        if self.closed.swap(true, Ordering::SeqCst) {
            return;
        }
        // One overall graceful budget, including writes and requests. Reserve
        // two seconds for SIGKILL/reaping instead of stacking request timeouts.
        transport::stop_child(
            &self.child,
            async {
                let _ = self.call("sample.cancel", json!({})).await;
                let _ = self.call("shutdown", json!({"discard":true})).await;
                self.requests.finish_input().await;
            },
            Duration::from_secs(10),
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
    if !discard.unwrap_or(false) && state.engine.requests.alive() {
        // The daemon atomically checks idle state and stops accepting captures.
        // Confirmed recovery may explicitly discard; ordinary update restarts may not.
        state
            .engine
            .call("shutdown", json!({"discard":false}))
            .await?;
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
) -> Result<(), EngineError> {
    if !discard && state.engine.requests.alive() {
        state
            .engine
            .call("shutdown", json!({"discard":false}))
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
