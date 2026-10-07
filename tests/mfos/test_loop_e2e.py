"""End-to-end: the real orchestrator drives objective O000 from approval to a supported claim,
using a fake `claude` that behaves like the CLI (same flags, same JSON envelope)."""
import time

from mfos.cli import main as cli
from mfos.loop import Orchestrator
from mfos.store import Store


def drive(max_ticks=60):
    s = Store()
    o = Orchestrator(s)
    for _ in range(max_ticks):
        o.tick()
        if s.objective_state("O000").status in ("passed", "failed", "needs_founder"):
            break
        time.sleep(0.3)
    return s


def setup_objective():
    assert cli(["exp", "register", "E000"]) == 0  # exactly what the founder runs
    assert cli(["objective", "approve", "O000"]) == 0


def test_canary_objective_passes_end_to_end(sandbox):
    setup_objective()
    s = drive()
    st = s.objective_state("O000")
    assert st.status == "passed", st
    assert st.last_verdict == "PASS"
    claims = list((s.project / "claims").glob("C*.yaml"))
    assert claims, "a supported claim must be recorded"
    kinds = [e["event"] for e in s.events(500)]
    for k in ("objective_approved", "plan_applied", "run_started", "verified", "merged",
              "experiment_finished", "evaluation", "objective_passed"):
        assert k in kinds, k
    assert (sandbox / "src" / "moduleforge" / "canary.py").exists()  # merged into main
    assert "O000-passed" in s.git("tag")  # milestones are addressable
    dirty = [x for x in s.git("status", "--porcelain").splitlines() if not x.endswith("project/STATUS.md")]
    assert dirty == []  # all state committed (a timestamp-only STATUS.md refresh is deliberately not)


def test_repair_loop_recovers_from_a_wrong_first_attempt(sandbox, monkeypatch):
    monkeypatch.setenv("FAKE_BUILDER_FAIL_FIRST", "1")
    setup_objective()
    s = drive()
    assert s.objective_state("O000").status == "passed"
    builder = [t for t in s.tasks("O000") if t.agent == "builder"][0]
    outcomes = [h.get("outcome") for h in builder.history]
    assert "dod_failed" in outcomes and builder.attempts == 2


def test_criteria_tampering_is_detected(sandbox):
    setup_objective()
    s = Store()
    p = s.objective_dir("O000") / "objective.yaml"
    p.write_text(p.read_text().replace("threshold: 1.0e-9", "threshold: 1.0"))
    assert cli(["doctor", "--ci"]) == 1


def test_fail_verdict_triggers_diagnosis_replan_and_recovery(sandbox, monkeypatch):
    """A bug invisible to the unit check is caught by the experiment; the system diagnoses, replans,
    rebuilds, and re-evaluates on its own — and records both evaluations."""
    monkeypatch.setenv("FAKE_SUBTLE_BUG_ONCE", "1")
    setup_objective()
    s = drive(max_ticks=120)
    st = s.objective_state("O000")
    assert st.status == "passed", st
    assert len(st.evaluations) == 2  # the FAIL is on the record, not hidden
    kinds = [e["event"] for e in s.events(1000)]
    assert "investigation_spawned" in kinds
    verdicts = [e.get("verdict") for e in s.events(1000) if e["event"] == "evaluation"]
    assert verdicts == ["FAIL", "PASS"]
    plans = [t for t in s.tasks("O000") if t.type == "plan"]
    assert len(plans) == 2 and plans[1].trigger.startswith("diagnosis:")
    assert any(t.type == "review" and t.target == "EV-O000-01" for t in s.tasks("O000"))


def _tick_until(pred, max_ticks=60):
    s = Store()
    o = Orchestrator(s)
    for _ in range(max_ticks):
        o.tick()
        if pred(Store()):
            return Store()
        time.sleep(0.3)
    raise AssertionError("condition not reached")


