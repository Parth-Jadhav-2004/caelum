"""Opt-in corpus benchmark. Results contain numeric metrics, never transcripts."""

import asyncio
import importlib.metadata
import json
import os
import platform
import resource
import statistics
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .audio import RATE, read_wav
from .providers import Providers
from .segmenter import Chunker


def wer(reference, hypothesis):
    def tokens(text):
        return "".join(
            c for c in text.casefold() if not unicodedata.category(c).startswith("P")
        ).split()

    a, b = tokens(reference), tokens(hypothesis)
    row = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        new = [i]
        for j, candidate in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (word != candidate)))
        row = new
    return row[-1] / max(1, len(a))


def percentile(values, percent):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * percent / 100
    lo = int(index)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (index - lo)


async def benchmark(config, manifest, repeat, output):
    manifest = Path(manifest)
    fixtures = json.loads(manifest.read_text())
    results = []
    provider = Providers(config)
    try:
        for iteration in range(repeat):
            for fixture in fixtures:
                pcm = read_wav(manifest.parent / fixture["audio"])
                reference = (manifest.parent / fixture["reference"]).read_text().strip()
                if len(pcm) > config.app.max_recording_seconds * RATE * 2:
                    raise ValueError("Fixture exceeds configured recording limit")
                # Alternate order to reduce warm-client ordering bias.
                strategies = ("single", "chunked") if iteration % 2 == 0 else ("chunked", "single")
                for strategy in strategies:
                    provider.reset_metrics()
                    chunker = Chunker(provider, config.stt) if strategy == "chunked" else None
                    released = None
                    try:
                        if chunker:
                            started = time.monotonic()
                            samples = len(pcm) // 2
                            for end in range(chunker.step, samples + 1, chunker.step):
                                await asyncio.sleep(max(0, started + end / RATE - time.monotonic()))
                                chunker.feed(
                                    lambda a, b, recording=pcm: recording[a * 2 : b * 2], end
                                )
                            await asyncio.sleep(max(0, started + samples / RATE - time.monotonic()))
                        released = time.monotonic()
                        raw = (
                            await chunker.finish(pcm) if chunker else (await provider.stt(pcm)).text
                        )
                        text, refined = await provider.cleanup(raw)
                        results.append(
                            {
                                "fixture": fixture.get("id", "unnamed"),
                                "iteration": iteration,
                                "strategy": strategy,
                                "release_to_ready_ms": (time.monotonic() - released) * 1000,
                                "raw_wer": wer(reference, raw),
                                "final_wer": wer(reference, text),
                                "error": False,
                                "refined": refined,
                                **provider.metrics,
                            }
                        )
                    except Exception:
                        if chunker:
                            chunker.cancel()
                        results.append(
                            {
                                "fixture": fixture.get("id", "unnamed"),
                                "iteration": iteration,
                                "strategy": strategy,
                                "error": True,
                            }
                        )
        summary = {}
        for strategy in ("single", "chunked"):
            all_rows = [r for r in results if r["strategy"] == strategy]
            rows = [r for r in all_rows if not r["error"]]
            latencies = [r["release_to_ready_ms"] for r in rows]
            summary[strategy] = {f"p{p}_ready_ms": percentile(latencies, p) for p in (50, 90, 95)}
            summary[strategy].update(
                {
                    "max_ready_ms": max(latencies, default=None),
                    "mean_raw_wer": statistics.mean(r["raw_wer"] for r in rows) if rows else None,
                    "mean_final_wer": statistics.mean(r["final_wer"] for r in rows)
                    if rows
                    else None,
                    "error_rate": sum(r["error"] for r in all_rows) / max(1, len(all_rows)),
                }
            )
        # The result explicitly excludes visible application insertion; never call this end-to-end.
        report = {
            "measurement": "release to text ready; insertion visibility is a separate manual test",
            "summary": summary,
            "runs": results,
            "default_strategy": "single",
            "cost": "Not estimated: supply verified provider rates before costing.",
        }
        path = Path(output)
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Numeric benchmark report written to {path}")
    finally:
        await provider.client.aclose()


