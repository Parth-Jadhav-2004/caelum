"""Pinned model storage and sidecar-owned download queue. No implicit downloads."""

import asyncio
import errno
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import httpx

EXTRA_MODULES = {"local": "sherpa_onnx", "whisper": "faster_whisper"}
INDIAN_LANGUAGES = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "or": "Odia",
    "ur": "Urdu", "as": "Assamese", "ne": "Nepali", "sa": "Sanskrit",
}


def recommend(hardware):
    from .hardware import local_support

    if reason := local_support(hardware):
        return {"id": None, "reason_code": "unsupported", "reason_text": reason}
    language = hardware.language

    def choice(model_id, reason, text):
        return {"id": model_id, "reason_code": reason, "reason_text": text}

    if language in INDIAN_LANGUAGES:
        return choice(None, "indian_language",
                      f"On-device models aren't good at {INDIAN_LANGUAGES[language]} yet. "
                      "Online works best for now.")
    parakeet = get_model("parakeet-v3")["languages"]
    if language not in parakeet:
        if language in get_model("cohere-transcribe")["languages"] and hardware.mem_total_mb >= 8192:
            return choice("cohere-transcribe", "language", "Best match for your language.")
        return choice("whisper-turbo", "language", "Understands your language." + (
            " It's slower on this computer." if not hardware.nvidia else ""))
    low = (hardware.mem_total_mb < 6144 or hardware.mem_available_mb < 2500
           or hardware.cores < 4 or hardware.arch == "x86_64" and not hardware.avx2)
    if low:
        if language == "en":
            return choice("parakeet-110m", "low_memory", "English only. Light on memory.")
        if hardware.mem_available_mb < 2048:
            return choice(None, "low_memory",
                          "This computer is low on memory for your language. Online works best.")
    return choice("parakeet-v3", "balanced", "Fast and accurate for your computer.")


