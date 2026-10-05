"""Task packets: the complete, durable instruction set for one agent run.

A packet replaces the hand-written Claude Code prompt of the manual workflow. It is
written into the agent's working directory (gitignored .mfos/packets/) and kept, so
every run can be audited later: "what exactly was this agent told?".

Context discipline:
  * builders/scientists get the task, the objective's hypothesis and criteria,
    the relevant decisions, and summaries of previous failed attempts;
  * reviewers get a NEUTRAL claim or diff and nothing about who wrote it or why;
  * the planner gets the objective, the task table, and the latest evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import models as m
from .store import Store


def _yaml(obj) -> str:
    data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    return yaml.safe_dump(data, sort_keys=False, width=100).strip()


def _write(cwd: Path, run_key: str, text: str) -> str:
    rel = f".mfos/packets/{run_key}.md"
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return rel


def _scopes(store: Store, role: str) -> str:
    pol = store.policy
    allowed = pol.get("role_write_scopes", {}).get(role, [])
    prot = pol.get("protected_paths", [])
    return (f"- You may create/modify only: {', '.join(allowed) if allowed else 'NOTHING (read-only role)'}\n"
            f"- Never modify (protected, enforced by hooks and CI): {', '.join(prot)}")


def _objective_brief(store: Store, oid: str, with_thresholds: bool = True) -> str:
    o = store.objective(oid)
    lines = [f"**{o.id} — {o.title}**", f"Hypothesis: {o.hypothesis.statement}"]
    if with_thresholds:
        for c in o.acceptance.pass_all:
            lines.append(f"- pass criterion {c.id}: {c.metric} {c.comparator} {c.threshold} ({c.uncertainty.use})")
        for c in o.acceptance.fail_any:
            lines.append(f"- kill criterion {c.id}: {c.metric} {c.comparator} {c.threshold}")
    if o.scope_out:
        lines.append("Out of scope: " + "; ".join(o.scope_out))
    return "\n".join(lines)


def _history(t: m.Task) -> str:
    if not t.history:
        return "None. This is the first attempt."
    out = []
    for h in t.history[-3:]:
        out.append(f"- attempt {h.get('attempt')}: {h.get('outcome')} — {h.get('summary', '')[:600]}")
        if h.get("failure_output"):
            # All of it (at most 4000 characters as stored): a review lists its findings most severe first, and the
            # last 1500 characters held only T0074's minor findings, not its blocker.
            out.append("  ```\n  " + h["failure_output"].replace("\n", "\n  ") + "\n  ```")
    return "\n".join(out) + (
        "\nStart from a fresh look at the code. Do not repeat an approach that already failed "
        "unless you can say concretely why it will now work.")


def _dod(t: m.Task) -> str:
    if not t.definition_of_done:
        return "- (none declared) — the orchestrator will still run the fast gate: `mfos gate --fast`"
    rows = []
    for d in t.definition_of_done:
        rows.append(f"- `{d.cmd}` must exit 0" if d.cmd else f"- `{d.exists}` must exist")
    return "\n".join(rows) + "\n- plus the fast gate: `mfos gate --fast`"


def work_packet(store: Store, t: m.Task, cwd: Path, run_key: str) -> str:
    role = t.agent
    text = f"""# Task packet {t.id} — role: {role}

## Task
**{t.title}** (type: {t.type}, risk: {t.risk})

{t.description.strip()}

## Deliverables
{chr(10).join('- ' + d for d in t.deliverables) or '- (see task)'}

## Definition of done — the orchestrator re-runs these itself; your report is not trusted
{_dod(t)}

## Boundaries
{_scopes(store, role)}
- Work only in this checkout ({cwd.name}). Do not push, merge, open PRs, or touch other branches.
- If the task is impossible or mis-specified, stop and report `blocked` with evidence. Do not improvise scope.

## Objective context
{_objective_brief(store, t.objective)}

## Read these first
{chr(10).join('- ' + f for f in t.context_files) or '- CLAUDE.md, then whatever the task names'}

## Previous attempts
{_history(t)}

