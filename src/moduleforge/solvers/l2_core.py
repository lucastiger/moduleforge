"""L2 core: exact-kernel round-wire PEEC, FFT-applied plane PEEC, compressed wire-to-plane coupling, bounded GMRES.

Productionised from the T0067 spike (research/scripts/spike_l2/l2proto.py; design reviewed in T0068).  SI units,
float64 (complex128 for impedances).  Everything the layout path (n4a) needs is a plain function or class here.

Model
-----
* Round wire: every straight, axis-aligned edge -> ``n`` equal segments; the cross-section -> graded annuli x azimuthal
  harmonics m <= P (cos/sin), current density 1_a(rho) T_m(phi) / A_a.  Coaxial couplings (same edge) are exact
  Toeplitz tables: the log part from the closed-form expansion ln|x-x'| = ln rho_> - sum (1/m)(rho_</rho_>)^m cos m
  theta (Gradshteyn-Ryzhik 1.514), the smooth remainder by Gauss x trapezoid (spectral), the |d| kink by graded Gauss.
  Other parallel edges and the plane couple through moment-matched proxy filaments (exact for transverse Taylor terms
  up to degree P; truncation ~ (r/D)^(P+1)).  Orthogonal pairs are exactly 0 (Neumann integral, [G] ch. 7).
* Plane: cell-centred node lattice (nx x ny cells), x- and y-branches on graded thickness layers.  The
  layer-pair kernel is computed once per distinct offset (Hoer-Love [HL] for |di|,|dj| <= N_NEAR, Gauss over the
  cross-sections beyond) and applied by FFT (block Toeplitz).
* Wire-to-plane coupling is compressed: for an edge whose segment length equals the plane's axial cell the coupling
  is Toeplitz in the axial index, so it is stored as one table per (proxy, layer, lateral row, axial offset) and
  applied by FFT along the edge (memory O(Q nl n2 (n_seg + n1)) instead of O(Q n_seg nl n1 n2)); it is exact (no
  compression error).  A segment length that does not match the plane lattice raises NotImplementedError (the
  axial-resampling extension is the layout path's work).
* Solve: dense LU for small systems, otherwise GMRES with a block (wire sector / plane layer / nodal Schur)
  preconditioner.  The reported bound is the rigorous a-posteriori bound ||P(Mx)||^2 / r_min plus rounding plus the
  stated bounds of the quadratures and of the proxy truncation (see ``Stated``).

References: [G] F. W. Grover, Inductance Calculations (1946) ch. 7 (filament Neumann integral);
[HL] Hoer & Love, J. Res. NBS 69C (1965) 127; [RWV] Ramo-Whinnery-Van Duzer 5.6 (skin effect);
[AT] Trefethen, Approximation Theory and Approximation Practice (2013) Thm 19.3 (Gauss error, Bernstein ellipse).
"""
from __future__ import annotations

import hashlib
import itertools
import math
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import scipy.fft as sfft
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from numpy.polynomial.legendre import leggauss

MU0 = 4e-7 * math.pi
K4 = MU0 / (4 * math.pi)
COUNTS = {1: 9, 2: 12, 3: 16, 4: 21, 5: 28}  # annuli per wire cross-section; realized ratios 1.333 1.333 1.3125 1.333
SEGMENTS = {1: 14, 2: 18, 3: 24, 4: 32, 5: 42}  # segments per wire edge (= plane cells per segment axis); ratios 1.286 1.333 1.333 1.3125
LAYERS = {k: round(0.5 * s) for k, s in SEGMENTS.items()}  # plane thickness layers: 7 9 12 16 21
MAX_REFINEMENT = 5
N_NEAR = 4  # plane tables: Hoer-Love box formula for |di|, |dj| <= N_NEAR, Gauss over cross-sections beyond
NTHREADS = max(1, os.cpu_count() or 1)
UNIT_ROUNDOFF = 1.1102230246251565e-16
ELLIPSE_M = 10.0  # assumed |f| bound on the Bernstein ellipse relative to max|f| on the real interval (stated, see Stated)


def skin(f: float, sig: float) -> float:
    """Skin depth sqrt(1/(pi f mu0 sigma)) [RWV]."""
    return 1.0 / math.sqrt(math.pi * f * MU0 * sig)


@lru_cache(maxsize=None)
def _leggauss(n: int):
    return leggauss(n)


def gq(n: int, a: float, b: float):
    """Gauss-Legendre nodes and weights on [a, b]."""
    x, w = _leggauss(n)
    return 0.5 * (b - a) * x + 0.5 * (a + b), 0.5 * (b - a) * w


def gfun(u, d):
    """g(u, d) = u asinh(u/d) - sqrt(u^2 + d^2) [G] ch. 7."""
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def fil_F(a1, a2, b1, b2, d):
    """int int dz dz' / R of two parallel filaments spanning [a1,a2], [b1,b2], transverse distance d > 0 [G] ch. 7."""
    return gfun(a2 - b1, d) + gfun(a1 - b2, d) - gfun(a1 - b1, d) - gfun(a2 - b2, d)


def gauss_bound(n: int, rho: float) -> float:
    """Relative Gauss-Legendre error bound (64/15) M rho^(-2n) / (rho^2 - 1) for an integrand analytic inside the
    Bernstein ellipse of parameter rho [AT Thm 19.3], with M = ELLIPSE_M x max|f| (a stated assumption)."""
    return 64.0 / 15.0 * ELLIPSE_M * rho ** (-2 * n) / (rho * rho - 1.0)


QUAD_TOL = 1e-14  # target of the Gauss orders of the plane / wire-to-plane tables (bound, not measurement)


def gauss_order(rho: float, tol: float | None = None, nmin: int = 3, nmax: int = 24) -> int:
    """Smallest Gauss order whose ``gauss_bound`` is <= tol (default QUAD_TOL)."""
    tol = QUAD_TOL if tol is None else tol
    for n in range(nmin, nmax + 1):
        if gauss_bound(n, rho) <= tol:
            return n
    return nmax


# ---------------------------------------------------------------------------------------------- Hoer-Love boxes
def hl_f(x, y, z):
    """Hoer-Love function whose second derivative in each variable is 1/R [HL eq. 14]."""
    x, y, z = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    x2, y2, z2 = x * x, y * y, z * z
    r = np.sqrt(x2 + y2 + z2)
    out = (x2 * x2 + y2 * y2 + z2 * z2 - 3 * x2 * y2 - 3 * y2 * z2 - 3 * z2 * x2) * r / 60.0

    def logt(a, b2, c2):
        rho = np.sqrt(b2 + c2)
        safe = np.where(rho > 0, rho, 1.0)
        return np.where(rho > 0, (6 * b2 * c2 - b2 * b2 - c2 * c2) * a * np.arcsinh(a / safe), 0.0) / 24.0

    def tant(a, b, c, c2):
        den = c * r
        safe = np.where(den != 0, den, 1.0)
        return np.where(den != 0, a * b * c * c2 * np.arctan(a * b / safe), 0.0) / 6.0

    out = out + logt(x, y2, z2) + logt(y, x2, z2) + logt(z, x2, y2)
    out = out - tant(x, y, z, z2) - tant(x, z, y, y2) - tant(z, y, x, x2)
    return out


