---
name: resume
description: Reorient after time away or a crash - what happened, what is running, what to do next.
disable-model-invocation: true
allowed-tools: Bash(uv run mfos *) Bash(git log *) Bash(cat *) Bash(systemctl --user status mfos*)
---

!`uv run mfos status`

!`git log --oneline --since="3 days ago" | head -30`

Orchestrator heartbeat (UTC): !`cat .mfos/heartbeat 2>/dev/null || echo "no heartbeat"`

Tell me: (1) what completed and what failed since the last heartbeat or my last session; (2) what
is running now and whether the loop is alive (heartbeat older than 5 minutes means it is not);
(3) decisions waiting for me. If the loop is down, give me the exact restart command
(`systemctl --user restart mfos` on the forge box, or `uv run mfos loop` in tmux). Interrupted agent
runs are resumed automatically on restart; do not re-run anything by hand.
