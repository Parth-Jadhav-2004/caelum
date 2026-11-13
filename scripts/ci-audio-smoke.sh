#!/usr/bin/env bash
# Run CI checks against an isolated, hardware-free PulseAudio server.
set -euo pipefail
# Minimal Arch containers do not run systemd-sysusers during package install.
if ! getent group pulse >/dev/null; then groupadd --system pulse; fi
if ! id pulse >/dev/null 2>&1; then
  useradd --system --gid pulse --home-dir /var/run/pulse --shell /usr/bin/nologin pulse
fi
pulse_dir=$(mktemp -d)
chown pulse:pulse "$pulse_dir"
export PULSE_SERVER="unix:$pulse_dir/native"
pulseaudio --system -n --daemonize=no --exit-idle-time=-1 \
  --disallow-exit --disallow-module-loading --log-target=stderr \
  --load="module-native-protocol-unix socket=$pulse_dir/native auth-anonymous=1" \
  --load="module-null-sink sink_name=ci" >"$pulse_dir/server.log" 2>&1 &
pulse_pid=$!
trap 'kill "$pulse_pid" || true; rm -rf "$pulse_dir"' EXIT
ready=false
for attempt in {1..50}; do
  if pactl info >/dev/null 2>&1; then ready=true; break; fi
  sleep 0.1
done
if [[ "$ready" != true ]]; then cat "$pulse_dir/server.log"; exit 1; fi
"$@"
