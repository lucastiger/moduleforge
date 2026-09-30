"""Manufacturing design rules (DRC) for wire-bonded DBC/AMB half-bridge layouts.

Default values are *typical* DBC/AMB design-guide numbers (Rogers/curamik and Heraeus/Kyocera substrate
design guidelines for 0.3 mm Cu: min. trace width ~1 mm, min. Cu-Cu isolation spacing ~1 mm, Cu-to-ceramic-edge
margin ~1 mm; die-to-Cu-edge margin ~1 mm; Al wire bonding pitch >= ~2 wire diameters; heavy Al bond wire
diameters ~100-500 um as in Heraeus / Hesse Bondtec heavy-Al-wire product ranges). They are placeholders
to be replaced with the customer's vendor rules; all lengths are SI (m).
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from moduleforge.geometry import Layout
from moduleforge.geometry.units import mm_to_m

TOL = 1e-9  # geometric comparison tolerance, 1 nm
WIDTH_TOL = 1e-7  # min_trace_width tolerance, 0.1 um: well above GEOS buffer precision (~1e-9 m at mm scale)


@dataclass(frozen=True)
class DesignRules:
    min_trace_width: float = mm_to_m(1.0)
    min_spacing: float = mm_to_m(1.0)
    edge_margin: float = mm_to_m(1.0)
    die_edge_margin: float = mm_to_m(1.0)
    die_spacing: float = mm_to_m(1.0)
    min_wire_length: float = mm_to_m(1.5)
    max_wire_length: float = mm_to_m(15.0)
    min_wire_pitch: float = mm_to_m(0.6)  # 2 x 0.3 mm wire diameter
    wire_landing_margin: float = mm_to_m(0.3)
    wire_pitch_diameters: float = 2.0  # pitch >= this many wire diameters (module docstring: ~2)
    min_wire_diameter: float = mm_to_m(0.1)  # placeholder, heavy Al wire (see module docstring)
    max_wire_diameter: float = mm_to_m(0.5)  # placeholder, heavy Al wire (see module docstring)
    # placeholder: same-net die-to-terminal-pad clearance, equal to the die-to-Cu-edge margin (1 mm)
    die_terminal_clearance: float = mm_to_m(1.0)
    # placeholder: a bond foot must sit >= half a typical 0.3 mm heavy-Al wire diameter inside the pad edge
    # so the wedge footprint does not overhang the metallisation
    wire_start_margin: float = mm_to_m(0.15)


DEFAULT_RULES = DesignRules()


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    where: tuple[float, float] | None = None


def _pt(g):
    c = g.representative_point()
    return (float(c.x), float(c.y))


def _topology(g) -> tuple[int, int]:
    """(number of polygon pieces, total number of holes) of a shapely geometry."""
    polys = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]
    return len(polys), sum(len(p.interiors) for p in polys)


def check(layout: Layout, rules: DesignRules = DEFAULT_RULES) -> list[Violation]:
    """Return all rule violations (empty list = DRC clean)."""
    v: list[Violation] = []
    mit = {"join_style": "mitre", "mitre_limit": 10.0}

    # min_trace_width: morphological opening with a square element of side min width
    r = rules.min_trace_width / 2 - WIDTH_TOL
    for i, t in enumerate(layout.traces):
        opened = t.polygon.buffer(-r, **mit).buffer(r, **mit)
        thin = t.polygon.difference(opened)
        if thin.area > 1e-12:
            v.append(Violation("min_trace_width", f"trace {i} ({t.net}) narrower than min width", _pt(thin)))
            continue
        # necks: eroding by half the min width must not split the trace into more pieces than it has, nor
        # close a hole into the outside (a neck closing a copper loop turns the ring into a C: one piece, fewer holes)
        eroded = t.polygon.buffer(-r, **mit)
        if (_topology(eroded)[0] > _topology(t.polygon)[0]) or (_topology(eroded)[1] < _topology(t.polygon)[1]):
            v.append(Violation("min_trace_width", f"trace {i} ({t.net}) has a neck narrower than min width",
                               _pt(t.polygon)))

    # net_split: each net's copper must be a single connected island
    for net in sorted({t.net for t in layout.traces}):
        merged = unary_union([t.polygon for t in layout.traces if t.net == net])
        if len(getattr(merged, "geoms", [merged])) > 1:
            v.append(Violation("net_split", f"net {net} copper is split into {len(merged.geoms)} islands",
                               _pt(merged)))

    # min_spacing
    for i in range(len(layout.traces)):
        for j in range(i + 1, len(layout.traces)):
            a, b = layout.traces[i], layout.traces[j]
            d = a.polygon.distance(b.polygon)
            if d < rules.min_spacing - TOL:
                v.append(Violation("min_spacing", f"traces {i}/{j} spacing {d:.3e} m", _pt(a.polygon)))

    # edge margin
    safe = layout.outline.buffer(-(rules.edge_margin - TOL), **mit)
    for i, t in enumerate(layout.traces):
        if not safe.contains(t.polygon):
            v.append(Violation("edge_margin", f"trace {i} ({t.net}) closer to substrate edge than margin",
                               _pt(t.polygon)))

    # die placement, net and margin
    want = {"HS": "DC+", "LS": "PHASE"}
    for i, d in enumerate(layout.dies):
        if d.switch not in want:
            v.append(Violation("die_bad_switch", f"die {i} has unknown switch {d.switch!r} (expected HS or LS)",
                               (d.cx, d.cy)))
        host = [t for t in layout.traces if t.polygon.contains(Point(d.cx, d.cy))]
        if not host:
            v.append(Violation("die_off_trace", f"die {i} not on any trace", (d.cx, d.cy)))
            continue
        if d.switch in want and host[0].net != want[d.switch]:
            v.append(Violation("die_wrong_net", f"die {i} ({d.switch}) on {host[0].net}", (d.cx, d.cy)))
        if not host[0].polygon.buffer(-(rules.die_edge_margin - TOL), **mit).contains(d.box):
            v.append(Violation("die_edge_margin", f"die {i} closer to trace edge than margin", (d.cx, d.cy)))
    for i in range(len(layout.dies)):
        for j in range(i + 1, len(layout.dies)):
            dist = layout.dies[i].box.distance(layout.dies[j].box)
            if dist < rules.die_spacing - TOL:
                v.append(Violation("die_spacing", f"dies {i}/{j} spacing {dist:.3e} m",
                                   (layout.dies[i].cx, layout.dies[i].cy)))

    # die / terminal keep-outs and switch presence
    pads = {net: box(tm.cx - tm.w / 2, tm.cy - tm.h / 2, tm.cx + tm.w / 2, tm.cy + tm.h / 2)
            for net, tm in layout.terminals.items()}
    for i, d in enumerate(layout.dies):
        for net, pad in pads.items():
            if d.box.buffer(-TOL).intersects(pad):
                v.append(Violation("die_on_terminal", f"die {i} overlaps terminal {net}", (d.cx, d.cy)))
            elif d.box.distance(pad) < rules.die_terminal_clearance - TOL:
                v.append(Violation("die_on_terminal", f"die {i} closer than clearance to terminal {net}",
                                   (d.cx, d.cy)))
    for sw in ("HS", "LS"):
        if not any(d.switch == sw for d in layout.dies):
            v.append(Violation("missing_switch", f"layout has no {sw} die"))

    # wires
    def on_source(d, x, y):
        p = d.pads.get("source")
        if p is None:
            return False
        return p[0] - TOL <= x <= p[2] + TOL and p[1] - TOL <= y <= p[3] + TOL

    for i, d in enumerate(layout.dies):
        if "source" not in d.pads:
            v.append(Violation("die_no_source_pad", f"die {i} ({d.switch}) has no source pad", (d.cx, d.cy)))

    expect = {"HS": "PHASE", "LS": "DC-"}
    bonded: set[int] = set()
    lines = []
    for i, w in enumerate(layout.wires):
        xy = (float(w.points[0, 0]), float(w.points[0, 1]))
        if not (rules.min_wire_length - TOL <= w.length <= rules.max_wire_length + TOL):
            v.append(Violation("wire_length", f"wire {i} length {w.length:.3e} m", xy))
        if not (rules.min_wire_diameter - TOL <= w.diameter <= rules.max_wire_diameter + TOL):
            v.append(Violation("wire_diameter", f"wire {i} diameter {w.diameter:.3e} m", xy))
        end = Point(w.points[-1, 0], w.points[-1, 1])
        ok = any(
            t.net == w.net and t.polygon.buffer(-(rules.wire_landing_margin - TOL), **mit).contains(end)
            for t in layout.traces
        )
        if not ok:
            v.append(Violation("wire_landing", f"wire {i} does not land on {w.net} Cu", (end.x, end.y)))
        if any(end.distance(g) < rules.wire_landing_margin - TOL
               for g in [d.box for d in layout.dies] + list(pads.values())):
            v.append(Violation("wire_landing_keepout", f"wire {i} lands too close to a die or terminal pad",
                               (end.x, end.y)))
        owners = [k for k, d in enumerate(layout.dies) if on_source(d, *xy)]
        if not owners:
            v.append(Violation("wire_start", f"wire {i} does not start on a die source pad", xy))
        else:
            bonded.update(owners)
            margin = max(rules.wire_start_margin, w.diameter / 2)  # bond foot must not overhang the pad
            if not any(box(*layout.dies[k].pads["source"]).buffer(-(margin - TOL), **mit)
                       .intersects(Point(xy)) for k in owners):
                v.append(Violation("wire_start", f"wire {i} starts closer than margin to its source-pad edge", xy))
            want_net = expect.get(layout.dies[owners[0]].switch)
            under = [t.net for t in layout.traces if t.polygon.buffer(TOL).contains(end)]
            if want_net is not None and (w.net != want_net or (under and want_net not in under)):
                v.append(Violation("wire_net", f"wire {i} from a {layout.dies[owners[0]].switch} die must land "
                                   f"on {want_net}; labelled {w.net}, copper under landing {under}", (end.x, end.y)))
        lines.append(LineString(w.points[:, :2]))
    for k, d in enumerate(layout.dies):
        if k not in bonded:
            v.append(Violation("die_unbonded", f"die {k} ({d.switch}) has no wire on its source pad", (d.cx, d.cy)))
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            d = lines[i].distance(lines[j])
            need = max(rules.min_wire_pitch,
                       rules.wire_pitch_diameters * max(layout.wires[i].diameter, layout.wires[j].diameter))
            if d < need - TOL:
                v.append(Violation("wire_pitch", f"wires {i}/{j} pitch {d:.3e} m < {need:.3e} m",
                                   (float(layout.wires[i].points[0, 0]), float(layout.wires[i].points[0, 1]))))

    # terminals must sit on their net's copper
    for net, tm in layout.terminals.items():
        pad = box(tm.cx - tm.w / 2, tm.cy - tm.h / 2, tm.cx + tm.w / 2, tm.cy + tm.h / 2).buffer(-TOL)
        if not any(t.net == net and t.polygon.contains(pad) for t in layout.traces):
            v.append(Violation("terminal_off_trace", f"terminal {net} not on {net} Cu", (tm.cx, tm.cy)))
    return v
