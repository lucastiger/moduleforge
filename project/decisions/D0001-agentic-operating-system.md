# D0001 — Build ModuleForge with a thin, git-native orchestrator over Claude Code
Date: 2026-09-28 · Status: accepted · Decider: founder

## Context
One founder must run research and engineering at the pace of a small team, with scientific rigor:
decisions must follow evidence, and agents must not be able to declare their own success.

## Decision
A ~2.5k-line Python orchestrator (`mfos`, in `tools/mfos`) drives headless Claude Code sessions
(`claude -p --agent <role>`) in git worktrees. Six ephemeral agent roles (planner, builder,
scientist, critic, scout, scribe). All durable state is files in this repository. Objectives are
frozen hypotheses with pre-registered, machine-evaluated acceptance criteria. Experiments run without
any LLM in clean checkouts with sealed seeds. A deterministic evaluator issues PASS / FAIL /
INCONCLUSIVE / INVALID. Blinded critics review high-stakes work. The founder approves objectives,
criteria, experiment registrations, protected changes, spend, and anything external.

## Alternatives considered
- Claude Code agent teams as the backbone — rejected: experimental, disabled by default, no worktree
  isolation, coordination state outside git.
- Claude Agent SDK as the core — deferred: its docs point products built on it to API-key auth; the
  CLI gives the same loop with the same configuration. Revisit for mid-run control or product features.
- LangGraph / CrewAI / AutoGen / OpenHands — rejected: re-implement the agent loop Claude Code already
  provides and move state out of git.
- Temporal / Prefect / Airflow — rejected for now: the task graph is small; revisit with multi-node compute.
- /goal and dynamic workflows as the control loop — rejected: model-judged completion and
  session-scoped resumability. Used opportunistically (scout uses /deep-research).

## Consequences
Every decision is traceable to files and commits; the loop can be killed and resumed at any time.
We own ~2.5k lines of orchestration code and must keep it boring. Full reasoning: docs/ARCHITECTURE.md.
