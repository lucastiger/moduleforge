# ModuleForge status
_generated 2026-09-30T00:37:37+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0005** [external_action] [O001] [O001] Pin FastHenry and rebuild it with --force before the L2 adapter (n3) starts; record D0002 at E001 registration
- **I0007** [protected_change] T0021: merge needs founder approval

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $5.90/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 12, done: 6, failed: 2, needs_founder: 1, running: 1, todo: 6

- T0020 `running` scientist/design_experiment: Select the L2 reference (license + capability audit) and pre-register E001 reference validation (attempt 1)
- T0021 `needs_founder` builder/implement: Layout IR, layer stack, DRC and DRC-valid half-bridge generator (3 families, 2–6 dies/switch) (attempt 1)

## Recent events
- 2026-09-29T22:51:55+00:00 inbox_resolved {"id": "I0003", "status": "answered", "note": "(b): use the provisioned binary (MF_FASTHENRY_BIN, then PATH); no auto-build. Pin scripts/provision_compute.sh to
- 2026-09-29T22:51:55+00:00 inbox_resolved {"id": "I0004", "status": "rejected", "note": "Founder chose option (b) on I0003. Re-issue the plan in project/tasks/T0011-T0018 unchanged (read their YAML) exc
- 2026-09-29T22:52:07+00:00 run_started {"run": "T0019-planner-20260929T155207-42aa", "task": "T0019", "role": "planner", "session": "1860d385-998a-4048-8c98-677e1ba36e5a"}
- 2026-09-29T22:56:48+00:00 run_finished {"run": "T0019-planner-20260929T155207-42aa", "status": "completed", "cost": 1.0976278000000002, "subtype": "success", "report": "structured_output"}
- 2026-09-29T22:56:48+00:00 inbox_opened {"id": "I0005", "kind": "external_action", "subject": "[O001] [O001] Pin FastHenry and rebuild it with --force before the L2 adapter (n3) starts; record D0002 a
- 2026-09-29T22:56:48+00:00 inbox_opened {"id": "I0006", "kind": "plan_approval", "subject": "[O001] approve initial plan (8 tasks)"}
- 2026-09-29T22:56:48+00:00 plan_applied {"objective": "O001", "created": ["T0020", "T0021", "T0022", "T0023", "T0024", "T0025", "T0026", "T0027"], "dropped": 0}
- 2026-09-30T00:18:54+00:00 inbox_resolved {"id": "I0006", "status": "approved", "note": "Approved: re-issued plan with I0003 option (b) applied to T0022; verified field-by-field against T0011-T0018."}
- 2026-09-30T00:23:20+00:00 run_started {"run": "T0020-scientist-20260929T172320-c0d9", "task": "T0020", "role": "scientist", "session": "db25861a-1be4-4f3b-9fac-62ace7fbbe9a"}
- 2026-09-30T00:23:20+00:00 run_started {"run": "T0021-builder-20260929T172320-d25b", "task": "T0021", "role": "builder", "session": "222fefeb-c158-4bfd-a133-6f39c9e0babc"}
- 2026-09-30T00:31:39+00:00 run_finished {"run": "T0021-builder-20260929T172320-d25b", "status": "completed", "cost": 1.1800618, "subtype": "success", "report": "structured_output"}
- 2026-09-30T00:31:42+00:00 verified {"task": "T0021"}
- 2026-09-30T00:31:42+00:00 run_started {"run": "T0028-critic-20260929T173142-bcfd", "task": "T0028", "role": "critic", "session": "7223def8-71e0-48ec-becb-80cf67cf2e9e"}
- 2026-09-30T00:37:30+00:00 run_finished {"run": "T0028-critic-20260929T173142-bcfd", "status": "completed", "cost": 1.6899538000000003, "subtype": "success", "report": "structured_output"}
- 2026-09-30T00:37:37+00:00 inbox_opened {"id": "I0007", "kind": "protected_change", "subject": "T0021: merge needs founder approval"}
