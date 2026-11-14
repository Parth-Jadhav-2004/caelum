#!/usr/bin/env python3
"""Promote tested bytes, resume drafts, and never replace published release assets."""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from release_candidate import ROOT, digest, verify
from sign_release import sign


class GitHub:
    def api(self, path, data=None):
        args = ["gh", "api", path]
        if data is not None:
            args += ["--method", "POST", "--input", "-"]
        paged = data is None and ("/assets?" in path or "/matching-refs/" in path)
        if paged:
            args += ["--paginate", "--slurp"]
        value = subprocess.check_output(args, input=json.dumps(data).encode() if data else None)
        parsed = json.loads(value)
        return [item for page in parsed for item in page] if paged else parsed

    def release(self, tag):
        # Listing avoids treating authentication/network failures as "not found".
        releases = json.loads(
            subprocess.check_output(
                ["gh", "api", "--paginate", "--slurp", "repos/{owner}/{repo}/releases?per_page=100"]
            )
        )
        return next(
            (release for page in releases for release in page if release["tag_name"] == tag), None
        )

    def latest_version(self):
        releases = json.loads(
            subprocess.check_output(
                ["gh", "api", "--paginate", "--slurp", "repos/{owner}/{repo}/releases?per_page=100"]
            )
        )
        versions = []
        for page in releases:
            for release in page:
                if release["draft"] or release["prerelease"]:
                    continue
                tag = release["tag_name"]
                if re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
                    versions.append(tuple(map(int, tag[1:].split("."))))
        return max(versions, default=None)

    def ensure_tag(self, tag, sha):
        refs = self.api(f"repos/{{owner}}/{{repo}}/git/matching-refs/tags/{tag}")
        ref = next((item for item in refs if item["ref"] == f"refs/tags/{tag}"), None)
        if ref is None:
            self.api("repos/{owner}/{repo}/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
            return
        obj = ref["object"]
        while obj["type"] == "tag":
            obj = self.api(f"repos/{{owner}}/{{repo}}/git/tags/{obj['sha']}")["object"]
        if obj["type"] != "commit" or obj["sha"] != sha:
            raise ValueError("Existing version tag points to another commit; publish a new version")

    def create(self, tag, sha, notes):
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                "--draft",
                "--verify-tag",
                "--target",
                sha,
                "--title",
                f"Caelum {tag}",
                "--notes-file",
                str(notes),
            ],
            check=True,
        )

    def download(self, tag, name, directory):
        subprocess.run(
            ["gh", "release", "download", tag, "--pattern", name, "--dir", str(directory)],
            check=True,
        )

    def upload(self, tag, path):
        # Deliberately no --clobber: changed bytes require a new version.
        subprocess.run(["gh", "release", "upload", tag, str(path)], check=True)

    def publish(self, tag):
        subprocess.run(["gh", "release", "edit", tag, "--draft=false", "--latest"], check=True)


def release_files(directory):
    return {path.name: digest(path) for path in directory.iterdir()}


def reconcile(github, tag, directory, expected, release):
    # Fetch all asset pages: large provenance sets must not be silently truncated.
    assets = github.api(f"repos/{{owner}}/{{repo}}/releases/{release['id']}/assets?per_page=100")
    names = [asset["name"] for asset in assets]
    if len(names) != len(set(names)) or set(names) - set(expected):
        raise ValueError("Release has duplicate or unexpected assets")
    with tempfile.TemporaryDirectory(prefix="caelum-release-verify-") as work:
        for asset in assets:
            name = asset["name"]
            if asset["state"] != "uploaded" or asset["size"] != expected[name]["size"]:
                raise ValueError(
                    f"Release asset is incomplete: {name}; remove the failed draft upload before retrying"
                )
            github.download(tag, name, Path(work))
            if digest(Path(work) / name) != expected[name]:
                raise ValueError(
                    f"Release asset differs: {name}; existing assets are never replaced"
                )
    if not release["draft"] and set(names) != set(expected):
        raise ValueError("Published release is incomplete; it cannot be modified by this publisher")
    return set(names)


def publish(directory, sha, run_id, run_attempt, private_key, github=None):
    manifest = verify(directory, sha, run_id, run_attempt)
    tag = "v" + manifest["version"]
    notes = ROOT / "docs" / f"release-{manifest['version']}.md"
    if not notes.is_file() or not notes.read_text().strip():
        raise ValueError(f"Reviewed release notes are required: {notes.name}")
    # Candidate creation time makes signing deterministic across publisher reruns.
    sign(directory, private_key, now=manifest["created"])
    checksums = directory / "SHA256SUMS"
    entries = {path.name: digest(path) for path in directory.iterdir() if path != checksums}
    checksums.write_text(
        "".join(f"{info['sha256']}  {name}\n" for name, info in sorted(entries.items()))
    )
    expected = release_files(directory)
    github = github or GitHub()
    latest = github.latest_version()
    if latest is not None and tuple(map(int, manifest["version"].split("."))) < latest:
        raise ValueError("Cannot publish an older stable version over a newer release")
    # Check tag before creating a draft, and never force-update it.
    github.ensure_tag(tag, sha)
    release = github.release(tag)
    if release is None:
        github.create(tag, sha, notes)
        release = github.release(tag)
    if release is None:
        raise ValueError("Draft creation could not be verified")
    present = reconcile(github, tag, directory, expected, release)
    if not release["draft"]:
        print(f"{tag} already published with identical verified assets")
        return
    for name in sorted(set(expected) - present):
        github.upload(tag, directory / name)
    complete = reconcile(github, tag, directory, expected, github.release(tag))
    if complete != set(expected):
        raise ValueError("Release is incomplete; keeping draft")
    github.publish(tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("sha")
    parser.add_argument("run_id")
    parser.add_argument("run_attempt")
    parser.add_argument("private_key", type=Path)
    args = parser.parse_args()
    publish(args.directory, args.sha, args.run_id, args.run_attempt, args.private_key)
