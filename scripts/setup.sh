#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# Use the distro Python so PyGObject/cairo match its installed GTK typelib ABI.
python_bin="${CAELUM_PYTHON:-/usr/bin/python3}"
for dependency in "$python_bin" uv; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency; see docs/linux.md"; exit 1; }
done
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"; import gi; gi.require_version("Gtk", "4.0"); import cairo'
uv venv --python "$python_bin" --system-site-packages --allow-existing .venv
uv sync --locked --extra dev --python "$python_bin"
echo 'Installed. Run .venv/bin/caelum init, configure credentials, then .venv/bin/caelum app.'