def test_initial_plan_waits_for_founder_approval(sandbox):
    p = sandbox / "project" / "objectives" / "O000" / "objective.yaml"
    p.write_text(p.read_text().replace("require_plan_approval: false", "require_plan_approval: true"))
    setup_objective()
    s = _tick_until(lambda s: any(i.kind == "plan_approval" for i in s.inbox("open")))
    assert all(t.status == "proposed" for t in s.tasks("O000") if t.type != "plan")
    item = next(i for i in s.inbox("open") if i.kind == "plan_approval")
    assert cli(["approve", item.id]) == 0
    s = drive()
    assert s.objective_state("O000").status == "passed"


def test_level2_every_merge_needs_founder_and_is_traceable(sandbox):
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("level = 3", "level = 2"))
    setup_objective()
    s = _tick_until(lambda s: any(i.kind == "protected_change" for i in s.inbox("open")))
    item = next(i for i in s.inbox("open") if i.kind == "protected_change")
    assert cli(["approve", item.id, "--note", "diff reviewed"]) == 0
    s = drive()
    assert s.objective_state("O000").status == "passed"
    log = s.git("log", "--format=%B", "-n", "40")
    assert f"Founder-Approved: {item.id}" in log
    import subprocess
    import sys
    from pathlib import Path
    audit = Path(__file__).resolve().parents[2] / "scripts" / "audit_main.py"
    r = subprocess.run([sys.executable, str(audit)], cwd=sandbox, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_level1_founder_starts_each_task_beside_the_running_loop(sandbox):
    """Level 1: the loop plans and finishes work but never starts it; `mfos task start` does, with dispatch's
    checks, and leaves polling, verification and merging to the loop (no second orchestrator)."""
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("level = 3", "level = 1"))
    setup_objective()
    s = _tick_until(lambda s: any(t.agent == "builder" and t.status == "todo" for t in s.tasks("O000")))
    o = Orchestrator(s)
    for _ in range(3):
        o.tick()
    build = next(t for t in Store().tasks("O000") if t.agent == "builder")
    assert build.status == "todo" and build.attempts == 0  # the loop leaves it to the founder
    exp = next(t for t in Store().tasks("O000") if t.type == "experiment")
    assert cli(["task", "start", exp.id]) == 1  # experiments are the loop's to dispatch
    full = Orchestrator(Store())
    full.pol = {**full.pol, "concurrency": {"agents": 0}}
    assert any("agent slots" in w for w in full.start_task(build.id))
    assert Store().task(build.id).status == "todo"
    assert cli(["task", "start", build.id]) == 0
    assert cli(["task", "start", build.id]) == 1  # already running
    s = _tick_until(lambda s: any(i.kind == "protected_change" for i in s.inbox("open")))
    item = next(i for i in s.inbox("open") if i.kind == "protected_change")
    assert cli(["approve", item.id]) == 0
    s = drive()
    assert s.objective_state("O000").status == "passed"
    assert Store().task(build.id).attempts == 1


def test_a_plan_limit_backs_off_instead_of_burning_attempts(sandbox):
    """O001, 2026-09-30: both T0020 critics died on "You've hit your session limit". Not recognized as capacity,
    every hit used an attempt (all three within 90 s), failed the reviews and spawned two diagnosis tasks."""
    from mfos import models as m
    from mfos.agents import RunRecord
    s = Store()
    o = Orchestrator(s)
    s.save_task(m.Task(id="T9001", objective="O000", title="Review T9000 (physics)", type="review", agent="critic",
                       status="running", attempts=1, target="T9000", lens="physics"))
    n_tasks = len(s.tasks())

    def finish(text):
        t = s.task("T9001")
        t.status, t.attempts = "running", 1
        s.save_task(t)
        o._on_run_done(t, RunRecord(run_id="r", task_id=t.id, role="critic", session_id="x", cwd=str(sandbox),
                                    started="", status="error", is_error=True, subtype="success", result_text=text))
        return s.task("T9001")

    for text in ("You've hit your session limit · resets 6pm (America/Los_Angeles)",
                 "You've hit your weekly limit · resets Oct 3, 9am", "5-hour limit reached ∙ resets 3pm",
                 "API Error: Can't reach the API server — check your internet or DNS (ENOTFOUND)"):
        t = finish(text)
        assert (t.status, t.attempts, t.history[-1]["outcome"]) == ("todo", 0, "capacity_backoff"), text
    assert o._backoff_active()
    t = finish("Traceback (most recent call last): KeyError: 'x'")  # a real failure still counts
    assert (t.attempts, t.history[-1]["outcome"]) == (1, "agent_error")
    assert len(s.tasks()) == n_tasks  # no diagnosis tasks for capacity