def hl_box(lo1, hi1, lo2, hi2, axis: int):
    """Mutual partial inductance (H) of parallel boxes (rows of (m, 3) arrays) carrying uniform current along ``axis``,
    per unit current in each [HL]."""
    tot = 0.0
    for (s0, i0), (s1, i1), (s2, i2) in itertools.product(*[[(1, 0), (-1, 1), (-1, 2), (1, 3)]] * 3):
        u = []
        for dd, ii in zip(range(3), (i0, i1, i2), strict=True):
            u.append([hi2[:, dd] - lo1[:, dd], hi2[:, dd] - hi1[:, dd], lo2[:, dd] - lo1[:, dd],
                      lo2[:, dd] - hi1[:, dd]][ii])
        tot = tot + s0 * s1 * s2 * hl_f(*u)
    tr = [d for d in range(3) if d != axis]
    a1 = (hi1[:, tr[0]] - lo1[:, tr[0]]) * (hi1[:, tr[1]] - lo1[:, tr[1]])
    a2 = (hi2[:, tr[0]] - lo2[:, tr[0]]) * (hi2[:, tr[1]] - lo2[:, tr[1]])
    return K4 * tot / (a1 * a2)


def _pmap(fn, items):
    """Thread-parallel map (numpy ufuncs release the GIL)."""
    items = list(items)
    if NTHREADS == 1 or len(items) == 1:
        return [fn(i) for i in items]
    with ThreadPoolExecutor(max_workers=NTHREADS) as ex:
        return list(ex.map(fn, items))


# ---------------------------------------------------------------------------------------------- coaxial tables
def _p(x, k):
    return math.log(x) if k == -1 else x ** (k + 1) / (k + 1)


def _rl(x, k):
    return 0.0 if x == 0 else x ** (k + 1) / (k + 1) * math.log(x) - x ** (k + 1) / (k + 1) ** 2


def ring_log(a, b, m):
    """int_a int_b rho rho' K drho drho', K = ln max (m=0) or (min/max)^m; annuli identical or disjoint."""
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


