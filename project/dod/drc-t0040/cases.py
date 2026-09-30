"""DRC DoD for the T0040 review of T0038: loop-closing necks, unknown die.switch, diameter-aware wire-start margin."""
import dataclasses

from shapely.geometry import box
from shapely.ops import unary_union

from moduleforge.drc import check
from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import Trace
from moduleforge.geometry.units import mm_to_m as mm


def rules(lay):
    try:
        return {v.rule for v in check(lay)}
    except Exception as e:  # a crash is a miss, not a pass
        return {f"CRASH {type(e).__name__}: {e}"}


s = generate_layouts(3, seed=3, family="side_by_side", dies_per_switch=3)[0]
assert check(s) == []
cases = {}
# A copper ring whose loop closes through a zero-length 0.1 mm neck: erosion turns the ring into a C (still one
# piece), so a piece count alone misses it; the hole disappears.
ring = unary_union([box(0, 0, mm(20), mm(2)), box(0, 0, mm(2), mm(20)), box(0, mm(18), mm(21.9), mm(20)),
                    box(mm(18), 0, mm(20), mm(10)), box(mm(19.9), mm(10), mm(21.9), mm(20))])
assert ring.geom_type == "Polygon" and len(ring.interiors) == 1
cases["0.1 mm neck closing a copper loop -> min_trace_width"] = "min_trace_width" in rules(
    dataclasses.replace(s, traces=[*s.traces, Trace("DC-", ring)]))
hs = next(d for d in s.dies if d.switch == "HS")
cases["die.switch 'hs' -> die_bad_switch, no crash"] = "die_bad_switch" in rules(
    dataclasses.replace(s, dies=[dataclasses.replace(hs, switch="hs") if d is hs else d for d in s.dies]))
x0, y0, x1, y1 = hs.pads["source"]
w0 = next(w for w in s.wires if x0 - 1e-9 <= w.points[0, 0] <= x1 + 1e-9 and y0 - 1e-9 <= w.points[0, 1] <= y1 + 1e-9)
p = w0.points.copy()
p[0, 0] = x0 + mm(0.2)
thick = dataclasses.replace(w0, points=p, diameter=mm(0.5))
cases["0.5 mm wire starting 0.2 mm inside its pad edge (< half its diameter) -> wire_start"] = "wire_start" in rules(
    dataclasses.replace(s, wires=[thick if w is w0 else w for w in s.wires]))
missed = [k for k, ok in cases.items() if not ok]
assert not missed, "not handled: " + "; ".join(missed)
print(f"all {len(cases)} T0040 cases handled")