def test_run_and_single_tick_refuse_while_a_loop_holds_the_lock(sandbox):
    """`mfos run` and `mfos loop --once` build their own orchestrator; beside a running loop both would poll
    the same finished runs and bill, verify and merge them twice."""
    from mfos.loop import acquire_loop_lock
    held = acquire_loop_lock(Store())
    assert held is not None and acquire_loop_lock(Store()) is None
    assert cli(["run", "T9999"]) == 1  # refused before the task is even looked up
    assert cli(["loop", "--once"]) == 1
    held.close()
    assert cli(["loop", "--once"]) == 0


def test_loop_refuses_to_start_on_stray_changes(sandbox, capsys):
    (sandbox / "src" / "moduleforge" / "__init__.py").write_text("# edited in the orchestrator checkout\n")
    Orchestrator(Store()).run_forever(poll_s=0, max_cycles=1)
    assert "non-state changes" in capsys.readouterr().err


def test_a_left_over_status_refresh_does_not_block_a_restart(sandbox):
    """A timestamp-only STATUS.md is deliberately left uncommitted; as the first `git status` line
    it once lost a character to output stripping and read as a stray change ("roject/STATUS.md")."""
    s = Store()
    (s.project / "STATUS.md").write_text("# status\n")
    s.git("add", "-A")
    s.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "status")
    (s.project / "STATUS.md").write_text("# status, fresher\n")
    assert Orchestrator(s).unexpected_changes() == []
    (sandbox / "src" / "moduleforge" / "__init__.py").write_text("# stray\n")
    assert Orchestrator(s).unexpected_changes() == ["src/moduleforge/__init__.py"]


def test_founder_files_are_never_committed_by_the_bot(sandbox):
    setup_objective()
    s = drive()
    assert s.objective_state("O000").status == "passed"
    # the frozen objective was committed by the founder at approval, never by mfos-bot
    authors = s.git("log", "--format=%ae", "--", "project/objectives/O000/objective.yaml").split()
    assert authors and all(a != "mfos-bot@users.noreply.github.com" for a in authors)
    # a founder draft left uncommitted in the main checkout is not swept into a state commit
    (s.project / "charter.md").write_text("# draft charter\n")
    Orchestrator(s).tick()
    assert "project/charter.md" in s.git("status", "--porcelain")


def test_agents_get_a_modern_python_first_on_path(sandbox, monkeypatch, tmp_path):
    """On macOS /usr/bin/python3 is 3.9 (no tomllib): hooks would fail closed. Agents must get ours first."""
    import os
    import sys
    rec = tmp_path / "path_head.txt"
    monkeypatch.setenv("FAKE_RECORD_PATH", str(rec))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # what launchd gives a job
    setup_objective()
    Orchestrator(Store()).tick()  # dispatches the planner
    time.sleep(1.0)
    assert rec.read_text() == os.path.dirname(sys.executable)


def test_sleep_extends_running_deadlines(sandbox):
    from mfos.agents import RunRecord
    s = Store()
    o = Orchestrator(s)
    rec = RunRecord(run_id="T9999-a1", task_id="T9999", role="builder", session_id="x", cwd=str(sandbox),
                    started="now", pid=999999, deadline=time.time() + 60)
    o.runner.save(rec)
    before = rec.deadline
    o._last_tick_wall = time.time() - 3600  # the lid was closed for an hour
    o._account_for_sleep()
    after = [r for r in o.runner.active() if r.run_id == "T9999-a1"][0].deadline
    assert 3590 < after - before < 3610


