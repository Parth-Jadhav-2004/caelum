"""Exercise the shipped Windows runtime over real stdio without a mic or network."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


async def online_setup():
    """Run Continue against a local model list and the actual Windows vault."""
    from caelum import credentials
    from caelum.config import Config, config_path, save
    from caelum.providers import ProviderError
    from caelum.sidecar import Backend

    config = Config()
    key_name = "CAELUM_TEST_" + uuid.uuid4().hex.upper()
    config.stt.key_env = config.cleanup.key_env = key_name
    key = uuid.uuid4().hex

    class Models(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != "/v1/models" or self.headers.get("Authorization") != f"Bearer {key}":
                self.send_error(401)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": config.stt.model}]}).encode())

    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
        "APPDATA": folder, "LOCALAPPDATA": folder, "NO_PROXY": "127.0.0.1",
    }), ThreadingHTTPServer(("127.0.0.1", 0), Models) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        config.stt.base_url = f"http://127.0.0.1:{server.server_port}/v1"
        save(config, config_path())
        backend = Backend(config_path())
        try:
            try:
                await backend.dispatch("setup.validate", {"consent": True, "keys": {key_name: "invalid"}})
            except ProviderError as exc:
                assert exc.kind == "invalid_key"
            else:
                raise AssertionError("Invalid key passed onboarding")
            assert credentials.get(key_name) is None
            result = await backend.dispatch("setup.validate", {"consent": True, "keys": {key_name: key}})
            assert result["storage"][key_name] == "keyring"
            assert credentials.get(key_name) == key
            assert key not in config_path().with_name("credentials.json").read_text()
            assert "Windows Credential Manager" in credentials.describe(key_name)["description"]
            # Only fail the vault write: exercise real current-user DPAPI in
            # both the embedded runtime and the installed application.
            import pywintypes

            replacement = uuid.uuid4().hex
            with patch("win32cred.CredWrite", side_effect=pywintypes.error(1312, "CredWrite", "offline")):
                assert credentials.store(key_name, replacement) == "dpapi"
            assert replacement not in config_path().with_name("credentials.json").read_text()
            assert credentials.get(key_name) == replacement
            assert credentials.describe(key_name)["storage"] == "dpapi"
        finally:
            server.shutdown()
            credentials.delete(key_name)
            await backend.models.aclose()


async def desktop_delivery():
    import win32clipboard
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
        focused = SimpleNamespace(top=edit, address=edit, pid=os.getpid(), output="")
        with patch("caelum.windows_desktop.focused_target", return_value=focused):
            original = await binding.target()
            assert await binding.insert("Unicode: café", original)
            assert win32gui.GetWindowText(edit) == "Unicode: café"
            original = await binding.target()
        with patch("caelum.windows_desktop.focused_target", return_value=None):
            assert not await binding.insert("manual paste", original)
            assert win32gui.GetWindowText(edit) == "Unicode: café"
            win32clipboard.OpenClipboard(hud.window)
            try:
                assert win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) == "manual paste"
            finally:
                win32clipboard.CloseClipboard()
        focus = win32gui.GetForegroundWindow()
        await hud.emit({"state": "recording", "history": [0.5] * 17})
        assert win32gui.GetForegroundWindow() == focus
    finally:
        win32gui.DestroyWindow(edit)
        await hud.close()


def main():
    from caelum import updates

    # Exercise the packaged trust policy with the Windows crypto backend.
    assert updates.trusted_public_keys(updates.BASE)
    methods = ["bootstrap", "status", "models.list", "history", "updates.pending", "shutdown"]
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
                        if method == "history":
                            assert frame["result"] == []
                        if method == "updates.pending":
                            assert frame["result"] is None
                        break
                else:
                    raise RuntimeError(f"Engine exited during {method}")
            child.stdin.close()
            assert child.wait(15) == 0
        # A read on first launch must not create a transcript database.
        assert not (Path(directory) / "Caelum/history.sqlite3").exists()


if __name__ == "__main__":
    import asyncio

    asyncio.run(desktop_delivery())
    asyncio.run(online_setup())
    main()
