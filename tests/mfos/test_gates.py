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


def test_a_killed_run_is_billed_from_its_session_transcript(tmp_path, monkeypatch):
    """2026-10-07: a T0075 run killed at its wall limit recorded $0; the CLI's transcript held its cost ($6.92).
    Only cost-state lines written by a process that started with this run count (a resumed session has earlier ones)."""
    import json
    from datetime import datetime

    from mfos.agents import AgentRunner
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    d = tmp_path / "cfg" / "projects" / "-Users-x-wt-T0075"
    d.mkdir(parents=True)
    started = "2026-10-07T05:55:40+00:00"
    t0 = datetime.fromisoformat(started).timestamp() * 1000
    lines = [{"type": "cost-state", "sessionId": "s1", "totalCostUSD": 3.0, "startTime": t0 - 3_600_000},
             {"type": "assistant", "message": {"usage": {}}},
             {"type": "cost-state", "sessionId": "s1", "totalCostUSD": 6.9232076, "startTime": t0 + 500}]
    (d / "s1.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    assert AgentRunner.transcript_cost("s1", started) == 6.9232076
    assert AgentRunner.transcript_cost("s1", "2026-10-07T09:00:00+00:00") is None  # only an earlier run's cost
    assert AgentRunner.transcript_cost("missing", started) is None