def test_heavy_experiment_goes_to_burst_compute_and_results_flow_back(sandbox):
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("local_cpu_hours_max = 6.0", "local_cpu_hours_max = 0.001"))
    setup_objective()
    s = _tick_until(lambda s: any("burst compute" in i.subject for i in s.inbox("open")))
    exp_task = [t for t in s.tasks("O000") if t.type == "experiment"][0]
    assert exp_task.status == "needs_founder"
    assert not list((sandbox / "experiments" / "results").glob("E000/*/result.json"))  # nothing ran locally
    assert cli(["exp", "run", "E000", "--force"]) == 0   # what scripts/burst.sh does on the VM
    s = drive()
    assert s.objective_state("O000").status == "passed"
    assert not [i for i in s.inbox("open") if "burst compute" in i.subject]


def test_a_run_still_being_finalized_is_not_evidence_yet(sandbox, monkeypatch):
    """CI, 2026-09-29: the loop evaluated a result.json while `mfos exp run` was still finishing the run (exit-code
    check, run.json, experiment_finished), passed O000, and committed state before those last writes landed."""
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("local_cpu_hours_max = 6.0", "local_cpu_hours_max = 0.001"))
    setup_objective()  # the loop builds the canary, then parks E000 for burst compute instead of running it
    _tick_until(lambda s: any("burst compute" in i.subject for i in s.inbox("open")))
    from mfos import experiments
    results = sandbox / "experiments" / "results" / "E000"
    marker_seen_at_finish = []
    event = Store.event

    def spy(self, name, /, *args, **kw):
        if name == "experiment_finished":
            marker_seen_at_finish.append(bool(list(results.glob("*/run.json"))))
        event(self, name, *args, **kw)

    monkeypatch.setattr(Store, "event", spy)
    assert experiments.run(Store(), "E000", force=True).status == "complete"
    assert marker_seen_at_finish == [False]  # run.json is the run's last tracked write, after the event
    run_json = next(results.glob("*/run.json"))
    record = run_json.read_text()
    run_json.unlink()  # the runner has written result.json; the wrapper has not finalized the run yet
    s = Store()
    o = Orchestrator(s)
    assert s.results("E000") == []
    o._maybe_evaluate("O000", s.objective("O000"), s.objective_state("O000"))
    assert s.objective_state("O000").evaluations == []
    run_json.write_text(record)
    o._maybe_evaluate("O000", s.objective("O000"), s.objective_state("O000"))
    assert len(s.objective_state("O000").evaluations) == 1


def test_agent_whose_allow_list_hides_structured_output_is_caught(sandbox):
    """O000 canary, 2026-09-28: every run returned structured_output=null because the agents'
    `tools:` allow-lists omitted StructuredOutput; the planner's plan was validated as {}."""
    assert cli(["doctor", "--ci"]) == 0
    md = sandbox / ".claude" / "agents" / "planner.md"
    md.write_text(md.read_text().replace(", StructuredOutput", ""))
    assert cli(["doctor", "--ci"]) == 1
    setup_objective()
    s = _tick_until(lambda s: any(h.get("outcome") == "agent_error"
                                  for t in s.tasks("O000") if t.type == "plan" for h in t.history))
    plan = next(t for t in s.tasks("O000") if t.type == "plan")
    failure = next(h for h in plan.history if h.get("outcome") == "agent_error")
    assert "no structured report" in failure["summary"] and "StructuredOutput" in failure["summary"]
    assert "schema but did not provide it" in failure["failure_output"]  # what the agent actually said


