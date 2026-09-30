import dataclasses

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

from moduleforge.drc import DEFAULT_RULES, check
from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import BondWire, Terminal, Trace, arc_wire


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


def _hs(lay):
    return next(d for d in lay.dies if d.switch == "HS")


def _start_on(w, d):
    x0, y0, x1, y1 = d.pads["source"]
    return x0 <= w.points[0, 0] <= x1 and y0 <= w.points[0, 1] <= y1


def _swap(seq, old, new):
    return [new if x is old else x for x in seq]


def test_good_fixture_clean(good):
    assert check(good) == []


def test_wire_start(good):
    w = good.wires[0]
    d = next(d for d in good.dies if _start_on(w, d))
    pts = w.points.copy()
    pts[0, :2] = (d.cx + 0.45 * d.w, d.cy + 0.45 * d.h)  # on the die but outside the source pad
    bad = dataclasses.replace(good, wires=_swap(good.wires, w, BondWire(pts, w.diameter, w.loop_height, w.net)))
    assert "wire_start" in rules(bad)


def test_terminal_off_trace(good):
    off = dict(good.terminals)
    off["DC+"] = Terminal("DC+", 35e-3, 0.5e-3, 4e-3, 4e-3)  # bare ceramic at the bottom edge
    assert "terminal_off_trace" in rules(dataclasses.replace(good, terminals=off))


def test_wire_net_label_and_copper(good):
    hs = _hs(good)
    w = next(w for w in good.wires if _start_on(w, hs))
    assert w.net == "PHASE"
    # label says DC- although the copper under the landing is PHASE
    lab = BondWire(w.points, w.diameter, w.loop_height, "DC-")
    assert "wire_net" in rules(dataclasses.replace(good, wires=_swap(good.wires, w, lab)))
    # HS die bonded onto DC- copper with a consistent label (DC-link short)
    dcm = next(t for t in good.traces if t.net == "DC-").polygon.representative_point()
    short = arc_wire(w.points[0, :2], (dcm.x, dcm.y), w.points[0, 2], w.points[-1, 2], w.loop_height, w.diameter,
                     "DC-")
    r = rules(dataclasses.replace(good, wires=_swap(good.wires, w, short)))
    assert "wire_net" in r and "wire_landing" not in r
    # LS die bonded to PHASE (would short the switch)
    ls = next(d for d in good.dies if d.switch == "LS")
    wl = next(w for w in good.wires if _start_on(w, ls))
    ph = next(t for t in good.traces if t.net == "PHASE").polygon
    tgt = ph.buffer(-2e-3).representative_point()
    bad = arc_wire(wl.points[0, :2], (tgt.x, tgt.y), wl.points[0, 2], wl.points[-1, 2], wl.loop_height,
                   wl.diameter, "PHASE")
    assert "wire_net" in rules(dataclasses.replace(good, wires=_swap(good.wires, wl, bad)))


def test_die_unbonded_and_missing_switch(good):
    hs = _hs(good)
    keep = [w for w in good.wires if not _start_on(w, hs)]
    assert "die_unbonded" in rules(dataclasses.replace(good, wires=keep))
    assert "die_unbonded" not in rules(good)
    only_ls = [d for d in good.dies if d.switch == "LS"]
    assert "missing_switch" in rules(dataclasses.replace(good, dies=only_ls))
    only_hs = [d for d in good.dies if d.switch == "HS"]
    assert "missing_switch" in rules(dataclasses.replace(good, dies=only_hs))
    assert "missing_switch" in rules(dataclasses.replace(good, dies=[], wires=[]))


def test_die_on_terminal(good):
    tm = good.terminals["DC+"]
    moved = dataclasses.replace(_hs(good), cx=tm.cx, cy=tm.cy)
    assert "die_on_terminal" in rules(dataclasses.replace(good, dies=[*good.dies, moved]))


def test_wire_landing_keepout_die_and_terminal(good):
    hs = _hs(good)
    ls = next(d for d in good.dies if d.switch == "LS")
    w = next(w for w in good.wires if _start_on(w, hs))
    under = arc_wire(w.points[0, :2], (ls.cx, ls.cy), w.points[0, 2], w.points[-1, 2], w.loop_height, w.diameter,
                     "PHASE")
    assert "wire_landing_keepout" in rules(dataclasses.replace(good, wires=_swap(good.wires, w, under)))
    tm = good.terminals["PHASE"]  # landing 0.1 mm beyond the PHASE terminal pad, on PHASE copper
    near = arc_wire(w.points[0, :2], (tm.cx + tm.w / 2 + 0.1e-3, tm.cy), w.points[0, 2], w.points[-1, 2],
                    w.loop_height, w.diameter, "PHASE")
    r = rules(dataclasses.replace(good, wires=_swap(good.wires, w, near)))
    assert "wire_landing_keepout" in r


