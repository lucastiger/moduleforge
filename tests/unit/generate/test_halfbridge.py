import numpy as np
import pytest

from moduleforge.drc import check
from moduleforge.generate import halfbridge
from moduleforge.generate.halfbridge import FAMILIES, generate_layouts, loop_area_proxy


@pytest.fixture(scope="module")
def sixty():
    return generate_layouts(60, seed=12345)


def test_all_drc_valid(sixty):
    assert len(sixty) == 60
    assert all(check(lay) == [] for lay in sixty)


def test_seeded_determinism(sixty):
    again = generate_layouts(60, seed=12345)
    assert [x.fingerprint() for x in sixty] == [x.fingerprint() for x in again]
    other = generate_layouts(60, seed=54321)
    assert [x.fingerprint() for x in sixty] != [x.fingerprint() for x in other]


def test_coverage_of_families_and_die_counts(sixty):
    assert {x.family for x in sixty} == set(FAMILIES)
    assert {x.dies_per_switch for x in sixty} == {2, 3, 4, 5, 6}
    for x in sixty:
        assert sum(d.switch == "HS" for d in x.dies) == x.dies_per_switch == sum(d.switch == "LS" for d in x.dies)


def test_families_topologically_distinct():
    by = {f: generate_layouts(1, seed=1, family=f, dies_per_switch=3)[0] for f in FAMILIES}
    # number of polygon exteriors/concavity differs: PHASE is convex in side_by_side, non-convex otherwise
    def convex(lay):
        p = next(t for t in lay.traces if t.net == "PHASE").polygon
        return abs(p.convex_hull.area - p.area) < 1e-12
    assert not convex(by["interleaved"]) and not convex(by["u_shaped"])
    # DC+/DC- adjacency: interleaved rows are separated only by the min gap, u_shaped by a PHASE row
    def gap(lay):
        a, b = (next(t for t in lay.traces if t.net == n).polygon for n in ("DC+", "DC-"))
        return a.distance(b)
    assert gap(by["interleaved"]) < 3e-3 < gap(by["u_shaped"])


def test_fixed_housing_terminals(sixty):
    ref = {n: (t.cx, t.cy, t.w, t.h) for n, t in sixty[0].terminals.items()}
    assert set(ref) == {"DC+", "DC-", "PHASE"}
    for x in sixty:
        assert {n: (t.cx, t.cy, t.w, t.h) for n, t in x.terminals.items()} == ref


def test_family_and_count_filters():
    ls = generate_layouts(5, seed=2, family="u_shaped", dies_per_switch=4)
    assert {x.family for x in ls} == {"u_shaped"} and {x.dies_per_switch for x in ls} == {4}
    with pytest.raises(ValueError):
        generate_layouts(1, seed=0, family="nope")
    with pytest.raises(ValueError):
        generate_layouts(1, seed=0, dies_per_switch=7)


def test_reject_and_resample_bounded(monkeypatch):
    monkeypatch.setattr(halfbridge, "check", lambda lay: ["always bad"])
    with pytest.raises(RuntimeError):
        generate_layouts(1, seed=0, max_tries=5)


@pytest.mark.parametrize("seed", [12345, 1, 2])
def test_loop_area_proxy_spread(seed):
    a = np.array([loop_area_proxy(x) for x in generate_layouts(60, seed=seed)])
    assert (a > 0).all()
    assert a.std(ddof=1) / a.mean() >= 0.3  # E002 sample_diverse early check (F2)


def test_loop_area_proxy_known_value(sixty):
    # closed form: shoelace area of terminal/centroid quadrilateral, checked on a hand-built case
    lay = sixty[0]
    hs = np.mean([(d.cx, d.cy) for d in lay.dies if d.switch == "HS"], axis=0)
    ls = np.mean([(d.cx, d.cy) for d in lay.dies if d.switch == "LS"], axis=0)
    tp, tn = lay.terminals["DC+"], lay.terminals["DC-"]
    pts = [(tp.cx, tp.cy), tuple(hs), tuple(ls), (tn.cx, tn.cy)]
    area = 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4)))
    assert loop_area_proxy(lay) == pytest.approx(area, rel=1e-12)