def read_stats(root=None):
    try:
        result = json.loads(((Path(root) if root else models_dir()) / "stats.json").read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def record_stats(model_id, decode_ms, root=None):
    root = Path(root) if root else models_dir()
    root.mkdir(parents=True, exist_ok=True)
    stats = read_stats(root)
    stats[model_id] = {"decode_ms": decode_ms}
    temporary = root / ".stats.json.part"
    temporary.write_text(json.dumps(stats) + "\n")
    os.replace(temporary, root / "stats.json")


class ModelError(RuntimeError):
    """Safe to display; never includes server bodies, redirect URLs, or credentials."""

    def __init__(self, message, code="http"):
        super().__init__(message)
        self.code = code


def catalog():
    data = json.loads(Path(__file__).with_name("model_catalog.json").read_text())
    ids = set()
    for model in data["models"]:
        model_id = model["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", model_id) or model_id in ids:
            raise ValueError("Invalid model catalog id")
        ids.add(model_id)
        paths = set()
        for item in model["files"]:
            # The current catalog is flat. Never trust a path from an archive.
            if (
                PurePosixPath(item["path"]).name != item["path"]
                or item["path"] in (".", "..", "receipt.json")
                or item["path"] in paths
                or item["bytes"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            ):
                raise ValueError("Invalid model catalog file")
            paths.add(item["path"])
    return data


def get_model(model_id):
    for model in catalog()["models"]:
        if model["id"] == model_id:
            return model
    raise ModelError("Unknown speech model", "model")


def models_dir():
    from .config import data_dir

    return data_dir() / "models"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _matches(path, item, full=False):
    try:
        return (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size == item["bytes"]
            and (not full or sha256(path) == item["sha256"])
        )
    except OSError:
        return False


def installed(model_id, root=None, *, full=False):
    """Check the receipt and file metadata; request full content checks before use."""
    model = get_model(model_id)
    path = (Path(root) if root is not None else models_dir()) / model_id
    try:
        receipt = json.loads((path / "receipt.json").read_text())
        return (
            not path.is_symlink()
            and receipt["id"] == model_id
            and receipt["catalog_version"] == catalog()["version"]
            and receipt["revision"] == model["revision"]
            and receipt["files"] == model["files"]
            and ("file_stats" not in receipt or receipt["file_stats"] == file_stats(path, model))
            and all(_matches(path / item["path"], item, full) for item in model["files"])
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def file_stats(path, model):
    return {item["path"]: {"size": (path / item["path"]).stat().st_size,
                           "mtime_ns": (path / item["path"]).stat().st_mtime_ns}
            for item in model["files"]}


def verify(model_id, root=None):
    model = get_model(model_id)
    path = (Path(root) if root is not None else models_dir()) / model_id
    bad = [item["path"] for item in model["files"] if not _matches(path / item["path"], item, True)]
    if not bad and not path.is_symlink():
        try:
            receipt = json.loads((path / "receipt.json").read_text())
            receipt["file_stats"] = file_stats(path, model)
            temporary = path / ".receipt.json.part"
            temporary.write_text(json.dumps(receipt, indent=2) + "\n")
            os.replace(temporary, path / "receipt.json")
        except (OSError, ValueError):
            pass
    return {"ok": installed(model_id, root) and not bad, "bad_files": bad}


def _source_url(url):
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    if url.startswith("https://huggingface.co/"):
        if not endpoint.startswith("https://"):
            raise ModelError("HF_ENDPOINT must use HTTPS", "http")
        return endpoint + url[len("https://huggingface.co") :]
    return url


class ModelManager:
    def __init__(self, root=None, client=None, progress=lambda event: None):
        self.root = Path(root) if root is not None else models_dir()
        self.client = client
        self.progress = progress
        self._last_progress = {}
        self.stall_seconds = 10
        self.states = {}
        self.queue = []
        self._runner = None
        self._active = None
        self._download_task = None
        self._recovered = False
        self._totals = {}
        self._source_kinds = {}
        self._queue_gate = asyncio.Event()
        self._queue_gate.set()
        known = {model["id"] for model in catalog()["models"]}
        for work in (self.root / ".download").glob("*"):
            if work.name in known and work.is_dir() and not work.is_symlink():
                self.states[work.name] = self._snapshot(work.name, "paused")

    def _snapshot(self, model_id, state):
        model = get_model(model_id)
        work = self.root / ".download" / model_id
        archive = work / "archive.tar.bz2.part"
        received = archive.stat().st_size if archive.is_file() and (
            self._source_kinds.get(model_id) != "files"
        ) else sum(
            next((path.stat().st_size for path in (
                work / "install" / item["path"], work / (item["path"] + ".part")
            ) if path.is_file() and not path.is_symlink()), 0)
            for item in model["files"]
        )
        return {"id": model_id, "state": state, "received_bytes": received,
                "total_bytes": self._totals.get(model_id, model["download_bytes"]), "bytes_per_sec": 0,
                "eta_seconds": None, "error": None}

    async def recover(self):
        if self._recovered:
            return
        # New receipts carry stats recorded after SHA-256 validation. Older
        # installs get a one-time verification, then subsequent starts only stat.
        for model in catalog()["models"]:
            receipt_path = self.root / model["id"] / "receipt.json"
            try:
                receipt = json.loads(receipt_path.read_text())
                if "file_stats" in receipt and not installed(model["id"], self.root):
                    receipt_path.unlink(missing_ok=True)
                elif "file_stats" not in receipt:
                    result = await asyncio.to_thread(verify, model["id"], self.root)
                    if not result["ok"]:
                        receipt_path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError):
                continue
        self._recovered = True

    def list(self, config, hardware):
        stats = read_stats(self.root)
        result = []
        for model in catalog()["models"]:
            ready = installed(model["id"], self.root)
            state = self.states.get(model["id"], {})
            current_state = state.get("state", "not_installed")
            if current_state in ("ready", "cancelled"):
                current_state = "not_installed"
            from .hardware import local_support

            disabled = local_support(hardware)
            visible = model["tier"] != "more" and hardware.mem_total_mb >= model["min_mem_total_mb"]
            extra = model["requires_extra"]
            if disabled:
                pass
            elif hardware.mem_total_mb < model["min_mem_total_mb"]:
                disabled = "Needs 8 GB memory"
            elif importlib.util.find_spec(EXTRA_MODULES[extra or "local"]) is None:
                disabled = "Needs an extra component."
            else:
                needed = max(model["min_disk_free_mb"], model["download_bytes"] * 1.1 / 1e6 + 200)
                if not ready and hardware.disk_free_mb < needed:
                    disabled = (f"Needs {needed / 1000:.1f} GB free. "
                                f"You have {hardware.disk_free_mb / 1000:.1f} GB.")
            result.append({
                **model, "state": "installed" if ready else current_state,
                "received_bytes": state.get("received_bytes", 0),
                "total_bytes": state.get("total_bytes", model["download_bytes"]),
                "bytes_per_sec": state.get("bytes_per_sec", 0),
                "eta_seconds": state.get("eta_seconds"),
                "error": state.get("error"), "in_use": config.stt.engine == "local"
                and config.stt.local_model == model["id"],
                "visible": visible, "disabled_reason": disabled,
                "stored_in": str(self.root / model["id"]),
                "decode_ms": stats.get(model["id"], {}).get("decode_ms"),
            })
        storage = sum(path.stat().st_size for path in self.root.rglob("*")
                      if path.is_file() and not path.is_symlink()) if self.root.exists() else 0
        return {"hardware": asdict(hardware), "recommended": recommend(hardware),
                "models": result, "storage_bytes": storage}

    async def submit(self, model_id):
        get_model(model_id)
        await self.recover()
        if installed(model_id, self.root) or model_id == self._active or model_id in self.queue:
            return
        (self.root / ".download" / model_id).mkdir(parents=True, exist_ok=True)
        self.queue.append(model_id)
        self._emit(self._snapshot(model_id, "queued"))
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run_queue())

    async def _run_queue(self):
        while self.queue:
            await self._queue_gate.wait()
            if not self.queue:
                break
            model_id = self.queue.pop(0)
            self._active = model_id
            self._download_started = time.monotonic()
            self._initial_received = self._snapshot(model_id, "downloading")["received_bytes"]
            self._download_task = asyncio.create_task(self.download(model_id))
            try:
                await self._download_task
            except asyncio.CancelledError:
                pass  # Pause/cancel controls set the final state after draining.
            except ModelError as error:
                event = self._snapshot(model_id, "failed")
                event["error"] = {"code": error.code, "message": str(error)}
                self._emit(event)
            except Exception:
                event = self._snapshot(model_id, "failed")
                event["error"] = {"code": "http", "message": "Couldn't download the speech model. Try again."}
                self._emit(event)
            finally:
                self._active = self._download_task = None

    async def pause(self, model_id, resume_queue=True):
        get_model(model_id)
        self._queue_gate.clear()
        if model_id in self.queue:
            self.queue.remove(model_id)
        if self._active == model_id and self._download_task:
            self._download_task.cancel()
            await asyncio.gather(self._download_task, return_exceptions=True)
        if not installed(model_id, self.root):
            self._emit(self._snapshot(model_id, "paused"))
        if resume_queue:
            self._queue_gate.set()

    async def cancel(self, model_id):
        await self.pause(model_id, resume_queue=False)
        try:
            def remove_work():
                work = self.root / ".download" / model_id
                if work.exists():
                    shutil.rmtree(work)
            if self._active and self._active != model_id:
                # This instance owns the process lock for a different model.
                remove_work()
            else:
                with self._locked():
                    remove_work()
            self._emit(self._snapshot(model_id, "cancelled"))
        finally:
            self._queue_gate.set()

    async def aclose(self):
        self.queue.clear()
        self._queue_gate.set()
        if self._active:
            await self.pause(self._active)
        if self._runner:
            await asyncio.gather(self._runner, return_exceptions=True)

    def _emit(self, event):
        model_id = event["id"]
        if "received_bytes" not in event:
            event = {**self._snapshot(model_id, event["state"]), **event}
        if event["state"] == "downloading":
            elapsed = time.monotonic() - getattr(self, "_download_started", time.monotonic())
            snapshot = self._snapshot(model_id, "downloading")
            received = snapshot["received_bytes"]
            speed = max(0, received - getattr(self, "_initial_received", 0)) / max(0.001, elapsed)
            event.update(received_bytes=received, total_bytes=snapshot["total_bytes"],
                         bytes_per_sec=speed,
                         eta_seconds=(max(0, snapshot["total_bytes"] - received) / speed)
                         if elapsed >= 3 and speed else None, error=None)
        self.states[model_id] = event
        previous_state, previous_time = self._last_progress.get(event["id"], (None, 0))
        now = time.monotonic()
        if event["state"] != previous_state or now - previous_time >= 0.25:
            self._last_progress[event["id"]] = (event["state"], now)
            self.progress(event)

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".lock").open("a") as lock:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                raise ModelError("Another model operation is running", "busy") from None
            yield  # Closing the file releases the lock on either platform.

    async def download(self, model_id):
        model = get_model(model_id)
        from .hardware import detect, local_support

        hardware = detect(directory=self.root)
        if reason := local_support(hardware):
            raise ModelError(reason, "unsupported")
        if hardware.mem_total_mb < model.get("min_mem_total_mb", 0):
            raise ModelError("Needs 8 GB memory", "memory")
        extra = model["requires_extra"]
        if extra is None and model.get("runtime", "").startswith("sherpa-"):
            extra = "local"
        if extra and importlib.util.find_spec(EXTRA_MODULES[extra]) is None:
            raise ModelError(
                f"Needs an extra component. Install caelum-dictation[{extra}].", "missing_extra"
            )
        with self._locked():
            if await asyncio.to_thread(installed, model_id, self.root, full=True):
                return self.root / model_id
            destination = self.root / model_id
            if destination.is_symlink():
                raise ModelError("Model folder must not be a link", "storage")
            work = self.root / ".download" / model_id
            work.mkdir(parents=True, exist_ok=True)
            self._download_started = time.monotonic()
            self._initial_received = self._snapshot(model_id, "downloading")["received_bytes"]
            owned_client = self.client is None
            client = self.client or httpx.AsyncClient(
                follow_redirects=True, timeout=httpx.Timeout(30, connect=10)
            )
            try:
                last_error = None
                for source in model["sources"]:
                    try:
                        self._totals[model_id] = (source["bytes"] if source["kind"] == "archive"
                                                 else sum(item["bytes"] for item in model["files"]))
                        self._source_kinds[model_id] = source["kind"]
                        self._preflight(model, source, work)
                        stage = work / "install"
                        stage.mkdir(exist_ok=True)
                        if source["kind"] == "files":
                            for item in model["files"]:
                                final = stage / item["path"]
                                if await asyncio.to_thread(_matches, final, item, True):
                                    continue
                                part = work / (item["path"] + ".part")
                                await self._fetch(client, source["base"] + item["path"],
                                                  part, item, model_id)
                                os.replace(part, final)
                        else:
                            archive = work / "archive.tar.bz2.part"
                            await self._fetch(client, source["url"], archive, source, model_id)
                            self._emit({"id": model_id, "state": "verifying"})
                            # Await the worker even if cancelled: do not release the filesystem
                            # lock while extraction can still mutate the staging directory.
                            extraction = asyncio.create_task(
                                asyncio.to_thread(self._extract, archive, stage, model, source)
                            )
                            try:
                                await asyncio.shield(extraction)
                            except asyncio.CancelledError:
                                await extraction
                                raise
                        for item in model["files"]:
                            if not await asyncio.to_thread(_matches, stage / item["path"], item, True):
                                raise ModelError("The download was damaged. Try again.", "checksum")
                        self._emit({"id": model_id, "state": "installing"})
                        receipt = {
                            "id": model_id,
                            "catalog_version": catalog()["version"],
                            "revision": model["revision"],
                            "files": model["files"],
                            "file_stats": file_stats(stage, model),
                            "verified_at": datetime.now(timezone.utc).isoformat(),
                            "source": source,
                        }
                        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
                        previous = work / "previous"
                        if destination.exists():
                            if previous.exists():
                                shutil.rmtree(previous)
                            os.replace(destination, previous)
                        try:
                            os.replace(stage, destination)
                        except BaseException:
                            if previous.exists():
                                os.replace(previous, destination)
                            raise
                        shutil.rmtree(work)
                        self._emit({"id": model_id, "state": "ready"})
                        return destination
                    except ModelError as error:
                        last_error = error
                raise last_error
            except OSError as error:
                if error.errno == errno.ENOSPC:
                    snapshot = self._snapshot(model_id, "failed")
                    remaining = max(0, snapshot["total_bytes"] - snapshot["received_bytes"]) + 200_000_000
                    raise ModelError(f"Ran out of space. Free up {remaining / 1e9:.1f} GB and try again.",
                                     "disk_full") from None
                raise ModelError("Couldn't save the speech model. Check file permissions.",
                                 "storage") from None
            finally:
                if owned_client:
                    await client.aclose()

    def _preflight(self, model, source, work):
        if source["kind"] == "archive":
            part = work / "archive.tar.bz2.part"
            remaining = max(0, source["bytes"] - (part.stat().st_size if part.exists() else 0))
            needed = max(
                remaining * 1.1 + model["disk_bytes"] + 200_000_000,
                model["min_disk_free_mb"] * 1_000_000 if not part.exists() else 0,
            )
        else:
            remaining = 0
            for item in model["files"]:
                final = work / "install" / item["path"]
                part = work / (item["path"] + ".part")
                have = final.stat().st_size if final.exists() else (
                    part.stat().st_size if part.exists() else 0
                )
                remaining += max(0, item["bytes"] - have)
            needed = remaining * 1.1 + 200_000_000
        free = shutil.disk_usage(self.root).free
        if free < needed:
            raise ModelError(
                f"Needs {needed / 1e9:.1f} GB free. You have {free / 1e9:.1f} GB.", "disk_full"
            )

    async def _fetch(self, client, url, part, item, model_id):
        self._last_byte = time.monotonic()

        async def watch():
            while True:
                await asyncio.sleep(min(2, self.stall_seconds))
                if time.monotonic() - self._last_byte >= self.stall_seconds:
                    self._emit(self._snapshot(model_id, "stalled"))

        watcher = asyncio.create_task(watch())
        try:
            return await self._fetch_body(client, url, part, item, model_id)
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

    async def _fetch_body(self, client, url, part, item, model_id):
        size = item["bytes"]
        if await asyncio.to_thread(_matches, part, item, True):
            return
        offset = part.stat().st_size if part.exists() else 0
        if offset >= size:
            part.unlink()
            offset = 0
        digest = hashlib.sha256()
        if offset:
            # Resume hashes include the existing bytes, not just the response.
            def rehash():
                with part.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
            await asyncio.to_thread(rehash)
        try:
            async with client.stream(
                "GET", _source_url(url),
                headers={"Range": f"bytes={offset}-", "Accept-Encoding": "identity"}
            ) as response:
                if response.status_code not in (200, 206):
                    raise ModelError("Couldn't reach the download server. Try again later.", "http")
                if response.status_code == 206:
                    expected = f"bytes {offset}-"
                    if not response.headers.get("Content-Range", "").startswith(expected):
                        raise ModelError("Couldn't resume the download. Try again.", "http")
                else:
                    offset = 0
                    digest = hashlib.sha256()
                with part.open("ab" if offset else "wb") as stream:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if offset + len(chunk) > size:
                            part.unlink()
                            raise ModelError("The download was damaged. Try again.", "checksum")
                        self._last_byte = time.monotonic()
                        stream.write(chunk)
                        digest.update(chunk)
                        offset += len(chunk)
                        self._emit({"id": model_id, "state": "downloading",
                                    "file": part.name, "received_bytes": offset,
                                    "total_bytes": size})
                    stream.flush()
                    os.fsync(stream.fileno())
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
            raise ModelError("Download stopped. Check your connection.", "offline") from None
        except httpx.HTTPError:
            raise ModelError("Couldn't reach the download server. Try again later.", "http") from None
        if offset != size or digest.hexdigest() != item["sha256"]:
            part.unlink(missing_ok=True)
            raise ModelError("The download was damaged. Try again.", "checksum")

    @staticmethod
    def _extract(archive, stage, model, source):
        expected = {item["path"]: item for item in model["files"]}
        seen = set()
        try:
            with tarfile.open(archive, "r:bz2") as tar:
                for member in tar:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or ".." in path.parts or (
                        not member.isfile() and not member.isdir()
                    ):
                        raise ModelError("Couldn't unpack the files. Try again.", "extract")
                    relative = PurePosixPath(*path.parts[source.get("strip", 0):]).as_posix()
                    if member.isdir() or relative not in expected:
                        continue
                    if relative in seen or member.size != expected[relative]["bytes"]:
                        raise ModelError("The download was damaged. Try again.", "checksum")
                    seen.add(relative)
                    # Only copy catalog allowlisted regular files, never links or
                    # archive permissions. tarfile.extract/extractall are not used.
                    with tar.extractfile(member) as src, (stage / relative).open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
            if seen != expected.keys():
                raise ModelError("Couldn't unpack the files. Try again.", "extract")
        except (tarfile.TarError, EOFError, ValueError):
            raise ModelError("Couldn't unpack the files. Try again.", "extract") from None

    def remove(self, model_id):
        get_model(model_id)
        with self._locked():
            path = self.root / model_id
            if path.is_symlink():
                raise ModelError("Model folder must not be a link", "storage")
            freed = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
            if path.exists():
                shutil.rmtree(path)
            return freed


