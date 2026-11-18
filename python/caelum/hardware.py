"""Fast, unprivileged Linux hardware hints. No subprocesses or network probes."""

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Hardware:
    mem_total_mb: int = 0
    mem_available_mb: int = 0
    cores: int = 1
    arch: str = ""
    avx2: bool = False
    avx512: bool = False
    disk_free_mb: int = 0
    nvidia: bool = False
    language: str = "en"


def detect(config=None, directory=None):
    from .models import models_dir

    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, value = line.split(":", 1)
            memory[name] = int(value.split()[0]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    arch = platform.machine()
    flags = set()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith(("flags", "Features")):
                flags = set(line.split(":", 1)[1].split())
                break
    except (OSError, IndexError):
        pass
    try:
        cores = len(os.sched_getaffinity(0))
    except (OSError, AttributeError):
        cores = os.cpu_count() or 1
    directory = Path(directory) if directory else models_dir()
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    try:
        free = shutil.disk_usage(directory).free // 1_000_000
    except OSError:
        free = 0
    language = (config.stt.language if config else "") or (
        os.environ.get("LC_ALL") or os.environ.get("LANG") or "en"
    )
    language = language.split("_")[0].split("-")[0].split(".")[0].lower()
    if language in ("c", "posix"):
        language = "en"
    return Hardware(
        mem_total_mb=memory.get("MemTotal", 0),
        mem_available_mb=memory.get("MemAvailable", 0),
        cores=cores, arch=arch, avx2="avx2" in flags or arch == "aarch64",
        avx512=any(flag.startswith("avx512") for flag in flags), disk_free_mb=free,
        nvidia=Path("/dev/nvidiactl").exists(), language=language,
    )


def local_support(hardware):
    if hardware.arch not in ("x86_64", "aarch64", "arm64") or (
        hardware.arch == "x86_64" and not hardware.avx2
    ):
        return "Local models aren’t supported on this computer. Use Online instead."
    return None
