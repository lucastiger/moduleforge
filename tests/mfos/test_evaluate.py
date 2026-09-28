"""The evaluator is the arbiter of truth; its three-valued logic is tested exhaustively."""
from mfos import models as m
from mfos.evaluate import judge


def crit(cmp, thr, use="ci"):
    return m.Criterion(id="A", metric="E.x", comparator=cmp, threshold=thr, uncertainty=m.Uncertainty(use=use))


def mv(v, lo=None, hi=None):
    return m.MetricValue(value=v, ci=(lo, hi) if lo is not None else None)


def test_pass_uses_conservative_bound():
    assert judge(crit(">=", 0.85), mv(0.93, 0.88, 0.96), as_fail=False).verdict == "satisfied"
    assert judge(crit(">=", 0.85), mv(0.90, 0.80, 0.95), as_fail=False).verdict == "undetermined"
    assert judge(crit(">=", 0.85), mv(0.70, 0.60, 0.80), as_fail=False).verdict == "not_satisfied"
    assert judge(crit("<=", 0.12), mv(0.08, 0.06, 0.10), as_fail=False).verdict == "satisfied"
    assert judge(crit("<=", 0.12), mv(0.10, 0.07, 0.14), as_fail=False).verdict == "undetermined"


def test_kill_requires_certainty():
    assert judge(crit("<", 0.80), mv(0.70, 0.62, 0.78), as_fail=True).verdict == "satisfied"
    assert judge(crit("<", 0.80), mv(0.78, 0.66, 0.86), as_fail=True).verdict == "undetermined"
    assert judge(crit(">", 0.20), mv(0.31, 0.26, 0.37), as_fail=True).verdict == "satisfied"
    assert judge(crit(">", 0.20), mv(0.22, 0.17, 0.27), as_fail=True).verdict == "undetermined"


def test_missing_uncertainty_is_not_silently_accepted():
    assert judge(crit(">=", 0.85), mv(0.99), as_fail=False).verdict == "missing"
    assert judge(crit(">=", 0.85, use="point"), mv(0.99), as_fail=False).verdict == "satisfied"
    assert judge(crit(">=", 0.85), None, as_fail=False).verdict == "missing"
