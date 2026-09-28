---
name: work
description: Pair with the founder on one task in this session, using the same packet and checks as the autonomous loop.
disable-model-invocation: true
argument-hint: "<task id>"
allowed-tools: Bash(uv run mfos *)
---

!`uv run mfos packet $ARGUMENTS`

Read the packet above and the files it lists, propose a short plan, then implement it with me.
Run every definition-of-done command before saying we are done. When finished, tell me to run
`uv run mfos task retry $ARGUMENTS` if the loop should re-verify and integrate it, or commit on the
task branch if we worked there.
