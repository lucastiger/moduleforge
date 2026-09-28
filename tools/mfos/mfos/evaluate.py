"""Deterministic acceptance evaluation. No LLM is involved in any verdict.

Three-valued logic with uncertainty:
  * A pass criterion is SATISFIED only if the conservative end of the CI clears it
    (lower bound for >=/>, upper bound for <=/<).
  * A fail criterion is SATISFIED only if the result is definitely on the failing side
    (e.g. "rho < 0.80" requires the CI *upper* bound < 0.80).
  * Anything else is UNDETERMINED.

Overall verdict:
  INVALID       evidence is not admissible (dirty tree, spec drift, failed sanity check,
                missing result, missing required uncertainty). This is an *experimental*
                failure and says nothing about the hypothesis.
  FAIL          any fail criterion satisfied.
  PASS          every pass criterion satisfied.
  INCONCLUSIVE  otherwise.
"""
from __future__ import annotations

import operator
from typing import Callable, Optional

from . import models as m
from .store import Store, now

EVALUATOR_VERSION = "1.0.0"

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt,
}


def _metric(results: dict[str, m.ExperimentResult], ref: str) -> Optional[m.MetricValue]:
    eid, _, name = ref.partition(".")
    res = results.get(eid)
    return res.metrics.get(name) if res else None


def judge(c: m.Criterion, mv: Optional[m.MetricValue], *, as_fail: bool) -> m.CriterionVerdict:
    base = dict(id=c.id, metric=c.metric, comparator=c.comparator, threshold=c.threshold)
    if mv is None:
        return m.CriterionVerdict(**base, verdict="missing")
    op = _OPS[c.comparator]
    if c.uncertainty.use == "point":
        ok = op(mv.value, c.threshold)
        return m.CriterionVerdict(**base, value=mv.value, bound_used=mv.value,
                                  verdict="satisfied" if ok else "not_satisfied")
    if mv.ci is None:
        return m.CriterionVerdict(**base, value=mv.value, verdict="missing")
    lo, hi = mv.ci
    greater = c.comparator in (">=", ">")
    # pass criteria use the pessimistic bound; fail criteria require certainty of failure
    if not as_fail:
        bound = lo if greater else hi
        sat = op(bound, c.threshold)
        other = hi if greater else lo
        verdict = "satisfied" if sat else ("not_satisfied" if not op(other, c.threshold) else "undetermined")
    else:
        bound = hi if not greater else lo  # e.g. "< t" -> need hi < t ; "> t" -> need lo > t
        sat = op(bound, c.threshold)
        verdict = "satisfied" if sat else "undetermined"
    return m.CriterionVerdict(**base, value=mv.value, bound_used=bound, verdict=verdict)


def select_results(store: Store, obj: m.Objective) -> tuple[dict[str, m.ExperimentResult], list[str]]:
    """Pick the latest admissible result for each required experiment."""
    chosen: dict[str, m.ExperimentResult] = {}
    problems: list[str] = []
    for eid in obj.acceptance.required_experiments:
        spec_file = store.spec_path(eid)
        if not spec_file.exists():
            problems.append(f"{eid}: no registered spec")
            continue
        spec = store.spec(eid)
        if spec.status != "registered" or spec.spec_hash != store.spec_hash(spec):
            problems.append(f"{eid}: spec not registered or modified after registration")
            continue
        runs = [r for r in store.results(eid) if r.status == "complete"]
        if not runs:
            problems.append(f"{eid}: no complete result")
            continue
        r = runs[-1]
        if r.provenance.git_dirty:
            problems.append(f"{eid}/{r.run_id}: produced from a dirty working tree")
        if r.provenance.spec_hash != spec.spec_hash:
            problems.append(f"{eid}/{r.run_id}: result spec_hash does not match registered spec")
        bad = [s.name for s in r.sanity if not s.passed]
        if bad:
            problems.append(f"{eid}/{r.run_id}: sanity checks failed: {', '.join(bad)}")
        missing = [x.name for x in spec.sanity_checks if x.name not in {s.name for s in r.sanity}]
        if missing:
            problems.append(f"{eid}/{r.run_id}: sanity checks not reported: {', '.join(missing)}")
        chosen[eid] = r
    return chosen, problems


def evaluate(store: Store, oid: str, record: bool = True) -> m.Evaluation:
    obj = store.objective(oid)
    st = store.objective_state(oid)
    results, problems = select_results(store, obj)
    if st.criteria_hash and st.criteria_hash != store.criteria_hash(obj):
        problems.append("acceptance criteria changed after approval (criteria_hash mismatch)")
    if len(st.evaluations) >= obj.acceptance.max_evaluations:
        problems.append(f"evaluation budget exhausted ({obj.acceptance.max_evaluations}); founder must decide")

    pass_checks = [judge(c, _metric(results, c.metric), as_fail=False) for c in obj.acceptance.pass_all]
    fail_checks = [judge(c, _metric(results, c.metric), as_fail=True) for c in obj.acceptance.fail_any]
    missing = [v.id for v in pass_checks + fail_checks if v.verdict == "missing"]
    if missing:
        problems.append("metrics missing or lacking required uncertainty: " + ", ".join(missing))

    if problems:
        verdict, why = "INVALID", "Evidence not admissible: " + "; ".join(problems)
    elif any(v.verdict == "satisfied" for v in fail_checks):
        hit = [v.id for v in fail_checks if v.verdict == "satisfied"]
        verdict, why = "FAIL", f"Kill criteria definitely met: {', '.join(hit)}"
    elif all(v.verdict == "satisfied" for v in pass_checks):
        verdict, why = "PASS", "All pass criteria met at the conservative bound"
    else:
        open_ = [v.id for v in pass_checks if v.verdict != "satisfied"]
        verdict, why = "INCONCLUSIVE", f"Pass criteria not established: {', '.join(open_)}"

    eid = f"EV-{oid}-{len(st.evaluations) + 1:02d}"
    ev = m.Evaluation(
        id=eid, objective=oid, timestamp=now(), criteria_hash=st.criteria_hash,
        evaluator_version=EVALUATOR_VERSION,
        results_used={k: v.run_id for k, v in results.items()},
        validity_problems=problems, pass_checks=pass_checks, fail_checks=fail_checks,
        verdict=verdict, explanation=why,
    )
    if record and verdict != "INVALID":
        store.write_json(store.objective_dir(oid) / "evaluations" / f"{eid}.json", ev)
        st.evaluations.append(eid)
        st.last_verdict = verdict
        store.save_objective_state(oid, st)
        store.event("evaluation", objective=oid, id=eid, verdict=verdict)
    elif record:
        store.write_json(store.objective_dir(oid) / "evaluations" / f"{eid}-invalid.json", ev)
        store.event("evaluation_invalid", objective=oid, problems=problems)
    return ev
