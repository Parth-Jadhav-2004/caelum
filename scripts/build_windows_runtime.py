"""Stage a relocatable x64 CPython runtime and locked wheels for the NSIS installer."""

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src-tauri/windows-runtime"


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    if os.name != "nt":
        raise SystemExit("Build the Windows runtime on x64 Windows.")
    version = "3.12.15"
    run("uv", "python", "install", version)
    python = Path(subprocess.check_output(
        ["uv", "python", "find", "--system", "--managed-python", "--no-project", version], text=True, cwd=ROOT
    ).strip())
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(python.parent, DEST)
    engine = DEST / "python.exe"
    site = DEST / "Lib/site-packages"
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        requirements = work / "requirements.txt"
        run("uv", "export", "--locked", "--extra", "whisper", "--no-dev", "--no-emit-project",
            "--format", "requirements-txt", "--output-file", requirements)
        run("uv", "pip", "install", "--python", engine, "--target", site, "--only-binary", ":all:",
            "--require-hashes", "--link-mode", "copy", "-r", requirements)
        run("uv", "build", "--wheel", "--out-dir", work)
        run("uv", "pip", "install", "--python", engine, "--target", site,
            "--no-deps", "--link-mode", "copy", next(work.glob("caelum*.whl")))
    run(engine, "-I", "-c", "import sherpa_onnx, faster_whisper, sounddevice, caelum.windows_desktop")
    info = {"version": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
            "target": "windows-x64", "source": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    (site / "caelum/release.json").write_text(json.dumps(info), encoding="utf-8")


if __name__ == "__main__":
    main()
