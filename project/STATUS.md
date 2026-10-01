# ModuleForge status
_generated 2026-10-01T07:02:29+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $69.63/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 28, failed: 2, review: 1, running: 1, todo: 8

- T0047 `review` builder/implement: L1 fidelity: converged bond-wire segmentation, consistent bar internal inductance, mesh within 3 % at <= 50 ms (T0044/T0045 reviews) (attempt 2)
- T0053 `running` critic/review: Review T0047 (physics) (attempt 1)

## Recent events
- 2026-10-01T05:34:28+00:00 run_started {"run": "T0052-critic-20260930T223428-3847", "task": "T0052", "role": "critic", "session": "e01ef9d5-37fb-49a9-9ac2-e6ff4ed91cf9"}
- 2026-10-01T05:34:28+00:00 run_started {"run": "T0047-builder-20260930T223428-968d", "task": "T0047", "role": "builder", "session": "77ed9dcb-9006-4114-ab43-1e5aa915e3f0"}
- 2026-10-01T05:38:14+00:00 run_finished {"run": "T0047-builder-20260930T223428-968d", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:38:14+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T05:38:14+00:00 run_finished {"run": "T0052-critic-20260930T223428-3847", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:38:14+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T06:08:15+00:00 run_started {"run": "T0052-critic-20260930T230815-e597", "task": "T0052", "role": "critic", "session": "edc25cec-b3c2-4bde-b907-d0efc6e24eb4"}
- 2026-10-01T06:08:15+00:00 run_started {"run": "T0047-builder-20260930T230815-8744", "task": "T0047", "role": "builder", "session": "4b2bebb3-085d-47f3-981f-6d9768884c41"}
- 2026-10-01T06:14:05+00:00 run_finished {"run": "T0052-critic-20260930T230815-e597", "status": "completed", "cost": 1.8439848000000003, "subtype": "success", "report": "structured_output"}
- 2026-10-01T06:14:05+00:00 task_failed_attempt {"task": "T0041", "signal": "review_rejected", "action": "repair"}
- 2026-10-01T06:46:19+00:00 run_finished {"run": "T0047-builder-20260930T230815-8744", "status": "completed", "cost": 6.812736800000001, "subtype": "success", "report": "structured_output"}
- 2026-10-01T06:46:35+00:00 verified {"task": "T0047"}
- 2026-10-01T06:46:36+00:00 run_started {"run": "T0053-critic-20260930T234636-3418", "task": "T0053", "role": "critic", "session": "d9605861-9559-437c-8050-1e3866f64a8b"}
- 2026-10-01T06:46:36+00:00 run_started {"run": "T0054-critic-20260930T234636-f3db", "task": "T0054", "role": "critic", "session": "ec2774f7-86d8-4a41-8d0d-dac62571613c"}
- 2026-10-01T06:58:05+00:00 run_finished {"run": "T0054-critic-20260930T234636-f3db", "status": "completed", "cost": 2.1523711999999997, "subtype": "success", "report": "structured_output"}
