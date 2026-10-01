# ModuleForge status
_generated 2026-10-01T06:08:15+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $58.82/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 26, failed: 2, review: 1, running: 2, todo: 7

- T0041 `review` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)
- T0047 `running` builder/implement: L1 fidelity: converged bond-wire segmentation, consistent bar internal inductance, mesh within 3 % at <= 50 ms (T0044/T0045 reviews) (attempt 2)
- T0052 `running` critic/review: Review T0041 (numerics) (attempt 1)

## Recent events
- 2026-10-01T04:33:26+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T05:03:29+00:00 run_started {"run": "T0052-critic-20260930T220329-6865", "task": "T0052", "role": "critic", "session": "aac52bab-3bc3-473f-8fcb-7ad97fd51b50"}
- 2026-10-01T05:03:29+00:00 run_started {"run": "T0047-builder-20260930T220329-53f7", "task": "T0047", "role": "builder", "session": "4caf4455-4fa2-444c-9e62-ede86b7d8ad8"}
- 2026-10-01T05:04:02+00:00 run_finished {"run": "T0052-critic-20260930T220329-6865", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:04:02+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T05:04:02+00:00 run_finished {"run": "T0047-builder-20260930T220329-53f7", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:04:02+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T05:34:28+00:00 run_started {"run": "T0052-critic-20260930T223428-3847", "task": "T0052", "role": "critic", "session": "e01ef9d5-37fb-49a9-9ac2-e6ff4ed91cf9"}
- 2026-10-01T05:34:28+00:00 run_started {"run": "T0047-builder-20260930T223428-968d", "task": "T0047", "role": "builder", "session": "77ed9dcb-9006-4114-ab43-1e5aa915e3f0"}
- 2026-10-01T05:38:14+00:00 run_finished {"run": "T0047-builder-20260930T223428-968d", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:38:14+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T05:38:14+00:00 run_finished {"run": "T0052-critic-20260930T223428-3847", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T05:38:14+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T06:08:15+00:00 run_started {"run": "T0052-critic-20260930T230815-e597", "task": "T0052", "role": "critic", "session": "edc25cec-b3c2-4bde-b907-d0efc6e24eb4"}
- 2026-10-01T06:08:15+00:00 run_started {"run": "T0047-builder-20260930T230815-8744", "task": "T0047", "role": "builder", "session": "4b2bebb3-085d-47f3-981f-6d9768884c41"}
