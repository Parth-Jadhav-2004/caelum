import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, load, save, validate
from caelum.desktop_services import CONTROL_FRAME_LIMIT, request
from caelum.service import reload_settings


@pytest.fixture
def context(tmp_path):
    original = Config()
    core = SimpleNamespace(
        config=original, control_lock=asyncio.Lock(), capture=None, pcm=None, work=None
    )
    bindings = SimpleNamespace(hotkey=original.app.hotkey, remove=AsyncMock(), install=AsyncMock())
    provider = SimpleNamespace(config=original)
    updated = Config()
    updated.app.hotkey = "CTRL + ALT + D"
    updated.app.microphone = "USB mic"
    path = tmp_path / "config.toml"
    save(updated, path)
    return core, bindings, provider, path


async def test_reload_updates_runtime_and_microphone(context):
    core, bindings, provider, path = context
    await reload_settings(core, bindings, provider, path)
    assert bindings.hotkey == core.config.app.hotkey == "CTRL + ALT + D"
    assert provider.config is core.config
    assert core.config.app.microphone == "USB mic"
    bindings.remove.assert_awaited_once()
    bindings.install.assert_awaited_once()


async def test_conflict_restores_previous_shortcut_and_runtime(context):
    core, bindings, provider, path = context
    original = core.config
    bindings.install.side_effect = [RuntimeError("Collision"), None]
    with pytest.raises(RuntimeError, match="Collision"):
        await reload_settings(core, bindings, provider, path)
    assert bindings.hotkey == original.app.hotkey
    assert core.config is provider.config is original
    assert bindings.install.await_count == 2


async def test_portal_edit_is_saved_without_disturbing_current_session(context):
    core, bindings, provider, path = context
    bindings.save_only = True
    session_key = bindings.hotkey
    updated = load(path)
    save(core.config, path)

    await reload_settings(core, bindings, provider, path, updated, persist=True)
    assert bindings.hotkey == session_key != load(path).app.hotkey
    assert core.config.app.microphone == "USB mic"
    await reload_settings(core, bindings, provider, path)
    bindings.remove.assert_not_awaited()
    bindings.install.assert_not_awaited()


@pytest.mark.parametrize("attribute", ["capture", "pcm", "work"])
async def test_active_session_rejects_reload(context, attribute):
    core, bindings, provider, path = context
    setattr(
        core, attribute, b"pending" if attribute == "pcm" else SimpleNamespace(done=lambda: False)
    )
    with pytest.raises(RuntimeError, match="Finish or cancel"):
        await reload_settings(core, bindings, provider, path)
    bindings.remove.assert_not_awaited()


async def test_reload_recording_mode_without_changing_shortcut(context):
    core, bindings, provider, path = context
    updated = Config()
    updated.app.recording_mode = "toggle"
    save(updated, path)
    await reload_settings(core, bindings, provider, path)
    assert bindings.recording_mode == core.config.app.recording_mode == "toggle"
    bindings.remove.assert_awaited_once()
    bindings.install.assert_awaited_once()


async def test_large_unicode_dictionary_crosses_settings_socket(tmp_path, monkeypatch):
    import tempfile

    config = Config()
    config.cleanup.replacements = {f"{i:03d}" + "界" * 197: "🪐" * 1000 for i in range(200)}
    validate(config)
    data = asdict(config)
    received = []

    async def handle(reader, writer):
        received.append(json.loads(await reader.readline()))
        writer.write(b'{"ok":true}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    # Keep the AF_UNIX path below the platform limit even in long CI worktrees.
    with tempfile.TemporaryDirectory() as runtime:
        monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
        directory = Path(runtime) / "caelum"
        directory.mkdir()
        async with await asyncio.start_unix_server(handle, directory / "control.sock", limit=CONTROL_FRAME_LIMIT):
            assert await asyncio.to_thread(request, "settings", config=data) == {"ok": True}
    assert received == [{"action": "settings", "config": data}]
