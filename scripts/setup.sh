#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python_bin="${CAELUM_PYTHON:-/usr/bin/python3}"
for dependency in "$python_bin" uv npm cargo; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency; see docs/linux.md"; exit 1; }
done
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
# System GI is optional and used only by the isolated native layer-shell HUD.
uv venv --python "$python_bin" --system-site-packages --allow-existing .venv
uv sync --locked --extra dev --python "$python_bin"
npm ci
uv run python scripts/generate-contracts.py
python3 scripts/dev-sidecar.py
echo 'Installed. Run npm run tauri dev; first-run setup configures the provider and microphone.'
