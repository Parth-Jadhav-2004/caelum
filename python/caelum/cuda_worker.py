"""Private stdio worker, launched by cuda_runtime with the optional venv's Python."""

import ctypes
import json
import os
import struct
import sys
import sysconfig
from pathlib import Path


def main():
    site = Path(sysconfig.get_path("purelib"))
    native = site / "sherpa_onnx/lib"
    windows = os.name == "nt"
    if windows:
        # Retain these handles for delayed provider DLL loads as well.
        dll_dirs = [native, *(site / "nvidia").glob("*/bin")]
        handles = [os.add_dll_directory(path) for path in dll_dirs]  # noqa: F841
    runtime = ctypes.CDLL("cudart64_12.dll" if windows else "libcudart.so.12")
    count = ctypes.c_int()
    if runtime.cudaGetDeviceCount(ctypes.byref(count)) or not count.value:
        os.write(2, b"CAELUM_NO_DEVICE\n")
        return
    import numpy as np
    import sherpa_onnx

    if not sherpa_onnx.__version__.startswith("2.0.1+cuda12.cudnn9"):
        return
    # Reuse package-owned adapters without importing the packaged CPU wheel.
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from caelum.sherpa_stt import ADAPTERS

    source = sys.stdin.buffer
    model, path, threads, language, vocabulary, profile = json.loads(source.readline())
    options = "LogSeverityLevel=0\narena_extend_strategy=kSameAsRequested\ncudnn_conv_algo_search=DEFAULT\n"
    # Parent supplies a private working directory, also used for opt-in QA traces.
    Path("cuda.conf").write_text(options, encoding="ascii")
    # Probe the same linked ORT using a tiny bundled graph before opening speech
    # weights. Parent accepts *positive* node placement separately for each graph.
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(Path(__file__).with_name("data") / "silero_vad.onnx")
    config.provider = "cuda:cuda.conf"
    probe = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=1)
    probe.accept_waveform(np.zeros(config.silero_vad.window_size, dtype=np.float32))
    del probe
    os.write(2, b"\nCAELUM_PROVIDER_READY\n")
    if source.readline() != b"load\n":
        return
    if profile:
        Path("cuda.conf").write_text(options + "ProfilingFilePrefix=ort\n", encoding="ascii")
    adapter = ADAPTERS[model["runtime"]](model, Path(path), threads, language, vocabulary,
                                         device="cuda:cuda.conf")
    os.write(2, b"\nCAELUM_MODEL_READY\n")
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 2)
    while header := source.read(4):
        size, = struct.unpack("<I", header)
        if size > 60 * 16000 * 4 or size % 4:
            return
        samples = np.frombuffer(source.read(size), dtype="<f4")
        text, words, tokens = adapter.transcribe(samples)
        print(json.dumps([text, words, tokens, adapter.detected_language]), flush=True)


if __name__ == "__main__":
    main()
