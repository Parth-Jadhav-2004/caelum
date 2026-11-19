"""Fast, unprivileged desktop hardware hints. No subprocesses or network probes."""

import ctypes
import os
import platform
import shutil
from dataclasses import dataclass
from itertools import count
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


def _windows_locale():
    name = ctypes.create_unicode_buffer(85)  # LOCALE_NAME_MAX_LENGTH
    if ctypes.windll.kernel32.GetUserDefaultLocaleName(name, len(name)):
        return name.value or "en"
    return "en"


def _windows_nvidia():
    import pywintypes
    import win32api

    try:
        for index in count():
            device = win32api.EnumDisplayDevices(None, index)
            if device.DeviceID.upper().startswith("PCI\\VEN_10DE&"):
                return True
    except pywintypes.error:  # End of enumeration or no accessible adapters.
        return False


def detect(config=None, directory=None):
    from .models import models_dir

    memory = {}
    flags = set()
    language = config.stt.language if config else ""
    arch = platform.machine()
    if os.name == "nt":
        class Memory(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint32), ("load", ctypes.c_uint32),
                        *((name, ctypes.c_uint64) for name in
                          ("total", "available", "page", "free_page", "virtual", "free_virtual", "extended"))]

        status = Memory()
        status.size = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            memory.update(MemTotal=status.total // 1048576, MemAvailable=status.available // 1048576)
        if arch.lower() == "amd64":
            arch = "x86_64"
        if ctypes.windll.kernel32.IsProcessorFeaturePresent(40):
            flags.add("avx2")
        language = language or _windows_locale()
        nvidia = _windows_nvidia()
    else:
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                name, value = line.split(":", 1)
                memory[name] = int(value.split()[0]) // 1024
        except (OSError, ValueError, IndexError):
            pass
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith(("flags", "Features")):
                    flags = set(line.split(":", 1)[1].split())
                    break
        except (OSError, IndexError):
            pass
        language = language or os.environ.get("LC_ALL") or os.environ.get("LANG") or "en"
        nvidia = Path("/dev/nvidiactl").exists()
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
    language = language.split("_")[0].split("-")[0].split(".")[0].lower()
    if language in ("c", "posix"):
        language = "en"
    return Hardware(
        mem_total_mb=memory.get("MemTotal", 0),
        mem_available_mb=memory.get("MemAvailable", 0),
        cores=cores, arch=arch, avx2="avx2" in flags or arch == "aarch64",
        avx512=any(flag.startswith("avx512") for flag in flags), disk_free_mb=free,
        nvidia=nvidia, language=language,
    )


def local_support(hardware):
    if hardware.arch not in ("x86_64", "aarch64", "arm64") or (
        hardware.arch == "x86_64" and not hardware.avx2
    ):
        return "Local models aren’t supported on this computer. Use Online instead."
    return None
