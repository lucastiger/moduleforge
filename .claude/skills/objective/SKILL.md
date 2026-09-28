---
name: objective
description: Turn a founder idea into a falsifiable, machine-evaluable objective draft.
disable-model-invocation: true
argument-hint: "<one-sentence idea>"
allowed-tools: Bash(uv run mfos objective *) Read Edit Write
---

Idea: $ARGUMENTS

Interview me briefly, then draft the objective. Work in this order and push back where I am vague:
1. The decision this objective informs, and what we do if it passes vs fails.
2. A falsifiable hypothesis, its null, and the scope (in / out).
3. The evidence plan: which experiments (new ids E0xx), what each measures, against which reference.
4. Acceptance: `pass_all` criteria on metrics with confidence intervals (`use: ci`), and `fail_any`
   kill criteria that are definitely-false conditions. Thresholds must be justified by the decision,
   not by what seems achievable. Set `max_evaluations` (default 3).
5. Failure modes with detection and response. Budget (USD, CPU-hours, wall days). Risk level.

Create it with `uv run mfos objective new <OID>` (next free id), fill `project/objectives/<OID>/objective.yaml`
from `templates/objective.yaml`, validate with `uv run mfos objective show <OID>`, and show me the file.
Do NOT approve it. Approval is my action: `uv run mfos objective approve <OID>`.
