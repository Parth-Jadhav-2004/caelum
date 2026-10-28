#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
credential_file="${XDG_CONFIG_HOME:-$HOME/.config}/caelum/environment"
if [[ -f "$credential_file" ]]; then
  set -a
  source "$credential_file"
  set +a
fi
if (( $# == 0 )); then
  set -- serve
fi
exec "$project_dir/.venv/bin/caelum" "$@"
