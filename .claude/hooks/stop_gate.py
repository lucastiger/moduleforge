#!/usr/bin/env python3
"""Stop hook: an implementing agent cannot finish while its definition of done fails.

Standard library only. Active only for headless runs launched by the orchestrator
(MFOS_ROLE in builder/scientist and MFOS_DOD_FILE present). Blocks at most
MAX_BLOCKS times per run so a stuck agent cannot loop forever; after that the run
ends and the orchestrator's own verification decides (it never trusts this hook
or the agent's report).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MAX_BLOCKS = 3
ROLES_GATED = {"builder", "scientist"}


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    role = os.environ.get("MFOS_ROLE", "")
    dod_path = os.environ.get("MFOS_DOD_FILE", "")
    if role not in ROLES_GATED or not dod_path or not Path(dod_path).exists():
        sys.exit(0)
    counter = Path(dod_path + ".blocks")
    blocks = int(counter.read_text()) if counter.exists() else 0
    if blocks >= MAX_BLOCKS:
        sys.exit(0)
    spec = json.loads(Path(dod_path).read_text())
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    failures = []
    for d in spec.get("deliverables", []):
        if not any(ch in d for ch in "*?[") and not d.endswith("/") and not (root / d).exists():
            failures.append(f"missing deliverable: {d}")
    cmds = [c["cmd"] for c in spec.get("checks", []) if c.get("cmd")] + list(spec.get("gate", []))
    for c in spec.get("checks", []):
        if c.get("exists") and not (root / c["exists"]).exists():
            failures.append(f"missing: {c['exists']}")
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                failures.append(f"`{cmd}` exited {r.returncode}:\n{(r.stdout + r.stderr)[-1200:]}")
        except subprocess.TimeoutExpired:
            failures.append(f"`{cmd}` timed out")
    if not failures:
        sys.exit(0)
    counter.write_text(str(blocks + 1))
    reason = ("Definition of done is not met, so you cannot finish yet "
              f"(check {blocks + 1}/{MAX_BLOCKS}). Fix the causes below, re-run the checks yourself, then finish. "
              "If a check is impossible to satisfy without violating your rules, finish with status 'blocked' "
              "and explain why.\n\n" + "\n\n".join(failures)[-6000:])
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
