"""Collect redistributable license/notice text for frontend and Rust dependencies."""

import json
import shutil
import subprocess
from pathlib import Path


def collect(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    records = []

    def add(ecosystem, name, version, license_id, source):
        folder = destination / ecosystem / (name.replace("/", "_") + "-" + version)
        files = []
        candidates = [
            path
            for path in source.iterdir()
            if path.name.lower().startswith(("license", "licence", "copying", "notice"))
        ]
        fallback = (
            root / "packaging/licenses" / ecosystem / (name.replace("/", "_") + "-" + version)
        )
        if fallback.is_dir():
            candidates.extend(fallback.iterdir())
        for path in sorted(candidates):
            allowed = source if path.parent == source else fallback
            if (
                path.is_symlink()
                or not path.is_file()
                or not path.resolve().is_relative_to(allowed.resolve())
            ):
                continue
            if path.stat().st_size > 200_000:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / path.name
            shutil.copy2(path, target)
            files.append(str(target.relative_to(destination)))
        records.append(
            {
                "ecosystem": ecosystem,
                "name": name,
                "version": version,
                "license": license_id or "UNKNOWN",
                "files": sorted(set(files)),
            }
        )

    lock = json.loads((root / "package-lock.json").read_text())
    for name, package in lock["packages"].items():
        if not name or package.get("dev") or not (root / name).is_dir():
            continue
        metadata = json.loads((root / name / "package.json").read_text())
        add("npm", metadata["name"], metadata["version"], metadata.get("license"), root / name)
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo/bin/cargo")
    metadata = json.loads(
        subprocess.check_output(
            [
                cargo,
                "metadata",
                "--locked",
                "--format-version=1",
                "--filter-platform=x86_64-unknown-linux-gnu",
                "--manifest-path",
                str(root / "src-tauri/Cargo.toml"),
            ],
            cwd=root,
        )
    )
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    selected, pending = set(), [metadata["resolve"]["root"]]
    while pending:
        identifier = pending.pop()
        if identifier in selected:
            continue
        selected.add(identifier)
        pending.extend(
            dep["pkg"]
            for dep in nodes[identifier]["deps"]
            if any(kind["kind"] != "dev" for kind in dep["dep_kinds"])
        )
    for package in metadata["packages"]:
        if package["id"] in selected and package["source"] is not None:
            add(
                "cargo",
                package["name"],
                package["version"],
                package["license"],
                Path(package["manifest_path"]).parent,
            )
    for package in metadata["packages"]:
        if package["id"] not in selected or package.get("license") != "MPL-2.0":
            continue
        source = Path(package["manifest_path"]).parent
        archive = (
            source.parent.parent.parent
            / "cache"
            / source.parent.name
            / f"{package['name']}-{package['version']}.crate"
        )
        sources = destination / "corresponding-source"
        sources.mkdir(exist_ok=True)
        shutil.copy2(archive, sources / archive.name)
    (destination / "SOURCE-NOTICE.txt").write_text(
        "Unmodified MPL-2.0 Rust crate source archives are provided in corresponding-source/.\n"
        "Versions and registry checksums are pinned in Caelum's published src-tauri/Cargo.lock.\n"
        "Python dependency notices remain alongside vendored *.dist-info metadata.\n"
        "License metadata and additional public upstream notice provenance are in inventory.json and provenance.json.\n"
    )
    shutil.copy2(root / "packaging/licenses/provenance.json", destination / "provenance.json")
    (destination / "inventory.json").write_text(json.dumps(records, indent=2) + "\n")
    return records
