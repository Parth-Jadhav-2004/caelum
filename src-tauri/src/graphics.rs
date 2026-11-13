//! Work around WebKitGTK/NVIDIA's missing Wayland acquire timeline before GTK starts.
//! https://v2.tauri.app/develop/debug/linux-graphics/
use std::sync::atomic::{AtomicBool, Ordering};

static AUTOMATIC_SYNC_WORKAROUND: AtomicBool = AtomicBool::new(false);

fn needs_sync_workaround(
    wayland: bool,
    nvidia_loaded: bool,
    backend: Option<&str>,
    explicitly_configured: bool,
) -> bool {
    let prefers_x11 = backend
        .and_then(|value| value.split(',').next())
        .is_some_and(|value| value.trim() == "x11");
    wayland && nvidia_loaded && !prefers_x11 && !explicitly_configured
}

pub fn configure() {
    #[cfg(target_os = "linux")]
    {
        let wayland = std::env::var_os("WAYLAND_DISPLAY").is_some_and(|value| !value.is_empty());
        let nvidia_loaded = std::path::Path::new("/sys/module/nvidia").is_dir();
        let backend = std::env::var("GDK_BACKEND").ok();
        if needs_sync_workaround(
            wayland,
            nvidia_loaded,
            backend.as_deref(),
            std::env::var_os("__NV_DISABLE_EXPLICIT_SYNC").is_some(),
        ) {
            // Called from main before Tauri/GTK creates threads or a WebView.
            std::env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
            AUTOMATIC_SYNC_WORKAROUND.store(true, Ordering::Relaxed);
            eprintln!("Caelum: enabled NVIDIA Wayland explicit-sync workaround for WebKitGTK");
        }
    }
}

pub fn configure_sidecar(command: &mut tokio::process::Command) {
    if AUTOMATIC_SYNC_WORKAROUND.load(Ordering::Relaxed) {
        // Leave capture and the separate GTK4 layer-shell helper on their normal path.
        // Explicitly user-configured overrides are preserved instead.
        command.env_remove("__NV_DISABLE_EXPLICIT_SYNC");
    }
}

#[cfg(test)]
mod tests {
    use super::needs_sync_workaround;

    #[test]
    fn applies_to_nvidia_wayland_including_hybrid_systems() {
        assert!(needs_sync_workaround(true, true, None, false));
        assert!(needs_sync_workaround(
            true,
            true,
            Some("wayland,x11,*"),
            false
        ));
    }

    #[test]
    fn leaves_other_drivers_and_x11_unchanged() {
        assert!(!needs_sync_workaround(true, false, None, false));
        assert!(!needs_sync_workaround(false, true, None, false));
        assert!(!needs_sync_workaround(true, true, Some("x11"), false));
        assert!(!needs_sync_workaround(
            true,
            true,
            Some("x11,wayland"),
            false
        ));
    }

    #[test]
    fn preserves_explicit_user_overrides_including_opt_out() {
        assert!(!needs_sync_workaround(true, true, None, true));
    }
}
