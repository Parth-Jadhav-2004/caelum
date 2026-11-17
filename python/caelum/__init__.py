"""Caelum native Linux dictation and desktop application."""

import os
import sys
from pathlib import Path

# Optional runtime components can be installed without modifying a native
# package or the system interpreter. Do not execute .pth files; keep packaged
# dependencies first, and segregate compiled extensions by Python ABI.
_components = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    / "caelum/components"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
)
if _components.is_dir():
    sys.path.append(str(_components))
