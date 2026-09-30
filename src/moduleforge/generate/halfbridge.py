"""Seeded generator of DRC-valid wire-bonded half-bridge layouts (3 topological families).

Housing-fixed geometry (mm, substrate 70 x 40 at the origin): DC+ pad centre (66, 15) and DC- pad centre
(66, 25) on the right edge, PHASE pad centre (4, 20) on the left edge, all 4 x 4 mm. HS dies sit on the DC+
trace and are wired to PHASE; LS dies sit on PHASE and are wired to DC-. Rows are listed bottom-up (y):

* ``side_by_side``: DC+ | PHASE | DC-, simple PHASE strip.
* ``interleaved``:  PHASE | DC+ | DC- | PHASE; DC+ and DC- rows adjacent, PHASE is a C joined at the left.
* ``u_shaped``:     PHASE | DC+ | PHASE | DC-; PHASE wraps the DC+ row (long U-shaped current path).
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from moduleforge.drc import check
from moduleforge.geometry import (
    DC_MINUS,
    DC_PLUS,
    PHASE,
    Die,
    Layout,
    Terminal,
    Trace,
    arc_wire,
    default_dbc_stack,
    mm_to_m,
)

FAMILIES = ("side_by_side", "interleaved", "u_shaped")
DIE_COUNTS = (2, 3, 4, 5, 6)

W_MM, H_MM = 70.0, 40.0
X_ROW_L, X_PH_R, X_EDGE = 9.0, 61.0, 68.0  # DC row start, PHASE row end, right end of Cu
Y_BOT = 1.5
PADS = {  # housing-fixed terminal pads (x0, y0, x1, y1) in mm
    DC_PLUS: (64.0, 13.0, 68.0, 17.0),
    DC_MINUS: (64.0, 23.0, 68.0, 27.0),
    PHASE: (2.0, 18.0, 6.0, 22.0),
}
WIRE_PITCH_MM = 1.0
X_DIE_MIN, X_DIE_MAX = 10.0, 60.0


def _rows(family, s, g, e, rng):
    """Return (rects by net, hs_y0, hs_land_y, ls_y0, ls_land_y) in mm."""
    pd, pm, pp = PADS[DC_PLUS], PADS[DC_MINUS], PADS[PHASE]
    R = {DC_PLUS: [], DC_MINUS: [], PHASE: [pp]}
    col = lambda pad, y0, y1: (pad[0], min(pad[1], y0), pad[2], max(pad[3], y1))  # noqa: E731
    if family == "side_by_side":
        hs_y0 = Y_BOT + 1.0
        y1 = hs_y0 + s + 1.0 + e[0]
        p0 = y1 + g
        ls_y0 = p0 + 3.0 + e[1]
        p1 = max(ls_y0 + s + 1.0, pp[3])
        q0 = p1 + g
        q1 = q0 + 3.0 + e[2]
        R[DC_PLUS] += [(X_ROW_L, Y_BOT, X_EDGE, y1), col(pd, Y_BOT, y1)]
        R[PHASE] += [(pp[0], min(p0, pp[1]), X_PH_R, p1)]
        R[DC_MINUS] += [(X_ROW_L, q0, X_EDGE, q1), col(pm, q0, q1)]
        return R, hs_y0, p0 + 1.0, ls_y0, q0 + 1.0
    if family == "interleaved":
        ptop = Y_BOT + 4.0 + e[0]
        a0 = ptop + g
        hs_y0 = a0 + 1.0
        a1 = max(hs_y0 + s + 1.0 + e[1], pd[3])
        c0 = a1 + g
        c1 = max(c0 + 3.0 + e[2], pm[3])
        p0 = c1 + g
        ls_y0 = p0 + 1.0
        p1 = ls_y0 + s + 1.0
        R[PHASE] += [(pp[0], Y_BOT, X_PH_R, ptop), (pp[0], p0, X_PH_R, p1), (pp[0], Y_BOT, 7.0, p1)]
        R[DC_PLUS] += [(X_ROW_L, a0, X_EDGE, a1), col(pd, a0, a1)]
        R[DC_MINUS] += [(X_ROW_L, c0, X_EDGE, c1), col(pm, c0, c1)]
        return R, hs_y0, ptop - 1.0, ls_y0, c1 - 1.0
    # u_shaped
    ptop = Y_BOT + 4.0 + e[0]
    a0 = ptop + g
    hs_y0 = a0 + 1.0
    a1 = max(hs_y0 + s + 1.0 + e[1], pd[3])
    p0 = a1 + g
    ls_y0 = p0 + 1.0
    p1 = ls_y0 + s + 1.0 + e[2]
    q0 = p1 + g
    q1 = q0 + 3.0 + e[3]
    R[PHASE] += [(pp[0], Y_BOT, X_PH_R, ptop), (pp[0], p0, X_PH_R, p1), (pp[0], Y_BOT, 7.0, p1)]
    R[DC_PLUS] += [(X_ROW_L, a0, X_EDGE, a1), col(pd, a0, a1)]
    R[DC_MINUS] += [(X_ROW_L, q0, X_EDGE, q1), col(pm, q0, q1)]
    return R, hs_y0, ptop - 1.0, ls_y0, q0 + 1.0


def _build(family: str, n: int, rng: np.random.Generator) -> Layout:
    stack = default_dbc_stack()
    s = round(rng.uniform(4.0, 5.5), 1)
    dg = round(rng.uniform(1.5, 2.5), 1)
    g = round(rng.uniform(1.5, 2.5), 1)
    emax = 1.5 if family == "u_shaped" else 2.0
    e = [round(rng.uniform(0.0, emax), 1) for _ in range(4)]
    k = int(rng.integers(2, 4))  # wires per die
    diam = float(rng.choice([0.3, 0.4]))
    hloop = round(rng.uniform(0.6, 1.5), 2)
    u = rng.uniform({"side_by_side": 0.85, "interleaved": 0.0, "u_shaped": 0.0}[family],
                    {"side_by_side": 1.0, "interleaved": 1.0, "u_shaped": 0.15}[family])
    ld = n * s + (n - 1) * dg
    xs = X_DIE_MIN + u * (X_DIE_MAX - X_DIE_MIN - ld)
    R, hs_y0, hs_land, ls_y0, ls_land = _rows(family, s, g, e, rng)

    traces = []
    for net, rects in R.items():
        poly = unary_union([box(*(mm_to_m(v) for v in r)) for r in rects])
        if not isinstance(poly, Polygon):
            raise ValueError(f"{net} trace is not a single polygon")
        traces.append(Trace(net, poly))
    z_top_cu = stack.z_top("top_cu")
    dies, wires = [], []
    for sw, y0, land, net in (("HS", hs_y0, hs_land, PHASE), ("LS", ls_y0, ls_land, DC_MINUS)):
        for i in range(n):
            cx, cy = xs + i * (s + dg) + s / 2, y0 + s / 2
            sgn = 1.0 if land > cy else -1.0
            hp = 0.35 * s
            pads = {
                "source": tuple(mm_to_m(v) for v in (cx - hp, cy - hp, cx + hp, cy + hp)),
                "gate": tuple(mm_to_m(v) for v in (cx + 0.36 * s, cy - 0.47 * s, cx + 0.47 * s, cy - 0.36 * s)),
            }
            die = Die(mm_to_m(cx), mm_to_m(cy), mm_to_m(s), mm_to_m(s), sw, pads)
            dies.append(die)
            z_start = z_top_cu + die.attach_thickness + die.thickness
            for j in range(k):
                x = cx + (j - (k - 1) / 2) * WIRE_PITCH_MM
                wires.append(arc_wire((mm_to_m(x), mm_to_m(cy + sgn * 0.25 * s)), (mm_to_m(x), mm_to_m(land)),
                                      z_start, z_top_cu, mm_to_m(hloop), mm_to_m(diam), net))
    terminals = {
        net: Terminal(net, mm_to_m((p[0] + p[2]) / 2), mm_to_m((p[1] + p[3]) / 2), mm_to_m(p[2] - p[0]),
                      mm_to_m(p[3] - p[1]))
        for net, p in PADS.items()
    }
    return Layout(
        family=family,
        dies_per_switch=n,
        outline=box(0.0, 0.0, mm_to_m(W_MM), mm_to_m(H_MM)),
        traces=traces,
        dies=dies,
        wires=wires,
        terminals=terminals,
        baseplate_outline=box(mm_to_m(-8.0), mm_to_m(-8.0), mm_to_m(W_MM + 8.0), mm_to_m(H_MM + 8.0)),
        stack=stack,
    )


def generate_layouts(n: int, seed: int, family: str | None = None, dies_per_switch: int | None = None,
                     max_tries: int = 200) -> list[Layout]:
    """Return ``n`` DRC-valid layouts, deterministic in ``seed`` (numpy Generator, no global state).

    (family, dies_per_switch) combinations are cycled in seeded random permutations so that all families
    and die counts 2..6 are covered evenly; ``family`` / ``dies_per_switch`` restrict the set. Each layout
    is drawn by bounded reject-and-resample (``max_tries``); RuntimeError if exhausted.
    """
    if family is not None and family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; choose from {FAMILIES}")
    if dies_per_switch is not None and dies_per_switch not in DIE_COUNTS:
        raise ValueError(f"dies_per_switch must be in {DIE_COUNTS}")
    combos = [(f, k) for f in FAMILIES for k in DIE_COUNTS
              if (family is None or f == family) and (dies_per_switch is None or k == dies_per_switch)]
    rng = np.random.default_rng(seed)
    out: list[Layout] = []
    order: list[int] = []
    while len(out) < n:
        if not order:
            order = list(rng.permutation(len(combos)))
        f, k = combos[order.pop()]
        for _ in range(max_tries):
            try:
                lay = _build(f, k, rng)
            except ValueError:
                continue
            if not check(lay):
                out.append(lay)
                break
        else:
            raise RuntimeError(f"no DRC-valid layout for family={f} dies_per_switch={k} in {max_tries} tries")
    return out


def loop_area_proxy(layout: Layout) -> float:
    """Crude commutation-loop area [m^2]: shoelace area of the polygon DC+ terminal -> HS die centroid ->
    LS die centroid -> DC- terminal. A geometric proxy only (not an inductance)."""
    hs = np.array([(d.cx, d.cy) for d in layout.dies if d.switch == "HS"]).mean(axis=0)
    ls = np.array([(d.cx, d.cy) for d in layout.dies if d.switch == "LS"]).mean(axis=0)
    tp, tn = layout.terminals[DC_PLUS], layout.terminals[DC_MINUS]
    p = np.array([(tp.cx, tp.cy), hs, ls, (tn.cx, tn.cy)])
    x, y = p[:, 0], p[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
