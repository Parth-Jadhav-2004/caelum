import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from caelum.service import lock_monitor


@pytest.mark.parametrize("audio", ["capture", "pcm"])
async def test_linux_manual_result_polls_slowly_until_audio_needs_protection(monkeypatch, audio):
    core = SimpleNamespace(capture=None, pcm=None, manual_result=None, handle=AsyncMock())
    now = 0.0
    probes = []

    async def locked():
        probes.append(now)
        if now >= 3:
            raise OSError("lock status unavailable")
        return False

    async def sleep(delay):
        nonlocal now
        now = round(now + delay, 6)
        if now >= 3.2:
            raise asyncio.CancelledError
        if now >= 2.6:
            core.manual_result = None
            setattr(core, audio, object())
        elif now >= 0.2:
            core.manual_result = "ready"

    monkeypatch.setattr("caelum.service.sys.platform", "linux")
    monkeypatch.setattr(asyncio.get_running_loop(), "time", lambda: now)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await lock_monitor(core, locked)

    assert probes == [0.2, 2.2, 2.6, 2.8, 3.0]
    core.handle.assert_awaited_once_with("cancel")
