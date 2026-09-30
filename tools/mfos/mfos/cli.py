"""mfos — the ModuleForge operating system CLI.

Founder commands:  status, inbox, approve, reject, answer, objective, loop, stop, start, costs, report
Agent/CI commands: gate, exp check, doctor
Level-1 trigger:   task start (start one task; the running loop finishes it)
Migration helpers: packet (render a task packet to paste into Claude Code), run (one task, synchronously,
                   only while no loop runs)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
from pathlib import Path

import yaml

from . import evaluate, experiments, gates, models as m, packets, report
from .store import Store, now


def _store() -> Store:
    return Store()


# ------------------------------------------------------------------ objectives
def cmd_objective(a: argparse.Namespace) -> int:
    s = _store()
    if a.action == "new":
        d = s.objective_dir(a.id)
        if d.exists():
            print(f"{a.id} already exists", file=sys.stderr)
            return 1
        d.mkdir(parents=True)
        tpl = (s.root / "templates" / "objective.yaml").read_text().replace("OXXX", a.id)
        (d / "objective.yaml").write_text(tpl)
        s.save_objective_state(a.id, m.ObjectiveState(status="draft"))
        print(f"created {d/'objective.yaml'} — edit it, then: mfos objective approve {a.id}")
        return 0
    if a.action == "approve":
        obj = s.objective(a.id)  # validates schema
        st = s.objective_state(a.id)
        st.status, st.approved_by, st.approved_at = "active", "founder", now()
        st.criteria_hash = s.criteria_hash(obj)
        st.needs_replan = True
        s.save_objective_state(a.id, st)
        s.event("objective_approved", actor="founder", objective=a.id, criteria_hash=st.criteria_hash)
        d = s.objective_dir(a.id).relative_to(s.root)
        s.git("add", "--", str(d / "objective.yaml"), str(d / "state.yaml"), check=False)
        s.git("commit", "-q", "-m", f"Approve {a.id}: freeze hypothesis and acceptance criteria",
              "-m", f"criteria_hash: {st.criteria_hash}", check=False, as_founder=True)
        print(f"{a.id} approved and frozen ({st.criteria_hash[:19]}…)")
        return 0
    if a.action == "show":
        print(yaml.safe_dump(s.objective(a.id).model_dump(mode="json"), sort_keys=False))
        print(yaml.safe_dump(s.objective_state(a.id).model_dump(mode="json"), sort_keys=False))
        return 0
    if a.action == "pause":
        st = s.objective_state(a.id)
        st.status = "needs_founder"
        s.save_objective_state(a.id, st)
        return 0
    if a.action == "resume":
        st = s.objective_state(a.id)
        st.status = "active"
        s.save_objective_state(a.id, st)
        return 0
    return 1


# ------------------------------------------------------------------ inbox
def _resolve(s: Store, iid: str, status: str, note: str) -> int:
    p = s.project / "inbox" / f"{iid}.yaml"
    item = s.read_yaml(p, m.InboxItem)
    if item.status != "open":
        print(f"{iid} is already {item.status}")
        return 1
    item.status, item.response, item.resolved_at = status, note, now()
    approved = status == "approved"
    if item.kind == "objective_approval" and approved:
        cmd_objective(argparse.Namespace(action="approve", id=item.refs[0]))
    elif item.kind == "plan_approval":
        oid, tids = item.refs[0], item.refs[1:]
        for tid in tids:
            t = s.task(tid)
            if t.status == "proposed":
                t.status = "todo" if approved else "cancelled"
                s.save_task(t)
        if not approved:
            st = s.objective_state(oid)
            st.needs_replan = True
            st.log.append(f"founder rejected plan: {note}")
            s.save_objective_state(oid, st)
    elif item.kind == "experiment_registration" and approved:
        experiments.register(s, item.refs[0], by="founder")
    elif item.kind == "protected_change" and approved:
        t = s.task(item.refs[0])
        t.protected_approved = True
        t.approval = iid
        t.status = "merge"
        s.save_task(t)
    elif item.kind == "budget_increase" and approved:
        for ref in item.refs:
            if ref.startswith("O"):
                st = s.objective_state(ref)
                extra = float(note.split("=", 1)[1]) if note.startswith("usd=") else 25.0
                st.budget_override_usd = st.spent_usd + extra
                st.status = "active"
                s.save_objective_state(ref, st)
        (s.mfos / "budget_notice").unlink(missing_ok=True)
    elif item.kind in ("decision", "question", "thesis_change", "criteria_change", "model_escalation"):
        for ref in item.refs:
            if ref.startswith("O") and (s.objective_dir(ref) / "objective.yaml").exists():
                st = s.objective_state(ref)
                st.log.append(f"founder {status} {iid}: {note}")
                st.needs_replan = True
                if st.status == "needs_founder" and approved:
                    st.status = "active"
                s.save_objective_state(ref, st)
    s.save_inbox(item)
    s.event("inbox_resolved", actor="founder", id=iid, status=status, note=note)
    print(f"{iid} {status}")
    return 0


def cmd_inbox(a: argparse.Namespace) -> int:
    s = _store()
    if a.action in (None, "list"):
        for i in s.inbox("open"):
            print(f"{i.id}  [{i.kind}]  {i.subject}")
        return 0
    if a.action == "show":
        print(yaml.safe_dump(s.read_yaml(s.project / "inbox" / f"{a.id}.yaml", m.InboxItem).model_dump(), sort_keys=False))
        return 0
    return 1


def cmd_approve(a: argparse.Namespace) -> int:
    return _resolve(_store(), a.id, "approved", a.note or "")


def cmd_reject(a: argparse.Namespace) -> int:
    return _resolve(_store(), a.id, "rejected", a.note)


def cmd_answer(a: argparse.Namespace) -> int:
    return _resolve(_store(), a.id, "answered", a.text)


# ------------------------------------------------------------------ tasks
def cmd_task(a: argparse.Namespace) -> int:
    s = _store()
    if a.action == "add":
        if not (a.objective and a.title and a.type):
            print("task add needs --objective, --type, --title", file=sys.stderr)
            return 1
        tid = s.new_task_id()
        t = m.Task(id=tid, objective=a.objective, title=a.title, type=a.type, agent=a.agent or "scientist",
                   description=a.description or "", status="todo", risk=a.risk or "medium",
                   created_by="founder", created_at=now(),
                   deliverables=[f"research/diagnoses/{tid}.md"] if a.type == "investigate" else [])
        s.save_task(t)
        s.event("task_added", actor="founder", task=tid)
        print(tid)
        return 0
    if a.action == "list":
        for t in s.tasks(a.objective):
            if a.status and t.status != a.status:
                continue
            print(f"{t.id} {t.status:13s} {t.agent:9s} {t.type:18s} {t.title}")
        return 0
    t = s.task(a.id)
    if a.action == "show":
        print(yaml.safe_dump(t.model_dump(mode="json"), sort_keys=False))
    elif a.action == "start":
        from .loop import Orchestrator
        why = Orchestrator(s).start_task(t.id)
        if why:
            print(f"{t.id} not started: " + "; ".join(why), file=sys.stderr)
            return 1
        print(f"{t.id} started; the loop verifies, reviews and merges it")
    elif a.action == "retry":
        t.status, t.max_attempts = "todo", max(t.max_attempts, t.attempts + 1)
        s.save_task(t)
    elif a.action == "cancel":
        t.status = "cancelled"
        s.save_task(t)
    return 0


def cmd_packet(a: argparse.Namespace) -> int:
    """Phase-1/2 migration helper: render the packet and the one-line prompt to paste into Claude Code."""
    s = _store()
    t = s.task(a.id)
    rel = packets.work_packet(s, t, s.root, f"{t.id}-manual")
    print(f"Packet written to {rel}\n\nPaste into Claude Code (or run `claude --agent {t.agent}`):\n")
    print(f"Read `{rel}` and complete task {t.id} exactly as specified. When done, run every definition-of-done "
          "command, fix failures, and report the commands and exit codes.")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    """Run the orchestrator until one task leaves the pipeline (Phase 3 helper; only while no loop runs)."""
    from .loop import Orchestrator, acquire_loop_lock
    s = _store()
    lock = acquire_loop_lock(s)  # held until return
    if lock is None:
        print(f"the orchestrator loop is running; use `mfos task start {a.id}` and the loop finishes the task",
              file=sys.stderr)
        return 1
    o = Orchestrator(s)
    t = s.task(a.id)
    if t.status in ("todo", "proposed"):
        t.status = "todo"
        s.save_task(t)
        if t.agent == "none":
            o._start_experiment(t)
        else:
            o._start_agent(t)
    while True:
        o._poll_runs()
        o._poll_experiments()
        o._advance(s.task(a.id))
        for x in s.tasks():  # reviews spawned for this task
            if x.type == "review" and x.target == a.id and x.status == "todo":
                o._start_agent(x)
            elif x.type == "review" and x.target == a.id:
                o._advance(x)
        cur = s.task(a.id)
        if cur.status in ("done", "failed", "cancelled", "needs_founder") or \
                (cur.status == "todo" and cur.attempts >= cur.max_attempts):
            print(f"{cur.id}: {cur.status}")
            return 0 if cur.status == "done" else 2
        if cur.status == "todo":
            o._start_agent(cur)
        time.sleep(a.poll)


# ------------------------------------------------------------------ experiments / evaluation
def cmd_exp(a: argparse.Namespace) -> int:
    s = _store()
    if a.action == "register":
        spec = experiments.register(s, a.id, by="founder")
        # Leave the same auditable trail as an inbox approval (checked by scripts/audit_main.py).
        item = s.add_inbox(kind="experiment_registration", subject=f"register {a.id} (direct, via CLI)",
                           summary=f"Registered directly by the founder. spec_hash={spec.spec_hash}", refs=[a.id])
        item.status, item.response, item.resolved_at = "approved", "registered via mfos exp register", now()
        s.save_inbox(item)
        print(f"registered {a.id} {spec.spec_hash}")
    elif a.action == "run":
        res = experiments.run(s, a.id, force=a.force, here=a.here)
        print(json.dumps({"run": res.run_id, "status": res.status,
                          "metrics": {k: v.model_dump() for k, v in res.metrics.items()}}, indent=2))
        return 0 if res.status == "complete" else 3
    elif a.action == "check":
        probs = experiments.validate_draft(s, a.id)
        for p in probs:
            print("PROBLEM:", p)
        return 1 if probs else 0
    return 0


def cmd_evaluate(a: argparse.Namespace) -> int:
    ev = evaluate.evaluate(_store(), a.id, record=not a.dry_run)
    print(ev.model_dump_json(indent=2))
    return 0


# ------------------------------------------------------------------ ops
def cmd_gate(a: argparse.Namespace) -> int:
    s = _store()
    res = gates.run_gate(s, Path.cwd(), "full" if a.full else "fast")
    ok, text = gates.summarize(res)
    print(text or "all gates passed")
    return 0 if ok else 1


def cmd_loop(a: argparse.Namespace) -> int:
    from .loop import Orchestrator, acquire_loop_lock
    o = Orchestrator()
    if a.once:
        lock = acquire_loop_lock(o.s)  # held until return
        if lock is None:
            print("the orchestrator loop is running; it already ticks", file=sys.stderr)
            return 1
        print(json.dumps(o.tick()))
        return 0
    o.run_forever(poll_s=a.poll, max_cycles=a.cycles)
    return 0


def cmd_stop(a: argparse.Namespace) -> int:
    s = _store()
    (s.mfos / "STOP").write_text(now())
    print("stop requested; running agents finish, nothing new starts")
    return 0


def cmd_start(a: argparse.Namespace) -> int:
    s = _store()
    (s.mfos / "STOP").unlink(missing_ok=True)
    (s.project / "STOP").unlink(missing_ok=True)
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    print(report.write_status(_store()))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    print(report.evidence_package(_store(), a.id))
    return 0


def cmd_costs(a: argparse.Namespace) -> int:
    s = _store()
    for oid in s.objective_ids():
        st = s.objective_state(oid)
        print(f"{oid}: ${st.spent_usd:.2f}")
    from .agents import AgentRunner
    today = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    print(f"today: ${AgentRunner(s).spent_since(today):.2f}")
    return 0


def cmd_doctor(a: argparse.Namespace) -> int:
    s = _store()
    problems: list[str] = []
    for oid in s.objective_ids():
        try:
            obj = s.objective(oid)
        except Exception as e:
            problems.append(f"{oid}: invalid objective.yaml: {e}")
            continue
        st = s.objective_state(oid)
        if st.criteria_hash and st.criteria_hash != s.criteria_hash(obj):
            problems.append(f"{oid}: acceptance criteria edited after approval — re-approve or revert")
    for p in sorted((s.root / "experiments" / "specs").glob("*.yaml")):
        spec = s.read_yaml(p, m.ExperimentSpec)
        if spec.status == "registered" and spec.spec_hash != s.spec_hash(spec):
            problems.append(f"{spec.id}: registered spec modified after registration")
        elif spec.status == "registered" and experiments.runner_changes(s.root, spec):
            problems.append(f"{spec.id}: runner changed after registration: {experiments.runner_changes(s.root, spec)}")
    try:
        s.tasks()  # every task file is schema-validated on load
    except Exception as e:
        problems.append(f"invalid task file: {e}")
    if not a.ci:
        from .loop import Orchestrator
        stray = Orchestrator(s).unexpected_changes()
        if stray:
            problems.append("orchestrator checkout has non-state changes: " + ", ".join(stray[:10]))
    free_gb = shutil.disk_usage(s.root).free / 1e9
    if free_gb < 20 and not a.ci:
        problems.append(f"only {free_gb:.0f} GB free disk: prune artifacts and caches (docs/INFRASTRUCTURE.md §9)")
    for p in sorted((s.root / ".claude" / "agents").glob("*.md")):
        tools = next((x for x in p.read_text().splitlines() if x.startswith("tools:")), None)
        if tools is not None and "StructuredOutput" not in tools.split(":", 1)[1].replace(",", " ").split():
            problems.append(f"{p.relative_to(s.root)}: tools: allow-list omits StructuredOutput, "
                            "so the agent never sees the --json-schema report format")
    claude_md = s.root / "CLAUDE.md"
    if claude_md.exists() and len(claude_md.read_text().splitlines()) > 200:
        problems.append("CLAUDE.md exceeds 200 lines; move procedures into skills")
    if not a.ci:
        for tool in ("git", s.policy.get("claude_bin", "claude")):
            if shutil.which(tool) is None:
                problems.append(f"{tool} not found on PATH")
    for p in problems:
        print("PROBLEM:", p)
    print("doctor: ok" if not problems else f"doctor: {len(problems)} problem(s)")
    return 1 if problems else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mfos", description="ModuleForge operating system")
    sub = p.add_subparsers(dest="cmd", required=True)

    def cmd(name: str, fn, help_: str = "") -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    o = cmd("objective", cmd_objective, "create, approve (freeze), show, pause, resume an objective")
    o.add_argument("action", choices=["new", "approve", "show", "pause", "resume"])
    o.add_argument("id")

    i = cmd("inbox", cmd_inbox, "list or show founder decisions")
    i.add_argument("action", nargs="?", choices=["list", "show"])
    i.add_argument("id", nargs="?")
    ap = cmd("approve", cmd_approve, "approve an inbox item")
    ap.add_argument("id")
    ap.add_argument("--note")
    rj = cmd("reject", cmd_reject, "reject an inbox item")
    rj.add_argument("id")
    rj.add_argument("--note", required=True)
    an = cmd("answer", cmd_answer, "answer an inbox question")
    an.add_argument("id")
    an.add_argument("text")

    t = cmd("task", cmd_task, "add, list, show, start, retry, cancel tasks")
    t.add_argument("action", choices=["add", "list", "show", "start", "retry", "cancel"])
    t.add_argument("id", nargs="?")
    t.add_argument("--objective")
    t.add_argument("--status")
    t.add_argument("--type", choices=["implement", "investigate", "research", "docs", "design_experiment"])
    t.add_argument("--agent", choices=["builder", "scientist", "scout"])
    t.add_argument("--title")
    t.add_argument("--description")
    t.add_argument("--risk", choices=["low", "medium", "high", "critical"])
    pk = cmd("packet", cmd_packet, "render a task packet for manual use in Claude Code")
    pk.add_argument("id")
    rn = cmd("run", cmd_run, "run one task through the pipeline, synchronously")
    rn.add_argument("id")
    rn.add_argument("--poll", type=int, default=10)

    e = cmd("exp", cmd_exp, "register, run, or check experiments")
    e.add_argument("action", choices=["register", "run", "check"])
    e.add_argument("id")
    e.add_argument("--force", action="store_true")
    e.add_argument("--here", action="store_true", help="dev only: run in this checkout")
    ev = cmd("evaluate", cmd_evaluate, "evaluate an objective's acceptance criteria")
    ev.add_argument("id")
    ev.add_argument("--dry-run", action="store_true")

    g = cmd("gate", cmd_gate, "run quality gates")
    g.add_argument("--fast", action="store_true")
    g.add_argument("--full", action="store_true")
    lp = cmd("loop", cmd_loop, "run the orchestrator")
    lp.add_argument("--once", action="store_true")
    lp.add_argument("--cycles", type=int)
    lp.add_argument("--poll", type=int, default=30)
    cmd("stop", cmd_stop, "stop dispatching new work")
    cmd("start", cmd_start, "clear a stop request")
    cmd("status", cmd_status, "write and print STATUS.md")
    rp = cmd("report", cmd_report, "write an objective's evidence package")
    rp.add_argument("id")
    cmd("costs", cmd_costs, "spend by objective and today")
    dr = cmd("doctor", cmd_doctor, "check repository integrity")
    dr.add_argument("--ci", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
