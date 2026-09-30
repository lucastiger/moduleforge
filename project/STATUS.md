# ModuleForge status
_generated 2026-09-30T13:45:36+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $22.60/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 17, failed: 2, review: 1, running: 2, todo: 6

- T0037 `review` builder/implement: Fingerprint: hash LayerStack.kind, pin every hashed input with a test, fix the docstring (T0035 review) (attempt 2)
- T0041 `running` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)
- T0042 `running` critic/review: Review T0037 (general) (attempt 1)

## Recent events
- 2026-09-30T01:46:09+00:00 run_finished {"run": "T0040-critic-20260929T184121-e5d4", "status": "completed", "cost": 1.2127989999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T01:46:12+00:00 inbox_opened {"id": "I0012", "kind": "protected_change", "subject": "T0038: merge needs founder approval"}
- 2026-09-30T02:00:56+00:00 inbox_resolved {"id": "I0011", "status": "approved", "note": "Approved (founder): merge audit note + E001 draft + runner; T0029/T0030 findings go to a scientist follow-up befo
- 2026-09-30T02:01:05+00:00 merged {"task": "T0020"}
- 2026-09-30T02:01:05+00:00 inbox_opened {"id": "I0013", "kind": "experiment_registration", "subject": "register E001 (pre-registration)"}
- 2026-09-30T02:09:35+00:00 inbox_resolved {"id": "I0005", "status": "answered", "note": "Done (founder session, 2026-09-30): provision_compute.sh pinned to fasthenry-3.0wr-031424 (xictools d28932a, sha2
- 2026-09-30T13:37:31+00:00 run_started {"run": "T0037-builder-20260930T063731-ab29", "task": "T0037", "role": "builder", "session": "f91e6d4a-da51-41f7-8a37-58fb22f69ed6"}
- 2026-09-30T13:38:05+00:00 inbox_resolved {"id": "I0012", "status": "approved", "note": "Approved per founder's standing instruction to follow the recommendation: DoD verified; T0040 accept_with_caveats
- 2026-09-30T13:38:35+00:00 merged {"task": "T0038"}
- 2026-09-30T13:42:17+00:00 task_added {"task": "T0041"}
- 2026-09-30T13:42:22+00:00 run_started {"run": "T0041-scientist-20260930T064222-9471", "task": "T0041", "role": "scientist", "session": "3cd7c2d3-b028-4a92-9f50-8f4f732a257a"}
- 2026-09-30T13:43:30+00:00 run_finished {"run": "T0037-builder-20260930T063731-ab29", "status": "completed", "cost": 1.2335206, "subtype": "success", "report": "structured_output"}
- 2026-09-30T13:43:45+00:00 verified {"task": "T0037"}
- 2026-09-30T13:43:46+00:00 run_started {"run": "T0042-critic-20260930T064346-d42f", "task": "T0042", "role": "critic", "session": "e5cc6f49-1f17-42ef-9307-c742ed57d8ba"}
- 2026-09-30T13:44:30+00:00 loop_started {"pid": 1039}
