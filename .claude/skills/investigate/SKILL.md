---
name: investigate
description: Queue an independent scientist investigation of a question or failure.
disable-model-invocation: true
argument-hint: "<objective id> <question>"
allowed-tools: Bash(uv run mfos *)
---

Request: $ARGUMENTS

Sharpen the question with me in at most two exchanges: what observation prompted it, what decision
depends on the answer, and what would count as an answer. Then queue it:

`uv run mfos task add --objective <OID> --type investigate --agent scientist --title "<short title>" --description "<the sharpened question, the triggering evidence with file paths, and the decision it informs>"`

Tell me the task id. The loop will run it with a fresh, independent context.
