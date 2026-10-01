"""L1 fast PEEC model of the half-bridge commutation loop (quasi-static, numpy, float64, SI).

Model (exactly the O001 hypothesis, no fitted factors, no L2 code)
-------------------------------------------------------------------
* **Trace cells.** Each top-Cu polygon is meshed on its own rectilinear grid whose lines contain every polygon
  vertex and every die-footprint edge (so the mesh conforms to the copper), plus the edges of a cell of size
  ``FOOT_FRAC * hmax`` centred on every attachment point (bond-wire foot, DC+/DC- terminal centre; feet closer
  than that cell share one cell centred on the group), and are subdivided to at most ``hmax``. Nodes sit at
  cell centres, so a current enters where the cell's bars meet. A current bar joins each pair of adjacent
  same-net cells (standard PEEC brick, length = centre spacing, width = cell width); a bar ending in a die
  footprint (one equipotential node) stops at the footprint edge. Partial inductances are Hoer & Love (1965)
  closed forms for near pairs; farther pairs use the filament form (Grover 1946) with 3 (mid range) or 1
  (far) sub-filaments across the bar width, and the point-element limit beyond.
* **HF current layer of the trace cells (internal inductance).** Above a few MHz the trace current flows in a
  skin layer on the face towards the image plane (proximity effect; delta = 1/sqrt(pi f mu0 sigma) = 29 / 14.6 /
  7.4 um at 5 / 20 / 80 MHz << t = 0.3 mm; Jackson, *Classical Electrodynamics*, sec. 5.18). The bars
  therefore carry uniform current in a layer of thickness ts = min(t, delta) on the plane-facing face (centred
  2 delta layer if the stack has no conductive plane). This removes the DC internal inductance that a
  full-thickness uniform-current bar carries. The HF internal inductance is kept, approximately: the layer's
  own internal inductance, mu0 ts/3 per square, differs from the surface-impedance value mu0 delta/2 by
  mu0 delta/6 (2.4 um against the 0.38 mm Cu-to-plane gap, ~0.6 % per square). Measured on 18 layouts at
  20 MHz, the former
  full-thickness model (``uniform_bars=True``) reads +4.7..+8.1 % (side_by_side), +12.0..+12.7 %
  (interleaved) and +10.2..+11.4 % (u_shaped) above this one. L(f) falls by 1.2..1.9 % from 5 to 80 MHz.
* **Skin-corrected resistance.** ``R = l / (sigma A_eff)``; bars: A_eff = w ts (the current layer above:
  only the plane-facing face carries current, so internal cell walls are not counted and R converges under
  mesh refinement); wires: skin annulus pi (a^2 - (a - delta)^2) (Grover/Smythe). R ~ sqrt(f) for delta << t.
  ``uniform_bars=True`` keeps the earlier perimeter layer A_eff = w t - (w - 2 delta)(t - 2 delta) (Wheeler
  1942), which counts shared cell walls.
* **Bond wires.** Each wire is one branch (series of straight round filaments = its polyline). Segment self
  inductance is Grover's round-wire (surface-current tube) formula plus the skin-scaled internal term
  mu0 l/(8 pi) min(1, 2 delta/a). Pairs of segments *of the same wire* use the finite-radius (thin-wire
  reduced) kernel 1/sqrt(R^2 + a^2) (``kernels.segment_mutual(core=a)``): for collinear segments it is exactly
  Grover's tube formula with GMD a, so a straight wire cut into any number of pieces keeps the whole-wire
  inductance, and a refined polyline converges instead of growing with the point count (the zero-radius
  filament mutual of touching segments diverged logarithmically: +1.1..+5.1 % of loop L from 7 to 25 points).
  Measured: loop L varies by 0.04..0.14 % across 7/13/25 points per wire (6 layouts, seed 5). Other wires and
  the bars use the Neumann integral of straight filaments (Grover ch. 8; analytic inner integral, Gauss outer).
* **Image planes.** Conductive planes of the stack (``LayerStack.conductive_plane_names``) are treated as
  infinite ideal planes whose surface facing the top Cu is the image plane; every conductor gets an image
  of opposite horizontal current at the mirrored z (image of the current vector J is (-Jx, -Jy, +Jz)), so
  L_eff = L - w * M_image. Which planes are imaged at frequency f follows from the skin depth delta(f)
  versus the plane thickness t: the field transmitted through a plane falls as T = exp(-t/delta). The
  topmost plane (backside Cu, 0.3 mm, delta = 29 / 14.6 / 7 um at 5 / 20 / 80 MHz) gets weight 1 - T1 and
  the next plane below (baseplate) gets T1 (1 - T2), i.e. only the flux leaking through the backside Cu.
  For delta << t (every frequency >= ~5 MHz with the default stack, T1 < 1e-4) this is exactly *one* image
  plane: the backside Cu, at the top face of the backside Cu; the baseplate is shielded and not imaged.
  Below ~4 MHz the baseplate begins to be imaged; planes with weight < 1e-4 are skipped. Finite plane
  extent is neglected (backside Cu is inset 1 mm from the substrate edge; all conductors lie inside),
  and the eddy-current penetration shift of the image plane (~delta) is neglected.
* **Quasi-static solve.** Branch impedances Z = R + j w L (full dense partial-inductance matrix, bars +
  wires); mesh analysis on a tree/cotree loop basis (identical to nodal analysis, checked to 1e-11) with unit
  current injected at the DC+ terminal node and extracted at the DC- terminal node: Z_port = V_pos - V_neg,
  L = Im(Z_port)/w, R = Re(Z_port).
* **Port / switches (same as ``Layout.to_conductors()``).** Positive node = top-Cu cell centred on the DC+
  terminal centre, negative node = cell centred on the DC- terminal centre; PHASE open. Each die is an ideal
  short (switch on) between its back-side footprint on the bottom net trace (all footprint cells merged to
  one node) and its top source pad node, where the wires start. Nothing is fitted to any reference solver.

Mesh bias (20 MHz; for the design of E002)
------------------------------------------
* **Default mesh (hmax = 4 mm) vs the 1 mm mesh**, 60 layouts (3 families x 2..6 dies per switch x seeds
  5/31/77/555): L(4 mm)/L(1 mm) - 1 = +1.44 % mean (sd 0.45 %), range +0.47..+2.41 %; side_by_side +1.03 %,
  interleaved +1.51 %, u_shaped +1.77 % (means). Positive throughout; Spearman rho(4 mm, 1 mm) = 1.000 in every
  family. It still grows mildly with die count (+1.16 % at 2 to +1.78 % at 6 dies per switch, r = 0.49), the
  F3 signature, at about a tenth of the former +0.3..+12 %. 2 mm vs 1 mm: +0.39..+1.90 %.
* **Error of the 1 mm mesh itself** (refinement 4/2/1/0.7/0.5 mm on the six seed-5 layouts of
  ``project/dod/l1-fidelity``): L decreases monotonically below 2 mm; L(1 mm)/L(0.5 mm) - 1 = +0.95..+1.48 %.
  Richardson extrapolation with order p = 1..2 (the range the 1/0.7/0.5 mm differences admit) puts the 1 mm
  mesh +1.3..+3.0 % and the default mesh +2.3..+5.4 % above the mesh-converged L1 (largest for 6 dies per
  switch, interleaved / u_shaped). The slow part is HF edge current crowding: on the plane-facing face of a
  strip over the image plane the current peaks within ~ the 0.38 mm gap of each edge, which cell-wide bars do
  not resolve (straight 3 / 8 / 12 mm strips: 1 mm cells read +4.0 / +1.7 / +1.1 %, 4 mm cells +5.0 / +2.7 /
  +1.8 % above a converged lane distribution).
* ``loop_inductance(..., edge_lanes=True)`` adds parallel edge-lane bars (width ``EDGE_LANE_FRAC`` x gap) along
  the trace boundary that capture most of this crowding: it lowers L by 1.1..1.9 % (4 mm) and 0.8..1.4 % (1 mm)
  on the six layouts above, but costs ~1.7x the time (p50 ~43 ms vs ~25 ms on the 6-die benchmark), so it is
  off by default. All of these biases are positive (L1 high), mesh-dependent, and not fitted to anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import shapely

from moduleforge.geometry import DC_MINUS, DC_PLUS, PHASE, Layout

from .kernels import (
    MU0,
    bar_mutual_hoer_love,
    filament_mutual_parallel,
    segment_mutual,
    bar_resistance,
    skin_depth,
    wire_resistance,
)

DEFAULT_HMAX = 4.0e-3  # m, maximum trace cell size
FOOT_FRAC = 0.25  # size of the cell centred on a wire foot / port point, in units of hmax
EDGE_LANE_FRAC = 0.25  # width of the optional edge-lane bars (``edge_lanes=True``), in units of the Cu-to-plane gap
_NQ = 4  # Gauss nodes along the wire (bar-to-wire near tier)
_NS = 3  # sub-filaments across a bar (bar-to-wire near tier)
_NEARSEG = 1.0  # near tier of bar-to-wire pairs: r < _NEARSEG * bar size + segment length / 2
_NEAR = 1.1  # centre distance / mean bar size below which Hoer-Love is used
_MID = 2.0  # ... below which 3 sub-filaments are used
_FAR = 4.0  # ... below which one filament is used (point-element limit beyond)
_FAR_SEG = 2.0  # same tiers for wire segments (r / summed size)
_NEAR_IMG = 0.7  # Hoer-Love limit for bar-to-image-bar pairs (3 sub-filaments beyond)
_SHIELD_MIN = 1e-4  # image planes with a smaller weight at every frequency are skipped


@dataclass
class LoopResult:
    """Port impedance of the commutation loop. Field names match the L2 reference-solver result."""

    L_H: np.ndarray  # (F,) inductance Im(Z)/w [H]
    R_ohm: np.ndarray  # (F,) resistance Re(Z) [Ohm]
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------------------
# meshing (one rectilinear grid per trace; lines contain every vertex and die edge of that trace)
# --------------------------------------------------------------------------------------------------
def _grid_lines(vals, hmax):
    v = np.unique(np.round(np.asarray(vals, float), 10))
    n = np.maximum(np.ceil(np.diff(v) / hmax - 1e-9), 1).astype(int)
    grp = np.repeat(np.arange(n.size), n)
    k = np.arange(grp.size) - np.repeat(np.cumsum(n) - n, n)
    return np.append(v[grp] + (v[grp + 1] - v[grp]) * k / n[grp], v[-1])


def _locate(xs, ys, x, y):
    i = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, xs.size - 2)
    j = np.clip(np.searchsorted(ys, y, side="right") - 1, 0, ys.size - 2)
    return j, i


@dataclass
class _TraceGrid:
    net: str
    xs: np.ndarray
    ys: np.ndarray
    occ: np.ndarray  # (ny, nx) bool
    node: np.ndarray  # (ny, nx) int, -1 outside copper

    @property
    def xc(self):
        return 0.5 * (self.xs[1:] + self.xs[:-1])

    @property
    def yc(self):
        return 0.5 * (self.ys[1:] + self.ys[:-1])


def _centred_cell_lines(v, half):
    """Mesh lines that put every value of ``v`` at the centre of its own cell.

    Values closer than ``half`` x 2 (= the cell size) are one group (e.g. the 2-3 wires of one die at 1 mm pitch
    on a 4 mm mesh) whose cell is centred on the group; a group / value gets the cell [first - s, last + s] with
    s = min(``half``, half the distance to the neighbouring group)."""
    v = np.unique(np.round(np.asarray(v, float), 10))
    if v.size == 0:
        return v
    new = np.r_[True, np.diff(v) > 2 * half * (1 + 1e-9)]
    first, last = v[new], v[np.r_[new[1:], True]]
    s = np.full(first.size, float(half))
    if first.size > 1:
        g = 0.5 * (first[1:] - last[:-1])
        s[1:] = np.minimum(s[1:], g)
        s[:-1] = np.minimum(s[:-1], g)
    return np.concatenate([first - s, last + s])


def _mesh_traces(layout: Layout, hmax):
    nets = [t.net for t in layout.traces]
    if len(set(nets)) != len(nets):
        raise ValueError("exactly one top-Cu trace per net is supported")
    bottom = {"HS": DC_PLUS, "LS": PHASE}
    grids, count = [], 0
    for t in layout.traces:
        co = shapely.get_coordinates(t.polygon)
        db = np.array([d.bounds for d in layout.dies if bottom[d.switch] == t.net]).reshape(-1, 4)
        # attachment points (wire feet landing on this trace, port terminal centre): each one is the centre of its
        # own cell of size FOOT_FRAC * hmax (smaller where points are closer), so the current enters at the node
        # where the cell's bars meet and neighbouring feet are not merged (shorted) into one node
        pts = [w.points[-1, :2] for w in layout.wires if w.net == t.net]
        if t.net in (DC_PLUS, DC_MINUS):
            pts.append(np.array([layout.terminals[t.net].cx, layout.terminals[t.net].cy]))
        pts = np.array(pts, float).reshape(-1, 2)
        x0, y0, x1, y1 = t.polygon.bounds
        lx, ly = (_centred_cell_lines(pts[:, k], 0.5 * FOOT_FRAC * hmax) for k in (0, 1))
        lx, ly = lx[(lx > x0) & (lx < x1)], ly[(ly > y0) & (ly < y1)]
        xs = _grid_lines(np.concatenate([co[:, 0], db[:, 0], db[:, 2], lx]), hmax)
        ys = _grid_lines(np.concatenate([co[:, 1], db[:, 1], db[:, 3], ly]), hmax)
        gx, gy = np.meshgrid(0.5 * (xs[1:] + xs[:-1]), 0.5 * (ys[1:] + ys[:-1]))
        occ = shapely.contains_xy(t.polygon, gx, gy)
        node = np.full(occ.shape, -1, np.int64)
        node[occ] = count + np.arange(int(occ.sum()))
        count += int(occ.sum())
        grids.append(_TraceGrid(t.net, xs, ys, occ, node))
    return grids, count


# --------------------------------------------------------------------------------------------------
# partial-inductance blocks. Tiers by centre distance r: Hoer-Love (near), 3 sub-filaments (mid),
# single filament (far) and the point-element limit mu0 l1 l2 (u1.u2)/(4 pi r) (very far, error O((l/r)^2)).
# --------------------------------------------------------------------------------------------------
def _hl_unique(c1, d1, c2, d2, axis):
    """Hoer-Love for pair lists, evaluating each distinct (relative offset, sizes) combination once."""
    key = np.round(np.concatenate([c2 - c1, d1, d2], axis=1) * 1e10).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return bar_mutual_hoer_love(c1[first], d1[first], c2[first], d2[first], axis)[inv.reshape(-1)]


def _fil_pairs(c1, d1, c2, d2, axis, nsub):
    """Mean parallel-filament mutual over ``nsub`` filaments across the bar width, for aligned pair lists."""
    tr = 1 if axis == 0 else 0
    o = (np.arange(nsub) - (nsub - 1) / 2) / nsub if nsub > 1 else np.zeros(1)
    dperp = ((c1[:, tr] - c2[:, tr])[:, None, None] + o[None, :, None] * d1[:, tr, None, None]
             - o[None, None, :] * d2[:, tr, None, None])
    d = np.sqrt(dperp**2 + ((c1[:, 2] - c2[:, 2])**2)[:, None, None])
    l1, l2 = d1[:, axis], d2[:, axis]
    off = (c2[:, axis] - l2 / 2) - (c1[:, axis] - l1 / 2)
    m = filament_mutual_parallel(l1[:, None, None], l2[:, None, None], d, off[:, None, None])
    return m.mean(axis=(1, 2))


def _bar_block(c, d, axis, sources):
    """Symmetric (n, n) weighted mutual partial-inductance matrix [H] of one set of parallel bars along ``axis``.

    ``sources`` is a list of ``(zp, weight, near)``: ``zp`` None couples the bars with themselves (direct,
    self terms on the diagonal), a float couples them with their mirror images in the plane z = zp; the
    result is sum_k weight_k M_k. Only the upper triangle of pairs is evaluated (M is symmetric, the image
    block by mirror symmetry). ``near`` is the Hoer-Love limit of the distance tiers (r / mean bar size)."""
    n = len(c)
    if n == 0:
        return np.zeros((0, 0))
    iu, ju = np.triu_indices(n)
    dmax = d.max(axis=1)
    lim = _FAR * 0.5 * (dmax[iu] + dmax[ju])
    dxy2 = (c[iu, 0] - c[ju, 0]) ** 2 + (c[iu, 1] - c[ju, 1]) ** 2
    za, zb = c[iu, 2], c[ju, 2]
    lu = MU0 / (4 * np.pi) * d[iu, axis] * d[ju, axis]
    # every source in the point-element limit mu0 l1 l2/(4 pi r) (error O((l/r)^2)); pairs closer than _FAR mean
    # bar sizes to any source are replaced below by the filament / Hoer-Love tiers (one gather for all sources)
    v = np.zeros(iu.size)
    close = np.zeros(iu.size, bool)
    for zp, weight, _ in sources:
        r = np.sqrt(dxy2 + (za - zb if zp is None else za + zb - 2 * zp) ** 2)
        v += weight * lu / np.maximum(r, 1e-12)
        close |= r < lim
    k = np.nonzero(close)[0]
    i, j = iu[k], ju[k]
    c1, d1, d2 = c[i], d[i], d[j]
    ref = 0.5 * (dmax[i] + dmax[j])
    for zp, weight, near in sources:
        c2 = c[j]
        if zp is not None:
            c2[:, 2] = 2 * zp - c2[:, 2]  # c[j] is a copy (fancy indexing)
        x = np.sqrt(np.sum((c1 - c2) ** 2, axis=1)) / ref
        val = lu[k] / np.maximum(x * ref, 1e-12)
        for sel, nsub in ((np.nonzero((x >= _MID) & (x < _FAR))[0], 1),
                          (np.nonzero((x >= near) & (x < _MID))[0], 3)):  # disjoint tiers
            val[sel] = _fil_pairs(c1[sel], d1[sel], c2[sel], d2[sel], axis, nsub)
        sel = np.nonzero(x < near)[0]
        val[sel] = _hl_unique(c1[sel], d1[sel], c2[sel], d2[sel], axis)
        v[k] += weight * (val - lu[k] / np.maximum(x * ref, 1e-12))
    m = np.empty((n, n))
    m[iu, ju] = v
    m[ju, iu] = v
    return m


def _bar_seg_block(c, d, axis, segsets, sl):
    """(B, S) weighted Neumann mutual [H] between axis-aligned bars and straight segments.

    ``segsets`` is a list of ``(sp, su, weight)`` segment sets of common lengths ``sl`` (the wire segments
    and their mirror images); the result is sum_k weight_k M(bars, set k)."""
    nset, ns = len(segsets), len(sl)
    sp = np.concatenate([s[0] for s in segsets])
    su = np.concatenate([s[1] for s in segsets])
    sl = np.tile(sl, nset)
    e = np.zeros(3)
    e[axis] = 1.0
    p0 = c - 0.5 * d[:, axis, None] * e
    smid = sp + 0.5 * sl[:, None] * su
    r = np.sqrt(np.sum((c[:, None, :] - smid[None, :, :]) ** 2, axis=-1))
    out = MU0 / (4 * np.pi) * d[:, axis, None] * sl[None, :] * (su @ e)[None, :] / np.maximum(r, 1e-12)
    dmax = d.max(axis=1)[:, None]
    i, j = np.nonzero(r < _FAR_SEG * (dmax + sl[None, :]))
    near = r[i, j] < _NEARSEG * dmax[i, 0] + 0.5 * sl[j]
    i1, j1 = i[~near], j[~near]
    out[i1, j1] = segment_mutual(p0[i1], e, d[i1, axis], sp[j1], su[j1], sl[j1], n=3)
    i, j = i[near], j[near]
    tr = 1 if axis == 0 else 0
    o = (np.arange(_NS) - (_NS - 1) / 2) / _NS  # sub-filaments across the bar width
    pn = p0[i][:, None, :] + (o[None, :] * d[i, tr, None])[..., None] * np.eye(3)[tr]
    m = segment_mutual(pn, e, d[i, axis, None], sp[j][:, None, :], su[j][:, None, :], sl[j, None], n=_NQ)
    out[i, j] = m.mean(axis=1)
    w = np.array([s[2] for s in segsets], float)
    return np.einsum("k,bks->bs", w, out.reshape(len(c), nset, ns))


def _reflect(sp, su, zp):
    """Geometric mirror of segments in the plane z = zp (direction vector mirrored, not sign-flipped)."""
    p = sp.copy()
    p[..., 2] = 2 * zp - sp[..., 2]
    u = su.copy()
    u[..., 2] = -su[..., 2]
    return p, u


def _seg_matrix(sp, su, sl, sp2, su2, wid=None, rad=None):
    """(S, S) symmetric Neumann mutual of segments (set 1 vs set 2 = set 1 or its image).

    With ``wid``/``rad`` (wire index and radius per segment) pairs of segments of the same wire use the
    finite-radius core kernel (``segment_mutual(core=a)``), so a refined polyline converges."""
    s = len(sl)
    iu, ju = np.triu_indices(s)
    smid, smid2 = sp + 0.5 * sl[:, None] * su, sp2 + 0.5 * sl[:, None] * su2
    r = np.sqrt(np.sum((smid[iu] - smid2[ju]) ** 2, axis=-1))
    size = sl[iu] + sl[ju]
    core = np.zeros(iu.size) if wid is None else np.where(wid[iu] == wid[ju], rad[iu], 0.0)
    v = (MU0 / (4 * np.pi) * sl[iu] * sl[ju] * np.sum(su[iu] * su2[ju], axis=-1)
         / np.maximum(np.sqrt(r * r + core * core), 1e-12))
    k = r < _FAR_SEG * size
    v[k] = segment_mutual(sp[iu[k]], su[iu[k]], sl[iu[k]], sp2[ju[k]], su2[ju[k]], sl[ju[k]], n=6, core=core[k])
    m = np.zeros((s, s))
    m[iu, ju] = v
    return m + np.triu(m, 1).T


# --------------------------------------------------------------------------------------------------
# main entry
# --------------------------------------------------------------------------------------------------
def _edge_lane_width(layout: Layout) -> float:
    """Width [m] of the edge lanes: ``EDGE_LANE_FRAC`` x the gap between the top-Cu bottom face and the top of the
    topmost conductive plane (the image plane at HF); the top-Cu thickness if the stack has no conductive plane."""
    st = layout.stack
    z0, z1 = layout.top_cu_z()
    planes = [n for n in ("backside_cu", "baseplate") if n in st.conductive_plane_names]
    gap = z0 - st.z_top(planes[0]) if planes else z1 - z0
    return EDGE_LANE_FRAC * gap


def _edge_lanes(c, dd, nl, nr, lo, hi, lane, tr):
    """Split bars that run along the copper boundary into parallel branches between the same two nodes.

    ``lo``/``hi``: the bar's side at the low/high transverse coordinate (axis ``tr``) lies on the trace edge. Each
    such side gets its own bar (lane) of width ``lane``; the remainder of the bar keeps the rest of the width. The
    lanes carry the HF edge current crowding (the current on the plane-facing face of a strip over a ground plane
    peaks within ~ the gap of each edge), which a cell-wide uniform-current bar cannot represent; for a straight
    strip the parallel lanes are exact because the voltage per length is uniform across the width. Bars narrower
    than (1 + number of lanes) x ``lane`` are not split."""
    w = dd[:, tr]
    ok = (lane > 0) & (w >= (1 + lo.astype(int) + hi.astype(int)) * lane)
    lo, hi = lo & ok, hi & ok
    edge0 = c[:, tr] - 0.5 * w
    edge1 = c[:, tr] + 0.5 * w
    main_c, main_d = c.copy(), dd.copy()
    a, b = edge0 + lane * lo, edge1 - lane * hi
    main_c[:, tr], main_d[:, tr] = 0.5 * (a + b), b - a
    parts_c, parts_d, parts_l, parts_r = [main_c], [main_d], [nl], [nr]
    for sel, centre in ((lo, edge0 + 0.5 * lane), (hi, edge1 - 0.5 * lane)):
        lc, ld = c[sel].copy(), dd[sel].copy()
        lc[:, tr], ld[:, tr] = centre[sel], lane
        parts_c.append(lc)
        parts_d.append(ld)
        parts_l.append(nl[sel])
        parts_r.append(nr[sel])
    return np.concatenate(parts_c), np.concatenate(parts_d), np.concatenate(parts_l), np.concatenate(parts_r)


def _plane_weights(layout: Layout, freqs):
    """Image-plane weights (P, F) for the stack's conductive planes, top-down, and their image z."""
    st = layout.stack
    names = [n for n in ("backside_cu", "baseplate") if n in st.conductive_plane_names]
    w = np.zeros((len(names), len(freqs)))
    transmit = np.ones(len(freqs))
    for k, name in enumerate(names):
        la = st.layer(name)
        t_k = np.exp(-la.thickness / skin_depth(freqs, la.sigma))
        w[k] = transmit * (1.0 - t_k)
        transmit = transmit * t_k
    return names, w, np.array([st.z_top(n) for n in names])


