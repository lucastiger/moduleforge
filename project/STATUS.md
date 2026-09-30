# ModuleForge status
_generated 2026-09-30T18:48:22+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $31.27/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 18, failed: 2, review: 1, running: 2, todo: 8

- T0023 `review` builder/implement: L1 fast PEEC moduleforge.physics.peec (trace cells, skin-corrected R, Grover bond wires, image planes) + single-core timing benchmark (attempt 1)
- T0044 `running` critic/review: Review T0023 (physics) (attempt 1)
- T0045 `running` critic/review: Review T0023 (numerics) (attempt 1)

## Recent events
- 2026-09-30T16:33:38+00:00 capacity_backoff {"task": "T0045", "minutes": 30}
- 2026-09-30T17:57:49+00:00 sleep_detected {"gap_s": 5052, "runs_extended": 0}
- 2026-09-30T17:57:51+00:00 run_started {"run": "T0044-critic-20260930T105751-2895", "task": "T0044", "role": "critic", "session": "6dd34840-d3aa-45fd-95d0-ee3b390ff315"}
- 2026-09-30T17:57:51+00:00 run_started {"run": "T0045-critic-20260930T105751-2e2f", "task": "T0045", "role": "critic", "session": "4af63d9f-bd6d-4848-9f31-03b1103481d6"}
- 2026-09-30T17:58:25+00:00 run_finished {"run": "T0045-critic-20260930T105751-2e2f", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T17:58:25+00:00 capacity_backoff {"task": "T0045", "minutes": 30}
- 2026-09-30T17:58:25+00:00 run_finished {"run": "T0044-critic-20260930T105751-2895", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T17:58:25+00:00 capacity_backoff {"task": "T0044", "minutes": 30}
- 2026-09-30T18:13:58+00:00 sleep_detected {"gap_s": 934, "runs_extended": 0}
- 2026-09-30T18:24:35+00:00 sleep_detected {"gap_s": 636, "runs_extended": 0}
- 2026-09-30T18:30:11+00:00 sleep_detected {"gap_s": 337, "runs_extended": 0}
- 2026-09-30T18:30:13+00:00 run_started {"run": "T0044-critic-20260930T113013-7ce6", "task": "T0044", "role": "critic", "session": "f1d0284f-bfcf-4c09-ba4b-124ee9f5c964"}
- 2026-09-30T18:30:13+00:00 run_started {"run": "T0045-critic-20260930T113013-ea65", "task": "T0045", "role": "critic", "session": "01689580-b643-4eee-83a5-b827baf8d7da"}
- 2026-09-30T18:44:17+00:00 sleep_detected {"gap_s": 529, "runs_extended": 2}
- 2026-09-30T18:48:20+00:00 loop_started {"pid": 14564}
