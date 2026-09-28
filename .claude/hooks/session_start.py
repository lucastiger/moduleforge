#!/usr/bin/env python3
"""SessionStart hook: orient every session in one screen. Standard library only.

Agent runs get their role contract; founder sessions get the live project status.
Plain stdout from SessionStart is added to Claude's context.
"""
import os
import sys
from pathlib import Path


def main() -> None:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    role = os.environ.get("MFOS_ROLE")
    if role:
        print(f"Session context: you are the `{role}` agent on task {os.environ.get('MFOS_TASK_ID', '?')} "
              f"for objective {os.environ.get('MFOS_OBJECTIVE', '?')}. The task packet named in the prompt is your "
              "complete brief. Deterministic checks run by the orchestrator decide whether this work counts; "
              "your own report does not. Hooks enforce your write scope and block integration commands.")
        return
    status = root / "project" / "STATUS.md"
    if status.exists():
        lines = status.read_text().splitlines()[:40]
        print("Current ModuleForge status (from project/STATUS.md; regenerate with `uv run mfos status`):")
        print("\n".join(lines)[:3500])
    print("\nFounder commands: /status, /inbox, /objective, /work <task>, /investigate <question>, "
          "/thesis-review, /resume. State lives in project/; policy in .mfos/policy.toml.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break a session over a status print
        print(f"(session_start hook: {e})", file=sys.stderr)
