"""The orchestrator. A deliberately boring, restartable state machine.

Every tick:
  1. poll agent runs and experiment processes (recovers after restarts)
  2. advance each task through  todo -> running -> verify -> review -> merge -> done
  3. per objective: gate on deps/budget, invoke the planner when a replan is due,
     evaluate when new admissible evidence exists, route verdicts
  4. dispatch ready tasks within concurrency and budget limits
  5. commit project state, write STATUS.md

All decisions that matter are deterministic code. Agents only produce proposals,
code, notes, and structured reports that this loop validates.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import fnmatch
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from . import diagnose, evaluate, experiments, gates, models as m, packets, report
from .agents import AgentRunner, RunRecord
from .gitops import GitOps
from .store import Store, now

TERMINAL = {"done", "cancelled", "failed", "needs_founder"}
OBJ_IDLE = {"draft", "passed", "failed", "abandoned", "superseded", "needs_founder"}
# The account, not the agent, ran out of capacity: back off without using an attempt. "session limit", "weekly
# limit" and "limit reached" are the Claude Code CLI's plan-limit messages (O001 critics, 2026-09-30).
CAPACITY_SIGNS = ("rate limit", "usage limit", "session limit", "weekly limit", "limit reached", "overloaded",
                  "429", "529", "quota")


def acquire_loop_lock(store: Store) -> Optional[Any]:
    """Take the single-orchestrator lock; None if a loop already holds it. Keep the handle open while running.

    Anything that polls runs and advances tasks (the loop, `mfos run`, `mfos loop --once`) must hold it: two
    orchestrators polling the same finished run would both bill, verify and merge it."""
    store.mfos.mkdir(exist_ok=True)
    fh = open(store.mfos / "loop.lock", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


class Orchestrator:
    def __init__(self, store: Optional[Store] = None):
        self.s = store or Store()
        self.git = GitOps(self.s)
        self.runner = AgentRunner(self.s)
        self.pol = self.s.policy
        # 1 = plan only (founder triggers execution) · 2 = execute, founder approves every merge
        # 3 = autonomous within policy. See docs/ARCHITECTURE.md §22.
        self.level = int(self.pol.get("autonomy", {}).get("level", 3))

    # ================================================================== loop
    def run_forever(self, poll_s: int = 30, max_cycles: Optional[int] = None) -> None:
        lock = acquire_loop_lock(self.s)  # held until this process exits
        if lock is None:
            print("another orchestrator loop is already running", file=sys.stderr)
            return
        stray = self.unexpected_changes()
        if stray:
            msg = "orchestrator checkout has non-state changes; resolve before starting: " + ", ".join(stray[:10])
            print(msg, file=sys.stderr)
            self.s.event("loop_refused", reason=msg)
            return
        self.s.event("loop_started", pid=os.getpid())
        n, errors = 0, 0
        while max_cycles is None or n < max_cycles:
            try:
                summary = self.tick()
                errors = 0
            except Exception as e:  # never crash-loop under systemd; stop cleanly after repeated failures
                errors += 1
                (self.s.mfos / "last_error").write_text(f"{now()} {type(e).__name__}: {e}")
                self.s.event("tick_error", error=f"{type(e).__name__}: {e}"[:500], consecutive=errors)
                if errors >= 3:
                    (self.s.mfos / "STOP").write_text(f"halted after repeated errors: {e}")
                    try:
                        self.s.add_inbox(kind="decision", subject="orchestrator halted after 3 consecutive errors",
                                         summary=f"{type(e).__name__}: {e}. See .mfos/last_error; fix, then `mfos start`.")
                    except Exception:
                        pass
                    break
                time.sleep(poll_s)
                continue
            n += 1
            if summary.get("stopped"):
                self.s.event("loop_stopped", reason="STOP file")
                break
            if summary.get("idle") and max_cycles is not None:
                break
            time.sleep(poll_s)

    def tick(self) -> dict[str, Any]:
        if self.s.stop_requested():
            return {"stopped": True}
        self._account_for_sleep()
        (self.s.mfos / "heartbeat").write_text(now())
        self.git.sync_main()
        self._poll_runs()
        self._poll_experiments()
        self._poll_burst()
        for t in self.s.tasks():
            self._advance(t)
        for oid in self.s.objective_ids():
            self._objective(oid)
        started = self._dispatch()
        report.write_status(self.s)
        self._commit_state("tick")
        busy = any(t.status in ("running", "verify", "review", "merge") for t in self.s.tasks())
        return {"started": started, "idle": not busy and started == 0}

    STATE_PATHS = ("project/", "experiments/specs/", "experiments/results/", "experiments/drafts/")

    def unexpected_changes(self) -> list[str]:
        out = self.s.git("status", "--porcelain", check=False).splitlines()
        # Store.git strips the output, so the first line may have lost the leading space of " M path":
        # split off the status code instead of slicing a fixed width.
        paths = [line.split(None, 1)[1] for line in out if line.strip()]
        return [p for p in paths if not p.startswith(self.STATE_PATHS)]

    def _account_for_sleep(self) -> None:
        """A laptop that slept shows a wall-clock gap between ticks. Extend running deadlines by it."""
        wall = time.time()
        last = getattr(self, "_last_tick_wall", None)
        self._last_tick_wall = wall
        if last is None:
            return
        gap = wall - last
        if gap > float(self.pol.get("limits", {}).get("sleep_gap_seconds", 300)):
            n = self.runner.extend_deadlines(gap)
            self.s.event("sleep_detected", gap_s=round(gap), runs_extended=n)

    def _needs_burst(self, t: m.Task) -> Optional[float]:
        """CPU-hours estimate if this experiment should run on burst compute instead of this machine."""
        limit = float(self.pol.get("compute", {}).get("local_cpu_hours_max", 1e9))
        spec_path = self.s.root / "experiments" / "specs" / f"{t.experiment}.yaml"
        if not spec_path.exists():
            return None
        est = float(self.s.read_yaml(spec_path, m.ExperimentSpec).cpu_hours_est or 0)
        return est if est > limit else None

    def _request_burst(self, t: m.Task, est: float) -> None:
        t.status = "needs_founder"
        t.history.append({"outcome": "awaiting_burst", "summary": f"~{est:g} CPU-h exceeds local limit",
                          "at": now(), "since": time.time()})
        self.s.save_task(t)
        self.s.add_inbox(kind="decision", subject=f"{t.experiment} needs burst compute (~{est:g} CPU-h)",
                         summary=f"Run it on an ephemeral VM: `scripts/burst.sh {t.experiment}`. Results copied back "
                                 f"into experiments/results/ are picked up automatically (provenance records the host). "
                                 f"To run it here instead: `uv run mfos exp run {t.experiment}`.",
                         refs=[t.id, t.experiment or ""])
        self.s.event("burst_requested", task=t.id, experiment=t.experiment, cpu_hours=est)

    def _poll_burst(self) -> None:
        """Close experiment tasks whose results arrived from elsewhere (burst VM or a manual local run)."""
        for t in self.s.tasks():
            if t.type != "experiment" or t.status != "needs_founder":
                continue
            marks = [h for h in t.history if h.get("outcome") == "awaiting_burst"]
            if not marks:
                continue
            since = float(marks[-1].get("since", 0))
            fresh = [r for r in self.s.results(t.experiment or "") if r.status == "complete" and r.provenance.finished
                     and dt.datetime.fromisoformat(r.provenance.finished).timestamp() >= since - 1]
            if not fresh:
                continue
            r = fresh[-1]
            ok = all(s.passed for s in r.sanity)
            t.status = "done" if ok else "todo"
            t.history.append({"outcome": "experiment_complete" if ok else "sanity_failed",
                              "summary": f"{r.run_id} on {r.provenance.host}"})
            self.s.save_task(t)
            for item in self.s.inbox("open"):
                if t.id in item.refs and "burst compute" in item.subject:
                    item.status, item.response, item.resolved_at = "answered", f"result {r.run_id} arrived", now()
                    self.s.save_inbox(item)
            if not ok:
                self._fail(t, "sanity_failed", f"sanity checks failed in {r.run_id}",
                           json.dumps([s.model_dump() for s in r.sanity if not s.passed], indent=1))

    def _backoff_active(self) -> bool:
        p = self.s.mfos / "backoff_until"
        return p.exists() and time.time() < float(p.read_text() or 0)

    # ================================================================== runs
    def _task_for_run(self, rec: RunRecord) -> Optional[m.Task]:
        p = self.s.task_path(rec.task_id)
        return self.s.task(rec.task_id) if p.exists() else None

    def _poll_runs(self) -> None:
        for rec in self.runner.active():
            rec = self.runner.poll(rec)
            if rec.status == "running":
                continue
            t = self._task_for_run(rec)
            if t is None:
                continue
            self._add_cost(t, rec.cost_usd)
            self._on_run_done(t, rec)

    def _add_cost(self, t: m.Task, usd: float) -> None:
        st = self.s.objective_state(t.objective)
        st.spent_usd = round(st.spent_usd + usd, 4)
        self.s.save_objective_state(t.objective, st)

    def _on_run_done(self, t: m.Task, rec: RunRecord) -> None:
        if rec.status in ("interrupted", "timeout"):
            resumes = sum(1 for h in t.history if h.get("outcome") == "resumed")
            if rec.status == "interrupted" and resumes < 1:
                t.history.append({"attempt": t.attempts, "outcome": "resumed", "summary": rec.run_id})
                self.s.save_task(t)
                self._start_agent(t, resume=rec.session_id)
                return
            self._fail(t, "agent_error", f"run {rec.status}", rec.result_text)
            return
        if rec.status == "error":
            text = (rec.result_text + " " + rec.subtype).lower()
            if any(k in text for k in CAPACITY_SIGNS):
                minutes = int(self.pol.get("limits", {}).get("backoff_minutes", 30))
                (self.s.mfos / "backoff_until").write_text(str(time.time() + 60 * minutes))
                t.attempts = max(0, t.attempts - 1)  # capacity problems are not the agent's failure
                t.status = "todo"
                t.history.append({"outcome": "capacity_backoff", "summary": rec.result_text[-300:], "at": now()})
                self.s.save_task(t)
                self.s.event("capacity_backoff", task=t.id, minutes=minutes)
                return
            if rec.subtype in ("error_max_turns", "error_max_budget_usd") and t.type not in ("plan", "review"):
                wt = self.git.wt_root / t.id
                if wt.exists():
                    self.git.commit_all(wt, f"[{t.id}] WIP: attempt {t.attempts} stopped at {rec.subtype}")
            self._fail(t, "agent_error", f"agent ended with {rec.subtype}", rec.result_text)
            return
        out = rec.structured_output or {}
        if not out and t.type in ("plan", "review"):
            # Say so plainly: validating {} reads like a bad plan, not a missing one (O000, 2026-09-28).
            self._fail(t, "agent_error", f"{t.agent} returned no structured report (run {rec.run_id}); "
                       "check that its tools: allow-list includes StructuredOutput", rec.result_text)
            return
        handler = {
            "plan": self._on_plan, "review": self._on_review,
        }.get(t.type, self._on_work)
        handler(t, rec, out)

    # ------------------------------------------------------------------ planner
    def _on_plan(self, t: m.Task, rec: RunRecord, out: dict[str, Any]) -> None:
        try:
            plan = m.PlanOutput.model_validate(out)
        except Exception as e:
            self._fail(t, "agent_error", "planner returned invalid plan", str(e))
            return
        oid = t.objective
        obj = self.s.objective(oid)
        st = self.s.objective_state(oid)
        limits = self.pol.get("planning", {})
        open_now = [x for x in self.s.tasks(oid) if x.status not in TERMINAL and x.type != "plan"]
        room = max(0, min(limits.get("max_new_tasks", 8), limits.get("max_open_tasks", 10) - len(open_now)))
        idmap: dict[str, str] = {}
        created: list[str] = []
        # Bug fix: replans is incremented when the plan task is created, so test the trigger instead.
        approval = obj.require_plan_approval and (t.trigger == "initial" or self.level < 3)
        for spec in plan.create_tasks[:room]:
            tid = self.s.new_task_id()
            idmap[spec.local_id] = tid
            task = m.Task(
                id=tid, objective=oid, title=spec.title, type=spec.type, agent=spec.agent,
                status="proposed" if approval else "todo",
                depends_on=[idmap.get(d, d) for d in spec.depends_on], description=spec.description,
                context_files=spec.context_files, deliverables=spec.deliverables, touches=spec.touches,
                definition_of_done=spec.definition_of_done, experiment=spec.experiment,
                risk=spec.risk, budget_usd=min(spec.budget_usd, self.pol.get("budgets", {}).get("max_task_usd", 8.0)),
                max_turns=spec.max_turns, created_by=f"planner:{t.id}", created_at=now(), rationale=spec.rationale,
            )
            if task.type == "experiment":
                task.agent = "none"
            self.s.save_task(task)
            created.append(tid)
        dropped = len(plan.create_tasks) - len(created)
        for c in plan.cancel_tasks:
            if self.s.task_path(c.id).exists():
                x = self.s.task(c.id)
                if x.status not in TERMINAL and x.objective == oid:
                    x.status = "cancelled"
                    x.history.append({"outcome": "cancelled", "summary": c.reason})
                    self.s.save_task(x)
        for fr in plan.founder_requests:
            self.s.add_inbox(kind=fr.kind, subject=f"[{oid}] {fr.subject}", summary=fr.summary,
                             options=fr.options, recommendation=fr.recommendation, refs=[oid, t.id])
        if approval and created:
            self.s.add_inbox(kind="plan_approval", subject=f"[{oid}] approve initial plan ({len(created)} tasks)",
                             summary=plan.assessment, refs=[oid, *created],
                             options=["approve", "reject (with note for the planner)"])
        st.needs_replan = False
        self.s.save_objective_state(oid, st)
        t.status = "done"
        t.history.append({"outcome": "planned", "summary": plan.assessment[:800], "created": created,
                          "dropped_for_limits": dropped})
        self.s.save_task(t)
        self.s.event("plan_applied", objective=oid, created=created, dropped=dropped)

    # ------------------------------------------------------------------ review
    def _on_review(self, t: m.Task, rec: RunRecord, out: dict[str, Any]) -> None:
        try:
            rv = m.Review.model_validate(out)
        except Exception as e:
            self._fail(t, "agent_error", "critic returned invalid review", str(e))
            return
        if rv.verdict in ("accept", "accept_with_caveats") and not rv.independent_checks_performed:
            rv.verdict = "cannot_assess"
            rv.caveats.append("downgraded: acceptance without any independent check is not admissible")
        path = self.s.project / "reviews" / (t.target or "unknown") / f"{t.id}.json"
        self.s.write_json(path, rv)
        t.status = "done"
        t.history.append({"outcome": f"review:{rv.verdict}", "summary": f"{len(rv.findings)} findings"})
        self.s.save_task(t)
        self.git.remove_worktree(self.git.wt_root / f"review-{t.id}")

    # ------------------------------------------------------------------ work tasks
    def _on_work(self, t: m.Task, rec: RunRecord, out: dict[str, Any]) -> None:
        path = self.git.task_worktree(t)
        self.git.commit_all(path, f"[{t.id}] {t.title} (attempt {t.attempts})")
        t.status = "verify"
        t.history.append({"attempt": t.attempts, "outcome": "agent_finished",
                          "summary": str(out.get("summary", ""))[:800], "report": out})
        self.s.save_task(t)
        self._verify(t, path, out)

    def _verify(self, t: m.Task, path: Path, out: dict[str, Any]) -> None:
        files = self.git.changed_files(path)
        bad = self.git.scope_violations(t.agent, files, t.protected_approved)
        if bad:
            self._fail(t, "scope_violation", "edited files outside its write scope", "\n".join(bad))
            return
        if t.agent == "builder" and not files:
            self._fail(t, "dod_failed", "no changes were produced", "")
            return
        if out.get("status") == "blocked":
            self._fail(t, "attempts_exhausted" if t.attempts >= t.max_attempts else "dod_failed",
                       "agent reported blocked", str(out.get("summary", ""))[:2000])
            return
        results = gates.run_dod(self.s, t, path)
        if t.type == "design_experiment":
            for eid in out.get("experiment_drafts", []) or ([t.experiment] if t.experiment else []):
                eid = Path(eid).stem
                sub = Store(path)
                for prob in experiments.validate_draft(sub, eid):
                    results.append(gates.CheckResult(f"draft:{eid}", False, prob))
        ok, text = gates.summarize(results)
        if not ok:
            self._fail(t, "dod_failed", "definition of done not met", text)
            return
        self.s.event("verified", task=t.id)
        lenses = self._review_lenses(t)
        if lenses:
            head = self.git.head(path)
            for lens in lenses:
                self._create_review(t.objective, target=t.id, lens=lens, ref=head)
            t.status = "review"
        else:
            t.status = "merge"
        self.s.save_task(t)

    def _review_lenses(self, t: m.Task) -> list[str]:
        ladder = self.pol.get("review_ladder", {})
        risk = t.risk
        if t.type == "design_experiment" and risk == "low":
            risk = "medium"  # experiment designs always get at least one adversarial read
        return [x.split(":", 1)[1] for x in ladder.get(risk, []) if x.startswith("critic:")]

    def _create_review(self, oid: str, target: str, lens: str, ref: str) -> m.Task:
        tid = self.s.new_task_id()
        rt = m.Task(id=tid, objective=oid, title=f"Review {target} ({lens})", type="review", agent="critic",
                    status="todo", target=target, lens=lens, description=ref, risk="low",
                    budget_usd=self.pol.get("budgets", {}).get("review_usd", 3.0), max_turns=60,
                    created_by="orchestrator", created_at=now())
        self.s.save_task(rt)
        return rt

    def _reviews_for(self, target: str, ref: Optional[str] = None) -> tuple[list[m.Task], list[m.Review]]:
        """Review tasks for ``target`` and their verdicts; with ``ref``, only those that reviewed that commit."""
        tasks = [x for x in self.s.tasks() if x.type == "review" and x.target == target
                 and (ref is None or x.description == ref)]
        revs = []
        for x in tasks:
            p = self.s.project / "reviews" / target / f"{x.id}.json"
            if p.exists():
                revs.append(m.Review.model_validate_json(p.read_text()))
        return tasks, revs

    # ================================================================== task advancement
    def _advance(self, t: m.Task) -> None:
        if t.status == "review":
            # A task is judged only by the reviews of the commit it would merge: a retry must not be rejected by
            # an earlier attempt's critic, nor merged on an earlier attempt's acceptance (T0037, 2026-09-30).
            head = self.git.head(self.git.wt_root / t.id)
            rtasks, revs = self._reviews_for(t.id, ref=head)
            if not rtasks:
                for lens in self._review_lenses(t):
                    self._create_review(t.objective, target=t.id, lens=lens, ref=head)
                if self._review_lenses(t):
                    return
            if any(x.status not in TERMINAL for x in rtasks):
                return
            if any(x.status == "failed" for x in rtasks) and len(revs) < len(rtasks):
                t.status = "needs_founder"
                self.s.save_task(t)
                self.s.add_inbox(kind="decision", subject=f"{t.id}: review could not be completed",
                                 summary="A critic run failed; decide whether to merge without it.", refs=[t.id])
                return
            rejects = [r for r in revs if r.verdict in ("reject", "cannot_assess")]
            if rejects:
                findings = "\n".join(f"- [{f.severity}] {f.title}: {f.detail}" for r in rejects for f in r.findings)
                self._fail(t, "review_rejected", "adversarial review rejected the work", findings)
                return
            t.status = "merge"
            self.s.save_task(t)
        if t.status == "merge":
            self._merge(t)

    def _merge(self, t: m.Task) -> None:
        path = self.git.task_worktree(t)
        files = self.git.changed_files(path)
        pol_auto = self.pol.get("auto_merge", {})
        risk_rank = ["low", "medium", "high", "critical"]
        protected = self.git.scope_violations("founder", files, approved_protected=False)
        auto = t.protected_approved or (
            self.level >= 3
            and pol_auto.get("enabled", True)
            and risk_rank.index(t.risk) <= risk_rank.index(pol_auto.get("max_risk", "medium"))
            and len(files) <= pol_auto.get("max_files", 25)
            and not protected)
        if t.pr and self.git.mode == "github":
            state = self.git.pr_state(t.pr)
        else:
            self._commit_state(f"before merging {t.id}")
            body = f"Task {t.id} for {t.objective}\n\n{t.description[:3000]}\n\nDefinition of done verified by mfos."
            state, pr = self.git.integrate(t, path, body, auto)
            t.pr = pr
        if state == "merged":
            t.status = "done"
            self.s.save_task(t)
            self.s.event("merged", task=t.id)
            self._post_merge(t)
            self.git.remove_worktree(path)
        elif state == "conflict":
            self._fail(t, "dod_failed", "merge conflict with main",
                       "Bring the branch up to date with main and resolve conflicts.\n" + self.git.last_error)
        elif state == "error":
            t.status = "needs_founder"
            self.s.save_task(t)
            self.s.add_inbox(kind="decision", subject=f"{t.id}: integration failed (infrastructure, not the agent)",
                             summary=self.git.last_error[-1500:], refs=[t.id],
                             options=["fix the environment, then `mfos task retry " + t.id + "`"])
        elif state == "needs_founder":
            t.status = "needs_founder"
            self.s.save_task(t)
            self.s.add_inbox(kind="protected_change", subject=f"{t.id}: merge needs founder approval",
                             summary=f"{t.title}\nRisk {t.risk}; {len(files)} files. PR: {t.pr}", refs=[t.id])
        else:
            self.s.save_task(t)

    def _post_merge(self, t: m.Task) -> None:
        if t.type == "design_experiment":
            last = next((h for h in reversed(t.history) if h.get("outcome") == "agent_finished"), {})
            drafts = [Path(x).stem for x in (last.get("report") or {}).get("experiment_drafts", [])] or \
                     ([t.experiment] if t.experiment else [])
            for eid in drafts:
                self.s.add_inbox(kind="experiment_registration", subject=f"register {eid} (pre-registration)",
                                 summary=f"Designed by {t.id}. Reviewed by critic. Registering freezes the design.",
                                 refs=[eid, t.id, t.objective], options=["approve", "reject with note"])
        if t.type == "investigate":
            last = next((h for h in reversed(t.history) if h.get("outcome") == "agent_finished"), {})
            self.s.write_json(self.s.objective_dir(t.objective) / "diagnoses" / f"{t.id}.json", last.get("report", {}))
            st = self.s.objective_state(t.objective)
            st.needs_replan = True
            self.s.save_objective_state(t.objective, st)

    # ------------------------------------------------------------------ failure routing
    def _fail(self, t: m.Task, signal: str, summary: str, output: str) -> None:
        t.history.append({"attempt": t.attempts, "outcome": signal, "summary": summary,
                          "failure_output": output[-4000:], "at": now()})
        resp = diagnose.respond(signal, t.attempts, t.max_attempts)
        self.s.event("task_failed_attempt", task=t.id, signal=signal, action=resp.action)
        if resp.action == "repair" and t.type not in ("plan", "review"):
            t.status = "todo"
        elif t.type in ("plan", "review") and t.attempts < t.max_attempts:
            t.status = "todo"
        elif resp.action in ("diagnose", "fix_experiment") and t.type != "investigate":
            t.status = "failed"
            self._spawn_investigation(t, resp.failure_class, summary, output)
        else:
            t.status = "needs_founder"
            self.s.add_inbox(kind="decision", subject=f"{t.id} stuck: {summary}",
                             summary=f"Class: {resp.failure_class}. {resp.note}\n\n{output[-1500:]}",
                             refs=[t.id, t.objective], options=["re-scope", "cancel", "give guidance"])
        self.s.save_task(t)

    def _spawn_investigation(self, t: m.Task, cls: str, summary: str, output: str,
                             st: Optional[m.ObjectiveState] = None) -> None:
        """Queue an independent scientist diagnosis. If the caller holds the objective state,
        pass it in (the caller saves it) so no stale copy can overwrite this log entry."""
        tid = self.s.new_task_id()
        inv = m.Task(
            id=tid, objective=t.objective, title=f"Diagnose failure of {t.id}", type="investigate",
            agent="scientist", status="todo", risk="medium",
            description=(f"Task {t.id} ('{t.title}') failed with preliminary class `{cls}`: {summary}.\n"
                         f"Failure output (tail):\n```\n{output[-2500:]}\n```\n"
                         "Determine the true failure class and root cause. Follow skill mf-diagnosis: list at least "
                         "two alternative explanations, design a discriminating test, run it if cheap, and write "
                         f"your notes to research/diagnoses/{tid}.md."),
            deliverables=[f"research/diagnoses/{tid}.md"], touches=[f"research/diagnoses/{tid}.md"],
            budget_usd=self.pol.get("budgets", {}).get("diagnosis_usd", 5.0),
            created_by="orchestrator", created_at=now(),
            context_files=[f"project/objectives/{t.objective}/evaluations/{t.id}.json" if t.id.startswith("EV-")
                           else f"project/tasks/{t.id}.yaml"],
        )
        self.s.save_task(inv)
        line = f"diagnosis:{tid} of {t.id} ({cls})"
        if st is not None:
            st.log.append(line)
        else:
            fresh = self.s.objective_state(t.objective)
            fresh.log.append(line)
            self.s.save_objective_state(t.objective, fresh)
        self.s.event("investigation_spawned", task=tid, about=t.id, cls=cls)

    # ================================================================== experiments
    def _exp_record(self, tid: str) -> Path:
        return self.s.mfos / "exp_runs" / f"{tid}.json"

    def _start_experiment(self, t: m.Task) -> None:
        rec_path = self._exp_record(t.id)
        rec_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.s.mfos / "exp_runs" / f"{t.id}.log", "w")
        env = {**os.environ, "MFOS_ROOT": str(self.s.root)}
        proc = subprocess.Popen([sys.executable, "-m", "mfos.cli", "exp", "run", t.experiment or "", "--force"],
                                cwd=self.s.root, stdout=log, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
        t.attempts += 1
        t.status = "running"
        rec_path.write_text(json.dumps({"pid": proc.pid, "started": time.time(), "task": t.id}))
        self.s.save_task(t)
        self.s.event("experiment_task_started", task=t.id, experiment=t.experiment)

    def _poll_experiments(self) -> None:
        d = self.s.mfos / "exp_runs"
        if not d.exists():
            return
        for p in d.glob("*.json"):
            rec = json.loads(p.read_text())
            if AgentRunner._alive(rec["pid"]):
                continue
            t = self.s.task(rec["task"])
            p.unlink()
            fresh = [r for r in self.s.results(t.experiment or "")
                     if r.provenance.finished and
                     dt.datetime.fromisoformat(r.provenance.finished).timestamp() >= rec["started"] - 1]
            if not fresh:
                self._fail(t, "experiment_error", "experiment produced no result",
                           (self.s.mfos / "exp_runs" / f"{t.id}.log").read_text()[-3000:])
                continue
            r = fresh[-1]
            if r.status == "complete" and all(s.passed for s in r.sanity):
                t.status = "done"
                t.history.append({"attempt": t.attempts, "outcome": "experiment_complete", "summary": r.run_id})
                self.s.save_task(t)
            elif r.status == "complete":
                self._fail(t, "sanity_failed", f"sanity checks failed in {r.run_id}",
                           json.dumps([s.model_dump() for s in r.sanity if not s.passed], indent=1))
            else:
                self._fail(t, "experiment_error", f"{r.run_id} status={r.status}", r.notes[-3000:])

    # ================================================================== objectives
    def _objective(self, oid: str) -> None:
        obj = self.s.objective(oid)
        st = self.s.objective_state(oid)
        if st.status in OBJ_IDLE:
            return
        for dep in obj.depends_on:
            if self.s.objective_state(dep).status != "passed":
                if st.status != "blocked":
                    st.status = "blocked"
                    self.s.save_objective_state(oid, st)
                return
        if st.status == "blocked":
            st.status = "active"
        cap = st.budget_override_usd or obj.budget.usd
        if st.spent_usd > cap:
            st.status = "needs_founder"
            self.s.save_objective_state(oid, st)
            self.s.add_inbox(kind="budget_increase", subject=f"[{oid}] budget exhausted (${st.spent_usd:.2f}/${cap:.2f})",
                             summary="Objective paused. Raise the budget, re-scope, or abandon.", refs=[oid])
            return
        if st.status == "evaluating":
            self._finish_evaluation_review(oid, obj, st)
            return
        tasks = self.s.tasks(oid)
        planning = any(t.type == "plan" and t.status not in TERMINAL for t in tasks)
        awaiting = any(t.status == "proposed" for t in tasks)
        if st.needs_replan and not planning and not awaiting:
            if st.replans > st.max_replans:
                st.status = "needs_founder"
                self.s.add_inbox(kind="decision", subject=f"[{oid}] replan limit reached",
                                 summary="The objective has been replanned too many times without resolution.",
                                 refs=[oid])
            else:
                trigger = "initial" if st.replans == 0 and not tasks else (st.log[-1] if st.log else "periodic")
                self._create_plan_task(oid, trigger)
                st.replans += 1
            self.s.save_objective_state(oid, st)
            return
        self._maybe_evaluate(oid, obj, st)

    def _create_plan_task(self, oid: str, trigger: str) -> None:
        tid = self.s.new_task_id()
        pt = m.Task(id=tid, objective=oid, title=f"Plan {oid} ({trigger})", type="plan", agent="planner",
                    status="todo", trigger=trigger, risk="low",
                    budget_usd=self.pol.get("budgets", {}).get("plan_usd", 4.0), max_turns=40,
                    created_by="orchestrator", created_at=now())
        self.s.save_task(pt)

    def _maybe_evaluate(self, oid: str, obj: m.Objective, st: m.ObjectiveState) -> None:
        latest: dict[str, str] = {}
        for eid in obj.acceptance.required_experiments:
            runs = [r for r in self.s.results(eid) if r.status == "complete"]
            if not runs:
                return
            latest[eid] = runs[-1].run_id
        if latest == st.evaluated_runs:
            return
        if len(st.evaluations) >= obj.acceptance.max_evaluations:
            st.status = "needs_founder"
            self.s.save_objective_state(oid, st)
            self.s.add_inbox(kind="decision", subject=f"[{oid}] evaluation budget exhausted",
                             summary="Further evaluations risk p-hacking. Decide: accept current evidence, "
                                     "reformulate, or abandon.", refs=[oid])
            return
        ev = evaluate.evaluate(self.s, oid)
        st = self.s.objective_state(oid)
        st.evaluated_runs = latest
        if ev.verdict == "PASS":
            lenses = [x.split(":", 1)[1] for x in self.pol.get("review_ladder", {}).get(obj.risk, [])
                      if x.startswith("critic:")]
            if lenses:
                for lens in lenses:
                    self._create_review(oid, target=ev.id, lens=lens, ref=self.git.head())
                st.status, st.pending_evaluation = "evaluating", ev.id
            else:
                self._objective_passed(oid, obj, st, ev.id, [])
        elif ev.verdict == "INVALID":
            st.log.append(f"verdict:INVALID {ev.id}")
            self._spawn_investigation(self._pseudo(oid, ev.id), "experimental", "evidence inadmissible",
                                      "\n".join(ev.validity_problems), st=st)
        else:  # FAIL or INCONCLUSIVE
            st.log.append(f"verdict:{ev.verdict} {ev.id}")
            cls = "model" if ev.verdict == "FAIL" else "experimental"
            self._spawn_investigation(self._pseudo(oid, ev.id), cls, f"objective verdict {ev.verdict}",
                                      ev.model_dump_json(indent=1), st=st)
            self._create_review(oid, target=ev.id, lens="statistics", ref=self.git.head())
        self.s.save_objective_state(oid, st)

    def _pseudo(self, oid: str, ev_id: str) -> m.Task:
        return m.Task(id=ev_id, objective=oid, title=f"evaluation {ev_id}", type="experiment", agent="none")

    def _finish_evaluation_review(self, oid: str, obj: m.Objective, st: m.ObjectiveState) -> None:
        target = st.pending_evaluation or ""
        rtasks, revs = self._reviews_for(target)
        if any(x.status not in TERMINAL for x in rtasks):
            return
        bad = [r for r in revs if r.verdict in ("reject", "cannot_assess")]
        if bad or len(revs) < len(rtasks):
            st.status = "needs_founder"
            self.s.save_objective_state(oid, st)
            self.s.add_inbox(kind="decision", subject=f"[{oid}] PASS verdict disputed by review",
                             summary="The deterministic evaluation passed but a blinded critic rejected the evidence. "
                                     f"See project/reviews/{target}/.", refs=[oid, target])
            return
        caveats = [c for r in revs for c in r.caveats]
        self._objective_passed(oid, obj, st, target, caveats)

    def _objective_passed(self, oid: str, obj: m.Objective, st: m.ObjectiveState, ev_id: str,
                          caveats: list[str]) -> None:
        st.status = "passed"
        st.pending_evaluation = None
        self.s.save_objective_state(oid, st)
        self.s.add_claim(statement=obj.hypothesis.statement, scope="; ".join(obj.scope_in) or "as stated",
                         status="supported", objective=oid, evaluation=ev_id,
                         reviews=[x.id for x in self._reviews_for(ev_id)[0]], caveats=caveats)
        self._commit_state(f"{oid} passed ({ev_id})")
        self.s.git("tag", "-f", "-a", f"{oid}-passed", "-m", f"{oid} passed: {ev_id}", check=False)
        self.s.event("objective_passed", objective=oid, evaluation=ev_id)
        for t in self.s.tasks(oid):
            if t.status in ("todo", "proposed"):
                t.status = "cancelled"
                t.history.append({"outcome": "cancelled", "summary": "objective passed"})
                self.s.save_task(t)

    # ================================================================== dispatch
    def _blockers(self, t: m.Task, running: list[m.Task]) -> list[str]:
        """Why ``t`` cannot be dispatched now; empty when it can. Shared by dispatch and `mfos task start`."""
        why = []
        if t.status != "todo":
            why.append(f"status is {t.status}, not todo")
        waiting = [d for d in t.depends_on if not self.s.task_path(d).exists() or self.s.task(d).status != "done"]
        if waiting:
            why.append("waiting on " + ", ".join(waiting))
        ost = self.s.objective_state(t.objective).status
        if ost not in ("active", "evaluating"):
            why.append(f"objective {t.objective} is {ost}")
        if self._conflicts(t, running):
            why.append("touches overlap a running task")
        return why

    def _conflicts(self, t: m.Task, running: list[m.Task]) -> bool:
        for r in running:
            for a in t.touches:
                for b in r.touches:
                    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a) or a == b:
                        return True
        return False

    def _budget_ok(self, t: m.Task) -> bool:
        b = self.pol.get("budgets", {})
        today = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        spent = self.runner.spent_since(today)
        if spent + t.budget_usd > b.get("daily_usd", 40.0):
            if not (self.s.mfos / "budget_notice").exists():
                self.s.add_inbox(kind="budget_increase", subject="daily LLM budget reached",
                                 summary=f"Spent ${spent:.2f} today. Work resumes tomorrow unless the cap is raised.")
                (self.s.mfos / "budget_notice").write_text(now())
            return False
        return True

    def start_task(self, tid: str) -> list[str]:
        """Start one agent task now with dispatch's checks: the founder's trigger at level 1 (`mfos task start`).

        Returns why it was not started (empty: started). Safe while the loop runs: it only starts the run, under
        the dispatch lock; the loop then polls, verifies, reviews and merges it like any other."""
        with self.s.lock("dispatch"):
            t = self.s.task(tid)
            if t.agent == "none":
                return [f"{t.type} tasks are dispatched by the loop itself"]
            running = [x for x in self.s.tasks() if x.status == "running"]
            why = self._blockers(t, running)
            if sum(1 for x in running if x.agent != "none") >= self.pol.get("concurrency", {}).get("agents", 2):
                why.append("all agent slots are busy (policy concurrency.agents)")
            if self._backoff_active():
                why.append("capacity backoff is active (.mfos/backoff_until)")
            if self.s.stop_requested():
                why.append("a stop is requested (`mfos start` clears it)")
            if not why and not self._budget_ok(t):
                why.append("the daily LLM budget is reached")
            if not why:
                self._start_agent(t)
            return why

    def _dispatch(self) -> int:
        with self.s.lock("dispatch"):  # serializes with `mfos task start`
            return self._dispatch_locked()

    def _dispatch_locked(self) -> int:
        if self._backoff_active():
            return 0
        conc = self.pol.get("concurrency", {})
        tasks = self.s.tasks()
        running = [t for t in tasks if t.status == "running"]
        n_agents = sum(1 for t in running if t.agent != "none")
        n_exps = sum(1 for t in running if t.agent == "none")
        prio = {oid: self.s.objective(oid).priority for oid in self.s.objective_ids()}
        ready = [t for t in tasks if not self._blockers(t, running)]
        ready.sort(key=lambda t: (prio.get(t.objective, 9), t.type != "plan", t.type != "review", t.id))
        started = 0
        for t in ready:
            if t.agent == "none" and t.type == "experiment":
                est = self._needs_burst(t)
                if est is not None:
                    self._request_burst(t, est)
                    continue
                if n_exps < conc.get("experiments", 1):
                    self._start_experiment(t)
                    n_exps += 1
                    started += 1
                continue
            resuming = bool(t.history) and t.history[-1].get("outcome") == "capacity_backoff"
            if self.level < 2 and t.type not in ("plan", "review") and not resuming:
                continue  # level 1: the founder triggers execution (`mfos task start <task>` or /work); a task the
                # founder started resumes after a capacity pause without a second trigger
            if n_agents >= conc.get("agents", 2) or not self._budget_ok(t):
                continue
            self._start_agent(t)
            running.append(t)
            n_agents += 1
            started += 1
        return started

    def _start_agent(self, t: m.Task, resume: Optional[str] = None) -> None:
        role = t.agent
        if not resume:
            t.attempts += 1
        models = self.pol.get("models", {})
        model = t.model or models.get(role)
        esc = self.pol.get("escalation", {})
        if t.attempts >= esc.get("after_attempts", 2) and role in esc.get("models", {}):
            model = esc["models"][role]
        run_key = f"{t.id}-a{t.attempts}"
        settings = None
        if t.type == "plan":
            cwd = self.s.root
            rel = packets.plan_packet(self.s, t.objective, cwd, run_key, t.trigger or "periodic")
        elif t.type == "review":
            cwd = self.git.review_checkout(f"review-{t.id}", t.description or self.git.main)
            claim, material = self._review_material(t, cwd)
            rel = packets.review_packet(self.s, cwd, run_key, claim, material, t.lens or "general")
            # The blinded snapshot is a fresh repository, which Claude Code does not trust, so it ignores the
            # snapshot's project settings. Pass the orchestrator's own permissions and hooks explicitly.
            settings = self.s.root / ".claude" / "settings.json"
        else:
            cwd = self.git.task_worktree(t)
            rel = packets.work_packet(self.s, t, cwd, run_key)
        rec = self.runner.start(task=t, role=role, cwd=cwd, packet_rel=rel, schema=packets.schema_for(role),
                                budget_usd=t.budget_usd, max_turns=t.max_turns, model=model, resume_session=resume,
                                settings_file=settings)
        t.status = "running"
        t.runs.append(rec.run_id)
        self.s.save_task(t)

    def _review_material(self, rt: m.Task, cwd: Path) -> tuple[str, str]:
        target = rt.target or ""
        if target.startswith("EV-"):
            oid = rt.objective
            obj = self.s.objective(oid)
            ev = (self.s.objective_dir(oid) / "evaluations" / f"{target}.json").read_text()
            specs = "\n\n".join((self.s.root / "experiments" / "specs" / f"{e}.yaml").read_text()
                                for e in obj.acceptance.required_experiments
                                if (self.s.root / "experiments" / "specs" / f"{e}.yaml").exists())
            claim = f"The evidence below supports: \"{obj.hypothesis.statement}\" within scope {obj.scope_in}."
            return claim, f"### Evaluation\n```json\n{ev}\n```\n### Registered experiment specs\n```yaml\n{specs}\n```\n" \
                          "Result files are under experiments/results/. Runner code is in the repository at this commit."
        t = self.s.task(target)
        wt = self.git.wt_root / t.id
        diff = self.git.diff(wt) if wt.exists() else "(diff unavailable)"
        claim = (f"This change correctly and completely implements: \"{t.title}\". "
                 f"Deliverables: {t.deliverables}. It must satisfy: "
                 + "; ".join(d.cmd or d.exists or "" for d in t.definition_of_done))
        return claim, f"```diff\n{diff}\n```"

    # ================================================================== state commits
    def _commit_state(self, why: str) -> None:
        paths = ["project", "experiments/specs", "experiments/results", "experiments/drafts"]
        existing = [p for p in paths if (self.s.root / p).exists()]
        if not existing:
            return
        founder_owned = [":(exclude,glob)project/objectives/*/objective.yaml", ":(exclude)project/charter.md",
                         ":(exclude)project/decisions", ":(exclude)project/customers"]
        self.s.git("add", "-A", "--", *existing, *founder_owned, check=False)
        staged = self.s.git("diff", "--cached", "--name-only", check=False).split()
        if not staged:
            return
        if staged == ["project/STATUS.md"]:  # a fresher timestamp alone is not worth a commit
            self.s.git("reset", "-q", "--", "project/STATUS.md", check=False)
            return
        self.s.git("commit", "-q", "-m", f"chore(state): {why}", check=False)
        self._push()

    def _push(self) -> None:
        """Publish main (merges, state, tags) in every mode. The forge box is main's single writer."""
        if not self.pol.get("git", {}).get("push_state", True):
            return
        if not self.s.git("remote", "get-url", self.git.remote, check=False).strip():
            return
        r = subprocess.run(["git", "push", "-q", "--follow-tags", self.git.remote, self.git.main],
                           cwd=self.s.root, env=self.git.gh_env, capture_output=True, text=True)
        notice = self.s.mfos / "push_diverged"
        if r.returncode != 0 and ("rejected" in r.stderr or "non-fast-forward" in r.stderr):
            if not notice.exists():
                notice.write_text(now())
                self.s.add_inbox(kind="decision", subject="GitHub main has commits the forge box does not",
                                 summary="Someone pushed to main from elsewhere. In ~/mf/main run "
                                         "`git pull --rebase` (state files never conflict with founder files), "
                                         "then `rm .mfos/push_diverged`.", refs=[])
        elif r.returncode == 0:
            notice.unlink(missing_ok=True)
