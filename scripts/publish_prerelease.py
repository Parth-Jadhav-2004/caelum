#!/usr/bin/env python3
"""Publish immutable development/testing packages, or verify testing before production."""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from publish_release import GitHub, reconcile, release_files
from release_candidate import verify


def tag_for(manifest, channel):
    run, attempt = str(manifest["run_id"]), str(manifest["run_attempt"])
    if not re.fullmatch(r"[1-9]\d*", run) or not re.fullmatch(r"[1-9]\d*", attempt):
        raise ValueError("Prereleases require a GitHub candidate run and attempt")
    if channel == "development":
        suffix = f"dev.{run}.{attempt}"
    elif channel == "testing":
        # Keep rc.N compatible with installed clients' manual testing discovery.
        # A changed/rebuilt candidate needs a new workflow run, never a moved tag.
        suffix = f"rc.{run}"
    else:
        raise ValueError("Choose development or testing")
    return f"v{manifest['version']}-{suffix}"


class PrereleaseGitHub(GitHub):
    def create(self, tag, sha, notes):
        channel = "Development" if "-dev." in tag else "Testing"
        # The releases list need not reflect a newly created draft yet. Use the
        # create response (including its immutable ID) instead of listing again.
        result = self.api("repos/{owner}/{repo}/releases", {
            "tag_name": tag, "target_commitish": sha, "draft": True,
            "prerelease": True, "make_latest": "false",
            "name": f"Caelum {tag} · {channel}", "body": notes.read_text(),
        })
        if result.get("tag_name") != tag or result.get("draft") is not True:
            raise ValueError("GitHub did not return the requested draft")
        return result

    def publish(self, tag):
        subprocess.run([
            "gh", "release", "edit", tag, "--draft=false", "--prerelease", "--latest=false",
        ], check=True)


def preview_files(directory, manifest):
    # Preview channels never carry signed stable-update metadata.
    expected = set(manifest["files"]) | {"candidate.json", "SHA256SUMS"}
    if {path.name for path in directory.iterdir()} - expected:
        raise ValueError("Prereleases must not contain production update metadata")
    entries = release_files(directory)
    entries.pop("SHA256SUMS", None)
    (directory / "SHA256SUMS").write_text("".join(
        f"{info['sha256']}  {name}\n" for name, info in sorted(entries.items())
    ))
    return release_files(directory)


def notes_for(manifest, channel):
    tag = tag_for(manifest, channel)
    return (
        f"# Caelum {tag} · {channel.capitalize()}\n\n"
        "This is a prerelease for finding bugs. Install it manually with your native package "
        "manager; production automatic updates never install it.\n\n"
        f"Source commit: `{manifest['sha']}`\n\n"
        f"Candidate workflow run: `{manifest['run_id']}`, attempt `{manifest['run_attempt']}`. "
        "The five distro packages passed installation, backend IPC, simulated audio and native "
        "React bootstrap checks. The AppImage and Windows installer also passed startup smoke tests. "
        "Real microphones, providers and desktop sessions still "
        "need manual acceptance testing.\n\n"
        f"The package version is `{manifest['version']}`. Keep this release tag and the "
        "source commit when reporting bugs; package version alone does not identify a preview. "
        "See the attached candidate.json and build-info files for checksums and provenance.\n\n"
        "Use the package matching your distro, architecture and system Python. "
        "Back up configuration/history before testing; previews currently share production "
        "profile paths and are not side-by-side installations. SHA256SUMS detects download "
        "corruption; it is not a signed production update manifest.\n\n"
        "### First dictation\n\n"
        "- **Online** — enter your provider API key and consent to send practice audio.\n"
        "- **On this computer** — download a model that fits your RAM and language. "
        "After download, disconnect and practice locally without an API key.\n\n"
        "Test your microphone in setup. On GNOME, KDE and other portable desktops, "
        "choose Record on Home, speak, then Finish recording. With history enabled, "
        "choose Copy on the transcript. With history disabled, paste from the clipboard. "
        "Paste into a text editor and compare the result with what you said. "
        "On Hyprland use the displayed shortcut from your editor.\n"
    )


def publish(directory, sha, run_id, run_attempt, channel, github=None):
    manifest = verify(directory, sha, run_id, run_attempt)
    tag = tag_for(manifest, channel)
    expected = preview_files(directory, manifest)
    github = github or PrereleaseGitHub()
    release = github.release(tag)
    if channel == "testing":
        latest = github.latest_version()
        if (latest is not None and tuple(map(int, manifest["version"].split("."))) <= latest
                and (release is None or release.get("draft") is not False)):
            raise ValueError("Bump the candidate version above production before publishing to testing")
    github.ensure_tag(tag, sha)
    if release is None:
        with tempfile.TemporaryDirectory() as work:
            notes = Path(work) / "release-notes.md"
            notes.write_text(notes_for(manifest, channel))
            release = github.create(tag, sha, notes)
    if release is None or release.get("prerelease") is not True:
        raise ValueError("Expected a verified GitHub prerelease")
    present = reconcile(github, tag, directory, expected, release)
    if not release["draft"]:
        print(f"{tag} already published with identical verified assets")
        return
    for name in sorted(set(expected) - present):
        github.upload(tag, directory / name)
    if reconcile(github, tag, directory, expected, release) != set(expected):
        raise ValueError("Prerelease is incomplete; keeping draft")
    github.publish(tag)


def verify_testing(directory, sha, run_id, run_attempt, github=None):
    """Require the exact candidate to have been published to testing before signing."""
    manifest = verify(directory, sha, run_id, run_attempt)
    tag = tag_for(manifest, "testing")
    github = github or PrereleaseGitHub()
    release = github.release(tag)
    if release is None or release.get("draft") is not False or release.get("prerelease") is not True:
        raise ValueError("Publish this exact candidate to testing before production")
    expected = preview_files(directory, manifest)
    if reconcile(github, tag, directory, expected, release) != set(expected):
        raise ValueError("Testing release does not match the production candidate")
    print(f"Verified testing release {tag}; production will use the same package bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("development", "testing", "verify-testing"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("sha")
    parser.add_argument("run_id")
    parser.add_argument("run_attempt")
    args = parser.parse_args()
    if args.channel == "verify-testing":
        verify_testing(args.directory, args.sha, args.run_id, args.run_attempt)
    else:
        publish(args.directory, args.sha, args.run_id, args.run_attempt, args.channel)