## Output
Return JSON matching the schema you were given. Report exactly which commands you ran and their exit codes.
"""
    if t.experiment:
        text += f"\n## Experiment\nThis task concerns experiment `{t.experiment}`. Follow skill `mf-evidence`.\n"
    dod = {"task": t.id, "checks": [d.model_dump() for d in t.definition_of_done],
           "deliverables": t.deliverables, "gate": store.policy.get("gates", {}).get("fast", [])}
    (cwd / ".mfos" / "packets").mkdir(parents=True, exist_ok=True)
    (cwd / ".mfos" / "packets" / f"{run_key}.dod.json").write_text(json.dumps(dod, indent=2))
    return _write(cwd, run_key, text)


def plan_packet(store: Store, oid: str, cwd: Path, run_key: str, trigger: str) -> str:
    o = store.objective(oid)
    st = store.objective_state(oid)
    tasks = store.tasks(oid)
    table = "\n".join(
        f"| {t.id} | {t.type} | {t.agent} | {t.status} | {','.join(t.depends_on)} | {t.title[:60]} |" for t in tasks
    ) or "| (none) |"
    evals = []
    for eid in st.evaluations[-2:]:
        p = store.objective_dir(oid) / "evaluations" / f"{eid}.json"
        if p.exists():
            evals.append(p.read_text()[:3000])
    diag = sorted((store.objective_dir(oid) / "diagnoses").glob("*.json"))[-2:] \
        if (store.objective_dir(oid) / "diagnoses").exists() else []
    specs = [p.stem for p in (store.root / "experiments" / "specs").glob("*.yaml")]
    drafts = [p.stem for p in (store.root / "experiments" / "drafts").glob("*.yaml")]
    limits = store.policy.get("planning", {})
    text = f"""# Planning packet — {oid} (trigger: {trigger})

## Objective (frozen; you may not change it)
```yaml
{_yaml(o)}
```

## Objective state
status={st.status} replans={st.replans}/{st.max_replans} evaluations={len(st.evaluations)} last_verdict={st.last_verdict} spent=${st.spent_usd:.2f}

## Current tasks
| id | type | agent | status | deps | title |
|---|---|---|---|---|---|
{table}

## Experiments
registered specs: {specs or 'none'}; drafts awaiting registration: {drafts or 'none'}

## Latest evaluations
{chr(10).join(evals) or 'none'}

## Latest diagnoses
{chr(10).join(p.read_text()[:3000] for p in diag) or 'none'}

## Planning limits
- at most {limits.get('max_new_tasks', 8)} new tasks per plan; at most {limits.get('max_open_tasks', 10)} open tasks per objective
- each task: one coherent deliverable, 20–120 agent-minutes, explicit definition_of_done commands
- every experiment named in acceptance.required_experiments needs: a design_experiment task (scientist) that drafts
  experiments/drafts/<EID>.yaml plus its runner, and later an `experiment` task (agent: none) with `experiment: <EID>`
- `experiment` tasks are run by the orchestrator, never by an agent
- budget remaining for this objective: ${max(0.0, (st.budget_override_usd or o.budget.usd) - st.spent_usd):.2f}

## Your job
{_trigger_instructions(trigger)}
"""
    return _write(cwd, run_key, text)


def _trigger_instructions(trigger: str) -> str:
    if trigger == "initial":
        return ("Produce the smallest task graph that generates the evidence the acceptance criteria require, "
                "including the infrastructure it depends on. Front-load the tasks that could kill the hypothesis cheaply.")
    if trigger.startswith("verdict:") or trigger.startswith("diagnosis:"):
        return ("An evaluation or diagnosis just landed. Decide the next steps from the evidence. For a FAIL or "
                "INCONCLUSIVE verdict, follow skill `mf-diagnosis`: prefer discriminating experiments over fixes, and "
                "never propose changing acceptance criteria yourself — raise a founder request instead.")
    if trigger.startswith("task_failed"):
        return ("A task exhausted its attempts. Read its history, decide whether to re-scope, split, replace, or cancel "
                "it, or whether this is a founder decision.")
    return "Review the objective and adjust the plan if needed. If nothing needs to change, return no tasks."


def review_packet(store: Store, cwd: Path, run_key: str, claim: str, material: str, lens: str) -> str:
    """Blinded: states a claim neutrally; contains no author, rationale, or history."""
    text = f"""# Review packet — lens: {lens}

You are reviewing work whose authorship and motivation are deliberately withheld.
Your job is to find reasons it is wrong. Follow skill `mf-review`.

## Claim under review
{claim}

## Material
{material}

## Output
Return JSON matching the Review schema. A verdict of `accept` with zero independent checks is invalid.
"""
    return _write(cwd, run_key, text)


def schema_for(role: str) -> dict:
    return m.ROLE_OUTPUT[role].model_json_schema()


def dump_json(obj) -> str:
    return json.dumps(obj, indent=2, default=str)
