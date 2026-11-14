#!/usr/bin/env bash
# Fixed upstream release and checksum, updated through a reviewed PR.
set -euo pipefail
workflow_tools=$(mktemp -d)
trap 'rm -rf "$workflow_tools"' EXIT
curl --proto '=https' --tlsv1.2 -fsSL \
  https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz \
  -o "$workflow_tools/actionlint.tar.gz"
printf '%s  %s\n' 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 "$workflow_tools/actionlint.tar.gz" | sha256sum -c -
tar -xzf "$workflow_tools/actionlint.tar.gz" -C "$workflow_tools" actionlint
"$workflow_tools/actionlint" -shellcheck= -pyflakes= .github/workflows/*.yml
