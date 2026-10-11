# ModuleForge status
_generated 2026-10-11T03:50:21+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $259.37/$285 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 20, done: 65, failed: 3, review: 1, running: 2, todo: 6

- T0076 `review` scientist/design_experiment: Design E002 (L1 vs L2 ranking, sealed seed) and E003 (L1 single-core timing) + runners, sized from the measured L2 layout cost (attempt 2)
- T0096 `running` critic/review: Review T0076 (physics) (attempt 1)
- T0097 `running` critic/review: Review T0076 (numerics) (attempt 1)

## Recent events
- 2026-10-10T05:21:47+00:00 sleep_detected {"gap_s": 3645, "runs_extended": 0}
- 2026-10-10T05:36:59+00:00 sleep_detected {"gap_s": 913, "runs_extended": 0}
- 2026-10-11T01:06:20+00:00 loop_started {"pid": 93011}
- 2026-10-11T01:06:55+00:00 run_started {"run": "T0076-scientist-20261010T180655-e404", "task": "T0076", "role": "scientist", "session": "5383acf8-410c-4621-830f-0cddd48006de"}
- 2026-10-11T02:35:43+00:00 run_finished {"run": "T0076-scientist-20261010T180655-e404", "status": "completed", "cost": 6.279168, "subtype": "success", "report": "structured_output"}
- 2026-10-11T03:19:14+00:00 verified {"task": "T0076"}
- 2026-10-11T03:19:16+00:00 run_started {"run": "T0096-critic-20261010T201916-7d97", "task": "T0096", "role": "critic", "session": "1e0e7e26-ec83-45b1-90d6-fcbe906b7f89"}
- 2026-10-11T03:19:16+00:00 run_started {"run": "T0097-critic-20261010T201916-a407", "task": "T0097", "role": "critic", "session": "98339234-90b8-4533-add6-23c18605c0ef"}
- 2026-10-11T03:19:49+00:00 sleep_detected {"gap_s": 2647, "runs_extended": 2}
- 2026-10-11T03:19:50+00:00 run_finished {"run": "T0096-critic-20261010T201916-7d97", "status": "error", "cost": 0.313172, "subtype": "success", "report": "missing"}
- 2026-10-11T03:19:50+00:00 capacity_backoff {"task": "T0096", "minutes": 30}
- 2026-10-11T03:19:50+00:00 run_finished {"run": "T0097-critic-20261010T201916-a407", "status": "error", "cost": 0.408222, "subtype": "success", "report": "missing"}
- 2026-10-11T03:19:50+00:00 capacity_backoff {"task": "T0097", "minutes": 30}
- 2026-10-11T03:50:21+00:00 run_started {"run": "T0096-critic-20261010T205021-8ea1", "task": "T0096", "role": "critic", "session": "25419070-3d4a-4184-b8e8-60804b76dd2f"}
- 2026-10-11T03:50:21+00:00 run_started {"run": "T0097-critic-20261010T205021-ddf9", "task": "T0097", "role": "critic", "session": "1a526a3e-658d-48a3-b198-ce1d354ff202"}
