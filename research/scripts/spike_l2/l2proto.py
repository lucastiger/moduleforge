"""T0067 spike: exact-geometry modal round-wire PEEC + uniform-grid plane PEEC (research prototype, not src/).

Wire: each straight edge -> n_e equal segments; cross-section -> graded annuli x azimuthal harmonics m <= P
(cos/sin), current density 1_a(rho) T_m(phi) / A_a. Coaxial (same edge) couplings: exact log part
(ln|x-x'| = ln rho_> - sum (1/m)(rho_</rho_>)^m cos m theta) + Gauss/trapezoid for the smooth remainder
+ graded Gauss for the |d| kink; Toeplitz in the segment offset. Other parallel edges and the plane couple
through moment-matched proxy filaments (degree-P transverse Taylor exactness, error ~ (r/D)^(P+1)).
Plane: uniform node grid, x/y branches with graded layers; plane-plane kernel computed once per distinct
offset (Hoer-Love near, Gauss-filament far), applied by FFT. Saddle system [M -C; C^T 0], Z = x^T M x
(stationary); a-posteriori bound |dZ| <= ||P(M x)||^2 / r_min (Re M = R diagonal >= r_min, x satisfies KCL).
Formulas: filament Neumann integral [Grover ch. 7]; Hoer-Love box mutual [Hoer & Love 1965, via the E001 runner].
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from numpy.polynomial.legendre import leggauss

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "runners"))
import e001_reference as E  # noqa: E402  (frozen runner: closed forms, Hoer-Love f, refinement rule)

MU0 = 4e-7 * math.pi
K4 = MU0 / (4 * math.pi)
COUNTS = {1: 9, 2: 12, 3: 16, 4: 21, 5: 28}  # realized ratios 1.333, 1.333, 1.3125, 1.333


def skin(f, sig):
    return 1.0 / math.sqrt(math.pi * f * MU0 * sig)


def gq(n, a, b):
    x, w = leggauss(n)
    return 0.5 * (b - a) * x + 0.5 * (a + b), 0.5 * (b - a) * w


def gfun(u, d):
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def fil_F(a1, a2, b1, b2, d):
    """int int dz dz' / R of two parallel filaments, transverse distance d > 0 [Grover ch. 7]."""
    return gfun(a2 - b1, d) + gfun(a1 - b2, d) - gfun(a1 - b1, d) - gfun(a2 - b2, d)


# ------------------------------------------------------------------ coaxial ring-mode kernel
def _p(x, k):
    return math.log(x) if k == -1 else x ** (k + 1) / (k + 1)


def _rl(x, k):
    return 0.0 if x == 0 else x ** (k + 1) / (k + 1) * math.log(x) - x ** (k + 1) / (k + 1) ** 2


def ring_log(a, b, m):
    """int_a int_b rho rho' K dr dr', K = ln max (m=0) or (min/max)^m; annuli identical or disjoint."""
    (al, be), (ga, de) = a, b
    if a == b:
        if m == 0:
            return (_rl(be, 3) - _rl(al, 3)) - al * al * (_rl(be, 1) - _rl(al, 1))
        t = al ** (m + 2) * (_p(be, 1 - m) - _p(al, 1 - m)) if al > 0 else 0.0
        return 2.0 / (m + 2) * ((be ** 4 - al ** 4) / 4 - t)
    if be > ga:
        (al, be), (ga, de) = (ga, de), (al, be)
    if m == 0:
        return (be * be - al * al) / 2 * (_rl(de, 1) - _rl(ga, 1))
    return (be ** (m + 2) - al ** (m + 2)) / (m + 2) * (_p(de, 1 - m) - _p(ga, 1 - m))


