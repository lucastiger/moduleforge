# ModuleForge status
_generated 2026-09-30T13:37:59+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0012** [protected_change] T0038: merge needs founder approval
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $21.36/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 16, failed: 2, needs_founder: 1, running: 1, todo: 6

- T0037 `running` builder/implement: Fingerprint: hash LayerStack.kind, pin every hashed input with a test, fix the docstring (T0035 review) (attempt 2)
- T0038 `needs_founder` builder/implement: DRC: per-net copper connectivity, neck detection, terminal clearance, wire start margin, no KeyError (T0036 review) (attempt 1)

## Recent events
- 2026-09-30T01:39:58+00:00 run_finished {"run": "T0030-critic-20260929T183110-ad7a", "status": "completed", "cost": 2.0264781999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:40:00+00:00 inbox_opened {"id": "I0011", "kind": "protected_change", "subject": "T0020: merge needs founder approval"}
- 2026-09-30T01:40:01+00:00 run_started {"run": "T0039-critic-20260929T184001-0075", "task": "T0039", "role": "critic", "session": "fd6fb6f0-c659-4a64-ae2e-92bac2a034e7"}
- 2026-09-30T01:41:05+00:00 run_finished {"run": "T0038-builder-20260929T183919-a124", "status": "completed", "cost": 0.2498322, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:41:20+00:00 verified {"task": "T0038"}
- 2026-09-30T01:41:21+00:00 run_started {"run": "T0040-critic-20260929T184121-e5d4", "task": "T0040", "role": "critic", "session": "8d6d2424-6974-4eae-88d5-054a4af70099"}
- 2026-09-30T01:43:28+00:00 run_finished {"run": "T0039-critic-20260929T184001-0075", "status": "completed", "cost": 0.9315315999999998, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:43:29+00:00 task_failed_attempt {"task": "T0037", "signal": "review_rejected", "action": "repair"}
- 2026-09-30T01:46:09+00:00 run_finished {"run": "T0040-critic-20260929T184121-e5d4", "status": "completed", "cost": 1.2127989999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:46:12+00:00 inbox_opened {"id": "I0012", "kind": "protected_change", "subject": "T0038: merge needs founder approval"}
- 2026-09-30T02:00:56+00:00 inbox_resolved {"id": "I0011", "status": "approved", "note": "Approved (founder): merge audit note + E001 draft + runner; T0029/T0030 findings go to a scientist follow-up befo
- 2026-09-30T02:01:05+00:00 merged {"task": "T0020"}
- 2026-09-30T02:01:05+00:00 inbox_opened {"id": "I0013", "kind": "experiment_registration", "subject": "register E001 (pre-registration)"}
- 2026-09-30T02:09:35+00:00 inbox_resolved {"id": "I0005", "status": "answered", "note": "Done (founder session, 2026-09-30): provision_compute.sh pinned to fasthenry-3.0wr-031424 (xictools d28932a, sha2
- 2026-09-30T13:37:31+00:00 run_started {"run": "T0037-builder-20260930T063731-ab29", "task": "T0037", "role": "builder", "session": "f91e6d4a-da51-41f7-8a37-58fb22f69ed6"}