def test_report_written_as_json_text_is_recovered_and_flagged(sandbox, monkeypatch):
    monkeypatch.setenv("FAKE_REPORT_AS_TEXT", "1")
    setup_objective()
    s = drive()
    assert s.objective_state("O000").status == "passed"
    finished = [e for e in s.events(1000) if e["event"] == "run_finished"]
    assert finished and all(e["report"] == "result_text" for e in finished)


def test_report_from_text_accepts_only_a_whole_json_object():
    from mfos.agents import report_from_text
    assert report_from_text('{"a": 1}') == {"a": 1}
    assert report_from_text('  ```json\n{"a": 1}\n```\n') == {"a": 1}
    assert report_from_text('```\n{"a": 1}\n```') == {"a": 1}
    assert report_from_text('Done. Report:\n```json\n{"a": 1}\n```') is None  # prose around it
    assert report_from_text('The config is {"a": 1}.') is None
    assert report_from_text("[1, 2]") is None
    assert report_from_text("") is None


def test_a_plans_own_cancellations_free_room_for_its_tasks(sandbox):
    """O001, 2026-10-04: replan T0069 cancelled five permanently blocked tasks and proposed eight, but the
    open-task limit was applied before the cancellations, so five of the eight were silently dropped."""
    from mfos import models as m
    s = Store()
    o = Orchestrator(s)
    blocked = [f"T90{i:02d}" for i in range(8)]
    for tid in blocked:
        s.save_task(m.Task(id=tid, objective="O000", title=f"blocked {tid}", type="implement", agent="builder",
                           status="todo"))
    plan = m.Task(id="T9100", objective="O000", title="replan", type="plan", agent="planner", status="running")
    s.save_task(plan)
    specs = [{"local_id": f"n{i}", "title": f"new {i}", "type": "implement", "agent": "builder",
              "description": "x", "depends_on": [f"n{i - 1}"] if i else []} for i in range(7)]
    out = {"assessment": "replan", "create_tasks": specs,
           "cancel_tasks": [{"id": tid, "reason": "blocked for good"} for tid in blocked[:5]]}
    o._on_plan(plan, None, out)
    s = Store()
    assert all(s.task(tid).status == "cancelled" for tid in blocked[:5])
    created = [t for t in s.tasks("O000") if t.created_by == "planner:T9100"]
    assert len(created) == 7  # 10 open allowed: 3 still-blocked + 7 new
    assert s.task("T9100").history[-1]["dropped_for_limits"] == 0
    by_title = {t.title: t for t in created}
    assert by_title["new 3"].depends_on == [by_title["new 2"].id]


def test_a_founder_listed_experiment_goes_to_burst_whatever_its_estimate(sandbox):
    """E001 (2026-10-05) was registered at 2 CPU-h but needs more memory and time than this machine has; listing it
    in policy compute.burst_experiments routes it to burst compute without re-registering its estimate."""
    pol = sandbox / ".mfos" / "policy.toml"
    text = pol.read_text()
    assert "local_cpu_hours_max = 6.0" in text and 'burst_experiments = ["E001"]' in text
    pol.write_text(text.replace('burst_experiments = ["E001"]', 'burst_experiments = ["E000"]'))
    setup_objective()
    s = _tick_until(lambda s: any("burst compute" in i.subject for i in s.inbox("open")))
    item = next(i for i in s.inbox("open") if "burst compute" in i.subject)
    assert "scripts/burst_gcp.sh E000" in item.summary
    assert not list((sandbox / "experiments" / "results").glob("E000/*/result.json"))  # nothing ran locally


def test_a_repair_packet_carries_every_review_finding(sandbox):
    """T0074, 2026-10-05: the packet kept only the last 1500 characters of the rejection, i.e. the minor findings,
    and dropped the blocker that the review lists first."""
    from mfos import models as m
    from mfos.packets import _history
    findings = "- [blocker] solver_tol leaves out the cross-section bound" + "\n- [minor] detail" * 200
    t = m.Task(id="T9200", objective="O000", title="x", type="implement", agent="builder", description="x",
               history=[{"attempt": 1, "outcome": "review_rejected", "summary": "rejected",
                         "failure_output": findings[:4000]}])
    assert "[blocker] solver_tol leaves out the cross-section bound" in _history(t)


