# ModuleForge status
_generated 2026-10-06T00:18:12+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $194.08/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 52, failed: 3, review: 1, running: 2, todo: 7

- T0071 `running` builder/implement: Complete moduleforge.solvers.l2 for E001: exact bars, two-port Z, ties; frozen E001 smoke passes within 40 min (attempt 2)
- T0074 `review` builder/implement: L2 layout path: Layout -> exact-kernel loop_inductance with a precorrected-FFT wire-to-grid operator (l2_layout.py) (attempt 2)
- T0084 `running` critic/review: Review T0074 (numerics) (attempt 1)

## Recent events
- 2026-10-05T22:58:24+00:00 run_started {"run": "T0071-builder-20261005T155824-c8d8", "task": "T0071", "role": "builder", "session": "129d2ab2-807a-4845-a84d-8756f0d2ba9c"}
- 2026-10-05T22:59:03+00:00 run_finished {"run": "T0084-critic-20261005T155822-976e", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T22:59:03+00:00 capacity_backoff {"task": "T0084", "minutes": 30}
- 2026-10-05T22:59:03+00:00 run_finished {"run": "T0071-builder-20261005T155824-c8d8", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T22:59:03+00:00 capacity_backoff {"task": "T0071", "minutes": 30}
- 2026-10-05T23:35:18+00:00 run_started {"run": "T0084-critic-20261005T163518-ceb3", "task": "T0084", "role": "critic", "session": "a5bb5488-e24e-4bfe-97a9-88d5345a9a87"}
- 2026-10-05T23:35:18+00:00 run_started {"run": "T0071-builder-20261005T163518-9409", "task": "T0071", "role": "builder", "session": "dcf461d8-c280-4199-a1e1-fd2ae8b5c2c5"}
- 2026-10-05T23:35:56+00:00 sleep_detected {"gap_s": 396, "runs_extended": 2}
- 2026-10-05T23:36:00+00:00 run_finished {"run": "T0071-builder-20261005T163518-9409", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T23:36:00+00:00 capacity_backoff {"task": "T0071", "minutes": 30}
- 2026-10-05T23:36:00+00:00 run_finished {"run": "T0084-critic-20261005T163518-ceb3", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T23:36:00+00:00 capacity_backoff {"task": "T0084", "minutes": 30}
- 2026-10-06T00:17:55+00:00 sleep_detected {"gap_s": 891, "runs_extended": 0}
- 2026-10-06T00:18:12+00:00 run_started {"run": "T0084-critic-20261005T171812-a3a5", "task": "T0084", "role": "critic", "session": "65238525-22aa-4c2a-a45d-9823d1f845e1"}
- 2026-10-06T00:18:12+00:00 run_started {"run": "T0071-builder-20261005T171812-eb98", "task": "T0071", "role": "builder", "session": "7a05fc62-17c3-4b2f-9f73-164d1ed22d05"}
