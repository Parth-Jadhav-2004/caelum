"""Render the packaged WebKit main window in an isolated Xvfb/D-Bus session.

Requires Xvfb, dbus-run-session and ImageMagick. Does not automate a user's desktop,
record audio, or contact providers. Inspect the PNG; liveness alone is not visual QA.
"""

import argparse
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def check(package, xvfb, screenshot, completed_setup=False):
    package = package.resolve()
    screenshot = screenshot.resolve()
    with tempfile.TemporaryDirectory(prefix="caelum-native-smoke-") as directory:
        work = Path(directory)
        for folder in ("config", "data", "runtime"):
            (work / folder).mkdir(mode=0o700)
        (work / "config/config.toml").write_text('[desktop]\ntheme="dark"\n')
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
        }
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
                    "1280x900x24",
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
                with os.fdopen(read_fd) as display:
                    env["DISPLAY"] = ":" + display.readline().strip()
                app = subprocess.Popen(
                    ["dbus-run-session", "--", str(package / "usr/bin/caelum-desktop")],
                    env=env,
                    stdout=app_log,
                    stderr=app_log,
                    start_new_session=True,
                )
                time.sleep(8)
                if app.poll() is not None:
                    raise RuntimeError("Native window exited; check target distro libraries")
                subprocess.run(
                    [
                        "magick",
                        "import",
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
                if app and app.poll() is None:
                    os.killpg(app.pid, signal.SIGTERM)
                    app.wait(timeout=10)
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
    args = parser.parse_args()
    if not args.xvfb:
        parser.error("Install Xvfb or provide --xvfb /path/to/Xvfb")
    check(args.package, args.xvfb, args.screenshot, args.completed_setup)
