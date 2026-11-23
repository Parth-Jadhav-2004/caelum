import asyncio
import hashlib
import io
import json
import os
import tarfile
from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest
from caelum import models
from caelum.local_stt import LocalEngine
from caelum.providers import ProviderError


@pytest.fixture
def tiny_catalog(monkeypatch):
    payload = b"verified speech weights"
    item = {"path": "model.bin", "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "role": "model"}
    model = {
        "id": "test-model", "revision": "pinned-commit", "files": [item],
        "download_bytes": len(payload), "disk_bytes": len(payload), "min_disk_free_mb": 0,
        "requires_extra": None,
        "sources": [{"kind": "files", "base": "https://huggingface.co/test/resolve/pinned/"}],
    }
    monkeypatch.setattr(models, "catalog", lambda: {"version": 1, "models": [model]})
    return model, payload


def corrupt_weights(path, *, preserve_mtime):
    before = path.stat()
    path.write_bytes(b"x" * before.st_size)
    mtime = before.st_mtime_ns if preserve_mtime else before.st_mtime_ns - 60_000_000_000
    os.utime(path, ns=(before.st_atime_ns, mtime))


def test_shipped_catalog_is_pinned_and_consistent():
    data = models.catalog()
    assert [model["id"] for model in data["models"]] == [
        "parakeet-v3", "parakeet-110m", "cohere-transcribe", "whisper-turbo"
        , "parakeet-v2", "canary-180m", "distil-large-v3.5", "whisper-large-v3", "moonshine-base"
    ]
    for model in data["models"]:
        assert model["disk_bytes"] == sum(item["bytes"] for item in model["files"])
        for source in model["sources"]:
            if source["kind"] == "files":
                assert f"/resolve/{model['revision']}/" in source["base"]
            else:
                assert len(source["sha256"]) == 64
                assert source["bytes"] > 0


async def test_download_verifies_receipt_and_skips_installed(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    handler = Mock(return_value=httpx.Response(200, content=payload))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        events = []
        manager = models.ModelManager(tmp_path, client, events.append)
        path = await manager.download(model["id"])
        states = [event["state"] for event in events]
        assert states.index("verifying") < states.index("installing") < states.index("ready")
        assert models.installed(model["id"], tmp_path)
        assert models.verify(model["id"], tmp_path) == {"ok": True, "bad_files": []}
        assert json.loads((path / "receipt.json").read_text())["revision"] == "pinned-commit"
        assert not (tmp_path / ".download" / model["id"]).exists()
        await manager.download(model["id"])
        assert handler.call_count == 1
        # Modified time invalidates the quick scan without rehashing.
        corrupt_weights(path / "model.bin", preserve_mtime=False)
        assert not models.installed(model["id"], tmp_path)
        assert models.verify(model["id"], tmp_path) == {"ok": False, "bad_files": ["model.bin"]}
        assert manager.remove(model["id"]) > len(payload)
        assert not models.installed(model["id"], tmp_path)


@pytest.mark.parametrize("accept_range", [True, False])
async def test_resume_handles_206_and_200(tmp_path, tiny_catalog, accept_range):
    model, payload = tiny_catalog
    work = tmp_path / ".download" / model["id"]
    work.mkdir(parents=True)
    (work / "model.bin.part").write_bytes(payload[:7])

    def serve(request):
        assert request.headers["Range"] == "bytes=7-"
        if accept_range:
            return httpx.Response(206, content=payload[7:],
                                  headers={"Content-Range": f"bytes 7-{len(payload)-1}/{len(payload)}"})
        return httpx.Response(200, content=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        path = await models.ModelManager(tmp_path, client).download(model["id"])
        assert (path / "model.bin").read_bytes() == payload


async def test_checksum_falls_back_once_and_never_installs_bad_files(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    model["sources"].append({"kind": "files", "base": "https://mirror.example/"})
    calls = []

    def serve(request):
        calls.append(request.url.host)
        return httpx.Response(200, content=payload if request.url.host == "mirror.example"
                              else b"x" * len(payload))

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        await models.ModelManager(tmp_path, client).download(model["id"])
    assert calls == ["huggingface.co", "mirror.example"]


async def test_bad_checksum_keeps_no_receipt(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * len(payload)))
    ) as client:
        with pytest.raises(models.ModelError) as error:
            await models.ModelManager(tmp_path, client).download(model["id"])
    assert error.value.code == "checksum"
    assert not models.installed(model["id"], tmp_path)
    assert not (tmp_path / ".download" / model["id"] / "model.bin.part").exists()


def make_archive(model, payload, attack=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as tar:
        member = tarfile.TarInfo("top/model.bin")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
        if attack:
            member = tarfile.TarInfo(attack)
            if attack == "top/link":
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/unsafe"
            elif attack == "top/hardlink":
                member.type = tarfile.LNKTYPE
                member.linkname = "top/model.bin"
            tar.addfile(member)
    data = buffer.getvalue()
    model["sources"] = [{
        "kind": "archive", "url": "https://example.test/model.tar.bz2",
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "strip": 1,
    }]
    return data


async def test_archive_is_verified_extracted_and_receipted(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    archive = make_archive(model, payload)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive))
    ) as client:
        await models.ModelManager(tmp_path, client).download(model["id"])
    assert models.verify(model["id"], tmp_path)["ok"]


@pytest.mark.parametrize("attack", [
    "/absolute", "top/../../escape", "top/link", "top/hardlink",
])
async def test_unsafe_archives_never_install(tmp_path, tiny_catalog, attack):
    model, payload = tiny_catalog
    archive = make_archive(model, payload, attack)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive))
    ) as client:
        with pytest.raises(models.ModelError) as error:
            await models.ModelManager(tmp_path, client).download(model["id"])
    assert error.value.code == "extract"
    assert not models.installed(model["id"], tmp_path)
    assert not (tmp_path / "escape").exists()


