#!/usr/bin/env bash
# Run from a dev checkout after npm ci and uv sync --extra dev --extra local.
set -euo pipefail
cd "$(dirname "$0")/.."
if pgrep -u "$UID" -x caelum-desktop >/dev/null ||
   { [[ -f "${XDG_RUNTIME_DIR:?}/caelum/daemon.lock" ]] &&
     ! flock -n "$XDG_RUNTIME_DIR/caelum/daemon.lock" true; }; then
  echo "Quit the running Caelum app and service before trying this build." >&2
  exit 1
fi
.venv/bin/python -c 'import caelum.sidecar, sherpa_onnx'
umask 077
mkdir -p "${XDG_STATE_HOME:-$HOME/.local/state}/caelum-dev"
profile=$(mktemp -d "${XDG_STATE_HOME:-$HOME/.local/state}/caelum-dev/profile.XXXXXXXX")
export XDG_CONFIG_HOME="$profile/config" XDG_DATA_HOME="$profile/data"
export CAELUM_CONFIG="$XDG_CONFIG_HOME/caelum/config.toml"
mkdir -p "$(dirname "$CAELUM_CONFIG")" "$XDG_DATA_HOME"
# Keep the actual session runtime and bus (Wayland, PipeWire, portals). Isolate
# history, downloads and the Secret Service credential lookup from stable.
cat >"$CAELUM_CONFIG" <<'TOML'
[app]
backend = "portable"
[stt]
key_env = "CAELUM_DEV_PROVIDER_KEY"
[cleanup]
key_env = "CAELUM_DEV_PROVIDER_KEY"
[desktop]
check_updates = false
TOML
printf 'Fresh portable test profile: %s\n' "$profile"
exec npm run tauri dev