def coax_tables(edges_r, s, n_seg, P, ng=8, nth=128, ngk=12, panels=40):
    """F[k, a, b, m] = int_a int_b rho rho' int cos(m th) F_k(d) dth (k = segment offset); returns entry
    factor-ready table (without K4 * eps_m / (A_a A_b))."""
    nr = len(edges_r) - 1
    ann = [(edges_r[i], edges_r[i + 1]) for i in range(nr)]
    ms = np.arange(P + 1)
    lam = np.zeros((nr, nr, P + 1))
    for a in range(nr):
        for b in range(nr):
            if a == b or ann[a][1] <= ann[b][0] or ann[b][1] <= ann[a][0]:
                lam[a, b, 0] = 2 * math.pi * ring_log(ann[a], ann[b], 0)
                for m in range(1, P + 1):
                    lam[a, b, m] = -(math.pi / m) * ring_log(ann[a], ann[b], m)
    # smooth part s(u, d) = |u| ln(|u| + sqrt(u^2+d^2)) - sqrt(u^2+d^2): tensor Gauss x trapezoid
    rg, wg = [], []
    for al, be in ann:
        x, w = gq(ng, al, be)
        rg.append(x)
        wg.append(w * x)
    rg, wg = np.concatenate(rg), np.concatenate(wg)
    th = 2 * math.pi * np.arange(nth) / nth
    cosm = np.cos(np.outer(th, ms)) * (2 * math.pi / nth)
    d2 = (rg[:, None, None] ** 2 + rg[None, :, None] ** 2
          - 2 * rg[:, None, None] * rg[None, :, None] * np.cos(th)[None, None, :])
    d2 = np.maximum(d2, 0.0)
    us = s * np.arange(n_seg + 1)
    gam = np.zeros((n_seg + 1, nr, nr, P + 1))
    for iu, u in enumerate(us[1:], start=1):
        q = np.sqrt(u * u + d2)
        sv = u * np.log(u + q) - q
        proj = sv @ cosm  # (R, R, m)
        proj = proj * wg[:, None, None] * wg[None, :, None]
        tab = proj.reshape(nr, ng, nr, ng, P + 1).sum(axis=(1, 3))
        gam[iu] = -u * lam + tab
    # u = 0: -int |x-x'|, graded Gauss in theta on [0, pi], split triangles for a == b
    tq, tw = [], []
    for j in range(panels):
        lo, hi = math.pi * 2.0 ** (-j - 1), math.pi * 2.0 ** (-j)
        x, w = gq(8, lo, hi)
        tq.append(x)
        tw.append(w)
    tq, tw = np.concatenate(tq), 2 * np.concatenate(tw)
    cq = np.cos(np.outer(tq, ms)) * tw[:, None]
    for a in range(nr):
        for b in range(a, nr):
            if a == b:
                x1, w1 = gq(ngk, *ann[a])
                pr, pp, pw = [], [], []
                for xi, wi in zip(x1, w1, strict=True):
                    x2, w2 = gq(ngk, ann[a][0], xi)
                    pr.append(np.full(ngk, xi))
                    pp.append(x2)
                    pw.append(2 * wi * w2)
                pr, pp, pw = np.concatenate(pr), np.concatenate(pp), np.concatenate(pw)
            else:
                x1, w1 = gq(ngk, *ann[a])
                x2, w2 = gq(ngk, *ann[b])
                pr, pp = np.repeat(x1, ngk), np.tile(x2, ngk)
                pw = np.outer(w1, w2).ravel()
            d = np.sqrt((pr[:, None] - pp[:, None]) ** 2 + 4 * pr[:, None] * pp[:, None] * np.sin(tq / 2) ** 2)
            val = ((d @ cq) * (pw * pr * pp)[:, None]).sum(axis=0)
            gam[0, a, b] = gam[0, b, a] = -val
    k = np.arange(n_seg)
    F = gam[np.abs(k - 1)] + gam[k + 1] - 2 * gam[k]
    return F


# ------------------------------------------------------------------ proxies (far field of a cross-section)
def proxy_rule(r, ann, P):
    npr, nph = P // 2 + 1, 2 * P + 1
    xg, _ = gq(npr, 0.0, 1.0)
    rho = r * np.sqrt(xg)
    phi = 2 * math.pi * np.arange(nph) / nph
    pts = np.array([(rr * math.cos(p), rr * math.sin(p)) for rr in rho for p in phi])
    modes, W = [], []
    for a, (al, be) in enumerate(ann):
        area = math.pi * (be * be - al * al)
        for m in range(P + 1):
            nj = (P - m) // 2 + 1
            A = np.array([(rho / r) ** (m + 2 * j) for j in range(nj)])
            eps = 2 * math.pi if m == 0 else math.pi
            rhs = np.array([eps / area * (be ** (m + 2 * j + 2) - al ** (m + 2 * j + 2)) / (m + 2 * j + 2)
                            / r ** (m + 2 * j) for j in range(nj)])
            ug = np.linalg.lstsq(A, rhs, rcond=None)[0]
            for c in ((0,) if m == 0 else (0, 1)):
                t = np.cos(m * phi) if c == 0 else np.sin(m * phi)
                W.append(np.outer(ug, t * (1 if m == 0 else 2) / nph).ravel())
                modes.append((a, m, c))
    return pts, modes, np.array(W).T  # W: (Q, n_modes)


