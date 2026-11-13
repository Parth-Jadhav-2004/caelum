#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
python3 scripts/dev-sidecar.py
exec npx --no-install tauri "$@"
