import dataclasses

import numpy as np
import pytest

from moduleforge.drc import check
from moduleforge.generate import halfbridge
from moduleforge.generate.halfbridge import FAMILIES, generate_layouts, loop_area_proxy
from moduleforge.geometry import Terminal


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


def test_loop_area_proxy_known_value():
    # hand-built: DC+ (0,0), DC- (0,3 mm), HS dies at (4,0) mm, LS dies at (4,3) mm -> 4 x 3 mm rectangle
    lay = generate_layouts(1, seed=3, family="side_by_side", dies_per_switch=3)[0]
    hs = [dataclasses.replace(d, cx=4e-3, cy=0.0) for d in lay.dies if d.switch == "HS"]
    ls = [dataclasses.replace(d, cx=4e-3, cy=3e-3) for d in lay.dies if d.switch == "LS"]
    terms = {**lay.terminals, "DC+": Terminal("DC+", 0.0, 0.0, 1e-3, 1e-3),
             "DC-": Terminal("DC-", 0.0, 3e-3, 1e-3, 1e-3)}
    rect = dataclasses.replace(lay, dies=hs + ls, terminals=terms)
    assert loop_area_proxy(rect) == pytest.approx(12e-6, rel=1e-12)
    # a right triangle: HS and LS centroids coincide -> DC+ (0,0), P (4,0), P, DC- (0,3): area 0.5*4*3 = 6 mm^2
    ls_at_hs = [dataclasses.replace(d, cx=4e-3, cy=0.0) for d in ls]
    tri = dataclasses.replace(lay, dies=hs + ls_at_hs, terminals=terms)
    assert loop_area_proxy(tri) == pytest.approx(6e-6, rel=1e-12)
