"""Qualify the packaged local engine with a pinned public speech fixture; no mic or HTTP."""

import argparse
import asyncio
import hashlib
import json
import platform
import tempfile
from collections import Counter
from pathlib import Path

from caelum.audio import read_wav
from caelum.local_stt import LocalEngine
from caelum.models import get_model
from caelum.providers import ProviderError

SAMPLE = "6bc58a4efdf20daac252b6b1502632601a71efe0308f6757dc1eda34891a7e4f"


async def check(root, sample, model, device, expect_setup_error=False):
    if hashlib.sha256(sample.read_bytes()).hexdigest() != SAMPLE:
        raise ValueError("Use librispeech-0.wav from scripts/download-local-fixtures.py")
    with tempfile.TemporaryDirectory() as folder:
        engine = LocalEngine(root=root, device=device, language="en", cuda_profile_dir=folder)
        try:
            try:
                await engine.load(model)
            except ProviderError as error:
                if expect_setup_error and error.kind == "local_setup" and "Auto or CPU" in str(error):
                    print(f"Expected setup error: {error}")
                    return
                raise
            if expect_setup_error:
                raise RuntimeError("GPU unexpectedly accepted unavailable runtime")
            result = await engine.transcribe(read_wav(sample))
            actual = engine.active_device
        finally:
            await engine.aclose()  # ORT flushes profiles when sessions close.
        words = result.text.casefold().split()
        if not words or "light" not in result.text.casefold():
            raise RuntimeError("Known speech was not recognized")
        if device == "gpu" and actual != "cuda" or device == "cpu" and actual != "cpu":
            raise RuntimeError("Unexpected execution device")
        ops = Counter()
        for trace in Path(folder).glob("ort*.json"):
            for event in json.loads(trace.read_text(encoding="utf-8")):
                args = event.get("args", {})
                if args.get("provider") == "CUDAExecutionProvider":
                    ops[args["op_name"]] += 1
        if actual == "cuda" and not any(
            name in ops for name in ("Conv", "MatMul", "Softmax", "LayerNormalization", "Gemm")
        ):
            raise RuntimeError("No CUDA neural-network compute operations in the speech-model trace")
        print(json.dumps({"os": platform.system(), "model": model, "revision": get_model(model)["revision"],
                          "device": actual, "fixture_sha256": SAMPLE, "words": len(words),
                          "cuda_node_events": sum(ops.values()), "cuda_ops": dict(ops)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", type=Path, help="Copied model directories with their receipts")
    parser.add_argument("sample", type=Path)
    parser.add_argument("--model", default="parakeet-v3")
    parser.add_argument("--device", choices=["gpu", "auto", "cpu"], default="gpu")
    parser.add_argument("--expect-setup-error", action="store_true")
    args = parser.parse_args()
    asyncio.run(check(args.models, args.sample, args.model, args.device, args.expect_setup_error))