async def pin(model_id, client=None):
    """Re-fetch one pinned source and print metadata, without installing or editing.

    Unlike install, this developer operation intentionally computes new hashes
    rather than trusting the old ones. Bound all responses/extraction by twice
    the current catalog footprint; large format changes require manual review.
    """
    model = get_model(model_id)
    owned = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=30)

    async def fetch(url, limit, destination=None):
        digest, count = hashlib.sha256(), 0
        async with client.stream("GET", _source_url(url),
                                 headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise ModelError("Couldn't reach the download server. Try again later.", "http")
            async for chunk in response.aiter_bytes(1024 * 1024):
                count += len(chunk)
                if count > limit:
                    raise ModelError("Source exceeds the pinning safety limit", "checksum")
                digest.update(chunk)
                if destination:
                    destination.write(chunk)
        return {"bytes": count, "sha256": digest.hexdigest()}

    try:
        last = None
        for source in model["sources"]:
            try:
                result = {"id": model_id, "revision": model["revision"], "source": source,
                          "files": []}
                if source["kind"] == "files":
                    for item in model["files"]:
                        metadata = await fetch(source["base"] + item["path"],
                                               item["bytes"] * 2 + 1_000_000)
                        result["files"].append({"path": item["path"], "role": item["role"], **metadata})
                else:
                    with tempfile.TemporaryDirectory(prefix="caelum-pin-") as temporary:
                        archive = Path(temporary) / "archive.tar.bz2"
                        with archive.open("wb") as output:
                            result["archive"] = await fetch(source["url"], source["bytes"] * 2, output)
                        expected = {item["path"]: item for item in model["files"]}
                        seen = set()
                        with tarfile.open(archive, "r:bz2") as tar:
                            for member in tar:
                                path = PurePosixPath(member.name)
                                if path.is_absolute() or ".." in path.parts or (
                                    not member.isfile() and not member.isdir()
                                ):
                                    raise ModelError("Couldn't unpack the files. Try again.", "extract")
                                name = PurePosixPath(*path.parts[source.get("strip", 0):]).as_posix()
                                if name not in expected or member.isdir():
                                    continue
                                if name in seen or member.size > expected[name]["bytes"] * 2 + 1_000_000:
                                    raise ModelError("Source exceeds the pinning safety limit", "extract")
                                seen.add(name)
                                with tar.extractfile(member) as stream:
                                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                                result["files"].append({
                                    "path": name, "role": expected[name]["role"],
                                    "bytes": member.size, "sha256": digest,
                                })
                        if seen != expected.keys():
                            raise ModelError("Source is missing catalog files", "extract")
                return result
            except (httpx.HTTPError, tarfile.TarError, ModelError) as error:
                last = error if isinstance(error, ModelError) else ModelError(
                    "Couldn't fetch pinned model metadata", "http")
        raise last
    finally:
        if owned:
            await client.aclose()
