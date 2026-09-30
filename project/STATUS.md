# ModuleForge status
_generated 2026-09-30T15:09:16+00:00 from repository state — do not edit_

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
- 2026-09-30T14:02:05+00:00 verified {"task": "T0023"}
- 2026-09-30T14:02:06+00:00 run_started {"run": "T0044-critic-20260930T070206-510a", "task": "T0044", "role": "critic", "session": "32c75498-b4f8-4056-95eb-dbdef38445fb"}
- 2026-09-30T14:04:19+00:00 run_finished {"run": "T0041-scientist-20260930T064222-9471", "status": "error", "cost": 4.2748292, "subtype": "success", "report": "missing"}
- 2026-09-30T14:04:20+00:00 capacity_backoff {"task": "T0041", "minutes": 30}
- 2026-09-30T14:04:20+00:00 run_finished {"run": "T0044-critic-20260930T070206-510a", "status": "error", "cost": 0.6792794000000001, "subtype": "success", "report": "missing"}
- 2026-09-30T14:04:20+00:00 capacity_backoff {"task": "T0044", "minutes": 30}
- 2026-09-30T14:34:37+00:00 run_started {"run": "T0043-builder-20260930T073437-9b41", "task": "T0043", "role": "builder", "session": "e635ccc6-f1d7-40fc-ac3a-1c50eb888559"}
- 2026-09-30T14:34:39+00:00 run_started {"run": "T0044-critic-20260930T073439-7ca3", "task": "T0044", "role": "critic", "session": "7833b620-12b1-4a15-8d5b-fc7861dc6691"}
- 2026-09-30T14:35:12+00:00 run_finished {"run": "T0043-builder-20260930T073437-9b41", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T14:35:12+00:00 capacity_backoff {"task": "T0043", "minutes": 30}
- 2026-09-30T14:35:12+00:00 run_finished {"run": "T0044-critic-20260930T073439-7ca3", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T14:35:12+00:00 capacity_backoff {"task": "T0044", "minutes": 30}
- 2026-09-30T15:09:14+00:00 sleep_detected {"gap_s": 632, "runs_extended": 0}
- 2026-09-30T15:09:16+00:00 run_started {"run": "T0044-critic-20260930T080916-1ddd", "task": "T0044", "role": "critic", "session": "8021deee-b88c-4f72-a6d7-d18f94a8dd18"}
- 2026-09-30T15:09:16+00:00 run_started {"run": "T0045-critic-20260930T080916-d621", "task": "T0045", "role": "critic", "session": "c48a74d0-7d04-426c-95f7-a452ec021f41"}
