# ModuleForge status
_generated 2026-10-11T04:32:24+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0044** [experiment_registration] register E002 (pre-registration)
- **I0045** [experiment_registration] register E003 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $263.73/$285 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 20, done: 68, failed: 3, running: 1, todo: 5

- T0077 `running` none/experiment: Run E002: L1 vs L2 loop-inductance ranking on sealed generated layouts (attempt 1)

## Recent events
- 2026-10-11T03:19:50+00:00 run_finished {"run": "T0096-critic-20261010T201916-7d97", "status": "error", "cost": 0.313172, "subtype": "success", "report": "missing"}
- 2026-10-11T03:19:50+00:00 capacity_backoff {"task": "T0096", "minutes": 30}
- 2026-10-11T03:19:50+00:00 run_finished {"run": "T0097-critic-20261010T201916-a407", "status": "error", "cost": 0.408222, "subtype": "success", "report": "missing"}
- 2026-10-11T03:19:50+00:00 capacity_backoff {"task": "T0097", "minutes": 30}
- 2026-10-11T03:50:21+00:00 run_started {"run": "T0096-critic-20261010T205021-8ea1", "task": "T0096", "role": "critic", "session": "25419070-3d4a-4184-b8e8-60804b76dd2f"}
- 2026-10-11T03:50:21+00:00 run_started {"run": "T0097-critic-20261010T205021-ddf9", "task": "T0097", "role": "critic", "session": "1a526a3e-658d-48a3-b198-ce1d354ff202"}
- 2026-10-11T03:55:47+00:00 run_finished {"run": "T0097-critic-20261010T205021-ddf9", "status": "completed", "cost": 2.103506, "subtype": "success", "report": "structured_output"}
- 2026-10-11T03:56:54+00:00 run_finished {"run": "T0096-critic-20261010T205021-8ea1", "status": "completed", "cost": 2.253956, "subtype": "success", "report": "structured_output"}
- 2026-10-11T04:02:33+00:00 inbox_opened {"id": "I0043", "kind": "protected_change", "subject": "T0076: merge needs founder approval"}
- 2026-10-11T04:03:06+00:00 sleep_detected {"gap_s": 373, "runs_extended": 0}
- 2026-10-11T04:32:20+00:00 inbox_resolved {"id": "I0043", "status": "approved", "note": "Approved per the founder's standing instruction (merge of reviewed work; registration is a separate founder decis
- 2026-10-11T04:32:23+00:00 merged {"task": "T0076"}
- 2026-10-11T04:32:23+00:00 inbox_opened {"id": "I0044", "kind": "experiment_registration", "subject": "register E002 (pre-registration)"}
- 2026-10-11T04:32:23+00:00 inbox_opened {"id": "I0045", "kind": "experiment_registration", "subject": "register E003 (pre-registration)"}
- 2026-10-11T04:32:24+00:00 experiment_task_started {"task": "T0077", "experiment": "E002"}
