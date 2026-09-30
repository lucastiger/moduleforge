import dataclasses

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import box

from moduleforge.drc import DEFAULT_RULES, check
from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import BondWire, Trace


@pytest.fixture(scope="module")
def good():
    return generate_layouts(3, seed=3, family="side_by_side", dies_per_switch=3)[0]


def rules(lay):
    return {v.rule for v in check(lay)}


def test_good_layouts_pass():
    for lay in generate_layouts(6, seed=11):
        assert check(lay) == []


def test_min_trace_width(good):
    # add a 0.5 mm-wide stub to the DC- trace (inside the substrate, away from others)
    t = next(t for t in good.traces if t.net == "DC-")
    minx, miny, maxx, maxy = t.polygon.bounds
    stub = box(minx + 0.010, maxy, minx + 0.0105, maxy + 0.006)
    bad = dataclasses.replace(good, traces=[Trace("DC-", t.polygon.union(stub)) if x is t else x
                                            for x in good.traces])
    assert "min_trace_width" in rules(bad)


def test_min_spacing(good):
    t = next(t for t in good.traces if t.net == "DC-")
    p = next(t for t in good.traces if t.net == "PHASE")
    gap = t.polygon.distance(p.polygon)
    assert gap >= DEFAULT_RULES.min_spacing
    shifted = affinity.translate(t.polygon, yoff=-(gap - 0.5e-3))  # leave 0.5 mm
    bad = dataclasses.replace(good, traces=[Trace("DC-", shifted) if x is t else x for x in good.traces])
    assert "min_spacing" in rules(bad)


def test_edge_margin(good):
    p = next(t for t in good.traces if t.net == "DC+")
    minx = p.polygon.bounds[0]
    shifted = affinity.translate(p.polygon, xoff=-(minx - 0.5e-3))
    bad = dataclasses.replace(good, traces=[Trace("DC+", shifted) if x is p else x for x in good.traces])
    assert "edge_margin" in rules(bad)


def test_die_edge_margin_and_off_trace(good):
    d = next(d for d in good.dies if d.switch == "HS")
    host = next(t for t in good.traces if t.net == "DC+")
    dy = host.polygon.bounds[1] + 0.3e-3 + d.h / 2 - d.cy  # 0.3 mm from the trace bottom edge
    bad = dataclasses.replace(good, dies=[dataclasses.replace(d, cy=d.cy + dy) if x is d else x
                                          for x in good.dies])
    assert "die_edge_margin" in rules(bad)
    far = dataclasses.replace(good, dies=[dataclasses.replace(d, cx=1e-3) if x is d else x
                                          for x in good.dies])
    assert "die_off_trace" in rules(far)


def test_die_wrong_net(good):
    ls = next(d for d in good.dies if d.switch == "LS")
    bad = dataclasses.replace(good, dies=[dataclasses.replace(ls, switch="HS") if x is ls else x
                                          for x in good.dies])
    assert "die_wrong_net" in rules(bad)


def test_die_spacing(good):
    a, b = [d for d in good.dies if d.switch == "HS"][:2]
    bad = dataclasses.replace(good, dies=[dataclasses.replace(b, cx=a.cx + a.w + 0.4e-3) if x is b else x
                                          for x in good.dies])
    assert "die_spacing" in rules(bad)


def test_wire_length(good):
    w = good.wires[0]
    long = BondWire(w.points * np.array([1, 1, 1]) + np.array([0, 0.03, 0]) * np.linspace(0, 1, len(w.points))[:, None],
                    w.diameter, w.loop_height, w.net)
    assert "wire_length" in rules(dataclasses.replace(good, wires=[long, *good.wires[1:]]))
    short = BondWire(w.points[0] + 0.1 * (w.points - w.points[0]), w.diameter, w.loop_height, w.net)
    assert "wire_length" in rules(dataclasses.replace(good, wires=[short, *good.wires[1:]]))


def test_wire_pitch(good):
    w = good.wires[0]
    dup = BondWire(w.points + np.array([0.2e-3, 0, 0]), w.diameter, w.loop_height, w.net)  # 0.2 mm apart
    bad = dataclasses.replace(good, wires=[*good.wires, dup])
    assert "wire_pitch" in rules(bad)


def test_wire_landing_wrong_net_and_off_copper(good):
    w = good.wires[0]
    assert w.net == "PHASE"
    wrong = BondWire(w.points, w.diameter, w.loop_height, "DC-")
    assert "wire_landing" in rules(dataclasses.replace(good, wires=[wrong, *good.wires[1:]]))
    off = w.points.copy()
    off[-1, 0] = 0.0005  # lands on bare ceramic left of all Cu
    assert "wire_landing" in rules(dataclasses.replace(
        good, wires=[BondWire(off, w.diameter, w.loop_height, w.net), *good.wires[1:]]))
