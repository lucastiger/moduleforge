"""L1 fast PEEC model of the half-bridge commutation loop (quasi-static, numpy, float64, SI).

Model (exactly the O001 hypothesis, no fitted factors, no L2 code)
-------------------------------------------------------------------
* **Trace cells.** The top-Cu polygons are meshed on a rectilinear grid whose lines contain every polygon
  vertex and every die-footprint edge (so the mesh conforms to the copper) and are subdivided to at most
  ``hmax``. Nodes sit at cell centres; a current bar joins each pair of adjacent same-net cells (standard
  PEEC brick, length = centre spacing, cross-section = cell width x Cu thickness, uniform current
  density). Partial inductances are Hoer & Love (1965) closed forms for near pairs; farther pairs use the
  filament form (Grover 1946) with 3 (mid range) or 1 (far) sub-filaments across the bar width.
* **Skin-corrected resistance.** ``R = l / (sigma A_eff)``; bars: current in a skin layer around the
  perimeter, A_eff = w t - (w - 2 delta)(t - 2 delta) (Wheeler 1942; Paul, *Inductance*, 2010), wires: skin
  annulus pi (a^2 - (a - delta)^2), delta = 1/sqrt(pi f mu0 sigma) (Jackson, *Classical Electrodynamics*,
  sec. 5.18). R ~ sqrt(f) when delta << t. Wire internal inductance is scaled with the skin effect
  (mu0 l/(8 pi) min(1, 2 delta/a)); the bar internal inductance is neglected (delta << t, and the external
  partial inductance dominates).
* **Bond wires.** Each wire is one branch (series of straight round filaments = its polyline); segment
  self inductance is Grover's round-wire formula and segment-to-segment / wire-to-bar mutuals are the
  Neumann integral of straight filaments (Grover ch. 8; analytic inner integral, Gauss outer).
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
  wires), nodal analysis with unit current injected at the DC+ terminal node and extracted at the DC-
  terminal node: Z_port = V_pos - V_neg, L = Im(Z_port)/w, R = Re(Z_port).
* **Port / switches (same as ``Layout.to_conductors()``).** Positive node = top-Cu cell containing the DC+
  terminal centre, negative node = cell containing the DC- terminal centre; PHASE open. Each die is an ideal
  short (switch on) between its back-side footprint on the bottom net trace (all footprint cells merged to
  one node) and its top source pad node, where the wires start. Nothing is fitted to any reference solver.
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
    bar_resistance,
    filament_mutual_parallel,
    segment_mutual,
    skin_depth,
    wire_resistance,
)

DEFAULT_HMAX = 4.0e-3  # m, maximum trace cell size
_NEAR = 1.1  # centre distance / mean bar size below which Hoer-Love is used
_MID = 3.0  # ... below which 3 sub-filaments are used
_FAR = 6.0  # ... below which one filament is used (point-element limit beyond)
_FAR_SEG = 3.5  # same tiers for wire segments (r / summed size)
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


def _mesh_traces(layout: Layout, hmax):
    nets = [t.net for t in layout.traces]
    if len(set(nets)) != len(nets):
        raise ValueError("exactly one top-Cu trace per net is supported")
    bottom = {"HS": DC_PLUS, "LS": PHASE}
    grids, count = [], 0
    for t in layout.traces:
        co = shapely.get_coordinates(t.polygon)
        db = np.array([d.bounds for d in layout.dies if bottom[d.switch] == t.net]).reshape(-1, 4)
        xs = _grid_lines(np.concatenate([co[:, 0], db[:, 0], db[:, 2]]), hmax)
        ys = _grid_lines(np.concatenate([co[:, 1], db[:, 1], db[:, 3]]), hmax)
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


def _bar_block(c1, d1, c2, d2, axis, symmetric=False, near=_NEAR):
    """(n, m) mutual partial-inductance matrix [H] of two sets of parallel bars along ``axis``."""
    n, m = len(c1), len(c2)
    if n == 0 or m == 0:
        return np.zeros((n, m))
    dc = c1[:, None, :] - c2[None, :, :]
    r = np.sqrt(np.sum(dc * dc, axis=-1))
    ref = 0.5 * (d1.max(axis=1)[:, None] + d2.max(axis=1)[None, :])
    out = MU0 / (4 * np.pi) * d1[:, axis, None] * d2[None, :, axis] / np.maximum(r, 1e-12)
    tri = np.triu(np.ones((n, m), bool)) if symmetric else np.ones((n, m), bool)
    for lim, nsub in ((_FAR * ref, 1), (_MID * ref, 3)):
        i, j = np.nonzero((r < lim) & tri)
        out[i, j] = _fil_pairs(c1[i], d1[i], c2[j], d2[j], axis, nsub)
    i, j = np.nonzero((r < near * ref) & tri)
    out[i, j] = _hl_unique(c1[i], d1[i], c2[j], d2[j], axis)
    if symmetric:
        out = np.triu(out) + np.triu(out, 1).T
    return out


def _bar_seg_block(c, d, axis, sp, su, sl):
    """(B, S) Neumann mutual between axis-aligned bars and straight segments (sp, su, sl)."""
    e = np.zeros(3)
    e[axis] = 1.0
    p0 = c - 0.5 * d[:, axis, None] * e
    smid = sp + 0.5 * sl[:, None] * su
    r = np.sqrt(np.sum((c[:, None, :] - smid[None, :, :]) ** 2, axis=-1))
    out = MU0 / (4 * np.pi) * d[:, axis, None] * sl[None, :] * (su @ e)[None, :] / np.maximum(r, 1e-12)
    size = d.max(axis=1)[:, None] + sl[None, :]
    i, j = np.nonzero(r < _FAR_SEG * size)
    out[i, j] = segment_mutual(p0[i], e, d[i, axis], sp[j], su[j], sl[j], n=3)
    i, j = np.nonzero(r < 1.5 * d.max(axis=1)[:, None] + 0.5 * sl[None, :])
    tr = 1 if axis == 0 else 0
    et = np.zeros(3)
    et[tr] = 1.0
    acc = 0.0
    for o in (-1 / 3, 0.0, 1 / 3):  # 3 sub-filaments across the bar width
        acc = acc + segment_mutual(p0[i] + (o * d[i, tr])[:, None] * et, e, d[i, axis], sp[j], su[j], sl[j], n=6)
    out[i, j] = acc / 3.0
    return out


def _reflect(sp, su, zp):
    """Geometric mirror of segments in the plane z = zp (direction vector mirrored, not sign-flipped)."""
    p = sp.copy()
    p[..., 2] = 2 * zp - sp[..., 2]
    u = su.copy()
    u[..., 2] = -su[..., 2]
    return p, u


def _seg_matrix(sp, su, sl, sp2, su2):
    """(S, S) symmetric Neumann mutual of segments (set 1 vs set 2 = set 1 or its image)."""
    s = len(sl)
    iu, ju = np.triu_indices(s)
    smid, smid2 = sp + 0.5 * sl[:, None] * su, sp2 + 0.5 * sl[:, None] * su2
    r = np.sqrt(np.sum((smid[iu] - smid2[ju]) ** 2, axis=-1))
    size = sl[iu] + sl[ju]
    v = MU0 / (4 * np.pi) * sl[iu] * sl[ju] * np.sum(su[iu] * su2[ju], axis=-1) / np.maximum(r, 1e-12)
    k = r < _FAR_SEG * size
    v[k] = segment_mutual(sp[iu[k]], su[iu[k]], sl[iu[k]], sp2[ju[k]], su2[ju[k]], sl[ju[k]], n=6)
    m = np.zeros((s, s))
    m[iu, ju] = v
    return m + np.triu(m, 1).T


# --------------------------------------------------------------------------------------------------
# main entry
# --------------------------------------------------------------------------------------------------
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


def _discretize(layout: Layout, hmax: float) -> SimpleNamespace:
    """Mesh the layout: bars, wire segments, node numbering and the ``assemble`` mutual-matrix builder."""
    z0, z1 = layout.top_cu_z()
    tcu = z1 - z0
    zc = z0 + 0.5 * tcu
    sig_cu = layout.stack.layer("top_cu").sigma
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
        bars[0].append((np.stack([0.5 * (xc[ix] + xc[ix + 1]), yc[jx], z(ix.size, zc)], 1),
                        np.stack([xc[ix + 1] - xc[ix], dys[jx], z(ix.size, tcu)], 1),
                        g.node[jx, ix], g.node[jx, ix + 1]))
        bars[1].append((np.stack([xc[iy], 0.5 * (yc[jy] + yc[jy + 1]), z(iy.size, zc)], 1),
                        np.stack([dxs[iy], yc[jy + 1] - yc[jy], z(iy.size, tcu)], 1),
                        g.node[jy, iy], g.node[jy + 1, iy]))
    cx, ddx, nx1, nx2 = (np.concatenate(v) for v in zip(*bars[0], strict=True))
    cy, ddy, ny1, ny2 = (np.concatenate(v) for v in zip(*bars[1], strict=True))
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

    def assemble(zp=None):
        """Mutual matrix among all branches; ``zp`` None -> direct (with self terms), else image at z = zp."""
        M = np.zeros((nbr, nbr))
        if zp is None:
            M[:nbx, :nbx] = _bar_block(cx, ddx, cx, ddx, 0, symmetric=True)
            M[nbx:nb, nbx:nb] = _bar_block(cy, ddy, cy, ddy, 1, symmetric=True)
            ssp, ssu = sp, su
        else:
            mx, my = cx.copy(), cy.copy()
            mx[:, 2] = 2 * zp - cx[:, 2]
            my[:, 2] = 2 * zp - cy[:, 2]
            M[:nbx, :nbx] = _bar_block(cx, ddx, mx, ddx, 0, symmetric=True, near=_NEAR_IMG)
            M[nbx:nb, nbx:nb] = _bar_block(cy, ddy, my, ddy, 1, symmetric=True, near=_NEAR_IMG)
            ssp, ssu = _reflect(sp, su, zp)
        e_x = _bar_seg_block(cx, ddx, 0, ssp, ssu, sl)
        e_y = _bar_seg_block(cy, ddy, 1, ssp, ssu, sl)
        bw = np.concatenate([e_x, e_y]) @ membership
        M[:nb, nb:] = bw
        M[nb:, :nb] = bw.T
        ms = _seg_matrix(sp, su, sl, ssp, ssu)
        if zp is None:
            a = rad[wid]
            np.fill_diagonal(ms, MU0 * sl / (2 * np.pi) * (np.arcsinh(sl / a) - np.sqrt(1 + (a / sl) ** 2) + a / sl))
        M[nb:, nb:] = membership.T @ ms @ membership
        return M

    return SimpleNamespace(**locals())


def _incidence(a1, a2, nn):
    """Branch-node incidence matrix (branch k runs from node a1[k] to a2[k])."""
    A = np.zeros((len(a1), nn), complex)
    A[np.arange(len(a1)), a1] += 1.0
    A[np.arange(len(a1)), a2] -= 1.0
    return A


def _port_impedance(Z, A, pos, neg):
    """Port impedance V(pos) - V(neg) for 1 A injected at ``pos`` and drawn at ``neg``.

    Nodal analysis with full branch impedance matrix ``Z`` (mutual coupling included): Y = A^T Z^-1 A,
    node ``neg`` is the reference.
    """
    nn = A.shape[1]
    Y = A.T @ np.linalg.solve(Z, A)
    Y[np.diag_indices(nn)] += 1e-12  # floating-node guard
    free = np.nonzero(np.arange(nn) != neg)[0]
    s = np.zeros(nn - 1, complex)
    k = int(np.searchsorted(free, pos))
    s[k] = 1.0
    return np.linalg.solve(Y[np.ix_(free, free)], s)[k]


def loop_inductance(layout: Layout, freqs_hz, hmax: float = DEFAULT_HMAX) -> LoopResult:
    """Commutation-loop inductance L(f) and resistance R(f) at the DC+/DC- port (see module docstring)."""
    freqs = np.atleast_1d(np.asarray(freqs_hz, float))
    if np.any(freqs <= 0):
        raise ValueError("frequencies must be positive")
    d = _discretize(layout, hmax)
    nb, nw, sl, wid, rad, membership = d.nb, d.nw, d.sl, d.wid, d.rad, d.membership
    ddx, ddy, bn1, bn2, wn1, wn2 = d.ddx, d.ddy, d.bn1, d.bn2, d.wn1, d.wn2
    tcu, sig_cu, pos_node, neg_node = d.tcu, d.sig_cu, d.pos_node, d.neg_node
    Lm = d.assemble(None)
    names, wts, zpl = _plane_weights(layout, freqs)
    used = [k for k in range(len(names)) if wts[k].max() > _SHIELD_MIN]
    images = {k: d.assemble(zpl[k]) for k in used}

    # ---- reduced network: drop bars shorted inside a die footprint, compact node numbers ----
    lbar = np.concatenate([ddx[:, 0], ddy[:, 1]])
    wbar = np.concatenate([ddx[:, 1], ddy[:, 0]])
    kb = np.concatenate([bn1 != bn2, np.ones(nw, bool)])
    sel = np.nonzero(kb)[0]
    nk = sel.size
    n1, n2 = np.concatenate([bn1, wn1])[sel], np.concatenate([bn2, wn2])[sel]
    uniq, inv = np.unique(np.concatenate([n1, n2, [pos_node, neg_node]]), return_inverse=True)
    a1, a2, ip_, in2 = inv[:nk], inv[nk:2 * nk], inv[-2], inv[-1]
    nn = uniq.size
    A = _incidence(a1, a2, nn)
    lw_seg = membership.T @ sl
    Lsel_base = Lm[np.ix_(sel, sel)]
    img_sel = {k: images[k][np.ix_(sel, sel)] for k in used}
    Lout, Rout = np.empty(freqs.size), np.empty(freqs.size)
    deltas = skin_depth(freqs, sig_cu)
    for fi, f in enumerate(freqs):
        w = 2 * np.pi * f
        L = Lsel_base.copy()
        for k in used:
            L -= wts[k, fi] * img_sel[k]
        d_w = skin_depth(f, layout.wire_sigma)
        r_bar = bar_resistance(lbar, wbar, tcu, sig_cu, deltas[fi])
        r_w = membership.T @ wire_resistance(sl, rad[wid], layout.wire_sigma, d_w)
        Z = L * (1j * w)
        dg = np.arange(nk)
        Z[dg, dg] += np.concatenate([r_bar, r_w])[sel]
        # internal inductance of the wires (skin-scaled): added on the wire branches
        Z[dg[-nw:], dg[-nw:]] += 1j * w * MU0 * lw_seg * np.minimum(1.0, 2.0 * d_w / rad) / (8 * np.pi)
        zport = _port_impedance(Z, A, ip_, in2)
        Lout[fi] = zport.imag / w
        Rout[fi] = zport.real
    meta = {
        "model": "L1 quasi-static PEEC: Hoer-Love bar cells, Grover wires, image planes",
        "freqs_hz": freqs.tolist(),
        "skin_depth_cu_m": deltas.tolist(),
        "imaged_planes": {names[k]: wts[k].tolist() for k in used},
        "n_bars": int(nb),
        "n_wires": int(nw),
        "n_wire_segments": int(len(sl)),
        "n_nodes": int(nn),
        "hmax_m": float(hmax),
        "port": {"pos": "DC+ terminal centre", "neg": "DC- terminal centre", "phase_open": True},
    }
    return LoopResult(Lout, Rout, meta)
