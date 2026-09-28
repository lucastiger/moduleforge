---
name: mf-planning
description: How to decompose an mfos objective into tasks - task types, sizing, definition-of-done patterns, risk levels, budgets, anti-patterns. Use when producing a plan.
user-invocable: false
---

# Planning reference

## Task types and owners
| type | agent | produces | typical DoD |
|---|---|---|---|
| implement | builder | code + unit tests | `uv run pytest tests/unit/test_x.py -q` |
| docs | builder | docs | `test -f docs/x.md` |
| research | scout | cited notes | `test -f project/memory/literature/x.md` |
| design_experiment | scientist | draft spec + runner | `uv run mfos exp check E002`, `uv run python experiments/runners/e002.py --smoke` |
| investigate | scientist | diagnosis notes + report | `test -f research/diagnoses/T00xx.md` |
| experiment | none (orchestrator) | registered result | (none — the runner and evaluator decide) |

## Sizing
One coherent deliverable; 20–120 agent-minutes; ≤ 15 files changed. Split by interface, not by layer.

## Risk (drives review depth and merge policy)
low: docs, refactors with tests, tooling · medium: new modules, generators, adapters ·
high: physics models, reference solvers, experiment runners that feed acceptance criteria ·
critical: anything the evaluator reads or that a public claim will rest on.

## Budgets (USD per task, before escalation)
research 1–3 · implement 2–6 · design_experiment 3–6 · investigate 3–5.

## Dependencies and `touches`
Depend on what you consume, not on what merely came earlier. `touches` lists the globs a task will
edit, so two tasks with overlapping `touches` never run concurrently.

## Anti-patterns (reject your own plan if it contains these)
Tasks without machine-checkable DoD · "investigate and fix" in one task · tasks that restate the
objective · speculative infrastructure no criterion needs · more than one open task per file ·
re-running an evaluation instead of designing a discriminating experiment.
