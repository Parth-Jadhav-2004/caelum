"""Smoke-test an extracted native package without installing it or reading user data.

Usage: /usr/bin/python3 scripts/smoke_package.py /tmp/extracted-package
Run on the target distro and Python ABI. Does not capture audio or call providers.
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def check(root):
    root = Path(root).resolve()
    for name in ("caelum", "caelum-desktop", "caelum-engine"):
        path = root / "usr/bin" / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Missing executable: {name}")
    with tempfile.TemporaryDirectory(prefix="caelum-package-smoke-") as directory:
        work = Path(directory)
        for name in ("config", "data", "runtime"):
            (work / name).mkdir(mode=0o700)
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(work / "config"),
            "XDG_DATA_HOME": str(work / "data"),
            "XDG_RUNTIME_DIR": str(work / "runtime"),
            "CAELUM_CONFIG": str(work / "config/config.toml"),
        }
        for key in ("GROQ_API_KEY", "CAELUM_OWNER_PID"):
            env.pop(key, None)
        requests = [
            {"v": 1, "id": 1, "method": "bootstrap"},
            {"v": 1, "id": 2, "method": "status"},
            {"v": 1, "id": 3, "method": "history"},
        ]
        result = subprocess.run(
            [str(root / "usr/bin/caelum-engine")],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
            env=env,
        )
        frames = {
            frame["id"]: frame
            for line in result.stdout.splitlines()
            if "id" in (frame := json.loads(line))
        }
        assert frames[1]["result"]["version"] == 1
        assert frames[2]["result"]["running"] is False
        assert frames[3]["result"] == []
        env["PYTHONPATH"] = str(root / "opt/caelum/lib")
        subprocess.run(
            [
                "/usr/bin/python3",
                "-S",
                "-c",
                "import sys; import caelum.sidecar, numpy, httpx, sounddevice; "
                "assert 'gi.repository.Gtk' not in sys.modules",
            ],
            env=env,
            check=True,
            timeout=10,
        )
    print(
        "Package smoke passed: executables, vendored imports, IPC, EOF, isolated data; no GTK main UI"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    check(parser.parse_args().root)