async def test_disk_preflight_never_calls_http(tmp_path, tiny_catalog, monkeypatch):
    model, _ = tiny_catalog
    monkeypatch.setattr(models.shutil, "disk_usage", lambda _: type("Disk", (), {"free": 0})())
    handler = Mock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(models.ModelError) as error:
            await models.ModelManager(tmp_path, client).download(model["id"])
    assert error.value.code == "disk_full"
    handler.assert_not_called()


async def test_offline_error_is_sanitized_and_part_is_kept(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    work = tmp_path / ".download" / model["id"]
    work.mkdir(parents=True)
    part = work / "model.bin.part"
    part.write_bytes(payload[:5])

    def disconnected(request):
        raise httpx.ConnectError("secret signed redirect URL", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(disconnected)) as client:
        with pytest.raises(models.ModelError) as error:
            await models.ModelManager(tmp_path, client).download(model["id"])
    assert error.value.code == "offline"
    assert "secret" not in str(error.value)
    assert part.read_bytes() == payload[:5]


async def test_unknown_id_cannot_escape_root(tmp_path):
    with pytest.raises(models.ModelError, match="Unknown"):
        await models.ModelManager(tmp_path).download("../escape")


def test_receipt_required_and_revision_checked(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    path = tmp_path / model["id"]
    path.mkdir()
    (path / "model.bin").write_bytes(payload)
    assert not models.installed(model["id"], tmp_path)
    (path / "receipt.json").write_text(json.dumps({
        "id": model["id"], "catalog_version": 1, "revision": "different",
        "files": model["files"],
    }))
    assert not models.installed(model["id"], tmp_path)


async def test_queue_pause_cancel_resume_and_one_active(tmp_path, tiny_catalog, monkeypatch):
    model, payload = tiny_catalog
    second = deepcopy(model)
    second["id"] = "second-model"
    monkeypatch.setattr(models, "catalog", lambda: {"version": 1, "models": [model, second]})
    events, order = [], []
    first_started, second_started = asyncio.Event(), asyncio.Event()
    release_second = asyncio.Event()
    manager = models.ModelManager(tmp_path, progress=events.append)

    async def download(model_id):
        order.append(model_id)
        if model_id == model["id"]:
            work = tmp_path / ".download" / model_id
            work.mkdir(parents=True, exist_ok=True)
            (work / "model.bin.part").write_bytes(payload[:4])
            first_started.set()
            await asyncio.Event().wait()
        else:
            assert not (tmp_path / ".download" / model["id"]).exists()
            second_started.set()
            await release_second.wait()

    monkeypatch.setattr(manager, "download", download)
    await manager.submit(model["id"])
    await first_started.wait()
    await manager.submit(second["id"])
    assert manager.states[second["id"]]["state"] == "queued"
    await manager.cancel(model["id"])
    await second_started.wait()
    assert manager.states[model["id"]]["state"] == "cancelled"
    assert order == [model["id"], second["id"]]
    release_second.set()
    await manager.aclose()


async def test_pause_resume_cancel_tracks_only_the_requested_transfer(tmp_path, tiny_catalog, monkeypatch):
    model, _ = tiny_catalog
    chunk = b"x" * (1024 * 1024)
    total = 3 * len(chunk)
    model.update(download_bytes=total, disk_bytes=total)
    model["files"][0].update(bytes=total, sha256=hashlib.sha256(chunk * 3).hexdigest())
    other = {**model, "id": "not-selected"}
    monkeypatch.setattr(models, "catalog", lambda: {"version": 1, "models": [model, other]})
    ranges = []
    chunks_written = asyncio.Queue()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield chunk
            chunks_written.put_nowait(True)
            await asyncio.Event().wait()

    def serve(request):
        ranges.append(request.headers["Range"])
        offset = (len(ranges) - 1) * len(chunk)
        return httpx.Response(206, headers={"Content-Range": f"bytes {offset}-{total-1}/{total}"},
                              stream=Stream())

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        manager = models.ModelManager(tmp_path, client)
        try:
            await manager.recover()
            assert not ranges and not manager.states
            for index in (1, 2):
                await manager.submit(model["id"])
                await asyncio.wait_for(chunks_written.get(), 2)
                progress = manager.states[model["id"]]
                assert (progress["state"], progress["received_bytes"], progress["total_bytes"]) == (
                    "downloading", index * len(chunk), total)
                if index == 1:
                    await manager.pause(model["id"])
                    assert manager.states[model["id"]]["state"] == "paused"
                    assert models.ModelManager(tmp_path).states[model["id"]]["received_bytes"] == len(chunk)
            await manager.cancel(model["id"])
            assert manager.states[model["id"]]["state"] == "cancelled"
            assert set(manager.states) == {model["id"]}
            assert not list((tmp_path / ".download").iterdir())
            assert ranges == ["bytes=0-", f"bytes={len(chunk)}-"]
        finally:
            await manager.aclose()


async def test_restart_restores_paused_and_rechecks_corrupt_receipt(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=payload)
    )) as client:
        await models.ModelManager(tmp_path, client).download(model["id"])
    work = tmp_path / ".download" / model["id"]
    work.mkdir(parents=True)
    (work / "model.bin.part").write_bytes(payload[:4])
    corrupt_weights(tmp_path / model["id"] / "model.bin", preserve_mtime=False)
    manager = models.ModelManager(tmp_path)
    assert manager.states[model["id"]]["state"] == "paused"
    await manager.recover()
    assert not models.installed(model["id"], tmp_path)
    assert not (tmp_path / model["id"] / "receipt.json").exists()


