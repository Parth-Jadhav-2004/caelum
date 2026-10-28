import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from caelum.config import Config, save
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


@pytest.mark.parametrize("attribute", ["capture", "pcm", "work"])
async def test_active_session_rejects_reload(context, attribute):
    core, bindings, provider, path = context
    setattr(
        core, attribute, b"pending" if attribute == "pcm" else SimpleNamespace(done=lambda: False)
    )
    with pytest.raises(RuntimeError, match="Finish or cancel"):
        await reload_settings(core, bindings, provider, path)
    bindings.remove.assert_not_awaited()
