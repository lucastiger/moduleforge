# ModuleForge status
_generated 2026-09-30T01:13:59+00:00 from repository state — do not edit_

## Founder inbox (2 open)
- **I0005** [external_action] [O001] [O001] Pin FastHenry and rebuild it with --force before the L2 adapter (n3) starts; record D0002 at E001 registration
- **I0008** [decision] T0020: review could not be completed

## Objectives
| id | status | verdict | evals | spent | title |
|---|---|---|---|---|---|
| O000 | passed | PASS | 1/2 | $0.50/$20 | Framework canary — the loop carries a known-answer hypothesis from plan to verdict |
| O001 | active | - | 0/3 | $12.13/$120 | L1 PEEC ranks half-bridge layouts faithfully enough to drive layout search |

## Tasks
cancelled: 12, done: 7, failed: 4, needs_founder: 1, running: 2, todo: 8

- T0020 `needs_founder` scientist/design_experiment: Select the L2 reference (license + capability audit) and pre-register E001 reference validation (attempt 1)
- T0033 `running` builder/implement: Layout fingerprint covers every to_conductors() input; die shorts span trace top to die top (attempt 1)
- T0034 `running` builder/implement: DRC hardening from the T0028 review: connectivity, keep-outs, diameter-aware pitch, width boundary, full rule coverage (attempt 1)

## Recent events
- 2026-09-30T00:46:40+00:00 run_finished {"run": "T0029-critic-20260929T174607-5ff4", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T00:46:40+00:00 task_failed_attempt {"task": "T0029", "signal": "agent_error", "action": "repair"}
- 2026-09-30T00:46:40+00:00 run_finished {"run": "T0030-critic-20260929T174607-ea79", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T00:46:40+00:00 task_failed_attempt {"task": "T0030", "signal": "agent_error", "action": "diagnose"}
- 2026-09-30T00:46:40+00:00 investigation_spawned {"task": "T0031", "about": "T0030", "cls": "implementation"}
- 2026-09-30T00:46:40+00:00 run_started {"run": "T0029-critic-20260929T174640-8d79", "task": "T0029", "role": "critic", "session": "b07ce2d2-ee5d-48c9-a638-d45ae102eb9a"}
- 2026-09-30T00:47:12+00:00 run_finished {"run": "T0029-critic-20260929T174640-8d79", "status": "error", "cost": 0.0, "subtype": "success", "report": "missing"}
- 2026-09-30T00:47:12+00:00 task_failed_attempt {"task": "T0029", "signal": "agent_error", "action": "diagnose"}
- 2026-09-30T00:47:12+00:00 investigation_spawned {"task": "T0032", "about": "T0029", "cls": "implementation"}
- 2026-09-30T00:47:12+00:00 inbox_opened {"id": "I0008", "kind": "decision", "subject": "T0020: review could not be completed"}
- 2026-09-30T01:12:20+00:00 loop_started {"pid": 15938}
- 2026-09-30T01:13:24+00:00 task_added {"task": "T0033"}
- 2026-09-30T01:13:24+00:00 task_added {"task": "T0034"}
- 2026-09-30T01:13:50+00:00 run_started {"run": "T0033-builder-20260929T181350-f8eb", "task": "T0033", "role": "builder", "session": "b828768c-b160-4cac-937a-402cc5d20782"}
- 2026-09-30T01:13:50+00:00 run_started {"run": "T0034-builder-20260929T181350-3a67", "task": "T0034", "role": "builder", "session": "a9206f69-5b68-4ca0-9fb4-2a079707271f"}
