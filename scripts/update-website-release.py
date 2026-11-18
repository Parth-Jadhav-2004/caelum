#!/usr/bin/env python3
"""Generate the website's download manifest from published, reachable stable assets.

Never guesses a URL for an unpublished target. Requires no third-party packages.
Run from the repository root before publishing the website.
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY = "Parth-Jadhav-2004/caelum"
GITHUB = f"https://github.com/{REPOSITORY}"
TARGETS = (
    ("ubuntu-2404", "Ubuntu 24.04", "apt", r"caelum_{version}-\d+_ubuntu-24\.04_amd64\.deb"),
    ("ubuntu-2604", "Ubuntu 26.04", "apt", r"caelum_{version}-\d+_ubuntu-26\.04_amd64\.deb"),
    ("debian-12", "Debian 12", "apt", r"caelum_{version}-\d+_debian-12_amd64\.deb"),
    ("arch", "Arch Linux", "pacman", r"caelum-{version}-\d+-x86_64\.pkg\.tar\.zst"),
    ("fedora", "Fedora 43", "dnf", r"caelum-{version}-\d+\.fedora43\.x86_64\.rpm"),
)


def request(url, *, method="GET", api=False):
    headers = {"User-Agent": "caelum-website-release-manifest"}
    if api and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=headers, method=method), timeout=30
    )


def build_manifest(release, read=request):
    tag = release.get("tag_name", "")
    if (
        release.get("draft")
        or release.get("prerelease")
        or not re.fullmatch(r"v\d+\.\d+\.\d+", tag)
    ):
        raise ValueError("Expected a published stable semantic-version release")
    version = tag[1:]
    base = f"{GITHUB}/releases/download/{tag}/"
    assets = {asset["name"]: asset for asset in release["assets"]}

    def asset_url(name):
        asset = assets[name]
        expected = base + name
        if asset["browser_download_url"] != expected:
            raise ValueError(f"Unexpected asset URL: {name}")
        return expected

    # Check the same published checksum file visitors will use.
    with read(asset_url("SHA256SUMS")) as response:
        sums = response.read().decode("utf-8")
    checksummed = set()
    for line in sums.splitlines():
        match = re.fullmatch(r"[a-fA-F0-9]{64}\s+\*?(.+)", line)
        if match:
            checksummed.add(match[1].removeprefix("./"))
    for name in ("update.json", "update.json.sig"):
        with read(asset_url(name), method="HEAD") as response:
            if response.status != 200:
                raise ValueError(f"Unreachable update metadata: {name}")
    packages = []
    for target, label, manager, pattern in TARGETS:
        matches = [
            name
            for name in assets
            if re.fullmatch(pattern.format(version=re.escape(version)), name)
        ]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous packages for {target}")
        if not matches:
            continue
        name = matches[0]
        if name not in checksummed:
            raise ValueError(f"Package missing from SHA256SUMS: {name}")
        try:
            with read(asset_url(name), method="HEAD") as response:
                if response.status != 200:
                    raise ValueError(f"Unreachable package: {name}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue  # A deleted/unpublished asset must never become a download option.
            raise
        size = assets[name]["size"]
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Invalid package size: {name}")
        packages.append(
            {"id": target, "name": label, "manager": manager, "file": name, "size": size}
        )
    if not packages:
        raise ValueError("No reachable, checksummed Linux packages; refusing to publish")
    return {
        "version": version,
        "releaseUrl": f"{GITHUB}/releases/tag/{tag}",
        "checksumsUrl": base + "SHA256SUMS",
        "packages": packages,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parents[1] / "website/release.json"
    )
    args = parser.parse_args()
    with request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest", api=True
    ) as response:
        release = json.load(response)
    manifest = build_manifest(release)
    # Build fully before replacing an existing manifest, including on request failures.
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Website: v{manifest['version']}, {len(manifest['packages'])} verified packages")


if __name__ == "__main__":
    main()
