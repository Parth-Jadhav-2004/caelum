"""Exercise the shipped Windows runtime over real stdio without a mic or network."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


async def desktop_delivery():
    import win32con
    import win32gui
    from caelum.config import App
    from caelum.windows_desktop import HUD, Bindings

    hud = HUD(App())
    await hud.start()
    edit = win32gui.CreateWindowEx(0, "EDIT", "", win32con.WS_POPUP, 0, 0, 100, 40, 0, 0, 0, None)
    try:
        binding = Bindings("CTRL + ALT + V", "hold")
        binding.core = SimpleNamespace(hud=hud)
        original = SimpleNamespace(top=edit, address=edit, pid=os.getpid(), output="")
        with patch("caelum.windows_desktop.focused_target", return_value=original):
            assert await binding.insert("Unicode: café", original)
            assert win32gui.GetWindowText(edit) == "Unicode: café"
        with patch("caelum.windows_desktop.focused_target", return_value=None):
            assert not await binding.insert("manual paste", original)
            assert win32gui.GetWindowText(edit) == "Unicode: café"
        focus = win32gui.GetForegroundWindow()
        await hud.emit({"state": "recording", "history": [0.5] * 17})
        assert win32gui.GetForegroundWindow() == focus
    finally:
        win32gui.DestroyWindow(edit)
        await hud.close()


def main():
    methods = ["bootstrap", "status", "models.list", "history", "shutdown"]
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "APPDATA": directory, "LOCALAPPDATA": directory}
        # Leave the pipe open until all replies arrive (EOF initiates shutdown).
        with subprocess.Popen([sys.executable, "-I", "-m", "caelum.sidecar"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, cwd=directory, env=env, text=True) as child:
            for i, method in enumerate(methods):
                params = {"discard": True} if method == "shutdown" else {}
                child.stdin.write(json.dumps({"v": 1, "id": i, "method": method, "params": params}) + "\n")
                child.stdin.flush()
                for line in child.stdout:
                    frame = json.loads(line)
                    if frame.get("id") == i:
                        assert "result" in frame, (method, frame)
                        break
                else:
                    raise RuntimeError(f"Engine exited during {method}")
            child.stdin.close()
            assert child.wait(15) == 0
        assert (Path(directory) / "Caelum/history.sqlite3").exists()


if __name__ == "__main__":
    import asyncio

    asyncio.run(desktop_delivery())
    main()
