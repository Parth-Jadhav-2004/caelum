"""Keep the opt-in sherpa CUDA runtime and native failures out of the CPU engine."""

import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import data_dir
from .providers import ProviderError


def runtime_dir():
    return data_dir() / "components/nvidia-cu12"


def install():
    """Explicit, hash-locked install into a separate user-owned environment."""
    import platform

    if platform.machine().lower() not in ("x86_64", "amd64") or platform.system() not in ("Windows", "Linux"):
        raise ValueError("The optional NVIDIA runtime requires x64 Linux or Windows.")
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("Install uv from https://docs.astral.sh/uv/ and retry.")
    root = runtime_dir()
    if root.exists() and not (root / "pyvenv.cfg").is_file():
        raise ValueError(f"Not a CUDA virtual environment: {root}")
    try:
        if not root.exists():
            subprocess.run([uv, "venv", "--python", "3.12.15", root], check=True)
        subprocess.run([uv, "pip", "sync", "--python", root, "--only-binary", ":all:",
                        "--require-hashes", Path(__file__).with_name("data") / "nvidia-cu12.txt"],
                       check=True)
    except subprocess.CalledProcessError:
        raise ValueError("NVIDIA runtime installation failed. Check the uv output above.") from None
    print("NVIDIA runtime installed. Choose Auto or GPU in Settings → Transcription.")


def setup_error(reason):
    platform = "Windows" if os.name == "nt" else "Linux"
    command = ("engine\\python.exe -I -m caelum.cli install-nvidia" if os.name == "nt"
               else "caelum install-nvidia")
    return ProviderError(f"{reason} On {platform}, run {command} to install or repair the runtime, "
                         "or choose Auto or CPU.", "local_setup")


@contextmanager
def deadline(process, seconds):
    timer = threading.Timer(seconds, process.kill)
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


def confirm_placement(process, marker):
    """Consume native diagnostics privately; never forward model paths or vocabulary."""
    placed = False
    for line in process.stderr:
        if line.strip() == b"CAELUM_NO_DEVICE":
            raise setup_error("No CUDA device is accessible. Check the NVIDIA driver.")
        if b". Fallback to cpu" in line:
            break
        if re.search(rb"VerifyEachNodeIsAssignedToAnEp.*placed on "
                     rb"\[CUDAExecutionProvider\]\. Number of nodes: [1-9]", line):
            placed = True
        if line.strip() == marker:
            if placed:
                return
            break
    raise setup_error("Sherpa couldn't activate CUDA. Check runtime libraries and free GPU memory.")


class SherpaCuda:
    device = "cuda"

    def __init__(self, model, path, threads, language, vocabulary, *, profile_dir=None):
        root = runtime_dir()
        windows = os.name == "nt"
        python = root / ("Scripts/python.exe" if windows else "bin/python")
        if not python.is_file():
            raise setup_error("The optional sherpa NVIDIA runtime isn't installed.")
        site = root / ("Lib/site-packages" if windows else "lib/python3.12/site-packages")
        search = "PATH" if windows else "LD_LIBRARY_PATH"
        dirs = [str(site / "sherpa_onnx/lib")]
        dirs.extend(map(str, (site / "nvidia").glob("*/bin" if windows else "*/lib")))
        if os.environ.get(search):
            dirs.append(os.environ[search])
        env = {**os.environ, search: os.pathsep.join(dirs)}
        self.tmp = tempfile.TemporaryDirectory(prefix="caelum-cuda-")
        self.process = None
        try:
            self.process = subprocess.Popen(
                [python, "-I", "-B", Path(__file__).with_name("cuda_worker.py").resolve()],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=profile_dir or self.tmp.name,
                creationflags=subprocess.CREATE_NO_WINDOW if windows else 0,
            )
            p = self.process
            with deadline(p, 120):
                p.stdin.write(json.dumps([model, str(path.resolve()), threads, language, vocabulary,
                                          profile_dir is not None]).encode() + b"\n")
                p.stdin.flush()
                # Accept positive ORT node placement from this model's sessions.
                # Pinned sherpa can print a CUDA error and proceed entirely on CPU.
                confirm_placement(p, b"CAELUM_PROVIDER_READY")
                p.stdin.write(b"load\n")
                p.stdin.flush()
                confirm_placement(p, b"CAELUM_MODEL_READY")
        except BaseException as exc:
            self.close()
            if isinstance(exc, OSError):
                raise setup_error("The sherpa NVIDIA runtime couldn't start.") from None
            raise

    def transcribe(self, samples):
        p = self.process
        try:
            payload = samples.astype("<f4", copy=False).tobytes()
            with deadline(p, 120):
                p.stdin.write(struct.pack("<I", len(payload)))
                p.stdin.write(payload)
                p.stdin.flush()
                text, words, tokens, self.detected_language = json.loads(p.stdout.readline())
            return text, words, tokens
        except (OSError, ValueError):
            raise ProviderError("NVIDIA decoding failed. Free GPU memory or choose Auto or CPU.",
                                "local_decode") from None

    def close(self):
        if self.process is not None:
            p = self.process
            try:
                p.stdin.close()
            except BrokenPipeError:
                pass
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            p.stdout.close()
            p.stderr.close()
            self.process = None
        self.tmp.cleanup()