def _discretize(layout: Layout, hmax: float, ts: float | None = None, zc: float | None = None,
                edge_lanes: bool = False) -> SimpleNamespace:
    """Mesh the layout: bars, wire segments, node numbering and the ``assemble`` mutual-matrix builder.

    The bars carry current in a layer of thickness ``ts`` centred at ``zc`` (default: the whole top-Cu
    thickness, uniform current, centred); ``loop_inductance`` passes the skin layer (see module docstring).
    ``edge_lanes`` splits the bars along the trace boundary into parallel edge lanes (``_edge_lanes``)."""
    z0, z1 = layout.top_cu_z()
    tcu = z1 - z0 if ts is None else ts
    zc = z0 + 0.5 * (z1 - z0) if zc is None else zc
    sig_cu = layout.stack.layer("top_cu").sigma
    lane = _edge_lane_width(layout) if edge_lanes else 0.0
    grids, n_cells = _mesh_traces(layout, hmax)
    gnet = {g.net: g for g in grids}
    ndie = len(layout.dies)
    die_node = n_cells + np.arange(ndie)

    # ---- die footprints merge into one node on the bottom trace ----
    bottom_net = {"HS": DC_PLUS, "LS": PHASE}
    for k, d in enumerate(layout.dies):
        g = gnet[bottom_net[d.switch]]
        x0, y0, x1, y1 = d.bounds
        xc, yc = g.xc, g.yc
        inside = ((xc[None, :] > x0) & (xc[None, :] < x1)) & ((yc[:, None] > y0) & (yc[:, None] < y1))
        g.node[inside & g.occ] = die_node[k]

    # ---- bars (x-directed first, then y-directed), from each trace grid ----
    bars = {0: [], 1: []}
    for g in grids:
        xc, yc = g.xc, g.yc
        dxs, dys = np.diff(g.xs), np.diff(g.ys)
        jx, ix = np.nonzero(g.occ[:, :-1] & g.occ[:, 1:])
        jy, iy = np.nonzero(g.occ[:-1, :] & g.occ[1:, :])
        z = np.full
        px, py = np.meshgrid(xc, yc)

        def span(lo, hi, e, nl, nr):
            """Centre and length of bars between the cell centres lo, hi; a bar that ends in a die footprint
            (equipotential node >= n_cells) stops at the footprint edge e."""
            lo = np.where((nl >= n_cells) & (nr < n_cells), e, lo)
            hi = np.where((nr >= n_cells) & (nl < n_cells), e, hi)
            return 0.5 * (lo + hi), hi - lo

        # copper boundary beside a bar: a neighbour cell (either end) across the bar is not copper
        occ = np.pad(g.occ, 1)  # occ[j + 1, i + 1] = g.occ[j, i], False outside the grid
        lo_x = ~occ[jx, ix + 1] | ~occ[jx, ix + 2]
        hi_x = ~occ[jx + 2, ix + 1] | ~occ[jx + 2, ix + 2]
        lo_y = ~occ[jy + 1, iy] | ~occ[jy + 2, iy]
        hi_y = ~occ[jy + 1, iy + 2] | ~occ[jy + 2, iy + 2]
        nl, nr = g.node[jx, ix], g.node[jx, ix + 1]
        cxm, lxm = span(px[jx, ix], px[jx, ix + 1], g.xs[ix + 1], nl, nr)
        bars[0].append(_edge_lanes(np.stack([cxm, yc[jx], z(ix.size, zc)], 1),
                                   np.stack([lxm, dys[jx], z(ix.size, tcu)], 1), nl, nr, lo_x, hi_x, lane, 1))
        nl, nr = g.node[jy, iy], g.node[jy + 1, iy]
        cym, lym = span(py[jy, iy], py[jy + 1, iy], g.ys[jy + 1], nl, nr)
        bars[1].append(_edge_lanes(np.stack([xc[iy], cym, z(iy.size, zc)], 1),
                                   np.stack([dxs[iy], lym, z(iy.size, tcu)], 1), nl, nr, lo_y, hi_y, lane, 0))
    cx, ddx, nx1, nx2 = (np.concatenate(v) for v in zip(*bars[0], strict=True))
    cy, ddy, ny1, ny2 = (np.concatenate(v) for v in zip(*bars[1], strict=True))
    kx, ky = nx1 != nx2, ny1 != ny2  # bars shorted inside one die footprint carry no branch
    cx, ddx, nx1, nx2 = cx[kx], ddx[kx], nx1[kx], nx2[kx]
    cy, ddy, ny1, ny2 = cy[ky], ddy[ky], ny1[ky], ny2[ky]
    nbx, nby = len(cx), len(cy)
    bn1, bn2 = np.concatenate([nx1, ny1]), np.concatenate([nx2, ny2])

    # ---- wires ----
    pts = [w.points for w in layout.wires]
    cnt = np.array([len(p) for p in pts])
    allp = np.concatenate(pts)
    starts = np.cumsum(cnt) - cnt
    seg_mask = np.ones(len(allp) - 1, bool)
    seg_mask[(starts + cnt - 1)[:-1]] = False
    sp = allp[:-1][seg_mask]
    vec = (allp[1:] - allp[:-1])[seg_mask]
    sl = np.linalg.norm(vec, axis=1)
    su = vec / sl[:, None]
    wid = np.repeat(np.arange(len(pts)), cnt - 1)
    nw = len(pts)
    rad = np.array([w.diameter for w in layout.wires]) / 2
    p_start, p_end = allp[starts], allp[starts + cnt - 1]
    die_b = np.array([d.bounds for d in layout.dies])
    ins = ((p_start[:, None, 0] >= die_b[None, :, 0] - 1e-9) & (p_start[:, None, 0] <= die_b[None, :, 2] + 1e-9)
           & (p_start[:, None, 1] >= die_b[None, :, 1] - 1e-9) & (p_start[:, None, 1] <= die_b[None, :, 3] + 1e-9))
    if not ins.any(axis=1).all():
        raise ValueError("every bond wire must start above a die footprint")
    wn1 = die_node[ins.argmax(axis=1)]
    wn2 = np.empty(nw, np.int64)
    for net_name, g in gnet.items():  # loop over the (<= 3) traces, vectorised over wires
        sel = np.array([w.net == net_name for w in layout.wires])
        j, i = _locate(g.xs, g.ys, p_end[sel, 0], p_end[sel, 1])
        if not g.occ[j, i].all():
            raise ValueError("bond wire lands outside its top-Cu trace")
        wn2[sel] = g.node[j, i]
    if (wn2 < 0).any():
        raise ValueError("bond wire net has no trace")
    port_nodes = []
    for net_name in (DC_PLUS, DC_MINUS):
        t, g = layout.terminals[net_name], gnet[net_name]
        j, i = _locate(g.xs, g.ys, np.array([t.cx]), np.array([t.cy]))
        if not g.occ[j[0], i[0]]:
            raise ValueError("terminal centre is not on top-Cu")
        port_nodes.append(g.node[j[0], i[0]])
    pos_node, neg_node = port_nodes

    # ---- partial inductances (frequency-independent geometry part) ----
    nb = nbx + nby
    nbr = nb + nw
    membership = np.zeros((len(sl), nw))
    membership[np.arange(len(sl)), wid] = 1.0

    def assemble(zp=None, planes=None):
        """Branch partial-inductance matrix [H] (bars, then wires).

        Default: direct partial inductances with self terms. ``zp``: mutual matrix to the mirror images in
        the plane z = zp only. ``planes`` = [(zp_k, w_k)]: effective matrix L - sum_k w_k M_image(zp_k),
        evaluated in one pass over the pairs."""
        if planes is not None:
            srcs = [(None, 1.0)] + [(z, -float(wk)) for z, wk in planes]
        else:
            srcs = [(None, 1.0)] if zp is None else [(zp, 1.0)]
        M = np.empty((nbr, nbr))
        M[:nbx, :nbx] = _bar_block(cx, ddx, 0, [(z, wk, _NEAR if z is None else _NEAR_IMG) for z, wk in srcs])
        M[nbx:nb, nbx:nb] = _bar_block(cy, ddy, 1, [(z, wk, _NEAR if z is None else _NEAR_IMG) for z, wk in srcs])
        M[:nbx, nbx:nb] = 0.0  # x- and y-directed bars are orthogonal
        M[nbx:nb, :nbx] = 0.0
        segsets = [(sp, su, wk) if z is None else (*_reflect(sp, su, z), wk) for z, wk in srcs]
        bw = np.concatenate([_bar_seg_block(cx, ddx, 0, segsets, sl), _bar_seg_block(cy, ddy, 1, segsets, sl)])
        bw = bw @ membership
        M[:nb, nb:] = bw
        M[nb:, :nb] = bw.T
        ms = np.zeros((len(sl), len(sl)))
        for z, wk in srcs:
            if z is None:  # same-wire pairs with the finite-radius core; diagonal = Grover tube self
                m = _seg_matrix(sp, su, sl, sp, su, wid, rad[wid])
                a = rad[wid]
                np.fill_diagonal(m, MU0 * sl / (2 * np.pi) * (np.arcsinh(sl / a) - np.sqrt(1 + (a / sl) ** 2) + a / sl))
            else:
                m = _seg_matrix(sp, su, sl, *_reflect(sp, su, z))
            ms += wk * m
        M[nb:, nb:] = membership.T @ ms @ membership
        return M

    return SimpleNamespace(**locals())