@lru_cache(maxsize=64)
def _coax_tables_cached(edges_r: tuple, s: float, n_seg: int, P: int, ng: int, nth: int, ngk: int, panels: int):
    F, g = _coax_tables(np.array(edges_r), s, n_seg, P, ng, nth, ngk, panels)
    # nested-rule error estimate of a spectrally convergent rule: the difference to a 1.5x richer rule bounds the error
    # of the coarser one (the richer rule's own error is orders smaller); x10 safety, floor 1e-15 (rounding)
    F2, _ = _coax_tables(np.array(edges_r), s, n_seg, P, ng + 4, nth * 3 // 2, ngk * 3 // 2, panels * 3 // 2)
    rel = 10.0 * (np.abs(F - F2).max(axis=0) / np.maximum(g, 1e-300)) + 1e-15
    return F2, g, rel




def coax_tables(edges_r, s, n_seg, P, ng=8, nth=128, ngk=64, panels=60):
    """F[k, a, b, m] = int_a int_b rho rho' int cos(m th) F_k(d) dth for segment offset k (k = 0 .. n_seg-1), without
    the factor K4 eps_m / (A_a A_b); the second difference of the offset table gamma_k = int int (-|u|-type kernel)."""
    return coax_tables_scaled(edges_r, s, n_seg, P, ng, nth, ngk, panels)[0]


def coax_tables_scaled(edges_r, s, n_seg, P, ng=8, nth=128, ngk=64, panels=60):
    """(F, g, rel): the table (from the richer of the two nested rules), g[a, b, m] = max_k |gamma_k[a, b, m]| and the
    stated entry-error scale rel[a, b, m]: every entry of F is accurate to 4 rel g (second difference of gamma)."""
    return _coax_tables_cached(tuple(float(v) for v in edges_r), float(s), int(n_seg), int(P), ng, nth, ngk, panels)


def _coax_tables(edges_r, s, n_seg, P, ng, nth, ngk, panels):
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
        proj = sv @ cosm
        proj = proj * wg[:, None, None] * wg[None, :, None]
        tab = proj.reshape(nr, ng, nr, ng, P + 1).sum(axis=(1, 3))
        gam[iu] = -u * lam + tab
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
    return gam[np.abs(k - 1)] + gam[k + 1] - 2 * gam[k], np.abs(gam).max(axis=0)


# ---------------------------------------------------------------------------------------------- proxies
def proxy_rule(r, ann, P):
    """Moment-matched proxy filaments: points (Q, 2) and weights W[sigma, a, q] (sector sigma = 0 for m = 0, 2m-1 / 2m
    for cos / sin m), exact for transverse monomials of degree <= P about the axis."""
    npr, nph = P // 2 + 1, 2 * P + 1
    xg, _ = gq(npr, 0.0, 1.0)
    rho = r * np.sqrt(xg)
    phi = 2 * math.pi * np.arange(nph) / nph
    pts = np.array([(rr * math.cos(p), rr * math.sin(p)) for rr in rho for p in phi])
    W = np.zeros((2 * P + 1, len(ann), pts.shape[0]))
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
                sig = 0 if m == 0 else 2 * m - 1 + c
                W[sig, a] = np.outer(ug, t * (1 if m == 0 else 2) / nph).ravel()
    return pts, W


def proxy_truncation_bound(r: float, dist: float, P: int) -> float:
    """Stated relative bound of the degree-P proxy truncation for a source of radius r seen from distance ``dist``
    (axis to the nearest source point): the multipole series ratio q = r / (dist - r), bound q^(P+1) / (1 - q)."""
    q = r / (dist - r)
    return float("inf") if q >= 1.0 else q ** (P + 1) / (1.0 - q)


def choose_P(r: float, dist: float, target: float, pmin: int = 3, pmax: int = 10) -> int:
    """Smallest P in [pmin, pmax] with ``proxy_truncation_bound`` <= target (pmax if none)."""
    for p in range(pmin, pmax + 1):
        if proxy_truncation_bound(r, dist, p) <= target:
            return p
    return pmax


# ---------------------------------------------------------------------------------------------- meshes
@dataclass
class WireSpec:
    name: str
    points: np.ndarray  # (nv, 3) polyline vertices (m)
    diameter: float
    sigma: float


@dataclass
class PlaneSpec:
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    z_top: float
    thickness: float
    sigma: float


@dataclass
class EdgeMesh:
    p0: np.ndarray
    p1: np.ndarray
    ax: int
    sgn: float
    n: int
    hs: float
    node0: int  # global node index of the start of segment 0 (flow order)
    off: int = 0  # offset of this edge's modes in the unknown vector
    Lm: np.ndarray | None = None  # (P+1, N, N) coaxial blocks, N = n nr
    R: np.ndarray | None = None  # (nsig, n, nr)


@dataclass
class WireMesh:
    spec: WireSpec
    r: float
    P: int
    edges_r: np.ndarray
    areas: np.ndarray
    pts: np.ndarray  # (Q, 2) proxy points
    W: np.ndarray  # (nsig, nr, Q)
    edges: list[EdgeMesh]
    node_base: int
    n_nodes: int
    vertex_node: list[int]  # node index of each polyline vertex


@dataclass
class PlaneMesh:
    spec: PlaneSpec
    nx: int
    ny: int
    ax: float
    ay: float
    layers: list[tuple[float, float]]
    mp: dict
    node_base: int = 0


def grading_rate(target: float, c0: int) -> float:
    """Grading rate g with G(1/c0) = target, G(xi) = (e^(g xi) - 1) / (e^g - 1) (0 if uniform cells already finer)."""
    if target >= 1.0 / c0:
        return 0.0
    lo, hi = 1e-6, 60.0
    for _ in range(200):
        g = 0.5 * (lo + hi)
        val = math.expm1(g / c0) / math.expm1(g)
        lo, hi = (g, hi) if val > target else (lo, g)
    return 0.5 * (lo + hi)


def graded_fractions(n: int, g: float) -> np.ndarray:
    """Cumulative fractions 0 = f_0 < ... < f_n = 1 of a grading with rate g, measured from the finest cell."""
    xi = np.arange(n + 1) / n
    return xi if g <= 1e-8 else np.expm1(g * xi) / math.expm1(g)


def build_wire_mesh(spec: WireSpec, level: int, fmax: float, P: int, node_base: int) -> WireMesh:
    r = spec.diameter / 2
    c, nseg = COUNTS[level], SEGMENTS[level]
    g = grading_rate(0.5 * skin(fmax, spec.sigma) / r, COUNTS[1])
    fr = graded_fractions(c, g)
    edges_r = r * (1.0 - fr[::-1])
    edges_r[0], edges_r[-1] = 0.0, r
    ann = [(edges_r[i], edges_r[i + 1]) for i in range(c)]
    areas = np.array([math.pi * (b * b - a * a) for a, b in ann])
    pts, W = proxy_rule(r, ann, P)
    edges, node = [], node_base
    vertex_node = [node_base]
    p = np.asarray(spec.points, float)
    for e in range(len(p) - 1):
        d = p[e + 1] - p[e]
        if np.count_nonzero(np.abs(d) > 1e-15 * max(1.0, np.abs(p).max())) != 1:
            raise NotImplementedError("inclined wire edge: only axis-parallel edges are supported (layout path)")
        ax = int(np.argmax(np.abs(d)))
        length = abs(d[ax])
        edges.append(EdgeMesh(p0=p[e], p1=p[e + 1], ax=ax, sgn=float(np.sign(d[ax])), n=nseg, hs=length / nseg, node0=node))
        node += nseg
        vertex_node.append(node)
    return WireMesh(spec=spec, r=r, P=P, edges_r=edges_r, areas=areas, pts=pts, W=W, edges=edges,
                    node_base=node_base, n_nodes=node - node_base + 1, vertex_node=vertex_node)


def _layer_edges(spec: PlaneSpec, level: int, fmax: float) -> list[tuple[float, float]]:
    n = LAYERS[level]
    g = grading_rate(0.5 * skin(fmax, spec.sigma) / spec.thickness, LAYERS[1])
    depth = spec.thickness * graded_fractions(n, g)
    return [(spec.z_top - depth[i + 1], spec.z_top - depth[i]) for i in range(n)]


def build_plane_mesh(spec: PlaneSpec, wires: list[WireMesh], level: int, fmax: float) -> PlaneMesh:
    """Cell-centred lattice.  Along each axis the cell size equals the segment length of the wire edges parallel to
    that axis (so the wire-to-plane coupling is axially Toeplitz); with no such edge it is W / (4 c)."""
    c = SEGMENTS[level]
    sizes = []
    for axis, (lo, hi) in enumerate(((spec.x_min, spec.x_max), (spec.y_min, spec.y_max))):
        ext = hi - lo
        hs = {round(e.hs, 15): e.hs for w in wires for e in w.edges if e.ax == axis}
        if not hs:
            n = 4 * c
        else:
            if len(hs) > 1 and max(hs.values()) / min(hs.values()) - 1.0 > 1e-9:
                raise NotImplementedError("edges parallel to one axis with different segment lengths (layout path)")
            n_f = ext / next(iter(hs.values()))
            n = int(round(n_f))
            if n < 2 or abs(n_f - n) > 1e-7 * n:
                raise NotImplementedError("plane extent is not a whole number of wire segments (layout path)")
        sizes.append(n)
    nx, ny = sizes
    lay = _layer_edges(spec, level, fmax)
    ax_, ay_ = (spec.x_max - spec.x_min) / nx, (spec.y_max - spec.y_min) / ny
    mp = {"plane_x": ax_, "plane_y": ay_, "plane_layer": lay[0][1] - lay[0][0]}
    return PlaneMesh(spec=spec, nx=nx, ny=ny, ax=ax_, ay=ay_, layers=lay, mp=mp)


# ---------------------------------------------------------------------------------------------- plane tables
def plane_table(lay_a, lay_b, ax_al: float, a_tr: float, n1: int, n2: int, near: int = N_NEAR):
    """T[a, b, di, dj] = mutual partial inductance (H) of two axis-parallel branches (axial length ax_al, lateral band
    a_tr) in layers lay_a[a], lay_b[b] at lattice offset (di axial, dj lateral), di in [0, n1), dj in [0, n2), computed
    once per distinct (offset, layer pair).  Hoer-Love [HL] for di, dj <= near; beyond, exact in the axial direction and
    Gauss over both cross-sections.  Returns (T, stated relative quadrature bound)."""
    na, nb = len(lay_a), len(lay_b)
    di, dj = np.meshgrid(np.arange(n1), np.arange(n2), indexing="ij")
    di, dj = di.ravel(), dj.ravel()
    nr_ = (di <= near) & (dj <= near)
    fi, ni = np.where(~nr_)[0], np.where(nr_)[0]
    dmin = near * min(ax_al, a_tr)
    h_y = 0.5 * a_tr
    ny_ord = gauss_order(1.0 + dmin / h_y)
    # int int over two bands of f(yb - ya) = int_{-a}^{a} (a - |t|) f(t) dt, split at the kink t = 0
    tn, wn = gq(ny_ord, -a_tr, 0.0)
    tp_, wp_ = gq(ny_ord, 0.0, a_tr)
    tt = np.concatenate([tn, tp_])
    wt = np.concatenate([wn * (a_tr + tn), wp_ * (a_tr - tp_)]) / (a_tr * a_tr)
    T = np.zeros((na, nb, n1, n2))
    bound = gauss_bound(ny_ord, 1.0 + dmin / h_y)

    def one(ab):
        la, lb = ab
        z1, z2 = lay_a[la], lay_b[lb]
        hz = 0.5 * max(z1[1] - z1[0], z2[1] - z2[0])
        nz = gauss_order(1.0 + dmin / hz, nmin=2)
        za, wza = gq(nz, *z1)
        zb, wzb = gq(nz, *z2)
        wza, wzb = wza / (z1[1] - z1[0]), wzb / (z2[1] - z2[0])
        dz = (zb[None, :] - za[:, None]).ravel()
        wz = np.outer(wza, wzb).ravel()
        dtr = dj[fi][:, None] * a_tr + tt[None, :]  # (nfar, nt)
        d = np.maximum(np.hypot(dtr[:, :, None], dz[None, None, :]), 1e-300)  # (nfar, nt, nzz)
        # second difference over the axial lattice: F_di = g(u_{di+1}) + g(u_{di-1}) - 2 g(u_{di}) (aligned boxes)
        ud = ax_al * di[fi]
        gp = gfun((ud + ax_al)[:, None, None], d)
        gm = gfun((ud - ax_al)[:, None, None], d)
        g0 = gfun(ud[:, None, None], d)
        f = gp + gm - 2.0 * g0
        val = np.einsum("ftz,t,z->f", f, wt, wz) * K4
        out = np.zeros(di.size)
        out[fi] = val
        if ni.size:
            lo1 = np.tile([0.0, 0.0, z1[0]], (ni.size, 1))
            hi1 = np.tile([ax_al, a_tr, z1[1]], (ni.size, 1))
            lo2 = np.stack([di[ni] * ax_al, dj[ni] * a_tr, np.full(ni.size, z2[0])], 1)
            hi2 = lo2 + np.array([ax_al, a_tr, z2[1] - z2[0]])
            out[ni] = hl_box(lo1, hi1, lo2, hi2, 0)
        return la, lb, out.reshape(n1, n2), gauss_bound(nz, 1.0 + dmin / hz)

    res = _pmap(one, [(a, b) for a in range(na) for b in range(nb)])
    for la, lb, v, bz in res:
        T[la, lb] = v
        bound += bz
    return T, bound


def circulant_fft(T: np.ndarray) -> np.ndarray:
    """FFT of the (2 n1, 2 n2) symmetric circulant embedding of the offset table T[a, b, di, dj], laid out as
    (ij, a, b) for batched matmul (real: the embedding is even in both axes)."""
    na, nb, n1, n2 = T.shape
    full = np.zeros((na, nb, 2 * n1, 2 * n2))
    full[:, :, :n1, :n2] = T
    full[:, :, n1 + 1:, :n2] = T[:, :, :0:-1, :]
    full[:, :, :n1, n2 + 1:] = T[:, :, :, :0:-1]
    full[:, :, n1 + 1:, n2 + 1:] = T[:, :, :0:-1, :0:-1]
    th = sfft.fft2(full, axes=(2, 3), workers=NTHREADS).real
    return np.ascontiguousarray(th.reshape(na, nb, -1).transpose(2, 0, 1))


def circulant_apply(Thr: np.ndarray, X: np.ndarray) -> np.ndarray:
    """y = T x for the block-Toeplitz table (``circulant_fft``) and X of shape (nb, n1, n2) (complex ok)."""
    nb, n1, n2 = X.shape
    Xh = sfft.fft2(X, s=(2 * n1, 2 * n2), axes=(1, 2), workers=NTHREADS)
    Y = np.matmul(Thr, Xh.reshape(nb, -1).T[:, :, None])[:, :, 0]  # (ij, a)
    Y = Y.T.reshape(Thr.shape[1], 2 * n1, 2 * n2)
    return sfft.ifft2(Y, axes=(1, 2), workers=NTHREADS)[:, :n1, :n2]


# ---------------------------------------------------------------------------------------------- wire -> plane
@dataclass
class WirePlaneOp:
    """Compressed coupling of one wire edge (axis ``ax``, n segments of length hs equal to the plane's axial cell) to
    the plane branches parallel to it.  Table T[q, layer, lateral row, t] (t = s_geo - i + n1 - 1) applied by FFT along
    the edge: exact, memory O(Q nl n2 (n + n1))."""
    That: np.ndarray  # (F, Q, L) complex, L = nl * n2
    n: int
    n1: int
    n2: int
    nl: int
    nf: int
    flip: bool
    bound: float

    def to_wire(self, X: np.ndarray) -> np.ndarray:
        """X (nl, n1, n2) real or complex -> (n, Q) in flow order."""
        if np.iscomplexobj(X):
            return self._to_wire(X.real) + 1j * self._to_wire(X.imag)
        return self._to_wire(X)

    def _to_wire(self, X):
        Xh = sfft.rfft(X, n=self.nf, axis=1, workers=NTHREADS)  # (nl, F, n2)
        Xh = np.ascontiguousarray(Xh.transpose(1, 0, 2).reshape(Xh.shape[1], -1))
        out = np.matmul(self.That, Xh[:, :, None])[:, :, 0]  # (F, Q)
        y = sfft.irfft(out, n=self.nf, axis=0, workers=NTHREADS)
        y = y[self.n1 - 1:self.n1 - 1 + self.n]
        return y[::-1] if self.flip else y

    def to_plane(self, w: np.ndarray) -> np.ndarray:
        """w (n, Q) in flow order -> (nl, n1, n2)."""
        if np.iscomplexobj(w):
            return self._to_plane(w.real) + 1j * self._to_plane(w.imag)
        return self._to_plane(w)

    def _to_plane(self, w):
        wg = w[::-1] if self.flip else w
        wh = sfft.rfft(wg[::-1], n=self.nf, axis=0, workers=NTHREADS)  # (F, Q)
        yh = np.matmul(wh[:, None, :], self.That)[:, 0, :]  # (F, L)
        y = sfft.irfft(yh, n=self.nf, axis=0, workers=NTHREADS)
        y = y[self.n + self.n1 - 2 - np.arange(self.n1)]  # (n1, L)
        return y.reshape(self.n1, self.nl, self.n2).transpose(1, 0, 2)


def wire_plane_op(wm: WireMesh, e: EdgeMesh, pm: PlaneMesh) -> WirePlaneOp:
    """Build the compressed wire-to-plane operator of edge ``e`` (axis 0 or 1) with the plane lattice of ``pm``."""
    ax = e.ax
    t1, t2 = (ax + 1) % 3, (ax + 2) % 3
    tp = np.stack([e.p0[t1] + wm.pts[:, 0], e.p0[t2] + wm.pts[:, 1]], 1)
    if ax == 0:
        tr, zpos = tp[:, 0], tp[:, 1]
        a_al, a_tr, o_al, o_tr = pm.ax, pm.ay, pm.spec.x_min, pm.spec.y_min
        n1, n2 = pm.nx - 1, pm.ny
    else:
        tr, zpos = tp[:, 1], tp[:, 0]
        a_al, a_tr, o_al, o_tr = pm.ay, pm.ax, pm.spec.y_min, pm.spec.x_min
        n1, n2 = pm.ny - 1, pm.nx
    if abs(e.hs - a_al) > 1e-9 * a_al:
        raise NotImplementedError("wire segment length differs from the plane's axial cell (layout path)")
    lay = pm.layers
    nl, nq, n = len(lay), tp.shape[0], e.n
    gap = float(np.min(zpos) - lay[0][1])
    if gap <= 0:
        raise ValueError("wire proxy points must lie above the plane top")
    h_y = 0.5 * a_tr
    ny_ord = gauss_order(1.0 + gap / h_y)
    y_n, y_w = gq(ny_ord, 0.0, a_tr)
    y_w = y_w / a_tr
    zs0 = min(e.p0[ax], e.p1[ax])
    c0 = zs0 - o_al - 0.5 * a_al
    m = np.arange(-n1, n + 1)
    um = c0 + m * a_al
    nt = n + n1 - 1
    rows = o_tr + a_tr * np.arange(n2)
    nzs = [gauss_order(1.0 + gap / (0.5 * (z1 - z0)), nmin=2) for z0, z1 in lay]
    bound = gauss_bound(ny_ord, 1.0 + gap / h_y) + max(
        gauss_bound(nz, 1.0 + gap / (0.5 * (z1 - z0))) for nz, (z0, z1) in zip(nzs, lay, strict=True))
    nf = sfft.next_fast_len(max(n + 2 * n1, 2 * n + n1) + 2, real=True)
    T0 = np.zeros((nq, nl, n2, nf))

    def job(args):
        li, qs = args
        z0, z1 = lay[li]
        zq, zw = gq(nzs[li], z0, z1)
        zw = zw / (z1 - z0)
        dy = tr[qs, None, None] - (rows[None, :, None] + y_n[None, None, :])  # (q, j, y)
        dz = zpos[qs, None] - zq[None, :]  # (q, z)
        d = np.hypot(dy[:, :, :, None], dz[:, None, None, :])  # (q, j, y, z)
        w = y_w[:, None] * zw[None, :]  # (y, z)
        for k in range(qs.size):
            dk = d[k]
            g = gfun(um[:, None, None, None], dk[None])  # (M, j, y, z)
            f = g[2:] + g[:-2] - 2.0 * g[1:-1]  # t' = m[1:-1]
            T0[qs[k], li, :, :nt] = np.einsum("tjyz,yz->jt", f, w) * K4
        return None

    chunks = np.array_split(np.arange(nq), max(1, min(nq, NTHREADS)))
    _pmap(job, [(li, qs) for li in range(nl) for qs in chunks])
    That = sfft.rfft(T0, axis=-1, workers=NTHREADS)  # (Q, nl, n2, F)
    T0 = None  # free before the transpose copy
    That = np.ascontiguousarray(That.transpose(3, 0, 1, 2).reshape(That.shape[3], nq, nl * n2))
    return WirePlaneOp(That=That, n=n, n1=n1, n2=n2, nl=nl, nf=nf, flip=e.sgn < 0, bound=bound)


# ---------------------------------------------------------------------------------------------- stated bounds
@dataclass
class Stated:
    """Stated (not measured) relative bounds on the entries of the operator parts, all counted in solver_tol:
    kernel = coaxial tables (absolute error 4 rel max|gamma| per entry, counted through the L1 norms of the
    edge currents; reported separately, this field stays 0), proxy = degree-P truncation ~ (r/D)^(P+1), plane = plane-table quadrature,
    wp = wire-to-plane quadrature.  Quadrature bounds follow [AT Thm 19.3] with ``ELLIPSE_M`` (assumption: the
    integrand stays within a factor ELLIPSE_M of its real maximum on the Bernstein ellipse)."""
    kernel: float = 0.0
    proxy: float = 0.0
    plane: float = 0.0
    wp: float = 0.0

    @property
    def total(self) -> float:
        return self.kernel + self.proxy + self.plane + self.wp


def _edge_lines(specs: list[WireSpec]):
    out = []
    for wi, s in enumerate(specs):
        p = np.asarray(s.points, float)
        for e in range(len(p) - 1):
            d = p[e + 1] - p[e]
            if np.count_nonzero(np.abs(d) > 1e-15 * max(1.0, np.abs(p).max())) != 1:
                raise NotImplementedError("inclined wire edge: only axis-parallel edges are supported (layout path)")
            out.append((wi, e, int(np.argmax(np.abs(d))), p[e]))
    return out


def _coupled_distances(specs: list[WireSpec], plane: PlaneSpec | None) -> list[tuple[WireSpec, float]]:
    """(wire spec, distance) for every coupled far pair seen from each wire: axis distance to a parallel edge, or the
    height of the edge axis above the plane top."""
    lines = _edge_lines(specs)
    need = []
    for i, (wi, _, ax, p0) in enumerate(lines):
        r = specs[wi].diameter / 2
        if plane is not None and ax != 2:
            need.append((specs[wi], float(p0[2]) - plane.z_top))
        for wj, _, axj, q0 in lines[i + 1:]:
            if axj != ax:
                continue
            t = [(ax + 1) % 3, (ax + 2) % 3]
            dist = float(np.hypot(p0[t[0]] - q0[t[0]], p0[t[1]] - q0[t[1]]))
            if dist < 2.5 * max(r, specs[wj].diameter / 2):
                raise NotImplementedError("collinear or touching parallel wire edges (layout path)")
            need.append((specs[wi], dist))
            need.append((specs[wj], dist))
    return need


def select_P(specs: list[WireSpec], plane: PlaneSpec | None) -> tuple[int, float]:
    """Proxy/harmonic order P and the stated proxy-truncation bound: smallest P (>= 3) whose truncation bound at the
    closest coupled pair is <= 1e-9 (no plane) or 2e-7 (plane); 0 when no pair is coupled."""
    target = 2e-7 if plane is not None else 1e-9
    need = _coupled_distances(specs, plane)
    if not need:
        return 0, 0.0
    if any(d <= s.diameter / 2 for s, d in need):
        raise ValueError("wire edge intersects its neighbour or the plane")
    P = max(choose_P(s.diameter / 2, d, target / 2.0) for s, d in need)
    return P, max(2.0 * proxy_truncation_bound(s.diameter / 2, d, P) for s, d in need)


# ---------------------------------------------------------------------------------------------- the linear system
class System:
    """Unknowns: wire modes (per edge an array (nsig, n, nr)), plane x-branch currents (nl, nx-1, ny), plane y-branch
    currents (nl, ny-1, nx).  M = R + j w L with L assembled from coaxial blocks, proxy pairs, the compressed
    wire-to-plane operators and the FFT plane tables."""

    def __init__(self, wires: list[WireMesh], plane: PlaneMesh | None, stated: Stated):
        self.wires, self.plane, self.stated = wires, plane, stated
        off = 0
        self.edges: list[tuple[WireMesh, EdgeMesh]] = []
        for wm in wires:
            for e in wm.edges:
                e.off = off
                off += (2 * wm.P + 1) * e.n * (len(wm.edges_r) - 1)
                self.edges.append((wm, e))
        self.n_wire = off
        self.n_wnodes = sum(w.n_nodes for w in wires)
        self.P = wires[0].P
        self.sec_m = np.array([0] + [m for m in range(1, self.P + 1) for _ in (0, 1)])
        self._build_wire()
        self._build_plane()
        self.n = self.n_wire + self.n_plane
        self.R = self._build_R()

    # -- wire parts
    def _build_wire(self):
        P, sec = self.P, self.sec_m
        eps = np.array([2 * math.pi] + [math.pi] * P)
        self.Lsec, self._Labs = [], {}
        self.kern_err = []
        for wm, e in self.edges:
            nr = len(wm.edges_r) - 1
            F, gmax, relerr = coax_tables_scaled(wm.edges_r, e.hs, e.n, P)
            kk = np.abs(np.arange(e.n)[:, None] - np.arange(e.n)[None, :])
            fac = K4 * eps[None, None, :] / (wm.areas[:, None, None] * wm.areas[None, :, None])
            G = F[kk] * fac[None, None]  # (s, s', a, b, m)
            e.Lm = np.ascontiguousarray(G.transpose(4, 0, 2, 1, 3).reshape(P + 1, e.n * nr, e.n * nr))
            self.Lsec.append(e.Lm[sec])
            area_fac = np.where(sec == 0, 1.0, 0.5)[:, None, None]
            e.R = e.hs / (wm.spec.sigma * wm.areas)[None, None, :] * area_fac * np.ones((1, e.n, 1))
            # absolute error of an entry of Lm: second difference of gamma tables -> 4 rel max|gamma| x factor
            E = np.moveaxis(fac * 4.0 * relerr * gmax, 2, 0)[sec]  # (nsig, a, b) entry-error bounds, k-independent
            self.kern_err.append(E)
        self.pairs = []
        for i, (wa, ea) in enumerate(self.edges):
            for j in range(i + 1, len(self.edges)):
                wb, eb = self.edges[j]
                if ea.ax != eb.ax:
                    continue
                self.pairs.append((i, j, self._far(wa, ea, wb, eb), ea.sgn * eb.sgn))

    @staticmethod
    def _proxy_lines(wm: WireMesh, e: EdgeMesh):
        ax = e.ax
        t1, t2 = (ax + 1) % 3, (ax + 2) % 3
        zs = min(e.p0[ax], e.p1[ax]) + e.hs * np.arange(e.n)
        if e.sgn < 0:
            zs = zs[::-1]
        return zs, np.stack([e.p0[t1] + wm.pts[:, 0], e.p0[t2] + wm.pts[:, 1]], 1)

    def _far(self, wa, ea, wb, eb):
        z1, p1 = self._proxy_lines(wa, ea)
        z2, p2 = self._proxy_lines(wb, eb)
        d = np.hypot(p1[:, None, 0] - p2[None, :, 0], p1[:, None, 1] - p2[None, :, 1])
        K = K4 * fil_F(z1[:, None, None, None], z1[:, None, None, None] + ea.hs,
                       z2[None, None, :, None], z2[None, None, :, None] + eb.hs, d[None, :, None, :])
        return np.ascontiguousarray(K.reshape(ea.n * p1.shape[0], eb.n * p2.shape[0]))

    # -- plane parts
    def _build_plane(self):
        pm = self.plane
        self.wp_ops = {}
        self.n_plane = 0
        if pm is None:
            return
        nl, nx, ny = len(pm.layers), pm.nx, pm.ny
        self.shape_x, self.shape_y = (nl, nx - 1, ny), (nl, ny - 1, nx)
        self.off_px = self.n_wire
        self.off_py = self.n_wire + nl * (nx - 1) * ny
        self.n_plane = nl * ((nx - 1) * ny + (ny - 1) * nx)
        self.tabs = []
        bound = 0.0
        for a_al, a_tr, n1, n2 in ((pm.ax, pm.ay, nx - 1, ny), (pm.ay, pm.ax, ny - 1, nx)):
            T, b = plane_table(pm.layers, pm.layers, a_al, a_tr, n1, n2)
            self.tabs.append((T[:, :, 0, 0].copy(), circulant_fft(T)))
            bound = max(bound, b)
        self.stated.plane = bound
        wpb = 0.0
        for i, (wm, e) in enumerate(self.edges):
            if e.ax in (0, 1):
                self.wp_ops[i] = wire_plane_op(wm, e, pm)
                wpb = max(wpb, self.wp_ops[i].bound)
        self.stated.wp = wpb

    def _build_R(self):
        parts = [np.ascontiguousarray(e.R).ravel() for _, e in self.edges]
        pm = self.plane
        if pm is not None:
            t = np.array([z1 - z0 for z0, z1 in pm.layers])[:, None, None]
            sg = pm.spec.sigma
            parts.append(np.broadcast_to(pm.ax / (sg * pm.ay * t), self.shape_x).ravel())
            parts.append(np.broadcast_to(pm.ay / (sg * pm.ax * t), self.shape_y).ravel())
        return np.concatenate(parts)

    # -- operator
    def lmul(self, x: np.ndarray, absolute: bool = False) -> np.ndarray:
        """y = L x (inductance operator, H).  absolute=True applies |L|-bounding operators (absolute weights and
        tables) to a non-negative x: the entrywise-absolute product used by the stated bounds and the rounding term."""
        y = np.zeros(self.n, dtype=complex)
        nsig = 2 * self.P + 1
        Pq, Qo, sgn = [], [], []
        for k, (wm, e) in enumerate(self.edges):
            nr = len(wm.edges_r) - 1
            X = x[e.off:e.off + nsig * e.n * nr].reshape(nsig, e.n, nr)
            if absolute:
                if k not in self._Labs:
                    self._Labs[k] = np.abs(self.Lsec[k])
                Ls, W = self._Labs[k], np.abs(wm.W)
            else:
                Ls, W = self.Lsec[k], wm.W
            Y = np.matmul(Ls, X.reshape(nsig, e.n * nr, 1))[:, :, 0]
            y[e.off:e.off + nsig * e.n * nr] = Y.reshape(-1)
            Pq.append(np.einsum("gsa,gaq->sq", X, W))
            Qo.append(np.zeros_like(Pq[-1], dtype=complex))
            sgn.append(1.0 if absolute else e.sgn)
        for i, j, K, sg in self.pairs:
            s = 1.0 if absolute else sg
            Qo[i] += s * (K @ Pq[j].reshape(-1)).reshape(Qo[i].shape)
            Qo[j] += s * (K.T @ Pq[i].reshape(-1)).reshape(Qo[j].shape)
        if self.plane is not None:
            nl = len(self.plane.layers)
            Xp = [x[self.off_px:self.off_py].reshape(self.shape_x), x[self.off_py:self.n].reshape(self.shape_y)]
            Yp = [circulant_apply(self.tabs[d][1], Xp[d]) for d in (0, 1)]
            for k, op in self.wp_ops.items():
                d = self.edges[k][1].ax
                Qo[k] += sgn[k] * op.to_wire(Xp[d])
                Yp[d] = Yp[d] + sgn[k] * op.to_plane(Pq[k])
            y[self.off_px:self.off_py] = Yp[0].reshape(-1)
            y[self.off_py:self.n] = Yp[1].reshape(-1)
            del nl
        for k, (wm, e) in enumerate(self.edges):
            nr = len(wm.edges_r) - 1
            W = np.abs(wm.W) if absolute else wm.W
            y[e.off:e.off + nsig * e.n * nr] += np.einsum("sq,gaq->gsa", Qo[k], W).reshape(-1)
        return y

    # -- incidence
    def incidence(self):
        """Sparse C (n x n_nodes): branch -> (start, end) nodes (+1, -1) for the m = 0 wire modes and plane branches."""
        rows, cols, vals = [], [], []
        for wm, e in self.edges:
            nr = len(wm.edges_r) - 1
            s, a = np.meshgrid(np.arange(e.n), np.arange(nr), indexing="ij")
            idx = (e.off + s * nr + a).ravel()  # sector 0 occupies the first n*nr entries
            rows += [idx, idx]
            cols += [(e.node0 + s).ravel(), (e.node0 + s + 1).ravel()]
            vals += [np.ones(idx.size), -np.ones(idx.size)]
        nn = self.n_wnodes
        if self.plane is not None:
            nl, nx, ny = len(self.plane.layers), self.plane.nx, self.plane.ny
            base = self.n_wnodes
            i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny), indexing="ij")
            na, nb = (base + i * ny + j).ravel(), (base + (i + 1) * ny + j).ravel()
            self.plane_x_nodes = (na, nb)
            jj, ii = np.meshgrid(np.arange(ny - 1), np.arange(nx), indexing="ij")
            ma, mb = (base + ii * ny + jj).ravel(), (base + ii * ny + jj + 1).ravel()
            self.plane_y_nodes = (ma, mb)
            for li in range(nl):
                for off0, (p, q) in ((self.off_px + li * na.size, (na, nb)), (self.off_py + li * ma.size, (ma, mb))):
                    idx = off0 + np.arange(p.size)
                    rows += [idx, idx]
                    cols += [p, q]
                    vals += [np.ones(idx.size), -np.ones(idx.size)]
            nn += nx * ny
        C = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(self.n, nn))
        grounds = [wm.node_base for wm in self.wires] + ([self.n_wnodes] if self.plane is not None else [])
        keep = np.setdiff1d(np.arange(nn), grounds)
        return C, keep, nn


