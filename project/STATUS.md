# ModuleForge status
_generated 2026-10-05T08:34:01+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $173.25/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 50, failed: 3, review: 1, running: 2, todo: 7

- T0071 `running` builder/implement: Complete moduleforge.solvers.l2 for E001: exact bars, two-port Z, ties; frozen E001 smoke passes within 40 min (attempt 1)
- T0074 `review` builder/implement: L2 layout path: Layout -> exact-kernel loop_inductance reusing l2_core's compressed wire-to-plane operator (l2_layout.py) (attempt 1)
- T0082 `running` critic/review: Review T0074 (numerics) (attempt 1)

## Recent events
- 2026-10-05T06:31:19+00:00 capacity_backoff {"task": "T0071", "minutes": 30}
- 2026-10-05T07:01:29+00:00 run_started {"run": "T0071-builder-20261005T000129-220a", "task": "T0071", "role": "builder", "session": "fae22405-df78-4c99-85fb-e7dc8a131053"}
- 2026-10-05T07:01:29+00:00 run_started {"run": "T0074-builder-20261005T000129-0208", "task": "T0074", "role": "builder", "session": "b91e6a78-7189-4590-a8b1-5a3b68840cd9"}
- 2026-10-05T07:02:02+00:00 run_finished {"run": "T0074-builder-20261005T000129-0208", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T07:02:02+00:00 capacity_backoff {"task": "T0074", "minutes": 30}
- 2026-10-05T07:02:02+00:00 run_finished {"run": "T0071-builder-20261005T000129-220a", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T07:02:02+00:00 capacity_backoff {"task": "T0071", "minutes": 30}
- 2026-10-05T07:32:15+00:00 run_started {"run": "T0071-builder-20261005T003215-ff71", "task": "T0071", "role": "builder", "session": "1b44fcc0-0839-493c-ba85-c54ea72e5423"}
- 2026-10-05T07:32:15+00:00 run_started {"run": "T0074-builder-20261005T003215-4c55", "task": "T0074", "role": "builder", "session": "177e1f8d-208a-44bc-be0e-fc2d5d09b7d1"}
- 2026-10-05T08:13:38+00:00 run_finished {"run": "T0074-builder-20261005T003215-4c55", "status": "completed", "cost": 4.0163486, "subtype": "success", "report": "structured_output"}
- 2026-10-05T08:18:52+00:00 verified {"task": "T0074"}
- 2026-10-05T08:18:54+00:00 run_started {"run": "T0081-critic-20261005T011854-03d5", "task": "T0081", "role": "critic", "session": "89290046-37d4-4a31-8823-a3f5624a61a6"}
- 2026-10-05T08:19:27+00:00 sleep_detected {"gap_s": 350, "runs_extended": 2}
- 2026-10-05T08:33:57+00:00 run_finished {"run": "T0081-critic-20261005T011854-03d5", "status": "completed", "cost": 2.525694599999999, "subtype": "success", "report": "structured_output"}
- 2026-10-05T08:34:01+00:00 run_started {"run": "T0082-critic-20261005T013401-faca", "task": "T0082", "role": "critic", "session": "6d0c0b20-b9e5-4e50-902d-4735f68ec38e"}
