#!/usr/bin/env bash
# Reuse the installed-and-tested Ubuntu 24.04 payload, including local inference.
set -euo pipefail
root=$PWD
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
dpkg-deb -x "$root"/dist/*ubuntu-24.04_amd64.deb AppDir
uv python install 3.12.15
python=$(uv python find --system --managed-python 3.12.15)
cp -a "$(dirname "$(dirname "$python")")" AppDir/opt/python
# The installed Ubuntu package supplies CPython 3.12 GI and Cairo extensions.
# Include their package directories so the HUD child uses the same bundled
# interpreter as the sidecar without adding the host Python path at runtime.
system_modules=/usr/lib/python3/dist-packages
cp -a "$system_modules/gi" "$system_modules/cairo" AppDir/opt/caelum/lib/
for package in python3-gi python3-gi-cairo python3-cairo; do
  install -Dm644 "/usr/share/doc/$package/copyright" \
    "AppDir/usr/share/licenses/caelum/third-party/$package/copyright"
done
cp AppDir/usr/share/applications/io.caelum.Dictation.desktop AppDir/caelum.desktop
cp AppDir/usr/share/icons/hicolor/scalable/apps/caelum.svg AppDir/
cat >AppDir/AppRun <<'EOF'
#!/bin/sh
set -eu
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export APPDIR
export PATH="$APPDIR/usr/bin:$PATH"
exec "$APPDIR/usr/bin/caelum-desktop" "$@"
EOF
for entry in caelum-engine caelum; do
  module=caelum.sidecar
  if [[ $entry == caelum ]]; then module=caelum.cli; fi
  cat >"AppDir/usr/bin/$entry" <<EOF
#!/bin/sh
set -eu
root=\$(CDPATH= cd -- "\$(dirname -- "\$0")/../.." && pwd)
export PYTHONPATH="\$root/opt/caelum/lib"
exec "\$root/opt/python/bin/python3" -m $module "\$@"
EOF
done
chmod +x AppDir/AppRun
fetch() {
  curl --proto '=https' -fsSL --retry 3 "$1" -o "$2"
  echo "$3  $2" | sha256sum -c -
}
fetch https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage tool e8c1169c4af66c3184d7ee110713d4be04befe671fa358e2c1591ee840553b03
fetch https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 runtime 617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46
chmod +x tool
version=$(node -p "require('$root/package.json').version")
image="$root/dist/caelum-$version-x86_64.AppImage"
ARCH=x86_64 ./tool --appimage-extract-and-run --runtime-file runtime AppDir "$image"
"$image" --appimage-extract >/dev/null
# Exercise the extracted HUD bindings with the interpreter the sidecar spawns.
PYTHONNOUSERSITE=1 PYTHONPATH="$PWD/squashfs-root/opt/caelum/lib" \
  squashfs-root/opt/python/bin/python3 - <<'PYTHON'
from pathlib import Path
import cairo
import gi

bundled = Path("squashfs-root/opt/caelum/lib").resolve()
assert all(Path(module.__file__).resolve().is_relative_to(bundled) for module in (cairo, gi))
gi.require_foreign("cairo")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

assert Gtk.get_major_version() == 4 and Gdk.Display is not None
PYTHON
printf '%s\n' '{"v":1,"id":1,"method":"bootstrap"}' | squashfs-root/usr/bin/caelum-engine | python3 -c 'import json,sys; assert any("result" in json.loads(s) for s in sys.stdin)'
python3 "$root/scripts/smoke_desktop.py" squashfs-root --screenshot "$work/appimage.png"
