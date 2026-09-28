---
name: inbox
description: Walk through open founder decisions one at a time and record each decision.
disable-model-invocation: true
allowed-tools: Bash(uv run mfos *)
---

## Open items
!`uv run mfos inbox`

For each open item, one at a time: run `uv run mfos inbox show <id>`, read every file it references,
then give me a 5-line brief — what is being asked, what the evidence says, the options, your
recommendation, and what happens after each choice. Then wait for my decision and record it with
`uv run mfos approve <id> --note "..."`, `uv run mfos reject <id> --note "..."`, or
`uv run mfos answer <id> "..."`. Never record a decision I have not explicitly given.
