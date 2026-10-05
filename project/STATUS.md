# ModuleForge status
_generated 2026-10-05T20:27:10+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $184.68/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 51, failed: 3, review: 1, running: 2, todo: 8

- T0071 `running` builder/implement: Complete moduleforge.solvers.l2 for E001: exact bars, two-port Z, ties; frozen E001 smoke passes within 40 min (attempt 2)
- T0074 `review` builder/implement: L2 layout path: Layout -> exact-kernel loop_inductance with a precorrected-FFT wire-to-grid operator (l2_layout.py) (attempt 2)
- T0083 `running` critic/review: Review T0074 (physics) (attempt 1)

## Recent events
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
- 2026-10-05T20:17:13+00:00 run_finished {"run": "T0074-builder-20261005T123730-3239", "status": "completed", "cost": 5.284989600000001, "subtype": "success", "report": "structured_output"}
- 2026-10-05T20:26:33+00:00 verified {"task": "T0074"}
- 2026-10-05T20:26:35+00:00 run_started {"run": "T0083-critic-20261005T132635-ca0c", "task": "T0083", "role": "critic", "session": "030320d9-b27c-47c8-b2a6-52d850f2a119"}
- 2026-10-05T20:27:08+00:00 sleep_detected {"gap_s": 598, "runs_extended": 2}
