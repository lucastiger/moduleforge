import dataclasses
import inspect
import itertools
import re

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import (
    DC_MINUS,
    NETS,
    PHASE,
    BondWire,
    Die,
    Layer,
    LayerStack,
    Layout,
    Terminal,
    Trace,
    decompose_polygon,
    default_amb_stack,
)
from moduleforge.geometry.stack import LAYER_ORDER


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


# --- Fingerprint pins: one test per hashed field of the Layout IR -------------------------------------------------
# A pin is (path, change). ``path`` walks the IR from the Layout: attribute names on dataclasses, indices into
# lists/tuples, keys into dicts, and "*" for *every* element of a list/dict in turn. ``change`` maps the value found
# there to a different one, far above the 1 nm / 12-significant-digit quantization. A fingerprint that ignored the
# field, or normalised it to a constant, therefore fails the pin. The completeness test below derives the set of IR
# fields from ``dataclasses.fields`` so that a new IR field cannot go unpinned silently.

FP_EXEMPT = {"BondWire.loop_height", "Terminal.net"}  # exactly the fingerprint docstring's 'Not covered' list
_IR_CLASSES = (Layout, Trace, Die, BondWire, Terminal, LayerStack, Layer)
# Containers: pinned through the fields of their elements, not as a whole.
_CONTAINERS = {"Layout.stack", "Layout.traces", "Layout.dies", "Layout.wires", "LayerStack.layers"}
# Hashed, but not a free input: LayerStack.__post_init__ forces the layer names to LAYER_ORDER.
_FIXED = {"Layer.name"}
_UM = 1e-6


def _bump(v):
    """Strictly different for every float, including the ceramic's sigma = 0."""
    return v * 1.1 + 1.0


def _grow(poly):
    return poly.buffer(1e-3, join_style="mitre")


def _other_net(net):
    return next(n for n in NETS if n != net)


