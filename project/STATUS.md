# ModuleForge status
_generated 2026-09-30T18:55:43+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $35.13/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 21, failed: 2, review: 1, running: 2, todo: 6

- T0037 `running` builder/implement: Fingerprint: hash LayerStack.kind, pin every hashed input with a test, fix the docstring (T0035 review) (attempt 3)
- T0041 `running` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)
- T0043 `review` builder/implement: DRC: loop-closing necks, unknown die.switch, diameter-aware wire-start margin (T0040 review) (attempt 1)

## Recent events
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
- 2026-09-30T18:54:21+00:00 run_finished {"run": "T0043-builder-20260930T115245-bba7", "status": "completed", "cost": 0.19824659999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T18:54:25+00:00 inbox_resolved {"id": "I0014", "status": "approved", "note": "Approved per the founder's standing instruction: DoD verified; both critics accept as the literal L1 hypothesis. 
- 2026-09-30T18:54:28+00:00 run_started {"run": "T0037-builder-20260930T115428-1e26", "task": "T0037", "role": "builder", "session": "0ec40a27-5ff9-478e-9990-7abfd78d2eab"}
- 2026-09-30T18:54:34+00:00 verified {"task": "T0043"}
- 2026-09-30T18:54:36+00:00 merged {"task": "T0023"}
