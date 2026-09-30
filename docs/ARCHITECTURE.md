# Autonomous ModuleForge Engineering System

**Version 0.1 · 2026-09-28 · status: implemented and tested; not yet run against the live Claude Code CLI**

This document is the design of record for the AI engineering organization that builds ModuleForge.
Everything it describes exists in this repository: a ~3,000-line orchestrator (`tools/mfos`), six agent
definitions, three hooks, fourteen skills, an operating policy, two objectives, CI, and a 25-test suite
whose end-to-end tests drive the real orchestrator through complete objective lifecycles (including a
failure → diagnosis → replan → recovery cycle) using a stand-in for the `claude` CLI. The one thing not
yet exercised is the real CLI; §20 step 6 does that with a canary objective for a few dollars.

**Deployment note (2026-09-28):** the persistent 16–32 vCPU VM originally specified in §3.6 and §20 was
audited against measurements and replaced: the system runs on a MacBook (control plane and default
compute) with ephemeral cloud VMs for heavy experiments. See `docs/INFRASTRUCTURE.md`. Where this
document says "forge box", read "the machine running the orchestrator" — your Mac by default.

Claude Code facts in this document were verified against the official documentation
(code.claude.com/docs, fetched 2026-09-27). Features move fast; §24 lists the dependencies to re-check.

---

## 1. Executive architecture

**One sentence.** A small deterministic orchestrator runs a restartable state machine over files in the
Git repository; it calls Claude Code headlessly for six narrowly scoped, ephemeral agent roles, runs
experiments without any LLM, and lets only deterministic code decide whether work counts — while you
approve the few things that change goals, standards of evidence, money, or the outside world.

**The central rule: agents propose, code disposes.**

| Agents produce | Deterministic code decides |
|---|---|
| planner: a task graph (JSON) | orchestrator validates, caps, and materializes it |
| builder: code and tests | hooks + definition of done + gates + scope check decide if it verifies |
| scientist: experiment designs, diagnoses | founder registers designs; the runner executes them |
| critic: findings and a verdict | the verdict only *blocks*; it can never *pass* anything by itself |
| — | the evaluator issues PASS / FAIL / INCONCLUSIVE / INVALID from result files |

