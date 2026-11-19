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
printf '%s\n' '{"v":1,"id":1,"method":"bootstrap"}' | squashfs-root/usr/bin/caelum-engine | python3 -c 'import json,sys; assert any("result" in json.loads(s) for s in sys.stdin)'
python3 "$root/scripts/smoke_desktop.py" squashfs-root --screenshot "$work/appimage.png"
