"""Manufacturing design rules (DRC) for wire-bonded DBC/AMB half-bridge layouts.

Default values are *typical* DBC/AMB design-guide numbers (Rogers/curamik and Heraeus/Kyocera substrate
design guidelines for 0.3 mm Cu: min. trace width ~1 mm, min. Cu-Cu isolation spacing ~1 mm, Cu-to-ceramic-edge
margin ~1 mm; die-to-Cu-edge margin ~1 mm; Al wire bonding pitch >= ~2 wire diameters). They are placeholders
to be replaced with the customer's vendor rules; all lengths are SI (m).
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Point, box

from moduleforge.geometry import Layout
from moduleforge.geometry.units import mm_to_m

TOL = 1e-9  # geometric comparison tolerance, 1 nm


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


DEFAULT_RULES = DesignRules()


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    where: tuple[float, float] | None = None


def _pt(g):
    c = g.representative_point()
    return (float(c.x), float(c.y))


def check(layout: Layout, rules: DesignRules = DEFAULT_RULES) -> list[Violation]:
    """Return all rule violations (empty list = DRC clean)."""
    v: list[Violation] = []
    mit = {"join_style": "mitre", "mitre_limit": 10.0}

    # min_trace_width: morphological opening with a square element of side min width
    r = rules.min_trace_width / 2 - TOL
    for i, t in enumerate(layout.traces):
        opened = t.polygon.buffer(-r, **mit).buffer(r, **mit)
        thin = t.polygon.difference(opened)
        if thin.area > 1e-12:
            v.append(Violation("min_trace_width", f"trace {i} ({t.net}) narrower than min width", _pt(thin)))

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
        host = [t for t in layout.traces if t.polygon.contains(Point(d.cx, d.cy))]
        if not host:
            v.append(Violation("die_off_trace", f"die {i} not on any trace", (d.cx, d.cy)))
            continue
        if host[0].net != want[d.switch]:
            v.append(Violation("die_wrong_net", f"die {i} ({d.switch}) on {host[0].net}", (d.cx, d.cy)))
        if not host[0].polygon.buffer(-(rules.die_edge_margin - TOL), **mit).contains(d.box):
            v.append(Violation("die_edge_margin", f"die {i} closer to trace edge than margin", (d.cx, d.cy)))
    for i in range(len(layout.dies)):
        for j in range(i + 1, len(layout.dies)):
            dist = layout.dies[i].box.distance(layout.dies[j].box)
            if dist < rules.die_spacing - TOL:
                v.append(Violation("die_spacing", f"dies {i}/{j} spacing {dist:.3e} m",
                                   (layout.dies[i].cx, layout.dies[i].cy)))

    # wires
    lines = []
    for i, w in enumerate(layout.wires):
        xy = (float(w.points[0, 0]), float(w.points[0, 1]))
        if not (rules.min_wire_length - TOL <= w.length <= rules.max_wire_length + TOL):
            v.append(Violation("wire_length", f"wire {i} length {w.length:.3e} m", xy))
        end = Point(w.points[-1, 0], w.points[-1, 1])
        ok = any(
            t.net == w.net and t.polygon.buffer(-(rules.wire_landing_margin - TOL), **mit).contains(end)
            for t in layout.traces
        )
        if not ok:
            v.append(Violation("wire_landing", f"wire {i} does not land on {w.net} Cu", (end.x, end.y)))
        start = Point(xy)
        if not any(
            (p[0] - TOL <= start.x <= p[2] + TOL and p[1] - TOL <= start.y <= p[3] + TOL)
            for d in layout.dies for k, p in d.pads.items() if k == "source"
        ):
            v.append(Violation("wire_start", f"wire {i} does not start on a die source pad", xy))
        lines.append(LineString(w.points[:, :2]))
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            d = lines[i].distance(lines[j])
            if d < rules.min_wire_pitch - TOL:
                v.append(Violation("wire_pitch", f"wires {i}/{j} pitch {d:.3e} m",
                                   (float(layout.wires[i].points[0, 0]), float(layout.wires[i].points[0, 1]))))

    # terminals must sit on their net's copper
    for net, tm in layout.terminals.items():
        pad = box(tm.cx - tm.w / 2, tm.cy - tm.h / 2, tm.cx + tm.w / 2, tm.cy + tm.h / 2).buffer(-TOL)
        if not any(t.net == net and t.polygon.contains(pad) for t in layout.traces):
            v.append(Violation("terminal_off_trace", f"terminal {net} not on {net} Cu", (tm.cx, tm.cy)))
    return v