# ------------------------------------------------------------------ wire mesh
def wire_mesh(cond, k, fmax, sig, P):
    r = cond["diameter"] / 2
    c = COUNTS[k]
    dl = skin(fmax, sig)
    target = 0.5 * dl / r  # surface cell = delta/2 at level 1 (N_r = 9) -> asymptotic from the start
    lo, hi = 1e-6, 50.0
    for _ in range(200):  # G(1/9) = target, G(xi) = (e^(g xi) - 1)/(e^g - 1)
        g = 0.5 * (lo + hi)
        val = math.expm1(g / 9) / math.expm1(g)
        lo, hi = (g, hi) if val > target else (lo, g)
    gam = 0.5 * (lo + hi) if target < 1 / 9 else 1e-9
    xi = np.arange(c + 1) / c
    edges_r = r * (1 - np.expm1(gam * xi[::-1]) / math.expm1(gam)) if gam > 1e-8 else r * xi
    edges_r[0], edges_r[-1] = 0.0, r
    pts = np.asarray(cond["pts"], float)
    out = []
    for e in range(len(pts) - 1):
        p0, p1 = pts[e], pts[e + 1]
        ax = int(np.argmax(np.abs(p1 - p0)))
        L = abs(p1[ax] - p0[ax])
        out.append(dict(p0=p0, p1=p1, ax=ax, L=L, sgn=float(np.sign(p1[ax] - p0[ax])), n=c, s=L / c))
    mp = {"seg": min(o["s"] for o in out), "fil_w": math.pi * r / c, "fil_h": r / c,
          "surf": float(edges_r[-1] - edges_r[-2])}
    return dict(r=r, edges_r=edges_r, P=P, sig=sig, edges=out, mp=mp)


# ------------------------------------------------------------------ plane mesh
def plane_mesh(pl, k, fmax, gap, growth=2.0):
    c = COUNTS[k]
    W, H = pl["x_max"] - pl["x_min"], pl["y_max"] - pl["y_min"]
    mx, my = max(1, round(W / (1.2 * gap * 9))), max(1, round(H / (1.2 * gap * 9)))
    nx, ny = mx * c, my * c
    t1 = 0.5 * skin(fmax, pl["sigma"]) * 9 / c
    lay, z = [], pl["z_top"]
    t, tot = t1, 0.0
    while tot < pl["thickness"] - 1e-15:
        t = min(t, pl["thickness"] - tot)
        lay.append((z - tot - t, z - tot))
        tot += t
        t *= growth
    mp = {"plane_x": W / nx, "plane_y": H / ny, "plane_layer": t1}
    return dict(nx=nx, ny=ny, ax=W / nx, ay=H / ny, x0=pl["x_min"], y0=pl["y_min"], lay=lay, sig=pl["sigma"], mp=mp)


def hl_box(lo1, hi1, lo2, hi2, axis):
    """Vectorized Hoer-Love mutual of parallel boxes (rows), using the frozen runner's f [HL]."""
    tot = 0.0
    import itertools
    for (s0, i0), (s1, i1), (s2, i2) in itertools.product(*[[(1, 0), (-1, 1), (-1, 2), (1, 3)]] * 3):
        u = []
        for dd, ii in zip(range(3), (i0, i1, i2), strict=True):
            u.append([hi2[:, dd] - lo1[:, dd], hi2[:, dd] - hi1[:, dd], lo2[:, dd] - lo1[:, dd],
                      lo2[:, dd] - hi1[:, dd]][ii])
        tot = tot + s0 * s1 * s2 * E._hl_f(*u)
    tr = [d for d in range(3) if d != axis]
    a1 = (hi1[:, tr[0]] - lo1[:, tr[0]]) * (hi1[:, tr[1]] - lo1[:, tr[1]])
    a2 = (hi2[:, tr[0]] - lo2[:, tr[0]]) * (hi2[:, tr[1]] - lo2[:, tr[1]])
    return K4 * tot / (a1 * a2)


