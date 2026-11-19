#!/usr/bin/env python3
"""Resolve a successful main or dev candidate before granting publication permissions."""

import json
import os
import re
import subprocess


def resolve(run, workflow_id, repository):
    if (
        run.get("workflow_id") != workflow_id
        or run.get("head_repository", {}).get("full_name") != repository
        or run.get("head_branch") not in ("main", "dev")
        or run.get("event") not in ("push", "workflow_dispatch")
        or run.get("status") != "completed" or run.get("conclusion") != "success"
        or not isinstance(run.get("head_sha"), str)
        or not re.fullmatch(r"[a-f0-9]{40}", run["head_sha"])
        or type(run.get("run_attempt")) is not int or run["run_attempt"] < 1
    ):
        raise ValueError("Select a completed successful candidate built from the candidate branch")
    return {"sha": run["head_sha"], "attempt": run["run_attempt"]}


def main():
    run_id, channel = os.environ["RUN_ID"], os.environ["CHANNEL"]
    if not re.fullmatch(r"[1-9]\d*", run_id) or channel not in ("testing", "production"):
        raise ValueError("Choose a numeric candidate run ID and a publication channel")
    if channel == "production" and os.environ.get("QUALIFIED") != "true":
        raise ValueError("Production requires completed manual desktop acceptance")

    def api(path):
        return json.loads(subprocess.check_output(["gh", "api", path]))

    repository = os.environ["GH_REPO"]
    ref = os.environ["GITHUB_REF"]
    allowed = ("refs/heads/main", "refs/heads/dev") if channel == "testing" else ("refs/heads/main",)
    if ref not in allowed:
        raise ValueError("Run promotion from an allowed integration branch")
    branch = ref.removeprefix("refs/heads/")
    if channel == "production" and api(f"repos/{repository}/issues/26")["state"] != "closed":
        raise ValueError("Production is on hold pending the evidence in issue #26")
    workflow = api(f"repos/{repository}/actions/workflows/release.yml")
    run = api(f"repos/{repository}/actions/runs/{run_id}")
    identity = resolve(run, workflow["id"], repository)
    tree = api(f"repos/{repository}/git/commits/{identity['sha']}")["tree"]["sha"]
    tip = api(f"repos/{repository}/commits/{branch}")
    if tip["sha"] != os.environ["GITHUB_SHA"] or tip["commit"]["tree"]["sha"] != tree:
        raise ValueError("Promotion branch must contain the exact candidate tree")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"sha={identity['sha']}\nattempt={identity['attempt']}\nrun_id={run_id}\n")


if __name__ == "__main__":
    main()
