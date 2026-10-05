# ModuleForge status
_generated 2026-10-05T04:00:17+00:00 from repository state — do not edit_

## Founder inbox (0 open)
- nothing needs you

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $157.23/$245 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 19, done: 46, failed: 3, review: 1, running: 2, todo: 9

- T0070 `review` builder/implement: L2 core in src: exact-kernel round wires, FFT plane, bounded GMRES; E001's C1 and B2 converge under the frozen rule (attempt 1)
- T0079 `running` critic/review: Review T0070 (physics) (attempt 1)
- T0080 `running` critic/review: Review T0070 (numerics) (attempt 1)

## Recent events
- 2026-10-05T01:09:00+00:00 run_finished {"run": "T0070-builder-20261004T180827-e764", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T01:09:00+00:00 capacity_backoff {"task": "T0070", "minutes": 30}
- 2026-10-05T01:39:03+00:00 run_started {"run": "T0070-builder-20261004T183903-9e70", "task": "T0070", "role": "builder", "session": "70d954f6-e016-4962-b36d-327f16a04779"}
- 2026-10-05T01:39:36+00:00 run_finished {"run": "T0070-builder-20261004T183903-9e70", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T01:39:36+00:00 capacity_backoff {"task": "T0070", "minutes": 30}
- 2026-10-05T02:09:46+00:00 run_started {"run": "T0070-builder-20261004T190946-e3b0", "task": "T0070", "role": "builder", "session": "95d744f2-d4d0-4942-85a3-594e81e20189"}
- 2026-10-05T02:10:19+00:00 run_finished {"run": "T0070-builder-20261004T190946-e3b0", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-10-05T02:10:19+00:00 capacity_backoff {"task": "T0070", "minutes": 30}
- 2026-10-05T02:20:45+00:00 inbox_resolved {"id": "I0033", "status": "approved", "note": ""}
- 2026-10-05T02:40:25+00:00 run_started {"run": "T0070-builder-20261004T194025-abdf", "task": "T0070", "role": "builder", "session": "86dd30fc-e625-4937-908e-8326f5d987f8"}
- 2026-10-05T03:53:00+00:00 run_finished {"run": "T0070-builder-20261004T194025-abdf", "status": "completed", "cost": 5.770738400000001, "subtype": "success", "report": "structured_output"}
- 2026-10-05T03:59:41+00:00 verified {"task": "T0070"}
- 2026-10-05T03:59:43+00:00 run_started {"run": "T0079-critic-20261004T205943-a6fb", "task": "T0079", "role": "critic", "session": "bfca28f5-9ffe-49b4-884e-76cea6fec2e8"}
- 2026-10-05T03:59:43+00:00 run_started {"run": "T0080-critic-20261004T205943-6047", "task": "T0080", "role": "critic", "session": "a2d2a7b2-1b9a-4a78-8519-0434dd26ed9c"}
- 2026-10-05T04:00:15+00:00 sleep_detected {"gap_s": 437, "runs_extended": 2}