# ---------------------------------------------------------------------------------------------- solve driver
def block_gmres(apply_M: Callable, apply_prec: Callable, Cr, rhs_d: np.ndarray, n: int, tol: float, restart: int = 100,
                maxit: int = 5):
    """GMRES on the saddle system [[M, -C], [C^T, 0]] [x; phi] = [0; d] with a user preconditioner; returns (x, iters)."""
    nk = Cr.shape[1]

    def amul(v):
        x, phi = v[:n], v[n:]
        return np.concatenate([apply_M(x) - Cr @ phi, Cr.T @ x])

    A = spla.LinearOperator((n + nk, n + nk), matvec=amul, dtype=complex)
    Pm = spla.LinearOperator((n + nk, n + nk), matvec=apply_prec, dtype=complex)
    rhs = np.concatenate([np.zeros(n, complex), rhs_d.astype(complex)])
    its = [0]
    sol, _ = spla.gmres(A, rhs, M=Pm, rtol=tol, atol=0.0, restart=restart, maxiter=maxit,
                        callback=lambda _r: its.__setitem__(0, its[0] + 1), callback_type="pr_norm")
    return sol[:n], its[0]


def a_posteriori(apply_M: Callable, Cr, X: np.ndarray, D: np.ndarray, r_min: float):
    """Exact KCL projection of approximate port currents X (n, np) for injections D (nk, np), the stationary
    impedance Z = X^T M X and the rigorous bound |dZ_ij| <= ||rho_i|| ||rho_j|| / r_min, rho = P (M x), P the
    orthogonal projector onto null(C^T): the error e = x - x~ lies in null(C^T), Z - Z~ = -e_i^T M e_j = e_i^T rho_j
    and ||e|| <= ||rho|| / r_min because Re M = R >= r_min on that space.  Returns (Xt, MX, Z, bound matrix)."""
    lu = spla.splu((Cr.T @ Cr).tocsc())

    def cs(v):
        return lu.solve(np.ascontiguousarray(v.real)) + 1j * lu.solve(np.ascontiguousarray(v.imag))

    Xt = np.stack([X[:, j] - Cr @ cs(Cr.T @ X[:, j] - D[:, j]) for j in range(X.shape[1])], 1)
    MX = np.stack([apply_M(Xt[:, j]) for j in range(X.shape[1])], 1)
    rho = np.stack([MX[:, j] - Cr @ cs(Cr.T @ MX[:, j]) for j in range(X.shape[1])], 1)
    nrm = np.linalg.norm(rho, axis=0)
    return Xt, MX, Xt.T @ MX, np.outer(nrm, nrm) / r_min


