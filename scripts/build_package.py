#!/usr/bin/env python3
"""Build native Linux packages with locked, target-specific Python dependencies.

Run on Linux with uv; RPM additionally needs rpmbuild. No credentials, local
configuration, transcripts, virtualenv, or git metadata enter the payload.
"""

import argparse
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "ubuntu-24.04": ("deb", "3.12"),
    "ubuntu-26.04": ("deb", "3.14"),
    "debian-12": ("deb", "3.11"),
    "debian-13": ("deb", "3.13"),
    "arch": ("arch", "3.14"),
    "fedora-43": ("rpm", "3.14"),
}


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, cwd=ROOT, **kwargs)


def archive(directory, epoch):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in sorted(directory.rglob("*")):
            info = tar.gettarinfo(path, arcname=str(path.relative_to(directory)))
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = epoch
            if path.is_file():
                with path.open("rb") as source:
                    tar.addfile(info, source)
            else:
                tar.addfile(info)
    return output.getvalue()


def ar_member(name, data, epoch):
    header = f"{name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
    return header.encode("ascii") + data + (b"\n" if len(data) % 2 else b"")


def write(path, text, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755 if executable else 0o644)


def build(target, output, epoch):
    kind, python = TARGETS[target]
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    upper = f"3.{int(python.split('.')[1]) + 1}"
    with tempfile.TemporaryDirectory(prefix="caelum-package-") as directory:
        work = Path(directory)
        stage = work / "stage"
        library = stage / "opt/caelum/lib"
        requirements = work / "requirements.txt"
        run(
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-editable",
            "--format",
            "requirements-txt",
            "--output-file",
            requirements,
            stdout=subprocess.DEVNULL,
        )
        run(
            "uv",
            "pip",
            "install",
            "--target",
            library,
            "--python-version",
            python,
            "--python-platform",
            "x86_64-manylinux_2_28",
            "--only-binary",
            ":all:",
            "--require-hashes",
            "-r",
            requirements,
        )
        shutil.copytree(
            ROOT / "src/caelum", library / "caelum", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copy2(ROOT / "config.example.toml", library / "caelum/config.example.toml")
        # Avoid metadata paths referring to the build machine.
        for bytecode in library.rglob("__pycache__"):
            shutil.rmtree(bytecode)
        write(
            stage / "usr/bin/caelum",
            """#!/bin/sh
set -eu
credential_file="${XDG_CONFIG_HOME:-$HOME/.config}/caelum/environment"
if [ -f "$credential_file" ]; then
    set -a
    . "$credential_file"
    set +a
fi
export PYTHONPATH=/opt/caelum/lib
exec /usr/bin/python3 -m caelum.cli "$@"
""",
            executable=True,
        )
        write(
            stage / "usr/share/applications/caelum.desktop",
            """[Desktop Entry]
Type=Application
Name=Caelum
Comment=Private dictation for Linux desktops
Exec=caelum app
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Audio;
StartupNotify=false
""",
        )
        docs = stage / "usr/share/doc/caelum"
        docs.mkdir(parents=True)
        for source in (ROOT / "README.md", ROOT / "docs/linux.md", ROOT / "docs/privacy.md"):
            shutil.copy2(source, docs / source.name)
        write(
            docs / "build-info.txt",
            f"Caelum {version}\nTarget: {target}\nPython: {python}\n"
            "Python dependencies: uv.lock, vendored with their upstream license metadata.\n"
            "This package does not configure credentials, autostart, or desktop shortcuts.\n",
        )
        output.mkdir(parents=True, exist_ok=True)
        if kind == "deb":
            control = work / "control"
            write(
                control / "control",
                f"""Package: caelum
Version: {version}-1
Section: sound
Priority: optional
Architecture: amd64
Maintainer: Parth Jadhav <Parth-Jadhav-2004@users.noreply.github.com>
Depends: python3 (>= {python}), python3 (<< {upper}), python3-gi, python3-cairo, gir1.2-gtk-4.0, libportaudio2, libnotify-bin, libglib2.0-bin, systemd
Installed-Size: {sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) // 1024}
Homepage: https://github.com/Parth-Jadhav-2004/caelum
Description: Private dictation for Linux desktops
 Records speech, transcribes it with your configured provider, and saves text locally.
 GNOME/KDE/X11 use explicit copy; native Hyprland integration is optional.
""",
            )
            destination = output / f"caelum_{version}-1_{target}_amd64.deb"
            destination.write_bytes(
                b"!<arch>\n"
                + b"".join(
                    ar_member(name, data, epoch)
                    for name, data in (
                        ("debian-binary", b"2.0\n"),
                        ("control.tar.gz", gzip.compress(archive(control, epoch), mtime=0)),
                        ("data.tar.gz", gzip.compress(archive(stage, epoch), mtime=0)),
                    )
                )
            )
        elif kind == "arch":
            write(
                stage / ".PKGINFO",
                f"""pkgname = caelum
pkgbase = caelum
pkgver = {version}-1
pkgdesc = Private dictation for Linux desktops
url = https://github.com/Parth-Jadhav-2004/caelum
builddate = {epoch}
packager = Caelum release build
size = {sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())}
arch = x86_64
depend = python>={python}
depend = python<{upper}
depend = python-gobject
depend = python-cairo
depend = gtk4
depend = portaudio
depend = libnotify
depend = glib2
depend = systemd
optdepend = gtk4-layer-shell: Hyprland recording overlay
optdepend = wl-clipboard: Hyprland automatic paste
""",
            )
            destination = output / f"caelum-{version}-1-x86_64.pkg.tar.zst"
            raw = work / "package.tar"
            raw.write_bytes(archive(stage, epoch))
            run("zstd", "-q", "-f", "-19", raw, "-o", destination)
        else:
            rpmroot = work / "rpm"
            for folder in ("BUILD", "BUILDROOT", "RPMS", "SOURCES", "SPECS", "SRPMS"):
                (rpmroot / folder).mkdir(parents=True)
            spec = rpmroot / "SPECS/caelum.spec"
            write(
                spec,
                f"""Name: caelum
Version: {version}
Release: 1
Summary: Private dictation for Linux desktops
License: LicenseRef-Caelum-No-License-Declared
URL: https://github.com/Parth-Jadhav-2004/caelum
BuildArch: x86_64
AutoReqProv: no
Requires: python3 >= {python}, python3 < {upper}, python3-gobject, python3-cairo, gobject-introspection, gtk4, portaudio, libnotify, glib2, systemd
%description
Dictation for Linux desktops. GNOME/KDE use explicit copy; Hyprland integration is optional.
%install
mkdir -p %{{buildroot}}
cp -a {stage}/. %{{buildroot}}/
%files
/opt/caelum
/usr/bin/caelum
/usr/share/applications/caelum.desktop
/usr/share/doc/caelum
""",
            )
            run(
                "rpmbuild",
                "--define",
                f"_topdir {rpmroot}",
                "--define",
                "_build_id_links none",
                "--define",
                "__os_install_post %{nil}",
                "-bb",
                spec,
            )
            destination = output / f"caelum-{version}-1.fedora43.x86_64.rpm"
            shutil.copy2(next((rpmroot / "RPMS").rglob("*.rpm")), destination)
        checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
        write(
            destination.with_name(destination.name + ".sha256"), f"{checksum}  {destination.name}\n"
        )
        print(destination)
        return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    epoch_value = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_value is None:
        epoch_value = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT, text=True
        ).strip()
    epoch = int(epoch_value)
    build(args.target, args.output.resolve(), epoch)
