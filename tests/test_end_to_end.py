"""Exercise capture → HTTP contracts → cleanup → saved result through real services.

The microphone and provider network are deterministic doubles; no user data/upload.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from caelum.config import Config, save
from caelum.history import History
from caelum.linux import Target
from caelum.orchestrator import Orchestrator
from caelum.providers import Providers


async def test_record_transcribe_cleanup_save_search_export_delete(tmp_path, monkeypatch):
    config = Config()
    config.app.backend = "portable"
    config.cleanup.model = "openai/gpt-oss-20b"
    path = tmp_path / "settings.toml"
    save(config, path)
    history = History(path)

    class Capture:
        size = 32000
        speech_ms = 500
        error = None
        full = False
        level = 0.4
        history = [0.4] * 17

        def __init__(self, app):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def snapshot(self):
            return b"\0" * self.size

        def discard(self):
            pass

    calls = []

    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/audio/transcriptions"):
            assert b"RIFF" in request.content
            return httpx.Response(200, json={"text": "a little less typing", "words": []})
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "A little less typing."}}]}
        )

    monkeypatch.setattr("caelum.orchestrator.Capture", Capture)
    monkeypatch.setattr("caelum.orchestrator.notify", AsyncMock())
    bindings = SimpleNamespace(
        save_only=True,
        active=AsyncMock(),
        locked=AsyncMock(return_value=False),
        target=AsyncMock(return_value=Target("", -1, -1, "")),
    )
    hud = SimpleNamespace(emit=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client, credential_resolver=lambda name: "test-only")
        core = Orchestrator(config, provider, hud, bindings)
        core.media = SimpleNamespace(pause=AsyncMock(), resume=AsyncMock())

        async def completed(session, text, metrics, refined, copied):
            return await asyncio.to_thread(
                history.record, session, text, metrics, config, refined, copied
            )

        core.on_completed = completed
        await core.handle("start")
        assert core.state == "listening"
        await core.handle("stop")
        await core.work
        assert core.state == "saved"
        assert core.pcm is None
        assert len(calls) == 2
        entries = history.read("less typing")
        assert entries[0]["final_transcript"] == "A little less typing."
        assert entries[0]["refined"] == 1
        assert history.summary()["total_words"] == 4
        export = tmp_path / "export.jsonl"
        history.export(export)
        assert "A little less typing." in export.read_text()
        history.delete(entries[0]["id"])
        assert not history.read()
        assert history.summary()["total_words"] == 4
        assert "typing" not in str(hud.emit.await_args_list)
        await core.cancel(feedback=False)
