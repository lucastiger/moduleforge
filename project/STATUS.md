# ModuleForge status
_generated 2026-10-01T04:01:57+00:00 from repository state — do not edit_

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
- 2026-10-01T02:29:31+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T03:00:04+00:00 run_started {"run": "T0052-critic-20260930T200004-c32b", "task": "T0052", "role": "critic", "session": "9d34ec6c-4f78-4461-9f09-7639c3554eb3"}
- 2026-10-01T03:00:04+00:00 run_started {"run": "T0047-builder-20260930T200004-b169", "task": "T0047", "role": "builder", "session": "49003365-e992-410e-8a85-bcac1609cea0"}
- 2026-10-01T03:00:36+00:00 run_finished {"run": "T0052-critic-20260930T200004-c32b", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T03:00:36+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T03:00:36+00:00 run_finished {"run": "T0047-builder-20260930T200004-b169", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T03:00:36+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T03:30:59+00:00 run_started {"run": "T0052-critic-20260930T203059-8902", "task": "T0052", "role": "critic", "session": "b39fd533-fec2-4657-9071-00d33534d9e2"}
- 2026-10-01T03:30:59+00:00 run_started {"run": "T0047-builder-20260930T203059-ed27", "task": "T0047", "role": "builder", "session": "f51291f3-f1f3-4fce-9924-180fefd6bd5b"}
- 2026-10-01T03:31:31+00:00 run_finished {"run": "T0052-critic-20260930T203059-8902", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T03:31:31+00:00 capacity_backoff {"task": "T0052", "minutes": 30}
- 2026-10-01T03:31:31+00:00 run_finished {"run": "T0047-builder-20260930T203059-ed27", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-01T03:31:31+00:00 capacity_backoff {"task": "T0047", "minutes": 30}
- 2026-10-01T04:01:57+00:00 run_started {"run": "T0052-critic-20260930T210157-7bcb", "task": "T0052", "role": "critic", "session": "2bb7d3bf-ea77-4920-9177-652559baa3af"}
- 2026-10-01T04:01:57+00:00 run_started {"run": "T0047-builder-20260930T210157-32b3", "task": "T0047", "role": "builder", "session": "4e8990f7-ca39-4363-a256-272bc1e7e95a"}
