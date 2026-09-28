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


def test_loop_refuses_to_start_on_stray_changes(sandbox, capsys):
    (sandbox / "src" / "moduleforge" / "__init__.py").write_text("# edited in the orchestrator checkout\n")
    Orchestrator(Store()).run_forever(poll_s=0, max_cycles=1)
    assert "non-state changes" in capsys.readouterr().err


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