def plane_table(pm, direction, nw=4, nt=2, near=2):
    """T[l, l', di, dj] for di in [-(n1-1), n1-1], dj in [-(n2-1), n2-1] (x: n1 = nx-1, n2 = ny)."""
    ax_, ay_ = (pm["ax"], pm["ay"]) if direction == 0 else (pm["ay"], pm["ax"])
    n1, n2 = (pm["nx"] - 1, pm["ny"]) if direction == 0 else (pm["ny"] - 1, pm["nx"])
    lay = pm["lay"]
    nl = len(lay)
    di, dj = np.meshgrid(np.arange(n1), np.arange(n2), indexing="ij")
    di, dj = di.ravel(), dj.ravel()
    T = np.zeros((nl, nl, n1, n2))
    yw, ww = gq(nw, 0.0, ay_)
    ww = ww / ay_
    for l1 in range(nl):
        for l2 in range(l1, nl):
            z1, w1 = gq(nt, *lay[l1])
            z2, w2 = gq(nt, *lay[l2])
            w1, w2 = w1 / (lay[l1][1] - lay[l1][0]), w2 / (lay[l2][1] - lay[l2][0])
            nr_ = (di <= near) & (dj <= near)
            val = np.zeros(di.size)
            # far: Gauss over both cross-sections, exact along the length
            fi = np.where(~nr_)[0]
            for ya, wa in zip(yw, ww, strict=True):
                for yb, wb in zip(yw, ww, strict=True):
                    for za, wza in zip(z1, w1, strict=True):
                        for zb, wzb in zip(z2, w2, strict=True):
                            d = np.maximum(np.hypot(dj[fi] * ay_ + yb - ya, zb - za), 1e-9 * ax_)
                            val[fi] += wa * wb * wza * wzb * fil_F(0.0, ax_, di[fi] * ax_, di[fi] * ax_ + ax_, d)
            val[fi] *= K4
            ni = np.where(nr_)[0]
            lo1 = np.tile([0.0, 0.0, lay[l1][0]], (ni.size, 1))
            hi1 = np.tile([ax_, ay_, lay[l1][1]], (ni.size, 1))
            lo2 = np.stack([di[ni] * ax_, dj[ni] * ay_, np.full(ni.size, lay[l2][0])], 1)
            hi2 = lo2 + np.array([ax_, ay_, lay[l2][1] - lay[l2][0]])
            val[ni] = hl_box(lo1, hi1, lo2, hi2, 0)
            T[l1, l2] = T[l2, l1] = val.reshape(n1, n2)
    full = np.zeros((nl, nl, 2 * n1, 2 * n2))
    full[:, :, :n1, :n2] = T
    full[:, :, n1 + 1:, :n2] = T[:, :, :0:-1, :]
    full[:, :, :n1, n2 + 1:] = T[:, :, :, :0:-1]
    full[:, :, n1 + 1:, n2 + 1:] = T[:, :, :0:-1, :0:-1]
    return T, np.fft.fft2(full), (n1, n2)