def test_a_branch_that_breaks_with_newer_main_is_not_merged(sandbox):
    """2026-10-06: T0074 was verified against T0070's core while T0071 changed a return value in it; both merged and
    9 tests failed on main. When main's code has moved, the merge takes it into the branch and re-runs the fast gate."""
    import subprocess
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("level = 3", "level = 2"))
    setup_objective()
    s = _tick_until(lambda s: any(i.kind == "protected_change" for i in s.inbox("open")))
    item = next(i for i in s.inbox("open") if i.kind == "protected_change")
    build = s.task(item.refs[0])
    # main gains code that is fine alone but fails once the task's canary (harmonic(1) == 1.0) is present
    init = sandbox / "src" / "moduleforge" / "__init__.py"
    init.write_text(init.read_text() + "\nimport importlib.util as _u\nif _u.find_spec('moduleforge.canary'):\n"
                    "    from .canary import harmonic as _h\n    assert _h(1) == 2.0, 'semantic conflict'\n")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "main moves"], cwd=sandbox,
                   check=True)
    assert cli(["approve", item.id]) == 0
    Orchestrator(Store()).tick()
    t = Store().task(build.id)
    failed = [h for h in t.history if h.get("outcome") == "dod_failed"]
    assert t.status != "done" and failed, t.history  # sent back for repair (level 2 redispatches it at once)
    assert "fast gate fails once current main is merged" in failed[-1]["summary"]
    assert "semantic conflict" in failed[-1]["failure_output"]
    assert not (sandbox / "src" / "moduleforge" / "canary.py").exists()  # main untouched


def test_a_decision_can_be_resolved_without_a_replan(sandbox):
    """O001, 2026-10-07: past its replan limit, every answered decision set needs_replan, the loop re-parked the
    objective and opened another "replan limit reached" item, so the inbox could never reactivate it."""
    setup_objective()
    s = Store()
    st = s.objective_state("O000")
    st.replans, st.max_replans, st.needs_replan, st.status = 9, 3, True, "needs_founder"
    s.save_objective_state("O000", st)
    item = s.add_inbox(kind="decision", subject="[O000] replan limit reached", summary="x", refs=["O000"])
    assert cli(["answer", item.id, "carry on as decided", "--no-replan"]) == 0
    st = Store().objective_state("O000")
    assert st.status == "active" and not st.needs_replan and "(no replan)" in st.log[-1]
    Orchestrator(Store()).tick()
    assert Store().objective_state("O000").status == "active"
    assert not [i for i in Store().inbox("open") if "replan limit" in i.subject]
    other = Store().add_inbox(kind="decision", subject="[O000] q", summary="x", refs=["O000"])
    assert cli(["approve", other.id]) == 0 and Store().objective_state("O000").needs_replan  # default unchanged


def test_a_task_carries_its_own_wall_limit(sandbox, monkeypatch):
    """T0075 (2026-10-07) needs ~4 h per run for its own solves; other agents keep the policy's limit."""
    from mfos import models as m
    from mfos.agents import RunRecord
    from mfos.store import now
    s = Store()
    o = Orchestrator(s)
    seen = {}

    def fake_start(**kw):
        seen.update(kw)
        return RunRecord(run_id="r", task_id=kw["task"].id, role=kw["role"], session_id="x", cwd=".", started=now())
    monkeypatch.setattr(o.runner, "start", fake_start)
    for tid, wall in (("T9300", 240), ("T9301", None)):
        t = m.Task(id=tid, objective="O000", title="x", type="implement", agent="builder", description="x",
                   status="todo", wall_minutes=wall)
        s.save_task(t)
        o._start_agent(t)
        assert seen["wall_minutes"] == wall