def _incidence(a1, a2, nn):
    """Branch-node incidence matrix (branch k runs from node a1[k] to a2[k])."""
    A = np.zeros((len(a1), nn))
    A[np.arange(len(a1)), a1] += 1.0
    A[np.arange(len(a1)), a2] -= 1.0
    return A


def _loop_basis(a1, a2, nn, pos, neg):
    """Tree/cotree loop basis of the branch network (mesh analysis).

    A spanning forest is grown over the branches (union-find, in branch order); every cotree branch closes one
    fundamental loop. The loop matrix ``C`` (nk, nl) has column j = branch currents of loop j: +1 on its cotree
    branch and the compensating forest currents; ``i0`` (nk,) = forest currents carrying 1 A from ``pos`` to
    ``neg``. Every branch-current vector that satisfies KCL with the port injection is i0 + C x. Returned in
    block form: forest branch indices ``t``, cotree indices ``c``, ``C[t]`` (C[c] is the identity) and ``i0[t]``
    (i0[c] = 0)."""
    nk = len(a1)
    parent = list(range(nn))

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    tree = np.zeros(nk, bool)
    for k, (u, v) in enumerate(zip(np.asarray(a1).tolist(), np.asarray(a2).tolist(), strict=True)):
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[ru] = rv
            tree[k] = True
    root = np.array([find(u) for u in range(nn)])
    if root[pos] != root[neg]:
        raise ValueError("the port terminals are not connected")
    keep = root != np.arange(nn)  # one KCL row per connected component is redundant: drop the roots
    t, c = np.nonzero(tree)[0], np.nonzero(~tree)[0]
    A = _incidence(a1, a2, nn)[:, keep]
    s = np.zeros(nn)
    s[pos], s[neg] = 1.0, -1.0
    # KCL A^T i = s (net outflow = injection), solved for the forest currents: A_T^T i_T = s - A_C^T i_C
    x = np.linalg.solve(A[t].T, np.column_stack([-A[c].T, s[keep]]))
    return t, c, x[:, :-1], x[:, -1]


