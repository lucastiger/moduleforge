# ModuleForge status
_generated 2026-09-30T14:34:39+00:00 from repository state — do not edit_

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
- T0043 `running` builder/implement: DRC: loop-closing necks, unknown die.switch, diameter-aware wire-start margin (T0040 review) (attempt 1)
- T0044 `running` critic/review: Review T0023 (physics) (attempt 1)

## Recent events
- 2026-09-30T13:43:46+00:00 run_started {"run": "T0042-critic-20260930T064346-d42f", "task": "T0042", "role": "critic", "session": "e5cc6f49-1f17-42ef-9307-c742ed57d8ba"}
- 2026-09-30T13:44:30+00:00 loop_started {"pid": 1039}
- 2026-09-30T13:46:04+00:00 task_added {"task": "T0043"}
- 2026-09-30T13:48:18+00:00 run_finished {"run": "T0042-critic-20260930T064346-d42f", "status": "completed", "cost": 1.4038266, "subtype": "success", "report": "structured_output"}
- 2026-09-30T13:48:18+00:00 run_started {"run": "T0023-builder-20260930T064818-74f0", "task": "T0023", "role": "builder", "session": "61215666-539f-4a65-8519-e06cc03f77a1"}
- 2026-09-30T13:48:19+00:00 task_failed_attempt {"task": "T0037", "signal": "review_rejected", "action": "repair"}
- 2026-09-30T14:02:00+00:00 run_finished {"run": "T0023-builder-20260930T064818-74f0", "status": "completed", "cost": 2.3203747999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T14:02:05+00:00 verified {"task": "T0023"}
- 2026-09-30T14:02:06+00:00 run_started {"run": "T0044-critic-20260930T070206-510a", "task": "T0044", "role": "critic", "session": "32c75498-b4f8-4056-95eb-dbdef38445fb"}
- 2026-09-30T14:04:19+00:00 run_finished {"run": "T0041-scientist-20260930T064222-9471", "status": "error", "cost": 4.2748292, "subtype": "success", "report": "missing"}
- 2026-09-30T14:04:20+00:00 capacity_backoff {"task": "T0041", "minutes": 30}
- 2026-09-30T14:04:20+00:00 run_finished {"run": "T0044-critic-20260930T070206-510a", "status": "error", "cost": 0.6792794000000001, "subtype": "success", "report": "missing"}
- 2026-09-30T14:04:20+00:00 capacity_backoff {"task": "T0044", "minutes": 30}
- 2026-09-30T14:34:37+00:00 run_started {"run": "T0043-builder-20260930T073437-9b41", "task": "T0043", "role": "builder", "session": "e635ccc6-f1d7-40fc-ac3a-1c50eb888559"}
- 2026-09-30T14:34:39+00:00 run_started {"run": "T0044-critic-20260930T073439-7ca3", "task": "T0044", "role": "critic", "session": "7833b620-12b1-4a15-8d5b-fc7861dc6691"}
