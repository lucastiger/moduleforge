# ModuleForge status
_generated 2026-10-05T22:24:58+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $191.88/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 52, failed: 3, review: 1, running: 2, todo: 7

- T0071 `running` builder/implement: Complete moduleforge.solvers.l2 for E001: exact bars, two-port Z, ties; frozen E001 smoke passes within 40 min (attempt 2)
- T0074 `review` builder/implement: L2 layout path: Layout -> exact-kernel loop_inductance with a precorrected-FFT wire-to-grid operator (l2_layout.py) (attempt 2)
- T0084 `running` critic/review: Review T0074 (numerics) (attempt 1)

## Recent events
- 2026-10-05T20:40:26+00:00 sleep_detected {"gap_s": 657, "runs_extended": 2}
- 2026-10-05T20:42:56+00:00 run_finished {"run": "T0083-critic-20261005T132635-ca0c", "status": "error", "cost": 0.6756326, "subtype": "success", "report": "missing"}
- 2026-10-05T20:42:58+00:00 capacity_backoff {"task": "T0083", "minutes": 30}
- 2026-10-05T20:45:56+00:00 run_finished {"run": "T0071-builder-20261005T123730-4cd6", "status": "error", "cost": 4.4823088, "subtype": "success", "report": "missing"}
- 2026-10-05T20:45:56+00:00 capacity_backoff {"task": "T0071", "minutes": 30}
- 2026-10-05T21:16:30+00:00 run_started {"run": "T0083-critic-20261005T141630-b236", "task": "T0083", "role": "critic", "session": "d03ea4a5-0b25-48f1-9417-534ffe47643b"}
- 2026-10-05T21:16:32+00:00 run_started {"run": "T0084-critic-20261005T141632-3572", "task": "T0084", "role": "critic", "session": "059b7c94-3791-49ba-9741-690235760e69"}
- 2026-10-05T21:26:19+00:00 run_finished {"run": "T0084-critic-20261005T141632-3572", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T21:26:21+00:00 capacity_backoff {"task": "T0084", "minutes": 30}
- 2026-10-05T21:26:21+00:00 run_finished {"run": "T0083-critic-20261005T141630-b236", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T21:26:21+00:00 capacity_backoff {"task": "T0083", "minutes": 30}
- 2026-10-05T21:56:41+00:00 run_started {"run": "T0083-critic-20261005T145641-7b2f", "task": "T0083", "role": "critic", "session": "403bdbf3-cfdb-486c-aae0-e4f98815c7fd"}
- 2026-10-05T21:56:45+00:00 run_started {"run": "T0084-critic-20261005T145645-f522", "task": "T0084", "role": "critic", "session": "71eaf20c-a2a3-42fa-9c5c-a82fa0fbfc27"}
- 2026-10-05T22:24:44+00:00 run_finished {"run": "T0083-critic-20261005T145641-7b2f", "status": "completed", "cost": 2.0481102, "subtype": "success", "report": "structured_output"}
- 2026-10-05T22:24:58+00:00 run_started {"run": "T0071-builder-20261005T152458-2677", "task": "T0071", "role": "builder", "session": "c69be6f3-293a-4647-a0e8-34ba160afd79"}