def _mesh_port_impedance(X, r, a1, a2, nn, pos, neg):
    """Port impedance V(pos) - V(neg) [Ohm] for 1 A injected at ``pos`` and drawn at ``neg``.

    Branch impedance matrix Z = diag(r) + j X (X = w L, real symmetric, mutual coupling included). Mesh
    analysis on the tree/cotree basis (``_loop_basis``): branch currents i = i0 + C x, KVL around every loop
    C^T Z (i0 + C x) = 0 fixes x, and the port voltage is the voltage along the forest path, i0^T Z i. This is
    the same network solution as nodal analysis (Y = A^T Z^-1 A) but needs real products and one (nl x nl)
    complex solve with a single right-hand side instead of an (nk x nk) complex solve with nn right-hand sides.
    """
    t, c, ct, i0t = _loop_basis(a1, a2, nn, pos, neg)
    # products with C = [I on cotree rows c; ct on forest rows t] and i0 (zero on c), in block form
    xt = X[:, t]
    xi0 = xt @ i0t  # X i0
    ri0t = r[t] * i0t  # R i0 on the forest rows
    zport = 1j * (i0t @ xi0[t]) + i0t @ ri0t  # i0^T Z i0
    if c.size:
        xc = X[:, c] + xt @ ct  # X C
        cxc = xc[c] + ct.T @ xc[t]  # C^T X C
        crc = (ct.T * r[t]) @ ct
        crc[np.diag_indices(c.size)] += r[c]  # C^T R C
        b = 1j * (xi0[c] + ct.T @ xi0[t]) + ct.T @ ri0t  # C^T Z i0
        x = np.linalg.solve(1j * cxc + crc, -b)
        zport += b @ x  # i0^T Z C x (Z symmetric)
    return zport


