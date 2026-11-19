#!/usr/bin/env python3
"""Publish a selected testing candidate or verify its public bytes before signing."""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from publish_release import GitHub, checksummed_files, public_assets, reconcile, release_notes
from release_candidate import verify


def tag_for(manifest, rc_number):
    if not all(re.fullmatch(r"[1-9][0-9]*", str(manifest[key])) for key in ("run_id", "run_attempt")):
        raise ValueError("Prereleases require a GitHub candidate run and attempt")
    if not re.fullmatch(r"[1-9][0-9]*", rc_number):
        raise ValueError("Choose a positive RC number, for example 1")
    return f"v{manifest['version']}-rc.{rc_number}"


class PrereleaseGitHub(GitHub):
    def create(self, tag, sha, notes):
        # The releases list need not reflect a newly created draft yet. Use the
        # create response (including its immutable ID) instead of listing again.
        result = self.api("repos/{owner}/{repo}/releases", {
            "tag_name": tag, "target_commitish": sha, "draft": True,
            "prerelease": True, "make_latest": "false",
            "name": f"Caelum {tag} · Testing", "body": notes.read_text(),
        })
        if result.get("tag_name") != tag or result.get("draft") is not True:
            raise ValueError("GitHub did not return the requested draft")
        return result

    def publish(self, tag):
        subprocess.run([
            "gh", "release", "edit", tag, "--draft=false", "--prerelease", "--latest=false",
        ], check=True)


def testing_manifest(directory, sha, run_id, run_attempt):
    manifest = verify(directory, sha, run_id, run_attempt)
    if {p.name for p in directory.iterdir()} != set(manifest["files"]) | {"candidate.json"}:
        raise ValueError("Prereleases must not contain production update metadata")
    return manifest


def publish(directory, sha, run_id, run_attempt, rc_number, github=None):
    manifest = testing_manifest(directory, sha, run_id, run_attempt)
    tag = tag_for(manifest, rc_number)
    notes = (
        release_notes(manifest) + "\nInstall this testing build manually. "
        "Use a disposable profile or back up settings and history before testing.\n"
    )
    with public_assets(directory, manifest) as stage:
        publish_testing(stage, tag, manifest, notes, github)


def publish_testing(directory, tag, manifest, body, github):
    expected = checksummed_files(directory)
    github = github or PrereleaseGitHub()
    release = github.release(tag)
    latest = github.latest_version()
    if (latest is not None and tuple(map(int, manifest["version"].split("."))) <= latest
            and (release is None or release.get("draft") is not False)):
        raise ValueError("Bump the candidate version above production before publishing to testing")
    github.ensure_tag(tag, manifest["sha"])
    if release is None:
        with tempfile.TemporaryDirectory() as work:
            notes = Path(work) / "release-notes.md"
            notes.write_text(body)
            release = github.create(tag, manifest["sha"], notes)
    if release is None or release.get("prerelease") is not True:
        raise ValueError("Expected a verified GitHub prerelease")
    if release["draft"] and (release.get("body") or "").rstrip() != body.rstrip():
        raise ValueError("Draft belongs to another candidate or its release notes changed")
    present = reconcile(github, tag, directory, expected, release)
    if not release["draft"]:
        print(f"{tag} already published with identical verified assets")
        return
    for name in sorted(set(expected) - present):
        github.upload(tag, directory / name)
    if reconcile(github, tag, directory, expected, release) != set(expected):
        raise ValueError("Prerelease is incomplete; keeping draft")
    github.publish(tag)


def verify_testing(directory, sha, run_id, run_attempt, rc_number, github=None):
    """Require the exact candidate to have been published to testing before signing."""
    manifest = testing_manifest(directory, sha, run_id, run_attempt)
    tag = tag_for(manifest, rc_number)
    github = github or PrereleaseGitHub()
    release = github.release(tag)
    if release is None or release.get("draft") is not False or release.get("prerelease") is not True:
        raise ValueError("Publish this exact candidate to testing before production")
    with public_assets(directory, manifest) as stage:
        expected = checksummed_files(stage)
        if reconcile(github, tag, stage, expected, release) != set(expected):
            raise ValueError("Testing release does not match the production candidate")
    print(f"Verified testing release {tag}; production will use the same package bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("testing", "verify-testing"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("sha")
    parser.add_argument("run_id")
    parser.add_argument("run_attempt")
    parser.add_argument("rc_number")
    args = parser.parse_args()
    if args.channel == "verify-testing":
        verify_testing(args.directory, args.sha, args.run_id, args.run_attempt, args.rc_number)
    else:
        publish(args.directory, args.sha, args.run_id, args.run_attempt, args.rc_number)
