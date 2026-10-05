# ModuleForge status
_generated 2026-10-05T19:37:41+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $179.39/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 51, failed: 3, running: 2, todo: 7

- T0071 `running` builder/implement: Complete moduleforge.solvers.l2 for E001: exact bars, two-port Z, ties; frozen E001 smoke passes within 40 min (attempt 2)
- T0074 `running` builder/implement: L2 layout path: Layout -> exact-kernel loop_inductance with a precorrected-FFT wire-to-grid operator (l2_layout.py) (attempt 2)

## Recent events
- 2026-10-05T09:08:21+00:00 tick_error {"error": "PermissionError: [Errno 1] Operation not permitted", "consecutive": 1}
- 2026-10-05T09:08:53+00:00 run_interrupted {"run": "T0071-builder-20261005T003215-ff71"}
- 2026-10-05T09:08:53+00:00 run_started {"run": "T0071-builder-20261005T020853-f29c", "task": "T0071", "role": "builder", "session": "1b44fcc0-0839-493c-ba85-c54ea72e5423"}
- 2026-10-05T09:30:52+00:00 run_finished {"run": "T0071-builder-20261005T020853-f29c", "status": "completed", "cost": 4.8149814, "subtype": "success", "report": "structured_output"}
- 2026-10-05T09:30:53+00:00 task_failed_attempt {"task": "T0071", "signal": "dod_failed", "action": "repair"}
- 2026-10-05T14:24:51+00:00 sleep_detected {"gap_s": 301, "runs_extended": 0}
- 2026-10-05T16:27:00+00:00 sleep_detected {"gap_s": 5203, "runs_extended": 0}
- 2026-10-05T16:36:48+00:00 sleep_detected {"gap_s": 587, "runs_extended": 0}
- 2026-10-05T18:01:43+00:00 sleep_detected {"gap_s": 564, "runs_extended": 0}
- 2026-10-05T18:51:28+00:00 sleep_detected {"gap_s": 2729, "runs_extended": 0}
- 2026-10-05T19:29:36+00:00 sleep_detected {"gap_s": 2042, "runs_extended": 0}
- 2026-10-05T19:34:54+00:00 loop_started {"pid": 32377}
- 2026-10-05T19:37:06+00:00 loop_started {"pid": 34498}
- 2026-10-05T19:37:30+00:00 run_started {"run": "T0071-builder-20261005T123730-4cd6", "task": "T0071", "role": "builder", "session": "a00b6f9c-1ceb-4745-9d83-535c5065b31f"}
- 2026-10-05T19:37:30+00:00 run_started {"run": "T0074-builder-20261005T123730-3239", "task": "T0074", "role": "builder", "session": "0cd8580c-0623-4209-ba51-55d0c542ab19"}