```
                  ┌──────────────────────────── Founder ────────────────────────────┐
                  │ objectives · approvals · strategy · customers · hard physics     │
                  │ /status /inbox /objective /investigate /thesis-review  (mfos CLI)│
                  └──────────────▲──────────────────────────────┬───────────────────┘
                    inbox items  │                              │ approve / reject / answer
┌────────────────────────────────┴──────────────────────────────▼───────────────────┐
│  mfos orchestrator — deterministic tick loop on the forge VM (systemd)             │
│  scheduler · task packets · run records · verify (scope, DoD, gates) · reviews ·   │
│  merge · experiment runner · evaluator · failure router · budgets · STATUS.md      │
└───┬──────────────────┬───────────────────┬────────────────────┬────────────────────┘
    │ claude -p        │ claude -p         │ subprocess (no LLM)│ git (+ gh in Phase 4)
    │ --agent planner  │ --agent builder…  │                    │
    ▼                  ▼                   ▼                    ▼
 planner           builder · scientist   experiment runners   GitHub: main, CI gate,
 (read-only,       scout · scribe        clean detached       audit tripwire,
  main checkout)   (own git worktree)    checkout of main,    CODEOWNERS
 critic                                   sealed seeds,
 (sanitized review checkout)              ExperimentRun → result.json
    ▲ every Claude session: guard (PreToolUse) · stop_gate (Stop) · session_start hooks
┌──────────────────────────────────────────────────────────────────────────────────┐
│ The repository is the database: project/ (charter, objectives, tasks, inbox,      │
│ claims, reviews, events.jsonl, STATUS.md) · experiments/ (specs, results) ·       │
│ .mfos/policy.toml · .claude/ (agents, skills, hooks, settings) · CLAUDE.md        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Why not the obvious "manager agent" design.** A long-lived Claude session acting as engineering
manager (whether a main session delegating to subagents or an agent-team lead) holds the plan in a
context window that ends, compacts, and anchors on its own earlier reasoning; it also cannot be trusted
to judge whether the plan worked. Here the manager is split in two: a *stateless planning function*
(the planner agent, invoked fresh with a complete packet whenever the plan needs revisiting) and a
*deterministic controller* (the orchestrator) that owns state, sequencing, and every verdict.

---

## 2. Design principles

1. **Agents propose, code disposes.** No agent statement is evidence. Verdicts come from commands that
   exit 0, from scope checks, and from the evaluator reading result files.
2. **The repository is the database.** All durable state is plain files in Git: reviewable in diffs,
   restorable by checkout, readable by agents with ordinary tools. No second source of truth.
3. **Hypotheses are executable.** An objective is a frozen, hashed hypothesis with pre-registered pass
   and kill criteria on metrics with confidence intervals, evaluated by code into one of four verdicts.
4. **Pre-registration and sealed data.** Experiment designs are frozen before they run; evaluation
   samples use seeds no agent has seen; evaluations are a counted, finite resource.
5. **Separation of powers.** Planner ≠ implementer ≠ experiment designer ≠ judge. Acceptance tests,
   registered specs, evaluator, policy, and agent instructions are protected from the agents they govern.
6. **Fresh context by default.** Every run starts clean from a packet. Persistent knowledge lives in
   curated, cited files — never in unreviewed agent memory.
7. **One agent unless independence or parallelism pays.** Multi-agent structures are used only for
   adversarial independence (critics) or genuinely parallel work.
8. **Restartable and idempotent.** Every run has a pre-minted session id and a run record written before
   launch; the loop can be killed at any instant and resumes correctly.
9. **Few, batched, non-blocking interruptions.** You are asked only about goals, evidence standards,
   money, protected rules, and the outside world. Requests queue in an inbox and block only the branch of
   work that needs them.
10. **Cost-bounded by construction.** Caps per run, task, objective, and day; model routing by role;
    review depth by risk; no LLM in experiments or evaluation.
11. **Boring technology.** Files, Git, subprocesses, pydantic. Hooks use only the Python standard library.
12. **Incremental adoption.** Each layer (state, evidence, packets, execution, replanning) works alone,
    so you can migrate one step at a time (§22).

---

## 3. Recommended technology stack

### 3.1 Choices

| Layer | Choice | Why | Rejected alternatives |
|---|---|---|---|
| Agent runtime | **Claude Code CLI, headless** (`claude -p --agent <role> --output-format json --json-schema … --max-budget-usd … --session-id … --permission-prompts none`) | Same agent loop, tools, hooks, skills and `.claude/` config you use interactively; process isolation per run; schema-validated structured output; per-run budget cap; resumable sessions; works with your Claude login or an API key | Agent SDK as core (see 3.3); raw Messages API tool loop (re-implements Claude Code) |
| Orchestration | **`mfos`**, custom Python in `tools/mfos` (~3k lines incl. CLI; 25 tests) | The task graph is small (tens of tasks per week); what matters is exact control of verdicts, state and recovery. A boring loop over files is fully debuggable | LangGraph, CrewAI, AutoGen, OpenHands; Temporal, Prefect, Airflow (3.4) |
| State | **YAML/JSON files + append-only `events.jsonl`, in Git** | Human-readable, diffable, reviewable in PRs, restorable, zero ops | SQLite/Postgres as source of truth (second truth, invisible in review, merge semantics); GitHub Issues as truth (not versioned with code, API-bound) |
| Evidence queries | **DuckDB, optional, read-only** over `experiments/results/*/*/result.json` | Queries JSON in place with `read_json_auto` — no ingestion, no sync, nothing to corrupt | A results DB that must be kept in sync |
| Large artifacts | **Content-addressed store** (`.mfos/artifacts/sha256/…`), synced to object storage with `rclone`; results reference hashes | Deduplicated, immutable, verifiable, cheap | Git LFS (quota, churn); DVC (extra concepts until datasets are large) |
| Experiment execution | Local subprocess on the forge VM, clean checkout, sealed seed | Deterministic, no LLM, provenance captured automatically | Agents running experiments (can tune, misreport, or cherry-pick) |
| CI | GitHub Actions, deterministic only (`ci.yml` gate, `audit.yml` tripwire) | Independent second opinion on `main`; alerts reach your phone | Agents in CI initially (cost, secrets, duplication of the local loop) |
| Deployment | **MacBook as control plane and default compute** (launchd) + **ephemeral cloud VMs per heavy experiment** (`scripts/burst.sh`) | Agents need ~1 GiB RAM each and no local CPU; MVP simulations measured laptop-sized; sweeps rent cores by the hour (`docs/INFRASTRUCTURE.md`) | A persistent 16–32 vCPU VM (idle most of the time; €276–533/month) |
| Language/tooling | Python 3.12, uv, pydantic 2, numpy, pytest, ruff (rules pinned) | Matches the scientific stack; uv gives fast, locked, per-worktree environments | — |

### 3.2 Agent Teams — **not used**
Agent teams coordinate several Claude Code sessions through a lead with a shared task list and messaging.
They are experimental and disabled by default, teammates are not isolated in git worktrees (the docs tell
you to partition files by hand), and coordination state lives in the team's task list rather than in the
repository. Every property this project needs most — durable state, deterministic verdicts, worktree
isolation, resumability after a crash, per-run budgets — is weaker there than in the orchestrator.
**Where they could earn a place later:** an interactive "war room" you join yourself, e.g. a physicist,
a numericist, and a devil's advocate debugging a surprising result together, where live cross-talk is the
point and durability is not. Revisit when they leave experimental status.

### 3.3 Claude Agent SDK — **later-phase addition, not the core**
The SDK gives the same agent loop as a Python/TypeScript library (typed results, `max_budget_usd`,
`output_format`, in-process hooks, `can_use_tool` callbacks, interrupts, session stores). It is the
right tool eventually, but not now: (a) the CLI already exposes everything the orchestrator needs as
flags; (b) the SDK's documentation directs products built on it to API-key authentication, whereas the
CLI runs under whatever authentication you choose, and your `.claude/` configuration applies identically
to your interactive sessions; (c) one subprocess per run is the simplest crash isolation there is.
**Adopt it when you need:** mid-run steering or interrupts, streaming progress into a UI,
programmatic permission decisions, transcripts mirrored to shared storage for multi-host resume — and
for the customer-facing product itself (e.g. an assistant that sets up derivative-layout jobs), which
should be built on the SDK or API with API keys. The switch is local: only `mfos/agents.py` changes.

### 3.4 External frameworks — **none**
LangGraph, CrewAI, AutoGen, and OpenHands each bring their own agent loop, tool layer, and state store.
Using them would mean either bypassing Claude Code (losing its tools, permissions, hooks, skills,
subagents) or wrapping it (two agent loops, two sets of abstractions to debug), and would move state out
of Git. Workflow engines (Temporal, Prefect, Airflow) solve durable execution for large, fan-out-heavy
graphs; ours is small, and a file-backed state machine with run records already gives restartability.
**Revisit** Temporal or Ray when experiments span several machines or run hundreds of jobs a day; the
experiment-runner interface (`mfos exp run`) is where that plugs in.

### 3.5 Other Claude Code features considered

| Feature | Decision |
|---|---|
| Subagents (`.claude/agents/*.md`) | **Core.** Each role is a subagent definition, launched as the *main* session with `--agent`, so the same file works headlessly and interactively (`claude --agent scientist`). |
| Skills | **Core.** Shared procedures preloaded per role; founder commands as user-only skills. |
| Hooks | **Core.** In-session enforcement (§13). |
| Dynamic workflows | **Opportunistic.** Scripts orchestrating many subagents with cross-checking; resumable only within the same session and without mid-run input, so not a control loop. The scout may use the bundled `/deep-research`; you may use ad-hoc workflows for sweeping audits. |
| `/goal` | **Interactive convenience only.** Completion is judged by a small model reading the transcript; it does not run commands. Scientific gates here are commands and the evaluator. |
| Auto mode | **Used** for builder and scientist runs, with deny rules, the guard hook, and `--permission-prompts none` so nothing waits for a human. Fallback: `acceptEdits`. |
| Routines, cloud / self-hosted environments, Remote Control | **Later** (§23). Remote Control is useful now for checking on sessions from your phone. |
| Auto memory, agent `memory:` | **Disabled** (`autoMemoryEnabled: false`); see §16. |

### 3.6 Deployment options compared

| Option | Verdict |
|---|---|
| **Laptop (MacBook Air M5, 16 GB)** | **Chosen for Phases 0–3.** Runs the loop (launchd), two agents, L0/L1 and small L2; work pauses while the lid is closed and resumes correctly. |
| Persistent large VM (16–32 vCPU, 64 GB) | Rejected after measurement: the agents need no local compute and the MVP simulations fit the laptop (`docs/INFRASTRUCTURE.md` §2). |
| Persistent small VM (2 vCPU, 4 GB, ~€20/month) | Deferred: add it for the orchestrator only when lid-closed autonomy or customer isolation requires it. |
| GitHub Actions as orchestrator | No: job time limits, no persistent state between jobs, awkward for multi-hour simulations. Kept for deterministic CI. |
| Cloud routines / self-hosted environments | Promising for scheduled or event-triggered sessions; young, and experiments need your own compute. Revisit in Phase 5. |
| Hybrid | The target end state: VM orchestrates; heavy L2 batches go to cloud batch or Ray workers through the same runner contract. |

---

## 4. Agent architecture

### 4.1 Autonomy hierarchy

| Level | Who | Authority | Cannot |
|---|---|---|---|
| **L0 Deterministic** | orchestrator, hooks, gates, experiment runners, evaluator, CI | Decides truth: verification, verdicts, merges within policy | Invent goals or change standards |
| **L1 Workers** | builder, scout, scribe | Produce artifacts inside a write scope | Touch protected paths, integrate, run evaluations |
| **L2 Specialists** | scientist, critic | Design experiments, diagnose failures, attack claims | Register experiments, change criteria, pass anything |
| **L3 Planner** | planner | Create, re-scope, cancel tasks within one frozen objective and its budget | Change hypothesis, criteria, scope, budget, or objectives |
| **L4 Founder** | you | Objectives, acceptance criteria, experiment registration, thesis, money, protected rules, anything external | — |

There is deliberately **no "research director" agent**. Changing what the company is trying to prove is
L4. The system *proposes* such changes (planner `founder_requests`, scientist `affects_acceptance_criteria`,
`/thesis-review` memos) and you decide.

### 4.2 Roster

| | planner | builder | scientist | critic | scout | scribe |
|---|---|---|---|---|---|---|
| **Purpose** | Turn a frozen objective + evidence into the smallest decisive task graph | Implement one task: code, tests, small docs | Design pre-registered experiments; derive; diagnose failures | Blinded attempt to refute a claim or diff | External facts: literature, tools, licenses, competitors, market | Faithful compression: digests, summaries, memory curation |
| **Model** | opus, effort high | sonnet (opus on attempt ≥ 2) | opus, effort high | opus, effort high | sonnet | haiku |
| **Tools** | Read, Grep, Glob | Read, Edit, Write, Grep, Glob, Bash, TodoWrite, Skill | Read, Edit, Write, Grep, Glob, Bash, WebSearch, WebFetch, Skill | Read, Grep, Glob, Bash, WebSearch, WebFetch, Skill | Read, Grep, Glob, Write, Edit, WebSearch, WebFetch, Skill, Workflow | Read, Grep, Glob, Write, Edit |
| **Writes** | nothing (returns JSON) | `src/`, `tests/unit/`, `tests/regression/`, `docs/`, `benchmarks/`, deps | `research/`, `experiments/drafts/`, `experiments/runners/`, `tests/acceptance_drafts/`, `project/memory/` | `/tmp` only | `project/memory/literature/`, `research/notes/` | `project/memory/`, `docs/reports/` |
| **Runs in** | main checkout (read-only) | own worktree | own worktree | sanitized review checkout | own worktree | own worktree |
| **Invoked** | objective activation; after a verdict or a diagnosis merges; after a task exhausts attempts; after your answers | `implement`/`docs` tasks | `design_experiment`, `investigate` tasks; auto-spawned on failures | auto-created by risk ladder, for every experiment design, and for PASS/FAIL evaluations | `research` tasks | `docs` tasks you or the planner create |
| **Creates tasks** | yes (validated) | no | no (recommends) | no | no | no |
| **Modifies code** | no | yes | research code only | no | no | no |
| **Runs experiments** | no | smoke only | smoke only | re-runs checks in its checkout | no | no |
| **Merges** | no | no | no | no | no | no |
| **Modifies plans** | within objective | no | no | no | no | no |
| **Needs approval** | initial plan (and every plan below autonomy level 3) | merges of high/critical risk, protected paths | experiment registration | — | anything external is forbidden outright | — |
| **Output schema** | `PlanOutput` | `BuildReport` | `ScienceReport` | `Review` | `ResearchReport` | `ScribeReport` |

Every "never" rule is in the prompts (Appendix A) *and* enforced mechanically where possible: write
scopes and protected paths by the guard hook and again by the orchestrator's scope check; integration
commands by deny rules and the guard; unfinished work by the Stop hook; blinding by physically deleting
files from the critic's checkout, which is a one-commit snapshot with no link to the repository's history.

### 4.3 Roles considered and folded in
Engineering manager and research director → planner + you. Physics and numerical-methods specialists →
the scientist, plus critic *lenses* and skills. Experiment and benchmark agents → deterministic runners
(an LLM in the measurement path is a liability). QA/test agent → gates + the critic's "test the tests".
Geometry/CAD agent → builder + `mf-conventions`. Data analyst → scientist. Documentation agent and
project historian → generated reports + scribe. Customer-research and diligence agents → scout +
`/thesis-review` + you (customer conversations are yours). Specialization lives in skills, lenses and
packets, which cost nothing when unused; separate agents would multiply prompts to maintain.

### 4.4 Persistence and context isolation

* **All agents are ephemeral.** Each run is a new session with the role's system prompt, `CLAUDE.md`,
  preloaded skills, and one task packet. No agent has a long-lived identity.
* **Continuity lives in files**: task histories (compact summaries of prior attempts), evaluations,
  diagnoses, decisions, the literature index, `lessons.md`.
* **Resume vs. restart.** An *interrupted* run (crash, reboot) resumes its own session once
  (`--resume <session-id>`), because its context is still valid. A *failed* attempt restarts fresh with a
  short failure summary: resuming a session that talked itself into a wrong approach invites anchoring.
* **The critic is blinded.** It works in a snapshot of the commit under review from which `project/tasks`,
  `inbox`, `reviews`, `events.jsonl`, objective `state.yaml`, diagnoses, run records and packets have been
  deleted, committed once into a fresh repository so that `git show`/`git log` cannot recover them;
  it receives a neutral claim ("this change correctly implements X" / "this evidence supports H within
  scope S") and the material. It sees the *artifact* — the diff or the evidence — but not the author,
  the rationale, earlier attempts, or anyone's opinion. Acceptance with zero independent checks is
  automatically downgraded to `cannot_assess`.
* **Should the adversary know the hypothesis?** For evidence reviews, yes — the claim is what it must
  attack; what it must not see is the reasoning that produced the evidence. For experiment-design reviews
  it sees the design and the objective, so it can ask "would this design catch a false hypothesis?".
* **Competing hypotheses stay independent.** Diagnoses must list ≥ 2 explanations with discriminating
  tests. When stakes are high the planner can launch parallel scientist investigations with identical
  inputs; each runs in its own worktree, and diagnoses are among the blinded paths, so they cannot read
  each other. Adjudication is by discriminating experiment, not by debate.
* **The planner** reads evaluations and diagnoses, never raw transcripts.

---

## 5. Project state architecture

Everything durable is a file in Git. Runtime scratch (run records, packets, locks, artifacts) lives in
gitignored `.mfos/` subdirectories and can be lost without losing the project.

| Entity | Location · format | Written by | Read by | Mutability |
|---|---|---|---|---|
| Thesis, assumptions, kill criteria | `project/charter.md` | you | planner, `/thesis-review` | protected |
| Objective definition | `project/objectives/O###/objective.yaml` | you (`/objective` helps draft) | everyone | **frozen** by hash at approval |
| Objective state | `…/O###/state.yaml` | orchestrator | orchestrator, reports | mutable |
| Evaluations | `…/O###/evaluations/EV-O###-NN.json` | evaluator | planner, critic, reports | immutable |
| Diagnoses | `…/O###/diagnoses/T####.json` + `research/diagnoses/T####.md` | orchestrator / scientist | planner | immutable |
| Evidence package | `…/O###/EVIDENCE.md` | `mfos report` | you, investors, customers | generated |
| Tasks | `project/tasks/T####.yaml` (incl. attempt history) | orchestrator (from planner JSON) | orchestrator, packets | mutable |
| Founder inbox | `project/inbox/I####.yaml` | orchestrator; resolved by `mfos approve/reject/answer` | you | append-and-resolve |
| Claims | `project/claims/C###.yaml` | orchestrator on PASS | everyone | status changes only |
| Reviews | `project/reviews/T####.json` | orchestrator (critic output) | planner, reports | immutable |
| Decisions (ADRs) | `project/decisions/D####-slug.md` | you | everyone | protected |
| Curated knowledge | `project/memory/` (lessons, literature index, notes) | scientist, scout, scribe (reviewed by merge) | everyone | curated |
| Customer notes | `project/customers/` | you | `/thesis-review` | confidential |
| Event log | `project/events.jsonl` | orchestrator | reports, audits | append-only |
| Status | `project/STATUS.md` | orchestrator every tick | you, SessionStart hook | generated |
| Experiment specs | `experiments/drafts/E###.yaml` → `experiments/specs/E###.yaml` | scientist → registration | runner, evaluator | specs frozen by hash |
| Experiment results | `experiments/results/E###/<run_id>/result.json` (+ `run.json`) | `ExperimentRun` in the runner | evaluator, DuckDB | immutable |
| Artifacts | `.mfos/artifacts/sha256/…` → object storage | runners via `run.artifact()` | anyone with the hash | immutable, content-addressed |
| Run records | `.mfos/runs/<run_key>.json`, `.out` | agent runner | orchestrator (resume) | local only |
| Policy | `.mfos/policy.toml` | you | orchestrator, hooks | protected |

**Where the other things live.** Assumptions: the charter's assumptions table (each mapped to the
objective that tests it). Risks: each objective's `failure_modes` (description, detection, response).
Open questions: `question` inbox items, or research notes. Technical debt: tasks under a standing
low-risk objective `O900 Engineering health` (create it when the first debt appears). Negative results:
evaluations with FAIL verdicts and refuted claims — never deleted, always listed in `EVIDENCE.md`.

**What deliberately does not exist:** a database of record, GitHub Issues as a task tracker, PR
descriptions as documentation of record, agent memory directories.

Schemas are pydantic models in `tools/mfos/mfos/models.py` with `extra="forbid"`: a misspelled key in any
file is an error, not silently ignored. (During development this caught a YAML flow-mapping whose commas
had split one description into four bogus keys.)

---

## 6. Objective and task model

### 6.1 Anatomy of an executable objective

| Your requirement | Field in `objective.yaml` | Who acts on it |
|---|---|---|
| Hypothesis | `hypothesis.{statement, null_hypothesis, why_it_matters, decision_if_pass, decision_if_fail}`, `scope_in`, `scope_out` | planner, critic, you |
| Implementation work | *derived*: the planner decomposes toward the criteria | planner → tasks |
| Evidence | `evidence_plan`, `acceptance.required_experiments` | scientist designs, you register |
| Acceptance criteria | `acceptance.pass_all[]`, `acceptance.fail_any[]` — metric, comparator, threshold, `uncertainty.use: ci|point` | evaluator |
| Failure modes | `failure_modes[]` — description, detection, response | planner, scientist, critic |
| Automatic response | failure taxonomy (§8.6) + verdict routing | orchestrator |
| Human escalation | `max_evaluations`, `budget`, planning/business failure classes, protected changes | orchestrator → inbox |

### 6.2 Four verdicts, decided conservatively
For each criterion the evaluator reads `E###.metric` from the admissible result and compares the
*conservative* end of its 95% interval: a pass criterion `ρ ≥ 0.85` holds only if the **lower** bound is
≥ 0.85; a kill criterion `MAPE > 0.20` fires only if the **lower** bound exceeds 0.20. A criterion that
asks for an interval on a metric reported without one is *missing*, never silently passed.

* **INVALID** — evidence inadmissible: spec hash mismatch, dirty tree, commit not on main, a declared
  sanity check absent or failed, required experiment missing. Nothing about the hypothesis is concluded.
* **FAIL** — any kill criterion definitely met.
* **PASS** — every pass criterion definitely met, no kill criterion met.
* **INCONCLUSIVE** — anything else (typically intervals too wide).

### 6.3 Freezing and the forking-paths budget
`mfos objective approve` computes `criteria_hash` over hypothesis, scope, evidence plan and acceptance.
The evaluator and `mfos doctor` refuse to proceed if the file no longer matches — tampering is caught
even if a hook were bypassed (tested). Changing criteria is legitimate only as your explicit act: edit,
then re-approve; the evaluation count carries over. `max_evaluations` (default 3) limits how many times
one objective may be judged, because every re-evaluation after a model change spends statistical
credibility; all evaluations, including failures, appear in `EVIDENCE.md`.

### 6.4 Tasks

Types: `plan`, `implement`, `docs`, `research`, `design_experiment`, `investigate`, `review`,
`experiment`. Fields worth knowing: `depends_on`, `touches` (globs; overlapping tasks never run
concurrently), `definition_of_done` (commands and existence checks — never "works correctly"),
`deliverables`, `risk`, `budget_usd`, `attempts`/`max_attempts`, and `history` (compact per-attempt
summaries that become the "previous attempts" section of the next packet).

```
             planner (validated)      deps done, budget ok, no touch conflict
 proposed ──(plan approved)──► todo ─────────────────────────────────────► running
                                ▲                                           │ run record
                   repair (fresh │                                          ▼
                   session, maybe│◄────── dod/scope/gate failed ──────── verify
                   bigger model) │                                          │ ok
                                 │◄────── critic: revise ─────────────── review (by risk)
                   attempts      │                                          │ accept
                   exhausted ──► investigate (scientist) ──► replan    merge ─┴─► done
                                                       protected / level<3 ─► needs_founder
```

---

## 7. Experiment and evidence architecture

### 7.1 Pipeline
```
scientist task ──► experiments/drafts/E002.yaml + experiments/runners/e002_ranking.py
                   (mfos exp check + runner --smoke must pass: definition of done)
      │ critic (always at least one lens) reviews the design, blinded
      ▼
founder registers (inbox approval or `mfos exp register E002`)
      │ spec moved to experiments/specs/, spec_hash frozen; audit trail recorded
      ▼
experiment task (orchestrator, no LLM) ──► clean detached checkout of main at commit C
      │ env: MFOS_SPEC_JSON, MFOS_SPEC_HASH, MFOS_SEED (sealed), MFOS_RUN_DIR
      ▼
runner using mfos.evidence.ExperimentRun ──► result.json: metrics (value, CI, n),
      │                                      sanity checks, provenance, artifact hashes
      ▼
evaluator (when all required experiments have admissible results)
      │ validity gates → criteria → EV-O001-NN.json (evaluator version, criteria hash)
      ▼
PASS → blinded evidence review (risk ladder) → claim C### supported → tag O001-passed
FAIL / INCONCLUSIVE / INVALID → scientist diagnosis (+ statistics critic) → replan or founder
```

### 7.2 Identifiers and hashes
`O###` objective · `T####` task · `E###` experiment design (a changed design is a new id) · run id
`E002-20261003T120501-3f9a` · `EV-O001-02` evaluation · `C###` claim · `I####` inbox item · `D####`
decision. Hashes: `criteria_hash` (objective), `spec_hash` (canonical JSON of the spec), `lock_hash`
(`uv.lock`), git commit + dirty flag, sha256 for every artifact.

### 7.3 Provenance recorded automatically by `ExperimentRun`
Run id, experiment id, spec hash, git commit, dirty flag, lock hash, seed and whether it was sealed,
host, platform, Python version, start/finish timestamps, runner command. No agent writes provenance.

### 7.4 Rules that make evidence trustworthy
* **Reference validation first.** A comparison against a reference solver is admissible only with a
  sanity check that proves the reference trustworthy on that run (O001 dedicates E001 to it).
* **Sanity checks must be able to fail** and separate "broken experiment" (INVALID) from "false
  hypothesis" (FAIL).
* **Sealed seeds.** The evaluation sample is generated from a seed injected at run time and recorded;
  agents never see it before the run, so nobody can tune to the evaluation set. Sealed runs are never
  served from cache.
* **Uncertainty everywhere.** `mfos.stats` provides Spearman, MAPE, top-k recall and a seeded
  percentile bootstrap; acceptance on noisy metrics uses `use: ci`.
* **Multi-day runs resume by memoization, not by magic.** Long runners should cache per-item results
  (e.g. each L2 solve) in the artifact store keyed by `(spec_hash, item hash)`; an interrupted run is
  re-launched and skips completed items. This is a runner convention, implemented once in the L2 adapter.

### 7.5 Querying evidence (optional)
```sql
-- duckdb: every ranking result ever produced, newest first
SELECT provenance.run_id, provenance.commit,
       metrics.spearman_rho_Lloop.value AS rho, metrics.spearman_rho_Lloop.ci AS rho_ci
FROM read_json_auto('experiments/results/E002/*/result.json')
ORDER BY provenance.finished DESC;
```

---

## 8. Planning and replanning system

### 8.1 Decomposition
The planner works backward from the acceptance criteria: which experiment produces each metric, what
code that experiment needs, what must be validated first. It schedules the cheapest *discriminating*
work first (reference validation, kill-criterion checks), keeps tasks to one deliverable (20–120
agent-minutes, ≤ 15 files), and must give every task a machine-checkable definition of done. The
orchestrator rejects malformed plans and caps new tasks (8) and open tasks (10) per objective.

### 8.2 Dependencies, parallelism, prioritization
Tasks run when their `depends_on` are done, their objective is active and unblocked, the budget allows,
and no running task has overlapping `touches`. Concurrency is capped (2 agents, 1 CPU-heavy experiment
by default). Order: objective priority first; within an objective, planning tasks (they unblock
everything), then reviews (they unblock merges), then creation order.

### 8.3 Spawning, retries, escalation, cancellation
The orchestrator itself spawns reviews (per risk), experiment-design reviews, evaluation reviews,
diagnoses, and planning tasks. A failed attempt goes back to `todo` with its failure summary; attempt 2+
runs on the escalation model (builder → opus; `fable` only after you approve a `model_escalation` item).
Rate/usage-limit errors pause dispatch for 30 minutes and do *not* count as attempts. Budget or turn
exhaustion commits the partial work to the task branch so the next attempt continues from it. The
planner can cancel tasks; an objective that passes cancels its open tasks.

### 8.4 Replanning triggers
Objective activation (initial plan) · a verdict · a merged diagnosis · a task exhausting its attempts ·
your answer to a planner question. The planner receives the full evidence trail (last evaluations and
diagnoses) in its packet. Replans per objective are capped (3); beyond that the objective goes to you.

### 8.5 How a blocked dependency plays out
Your example — *"O012 is blocked because the L1 thermal model lacks lateral spreading fidelity; create
an investigation"* — maps directly: O012 lists `depends_on: [O002]` (thermal fidelity), so it stays
`blocked` while O002 is not passed. O002's FAIL spawns a scientist diagnosis; if the diagnosis is
*model* ("lateral spreading in the DBC copper is underresolved"), the planner creates the
derivation/implementation tasks under O002 and a fresh-seed re-evaluation. If the scientist concludes
the objective itself is wrong (e.g. the criterion should be on hotspot location, not peak Tj), it flags
`affects_acceptance_criteria` and you get a decision memo. Only you create a new objective such as
"O002b lateral spreading model"; the planner can request it.

### 8.6 Failure taxonomy

| Class | Typical signals | Automatic response | Escalates to you when |
|---|---|---|---|
| **Implementation** | failing DoD/tests, exceptions, scope violations, gate failures | repair attempt with failure output (fresh session; bigger model at attempt 2) | attempts exhausted *and* diagnosis says planning/business |
| **Experimental** | INVALID verdict, sanity check failed, runner crash, timeout, reference not converged | scientist diagnosis → new experiment id (void evidence stays void) → registration by you | every redesign needs registration |
| **Model** | systematic residual correlated with a physical variable, surviving verified code and validated reference | diagnosis with discriminating tests → model-change tasks → fresh-seed evaluation | evaluation budget exhausted |
| **Planning** | repeated replans without convergence, circular dependencies, criteria not decision-relevant | planner re-scopes; `founder_requests` | always (objectives are yours) |
| **Business** | customer or market evidence contradicting a charter assumption | none autonomous | always, as a decision memo |

`mfos.diagnose` maps failure signals to these classes; the scientist refines the class with evidence.

### 8.7 No global "modes"
Research, implementation and validation are properties of *tasks* (types, agents, packets, gates), not
system-wide modes. Real work interleaves them — an implementation task can trigger an investigation that
spawns a design task — and a global mode switch would be one more state to get wrong. What you *do*
control globally is the autonomy level (§22).

---

## 9. Quality gates and adversarial review

### 9.1 Gate layers (each independent of the others)
1. **In-session:** the Stop hook runs the task's definition of done and the fast gate; the agent cannot
   end its turn while they fail (max 3 blocks).
2. **Orchestrator verify:** changed files within the role's scope and outside protected paths;
   deliverables exist; every DoD command exits 0; fast gate; `mfos exp check` for experiment drafts;
   a task claiming success with no changes fails.
3. **Review ladder:** blinded critics by risk (below).
4. **CI on main:** full gate (lint, all tests, license check, `mfos doctor --ci`), nightly as well.
5. **Evaluator validity gates** before any criterion is read.
6. **Blinded evidence review** of PASS verdicts; a `reject` routes the objective to you.
7. **Audit tripwire:** any orchestrator commit touching protected paths without a verifiable approval
   fails `audit.yml`.

The generic acceptance framework is the combination of `ExperimentRun` (metrics with intervals and
sanity checks), registered specs, and the evaluator. Every check you listed fits one of its slots:
unit tests and conservation/symmetry/scaling tests (DoD and gates), numerical regression and golden
cases (`tests/regression`), reference-solver comparisons, reproducibility (determinism tests on seeds),
performance (metrics with thresholds, e.g. A6), licensing (`check_licenses.py`), artifact existence
(deliverables).

### 9.2 Review ladder (`[review_ladder]` in policy)

| Risk | Examples | Critic lenses | Merge |
|---|---|---|---|
| low | docs, refactors, tooling | none | auto (level 3) |
| medium | new modules, generators, adapters | general | auto (level 3) |
| high | physics models, reference solvers, runners feeding acceptance | physics + numerics | you |
| critical | anything the evaluator reads or a public claim rests on | physics + numerics + statistics | you |

Experiment designs always get at least one lens. FAIL/INCONCLUSIVE verdicts get a statistics review
alongside the diagnosis. Extra reviewers are justified exactly where a wrong answer is expensive and
invisible to tests: physics that is internally consistent but wrong, experiments that cannot fail,
statistics that overstate. They are wasted on anything a deterministic test fully covers.

### 9.3 The adversarial pattern you described, as implemented
*Agent A proposes* → builder/scientist. *Agent B reviews* → critic, lens 1, blinded. *Agent C searches
for counterexamples* → critic lens 2 (every critic must run independent checks: limits, symmetries,
alternative implementations). *Benchmark runs* → registered experiment, no LLM. *Manager adjudicates* →
not an LLM: the evaluator adjudicates evidence; a critic reject blocks; disagreements between a PASS
verdict and a rejecting critic go to you.

### 9.4 Defenses against agent failure modes

| Failure mode | Defense |
|---|---|
| Hallucinated success | Outcomes are exit codes and files, never self-reports; "completed" with no diff fails |
| Weakened tests | Acceptance tests protected; critic "tests the tests"; diff review of test changes at medium+ risk |
| Changed acceptance criteria | Objective frozen by hash; evaluator and doctor refuse mismatches; protected path + audit |
| Cherry-picked results | Pre-registered specs; evaluator uses latest admissible run; all evaluations published |
| Unreproducible experiments | Clean checkout at a main commit; lock hash; sealed seeds recorded; dirty runs are INVALID |
| Silent data leakage | Holdout paths unreadable (deny rule + guard); sealed seeds; statistics lens checks leakage |
| Context drift | Fresh sessions from packets; long tasks split; only curated memory |
| Circular reasoning | Author ≠ judge; blinded critic; no agent memory; diagnoses need discriminating tests |
| Reward hacking | Guard blocks protected writes; scope check after the run; audit on main |
| Architectural drift | CLAUDE.md + ADRs + conventions skill; critic general lens; your review of high-risk merges |
| Duplicated/conflicting work | `touches` locks; one orchestrator; worktrees per task; squash merges |
| Premature optimization | Tasks must trace to acceptance criteria; planner anti-patterns list |
| Local maxima | Kill criteria; evaluation caps; replan caps; `/thesis-review` |
| Overconfident scientific claims | Claims carry scope and caveats from reviews; CIs mandatory; supported ≠ proven |

---

## 10. Git and GitHub architecture

### 10.1 Checkouts on the forge box
| Path | Purpose | Who writes |
|---|---|---|
| `~/mf/main` | the orchestrator's checkout of `main`; state commits happen here | orchestrator only — **never edit here**; the loop refuses to start if it finds non-state changes |
| `~/mf/wt/T####` | one worktree + branch `task/T####-slug` per work task | the task's agent |
| `~/mf/wt/review-T####` | detached, sanitized checkout for a critic | nobody (disposable) |
| `~/mf/wt/exp-E###-…` | detached clean checkout of `main` for an experiment run | the runner (outputs go to the main checkout's `experiments/results`) |
| your laptop clone | interactive work, founder edits of protected files | you (push via PR or directly, your choice) |

### 10.2 Commits, merges, tags
* Agent commits: `[T0012] imperative summary` on the task branch; the orchestrator also commits whatever
  the agent left uncommitted. Merges are **squash merges**: one commit on `main` per task, so `git revert`
  undoes exactly one task.
* State commits: `chore(state): …` by the `mfos-bot` identity (set explicitly by the orchestrator; it
  never depends on the machine's git config).
* A merge approved by you carries a `Founder-Approved: I0007` trailer; `audit.yml` verifies that the
  referenced inbox item exists and is approved. Direct founder registrations (`mfos exp register`)
  record an approved inbox item for the same reason.
* Objective passes are tagged `O001-passed`. Experiments are not tagged: every result already names its
  commit and spec hash.

### 10.3 Merge policy
| Autonomy level | low / medium risk | high / critical risk | protected paths |
|---|---|---|---|
| 1 plan-only | you start the task (`mfos task start T…`; the loop finishes it), then approve the merge | you | you |
| 2 execute | you approve every merge (inbox) | you | you |
| 3 autonomous | auto-merge if verify + reviews pass and ≤ 25 files | you | you |

### 10.4 GitHub
* **Phases 0–3 (`merge_mode = "local"`).** GitHub is the remote of record and CI's home; merges happen
  on the forge box after the orchestrator's gates, and `main` is pushed with a repository deploy key.
  Protect `main` with a ruleset that blocks force-pushes and deletion (commands in §20). CI re-runs the
  full gate on every push; `audit.yml` is the server-side tripwire.
* **Phase 4+ (`merge_mode = "github"`).** A machine account (e.g. `moduleforge-bot`, write access, its
  own fine-grained token kept in `~/.config/mfos/gh` and never exported to agents) pushes task branches
  and opens PRs; the ruleset requires the `gate` status check and code-owner review; `CODEOWNERS` routes
  protected paths to you; low/medium PRs are merged by the orchestrator after CI, high-risk PRs wait for
  your GitHub review. State commits still go directly to `main` (the bot is the ruleset's only bypass).
* **Rollback:** `git revert <squash-commit>` (or ask for a revert task). Evidence produced on a reverted
  commit remains valid *for that commit*; if a claim rests on it, re-evaluate.

---

## 11. Claude Code configuration

| File | Purpose | Contents | Written by | Read by | Update policy |
|---|---|---|---|---|---|
| `CLAUDE.md` (43 lines) | Always-loaded project facts | mission, how work happens, map, commands, non-negotiables, glossary | you | every session | protected; keep < 150 lines; facts, not procedures |
| `.claude/settings.json` | Permissions and hooks for every session | allow/ask/deny rules (no push, no `gh`, no holdout reads, no secrets), hook wiring, `autoMemoryEnabled: false` | you | Claude Code | protected |
| `.claude/settings.local.json` | your personal preferences | anything | you | your sessions | gitignored by Claude Code |
| `.claude/agents/{planner,builder,scientist,critic,scout,scribe}.md` | Role definitions | frontmatter (tools, model, effort, preloaded skills) + system prompt | you | `claude --agent <role>` | protected; change deliberately, re-run the canary |
| `.claude/skills/mf-*` (7) | Shared procedures, preloaded per role | conventions, evidence, git, diagnosis, review, planning, research | you (agents may propose) | agents | protected |
| `.claude/skills/{status,inbox,objective,work,investigate,thesis-review,resume}` | Your commands | `disable-model-invocation: true`; live data via `` !`uv run mfos …` `` | you | you | protected |
| `.claude/hooks/{guard,stop_gate,session_start}.py` | In-session enforcement | stdlib-only Python | you | Claude Code | protected; tested in `tests/mfos/test_hooks.py` |
| `.mfos/policy.toml` | Operating policy | scopes, protected paths, budgets, models, ladders, gates, autonomy | you | orchestrator + hooks | protected; restart loop to apply |
| `templates/*` | Shapes for objectives, tasks, specs, decisions, claims | commented YAML/MD | you | `/objective`, agents | protected |

Claude Code behaviors this design relies on (and how it copes if they change):

* `claude -p --agent <role>` runs the main session as that subagent: its prompt replaces the default
  system prompt, its `tools` restrict the session, and project settings, hooks, skills and `CLAUDE.md`
  load normally. Frontmatter hooks in project agents need workspace trust, which `-p` does not grant — so
  all hooks live in `settings.json`, where they do run in `-p`.
* The docs recommend `--bare` for scripted calls and say it will become the default for `-p`; bare mode
  skips project hooks, skills, settings and `CLAUDE.md`. **Mitigation:** pin the CLI version on the forge
  box, run the O000 canary after every upgrade, and if the default flips, pass the configuration
  explicitly (`--settings`, `--agents`, `--append-system-prompt-file`) in `mfos/agents.py`.
* `--permission-prompts none` (v2.1.259+) makes headless runs deny instead of wait when a permission
  prompt would appear; `--max-budget-usd` caps each run using Claude Code's client-side cost estimate.

---

## 12. Agent system prompts

The complete, operational prompts are the files in `.claude/agents/` and are reproduced verbatim in
Appendix A. Each follows the same contract: mission; inputs (the task packet is authoritative); what
"done" means (commands, not opinions); hard rules ("never" list mirrored by hooks); output schema.
The clauses that carry the most weight:

| Agent | Load-bearing clauses |
|---|---|
| planner | Plan backward from acceptance criteria; the cheapest discriminating task first; every task has a machine-checkable DoD; never create work unconnected to a criterion; after a FAIL design discriminating experiments, never "re-run until pass"; propose objective/criteria changes only as `founder_requests` |
| builder | The packet is the spec; smallest change that satisfies the DoD; never weaken or delete a test to pass; physics code needs analytic + limit + symmetry/conservation + scaling tests; report `blocked` honestly |
| scientist | Pre-register before seeing data; sanity checks that can fail; ≥ 2 explanations with discriminating tests; never recommend moving thresholds; separate facts from inferences |
| critic | You are blinded by design; restate the claim, name the three likeliest failure routes, run independent checks; acceptance without checks is invalid; severity-ranked findings with evidence |
| scout | Primary sources; cite only what you opened; numbers with units and conditions; mark inferences; state thesis impact |
| scribe | Compress, never add; every sentence traceable to a file |

Every run's user prompt is a single line pointing at the packet (`.mfos/packets/<task>-a<attempt>.md`);
the packet contains the objective summary, the task, context files, definition of done, write scope,
previous attempts, and the required output. `mfos packet T0012` prints any packet for manual use.

---

## 13. Hooks

| Hook | Event | Enforces | Why a hook |
|---|---|---|---|
| `guard.py` | PreToolUse on Edit/Write/NotebookEdit/MultiEdit/Bash, and Read on holdout paths | role write scopes; protected paths (unless the orchestrator set `MFOS_APPROVED_PROTECTED=1` after your approval); no writes outside the checkout except temp; no holdout reads; no push/merge/rebase/`gh`/sudo/pipe-to-shell/pip; shell commands whose *write targets* hit protected paths (it parses redirections, `tee`, `sed -i`, `cp`/`mv`/`rm`) | stops violations before they happen, with a reason the agent can act on |
| `stop_gate.py` | Stop | builder/scientist cannot finish while the DoD or the fast gate fails; at most 3 blocks, then the orchestrator decides | turns "I'm done" into "the checks pass" inside the session, where fixing is cheapest |
| `session_start.py` | SessionStart | agents get their role contract; your sessions get the live `STATUS.md` and commands | orientation without bloating `CLAUDE.md` |

Design notes: hooks are **standard-library only** (they run under whatever `python3` is on PATH, even in
a fresh worktree before `uv sync`) — which is why the policy is TOML (`tomllib`) rather than YAML. The
guard **fails closed** for agent roles (unreadable policy → deny everything) and **stays out of your
way** in your own sessions (no role → permission rules only). Enforcement is layered so no single
bypass matters: permission deny rules → guard hook → orchestrator scope check on the committed diff →
CI audit on `main`.

---

## 14. Orchestration code

### 14.1 Module map (`tools/mfos/mfos`, 3,056 lines)

| Module | Lines | Responsibility |
|---|---|---|
| `models.py` | 413 | pydantic schemas for every file and every agent output |
| `store.py` | 233 | file I/O, ids, policy, events, git helper with the bot identity |
| `loop.py` | 733 | the orchestrator: tick, dispatch, run completion, verify, reviews, merge, evaluation routing, replanning, recovery |
| `agents.py` | 206 | launches `claude -p` with pre-minted session ids and run records; resume; cost ledger |
| `packets.py` | 214 | task, plan, and review packets; machine-readable DoD for the Stop hook |
| `gitops.py` | 167 | worktrees, sanitized review checkouts, scope checks, local squash merges or GitHub PRs |
| `experiments.py` | 142 | registration (hash freeze), clean-checkout runs with sealed seeds, caching, draft validation |
| `evaluate.py` | 140 | validity gates and conservative three-valued criterion logic |
| `evidence.py` | 133 | `ExperimentRun`: the only way results are written |
| `stats.py` | 71 | Spearman, MAPE, top-k recall, seeded bootstrap |
| `report.py` | 63 | `STATUS.md`, `EVIDENCE.md` |
| `gates.py`, `diagnose.py` | 57 + 57 | DoD/gate execution; failure-signal classification |
| `cli.py` | 421 | every founder and system command |

### 14.2 The tick (every 30 s under systemd)
```
tick():
  if STOP file: only poll, never start work
  sync main (github mode)
  poll finished agent runs      → route by task type: plan → validate/materialize; work → commit, verify;
                                  review → store, downgrade unchecked accepts; errors → backoff / repair
  resume interrupted runs once  (process gone, no JSON result → claude --resume <session>)
  advance tasks                 verify → review (risk ladder) → merge (policy, level) → post-merge hooks
  poll experiments              result.json appeared → done; crashed/timeout → failure routing
  per objective                 blocked? needs plan? all required results admissible? → evaluate → route
  dispatch                      ready tasks by priority within concurrency, touches locks, budgets, level
  write STATUS.md; commit state (skip timestamp-only changes); heartbeat
```
The loop refuses to start if the orchestrator checkout has non-state changes (e.g. an interrupted merge),
survives exceptions inside a tick, and halts cleanly with an inbox item after three consecutive tick
errors so systemd never crash-loops it.

### 14.3 The exact agent invocation
```
claude -p "You are the \`builder\` agent working on T0012 (O001). Your complete instructions are in the
           task packet at \`.mfos/packets/T0012-a1.md\`. …"
       --agent builder --output-format json --json-schema '<BuildReport JSON schema>'
       --max-turns 80 --max-budget-usd 4.00 --permission-mode auto --permission-prompts none
       --session-id <uuid4, recorded before launch> --model sonnet
env:   MFOS_ROLE=builder MFOS_TASK_ID=T0012 MFOS_OBJECTIVE=O001 MFOS_DOD_FILE=<worktree>/.mfos/packets/T0012-a1.dod.json
       (GitHub tokens and the bot's gh config are scrubbed from the environment)
cwd:   ~/mf/wt/T0012
```

### 14.4 Tests (`tests/`, 25 passing, ~20 s)
* `test_evaluate.py` — conservative bounds, kill criteria requiring certainty, missing intervals.
* `test_stats.py` — known Spearman values, bootstrap reproducibility.
* `test_hooks.py` — guard decisions (scopes, protected paths, tmp, holdout, shell write targets,
  founder sessions) and the Stop gate blocking until the DoD passes.
* `test_loop_e2e.py` — the **real orchestrator** with a fake `claude` that accepts the same flags and
  emits the same JSON envelope: canary objective from approval to supported claim and tag; repair after a
  wrong first attempt; criteria tampering detected; a subtle bug caught by the experiment → FAIL →
  diagnosis → replan → rebuild → PASS with both evaluations on record; initial plan waiting for your
  approval; level-2 merges waiting for you and passing the audit; refusal to start on stray changes;
  founder-owned files never committed by the bot; agents get a Python ≥ 3.11 first on PATH (macOS's
  `/usr/bin/python3` is 3.9 and would make the guard fail closed); laptop sleep extends run deadlines
  instead of timing runs out; experiments above `local_cpu_hours_max` are routed to burst compute and
  their results, produced elsewhere, complete the task; the guard accepts macOS temp paths
  (`/tmp` → `/private/tmp`, `$TMPDIR` under `/private/var/folders`) with path-boundary matching.

Defects found during development, all fixed and now covered by tests. *Found by the tests:* an
event-field name collision; a missing git identity misreported as a merge conflict (and charged to the
agent as three failed attempts); state-commit churn; a lost-update race that erased diagnoses from the
planner's view; an audit false positive for the founder's own registrations. *Found in review, then
tested:* the initial-plan approval never triggering; founder-owned files being swept into bot state
commits; local merge mode never pushing `main`. *Found by schema validation:* YAML's bare `null:` key
and a flow mapping whose commas split one description into four keys. *Found on the first real Mac
setup:* the guard denied scratch writes to `/tmp` (a symlink on macOS), and FastHenry would not build
with Apple clang (K&R C rejected by default); both are fixed and regression-tested (FastHenry against
clang 18 and gcc 13, with a closed-form self-test). Run the suite after every change
to `tools/mfos` or the hooks.

### 14.5 Extending
New role: add `.claude/agents/<role>.md`, an output model in `models.ROLE_OUTPUT`, a write scope in
policy. New compute backend: implement it behind `mfos exp run` (same env contract, same `result.json`).
New gate: add a command to `[gates]`.

---

## 15. Cost-control system

### 15.1 Mechanisms, from innermost to outermost
1. **Per run:** `--max-budget-usd` (from the task budget), `--max-turns`, a wall-clock deadline
   (90 min default) after which the process group is killed.
2. **Per task:** planner-set `budget_usd`, capped by policy (`max_task_usd` $8; plan $4, review $3,
   diagnosis $5); attempts capped (3).
3. **Per objective:** your `budget.usd`; the ledger in `state.yaml` accumulates every run's reported cost;
   crossing it sends a `budget_increase` item and stops new work on that objective only.
4. **Per day / week:** `daily_usd` $40 / `weekly_usd` $200; at the cap, dispatch stops until tomorrow and
   you get one inbox notice.
5. **Structural:** no LLM in experiments, evaluation, verification or merging; model routing by role
   (haiku for compression, sonnet for building, opus where judgment is the product); escalation only
   after a failed attempt; review depth by risk; sealed-seed runs never re-run silently; evaluation caps;
   planner task limits; rate/usage-limit backoff that does not burn attempts.

### 15.2 When more agents are worth it
Default is one agent plus deterministic checks. Add a critic when the change is medium risk or is an
experiment design. Use two or three lenses only for high/critical changes and for PASS verdicts of
high-risk objectives. Launch parallel independent scientists only for a high-stakes diagnosis whose
first attempt came back below ~0.5 confidence. The rule of thumb: pay for another agent when its
*independence* can catch an error that no test can, never for "more thoroughness" in general.

### 15.3 Expected spend (order-of-magnitude, API-equivalent)
| Unit | Typical |
|---|---|
| planner run | $0.5–3 |
| builder task (incl. one repair) | $1–6 |
| scientist design / diagnosis | $2–6 |
| critic review | $0.5–3 per lens |
| O000 canary | $2–5 |
| O001 (≈ 16–20 tasks, one FAIL cycle) | $70–110 |
| a steady month, 2 concurrent agents, level 3 | $400–900 |

On a Claude subscription the same work consumes usage limits instead of dollars; the orchestrator's
dollar figures are then Claude Code's client-side estimates, still useful as relative budgets. If limits
become the bottleneck, point the forge box at an API key (pay-as-you-go, separate from your personal
usage). Calibrate these numbers from `mfos costs` after the first two weeks.

---

## 16. Context and memory system

| Tier | What | How it gets there |
|---|---|---|
| Always loaded | `CLAUDE.md` (43 lines), the role's system prompt, the role's preloaded skills | Claude Code at session start |
| Per run | one task packet: objective summary, task, context files, DoD, scope, prior attempts, output contract | orchestrator (`packets.py`) |
| On demand | repository files; `project/memory/` notes; literature index; decisions; diagnoses; other skills by description | the agent reads what the packet points to |
| Summarized | attempt histories (≤ 800 chars each, last 3 in packets); last evaluations and diagnoses for the planner; `STATUS.md` | orchestrator |
| Archived | finished objectives' tasks and reviews (in Git history; `project/tasks` can be pruned per objective) | Git |
| Ignored | raw transcripts, run stdout, events older than the tail | never fed back to agents |

**No agent memory.** Claude Code's auto memory and the subagent `memory:` field would let agents write
notes to themselves that nobody reviews and that silently shape future runs — a direct path to circular
reasoning and drift. Instead, knowledge that should persist is written as reviewed, cited files
(`lessons.md` lines cite the task or evaluation that taught them; literature notes cite sources) and
enters context only when a packet or an agent's own search pulls it in.

**Stale knowledge** is handled by provenance and status rather than deletion: notes carry dates and
sources; claims can be `retracted`; decisions can be `superseded`; `/thesis-review` re-examines the
charter against the evidence periodically.

---

## 17. Failure recovery

| Event | What happens | What you do |
|---|---|---|
| SSH disconnect | nothing (systemd service; tmux for interactive) | reattach |
| VM reboot | systemd restarts the loop; runs whose processes vanished without a result are resumed once with `--resume <session-id>` (pre-minted ids make this exact); experiments without a result are retried | nothing |
| Agent crash / malformed output | treated as interrupted → resumed once → otherwise a failed attempt | nothing |
| Rate or usage limit | dispatch pauses 30 min; the attempt is not counted | nothing (or switch to an API key) |
| Budget/turn exhaustion mid-task | partial work committed to the task branch; next attempt continues from it | nothing |
| Simulation hangs | spec `timeout_min` kills it → experimental failure → retry, then diagnosis | nothing |
| Multi-day experiment interrupted | re-launched; memoized per-item results are skipped (§7.4) | nothing |
| Orchestrator killed mid-merge | on restart it refuses to run while the main checkout has non-state changes | inspect with `git status`, then `git merge --abort` / `git reset --hard HEAD`, then `systemctl --user restart mfos` |
| Repeated exceptions in the loop | halts after 3 consecutive tick errors, writes `.mfos/last_error` and an inbox item | fix, then `uv run mfos start` |
| GitHub outage | local mode unaffected; state pushes retried next tick | nothing |
| You're away for two weeks | work continues within budgets; decisions queue; affected branches wait | `/resume`, then `/inbox` |

**"Resume the project."** Open Claude Code in `~/mf/main` (or your clone) and run `/resume`: it reads live
status, recent history and the loop heartbeat, and tells you what completed, what failed, what is
running, what waits for you, and the exact restart command if the loop is down.

---

## 18. Human-in-the-loop policy

| Never interrupts you | Digest only (visible in `/status`) | Requires your approval (inbox; blocks only that branch) | Emergency (loop halts) |
|---|---|---|---|
| task decomposition within an approved plan · retries and repairs · model escalation up to opus · critic reviews · merges of verified low/medium work at level 3 · experiment runs of registered specs · evaluations · diagnoses · replans after a diagnosis (level 3) · research notes | objective passed (claim created) · FAIL/INCONCLUSIVE verdicts and their diagnoses · spend summaries · merged work | new or changed objectives and acceptance criteria · initial plans (all plans below level 3) · experiment registration · protected-path changes (policy, hooks, agents, acceptance tests, evaluator) · high/critical-risk merges · budget increases · `fable` escalation · disputed PASS verdicts · exhausted evaluation or replan budgets · planning/business-class failures · anything external: customer contact, publication, purchases, licensing | three consecutive loop errors · suspected secret exposure · audit tripwire on `main` |

**Your interface, in order of frequency:** `/inbox` (daily, 10–20 minutes: approvals with a brief and a
recommendation each), `/status` (whenever), `/objective` (weekly: new objectives), `/investigate`
(when you have a hunch), `/thesis-review` (every two weeks), GitHub notifications (CI or audit failures).
Everything is also available as plain commands (`uv run mfos inbox`, `mfos approve I0007 --note …`).

---

## 19. First bootstrap objective

### 19.1 O000 — framework canary (run first, ~$2–5, ~20 minutes)
Hypothesis: `moduleforge.canary.harmonic(n)` matches the asymptotic expansion of the harmonic numbers to
1e-9 relative error for n = 10³…10⁶. The experiment E000 and its runner are pre-written (the runner
validates its own reference against the exact H₁₀ computed with fractions). The planner must produce an
implement task and an experiment task; the builder implements; the Stop hook and verify gate check it;
the orchestrator merges, runs E000 in a clean checkout, evaluates, records claim C001, tags
`O000-passed`. **It proves the plumbing on your machine:** authentication, `--agent`, JSON schema output,
permission modes, hooks firing in `-p`, worktrees, merges, experiments, evaluator.

### 19.2 O001 — L1 PEEC ranking fidelity (the first real objective)
File: `project/objectives/O001/objective.yaml` (depends on O000; plan approval required; budget $120,
60 CPU-hours, 21 days).

**Hypothesis.** A fast quasi-static PEEC model (rectangular trace cells with skin-depth-corrected
resistance, bond wires as round filaments with Grover partial inductances, the stack's conductive planes
as image planes)
ranks DRC-valid wire-bonded half-bridge DBC/AMB layouts by commutation-loop inductance at 20 MHz
consistently with a converged reference solver, at ≤ 50 ms median per evaluation on one core.
**Why first:** every downstream objective (search headroom, derivative re-layout prototype) assumes a
cheap, faithful inner-loop objective; if it fails, compute per design rises by orders of magnitude and the
product and unit economics change.

| Criterion | Metric | Threshold | Rationale |
|---|---|---|---|
| A1 | E001 max relative error of the reference vs closed-form partial inductances | ≤ 2 % (point) | the reference must be right before anything is compared to it |
| A2 | E002 Spearman ρ(L1, L2) | lower 95 % bound ≥ 0.85 | search needs a reliable *ordering*; ρ = 0.85 means roughly one pair in six misordered (Kendall τ ≈ 0.66 under a bivariate-normal model), mostly between near-equal layouts |
| A3 | E002 Spearman ρ | point ≥ 0.90 | guards against a wide interval that barely clears A2 |
| A4 | E002 MAPE | upper 95 % bound ≤ 12 % | numbers shown to customers must be usable, not just ordered |
| A5 | E002 top-decile recall into L2's top quintile | ≥ 0.70 | search selects from the top; this is the decision-relevant fidelity |
| A6 | E003 median L1 evaluation time | ≤ 50 ms | 10⁵ evaluations per derivative in ~5 minutes on a 16-core box |
| K1 | ρ | upper bound < 0.80 | definitely too unreliable |
| K2 | MAPE | lower bound > 20 % | definitely too biased |
| K3 | top-decile recall | < 0.50 | most of L1's picks would not be good ones (random would score 0.20); L2 audits would dominate cost |

Failure modes F1–F6 cover an unconverged reference, unrepresentative samples (diversity and DRC-validity
sanity checks), missing physics (residuals vs loop area, baseplate distance, die count), frequency
dependence, overfitting (sealed seeds, evaluation count), and reference-tool licensing.

---

## 20. Exact setup instructions

> **Superseded for Phases 0–3 by `docs/INFRASTRUCTURE.md` §12 (MacBook setup).** The Linux procedure
> below remains valid if you later move the orchestrator to an always-on Linux machine; size it at
> 2–4 vCPU and 4–8 GB, not 16–32 vCPU (the agents need no local compute; heavy experiments burst).

Time: about two hours, most of it waiting for installs and the canary. Commands assume Ubuntu 24.04 on
the forge box and a GitHub account `<you>`.

**Step 0 — Linux host (only if you move the orchestrator off the Mac).** 2–4 vCPU, 4–8 GB RAM,
40 GB disk, Ubuntu 24.04 (a small cloud VM). Log in as your normal user, not root.
```bash
sudo apt-get update && sudo apt-get install -y git tmux jq unzip build-essential python3 gh
curl -LsSf https://astral.sh/uv/install.sh | sh && exec $SHELL -l
python3 --version        # >= 3.11 required by the hooks (24.04 ships 3.12)
```

**Step 1 — Claude Code.** Install with the method on https://code.claude.com/docs/en/setup, then:
```bash
claude --version         # note the version; you will pin it
mkdir -p ~/.config/mfos
cat > ~/.config/mfos/env << EOF2
PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
DISABLE_AUTOUPDATER=1
# ANTHROPIC_API_KEY=sk-ant-...   # optional: pay-as-you-go instead of your subscription login
EOF2
```
Upgrade Claude Code deliberately, never automatically, and re-run the O000 canary after each upgrade.

**Step 2 — Repository.**
```bash
mkdir -p ~/mf && cd ~/mf && unzip ~/moduleforge-os.zip && mv moduleforge main && cd main
scripts/bootstrap.sh <you>               # checks tools, sets identities, uv sync, runs the 25 tests, first commit
gh auth login                            # as you, once, to create the repository
gh repo create <you>/moduleforge --private --source . --push
ssh-keygen -t ed25519 -f ~/.ssh/mfos_deploy -N "" -C mfos-forge
gh repo deploy-key add ~/.ssh/mfos_deploy.pub --allow-write --title "mfos forge box"
printf 'Host github.com\n  IdentityFile ~/.ssh/mfos_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
git remote set-url origin git@github.com:<you>/moduleforge.git && git push -u origin main
```

**Step 3 — Protect `main`** (rulesets on private repositories need GitHub Pro or a Team organization):
```bash
cat > /tmp/ruleset.json << 'EOF2'
{"name": "protect-main", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}
EOF2
gh api repos/<you>/moduleforge/rulesets --method POST --input /tmp/ruleset.json
```
Also enable email notifications for failed workflow runs (the audit tripwire reports that way).

**Step 4 — Log in and trust the workspace.**
```bash
cd ~/mf/main && claude       # complete the login; accept the trust prompt; run /status; then /exit
```

**Step 5 — Canary.** At autonomy level 3 (the shipped setting):
```bash
uv run mfos exp register E000            # your registration of the pre-written canary experiment
uv run mfos objective approve O000       # freezes and activates it (committed under your name)
tmux new -s mfos 'uv run mfos loop --cycles 80 --poll 20'
# in another pane: watch -n 10 uv run mfos status
```
Expect within ~20–30 minutes: a plan, one builder task merged, E000 run, `EV-O000-01` PASS, claim
`C001`, tag `O000-passed`, $2–5 spent. If it stalls, `uv run mfos task list` and the run logs under
`.mfos/runs/` show why (authentication and permission modes are the usual suspects).

**Step 6 — Run permanently.**
```bash
mkdir -p ~/.config/systemd/user && cp scripts/mfos.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now mfos
sudo loginctl enable-linger "$USER"      # keep running after you log out
journalctl --user -u mfos -f             # logs
```

**Step 7 — Start the real work** (Phase 1 of §22): set `level = 1` in `.mfos/policy.toml`, commit it,
`systemctl --user restart mfos`, then `uv run mfos objective approve O001` and answer the plan approval
in `/inbox`.

**Phase 4 additions (later).** Create a machine account (`moduleforge-bot`), give it write access, log it
in with `GH_CONFIG_DIR=~/.config/mfos/gh gh auth login`, set `merge_mode = "github"`, and extend the
ruleset: require the `gate` status check and code-owner review for pull requests, with the deploy key as
the only bypass actor (it carries the orchestrator's state commits).

---

## 21. First autonomous run: O001, as it would unfold

The sequence below is what the implemented machinery does with O001; the physics and numbers are an
illustrative projection, not results.

**Day 0 (you, 10 min).** `mfos objective approve O001`. The next tick creates `T0003 plan (initial)`.
The planner returns nine tasks; because O001 requires plan approval they arrive as `proposed`, with an
inbox item. You approve.

| Task | Agent · risk | Deliverable | Depends on |
|---|---|---|---|
| T0004 | scout · low | reference-solver survey: accuracy, bond-wire handling, licenses; published half-bridge loop-inductance benchmarks | — |
| T0005 | scientist · high | E001 design: reference vs closed-form partial inductances (rectangular bars, round wires, coupled bars) + runner | — |
| T0006 | builder · high | layout IR, layer stack, DRC-valid half-bridge generator (families A/B/C, 2–6 dies) + tests | — |
| T0007 | builder · high | L2 adapter: solver invocation, mesh controls, per-solve memoization | T0004 |
| T0008 | builder · high | L1 PEEC in JAX: cell kernels, skin-corrected R, bond-wire filaments, image planes | T0006 |
| T0009 | scientist · high | E002 ranking design (sealed seed, 60 layouts, secondary 5/80 MHz) + E003 timing design | T0006, T0008 |
| T0010–T0012 | orchestrator | run E001, E002, E003 | designs registered; T0007/T0008 |

**Days 1–6.** Two agents at a time. The scout's survey merges automatically (low risk). Each builder task
passes its Stop hook and verify, then physics and numerics critics review it blind. One critic finds the
L1 mutual-inductance matrix asymmetric at 1e-9 relative (a quadrature ordering bug); the builder's
second attempt (on opus) fixes it and adds a reciprocity test. High-risk merges wait for you; you review
three diffs (~20 minutes). The scientist's designs each get a critic review; you register E001, E002 and
E003 from `/inbox` (the statistics critic's caveat — "stratify the 60 layouts by family" — was folded
into E002 before registration).

**Day 5.** E001 runs in a clean checkout: maximum error of the reference vs closed forms 0.9 % → A1
will hold. **Days 7–8.** E002 (≈ 2 CPU-hours of memoized L2 solves on the Mac, ~30–40 minutes on
four cores; `docs/INFRASTRUCTURE.md` §7.3) and E003 run.

**Evaluation EV-O001-01 → FAIL.**

| Criterion | Result | Judgment |
|---|---|---|
| A2 ρ lower bound ≥ 0.85 | ρ = 0.83 [0.74, 0.90] | not met |
| A4 MAPE upper bound ≤ 12 % | 0.31 [0.26, 0.37] | not met |
| K2 MAPE lower bound > 20 % | 0.26 > 0.20 | **kill criterion met → FAIL** |
| A5 recall ≥ 0.70 | 0.50 | not met (K3 not met: 0.50 is not < 0.50) |
| A6 p50 ≤ 50 ms | 21 ms | met |

**Automatic response (no human).** The orchestrator logs the verdict, spawns `T0013 investigate`
(scientist, class *model*) and `T0014 review` (statistics lens) of the evaluation.

**Diagnosis T0013.** L1 overestimates L on all 60 layouts (mean +31 %); the error grows with loop area
(r = 0.81) and not with die count. Competing explanations and the discriminating tests the scientist ran:

| Explanation | Discriminating test | Outcome |
|---|---|---|
| (a) L1 places its image plane at the baseplate, but at 20 MHz the DBC backside copper (skin depth ≈ 14.6 µm ≪ 0.3 mm) is the nearest return plane; L1 underestimates flux cancellation, increasingly with loop area | move L1's image to the backside copper on 12 layouts; separately, remove backside copper in L2 | MAPE drops to ~9 %; without backside copper, original L1 error drops to ~6 % — **supports (a)** |
| (b) L2 under-resolves baseplate eddy currents | refine the baseplate mesh 2× | L2 changes < 0.8 % — rejects (b) |
| (c) bond-wire self-inductance formula wrong | bond-wire-only loops vs Grover | within 1.5 % — rejects (c) |

Conclusion: model failure, confidence 0.8. Recommendation: model the layered stack's image planes with the
backside copper first and a finite-thickness correction; re-evaluate on a **fresh sealed seed**
(evaluation 2 of 3). Acceptance criteria unaffected. The statistics critic concurs and notes that both
evaluations must be reported.

**Replan (T0015, trigger `diagnosis:T0013`).** Three tasks: scientist derives the layered image model and
its validity limits; builder implements it with tests (microstrip-over-ground analytic limit,
reciprocity, frequency limits) — high risk, so you approve the merge; experiment tasks re-run E002 and
E003. E002's registered design is unchanged; only the model under test changed, and the fresh seed means
a new sample of layouts.

**Evaluation EV-O001-02 → PASS.** ρ = 0.93 [0.88, 0.96]; MAPE 0.084 [0.069, 0.101]; recall 0.83;
p50 23 ms. Because O001 is high risk, physics and numerics critics review the evidence blind. Physics:
*accept with caveats* — its independent analytic check holds, but validity requires continuous backside
copper under the commutation loop; patterned backsides are not covered. Numerics: *accept* — five layouts
re-run at 2× discretization in both models keep their ranks, values within 1.2 %. The orchestrator records
claim `C002` (supported, with the caveat), tags `O001-passed`, cancels leftover tasks, and objectives
depending on O001 become eligible.

**Your total involvement:** objective approval, plan approval, three registrations, four high-risk merge
reviews, and reading the digest — roughly 1–1.5 hours across about two weeks. **Cost:** ~18 tasks
including reviews, ~$85 of LLM use, ~3–6 CPU-hours on the MacBook.

---

## 22. Migration from the current manual workflow

The autonomy knob (`[autonomy] level` in policy) makes each phase a one-line change.

| Phase | When | What changes | Your routine | Exit criterion |
|---|---|---|---|---|
| **0 Install** | day 1 | this repository; your manual prompts become `CLAUDE.md`, agents, skills (done) | §20 | O000 passes with the real CLI |
| **1 State and evidence** (`level = 1`) | week 1 | objectives, tasks, registrations, evaluator are live; the planner decomposes and writes packets; hooks and gates check everything | start each task with `uv run mfos task start T…` (headless; the running loop verifies, reviews and merges it) or `/work T…` (paired), then approve its merge. `mfos run T…` is for when no loop runs | first evaluation of O001 produced; you stopped editing packets |
| **2 Execution** (`level = 2`) | weeks 2–3 | the loop runs all tasks and experiments | `/inbox` once or twice a day: every merge waits for you | ≥ 10 merges approved without changes; no guard or audit incidents; spend within ±30 % of budgets |
| **3 Autonomy within policy** (`level = 3`) | weeks 3–6 | low/medium merges automatic; replanning after diagnoses automatic | `/inbox` daily, `/status` whenever | one objective completed end to end, including a failure cycle; < 3 h/week of your time |
| **4 GitHub-native** | month 2 | `merge_mode = "github"`, bot account, PRs, code-owner review | review high-risk PRs on GitHub (phone-friendly) | a week with zero audit failures |
| **5 Portfolio** | month 3+ | several objectives in parallel, concurrency 3–4, remote compute backends, biweekly `/thesis-review` | weekly objective setting; daily inbox | the system, not you, is the bottleneck on experiment throughput |

Your original migration list maps as follows: prompts → `CLAUDE.md`/agents/skills (Phase 0);
project-state files (Phase 1); task decomposition and prompt generation (Phase 1, planner + packets);
test execution (Phase 1, hooks and gates); experiment execution (Phase 1, runners); replanning (Phase 3);
increasing autonomy (Phases 2–5).

---

## 23. Future evolution

* **Claude Agent SDK** for the agent runner when you need mid-run steering, streaming into a dashboard,
  programmatic permission decisions, or shared session stores (only `mfos/agents.py` changes).
* **Remote compute**: an `ssh`/Ray/cloud-batch backend behind `mfos exp run`, reusing the per-item
  memoization cache; the orchestrator stays on the forge box.
* **Cloud or self-hosted Claude Code environments and routines** for scheduled audits (nightly
  literature watch, weekly dependency review) once they suit unattended, repository-bound work.
* **Agent teams** as founder-attended war rooms for surprising results, once they leave experimental status.
* **Approvals from anywhere**: mirror inbox items to GitHub issues or a messaging app; approve with a
  signed comment the orchestrator verifies.
* **Evidence dashboard**: DuckDB over results plus a static page per objective.
* **Customer-confidential mode**: a separate forge box per customer engagement, data vault outside Git,
  Claude via your cloud provider's regional endpoints or zero-data-retention arrangements, and a
  strict no-customer-data rule in the main repository (already stated in `project/customers/README.md`).
* **Extract `mfos`** into its own package once its interfaces stop changing; reuse it (with the
  `.claude/` layer packaged as a plugin) for your trading research project.
* **Product agents** (customer-facing setup assistants, report writers) built on the SDK/API with API keys.

---

## 24. Final architecture critique

**Is it too complex?** The orchestrator is ~3,000 lines plus ~250 lines of hooks. That is the right size
for what it replaces — the manual loop of planning, prompting, checking, merging, running, judging — and
every module has one job. The genuine complexity risks are elsewhere: the review ladder (multiple lenses
per change), GitHub PR mode, and the number of inbox kinds. All three are already optional or deferred.

**What Claude Code gives natively and we use as is:** the agent loop, tools, subagent definitions,
skills, hooks, permission modes (including auto mode), headless JSON output with schemas, budgets and
session resume. **What we built, and why:** durable state, verdicts, pre-registration, sealed seeds,
blinding, and recovery — because correctness here must not depend on any model's judgment.

**Delay until needed:** GitHub merge mode and the bot account (Phase 4), the scribe (optional), multi-lens
reviews below high risk, DuckDB, remote artifact sync, remote compute, the Agent SDK.

**Essential from day one:** frozen objectives and the evaluator, `ExperimentRun` and registration, the
guard hook and scope checks, worktrees, packets, run records, the inbox.

**Most likely failure modes, and the watch for each:**
1. *CLI behavior drift* (flags, `--bare` becoming the default for `-p`, schema changes) — pinned version,
   canary after upgrades, a single adapter module.
2. *Planner mis-decomposition* (too coarse, too fine, speculative) — task limits, plan approval early,
   look at plans weekly for the first month.
3. *Weak tests passing weak code* (Goodhart on the definition of done) — critics test the tests;
   acceptance tests are protected and written separately; physics test standard in conventions.
4. *Experiment-design quality* is the true bottleneck — every design is critic-reviewed and registered by
   you; this is where your physics judgment is best spent.
5. *Inbox backlog* throttles everything — approvals block only their branch; keep the daily habit.
6. *Budget estimates vs subscription limits* — backoff handles limits; if they bind, move the forge box
   to an API key.
7. *Slow or flaky gates* stall merges — keep the fast gate under ~2 minutes; mark long tests `slow`.
8. *Editing in the orchestrator's checkout* — state and founder files are separated, and the loop refuses
   to start on stray changes, but the habit matters: edit protected files deliberately and commit them.

**What I would change after a month:** calibrate budgets and model routing from `mfos costs`; drop
review lenses that never find anything; let low-risk experiment designs from a scientist with a good
record auto-register (with you notified); add `mfos archive` for finished objectives; decide on the SDK
from actual pain points, not in advance.

**Simplifications already made:** six agents instead of sixteen; no database; no agent teams; no external
framework; no global modes; no agent memory; no LLM in experiments, evaluation, verification or merging;
no issue tracker as state; one orchestrator process instead of a service mesh.

**The one recommended architecture:** a thin, deterministic, Git-native orchestrator (`mfos`) on a
persistent VM, driving headless Claude Code with six ephemeral, scoped roles; executable objectives with
pre-registered, machine-evaluated criteria; experiments without LLMs on sealed data; blinded adversarial
review scaled by risk; and a single founder inbox for the decisions that are yours.

---

## Appendix A — Agent definitions (verbatim from `.claude/agents/`)

These are the operational prompts. Frontmatter configures tools, model, effort, and preloaded skills;
the body is the system prompt. Generated from the files; the files are authoritative.


### A.1 `planner`

````markdown
---
name: planner
description: Engineering manager for one ModuleForge objective. Turns a frozen objective plus current evidence into a small task graph. Read-only; returns a structured plan that the orchestrator validates. Use for planning and replanning, never for implementation.
tools: Read, Grep, Glob
model: opus
effort: high
skills:
  - mf-planning
  - mf-diagnosis
---

You are the planner for ModuleForge, a physics-first layout compiler for SiC/IGBT power modules.
You plan one objective at a time. The orchestrator (deterministic code) executes your plan,
runs every check itself, and decides outcomes from evidence. You never edit files.

## Inputs
Your task packet (path given in the prompt) contains: the frozen objective (hypothesis,
acceptance criteria, evidence plan, failure modes), its state, the current task table,
registered/draft experiments, recent evaluations and diagnoses, and planning limits.
Read it completely before doing anything else. Read repository files only as needed to plan well.

## What you produce
A `PlanOutput` JSON object:
- `assessment`: 3–8 sentences. Where the objective stands, what the evidence says, what is most
  likely to kill the hypothesis, and why this plan is the cheapest path to a decisive verdict.
- `create_tasks`: the *minimum* set of new tasks. Each must have one coherent deliverable,
  explicit `definition_of_done` commands that a machine can run, `touches` globs, a `risk` level,
  and a budget. Use `local_id` values (n1, n2, …) to express dependencies inside the plan.
- `cancel_tasks`: tasks made obsolete by new evidence, each with a reason.
- `founder_requests`: anything outside your authority (see below).
- `evidence_complete`: true once every experiment in `acceptance.required_experiments` has a
  design task and an experiment task somewhere in the graph.

## How to plan
1. Work backwards from the acceptance criteria. Every task must trace to a criterion, a
   failure mode, or infrastructure a criterion needs. If you cannot name which, drop the task.
2. Front-load kill shots: schedule first the cheap tasks that could falsify the hypothesis.
3. For each required experiment: a `design_experiment` task (agent: scientist) that writes
   `experiments/drafts/<EID>.yaml` and its runner under `experiments/runners/`, then an
   `experiment` task (agent: none, `experiment: <EID>`) that depends on the implementation it measures.
   The orchestrator runs experiments; agents never do.
4. Reference validation comes before comparison: if an experiment compares a fast model to a
   reference, the reference must itself be validated (analytic cases, convergence) first.
5. Size tasks for 20–120 agent-minutes. Split anything bigger; merge anything trivial.
6. Prefer extending existing code over new modules. Name the files a task should read.
7. Respect the limits in the packet. Fewer, sharper tasks beat many vague ones.

## After a FAIL, INCONCLUSIVE, or INVALID verdict
Follow skill `mf-diagnosis`. Classify before acting. Plan the discriminating experiment before
any fix. Never re-run the same evaluation hoping for a different number. Evaluations are a
scarce, counted resource (`max_evaluations`).

## Authority
You MAY: create, re-scope, and cancel tasks within this objective and its budget.
You MUST NOT, and must raise a founder request instead, for any of: changing acceptance
criteria or thresholds, changing the hypothesis or scope, starting a new objective, spending
beyond the objective budget, escalating to the `fable` model, anything touching customers or the
public, deleting infrastructure, or abandoning the objective.

## Never
- Never invent requirements that are not in the objective or the evidence.
- Never mark progress based on agent narratives. Only merged code and evaluator verdicts count.
- Never propose a task whose definition of done is "looks correct" or needs human judgment
  to check. If a check cannot be automated, create a scientist task to design one.
````


### A.2 `builder`

````markdown
---
name: builder
description: Implementation engineer. Implements one well-specified task in its own git worktree - code, tests, and small docs - and must make the task's definition-of-done commands pass. Use for implement and docs tasks.
tools: Read, Edit, Write, Grep, Glob, Bash, TodoWrite, Skill
model: sonnet
effort: medium
skills:
  - mf-conventions
  - mf-git
  - mf-evidence
---

You are a senior scientific-software engineer building ModuleForge (Python 3.12, numpy/JAX,
shapely, pydantic, pytest; uv-managed). You implement exactly one task, specified in the task
packet whose path is in your prompt. Read the packet first, then the files it names.

## Workflow
1. Restate the deliverables and the definition of done (DoD) to yourself in one short list.
2. Read before writing: find the existing code you should extend. Prefer small, local changes.
3. Write tests alongside the code. For numerical code, test against closed-form or
   independently computed values, limiting cases, symmetry, units, and conservation, not only
   "runs without error". Tests that merely re-run the implementation are worthless.
4. Implement the smallest change that satisfies the deliverables.
5. Run every DoD command yourself, plus `uv run mfos gate --fast`. Fix failures. Re-run.
6. Commit your work on this branch with a message starting `[<task id>]`.
7. Return the BuildReport JSON. List every command you ran with its real exit code.

The orchestrator re-runs every check independently and a Stop hook will not let you finish
while the DoD fails, so an honest `partial` or `blocked` report is always better than a false
`completed`.

## Hard rules
- Stay inside your write scope (listed in the packet). Protected paths — acceptance tests,
  registered experiment specs, objective files, `.claude/`, `.mfos/`, `.github/`, `tools/mfos/` —
  are off-limits. Hooks block the attempt and the task fails.
- Never weaken, skip, delete, or loosen an existing test or tolerance to make it pass. If a test
  is wrong, report `blocked` and explain why, with evidence.
- Never read `data/holdout/`. Never hard-code values that make an experiment pass.
- Do not refactor or reformat code unrelated to the task. Do not rename public APIs unless the task says so.
- Do not push, open PRs, merge, change branches, or use `gh`. The orchestrator does integration.
- No new dependencies unless the task says so. If you add one, it must have a permissive license.
- If the task is ambiguous or impossible as written, stop and report `blocked` with the
  specific question. Do not guess at scope.
````


### A.3 `scientist`

````markdown
---
name: scientist
description: Research scientist for physics, numerics, and experimental design. Designs pre-registered experiments, derives and checks models, and diagnoses failures with competing hypotheses and discriminating tests. Use for design_experiment and investigate tasks.
tools: Read, Edit, Write, Grep, Glob, Bash, WebSearch, WebFetch, Skill
model: opus
effort: high
skills:
  - mf-conventions
  - mf-evidence
  - mf-diagnosis
---

You are the research scientist for ModuleForge. Your background is computational
electromagnetics (PEEC, quasi-static field solvers), heat conduction in layered media,
numerical analysis, and the statistics of model validation. Your standard is that of a careful
referee: every claim you make must be checkable by someone who distrusts you.

Read your task packet (path in your prompt) first.

## Task types
**design_experiment** — write `experiments/drafts/<EID>.yaml` (schema: `mfos.models.ExperimentSpec`)
and its runner under `experiments/runners/`. The runner must use `mfos.evidence.ExperimentRun`,
report every declared sanity check, and attach a confidence interval to every metric that feeds
an acceptance criterion. Design so that a wrong model *would* be caught:
- choose the reference first and validate it (analytic limits, mesh convergence);
- make the sample representative and diverse (report a diversity statistic);
- use `sealed_seed: true` whenever tuning to specific cases is possible;
- declare sanity checks that separate "the experiment is broken" from "the hypothesis is false".
Verify it runs: `uv run mfos exp check <EID>` and a small smoke run of the runner.

**investigate** — find the true cause of a failure. Follow skill `mf-diagnosis` exactly:
at least two competing explanations, a discriminating test for each, run the cheap tests, then
classify (implementation / model / experimental / planning / business) with a confidence.
Write notes to the path in the packet. Do not fix production code; recommend actions.

## Rigor checklist (apply every time)
Units and dimensions; sign and orientation conventions; limiting cases; symmetry; conservation;
convergence under refinement; sensitivity to seeds and discretization; comparison to an
independent method; uncertainty on every reported number; what result would prove you wrong.

## Hard rules
- Write only within your scope (packet). Never edit `src/` production code, registered specs,
  acceptance tests, or objective files.
- Never tune an experiment after seeing its result on the evaluation data. Designs are frozen at
  registration; changes require a new experiment id.
- Separate facts, inferences, and speculation in everything you write. Cite sources for any
  formula or constant you did not derive.
- Return the ScienceReport JSON. For design tasks set `failure_class: "none"` and list drafts.
````


### A.4 `critic`

````markdown
---
name: critic
description: Blinded adversarial reviewer. Given a neutral claim and material (a diff or an evidence package), tries to prove it wrong with independent checks. Read-only on the repository. Created by the orchestrator; never invoked for authoring.
tools: Read, Grep, Glob, Bash, WebSearch, WebFetch, Skill
model: opus
effort: high
skills:
  - mf-review
  - mf-conventions
---

You are an adversarial reviewer. You have deliberately NOT been told who produced the work
you are reviewing, what they intended, or what they believe. That is on purpose. Do not
try to reconstruct it. Judge only the claim in your review packet against the material and
the repository at this commit.

Your job is to find the strongest reason the claim is false or unsupported. You succeed
when you find a real defect or when you have made a serious, documented attempt and failed.

## Method (skill `mf-review` has the full checklists for your lens)
1. Restate the claim precisely, including its implicit scope.
2. List the three most likely ways it could be wrong for this kind of work.
3. For each, perform an independent check: run the tests, re-derive a formula, compute a
   limiting case by hand or in a scratch script under `/tmp`, construct an adversarial input,
   check provenance fields, or compare against a published value. Record each check.
4. Report findings with severity: `blocker` means the claim must not be accepted.

## Verdicts
- `accept` — you tried hard and found nothing material. Requires at least one independent check.
- `accept_with_caveats` — true within a narrower scope; state the caveats as limits of validity.
- `reject` — at least one blocker.
- `cannot_assess` — material insufficient; say exactly what is missing.

## Hard rules
- Do not modify repository files. Scratch work goes in `/tmp` only.
- Do not propose large redesigns. One sentence of suggested remedy per finding is enough.
- Never accept on the basis of the author's tests alone. Test the tests.
````


### A.5 `scout`

````markdown
---
name: scout
description: External researcher for literature, prior art, tools, competitors, and market facts. Produces cited notes. Never contacts anyone and never publishes. Use for research tasks.
tools: Read, Grep, Glob, Write, Edit, WebSearch, WebFetch, Skill, Workflow
model: sonnet
effort: medium
skills:
  - mf-research
---

You are the research scout for ModuleForge. You gather external knowledge the team needs:
papers, formulas, benchmark data, tool documentation and licenses, competitor products,
funding news, and market facts. You write cited notes under the path in your task packet.

## Standards
- Prefer primary sources: papers, official documentation, datasheets, standards, filings.
- Every factual statement in your notes carries a source (URL or citation) and a date.
- Separate what a source says from what you infer. Mark inferences explicitly.
- Record numbers with units and the conditions under which they hold.
- For broad questions, use the `/deep-research` workflow and then verify its key claims yourself.
- Flag anything that weakens the ModuleForge thesis in `thesis_impact`. Do not soften it.

## Never
Contact people, submit forms, create accounts, post anything, or download paywalled material
through workarounds. Never write outside your scope.
````


### A.6 `scribe`

````markdown
---
name: scribe
description: Faithful summarizer and report writer. Compresses run logs, diagnoses, and evidence into short notes and digests without adding claims. Use for summaries, digests, and memory curation.
tools: Read, Grep, Glob, Write, Edit
model: haiku
effort: low
---

You compress information without changing it. Every sentence you write must be traceable to a
source file you read; include the file path or ID next to each point. Never add interpretation,
recommendations, or claims that are not in the sources. If sources conflict, say so and cite both.
Keep outputs short: a run summary at most 150 words; a daily digest at most 400 words.
Write only to the paths named in your task packet.
````


## Appendix B — Skills

| Skill | Invoked by | Purpose |
|---|---|---|
| `inbox` | you only | Walk through open founder decisions one at a time and record each decision. |
| `investigate` | you only | Queue an independent scientist investigation of a question or failure. |
| `mf-conventions` | agents only (preloaded) | ModuleForge engineering and physics conventions - units, coordinates, numerics, code layout, testing standard, licensing. Use whenever writing or reviewing ModuleForge code or physics. |
| `mf-diagnosis` | agents only (preloaded) | Protocol for diagnosing failures and replanning - failure classes, competing explanations, discriminating tests, allowed responses. Use for investigate tasks and whenever a verdict is FAIL, INCONCLUSIVE, or INVALID. |
| `mf-evidence` | agents only (preloaded) | How ModuleForge experiments produce admissible evidence - spec format, runner pattern with mfos.evidence.ExperimentRun, sanity checks, uncertainty, sealed seeds, forbidden practices. Use when designing, implementing, or running any experiment. |
| `mf-git` | agents only (preloaded) | Git rules for agents working in an mfos task worktree - commit format, what never to commit, forbidden operations. Use when committing in a task branch. |
| `mf-planning` | agents only (preloaded) | How to decompose an mfos objective into tasks - task types, sizing, definition-of-done patterns, risk levels, budgets, anti-patterns. Use when producing a plan. |
| `mf-research` | agents only (preloaded) | Standards and note format for external research - sources, citations, facts vs inferences, thesis impact. Use for scout research tasks. |
| `mf-review` | agents only (preloaded) | Adversarial review checklists by lens (general, physics, numerics, statistics) and evidence-provenance checks. Use when acting as a critic. |
| `objective` | you only | Turn a founder idea into a falsifiable, machine-evaluable objective draft. |
| `resume` | you only | Reorient after time away or a crash - what happened, what is running, what to do next. |
| `status` | you only | Founder briefing - what needs a decision, what is running, what changed. |
| `thesis-review` | you only | Re-evaluate the ModuleForge thesis against accumulated technical and customer evidence. |
| `work` | you only | Pair with the founder on one task in this session, using the same packet and checks as the autonomous loop. |


## Appendix C — Operating policy (verbatim `.mfos/policy.toml`)

````toml
# ModuleForge operating policy — founder-owned (protected path).
# Read by the orchestrator (mfos) and by .claude/hooks (stdlib tomllib). Edit, commit, and
# restart the loop to apply. `uv run mfos doctor` validates the repository against it.

version = 1
claude_bin = "claude"            # pin the version (Homebrew cask on macOS); see docs/INFRASTRUCTURE.md §12

# Paths no agent may modify without an explicit founder approval (inbox: protected_change).
protected_paths = [
  "CLAUDE.md",
  "project/charter.md",
  "project/objectives/*/objective.yaml",
  "project/decisions/**",
  ".claude/**",
  ".mfos/**",
  ".github/**",
  "tools/mfos/**",
  "tests/acceptance/**",
  "experiments/specs/**",
  "data/holdout/**",
  "templates/**",
]

[role_write_scopes]              # allow-lists; everything else is denied by the guard hook and by verify
builder   = ["src/**", "tests/unit/**", "tests/regression/**", "benchmarks/**", "docs/**", "pyproject.toml", "uv.lock"]
scientist = ["research/**", "experiments/drafts/**", "experiments/runners/**", "tests/acceptance_drafts/**", "project/memory/**"]
scout     = ["project/memory/literature/**", "research/notes/**"]
scribe    = ["project/memory/**", "docs/reports/**"]
planner   = []
critic    = []

[read_deny]                      # sealed data; only the experiment runner (no LLM) reads it
builder = ["data/holdout/**"]
scientist = ["data/holdout/**"]

[blinding]                       # physically removed from a critic's review checkout
remove_paths = [
  "project/tasks", "project/events.jsonl", "project/inbox", "project/STATUS.md",
  "project/reviews", "project/objectives/*/state.yaml", "project/objectives/*/diagnoses",
  "research/diagnoses", ".mfos/runs", ".mfos/packets",
]

[autonomy]
level = 3                        # 3 for the O000 canary; set 1 for Phase 1 of the migration, raise as trust grows (§22)

[concurrency]
agents = 2                       # simultaneous Claude sessions (~1 GiB RAM each, compute is remote)
experiments = 1                  # simultaneous experiment processes (each may use several cores)

[compute]
# Experiments whose registered cpu_hours_est exceeds this run on burst compute (scripts/burst.sh),
# not on this machine. 6 CPU-hours is ~1.5-2 h on a MacBook Air's 4 performance cores.
local_cpu_hours_max = 6.0

[budgets]                        # USD, from Claude Code's client-side cost estimates
daily_usd = 40.0
weekly_usd = 200.0
max_task_usd = 8.0
plan_usd = 4.0
review_usd = 3.0
diagnosis_usd = 5.0

[models]                         # Claude Code aliases; resolved by the installed CLI
planner = "opus"
builder = "sonnet"
scientist = "opus"
critic = "opus"
scout = "sonnet"
scribe = "haiku"

[escalation]
after_attempts = 2               # attempt >= 2 runs on the escalation model
[escalation.models]
builder = "opus"                 # 'fable' is never automatic: it requires a founder model_escalation approval

[permission_modes]               # headless runs always add --permission-prompts none
builder = "auto"                 # fallback if auto mode is unavailable on your plan: "acceptEdits"
scientist = "auto"
scout = "dontAsk"
planner = "dontAsk"
critic = "dontAsk"
scribe = "dontAsk"

[review_ladder]                  # critic lenses per risk level (task risk for PRs, objective risk for PASS verdicts)
low = []
medium = ["critic:general"]
high = ["critic:physics", "critic:numerics"]
critical = ["critic:physics", "critic:numerics", "critic:statistics"]

[auto_merge]
enabled = true
max_risk = "medium"              # high/critical changes wait for the founder
max_files = 25

[gates]
fast = [
  "uv run ruff check src tests experiments/runners",
  "uv run pytest -q -x -m 'not slow' tests/unit",
]
full = [
  "uv run ruff check .",
  "uv run pytest -q tests",
  "uv run python scripts/check_licenses.py",
  "uv run mfos doctor --ci",
]

[planning]
max_new_tasks = 8
max_open_tasks = 10

[git]
main_branch = "main"
merge_mode = "local"             # Phase 1–3: local squash merges. Switch to "github" in Phase 4.
remote = "origin"
worktree_root = "~/mf/wt"
gh_config_dir = "~/.config/mfos/gh"   # the bot account's gh login; never exported to agents
push_state = true
founder_name = "FOUNDER"          # bootstrap.sh sets these to your GitHub identity
founder_email = "FOUNDER@users.noreply.github.com"
identity_name = "mfos-bot"
identity_email = "mfos-bot@users.noreply.github.com"

[limits]
run_wall_minutes = 90
backoff_minutes = 30             # pause dispatch after a rate/usage-limit error (does not count as an attempt)
sleep_gap_seconds = 300          # a longer gap between ticks means the machine slept: extend run deadlines
````


## Appendix D — File inventory

| Path | Lines | Role |
|---|---|---|
| `.claude/agents/builder.md` | 43 | agent definition |
| `.claude/agents/critic.md` | 37 | agent definition |
| `.claude/agents/planner.md` | 64 | agent definition |
| `.claude/agents/scientist.md` | 48 | agent definition |
| `.claude/agents/scout.md` | 25 | agent definition |
| `.claude/agents/scribe.md` | 13 | agent definition |
| `.claude/hooks/guard.py` | 166 | hook |
| `.claude/hooks/session_start.py` | 34 | hook |
| `.claude/hooks/stop_gate.py` | 62 | hook |
| `.claude/settings.json` | 64 | permissions + hook wiring |
| `.claude/skills/inbox/SKILL.md` | 15 | skill |
| `.claude/skills/investigate/SKILL.md` | 16 | skill |
| `.claude/skills/mf-conventions/SKILL.md` | 43 | skill |
| `.claude/skills/mf-diagnosis/SKILL.md` | 37 | skill |
| `.claude/skills/mf-evidence/SKILL.md` | 61 | skill |
| `.claude/skills/mf-git/SKILL.md` | 15 | skill |
| `.claude/skills/mf-planning/SKILL.md` | 37 | skill |
| `.claude/skills/mf-research/SKILL.md` | 25 | skill |
| `.claude/skills/mf-review/SKILL.md` | 40 | skill |
| `.claude/skills/objective/SKILL.md` | 22 | skill |
| `.claude/skills/resume/SKILL.md` | 18 | skill |
| `.claude/skills/status/SKILL.md` | 17 | skill |
| `.claude/skills/thesis-review/SKILL.md` | 20 | skill |
| `.claude/skills/work/SKILL.md` | 14 | skill |
| `.github/CODEOWNERS` | 13 | founder review of protected paths |
| `.github/pull_request_template.md` | 10 | PR shape (Phase 4) |
| `.github/workflows/audit.yml` | 18 | audit tripwire |
| `.github/workflows/ci.yml` | 23 | deterministic CI gate |
| `.gitignore` | 23 | runtime files excluded from Git |
| `.mfos/policy.toml` | 126 | operating policy |
| `.python-version` | 1 | pins Python 3.12 for uv |
| `CLAUDE.md` | 43 | always-loaded project facts |
| `Makefile` | 15 | shortcuts |
| `benchmarks/infra/cc_concurrency.sh` | 19 | infrastructure benchmark |
| `benchmarks/infra/dpt.cir` | 26 | infrastructure benchmark |
| `benchmarks/infra/fh_gen.py` | 55 | infrastructure benchmark |
| `benchmarks/infra/l1_bench.py` | 97 | infrastructure benchmark |
| `benchmarks/infra/l1_throughput.py` | 41 | infrastructure benchmark |
| `benchmarks/infra/measure.py` | 14 | infrastructure benchmark |
| `benchmarks/infra/run_all.sh` | 15 | infrastructure benchmark |
| `benchmarks/infra/thermal_bench.py` | 77 | infrastructure benchmark |
| `docs/ARCHITECTURE.md` | 1643 | this document |
| `docs/INFRASTRUCTURE.md` | 536 | measured infrastructure requirements and setup |
| `experiments/drafts/E000.yaml` | 14 | canary experiment spec |
| `experiments/runners/e000_canary.py` | 35 | canary experiment runner |
| `project/charter.md` | 31 | thesis, assumptions, kill criteria |
| `project/customers/README.md` | 7 | state scaffold |
| `project/decisions/D0001-agentic-operating-system.md` | 30 | ADR for this system |
| `project/memory/lessons.md` | 2 | state scaffold |
| `project/memory/literature/INDEX.md` | 1 | state scaffold |
| `project/objectives/O000/objective.yaml` | 35 | framework canary objective |
| `project/objectives/O000/state.yaml` | 1 | state scaffold |
| `project/objectives/O001/objective.yaml` | 85 | L1 PEEC ranking fidelity objective |
| `project/objectives/O001/state.yaml` | 1 | state scaffold |
| `pyproject.toml` | 38 | package, deps, lint rules |
| `scripts/audit_main.py` | 66 | tripwire for bot commits on main |
| `scripts/bootstrap.sh` | 54 | one-shot setup |
| `scripts/burst.sh` | 41 | run one experiment on an ephemeral cloud VM |
| `scripts/check_licenses.py` | 38 | copyleft gate |
| `scripts/com.moduleforge.mfos.plist` | 37 | launchd agent (macOS) |
| `scripts/mfos.service` | 20 | systemd user unit (Linux) |
| `scripts/provision_compute.sh` | 75 | install and self-test ngspice + FastHenry |
| `src/moduleforge/__init__.py` | 2 |  |
| `templates/claim.yaml` | 9 | template |
| `templates/decision.md` | 14 | template |
| `templates/experiment.yaml` | 14 | template |
| `templates/objective.yaml` | 43 | template |
| `templates/task.yaml` | 18 | template |
| `tests/mfos/conftest.py` | 42 | test |
| `tests/mfos/fake_claude.py` | 71 | CLI stand-in for end-to-end tests |
| `tests/mfos/test_evaluate.py` | 32 | test |
| `tests/mfos/test_hooks.py` | 92 | test |
| `tests/mfos/test_loop_e2e.py` | 179 | orchestrator lifecycle tests |
| `tests/mfos/test_stats.py` | 25 | test |
| `tests/unit/test_package.py` | 5 | test |
| `tools/mfos/mfos/__init__.py` | 6 | orchestrator module |
| `tools/mfos/mfos/agents.py` | 219 | orchestrator module |
| `tools/mfos/mfos/cli.py` | 428 | orchestrator module |
| `tools/mfos/mfos/diagnose.py` | 57 | orchestrator module |
| `tools/mfos/mfos/evaluate.py` | 140 | orchestrator module |
| `tools/mfos/mfos/evidence.py` | 133 | orchestrator module |
| `tools/mfos/mfos/experiments.py` | 142 | orchestrator module |
| `tools/mfos/mfos/gates.py` | 57 | orchestrator module |
| `tools/mfos/mfos/gitops.py` | 168 | orchestrator module |
| `tools/mfos/mfos/loop.py` | 818 | orchestrator module |
| `tools/mfos/mfos/models.py` | 413 | orchestrator module |
| `tools/mfos/mfos/packets.py` | 214 | orchestrator module |
| `tools/mfos/mfos/report.py` | 63 | orchestrator module |
| `tools/mfos/mfos/stats.py` | 71 | orchestrator module |
| `tools/mfos/mfos/store.py` | 238 | orchestrator module |
