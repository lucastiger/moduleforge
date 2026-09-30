"""Blinded review checkouts: a critic must not be able to recover a blinded file through git."""
import subprocess

from mfos.gitops import GitOps
from mfos.store import Store


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def test_review_checkout_has_no_history_to_recover_blinded_files(sandbox):
    """T0028, 2026-09-30: a critic read project/tasks/T0021.yaml with `git show HEAD:...` because the review
    checkout was a worktree of the repository and shared all of its history."""
    s = Store()
    blinded = "project/objectives/O000/state.yaml"
    assert git(sandbox, "cat-file", "-e", f"HEAD:{blinded}").returncode == 0  # committed, hence recoverable
    head = s.git("rev-parse", "HEAD").strip()
    path = GitOps(s).review_checkout("review-T9999", head)
    assert not (path / blinded).exists()
    assert (path / "src" / "moduleforge" / "__init__.py").exists()  # the code under review is there
    assert git(path, "show", f"HEAD:{blinded}").returncode != 0
    assert git(path, "cat-file", "-e", head).returncode != 0  # the repository's commits are unreachable
    assert git(path, "rev-list", "--all").stdout.split() == [git(path, "rev-parse", "HEAD").stdout.strip()]
    assert blinded not in git(path, "log", "--all", "--name-only").stdout.split()
    assert str(path) not in git(sandbox, "worktree", "list").stdout  # not linked to the repository
    assert git(path, "status", "--porcelain").stdout == ""  # a clean snapshot the critic can diff against


def test_critics_get_the_orchestrator_settings_in_their_untrusted_snapshot(sandbox, monkeypatch):
    """2026-09-30: a fresh snapshot repository is an untrusted workspace, so Claude Code ignored its
    .claude/settings.json ("Ignoring 38 permissions.allow entries ... has not been trusted") and critics could not
    run uv or python. Settings passed with --settings do apply there (probe, same day)."""
    from mfos import models as m
    from mfos.agents import RunRecord
    from mfos.loop import Orchestrator
    s = Store()
    o = Orchestrator(s)
    seen = {}

    def start(**kw):
        seen[kw["task"].id] = kw
        return RunRecord(run_id="r", task_id=kw["task"].id, role=kw["role"], session_id="x", cwd=str(kw["cwd"]),
                         started="")

    monkeypatch.setattr(o.runner, "start", start)
    s.save_task(m.Task(id="T9000", objective="O000", title="Change", type="implement", agent="builder", status="todo"))
    s.save_task(m.Task(id="T9001", objective="O000", title="Review T9000 (general)", type="review", agent="critic",
                       status="todo", target="T9000", lens="general", description=s.git("rev-parse", "HEAD")))
    o._start_agent(s.task("T9001"))
    o._start_agent(s.task("T9000"))
    assert seen["T9001"]["settings_file"] == s.root / ".claude" / "settings.json"  # the orchestrator's own copy
    assert seen["T9001"]["settings_file"].is_file()
    assert seen["T9000"]["settings_file"] is None  # task worktrees inherit the main repository's trust
