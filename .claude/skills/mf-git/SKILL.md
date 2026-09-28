---
name: mf-git
description: Git rules for agents working in an mfos task worktree - commit format, what never to commit, forbidden operations. Use when committing in a task branch.
user-invocable: false
---

# Git in a task worktree
- You are on your own task branch in your own worktree. Commit there; nothing else.
- Commit message: `[T0007] imperative summary` (≤ 72 chars), optional body explaining why.
- Small, coherent commits. The orchestrator squash-merges, so history on your branch is for you.
- Never commit: files over 1 MB, generated data, experiment outputs, notebooks with outputs,
  secrets, `.env` files, anything under `.mfos/`.
- Never: push, merge, rebase, reset --hard, switch to main, amend commits you did not make, use `gh`.
  Hooks block these; attempts count against you.
- If you need something from main that is not in your branch, report `blocked` and say what.