async def local_benchmark(config, manifest, repeat, output, model_id, threads=0):
    """Decode complete clips, without HTTP, cleanup, realtime replay, or insertion.

    Run one model per CLI process: ru_maxrss is a process-lifetime high-water
    mark, not a sum of models' individual memory use.
    """
    from .local_stt import LocalEngine
    from .models import get_model
    from .providers import ProviderError

    if not 1 <= repeat <= 20:
        raise ValueError("repeat must be between 1 and 20")
    model = get_model(model_id)
    manifest = Path(manifest)
    fixtures = json.loads(manifest.read_text())
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("Benchmark manifest must be a non-empty list")
    engine = LocalEngine(threads=threads, language=config.stt.language,
                         vocabulary=config.stt.vocabulary, silence_dbfs=config.app.silence_dbfs,
                         prefer_cuda=False)
    results = []
    try:
        await engine.load(model_id)
        load_seconds = engine.load_seconds
        for iteration in range(repeat):
            for fixture in fixtures:
                pcm = read_wav(manifest.parent / fixture["audio"])
                duration = len(pcm) / (RATE * 2)
                if not 0 < duration <= config.app.max_recording_seconds:
                    raise ValueError("Fixture is empty or exceeds configured recording limit")
                reference = (
                    (manifest.parent / fixture["reference"]).read_text().strip()
                    if fixture.get("reference") else None
                )
                began = time.monotonic()
                row = {
                    "fixture": fixture.get("id", "unnamed"),
                    "iteration": iteration,
                    "first_decode": not results,
                    "audio_seconds": duration,
                    "http_calls": 0,
                    "uploaded_audio_bytes": 0,
                }
                try:
                    transcript = await engine.transcribe(pcm)
                    row.update({
                        "release_to_ready_ms": (time.monotonic() - began) * 1000,
                        "decode_ms": engine.decode_ms,
                        "raw_wer": wer(reference, transcript.text) if reference is not None else None,
                        "empty_output": not bool(transcript.text),
                        "error": False,
                    })
                except ProviderError as error:
                    row.update({"error": True, "error_kind": error.kind})
                results.append(row)
        successful = [row for row in results if not row["error"]]
        decode_seconds = sum(row["decode_ms"] for row in successful) / 1000
        waits = [row["release_to_ready_ms"] for row in successful]
        wers = [row["raw_wer"] for row in successful if row["raw_wer"] is not None]
        versions = {}
        for name in ("sherpa-onnx", "faster-whisper", "ctranslate2", "numpy"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
        report = {
            "engine": "local",
            "model": model_id,
            "revision": model["revision"],
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "measurement": "complete clip release to text ready; no cleanup or insertion",
            "hardware": {
                "arch": platform.machine(),
                "logical_cpus": os.cpu_count(),
                "threads": engine.threads,
                "python": platform.python_version(),
                "device": "cpu",
            },
            "versions": versions,
            "summary": {
                "load_seconds": load_seconds,
                "realtime_factor": (
                    sum(row["audio_seconds"] for row in successful) / decode_seconds
                    if decode_seconds else None
                ),
                "mean_wait_ms": statistics.mean(waits) if waits else None,
                "p95_wait_ms": percentile(waits, 95),
                "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                "mean_raw_wer": statistics.mean(wers) if wers else None,
                "error_rate": sum(row["error"] for row in results) / len(results),
                "empty_outputs": sum(row.get("empty_output", False) for row in results),
                "http_calls": 0,
                "uploaded_audio_bytes": 0,
            },
            "runs": results,
        }
        path = Path(output)
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Numeric local benchmark report written to {path}")
        print(json.dumps(report["summary"], indent=2))
        return report
    finally:
        await engine.aclose()