async def test_pin_rehashes_changed_source_without_installing(tmp_path, tiny_catalog):
    model, _ = tiny_catalog
    changed = b"new revision"
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=changed)
    )) as client:
        result = await models.pin(model["id"], client)
    assert result["files"][0]["sha256"] == hashlib.sha256(changed).hexdigest()
    assert result["files"][0]["bytes"] == len(changed)
    assert not models.models_dir().exists()


def test_progress_is_throttled_but_state_transitions_are_not(tmp_path, tiny_catalog, monkeypatch):
    clock = [1.0]
    monkeypatch.setattr(models.time, "monotonic", lambda: clock[0])
    events = []
    manager = models.ModelManager(tmp_path, progress=events.append)
    for index in range(100):
        clock[0] = 1 + index / 100
        manager._emit({"id": "test-model", "state": "downloading"})
    assert len(events) == 4
    manager._emit({"id": "test-model", "state": "paused"})
    assert len(events) == 5


async def test_startup_uses_size_and_mtime_cache_without_hashing(tmp_path, tiny_catalog, monkeypatch):
    model, payload = tiny_catalog
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=payload)
    )) as client:
        path = await models.ModelManager(tmp_path, client).download(model["id"])
    monkeypatch.setattr(models, "sha256", lambda _: pytest.fail("Rehashed a verified model"))
    manager = models.ModelManager(tmp_path)
    await manager.recover()
    assert models.installed(model["id"], tmp_path)
    corrupt_weights(path / "model.bin", preserve_mtime=False)
    assert not models.installed(model["id"], tmp_path)


async def test_load_rejects_corrupt_weights_with_matching_stats_and_download_repairs(
    tmp_path, tiny_catalog
):
    model, payload = tiny_catalog
    model.update(languages=["en"], auto_language=True)
    adapter = Mock()
    engine = LocalEngine(root=tmp_path, adapter_factory=adapter, speech_detector=Mock())
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload)
        )) as client:
            manager = models.ModelManager(tmp_path, client)
            path = await manager.download(model["id"])
            corrupt_weights(path / "model.bin", preserve_mtime=True)
            assert models.installed(model["id"], tmp_path)
            with pytest.raises(ProviderError, match="Check files.*Download again"):
                await engine.load(model["id"])
            adapter.assert_not_called()

            await manager.download(model["id"])
            assert (path / "model.bin").read_bytes() == payload
            await engine.load(model["id"])
            adapter.assert_called_once()
    finally:
        await engine.aclose()


async def test_legacy_receipt_is_verified_once_then_cached(tmp_path, tiny_catalog, monkeypatch):
    model, payload = tiny_catalog
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=payload)
    )) as client:
        path = await models.ModelManager(tmp_path, client).download(model["id"])
    receipt_path = path / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt.pop("file_stats")
    receipt_path.write_text(json.dumps(receipt))
    digest = Mock(wraps=models.sha256)
    monkeypatch.setattr(models, "sha256", digest)
    await models.ModelManager(tmp_path).recover()
    assert digest.call_count == 1
    assert "file_stats" in json.loads(receipt_path.read_text())
    await models.ModelManager(tmp_path).recover()
    assert digest.call_count == 1


async def test_download_stall_is_reported_and_clears_when_bytes_resume(tmp_path, tiny_catalog):
    model, payload = tiny_catalog
    release, stalled = asyncio.Event(), asyncio.Event()
    states = []
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield payload[:4]
            await release.wait()
            yield payload[4:]
    def progress(event):
        states.append(event["state"])
        if event["state"] == "stalled":
            stalled.set()
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, stream=SlowStream())
    )) as client:
        manager = models.ModelManager(tmp_path, client, progress)
        manager.stall_seconds = 0.01
        task = asyncio.create_task(manager.download(model["id"]))
        try:
            await asyncio.wait_for(stalled.wait(), 1)
            release.set()
            await task
            assert states.index("stalled") < states.index("downloading") < states.index("ready")
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
