---
name: status
description: Founder briefing - what needs a decision, what is running, what changed.
disable-model-invocation: true
allowed-tools: Bash(uv run mfos *) Bash(git log *)
---

## Live state
!`uv run mfos status`

## Recent history
!`git log --oneline -12`

Brief me in at most 12 lines: (1) decisions waiting for me, most consequential first, each with your
recommendation; (2) objectives and their verdicts; (3) what is running and whether anything looks
stuck (a task in the same state for more than a day, repeated failed attempts); (4) spend vs budget.
Report only what the files above show.
