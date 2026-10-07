"""Definition-of-done commands: a timeout ends the whole command, not just its shell."""
import os
import time

from mfos.gates import run_cmd


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_timed_out_check_leaves_no_orphans(tmp_path):
    """2026-10-04: T0022's E001 smoke and layout checks timed out, but their python children kept running as
    orphans (71 and 31 minutes, ~0.6 GB), competing with the next attempt."""
    pidfile = tmp_path / "child.pid"
    r = run_cmd(f"sleep 60 & echo $! > {pidfile}; wait", tmp_path, timeout_s=1)
    assert not r.ok and r.output.startswith("TIMEOUT")
    child = int(pidfile.read_text())
    for _ in range(50):
        if not _alive(child):
            break
        time.sleep(0.1)
    assert not _alive(child), "the check's child process survived the timeout"


def test_a_finished_check_reports_its_output(tmp_path):
    r = run_cmd("echo out; echo err >&2; exit 3", tmp_path, timeout_s=10)
    assert not r.ok and "out" in r.output and "err" in r.output
    assert run_cmd("true", tmp_path, timeout_s=10).ok


def test_killing_a_timed_out_agent_survives_its_unreaped_leader():
    """2026-10-05: T0071's builder exited on the SIGINT, and macOS refused the follow-up SIGTERM to its group
    (EPERM: only the unreaped leader was left). The tick crashed and the timeout was recorded as an interruption."""
    import subprocess

    from mfos.agents import AgentRunner
    p = subprocess.Popen(["sleep", "60"], start_new_session=True)
    AgentRunner._kill(p.pid)
    assert p.wait(timeout=10) != 0



def test_a_killed_run_is_billed_from_its_session_transcript(sandbox, tmp_path, monkeypatch):
    """2026-10-07: a T0075 run killed at its wall limit recorded $0; the CLI's transcript held its cost ($6.92).
    The CLI's totals are cumulative over a session, so a resumed run is billed only what it added (T0071,
    2026-10-05: $4.48 at the interruption, $4.81 after the resume)."""
    import json

    from mfos.agents import RunRecord
    from mfos.loop import Orchestrator
    from mfos.store import Store
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    d = tmp_path / "cfg" / "projects" / "-Users-x-wt-T0071"
    d.mkdir(parents=True)
    cs = lambda c: json.dumps({"type": "cost-state", "sessionId": "s1", "totalCostUSD": c, "startTime": 1})  # noqa: E731
    (d / "s1.jsonl").write_text(cs(4.4831658) + "\n" + json.dumps({"type": "assistant"}) + "\nnot json\n")
    runner = Orchestrator(Store()).runner
    assert runner.transcript_cost("s1") == 4.4831658 and runner.transcript_cost("missing") is None
    first = RunRecord(run_id="r1", task_id="T1", role="builder", session_id="s1", cwd=".", started="2026-10-05T07:32:15+00:00")
    runner._bill_from_transcript(first)
    first.status = "interrupted"
    runner.save(first)
    assert abs(first.cost_usd - 4.4831658) < 1e-6 and first.extra["cost_source"] == "transcript"
    resumed = RunRecord(run_id="r2", task_id="T1", role="builder", session_id="s1", cwd=".",
                        started="2026-10-05T09:08:53+00:00", resumed_from="s1")
    assert abs(runner._net_of_session(resumed, 4.8149814) - 0.3318156) < 1e-6  # the resume's own share
