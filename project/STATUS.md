# ModuleForge status
_generated 2026-09-30T13:48:19+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $24.00/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 18, failed: 2, running: 2, todo: 7

- T0023 `running` builder/implement: L1 fast PEEC moduleforge.physics.peec (trace cells, skin-corrected R, Grover bond wires, image planes) + single-core timing benchmark (attempt 1)
- T0041 `running` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)

## Recent events
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
- 2026-09-30T13:46:04+00:00 task_added {"task": "T0043"}
- 2026-09-30T13:48:18+00:00 run_finished {"run": "T0042-critic-20260930T064346-d42f", "status": "completed", "cost": 1.4038266, "subtype": "success", "report": "structured_output"}
- 2026-09-30T13:48:18+00:00 run_started {"run": "T0023-builder-20260930T064818-74f0", "task": "T0023", "role": "builder", "session": "61215666-539f-4a65-8519-e06cc03f77a1"}
- 2026-09-30T13:48:19+00:00 task_failed_attempt {"task": "T0037", "signal": "review_rejected", "action": "repair"}