def _port_impedance(Z, A, pos, neg):
    """Port impedance for a branch impedance matrix ``Z`` with diagonal real part and incidence ``A``."""
    r = np.real(np.diag(Z)).copy()
    if np.any(np.real(Z) - np.diag(r)):
        raise ValueError("the real part of Z must be diagonal (branch resistances)")
    a1, a2 = np.argmax(A > 0.5, axis=1), np.argmax(A < -0.5, axis=1)
    return _mesh_port_impedance(np.imag(Z), r, a1, a2, A.shape[1], pos, neg)


def loop_inductance(layout: Layout, freqs_hz, hmax: float = DEFAULT_HMAX, uniform_bars: bool = False,
                    edge_lanes: bool = False) -> LoopResult:
    """Commutation-loop inductance L(f) and resistance R(f) at the DC+/DC- port (see module docstring).

    ``uniform_bars=True`` selects the earlier (T0023) trace-cell model - uniform current over the full Cu
    thickness, centred, skin-perimeter resistance - which keeps the DC internal inductance; it exists only to
    quantify that bias (module docstring) and is not used by the experiments. ``edge_lanes=True`` adds the
    edge-lane bars along the trace boundary that resolve the HF edge current crowding (module docstring, "Mesh
    bias"); off by default because it costs ~60 % more time per evaluation than the 50 ms budget allows."""
    freqs = np.atleast_1d(np.asarray(freqs_hz, float))
    if np.any(freqs <= 0):
        raise ValueError("frequencies must be positive")
    z0, z1 = layout.top_cu_z()
    sig_cu = layout.stack.layer("top_cu").sigma
    names, wts, zpl = _plane_weights(layout, freqs)
    deltas = skin_depth(freqs, sig_cu)
    Lout, Rout = np.empty(freqs.size), np.empty(freqs.size)
    for fi, f in enumerate(freqs):
        w = 2 * np.pi * f
        # high-frequency current layer of the trace cells: one skin depth on the face towards the image
        # plane(s) (proximity effect), two skin depths centred when the stack has no conductive plane
        faces = 1 if names else 2
        ts = z1 - z0 if uniform_bars else min(z1 - z0, faces * deltas[fi])
        zc = z0 + 0.5 * ts if names and not uniform_bars else 0.5 * (z0 + z1)
        d = _discretize(layout, hmax, ts, zc, edge_lanes)
        nb, nw, sl, wid, rad, membership = d.nb, d.nw, d.sl, d.wid, d.rad, d.membership
        planes = [(zpl[k], wts[k, fi]) for k in range(len(names)) if wts[k, fi] > _SHIELD_MIN]
        L = d.assemble(planes=planes)  # L - sum_k w_k M_image,k
        # internal inductance of the wires (skin-scaled), on the wire branches
        d_w = skin_depth(f, layout.wire_sigma)
        iw = np.arange(nb, nb + nw)
        L[iw, iw] += MU0 * (membership.T @ sl) * np.minimum(1.0, 2.0 * d_w / rad) / (8 * np.pi)
        lbar = np.concatenate([d.ddx[:, 0], d.ddy[:, 1]])
        wbar = np.concatenate([d.ddx[:, 1], d.ddy[:, 0]])
        if uniform_bars:
            r_bar = bar_resistance(lbar, wbar, ts, sig_cu, deltas[fi])
        else:
            r_bar = lbar / (sig_cu * wbar * ts)  # current confined to the layer of thickness ts
        r_w = membership.T @ wire_resistance(sl, rad[wid], layout.wire_sigma, d_w)
        # network: compact node numbers (cells without a branch drop out), mesh analysis at the port
        n1, n2 = np.concatenate([d.bn1, d.wn1]), np.concatenate([d.bn2, d.wn2])
        uniq, inv = np.unique(np.concatenate([n1, n2, [d.pos_node, d.neg_node]]), return_inverse=True)
        nk, nn = n1.size, uniq.size
        zport = _mesh_port_impedance(w * L, np.concatenate([r_bar, r_w]), inv[:nk], inv[nk:2 * nk], nn,
                                     inv[-2], inv[-1])
        Lout[fi] = zport.imag / w
        Rout[fi] = zport.real
    meta = {
        "model": "L1 quasi-static PEEC: Hoer-Love bar cells, Grover wires, image planes",
        "freqs_hz": freqs.tolist(),
        "skin_depth_cu_m": deltas.tolist(),
        "imaged_planes": {names[k]: wts[k].tolist() for k in range(len(names)) if wts[k].max() > _SHIELD_MIN},
        "n_bars": int(nb),
        "n_wires": int(nw),
        "n_wire_segments": int(len(sl)),
        "n_nodes": int(nn),
        "hmax_m": float(hmax),
        "bar_layer_thickness_m": None if uniform_bars else [min(z1 - z0, (1 if names else 2) * x) for x in deltas],
        "port": {"pos": "DC+ terminal centre", "neg": "DC- terminal centre", "phase_open": True},
    }
    return LoopResult(Lout, Rout, meta)