def test_wire_pitch_scales_with_diameter(good):
    w = good.wires[0]

    def pair(dia, pitch):
        a = BondWire(w.points, dia, w.loop_height, w.net)
        b = BondWire(w.points + np.array([pitch, 0.0, 0.0]), dia, w.loop_height, w.net)
        return dataclasses.replace(good, wires=[a, b])

    assert "wire_pitch" in rules(pair(0.6e-3, 0.6e-3))  # 0.6 mm wires need >= 1.2 mm
    assert "wire_pitch" in rules(pair(0.6e-3, 1.1e-3))
    assert "wire_pitch" not in rules(pair(0.6e-3, 1.2e-3))  # exactly 2 diameters passes
    assert "wire_pitch" not in rules(pair(0.3e-3, 0.6e-3))  # min_wire_pitch floor still 0.6 mm


@pytest.mark.parametrize("dia", [0.0, -1e-3, 0.05e-3, 1.0e-3])
def test_wire_diameter(good, dia):
    wires = [BondWire(w.points, dia, w.loop_height, w.net) for w in good.wires]
    assert "wire_diameter" in rules(dataclasses.replace(good, wires=wires))


def test_min_trace_width_boundary(good):
    t = next(t for t in good.traces if t.net == "DC-")
    minx, _, _, maxy = t.polygon.bounds

    def with_stub(width):
        poly = t.polygon.union(box(minx + 0.010, maxy, minx + 0.010 + width, maxy + 0.006))
        return rules(dataclasses.replace(good, traces=_swap(good.traces, t, Trace("DC-", poly))))

    assert "min_trace_width" not in with_stub(1.0e-3)
    assert "min_trace_width" in with_stub(0.999e-3)


def test_min_spacing_boundary(good):
    t = next(t for t in good.traces if t.net == "DC-")
    p = next(t for t in good.traces if t.net == "PHASE")
    gap = t.polygon.distance(p.polygon)

    def at(sp):
        sh = affinity.translate(t.polygon, yoff=-(gap - sp))
        return rules(dataclasses.replace(good, traces=_swap(good.traces, t, Trace("DC-", sh))))

    assert "min_spacing" not in at(1.0e-3)
    assert "min_spacing" in at(0.999e-3)


def _split(lay, net):
    t = next(x for x in lay.traces if x.net == net)
    tm = lay.terminals[net]
    x0, y0, x1, y1 = t.polygon.bounds
    cut = tm.cx - tm.w / 2 - 2e-3
    left = t.polygon.intersection(box(x0, y0, cut - 0.5e-3, y1))
    right = t.polygon.intersection(box(cut + 0.5e-3, y0, x1, y1))
    return dataclasses.replace(lay, traces=[x for x in lay.traces if x is not t] + [Trace(net, left), Trace(net, right)])


@pytest.mark.parametrize("net", ["DC+", "DC-"])
def test_net_split(good, net):
    assert "net_split" not in rules(good)
    assert "net_split" in rules(_split(good, net))


@pytest.mark.parametrize("shape", [
    box(0, 0, 5e-3, 5e-3).union(box(5e-3, 4.9e-3, 10e-3, 9.9e-3)),  # 0.1 mm shared edge
    box(0, 0, 5e-3, 5e-3).union(box(4.9e-3, 4.9e-3, 9.9e-3, 9.9e-3)),  # 0.1 x 0.1 mm corner overlap
])
def test_min_trace_width_neck(good, shape):
    assert "min_trace_width" in rules(dataclasses.replace(good, traces=[*good.traces, Trace("DC-", shape)]))


def test_min_trace_width_wide_joint_ok(good):
    shape = box(0, 0, 5e-3, 5e-3).union(box(5e-3, 1e-3, 10e-3, 4e-3))  # 3 mm wide joint
    assert "min_trace_width" not in rules(dataclasses.replace(good, traces=[*good.traces, Trace("DC-", shape)]))