class Preconditioner:
    """Block preconditioner of the saddle system: inverse of each wire (edge, sector) block and of each plane
    branch's layer block (zero lateral offset), with the nodal Schur complement S = C^T M_b^-1 C (wire m = 0 blocks
    exact, plane branches by their total layer admittance) factorised sparse."""

    def __init__(self, sys_: System, w: float, Cr, keep, nn):
        self.s, self.w, self.Cr = sys_, w, Cr
        nsig = 2 * sys_.P + 1
        self.inv = []
        rows, cols, vals = [], [], []
        for wm, e in sys_.edges:
            nr = len(wm.edges_r) - 1
            N = e.n * nr
            Rm = e.R.reshape(nsig, N)
            Mi = np.empty((sys_.P + 1, N, N), complex)
            for m in range(sys_.P + 1):
                sg = 0 if m == 0 else 2 * m - 1
                Mi[m] = np.linalg.inv(1j * w * e.Lm[m] + np.diag(Rm[sg]))
            self.inv.append(Mi[sys_.sec_m])
            C0 = np.zeros((N, e.n + 1))
            s_, a_ = np.meshgrid(np.arange(e.n), np.arange(nr), indexing="ij")
            C0[(s_ * nr + a_).ravel(), s_.ravel()] = 1.0
            C0[(s_ * nr + a_).ravel(), s_.ravel() + 1] = -1.0
            Sb = C0.T @ (Mi[0] @ C0)
            ii, jj = np.meshgrid(e.node0 + np.arange(e.n + 1), e.node0 + np.arange(e.n + 1), indexing="ij")
            rows.append(ii.ravel())
            cols.append(jj.ravel())
            vals.append(Sb.ravel())
        self.pinv = []
        if sys_.plane is not None:
            pm = sys_.plane
            nl = len(pm.layers)
            for d, (T00, _) in enumerate(sys_.tabs):
                lo, hi = (sys_.off_px, sys_.off_py) if d == 0 else (sys_.off_py, sys_.n)
                Rl = sys_.R[lo:hi].reshape(nl, -1)[:, 0]
                Bi = np.linalg.inv(1j * w * T00 + np.diag(Rl))
                self.pinv.append(Bi)
                ysum = Bi.sum()
                p, q = sys_.plane_x_nodes if d == 0 else sys_.plane_y_nodes
                rows += [p, q, p, q]
                cols += [p, q, q, p]
                vals += [np.full(p.size, ysum), np.full(p.size, ysum), np.full(p.size, -ysum), np.full(p.size, -ysum)]
        S = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(nn, nn)).tocsr()
        self.Slu = spla.splu(S[keep][:, keep].tocsc())
        self.nsig = nsig

    def minv(self, v: np.ndarray) -> np.ndarray:
        s = self.s
        out = np.zeros_like(v)
        for k, (wm, e) in enumerate(s.edges):
            nr = len(wm.edges_r) - 1
            sz = self.nsig * e.n * nr
            blk = v[e.off:e.off + sz].reshape(self.nsig, e.n * nr, 1)
            out[e.off:e.off + sz] = np.matmul(self.inv[k], blk)[:, :, 0].reshape(-1)
        if s.plane is not None:
            nl = len(s.plane.layers)
            for d, Bi in enumerate(self.pinv):
                lo, hi = (s.off_px, s.off_py) if d == 0 else (s.off_py, s.n)
                out[lo:hi] = (Bi @ v[lo:hi].reshape(nl, -1)).reshape(-1)
        return out

    def __call__(self, v: np.ndarray) -> np.ndarray:
        n = self.s.n
        f, g = v[:n], v[n:]
        mf = self.minv(f)
        phi = self.Slu.solve(g - self.Cr.T @ mf)
        return np.concatenate([self.minv(f + self.Cr @ phi), phi])


