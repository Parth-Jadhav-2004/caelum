"""Offline whisper.cpp CLI adapter. Audio lives in an anonymous Linux memory file."""

import asyncio
import os
import shutil
from pathlib import Path

from .audio import wav_bytes
from .providers import ProviderError


def check_local(config):
    binary = shutil.which(config.local_binary)
    if not binary:
        raise ProviderError("Install whisper.cpp and set its whisper-cli executable in Settings", "local_setup")
    if not config.local_model_path or not Path(config.local_model_path).is_file():
        raise ProviderError("Choose an existing whisper.cpp GGML model file in Settings", "local_setup")
    return binary


async def transcribe(config, pcm):
    binary = check_local(config)
    fd = os.memfd_create("caelum-audio", flags=0)
    process = None
    try:
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(wav_bytes(pcm))
        os.lseek(fd, 0, os.SEEK_SET)
        args = [binary, "-m", config.local_model_path, "-f", f"/proc/self/fd/{fd}",
                "-nt", "-np", "-l", config.language or "auto"]
        if config.vocabulary:
            args.extend(["--prompt", config.vocabulary])
        process = await asyncio.create_subprocess_exec(
            *args, pass_fds=(fd,), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), config.local_timeout_seconds)
        except TimeoutError:
            raise ProviderError("Local transcription timed out; choose a smaller model or increase its timeout", "timeout") from None
        if process.returncode:
            raise ProviderError("Local transcription failed; check the executable and model file", "local_setup")
        return stdout.decode("utf-8").strip()
    except (OSError, UnicodeError):
        raise ProviderError("Local transcription unavailable; check whisper.cpp installation", "local_setup") from None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        os.close(fd)
