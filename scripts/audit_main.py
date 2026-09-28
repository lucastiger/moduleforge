"""Server-side tripwire for direct commits on main by the orchestrator's identity.

Rules for commits authored by mfos-bot:
  * a commit touching a protected path must carry `Founder-Approved: I####` and that inbox item
    must exist in the repository with status `approved` — except
  * newly added registered specs under experiments/specs/, which require an approved
    `experiment_registration` inbox item for that experiment id.
Anything else fails the job, and GitHub notifies the founder.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

BOT_EMAIL = "mfos-bot@users.noreply.github.com"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def inbox() -> dict[str, dict]:
    out = {}
    for p in Path("project/inbox").glob("I*.yaml"):
        d = yaml.safe_load(p.read_text()) or {}
        out[d.get("id", p.stem)] = d
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2 days ago")
    a = ap.parse_args()
    protected = tomllib.loads(Path(".mfos/policy.toml").read_text()).get("protected_paths", [])
    items = inbox()
    bad = []
    for line in git("log", f"--since={a.since}", "--format=%H%x09%ae", "main").splitlines():
        sha, email = line.split("\t")
        if email != BOT_EMAIL:
            continue
        body = git("show", "-s", "--format=%B", sha)
        approval = re.search(r"Founder-Approved:\s*(I\d+)", body)
        for f in git("show", "--name-only", "--format=", sha).split():
            if not any(fnmatch.fnmatch(f, g) for g in protected):
                continue
            if f.startswith("experiments/specs/"):
                eid = Path(f).stem
                if any(i.get("kind") == "experiment_registration" and i.get("status") == "approved"
                       and eid in i.get("refs", []) for i in items.values()):
                    continue
            if approval and items.get(approval.group(1), {}).get("status") == "approved":
                continue
            bad.append(f"{sha[:10]} touched protected {f} without a verifiable founder approval")
    for b in bad:
        print("UNEXPECTED", b)
    print("audit:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