@dataclass
class SolveOut:
    z: np.ndarray
    solver_tol: float
    parts: dict = field(default_factory=dict)
    iters: list = field(default_factory=list)
    n: int = 0


DENSE_MAX = 2500


def solve_system(sys_: System, port_nodes: list[tuple[int, int]], freqs, tol: float = 1e-11,
                 dense: bool | None = None) -> SolveOut:
    """Impedance matrices Z[f, i, j] = V_i / I_j (other ports open) and the reported forward-error bound."""
    C, keep, nn = sys_.incidence()
    Cr = C[:, keep].tocsc()
    pos = {int(k): i for i, k in enumerate(keep)}
    npt = len(port_nodes)
    D = np.zeros((len(keep), npt))
    for j, (a, b) in enumerate(port_nodes):
        if a in pos:
            D[pos[a], j] += 1.0
        if b in pos:
            D[pos[b], j] -= 1.0
    n, R = sys_.n, sys_.R
    rmin = float(R.min())
    if dense is None:
        dense = sys_.plane is None and n + Cr.shape[1] <= DENSE_MAX
    if dense:
        Ld = np.stack([sys_.lmul(np.eye(n)[:, i]).real for i in range(n)], 1)
    zs, tols, iters, parts = [], [], [], []
    for f in freqs:
        w = 2 * math.pi * f

        def apply_M(v, w=w):
            return R * v + 1j * w * sys_.lmul(v)

        if dense:
            Md = 1j * w * Ld + np.diag(R)
            A = np.zeros((n + Cr.shape[1], n + Cr.shape[1]), complex)
            A[:n, :n] = Md
            A[:n, n:] = -Cr.toarray()
            A[n:, :n] = Cr.T.toarray()
            sol = np.linalg.solve(A, np.concatenate([np.zeros((n, npt)), D]))
            X = sol[:n]
            iters.append(0)
        else:
            pre = Preconditioner(sys_, w, Cr, keep, nn)
            X = np.zeros((n, npt), complex)
            it = 0
            for j in range(npt):
                X[:, j], k = block_gmres(apply_M, pre, Cr, D[:, j], n, tol)
                it += k
            iters.append(it)
        Xt, MX, Z, resid = a_posteriori(apply_M, Cr, X, D, rmin)
        xa = np.abs(Xt)
        Lx = np.stack([sys_.lmul(xa[:, j], absolute=True).real for j in range(npt)], 1)
        e_l = w * (xa.T @ Lx)
        e_r = xa.T @ (R[:, None] * xa)
        rnd = 2.0 * UNIT_ROUNDOFF * n * (e_l + e_r)
        stated = sys_.stated.total * e_l
        kern = np.zeros((npt, npt))
        nsig = 2 * sys_.P + 1
        for k, (wm, e) in enumerate(sys_.edges):
            nr = len(wm.edges_r) - 1
            v = xa[e.off:e.off + nsig * e.n * nr].reshape(nsig, e.n, nr, npt).sum(axis=1)  # (nsig, nr, npt)
            kern += w * np.einsum("gai,gab,gbj->ij", v, sys_.kern_err[k], v)
        stated = stated + kern
        zref = float(np.max(np.abs(np.diag(Z))))
        parts.append(dict(resid=float(resid.max() / zref), round=float(rnd.max() / zref),
                          stated=float(stated.max() / zref)))
        tols.append(parts[-1]["resid"] + parts[-1]["round"] + parts[-1]["stated"])
        zs.append(Z)
    return SolveOut(z=np.array(zs), solver_tol=float(max(tols)), parts=parts, iters=iters, n=n)


