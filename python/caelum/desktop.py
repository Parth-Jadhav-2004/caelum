"""Compatibility imports for desktop operations; the only main UI is Tauri."""
from .desktop_services import *  # noqa: F403


def run(path=None):
    import os
    import shutil
    import subprocess

    binary = shutil.which("caelum-desktop")
    if not binary:
        raise RuntimeError("Build the desktop with npm run tauri build, or use npm run tauri dev")
    env = os.environ.copy()
    if path:
        env["CAELUM_CONFIG"] = str(path)
    subprocess.run([binary], env=env, check=True)
