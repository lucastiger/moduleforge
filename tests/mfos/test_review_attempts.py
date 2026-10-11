"""Reviews judge the code they reviewed; a capacity pause does not undo a founder's start at level 1."""
from mfos import models as m
from mfos.agents import RunRecord
from mfos.loop import Orchestrator
from mfos.store import Store


def _review(s, rid, target, ref, verdict):
    s.save_task(m.Task(id=rid, objective="O000", title=f"Review {target} (general)", type="review", agent="critic",
                       status="done", target=target, lens="general", description=ref))
    p = s.project / "reviews" / target / f"{rid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(m.Review(verdict=verdict).model_dump_json())


def _task_in_review(s, o):
    t = m.Task(id="T9000", objective="O000", title="Change", type="implement", agent="builder", status="review",
               risk="medium", attempts=2)  # medium risk: the ladder requires a critic
    s.save_task(t)
    path = o.git.task_worktree(t)
    s.save_task(t)
    return s.task("T9000"), o.git.head(path)


def test_a_retry_is_not_judged_by_the_reviews_of_an_earlier_attempt(sandbox, monkeypatch):
    """O001, 2026-09-30: T0037 attempt 2 was accepted by its critic (T0042) but rejected again, because the loop
    still counted attempt 1's rejecting review (T0039) of a different commit."""
    s = Store()
    o = Orchestrator(s)
    merged = []
    monkeypatch.setattr(o, "_merge", lambda t: merged.append(t.id))
    t, head = _task_in_review(s, o)
    _review(s, "T9001", "T9000", "0" * 40, "reject")  # attempt 1, another commit
    _review(s, "T9002", "T9000", head, "accept_with_caveats")  # this commit
    o._advance(s.task("T9000"))
    assert merged == ["T9000"]
    assert not any(h.get("outcome") == "review_rejected" for h in s.task("T9000").history)


def test_a_commit_without_its_own_reviews_is_reviewed_not_merged(sandbox, monkeypatch):
    s = Store()
    o = Orchestrator(s)
    merged = []
    monkeypatch.setattr(o, "_merge", lambda t: merged.append(t.id))
    t, head = _task_in_review(s, o)
    _review(s, "T9001", "T9000", "0" * 40, "accept")  # accepted a different commit
    o._advance(s.task("T9000"))
    assert merged == []
    fresh = [x for x in s.tasks() if x.type == "review" and x.target == "T9000" and x.description == head]
    assert fresh and all(x.status == "todo" for x in fresh)
    assert s.task("T9000").status == "review"


def test_level1_resumes_a_founder_started_task_after_a_capacity_pause(sandbox, monkeypatch):
    """2026-09-30: T0041 and T0043 hit the plan limit; the backoff returned them to todo and, at level 1, nothing
    started them again for four hours."""
    pol = sandbox / ".mfos" / "policy.toml"
    pol.write_text(pol.read_text().replace("level = 3", "level = 1"))
    s = Store()
    s.save_objective_state("O000", m.ObjectiveState(status="active"))
    paused = m.Task(id="T9010", objective="O000", title="Paused", type="implement", agent="builder", status="todo",
                    history=[{"outcome": "capacity_backoff", "summary": "You've hit your session limit"}])
    fresh = m.Task(id="T9011", objective="O000", title="Never started", type="implement", agent="builder",
                   status="todo")
    s.save_task(paused)
    s.save_task(fresh)
    o = Orchestrator(s)
    started = []

    def start(**kw):
        started.append(kw["task"].id)
        return RunRecord(run_id="r", task_id=kw["task"].id, role="builder", session_id="x", cwd=str(kw["cwd"]),
                         started="")

    monkeypatch.setattr(o.runner, "start", start)
    o._dispatch()
    assert started == ["T9010"]


def test_a_rejection_keeps_its_most_severe_findings():
    """T0076, 2026-10-08: two long rejections were stored as their last 4000 characters, so the repair packet lost
    T0094's blocker. Findings are ordered most severe first and the tail is cut, with a pointer to the reviews."""
    from mfos import models as m
    from mfos.loop import rejection_text
    minor = m.Finding(severity="minor", title="m", detail="x" * 3000)
    blocker = m.Finding(severity="blocker", title="crash after all compute", detail="IndexError")
    reviews = [m.Review(verdict="reject", findings=[minor]), m.Review(verdict="reject", findings=[minor, blocker])]
    text = rejection_text("T9", reviews)
    assert text.startswith("- [blocker] crash after all compute") and len(text) < 4000
    assert text.endswith("full reviews: project/reviews/T9/]")
