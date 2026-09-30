import dataclasses

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from moduleforge.geometry import decompose_polygon, default_amb_stack
from moduleforge.generate.halfbridge import generate_layouts


@pytest.fixture(scope="module")
def layouts():
    return generate_layouts(6, seed=7)


def test_decompose_l_shape_area_and_disjoint():
    L = Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)])
    rects = decompose_polygon(L)
    assert sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects) == pytest.approx(L.area, rel=1e-12)
    assert L.area == pytest.approx(4 + 2)
    boxes = [box(*r) for r in rects]
    assert sum(b.area for b in boxes) == pytest.approx(box(*[0, 0, 4, 3]).union(L).intersection(L).area)
    from shapely.ops import unary_union
    assert unary_union(boxes).symmetric_difference(L).area < 1e-12


def test_decompose_with_hole():
    P = box(0, 0, 4, 4).difference(box(1, 1, 3, 3))
    rects = decompose_polygon(P)
    assert sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects) == pytest.approx(12.0, rel=1e-12)


def test_conductor_model_preserves_copper_area(layouts):
    for lay in layouts:
        cm = lay.to_conductors()
        for net in ("DC+", "DC-", "PHASE"):
            expect = sum(t.polygon.area for t in lay.traces if t.net == net)
            assert cm.copper_area(net) == pytest.approx(expect, rel=1e-9)
        z0, z1 = lay.stack.z_bottom("top_cu"), lay.stack.z_top("top_cu")
        assert all(r.z == z0 and r.thickness == pytest.approx(z1 - z0) and r.sigma == 5.8e7 for r in cm.rects)


def test_conductor_model_wires_planes_dies_port(layouts):
    lay = layouts[0]
    cm = lay.to_conductors()
    assert len(cm.wires) == sum(len(w.points) - 1 for w in lay.wires)
    # segments chain into the original polyline length
    assert sum(np.linalg.norm(np.subtract(s.p1, s.p0)) for s in cm.wires) == pytest.approx(
        sum(w.length for w in lay.wires), rel=1e-12)
    names = {p.name: p for p in cm.planes}
    assert set(names) == {"backside_cu", "baseplate"}
    sb = lay.outline.bounds
    bb = names["backside_cu"].bounds
    assert bb == pytest.approx((sb[0] + 1e-3, sb[1] + 1e-3, sb[2] - 1e-3, sb[3] - 1e-3), abs=1e-12)  # inset
    assert names["baseplate"].bounds == pytest.approx(lay.baseplate_outline.bounds)
    assert names["baseplate"].bounds[2] - names["baseplate"].bounds[0] > sb[2] - sb[0]  # larger than substrate
    assert names["baseplate"].z_bottom == 0.0 and names["baseplate"].thickness == pytest.approx(3e-3)
    assert len(cm.shorts) == 2 * lay.dies_per_switch
    assert {s.bottom_net for s in cm.shorts if s.switch == "HS"} == {"DC+"}
    assert {s.bottom_net for s in cm.shorts if s.switch == "LS"} == {"PHASE"}
    assert all(s.z_top > s.z_bottom for s in cm.shorts)
    zt = lay.stack.z_top("top_cu")
    assert cm.port.phase_open and cm.port.p_pos[2] == zt == cm.port.p_neg[2]
    assert cm.port.p_pos[:2] == pytest.approx((lay.terminals["DC+"].cx, lay.terminals["DC+"].cy))
    assert cm.port.p_neg[:2] == pytest.approx((lay.terminals["DC-"].cx, lay.terminals["DC-"].cy))


def test_wire_endpoints_z(layouts):
    lay = layouts[0]
    zt = lay.stack.z_top("top_cu")
    for w in lay.wires:
        assert w.points[-1, 2] == pytest.approx(zt)  # lands on Cu
        assert w.points[0, 2] > zt  # starts on the die top
        assert w.points[:, 2].max() > w.points[0, 2]  # loop rises above start


def test_fingerprint_stable_and_sensitive(layouts):
    lay = layouts[0]
    assert lay.fingerprint() == lay.fingerprint()
    assert len({la.fingerprint() for la in layouts}) == len(layouts)
    moved = dataclasses.replace(lay, dies=[dataclasses.replace(lay.dies[0], cx=lay.dies[0].cx + 1e-6),
                                           *lay.dies[1:]])
    assert moved.fingerprint() != lay.fingerprint()
    assert dataclasses.replace(lay, stack=default_amb_stack()).fingerprint() != lay.fingerprint()


def _with_layer(lay, name, **kw):
    layers = tuple(dataclasses.replace(la, **kw) if la.name == name else la for la in lay.stack.layers)
    return dataclasses.replace(lay, stack=dataclasses.replace(lay.stack, layers=layers))


def test_fingerprint_deterministic_and_covers_conductor_inputs():
    g = generate_layouts(1, seed=7, dies_per_switch=2)[0]
    f0 = g.fingerprint()
    assert generate_layouts(1, seed=7, dies_per_switch=2)[0].fingerprint() == f0
    d0 = g.dies[0]
    variants = {
        "top_cu sigma": _with_layer(g, "top_cu", sigma=5.0e7),
        "backside_cu sigma": _with_layer(g, "backside_cu", sigma=5.0e7),
        "baseplate sigma": _with_layer(g, "baseplate", sigma=5.0e7),
        "ceramic k": _with_layer(g, "ceramic", k=90.0),
        "ceramic material": _with_layer(g, "ceramic", material="other"),
        "top_cu thickness": _with_layer(g, "top_cu", thickness=g.stack.layer("top_cu").thickness + 10e-6),
        "backside_inset": dataclasses.replace(g, backside_inset=g.backside_inset + 0.5e-3),
        "wire_sigma": dataclasses.replace(g, wire_sigma=g.wire_sigma * 0.9),
        "die attach_thickness": dataclasses.replace(
            g, dies=[dataclasses.replace(d0, attach_thickness=d0.attach_thickness + 20e-6), *g.dies[1:]]),
        "die thickness": dataclasses.replace(
            g, dies=[dataclasses.replace(d0, thickness=d0.thickness + 20e-6), *g.dies[1:]]),
        "die switch": dataclasses.replace(
            g, dies=[dataclasses.replace(d0, switch="LS" if d0.switch == "HS" else "HS"), *g.dies[1:]]),
    }
    for name, v in variants.items():
        assert v.fingerprint() != f0, name


def test_fingerprint_conductivity_relative_rounding():
    g = generate_layouts(1, seed=7)[0]
    sigma = g.stack.layer("top_cu").sigma
    # sub-1e-12 relative change is absorbed; 1e-6 relative change is not (a 1 nm grid would fail both)
    assert _with_layer(g, "top_cu", sigma=sigma * (1 + 1e-14)).fingerprint() == g.fingerprint()
    assert _with_layer(g, "top_cu", sigma=sigma * (1 + 1e-6)).fingerprint() != g.fingerprint()


def test_die_shorts_span_trace_top_to_die_top(layouts):
    for lay in layouts:
        z1 = lay.top_cu_z()[1]
        shorts = lay.to_conductors().shorts
        assert len(shorts) == len(lay.dies)
        for s, d in zip(shorts, lay.dies, strict=True):
            assert s.z_bottom == pytest.approx(z1, abs=1e-12)
            assert s.z_top == pytest.approx(lay.die_z_range(d)[1], abs=1e-12)
            assert s.z_top - s.z_bottom == pytest.approx(d.attach_thickness + d.thickness, abs=1e-12)
            assert s.z_top - s.z_bottom == pytest.approx(230e-6, abs=1e-12)