def _raise_apex(points):
    p = points.copy()
    p[len(p) // 2, 2] += 10 * _UM
    return p


_LAYER_CHANGES = {"material": lambda m: m + "-x", "thickness": lambda t: t + 10 * _UM, "sigma": _bump, "k": _bump}

FP_PINS = {
    "family": (("family",), lambda f: f + "-x"),
    "dies_per_switch": (("dies_per_switch",), lambda n: n + 1),
    "substrate outline": (("outline",), _grow),
    "baseplate outline": (("baseplate_outline",), _grow),
    "backside_inset": (("backside_inset",), lambda v: v + 0.5e-3),
    "wire_sigma": (("wire_sigma",), lambda v: v * 0.9),
    "stack kind": (("stack", "kind"), lambda k: k + "-relabelled"),
    "trace net": (("traces", "*", "net"), _other_net),
    "trace polygon": (("traces", "*", "polygon"), _grow),
    **{f"die {f}": (("dies", "*", f), lambda v: v + 10 * _UM)
       for f in ("cx", "cy", "w", "h", "thickness", "attach_thickness")},
    "die switch": (("dies", "*", "switch"), {"HS": "LS", "LS": "HS"}.__getitem__),
    "die source pad": (("dies", "*", "pads", "source"), lambda r: tuple(c + 10 * _UM for c in r)),
    "die gate pad": (("dies", "*", "pads", "gate"), lambda r: tuple(c + 10 * _UM for c in r)),
    "die pad names": (("dies", "*", "pads"), lambda p: {("kelvin" if k == "source" else k): r for k, r in p.items()}),
    "wire points": (("wires", "*", "points"), _raise_apex),
    "wire diameter": (("wires", "*", "diameter"), lambda v: v * 1.1),
    "wire net": (("wires", "*", "net"), _other_net),
    **{f"terminal {f}": (("terminals", "*", f), lambda v: v + 10 * _UM) for f in ("cx", "cy", "w", "h")},
    "terminal names": (("terminals",), lambda ts: {("AC" if k == PHASE else k): t for k, t in ts.items()}),
    **{f"{n} {f}": (("stack", "layers", LAYER_ORDER.index(n), f), change)
       for n in LAYER_ORDER for f, change in _LAYER_CHANGES.items()},
}


def _step(obj, key):
    return getattr(obj, key) if dataclasses.is_dataclass(obj) else obj[key]


def _get(obj, path):
    for key in path:
        obj = _step(obj, key)
    return obj


def _set(obj, path, change):
    """Copy of ``obj`` with ``change`` applied at ``path``; nothing is mutated in place."""
    if not path:
        return change(obj)
    key, rest = path[0], path[1:]
    if dataclasses.is_dataclass(obj):
        return dataclasses.replace(obj, **{key: _set(getattr(obj, key), rest, change)})
    if isinstance(obj, dict):
        return {**obj, key: _set(obj[key], rest, change)}
    items = list(obj)
    items[key] = _set(items[key], rest, change)
    return type(obj)(items)


def _concrete(obj, path):
    """Expand every "*" in ``path`` into each index/key of that list or dict."""
    if not path:
        yield ()
        return
    key, rest = path[0], path[1:]
    keys = (sorted(obj) if isinstance(obj, dict) else range(len(obj))) if key == "*" else (key,)
    for k in keys:
        for tail in _concrete(_step(obj, k), rest):
            yield (k, *tail)


def _field_label(obj, path):
    """'Class.field' of the last dataclass attribute on ``path``."""
    label = None
    for key in path:
        if dataclasses.is_dataclass(obj):
            label = f"{type(obj).__name__}.{key}"
        obj = _step(obj, key)
    return label


def _same(a, b):
    if isinstance(a, np.ndarray):
        return np.array_equal(a, b)
    if isinstance(a, BaseGeometry):
        return a.equals(b)
    return a == b


@pytest.fixture(scope="module")
def g2():
    return generate_layouts(1, seed=7, dies_per_switch=2)[0]


@pytest.mark.parametrize("name", list(FP_PINS))
def test_fingerprint_pins_each_hashed_field(g2, name):
    path, change = FP_PINS[name]
    f0 = g2.fingerprint()
    paths = list(_concrete(g2, path))
    assert paths, name
    for p in paths:
        v = _set(g2, p, change)
        assert not _same(_get(v, p), _get(g2, p)), f"{name} at {p}: the change is a no-op, so the pin is vacuous"
        assert v.fingerprint() != f0, f"the fingerprint ignores {name} at {p}"
    assert g2.fingerprint() == f0  # the fixture was not mutated


def test_fingerprint_pin_table_covers_every_ir_field(g2):
    ir_fields = {f"{c.__name__}.{f.name}" for c in _IR_CLASSES for f in dataclasses.fields(c)}
    assert FP_EXEMPT | _CONTAINERS | _FIXED <= ir_fields
    pinned = {_field_label(g2, next(_concrete(g2, path))) for path, _ in FP_PINS.values()}
    assert pinned == ir_fields - FP_EXEMPT - _CONTAINERS - _FIXED
    # every layer x every free Layer field, and every pad name present on the dies
    layer_pins = {path[2:] for path, _ in FP_PINS.values() if path[:2] == ("stack", "layers")}
    assert layer_pins == {(i, f.name) for i in range(len(LAYER_ORDER)) for f in dataclasses.fields(Layer)
                          if f"Layer.{f.name}" not in _FIXED}
    pad_pins = {path[3] for path, _ in FP_PINS.values() if path[:3] == ("dies", "*", "pads") and len(path) == 4}
    assert pad_pins == {k for d in g2.dies for k in d.pads} == {"source", "gate"}
    # element fields of lists/dicts are pinned on every element, not only the first
    for path, _ in FP_PINS.values():
        for i, key in enumerate(path[:-1]):
            if key in ("traces", "dies", "wires", "terminals"):
                assert path[i + 1] == "*", path


@pytest.mark.parametrize("path", [("wires", 0, "loop_height"), ("terminals", PHASE, "net")])
def test_fingerprint_ignores_exactly_the_documented_fields(g2, path):
    assert _field_label(g2, path) in FP_EXEMPT
    changed = _set(g2, path, lambda v: v * 2 if isinstance(v, float) else v + "-x")
    assert not _same(_get(changed, path), _get(g2, path))
    assert changed.fingerprint() == g2.fingerprint()


def test_fingerprint_docstring_not_covered_list_is_exact():
    doc = " ".join(inspect.getdoc(Layout.fingerprint).split())
    assert "thermal" not in doc  # there is no thermal model to cover
    assert "1 nm per field" in doc and "12 significant digits" in doc
    head, not_covered = doc.split("Not covered", 1)
    assert set(re.findall(r"``(\w+\.\w+)``", not_covered)) == FP_EXEMPT
    assert "kind" in head


def _map_lengths(v, f):
    """Apply ``f`` to every length inside a scalar, coordinate tuple, point array or polygon."""
    if isinstance(v, BaseGeometry):
        return shapely.transform(v, f)
    if isinstance(v, tuple):
        return tuple(float(f(c)) for c in v)
    return f(v)


_QUANTUM_PATHS = {
    "die cx": ("dies", 0, "cx"),
    "die attach_thickness": ("dies", 1, "attach_thickness"),
    "die source pad": ("dies", 2, "pads", "source"),
    "wire points": ("wires", 0, "points"),
    "wire diameter": ("wires", 0, "diameter"),
    "terminal cy": ("terminals", DC_MINUS, "cy"),
    "trace polygon": ("traces", 0, "polygon"),
    "substrate outline": ("outline",),
    "top_cu thickness": ("stack", "layers", LAYER_ORDER.index("top_cu"), "thickness"),
    "backside_inset": ("backside_inset",),
}


@pytest.mark.parametrize("name", list(_QUANTUM_PATHS))
def test_fingerprint_length_quantum_is_1nm_on_both_sides(g2, name):
    path = _QUANTUM_PATHS[name]
    # Snap the field onto the 1 nm grid first, so that no shift below starts next to a rounding tie.
    base = _set(g2, path, lambda v: _map_lengths(v, lambda c: np.round(np.asarray(c) * 1e9) / 1e9))
    f0 = base.fingerprint()
    for dx in (0.01e-9, -0.01e-9, 0.4e-9, -0.4e-9):  # below half a quantum: absorbed
        assert _set(base, path, lambda v, dx=dx: _map_lengths(v, lambda c: c + dx)).fingerprint() == f0, dx
    for dx in (1e-9, -1e-9, 2e-9):  # one quantum or more: seen
        assert _set(base, path, lambda v, dx=dx: _map_lengths(v, lambda c: c + dx)).fingerprint() != f0, dx


def test_fingerprint_length_quantum_on_unsnapped_generator_output(g2):
    d0 = g2.dies[0]

    def shifted(dx):
        return dataclasses.replace(g2, dies=[dataclasses.replace(d0, cx=d0.cx + dx), *g2.dies[1:]])

    assert shifted(0.01e-9).fingerprint() == g2.fingerprint()
    assert shifted(2e-9).fingerprint() != g2.fingerprint()


def test_fingerprint_rounding_boundary_is_not_absorbed(g2):
    # The docstring promises no absorption below the quantum: a 0.002 nm change across a half-nanometre boundary is
    # seen, the same change away from the boundary is not.
    path = ("dies", 0, "cx")
    n = round(g2.dies[0].cx * 1e9)
    at = {off: _set(g2, path, lambda _, off=off: (n + off) * 1e-9).fingerprint() for off in (0.2, 0.202, 0.499, 0.501)}
    assert at[0.2] == at[0.202]
    assert at[0.499] != at[0.501]


# --- Re-pairing pins: every value is hashed with the element and the field that carry it -------------------------
# A fingerprint that hashed a field's values apart from their elements (say the sorted trace nets, then the
# polygons) would see every single-value change above, yet miss an exchange of values between two elements, which
# changes the conductor model (e.g. which net each RectCell or WireSegment belongs to). The same holds for an
# exchange between two fields of one element (die cx <-> cy, outline <-> baseplate_outline). Each exchange below is
# made between two different values; where the layout has none, the first value is changed first.

_ELEMENT_FIELDS = {
    ("traces",): ("net", "polygon"),
    ("dies",): ("cx", "cy", "w", "h", "switch", "thickness", "attach_thickness", "pads"),
    ("wires",): ("points", "diameter", "net"),
    ("terminals",): ("cx", "cy", "w", "h"),
    ("stack", "layers"): ("material", "thickness", "sigma", "k"),
}
# (container, field within each element): the values of ``field`` are exchanged between two elements of container.
FP_SWAPS = {
    **{f"{c[-1]} {f}": (c, (f,)) for c, fs in _ELEMENT_FIELDS.items() for f in fs},
    "die pad name/rectangle": (("dies", "*", "pads"), ()),  # each die's source and gate rectangles exchanged
}


def _perturb(v):
    if isinstance(v, str):
        return v + "-x"
    if isinstance(v, float):
        return _bump(v)
    if isinstance(v, tuple):
        return tuple(c + 10 * _UM for c in v)
    if isinstance(v, np.ndarray):
        return _raise_apex(v)
    if isinstance(v, BaseGeometry):
        return _grow(v)
    raise TypeError(type(v))


def _exchange(lay, pa, pb):
    """Copy of ``lay`` with the values at paths ``pa`` and ``pb`` exchanged (``pa``'s changed first if equal)."""
    if _same(_get(lay, pa), _get(lay, pb)):
        lay = _set(lay, pa, _perturb)
    va, vb = _get(lay, pa), _get(lay, pb)
    assert not _same(va, vb)  # a real exchange, not a no-op
    return lay, _set(_set(lay, pa, lambda _: vb), pb, lambda _: va)


def _keys(container):
    return sorted(container) if isinstance(container, dict) else list(range(len(container)))


@pytest.mark.parametrize("name", list(FP_SWAPS))
def test_fingerprint_pairs_values_with_their_element(g2, name):
    container, field = FP_SWAPS[name]
    for cpath in _concrete(g2, container):
        c = _get(g2, cpath)
        pairs = list(itertools.combinations(_keys(c), 2))
        a, b = next(((a, b) for a, b in pairs if not _same(_get(c, (a, *field)), _get(c, (b, *field)))), pairs[0])
        base, swapped = _exchange(g2, (*cpath, a, *field), (*cpath, b, *field))
        assert swapped.fingerprint() != base.fingerprint(), f"{name}: exchanging {a} and {b} at {cpath} is not seen"


def _element_paths(lay):
    """One instance path per IR dataclass: the Layout itself, its stack, and the first of every list/dict."""
    yield ()
    yield ("stack",)
    for c in _ELEMENT_FIELDS:
        yield (*c, _keys(_get(lay, c))[0])


def _same_type_field_pairs(lay):
    for ep in _element_paths(lay):
        el = _get(lay, ep)
        free = [f for f in dataclasses.fields(el) if f"{type(el).__name__}.{f.name}" not in FP_EXEMPT | _FIXED]
        for fa, fb in itertools.combinations(free, 2):
            if fa.type == fb.type:
                yield f"{type(el).__name__}.{fa.name}<->{fb.name}", (*ep, fa.name), (*ep, fb.name)


_FIELD_SWAPS = {name: (pa, pb) for name, pa, pb in _same_type_field_pairs(generate_layouts(1, seed=7,
                                                                                           dies_per_switch=2)[0])}


@pytest.mark.parametrize("name", list(_FIELD_SWAPS))
def test_fingerprint_pairs_values_with_their_field(g2, name):
    base, swapped = _exchange(g2, *_FIELD_SWAPS[name])
    assert swapped.fingerprint() != base.fingerprint(), f"exchanging {name} is not seen"


def test_fingerprint_repairing_tables_cover_every_element_field(g2):
    element_classes = {"Trace", "Die", "BondWire", "Terminal", "Layer"}
    pinned = {_field_label(g2, next(_concrete(g2, path))) for path, _ in FP_PINS.values()}
    swapped = {_field_label(g2, (*c, _keys(_get(g2, c))[0], *f)) for c, f in FP_SWAPS.values() if f}
    assert swapped == {label for label in pinned if label.split(".")[0] in element_classes}
    assert {"Layout.outline<->baseplate_outline", "Die.cx<->cy", "Die.w<->h", "Terminal.cx<->cy",
            "Layer.sigma<->k"} <= set(_FIELD_SWAPS)


def test_fingerprint_order_semantics_match_docstring(g2):
    f0 = g2.fingerprint()
    for key in ("traces", "dies", "wires"):  # hashed in list order
        assert dataclasses.replace(g2, **{key: getattr(g2, key)[::-1]}).fingerprint() != f0, key
    # pads and terminals are hashed sorted by name: dict insertion order does not matter
    reordered = dataclasses.replace(
        g2, terminals=dict(reversed(g2.terminals.items())),
        dies=[dataclasses.replace(d, pads=dict(reversed(d.pads.items()))) for d in g2.dies])
    assert [list(d.pads) for d in reordered.dies] != [list(d.pads) for d in g2.dies]
    assert list(reordered.terminals) != list(g2.terminals)
    assert reordered.fingerprint() == f0
