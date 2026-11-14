"""Render the packaged WebKit main window in an isolated Xvfb/D-Bus session.

Requires Xvfb, dbus-run-session and ImageMagick. Does not automate a user's desktop,
record audio, or contact providers. Inspect the PNG; liveness alone is not visual QA.
"""

import argparse
import json
import os
import select
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path


def process_memory(wrapper_pid):
    rows = subprocess.check_output(["ps", "-eo", "pid=,ppid=,rss=,comm="], text=True)
    processes = {}
    for row in rows.splitlines():
        pid, parent, rss, name = row.split(maxsplit=3)
        processes[int(pid)] = (int(parent), int(rss), name)

    def descendants(root):
        result = {root}
        while True:
            updated = result | {
                pid for pid, (parent, _, _) in processes.items() if parent in result
            }
            if updated == result:
                return result
            result = updated

    owned = descendants(wrapper_pid)
    main = next(
        (pid for pid in owned if processes.get(pid, (0, 0, ""))[2] == "caelum-desktop"), None
    )
    if main is None:
        raise RuntimeError("Cannot identify native app for memory sampling")
    owned = descendants(main)
    pss, covered = 0, 0
    for pid in owned:
        try:
            lines = Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines()
            pss += int(next(line.split()[1] for line in lines if line.startswith("Pss:")))
            covered += 1
        except (OSError, StopIteration):
            pass
    return {
        "processes": len(owned),
        "rss_kib": sum(processes[pid][1] for pid in owned if pid in processes),
        "pss_kib": pss if covered else None,
        "pss_processes_covered": covered,
    }


def check(
    package,
    xvfb,
    screenshot,
    completed_setup=False,
    theme="t3-code",
    appearance="dark",
    *,
    metrics=None,
    width=1100,
    height=780,
    scale=1,
):
    package = package.resolve()
    screenshot = screenshot.resolve()
    with tempfile.TemporaryDirectory(prefix="caelum-native-smoke-") as directory:
        work = Path(directory)
        for folder in ("config", "data", "runtime"):
            (work / folder).mkdir(mode=0o700)
        (work / "config/config.toml").write_text(
            f'[desktop]\ntheme="{appearance}"\ncolor_theme="{theme}"\n'
        )
        if completed_setup:
            (work / "config/onboarding.json").write_text('{"stage":4,"complete":true}')
        env = {
            **os.environ,
            "GDK_BACKEND": "x11",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "XDG_CONFIG_HOME": str(work / "config"),
            "XDG_DATA_HOME": str(work / "data"),
            "XDG_RUNTIME_DIR": str(work / "runtime"),
            "CAELUM_CONFIG": str(work / "config/config.toml"),
            "WEBKIT_DISABLE_DMABUF_RENDERER": "1",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "CAELUM_SMOKE_TEST": "1",
            "CAELUM_SMOKE_WIDTH": str(width),
            "CAELUM_SMOKE_HEIGHT": str(height),
            "GDK_SCALE": str(scale),
        }
        if os.geteuid() == 0:
            # Only for ephemeral root CI containers, never the normal launcher.
            env["WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"] = "1"
        for name in (
            "WAYLAND_DISPLAY",
            "HYPRLAND_INSTANCE_SIGNATURE",
            "GROQ_API_KEY",
            "WEBKIT_INSPECTOR_SERVER",
        ):
            env.pop(name, None)
        with (work / "display.log").open("w") as output, (work / "app.log").open("w") as app_log:
            # -displayfd reserves a free display without racing another test.
            read_fd, write_fd = os.pipe()
            server = subprocess.Popen(
                [
                    xvfb,
                    "-displayfd",
                    str(write_fd),
                    "-screen",
                    "0",
                    f"{1280 * scale}x{900 * scale}x24",
                    "-nolisten",
                    "tcp",
                ],
                pass_fds=(write_fd,),
                env=env,
                stdout=output,
                stderr=output,
            )
            os.close(write_fd)
            app = None
            try:
                if not select.select([read_fd], [], [], 10)[0]:
                    os.close(read_fd)
                    raise RuntimeError("Xvfb did not become ready within 10 seconds")
                with os.fdopen(read_fd) as display:
                    env["DISPLAY"] = ":" + display.readline().strip()
                launch_started = time.monotonic()
                app = subprocess.Popen(
                    ["dbus-run-session", "--", str(package / "usr/bin/caelum-desktop")],
                    env=env,
                    stdout=app_log,
                    stderr=app_log,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 30
                while "CAELUM_FRONTEND_READY_V1" not in (work / "app.log").read_text():
                    if app.poll() is not None:
                        raise RuntimeError("Native window exited; inspect the smoke log")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "React/bootstrap IPC did not become ready within 30 seconds"
                        )
                    time.sleep(0.1)
                ready_ms = round((time.monotonic() - launch_started) * 1000, 2)
                if app.poll() is not None:
                    raise RuntimeError("Native window exited after frontend readiness")
                time.sleep(0.3)
                if metrics:
                    info = process_memory(app.pid)
                    info.update(
                        {
                            "ready_ms": ready_ms,
                            "width": width,
                            "height": height,
                            "scale": scale,
                            "theme": theme,
                            "appearance": appearance,
                            "scope": "Tauri and descendants; excludes D-Bus helpers",
                        }
                    )
                    metrics.write_text(json.dumps(info, indent=2) + "\n")
                subprocess.run(
                    [
                        *(["magick", "import"] if shutil.which("magick") else ["import"]),
                        "-display",
                        env["DISPLAY"],
                        "-window",
                        "root",
                        str(screenshot),
                    ],
                    check=True,
                    env=env,
                )
            finally:
                if app:
                    with suppress(ProcessLookupError):
                        os.killpg(app.pid, signal.SIGTERM)
                    try:
                        app.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        with suppress(ProcessLookupError):
                            os.killpg(app.pid, signal.SIGKILL)
                        app.wait(timeout=2)
                shutil.copy2(work / "app.log", screenshot.with_suffix(".log"))
                server.terminate()
                server.wait(timeout=5)
    print(f"Native window captured for visual inspection: {screenshot}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--xvfb", default=shutil.which("Xvfb"))
    parser.add_argument("--screenshot", type=Path, default=Path("/tmp/caelum-native-smoke.png"))
    parser.add_argument(
        "--completed-setup",
        action="store_true",
        help="Render dashboard; absent temporary credentials prevent service capture",
    )
    parser.add_argument(
        "--theme",
        choices=("t3-code", "t3-chat", "grove", "ocean", "ember", "iris", "caelum"),
        default="t3-code",
    )
    parser.add_argument("--appearance", choices=("dark", "light"), default="dark")
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--height", type=int, default=780)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if not args.xvfb:
        parser.error("Install Xvfb or provide --xvfb /path/to/Xvfb")
    check(
        args.package,
        args.xvfb,
        args.screenshot,
        args.completed_setup,
        args.theme,
        args.appearance,
        metrics=args.metrics,
        width=args.width,
        height=args.height,
        scale=args.scale,
    )
