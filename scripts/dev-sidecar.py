"""Create the required target-suffixed sidecar launcher (no secrets or local data)."""

import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rustc = shutil.which("rustc") or str(Path.home() / ".cargo/bin/rustc")
target = subprocess.check_output([rustc, "-vV"], text=True).split("host: ")[1].splitlines()[0]
path = root / "src-tauri/binaries" / f"caelum-engine-{target}"
path.parent.mkdir(exist_ok=True)
path.write_text(
    '#!/bin/sh\nset -eu\nengine_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport PYTHONPATH="$engine_dir/../../opt/caelum/lib"\nexec /usr/bin/python3 -m caelum.sidecar "$@"\n'
)
path.chmod(0o755)