def mesh_digest(wires: list[WireMesh], plane: PlaneMesh | None, level: int, freqs_max: float) -> str:
    """sha256 of the mesh actually built (annulus edges, segment geometry, proxy order, plane lattice and layers)."""
    h = hashlib.sha256()
    h.update(f"L{level}:{freqs_max!r}".encode())
    for wm in wires:
        h.update(wm.edges_r.tobytes())
        h.update(f"{wm.P}:{wm.spec.sigma!r}".encode())
        for e in wm.edges:
            h.update(np.concatenate([e.p0, e.p1, [e.hs, e.n]]).astype(np.float64).tobytes())
    if plane is not None:
        h.update(f"{plane.nx}:{plane.ny}:{plane.ax!r}:{plane.ay!r}:{plane.spec.sigma!r}".encode())
        h.update(np.array(plane.layers).tobytes())
    return h.hexdigest()


def solve_case(specs: list[WireSpec], plane: PlaneSpec | None, ports: list[tuple[tuple[int, int], tuple[int, int]]],
               freqs, level: int, P: int | None = None, gmres_tol: float = 1e-11, dense: bool | None = None):
    """One mesh for the call (graded to the skin depth at max(freqs)); ports = ((wire, vertex), (wire, vertex)).
    Returns (SolveOut, meta dict with mesh_params, n_filaments, mesh_hash, timings)."""
    if not 1 <= level <= MAX_REFINEMENT:
        raise ValueError(f"refinement level must be in 1..{MAX_REFINEMENT}")
    t0 = time.perf_counter()
    fmax = float(max(freqs))
    P_sel, eps_proxy = select_P(specs, plane)
    if P is None:
        P = P_sel
    elif P_sel:
        eps_proxy = max(2.0 * proxy_truncation_bound(s.diameter / 2, d, P) for s, d in _coupled_distances(specs, plane))
    wires, base = [], 0
    for s in specs:
        wm = build_wire_mesh(s, level, fmax, P, base)
        wires.append(wm)
        base += wm.n_nodes
    pm = build_plane_mesh(plane, wires, level, fmax) if plane is not None else None
    stated = Stated(proxy=eps_proxy)
    sys_ = System(wires, pm, stated)
    t1 = time.perf_counter()
    pn = [(wires[a[0]].vertex_node[a[1]], wires[b[0]].vertex_node[b[1]]) for a, b in ports]
    out = solve_system(sys_, pn, list(freqs), tol=gmres_tol, dense=dense)
    mp = {}
    for wm in wires:
        e0 = wm.edges[0]
        c = len(wm.edges_r) - 1
        mp.update({f"seg:{wm.spec.name}": min(e.hs for e in wm.edges), f"fil_w:{wm.spec.name}": math.pi * wm.r / c,
                   f"fil_h:{wm.spec.name}": wm.r / c, f"surf:{wm.spec.name}": float(wm.edges_r[-1] - wm.edges_r[-2])})
        del e0
    if pm is not None:
        mp.update({f"{k}:{pm.spec.name}": v for k, v in pm.mp.items()})
    digest = mesh_digest(wires, pm, level, fmax)
    meta = dict(mesh_params=mp, n_filaments=int(sys_.n), mesh_hash=[digest] * len(freqs), solver_tol=out.solver_tol,
                P=P, stated=vars(stated), tol_parts=out.parts, gmres_iters=out.iters, build_s=t1 - t0,
                wall_s=time.perf_counter() - t0)
    return out, meta
