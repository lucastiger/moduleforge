# ModuleForge status
_generated 2026-10-04T04:59:57+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0024** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $110.82/$165 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 39, failed: 2, review: 1, running: 2, todo: 7

- T0063 `review` scientist/design_experiment: E001 final: solver error budget 1e-5 (rule power under solver noise), review minors (T0061/T0062) (attempt 1)
- T0064 `running` critic/review: Review T0063 (physics) (attempt 1)
- T0065 `running` critic/review: Review T0063 (numerics) (attempt 1)

## Recent events
- 2026-10-04T03:16:47+00:00 inbox_resolved {"id": "I0022", "status": "rejected", "note": "Superseded by I0024 (registration request for E001 as redesigned by T0060)."}
- 2026-10-04T03:33:00+00:00 inbox_opened {"id": "I0025", "kind": "budget_increase", "subject": "[O001] raise the objective budget by $60 (founder decision)"}
- 2026-10-04T03:33:11+00:00 inbox_resolved {"id": "I0025", "status": "approved", "note": "usd=60"}
- 2026-10-04T03:34:22+00:00 task_added {"task": "T0063"}
- 2026-10-04T03:34:22+00:00 run_started {"run": "T0063-scientist-20261003T203422-9eb4", "task": "T0063", "role": "scientist", "session": "2284cda1-8dc7-4d45-912b-c134db94a89b"}
- 2026-10-04T03:41:02+00:00 run_finished {"run": "T0063-scientist-20261003T203422-9eb4", "status": "error", "cost": 2.317722, "subtype": "success", "report": "missing"}
- 2026-10-04T03:41:02+00:00 capacity_backoff {"task": "T0063", "minutes": 30}
- 2026-10-04T04:11:25+00:00 run_started {"run": "T0063-scientist-20261003T211125-c722", "task": "T0063", "role": "scientist", "session": "a1b0c58e-ee01-4794-941e-4dff215c5a40"}
- 2026-10-04T04:11:57+00:00 run_finished {"run": "T0063-scientist-20261003T211125-c722", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-04T04:11:57+00:00 capacity_backoff {"task": "T0063", "minutes": 30}
- 2026-10-04T04:42:21+00:00 run_started {"run": "T0063-scientist-20261003T214221-33c6", "task": "T0063", "role": "scientist", "session": "e07ea640-4d02-4520-b964-a138924756ca"}
- 2026-10-04T04:58:45+00:00 run_finished {"run": "T0063-scientist-20261003T214221-33c6", "status": "completed", "cost": 3.5479912000000002, "subtype": "success", "report": "structured_output"}
- 2026-10-04T04:59:56+00:00 verified {"task": "T0063"}
- 2026-10-04T04:59:57+00:00 run_started {"run": "T0064-critic-20261003T215957-9049", "task": "T0064", "role": "critic", "session": "62d6a5ba-c371-486c-a7c5-2638d78565ab"}
- 2026-10-04T04:59:57+00:00 run_started {"run": "T0065-critic-20261003T215957-b549", "task": "T0065", "role": "critic", "session": "7416b4f0-751c-4777-9c65-3f2b86596be0"}
