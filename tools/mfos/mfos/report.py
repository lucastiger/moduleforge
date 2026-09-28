"""Human-readable state, generated only from files (never from agent narrative)."""
from __future__ import annotations

import json
from collections import Counter

from . import models as m
from .store import Store, now


def write_status(s: Store) -> str:
    lines = ["# ModuleForge status", f"_generated {now()} from repository state — do not edit_", ""]
    inbox = s.inbox("open")
    lines.append(f"## Founder inbox ({len(inbox)} open)")
    for i in inbox:
        lines.append(f"- **{i.id}** [{i.kind}] {i.subject}")
    if not inbox:
        lines.append("- nothing needs you")
    lines += ["", "## Objectives", "| id | status | verdict | evals | spent | title |", "|---|---|---|---|---|---|"]
    for oid in s.objective_ids():
        o, st = s.objective(oid), s.objective_state(oid)
        cap = st.budget_override_usd or o.budget.usd
        lines.append(f"| {oid} | {st.status} | {st.last_verdict or '-'} | {len(st.evaluations)}/"
                     f"{o.acceptance.max_evaluations} | ${st.spent_usd:.2f}/${cap:.0f} | {o.title} |")
    tasks = s.tasks()
    counts = Counter(t.status for t in tasks)
    lines += ["", "## Tasks", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none", ""]
    for t in tasks:
        if t.status in ("running", "verify", "review", "merge", "needs_founder", "proposed"):
            lines.append(f"- {t.id} `{t.status}` {t.agent}/{t.type}: {t.title} (attempt {t.attempts})")
    lines += ["", "## Recent events"]
    for e in s.events(15):
        extra = {k: v for k, v in e.items() if k not in ("ts", "event", "actor")}
        lines.append(f"- {e['ts']} {e['event']} {json.dumps(extra, default=str)[:160]}")
    text = "\n".join(lines) + "\n"
    (s.project / "STATUS.md").write_text(text)
    return text


def evidence_package(s: Store, oid: str) -> str:
    o, st = s.objective(oid), s.objective_state(oid)
    out = [f"# Evidence package — {oid}: {o.title}", "", f"**Hypothesis.** {o.hypothesis.statement}", "",
           f"**Status:** {st.status}  **Last verdict:** {st.last_verdict}  **Evaluations used:** "
           f"{len(st.evaluations)}/{o.acceptance.max_evaluations}", ""]
    for eid in st.evaluations:
        p = s.objective_dir(oid) / "evaluations" / f"{eid}.json"
        if not p.exists():
            continue
        ev = m.Evaluation.model_validate_json(p.read_text())
        out += [f"## {ev.id} — {ev.verdict}", ev.explanation, "",
                "| criterion | metric | value | bound | rule | verdict |", "|---|---|---|---|---|---|"]
        for c in ev.pass_checks + ev.fail_checks:
            out.append(f"| {c.id} | {c.metric} | {c.value} | {c.bound_used} | {c.comparator} {c.threshold} | {c.verdict} |")
        out += ["", "Results used: " + ", ".join(f"{k}={v}" for k, v in ev.results_used.items()), ""]
        rdir = s.project / "reviews" / ev.id
        for rp in sorted(rdir.glob("*.json")) if rdir.exists() else []:
            rv = m.Review.model_validate_json(rp.read_text())
            out.append(f"- review {rp.stem}: **{rv.verdict}**; checks: {'; '.join(rv.independent_checks_performed)[:300]}")
            for f in rv.findings:
                out.append(f"  - [{f.severity}] {f.title}")
    text = "\n".join(out) + "\n"
    (s.objective_dir(oid) / "EVIDENCE.md").write_text(text)
    return text