def test_min_trace_width_dead_band(good):
    t = next(t for t in good.traces if t.net == "DC-")
    minx, _, _, maxy = t.polygon.bounds

    def stub(width):
        poly = t.polygon.union(box(minx + 0.010, maxy, minx + 0.010 + width, maxy + 0.006))
        return rules(dataclasses.replace(good, traces=_swap(good.traces, t, Trace("DC-", poly))))

    assert "min_trace_width" not in stub(1.0e-3)
    assert "min_trace_width" in stub(0.9997e-3)


@pytest.mark.parametrize("gap", [0.0, 0.5e-3])
def test_die_terminal_clearance(good, gap):
    hs = _hs(good)
    tm = good.terminals["DC+"]
    moved = dataclasses.replace(hs, cx=tm.cx - (tm.w / 2 + hs.w / 2 + gap), cy=tm.cy)
    bad = dataclasses.replace(good, dies=_swap(good.dies, hs, moved))
    assert "die_on_terminal" in rules(bad)
    far = dataclasses.replace(hs, cx=tm.cx - (tm.w / 2 + hs.w / 2 + 1.5e-3), cy=tm.cy)
    assert "die_on_terminal" not in rules(dataclasses.replace(good, dies=_swap(good.dies, hs, far)))


def test_wire_start_margin(good):
    hs = _hs(good)
    w = next(w for w in good.wires if _start_on(w, hs))
    x0, y0, x1, y1 = hs.pads["source"]
    for xy in ((x0, w.points[0, 1]), (x0 + 0.05e-3, w.points[0, 1]), (w.points[0, 0], y1)):
        p = w.points.copy()
        p[0, :2] = xy
        bad = dataclasses.replace(good, wires=_swap(good.wires, w, dataclasses.replace(w, points=p)))
        assert "wire_start" in rules(bad)


def test_die_without_source_pad(good):
    hs = _hs(good)
    nopad = dataclasses.replace(hs, pads={k: v for k, v in hs.pads.items() if k != "source"})
    r = rules(dataclasses.replace(good, dies=_swap(good.dies, hs, nopad)))  # must not raise
    assert "die_no_source_pad" in r
    assert "die_no_source_pad" not in rules(good)


def _ring(neck):
    """20 mm square ring, 2 mm legs; the loop closes through a `neck`-wide overlap on the right side."""
    return unary_union([box(0, 0, 20e-3, 2e-3), box(0, 0, 2e-3, 20e-3), box(0, 18e-3, 21.9e-3, 20e-3),
                        box(18e-3, 0, 20e-3, 10e-3), box(20e-3 - neck, 10e-3, 21.9e-3, 20e-3)])


def test_min_trace_width_loop_closing_neck(good):
    ring = _ring(0.1e-3)
    assert ring.geom_type == "Polygon" and len(ring.interiors) == 1
    assert "min_trace_width" in rules(dataclasses.replace(good, traces=[*good.traces, Trace("DC-", ring)]))
    wide = unary_union([box(0, 0, 20e-3, 2e-3), box(0, 0, 2e-3, 20e-3), box(0, 18e-3, 20e-3, 20e-3),
                        box(18e-3, 0, 20e-3, 20e-3)])  # same ring, loop closed by a full-width leg
    assert len(wide.interiors) == 1
    assert "min_trace_width" not in rules(dataclasses.replace(good, traces=[*good.traces, Trace("DC-", wide)]))


def test_die_bad_switch(good):
    hs = _hs(good)
    for sw in ("hs", "", "XX"):
        bad = dataclasses.replace(good, dies=_swap(good.dies, hs, dataclasses.replace(hs, switch=sw)))
        r = rules(bad)  # must not raise
        assert "die_bad_switch" in r
        assert "die_wrong_net" not in r and "wire_net" not in r  # switch-dependent rules skipped for that die
    assert "die_bad_switch" not in rules(good)


def test_wire_start_margin_scales_with_diameter(good):
    hs = _hs(good)
    w = next(w for w in good.wires if _start_on(w, hs))
    x0, _, _, _ = hs.pads["source"]

    def with_(dia, inset):
        p = w.points.copy()
        p[0, 0] = x0 + inset
        return rules(dataclasses.replace(good, wires=_swap(good.wires, w, dataclasses.replace(
            w, points=p, diameter=dia))))

    assert "wire_start" in with_(0.5e-3, 0.2e-3)  # < d/2 = 0.25 mm
    assert "wire_start" not in with_(0.5e-3, 0.3e-3)
    assert "wire_start" not in with_(0.2e-3, 0.2e-3)  # default margin 0.15 mm governs thin wires
