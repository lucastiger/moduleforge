# ModuleForge status
_generated 2026-09-30T01:43:29+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0005** [external_action] [O001] [O001] Pin FastHenry and rebuild it with --force before the L2 adapter (n3) starts; record D0002 at E001 registration
- **I0011** [protected_change] T0020: merge needs founder approval

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $20.15/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 14, failed: 2, needs_founder: 1, review: 1, running: 1, todo: 7

- T0020 `needs_founder` scientist/design_experiment: Select the L2 reference (license + capability audit) and pre-register E001 reference validation (attempt 1)
- T0038 `review` builder/implement: DRC: per-net copper connectivity, neck detection, terminal clearance, wire start margin, no KeyError (T0036 review) (attempt 1)
- T0040 `running` critic/review: Review T0038 (general) (attempt 1)

## Recent events
- 2026-09-30T01:37:12+00:00 task_added {"task": "T0037"}
- 2026-09-30T01:37:12+00:00 task_added {"task": "T0038"}
- 2026-09-30T01:37:35+00:00 run_finished {"run": "T0029-critic-20260929T183110-7915", "status": "completed", "cost": 1.7509468000000004, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:37:41+00:00 run_started {"run": "T0037-builder-20260929T183741-757d", "task": "T0037", "role": "builder", "session": "eb48c050-6838-4272-bd78-95b0af4b2550"}
- 2026-09-30T01:39:12+00:00 run_finished {"run": "T0037-builder-20260929T183741-757d", "status": "completed", "cost": 0.1809562, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:39:19+00:00 run_started {"run": "T0038-builder-20260929T183919-a124", "task": "T0038", "role": "builder", "session": "04590944-3de8-4a2a-82ea-aa2bc4a148c1"}
- 2026-09-30T01:39:25+00:00 verified {"task": "T0037"}
- 2026-09-30T01:39:58+00:00 run_finished {"run": "T0030-critic-20260929T183110-ad7a", "status": "completed", "cost": 2.0264781999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:40:00+00:00 inbox_opened {"id": "I0011", "kind": "protected_change", "subject": "T0020: merge needs founder approval"}
- 2026-09-30T01:40:01+00:00 run_started {"run": "T0039-critic-20260929T184001-0075", "task": "T0039", "role": "critic", "session": "fd6fb6f0-c659-4a64-ae2e-92bac2a034e7"}
- 2026-09-30T01:41:05+00:00 run_finished {"run": "T0038-builder-20260929T183919-a124", "status": "completed", "cost": 0.2498322, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:41:20+00:00 verified {"task": "T0038"}
- 2026-09-30T01:41:21+00:00 run_started {"run": "T0040-critic-20260929T184121-e5d4", "task": "T0040", "role": "critic", "session": "8d6d2424-6974-4eae-88d5-054a4af70099"}
- 2026-09-30T01:43:28+00:00 run_finished {"run": "T0039-critic-20260929T184001-0075", "status": "completed", "cost": 0.9315315999999998, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:43:29+00:00 task_failed_attempt {"task": "T0037", "signal": "review_rejected", "action": "repair"}
