# ModuleForge status
_generated 2026-09-30T18:52:45+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0013** [experiment_registration] register E001 (pre-registration)
- **I0014** [protected_change] T0023: merge needs founder approval

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $34.93/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 20, failed: 2, needs_founder: 1, running: 2, todo: 6

- T0023 `needs_founder` builder/implement: L1 fast PEEC moduleforge.physics.peec (trace cells, skin-corrected R, Grover bond wires, image planes) + single-core timing benchmark (attempt 1)
- T0041 `running` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)
- T0043 `running` builder/implement: DRC: loop-closing necks, unknown die.switch, diameter-aware wire-start margin (T0040 review) (attempt 1)

## Recent events
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
- 2026-09-30T18:51:06+00:00 run_finished {"run": "T0045-critic-20260930T113013-ea65", "status": "completed", "cost": 1.5063718000000001, "subtype": "success", "report": "structured_output"}
- 2026-09-30T18:51:06+00:00 run_started {"run": "T0041-scientist-20260930T115106-58f7", "task": "T0041", "role": "scientist", "session": "d6adbdbf-37a0-4df4-86d5-9ceaaca5d8fa"}
- 2026-09-30T18:52:42+00:00 run_finished {"run": "T0044-critic-20260930T113013-7ce6", "status": "completed", "cost": 2.1548241999999993, "subtype": "success", "report": "structured_output"}
- 2026-09-30T18:52:45+00:00 inbox_opened {"id": "I0014", "kind": "protected_change", "subject": "T0023: merge needs founder approval"}
- 2026-09-30T18:52:45+00:00 run_started {"run": "T0043-builder-20260930T115245-bba7", "task": "T0043", "role": "builder", "session": "02133b8f-da4d-4047-b677-daba8f9a7386"}
