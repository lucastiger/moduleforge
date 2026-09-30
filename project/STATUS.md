# ModuleForge status
_generated 2026-09-30T19:09:10+00:00 from repository state — do not edit_

## Founder inbox (1 open)
- **I0013** [experiment_registration] register E001 (pre-registration)

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $38.07/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 14, done: 22, failed: 2, merge: 1, review: 1, running: 2, todo: 7

- T0037 `review` builder/implement: Fingerprint: hash LayerStack.kind, pin every hashed input with a test, fix the docstring (T0035 review) (attempt 3)
- T0041 `running` scientist/design_experiment: Fix E001's design before registration: wire model error bounds, convergence estimate, L2 contract, coverage (T0029/T0030 reviews) (attempt 1)
- T0043 `merge` builder/implement: DRC: loop-closing necks, unknown die.switch, diameter-aware wire-start margin (T0040 review) (attempt 1)
- T0048 `running` critic/review: Review T0037 (general) (attempt 1)

## Recent events
- 2026-09-30T18:52:45+00:00 run_started {"run": "T0043-builder-20260930T115245-bba7", "task": "T0043", "role": "builder", "session": "02133b8f-da4d-4047-b677-daba8f9a7386"}
- 2026-09-30T18:54:21+00:00 run_finished {"run": "T0043-builder-20260930T115245-bba7", "status": "completed", "cost": 0.19824659999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T18:54:25+00:00 inbox_resolved {"id": "I0014", "status": "approved", "note": "Approved per the founder's standing instruction: DoD verified; both critics accept as the literal L1 hypothesis. 
- 2026-09-30T18:54:28+00:00 run_started {"run": "T0037-builder-20260930T115428-1e26", "task": "T0037", "role": "builder", "session": "0ec40a27-5ff9-478e-9990-7abfd78d2eab"}
- 2026-09-30T18:54:34+00:00 verified {"task": "T0043"}
- 2026-09-30T18:54:36+00:00 merged {"task": "T0023"}
- 2026-09-30T18:55:56+00:00 task_added {"task": "T0047"}
- 2026-09-30T19:01:48+00:00 run_finished {"run": "T0037-builder-20260930T115428-1e26", "status": "completed", "cost": 1.5444503999999997, "subtype": "success", "report": "structured_output"}
- 2026-09-30T19:02:05+00:00 verified {"task": "T0037"}
- 2026-09-30T19:02:06+00:00 run_started {"run": "T0046-critic-20260930T120206-8ae8", "task": "T0046", "role": "critic", "session": "dc5e464e-7533-4c3c-8046-600f0189ea93"}
- 2026-09-30T19:08:00+00:00 run_finished {"run": "T0046-critic-20260930T120206-8ae8", "status": "completed", "cost": 1.3927440000000004, "subtype": "success", "report": "structured_output"}
- 2026-09-30T19:08:03+00:00 inbox_opened {"id": "I0015", "kind": "protected_change", "subject": "T0043: merge needs founder approval"}
- 2026-09-30T19:08:04+00:00 run_started {"run": "T0048-critic-20260930T120804-4a4b", "task": "T0048", "role": "critic", "session": "56acd006-4f11-452a-8d8b-a747f1ae2dfb"}
- 2026-09-30T19:08:45+00:00 inbox_resolved {"id": "I0015", "status": "approved", "note": "Approved per the founder's standing instruction: DoD verified; T0046 accept_with_caveats with minor findings only
- 2026-09-30T19:08:45+00:00 task_added {"task": "T0049"}
