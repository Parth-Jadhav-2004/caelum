#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# Use Arch's Python so PyGObject/cairo match the installed GTK typelib ABI.
for dependency in /usr/bin/python uv hyprctl wl-copy; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency"; exit 1; }
done
/usr/bin/python -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0"); import cairo'
uv venv --python /usr/bin/python --system-site-packages --allow-existing .venv
uv sync --locked --extra dev --python /usr/bin/python
echo 'Installed. Run .venv/bin/caelum init, configure credentials/model, then .venv/bin/caelum serve.'