# ------------------------------------------------------------------ assembly + solve
class Problem:
    def __init__(self, wires, plane=None):
        self.wires, self.plane = wires, plane
        self.t = {}

    def build(self):
        t0 = time.perf_counter()
        self.wslices, Rw, Cw_rows, nodes = [], [], [], 0
        self.wmodes = []
        for wi, wm in enumerate(self.wires):
            ann = [(wm["edges_r"][i], wm["edges_r"][i + 1]) for i in range(len(wm["edges_r"]) - 1)]
            areas = np.array([math.pi * (b * b - a * a) for a, b in ann])
            pts, modes, Wp = proxy_rule(wm["r"], ann, wm["P"])
            wm.update(ann=ann, areas=areas, pts=pts, modes=modes, Wp=Wp)
            for e in wm["edges"]:
                e["F"] = coax_tables(wm["edges_r"], e["s"], e["n"], wm["P"])
            node = start = nodes
            for ei, e in enumerate(wm["edges"]):
                for si in range(e["n"]):
                    for mi, (a, m, _c) in enumerate(modes):
                        self.wmodes.append((wi, ei, si, mi))
                        Rw.append(e["s"] / (wm["sig"] * areas[a]) * (1.0 if m == 0 else 0.5))
                        Cw_rows.append((node, node + 1) if m == 0 else None)
                    node += 1
            wm["port_nodes"] = (start, node)
            nodes = node + 1
        self.n_wnodes = nodes
        nw = len(self.wmodes)
        Lw = np.zeros((nw, nw))
        idx = {}
        for i, (wi, ei, _si, _mi) in enumerate(self.wmodes):
            idx.setdefault((wi, ei), []).append(i)
        for (wi, ei), ii in idx.items():
            wm = self.wires[wi]
            e = wm["edges"][ei]
            nm = len(wm["modes"])
            ii = np.array(ii).reshape(e["n"], nm)
            for mi, (a, m, c) in enumerate(wm["modes"]):
                for mj, (b, m2, c2) in enumerate(wm["modes"]):
                    if m != m2 or c != c2:
                        continue
                    eps = 2 * math.pi if m == 0 else math.pi
                    fac = K4 * eps / (wm["areas"][a] * wm["areas"][b])
                    kk = np.abs(np.arange(e["n"])[:, None] - np.arange(e["n"])[None, :])
                    Lw[np.ix_(ii[:, mi], ii[:, mj])] = fac * e["F"][kk, a, b, m]
        keys = list(idx)
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                (w1, e1), (w2, e2) = keys[x], keys[y]
                E1, E2 = self.wires[w1]["edges"][e1], self.wires[w2]["edges"][e2]
                if E1["ax"] != E2["ax"]:
                    continue
                B = self._far(self.wires[w1], E1, self.wires[w2], E2)
                i1, i2 = np.array(idx[keys[x]]), np.array(idx[keys[y]])
                Lw[np.ix_(i1, i2)] = B
                Lw[np.ix_(i2, i1)] = B.T
        self.Lw, self.Rw = Lw, np.array(Rw)
        self.Cw_rows = Cw_rows
        self.t["wire_kernel_s"] = time.perf_counter() - t0
        if self.plane is not None:
            self._build_plane()

    def _proxy_lines(self, wm, e):
        t1, t2 = (e["ax"] + 1) % 3, (e["ax"] + 2) % 3
        zs = np.minimum(e["p0"][e["ax"]], e["p1"][e["ax"]]) + e["s"] * np.arange(e["n"])
        if e["sgn"] < 0:
            zs = zs[::-1]
        tp = np.stack([e["p0"][t1] + wm["pts"][:, 0], e["p0"][t2] + wm["pts"][:, 1]], 1)
        return zs, tp

    def _far(self, w1, E1, w2, E2):
        z1, p1 = self._proxy_lines(w1, E1)
        z2, p2 = self._proxy_lines(w2, E2)
        d = np.hypot(p1[:, None, 0] - p2[None, :, 0], p1[:, None, 1] - p2[None, :, 1])
        K = K4 * E1["sgn"] * E2["sgn"] * fil_F(z1[:, None, None, None], z1[:, None, None, None] + E1["s"],
                                                z2[None, None, :, None], z2[None, None, :, None] + E2["s"],
                                                d[None, :, None, :])
        B = np.einsum("iqjr,qa,rb->iajb", K, w1["Wp"], w2["Wp"], optimize=True)
        return B.reshape(E1["n"] * w1["Wp"].shape[1], E2["n"] * w2["Wp"].shape[1])

    def _build_plane(self):
        t0 = time.perf_counter()
        pm = self.plane
        self.tabs = [plane_table(pm, 0), plane_table(pm, 1)]
        self.t["plane_kernel_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        nx, ny, nl = pm["nx"], pm["ny"], len(pm["lay"])
        self.np_x, self.np_y = nl * (nx - 1) * ny, nl * nx * (ny - 1)
        # wire-plane coupling through proxies: rows = wire modes, cols = plane filaments
        self.wp = []  # (mode rows, n_seg, n_modes, Wp, K (n_seg*Q, plane cols of this direction), col offset)
        coff = len(self.wmodes)
        for direction, (n1, n2) in ((0, (nx - 1, ny)), (1, (ny - 1, nx))):
            a_al, a_tr = (pm["ax"], pm["ay"]) if direction == 0 else (pm["ay"], pm["ax"])
            o_al, o_tr = (pm["x0"], pm["y0"]) if direction == 0 else (pm["y0"], pm["x0"])
            yw, ww = gq(6, 0.0, a_tr)
            ww = ww / a_tr
            row = 0
            for wm in self.wires:
                nm = len(wm["modes"])
                for e in wm["edges"]:
                    if e["ax"] != direction:
                        row += e["n"] * nm
                        continue
                    zs, tp = self._proxy_lines(wm, e)
                    t1 = (e["ax"] + 1) % 3  # transverse in-plane coordinate index in tp: for x-edge t1=y, t2=z
                    tr_pos, zpos = (tp[:, 0], tp[:, 1]) if t1 != 2 else (tp[:, 1], tp[:, 0])
                    al0 = o_al + a_al * (0.5 + np.arange(n1))
                    tr0 = o_tr + a_tr * np.arange(n2)
                    K = np.zeros((e["n"], tp.shape[0], nl, n1, n2))
                    for li, (zl0, zl1) in enumerate(pm["lay"]):
                        zq, wz = gq(2, zl0, zl1)
                        wz = wz / (zl1 - zl0)
                        for yy, wy in zip(yw, ww, strict=True):
                            for zz, wzz in zip(zq, wz, strict=True):
                                d = np.hypot(tr_pos[:, None] - (tr0[None, :] + yy), zpos[:, None] - zz)
                                K[:, :, li] += wy * wzz * fil_F(zs[:, None, None, None],
                                                               zs[:, None, None, None] + e["s"],
                                                               al0[None, None, :, None],
                                                               al0[None, None, :, None] + a_al,
                                                               d[None, :, None, :])
                    K *= K4 * e["sgn"]
                    self.wp.append((slice(row, row + e["n"] * nm), e["n"], nm, wm["Wp"],
                                    K.reshape(e["n"] * K.shape[1], -1), coff))
                    row += e["n"] * nm
            coff += nl * n1 * n2
        self.t["wire_plane_kernel_s"] = time.perf_counter() - t0
        # plane resistances and incidence
        R = []
        for direction, (n1, n2) in ((0, (nx - 1, ny)), (1, (ny - 1, nx))):
            a_al, a_tr = (pm["ax"], pm["ay"]) if direction == 0 else (pm["ay"], pm["ax"])
            for zl0, zl1 in pm["lay"]:
                R.append(np.full(n1 * n2, a_al / (pm["sig"] * a_tr * (zl1 - zl0))))
        self.Rp = np.concatenate(R)

    # ---------------------------------------------------------------- system pieces
    def incidence(self):
        rows, cols, vals = [], [], []
        nwn = self.n_wnodes
        for i, cr in enumerate(self.Cw_rows):
            if cr is not None:
                rows += [i, i]
                cols += [cr[0], cr[1]]
                vals += [1.0, -1.0]
        nw = len(self.wmodes)
        ncol = nwn
        if self.plane is not None:
            pm = self.plane
            nx, ny, nl = pm["nx"], pm["ny"], len(pm["lay"])
            nid = lambda i, j: nwn + i * ny + j  # noqa: E731
            off = nw
            for _li in range(nl):
                for i in range(nx - 1):
                    for j in range(ny):
                        rows += [off, off]
                        cols += [nid(i, j), nid(i + 1, j)]
                        vals += [1.0, -1.0]
                        off += 1
            for _li in range(nl):
                for j in range(ny - 1):
                    for i in range(nx):
                        rows += [off, off]
                        cols += [nid(i, j), nid(i, j + 1)]
                        vals += [1.0, -1.0]
                        off += 1
            ncol = nwn + nx * ny
        C = sp.csr_matrix((vals, (rows, cols)), shape=(self.n, ncol))
        ground = [self.wires[0]["port_nodes"][1]] + ([nwn] if self.plane is not None else [])
        keep = np.setdiff1d(np.arange(ncol), ground)
        d = np.zeros(ncol)
        d[self.wires[0]["port_nodes"][0]] = 1.0
        return C[:, keep].tocsc(), d[keep]

    @property
    def n(self):
        return len(self.wmodes) + (self.np_x + self.np_y if self.plane is not None else 0)

    def Lmul(self, x):
        nw = len(self.wmodes)
        y = np.zeros(x.shape, complex if self.plane is not None else x.dtype)
        y[:nw] = self.Lw @ x[:nw]
        if self.plane is not None:
            for rows, ns, nm, Wp, K, c0 in self.wp:
                xp = x[c0:c0 + K.shape[1]]
                y[rows] += ((K @ xp).reshape(ns, -1) @ Wp).ravel()
                y[c0:c0 + K.shape[1]] += K.T @ (x[rows].reshape(ns, nm) @ Wp.T).ravel()
            o = nw
            for (T, Th, (n1, n2)) in self.tabs:
                nl = T.shape[0]
                X = x[o:o + nl * n1 * n2].reshape(nl, n1, n2)
                Xh = np.fft.fft2(X, s=(2 * n1, 2 * n2))
                Y = np.fft.ifft2(np.einsum("abij,bij->aij", Th, Xh))[:, :n1, :n2]
                y[o:o + nl * n1 * n2] += Y.ravel()
                o += nl * n1 * n2
        return y

    def solve(self, f, dense=None, tol=1e-10):
        w = 2 * math.pi * f
        C, d = self.incidence()
        R = np.concatenate([self.Rw, self.Rp]) if self.plane is not None else self.Rw
        n, nc = self.n, C.shape[1]
        t0 = time.perf_counter()
        info = {}
        if dense or (dense is None and self.plane is None and n <= 16000):
            A = np.zeros((n + nc, n + nc), complex)
            A[:n, :n] = 1j * w * self.Lw
            A[np.arange(n), np.arange(n)] += R
            Cd = C.toarray()
            A[:n, n:] = -Cd
            A[n:, :n] = Cd.T
            rhs = np.concatenate([np.zeros(n), d])
            sol = sla.solve(A, rhs, overwrite_a=True, check_finite=False)
            x = sol[:n]
            info["method"] = "dense LU"
        else:
            x, it = self._gmres(w, R, C, d, tol)
            info["method"] = "GMRES+FFT"
            info["iters"] = it
        # exact KCL projection, stationary Z, a-posteriori bound
        lu = spla.splu((C.T @ C).tocsc())

        def cs(v):
            return lu.solve(np.ascontiguousarray(v.real)) + 1j * lu.solve(np.ascontiguousarray(v.imag))
        x = x - C @ cs(C.T @ x - d)
        Mx = R * x + 1j * w * self.Lmul(x)
        rho = Mx - C @ cs(C.T @ Mx)
        Z = x @ Mx
        bound = float(np.vdot(rho, rho).real) / R.min()
        rnd = 1e-16 * n * float(np.abs(x) @ (R * np.abs(x) + w * np.abs(self.Lmul(np.abs(x).astype(complex)))))
        info.update(solve_s=time.perf_counter() - t0, resid_bound=bound / abs(Z), round_bound=rnd / abs(Z))
        return Z, info

    def _gmres(self, w, R, C, d, tol):
        nw, n = len(self.wmodes), self.n
        # block preconditioner: per wire edge dense block, per plane branch layer block; Schur on nodes
        blocks = []
        for wi, wm in enumerate(self.wires):
            for ei in range(len(wm["edges"])):
                ii = np.array([i for i, mm in enumerate(self.wmodes) if mm[0] == wi and mm[1] == ei])
                Mb = 1j * w * self.Lw[np.ix_(ii, ii)]
                Mb[np.arange(ii.size), np.arange(ii.size)] += self.Rw[ii]
                blocks.append((ii, sla.lu_factor(Mb)))
        pb = []
        if self.plane is not None:
            o = nw
            for (T, _Th, (n1, n2)) in self.tabs:
                nl = T.shape[0]
                nb = n1 * n2
                ii = o + np.arange(nl)[:, None] * nb + np.arange(nb)[None, :]  # (nl, nb)
                Mb = 1j * w * T[:, :, 0, 0] + np.diag(R[ii[:, 0]])
                pb.append((ii, np.linalg.inv(Mb)))
                o += nl * nb

        def minv(v):
            out = np.zeros_like(v)
            for ii, f in blocks:
                out[ii] = sla.lu_solve(f, v[ii])
            for ii, Bi in pb:
                out[ii] = Bi @ v[ii]
            return out
        nc = C.shape[1]
        S = sp.lil_matrix((nc, nc), dtype=complex)
        for ii, f in blocks:
            Cb = C[ii, :]
            nz = np.unique(Cb.nonzero()[1])
            X = sla.lu_solve(f, Cb[:, nz].toarray().astype(complex))
            S[np.ix_(nz, nz)] = S[np.ix_(nz, nz)].toarray() + Cb[:, nz].T @ X
        S = S.tocsc()
        for ii, Bi in pb:
            y = Bi.sum(axis=0)  # admittance per layer column; branch admittance = 1^T Bi 1
            C0 = C[ii[0], :]
            S = S + (C0.T @ sp.diags(np.full(ii.shape[1], y.sum())) @ C0).tocsc()
        Slu = spla.splu(S.tocsc())

        def prec(v):
            f, g = v[:n], v[n:]
            mf = minv(f)
            phi = Slu.solve(g - C.T @ mf)
            return np.concatenate([minv(f + C @ phi), phi])

        def amul(v):
            x, phi = v[:n], v[n:]
            return np.concatenate([R * x + 1j * w * self.Lmul(x) - C @ phi, C.T @ x])
        A = spla.LinearOperator((n + nc, n + nc), matvec=amul, dtype=complex)
        Pm = spla.LinearOperator((n + nc, n + nc), matvec=prec, dtype=complex)
        rhs = np.concatenate([np.zeros(n, complex), d.astype(complex)])
        its = [0]
        sol, _ = spla.gmres(A, rhs, M=Pm, rtol=tol, atol=0.0, restart=300, maxiter=5,
                            callback=lambda _r: its.__setitem__(0, its[0] + 1), callback_type="pr_norm")
        return sol[:n], its[0]


def solve_case(case, freqs, k, sig, P=None):
    """E001-style call: one mesh for all freqs; returns z (nf,), meta (mesh_params, n_filaments, solver_tol...)."""
    fmax = max(freqs)
    wires, mp = [], {}
    has_plane = bool(case["planes"])
    single = len(case["conductors"]) == 1 and len(case["conductors"][0]["pts"]) == 2 and not has_plane
    for c in case["conductors"]:
        pz = P if P is not None else (0 if single else (6 if has_plane else 5))
        wm = wire_mesh(c, k, fmax, sig[c["mat"]], pz)
        wires.append(wm)
        mp.update({f"{kk}:{c['name']}": v for kk, v in wm["mp"].items()})
    plane = None
    if has_plane:
        pl = dict(case["planes"][0])
        pl["sigma"] = sig[pl["mat"]]
        r = wires[0]["r"]
        gap = min(abs(p[2] - pl["z_top"]) for p in case["conductors"][0]["pts"]) - r
        plane = plane_mesh(pl, k, fmax, gap)
        mp.update({f"{kk}:{pl['name']}": v for kk, v in plane["mp"].items()})
    t0 = time.perf_counter()
    pb = Problem(wires, plane)
    pb.build()
    zs, infos = [], []
    for f in freqs:
        z, info = pb.solve(f)
        zs.append(z)
        infos.append(info)
    meta = dict(mesh_params=mp, n_filaments=pb.n, n_wire=len(pb.wmodes), timings=pb.t,
                wall_s=time.perf_counter() - t0, infos=infos,
                solver_tol=max(i["resid_bound"] + i["round_bound"] for i in infos),
                mesh_hash=[f"k{k}-n{pb.n}"] * len(freqs))
    if plane is not None:
        meta.update(plane_nx=plane["nx"], plane_ny=plane["ny"], plane_layers=len(plane["lay"]))
    return np.array(zs), meta
