"""Tests of the L2 layout path (moduleforge.solvers.l2_layout).

Closed forms used (cited, implemented here independently of the module under test):
[G]  Grover, Inductance Calculations (1946) ch. 7: Neumann integral of two straight filaments, M = mu0/(4 pi) cos(eps)
     int int ds dt / R  (checked by adaptive double quadrature of the integral itself).
[HL] Hoer & Love, J. Res. NBS 69C (1965) 127: partial inductance of a rectangular bar with uniform current, re-typed below
     (``hoer_love_self``) and cross-checked against the Rosa/Grover (1946) approximation for a long bar.
[RWV] Ramo, Whinnery, Van Duzer: skin depth; DC resistance R = l / (sigma w t).
Scaling (Maxwell): all lengths x s, f / s^2, sigma fixed -> L x s, R / s.
"""
from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import integrate
from shapely.geometry import box

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
)
from moduleforge.solvers import l2, l2_layout as L

MU0 = 4e-7 * math.pi
K4 = MU0 / (4 * math.pi)
SIG_CU, SIG_AL = 5.8e7, 3.77e7


# ------------------------------------------------------------------------------------------------ independent closed forms
def hoer_love_self(blen, w, t):
    """[HL] self partial inductance (H) of a bar l x w x t, current along l: the 64-term corner sum of the Hoer-Love
    function with all four corner differences of a bar with itself."""
    def f(x, y, z):
        r = math.sqrt(x * x + y * y + z * z)
        tot = (x ** 4 + y ** 4 + z ** 4 - 3 * x * x * y * y - 3 * y * y * z * z - 3 * z * z * x * x) * r / 60.0

        def lg(a, b, c):  # a (b^2 c^2 6 - b^4 - c^4) asinh(a / sqrt(b^2 + c^2)) / 24
            rho = math.hypot(b, c)
            return 0.0 if rho == 0 else a * (6 * b * b * c * c - b ** 4 - c ** 4) * math.asinh(a / rho) / 24.0

        def at(a, b, c):  # a b c^3 atan(a b / (c r)) / 6
            return 0.0 if c == 0 or r == 0 else a * b * c ** 3 * math.atan(a * b / (c * r)) / 6.0

        return tot + lg(x, y, z) + lg(y, x, z) + lg(z, x, y) - at(x, y, z) - at(x, z, y) - at(z, y, x)

    dims = (blen, w, t)
    tot = 0.0
    for sel in itertools.product(range(4), repeat=3):
        sign, args = 1.0, []
        for d, k in zip(dims, sel, strict=True):
            # corner differences of two coincident intervals [0, d]: offsets -d, 0, 0, +d with signs (+, -, -, +)
            off, sg = ((d, 1), (0.0, -1), (0.0, -1), (-d, 1))[k]
            args.append(off)
            sign *= sg
        tot += sign * f(*args)
    return K4 * tot / (w * t) ** 2


def rosa_bar(blen, w, t):
    """Grover (1946) / Rosa approximation for a straight rectangular bar: mu0 l / (2 pi) [ln(2l/(w+t)) + 1/2 +
    0.2235 (w+t)/l]."""
    return MU0 * blen / (2 * math.pi) * (math.log(2 * blen / (w + t)) + 0.5 + 0.2235 * (w + t) / blen)


def test_hoer_love_reference_matches_rosa_for_a_long_bar():
    blen, w, t = 0.2, 3e-3, 0.3e-3
    assert hoer_love_self(blen, w, t) == pytest.approx(rosa_bar(blen, w, t), rel=2e-3)


# ------------------------------------------------------------------------------------------------ kernels
def test_inclined_filament_mutual_vs_independent_quadrature():
    """[G] closed form of two skew, non-parallel straight filaments vs adaptive quadrature of the Neumann integral."""
    p0, p1 = np.array([0.0, 0.0, 0.0]), np.array([1.0e-3, 0.2e-3, 0.1e-3])
    q0, q1 = np.array([0.3e-3, 0.5e-3, 0.4e-3]), np.array([1.1e-3, 1.4e-3, -0.3e-3])
    u, v = p1 - p0, q1 - q0

    def integrand(t, s):
        d = (p0 + s * u) - (q0 + t * v)
        return 1.0 / math.sqrt(float(d @ d))

    val, _ = integrate.dblquad(integrand, 0.0, 1.0, 0.0, 1.0, epsabs=1e-12, epsrel=1e-13)
    ref = K4 * float(u @ v) * val
    got = float(L.segment_mutual(p0, p1, q0, q1))
    assert got == pytest.approx(ref, rel=1e-9)
    # symmetric in the two filaments and sign-flips with the direction of one of them
    assert float(L.segment_mutual(q0, q1, p0, p1)) == pytest.approx(got, rel=1e-12)
    assert float(L.segment_mutual(p0, p1, q1, q0)) == pytest.approx(-got, rel=1e-12)


def test_filament_mutual_orthogonal_is_zero_and_parallel_limit_is_continuous():
    z = np.zeros(3)
    assert abs(float(L.segment_mutual(z, np.array([1e-3, 0, 0]), np.array([0, 1e-3, 1e-3]),
                                      np.array([0, 2e-3, 1e-3])))) < 1e-18
    # a tiny angle must give the parallel-filament value (continuity across PARALLEL_SIN)
    a = np.array([2e-3, 0.0, 0.0])
    par = float(L.segment_mutual(z, a, np.array([0.5e-3, 0.3e-3, 0]), np.array([2.5e-3, 0.3e-3, 0])))
    tilt = float(L.segment_mutual(z, a, np.array([0.5e-3, 0.3e-3, 0]), np.array([2.5e-3, 0.3e-3 + 2e-3 * 1e-5, 0])))
    assert tilt == pytest.approx(par, rel=1e-4)


def test_box_potential_vs_tensor_gauss():
    """Potential of a uniform box at an exterior point: closed form [Waldvogel] vs tensor Gauss-Legendre of 1/R."""
    lo, hi = np.array([[0.0, 0.0, 0.0]]), np.array([[1.0e-3, 2.0e-3, 0.3e-3]])
    pt = np.array([0.4e-3, 0.7e-3, 0.8e-3])
    x, w = np.polynomial.legendre.leggauss(24)
    pts = [0.5 * (h - lw) * x + 0.5 * (h + lw) for lw, h in zip(lo[0], hi[0], strict=True)]
    ws = [0.5 * (h - lw) * w for lw, h in zip(lo[0], hi[0], strict=True)]
    X, Y, Z = np.meshgrid(*pts, indexing="ij")
    W = ws[0][:, None, None] * ws[1][None, :, None] * ws[2][None, None, :]
    ref = np.sum(W / np.sqrt((X - pt[0]) ** 2 + (Y - pt[1]) ** 2 + (Z - pt[2]) ** 2))
    got = float(L.box_potential(pt[0], pt[1], pt[2], lo, hi)[0])
    assert got == pytest.approx(ref, rel=1e-9)


def test_rod_self_vs_averaged_filament_mutual_and_bound():
    """rod_self = K4 <F(d)> over two uniform points of a disc, F the full-length parallel filament mutual [G]."""
    ln, rho = 1e-3, 0.1e-3
    rng = np.random.default_rng(3)
    n = 400000
    r1, r2 = rho * np.sqrt(rng.random(n)), rho * np.sqrt(rng.random(n))
    a1, a2 = 2 * math.pi * rng.random(n), 2 * math.pi * rng.random(n)
    d = np.hypot(r1 * np.cos(a1) - r2 * np.cos(a2), r1 * np.sin(a1) - r2 * np.sin(a2))
    F = 2.0 * (ln * np.arcsinh(ln / d) - np.sqrt(ln * ln + d * d) + d)
    mc = K4 * F.mean()
    got = float(L.rod_self(ln, rho))
    assert got == pytest.approx(mc, rel=3e-3)  # Monte-Carlo noise 1 / sqrt(n) of the mean distance term
    assert float(L.rod_self_bound(ln, rho)) < 1e-4 * got


def _disc_rule(u, a, n_s=10, n_th=24):
    """Points / weights of the mean over the disc of radius a normal to u: (1/2pi) int_0^1 ds int dth f(a sqrt(s), th)
    (Gauss in s = r^2/a^2, trapezoid in th; spectrally accurate for smooth f)."""
    e1 = np.cross([0.0, 0.0, 1.0], u)
    e1 = e1 / np.linalg.norm(e1) if np.linalg.norm(e1) > 1e-9 else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(u, e1)
    xs, ws = np.polynomial.legendre.leggauss(n_s)
    xs, ws = 0.5 * (xs + 1), 0.5 * ws
    th = 2 * math.pi * np.arange(n_th) / n_th
    pts = [a * math.sqrt(sv) * (math.cos(t) * e1 + math.sin(t) * e2) for sv in xs for t in th]
    return np.array(pts), np.repeat(ws, n_th) / n_th


@pytest.mark.parametrize("geo", [
    ((0, 0, 0), (1e-3, 0, 0), (0.2e-3, 0.35e-3, 0), (1.3e-3, 0.35e-3, 0.1e-3), 0.06e-3, 0.05e-3),
    ((0, 0, 0), (1e-3, 0.2e-3, 0.3e-3), (0.9e-3, 0.4e-3, 0.5e-3), (0.2e-3, 0.5e-3, 1.0e-3), 0.08e-3, 0.06e-3)])
def test_finite_radius_rod_pair_vs_disc_quadrature(geo):
    """Mutual of two round rods (uniform current over each disc): reference = quadrature over both cross-sections of the
    filament Neumann integral (``segment_mutual``, itself checked against dblquad above).  The centre-line value is off by
    ~1e-3; centre line + ``rod_pair_correction`` is within its stated remainder."""
    p0, p1, q0, q1 = (np.array(v, float) for v in geo[:4])
    a, b = geo[4:]
    X, wx = _disc_rule((p1 - p0) / np.linalg.norm(p1 - p0), a)
    Y, wy = _disc_rule((q1 - q0) / np.linalg.norm(q1 - q0), b)
    ref = np.sum(wx[:, None] * wy[None, :] * L.segment_mutual(p0 + X[:, None], p1 + X[:, None], q0 + Y[None], q1 + Y[None]))
    cl = float(L.segment_mutual(p0, p1, q0, q1))
    corr, rem = L.rod_pair_correction(p0, p1, a, q0, q1, b)
    err = abs(cl + float(corr) - ref)
    assert err <= float(rem)
    assert err < 0.02 * abs(cl - ref)
    assert float(rem) < 2e-3 * abs(ref)


def test_box_gradient_vs_central_differences():
    lo, hi = np.array([[0.0, 0.0, 0.0]]), np.array([[1e-3, 2e-3, 0.3e-3]])
    p, h = np.array([0.4e-3, 2.5e-3, 0.5e-3]), 1e-8
    g = L.box_grad(*p, lo, hi)[0]
    fd = np.array([(L.box_potential(*(p + h * e), lo, hi)[0] - L.box_potential(*(p - h * e), lo, hi)[0]) / (2 * h)
                   for e in np.eye(3)])
    assert np.max(np.abs(g - fd)) <= 1e-7 * np.max(np.abs(fd))


@pytest.mark.parametrize("geo", [((-0.5e-3, -0.5e-3, 0.15e-3), (0.6e-3, -0.2e-3, 0.6e-3), 0.06e-3),
                                 ((-0.8e-3, -0.3e-3, 0.25e-3), (-0.2e-3, -0.4e-3, 0.18e-3), 0.09e-3)])
def test_finite_radius_rod_box_vs_disc_quadrature(geo):
    """Rod (radius a) over a Cu branch box: disc quadrature of the centre-line box integral vs centre line +
    ``rod_box_correction``, within the stated remainder; the uncorrected centre line is outside it."""
    lo, hi = np.array([[-1e-3, -1e-3, -0.1e-3]]), np.array([[0.0, 0.0, 0.0]])
    p0, p1, a = np.array(geo[0]), np.array(geo[1]), geo[2]
    X, wx = _disc_rule((p1 - p0) / np.linalg.norm(p1 - p0), a)
    ref = sum(w * L.line_box_integral(p0 + x, p1 + x, lo, hi)[0][0] for x, w in zip(X, wx, strict=True))
    cl = L.line_box_integral(p0, p1, lo, hi)[0][0]
    corr, rem = L.rod_box_correction(p0, p1, a, lo, hi)
    assert abs(cl + corr[0] - ref) <= rem[0]
    assert rem[0] < abs(cl - ref)


# ------------------------------------------------------------------------------------------------ system builders
def strip_system(nx=20, ny=3, cell=1e-3, thick=0.3e-3, nlay=3):
    """Single copper strip (no wires): ends are shorted columns, port between them.  Returns (system, port, bar dims)."""
    mask = np.ones((nx, ny), bool)
    slab = L.SlabSpec("strip", mask, L.graded_layers(0.0, thick, nlay, 100.0, SIG_CU, False), SIG_CU)
    g = L.Grid(0.0, 0.0, cell, cell, nx, ny, [slab])
    nid = g.node_id[0]
    fs = L.FilamentSet(*(np.zeros((0, 3)),) * 2, np.zeros(0, int), np.zeros(0, int), np.zeros(0), np.zeros(0), np.zeros(0))
    wg = L.WireGridDense(fs, g)
    sys_ = L.LayoutSystem(fs, g, wg, np.zeros((0, 2), int), [nid[0, :], nid[-1, :]], 0)
    sys_.stated_total = g.plane_bound
    return sys_, (int(nid[0, 0]), int(nid[-1, 0])), ((nx - 1) * cell, ny * cell, thick)


def test_straight_trace_100hz_vs_hoer_love_and_dc_resistance():
    """A 3 mm wide, 0.3 mm thick strip between equipotential end columns at 100 Hz (skin depth 6.6 mm >> thickness, so the
    current is uniform): L = Hoer-Love self inductance of the bar spanned by the branches ((nx - 1) cells long), R = l/(sigma w t)."""
    sys_, port, (ln, w, t) = strip_system()
    out = L.solve_system(sys_, [port], [100.0])
    z = out.z[0, 0, 0]
    ref = hoer_love_self(ln, w, t)
    assert z.imag / (2 * math.pi * 100.0) == pytest.approx(ref, rel=2e-3)
    assert z.real == pytest.approx(ln / (SIG_CU * w * t), rel=1e-6)
    assert 0 <= out.solver_tol < 1e-6


def test_wire_filament_bundle_vs_rod_closed_form():
    """A straight 5 mm round Al wire (one filament set, no grid contact) at 100 Hz: the bundle's series L equals the rod
    closed form of the whole wire (uniform current, mu0/(2 pi) [l (ln(2l/r) - 3/4) + 128 r/(45 pi) - r^2/(4l)]) within 1 %
    (the filament bundle approximates the uniform disc; error ~ (r/l)^2)."""
    r, ln = 0.15e-3, 5e-3
    pts = np.array([[0, 0, 2e-3], [ln, 0, 2e-3]])
    fs = L.build_filaments([L.WireIn("w", pts, 2 * r, SIG_AL)], 1)
    Lw, _, Rw, _, _, _ = L.wire_matrices(fs)
    # all filaments in parallel with equal DC current density: I_f ~ conductance-weighted; at 100 Hz R dominates
    gcond = 1.0 / Rw
    x = gcond / gcond.sum()
    ltot = x @ Lw @ x
    ref = MU0 / (2 * math.pi) * (ln * (math.log(2 * ln / r) - 0.75) + 128 * r / (45 * math.pi) - r * r / (4 * ln))
    assert ltot == pytest.approx(ref, rel=1e-2)


def c1_system(refinement, cell_mm, nlay, fmax, scale=1.0):
    """E001's C1 geometry (10 x 5 mm rectangular loop of 0.3 mm Al wire, 1 mm over a 0.3 mm Cu plane of 40 x 35 mm,
    plane top at z = 0) on the layout path's internals; gap port between the two ends of the loop."""
    s = scale * 1e-3
    pts = np.array([(0, 0, 1), (10, 0, 1), (10, 5, 1), (0, 5, 1), (0, 0, 1)], float) * s
    nx, ny = round(40 / cell_mm), round(35 / cell_mm)
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, nlay, fmax, SIG_CU, False), SIG_CU)
    g = L.Grid(-15 * s, -15 * s, 40 * s / nx, 35 * s / ny, nx, ny, [slab])
    fs = L.build_filaments([L.WireIn("loop", pts, 0.3 * s, SIG_AL)], refinement)
    wg = L.WireGridPFFT(fs, g)
    nc = g.n_cell_nodes
    sys_ = L.LayoutSystem(fs, g, wg, np.array([[nc, nc + 1]]), [], 2)
    sys_.set_stated()
    return sys_, (nc, nc + 1)


def l2_c1(level, f):
    w = l2.RoundWire("loop", tuple(tuple(1e-3 * c for c in p) for p in [(0, 0, 1), (10, 0, 1), (10, 5, 1), (0, 5, 1),
                                                                         (0, 0, 1)]), 0.3e-3, SIG_AL)
    pl = l2.Plane("gnd", -15e-3, -15e-3, 25e-3, 20e-3, 0.0, 0.3e-3, SIG_CU)
    r = l2.solve([w], [pl], [l2.Port("p", l2.Terminal("loop", 0), l2.Terminal("loop", 4))], [f], level)
    return r.z[0, 0, 0].imag / (2 * math.pi * f), r.meta["solver_tol"]


def test_c1_layout_internals_vs_l2_solve_same_refinement():
    """E001's C1 at 20 MHz: layout path (refinement 1) vs ``l2.solve`` at refinement 1 within 0.5 %."""
    f = 2e7
    sys_, port = c1_system(1, 0.7, L.LAYERS_BACK[1], f)
    out = L.solve_system(sys_, [port], [f])
    lay = out.z[0, 0, 0].imag / (2 * math.pi * f)
    ref, tol_ref = l2_c1(1, f)
    assert tol_ref < 1e-5
    assert lay == pytest.approx(ref, rel=5e-3)


def test_scaling_double_lengths_quarter_frequency_doubles_L():
    f = 2e7
    s1, p1 = c1_system(0, 1.0, 3, f)
    s2, p2 = c1_system(0, 1.0, 3, f / 4, scale=2.0)
    z1 = L.solve_system(s1, [p1], [f]).z[0, 0, 0]
    z2 = L.solve_system(s2, [p2], [f / 4]).z[0, 0, 0]
    l1, l2_ = z1.imag / (2 * math.pi * f), z2.imag / (2 * math.pi * f / 4)
    assert l2_ == pytest.approx(2.0 * l1, rel=1e-3)
    # the resistance scales the other way: R / 2 (same skin-depth ratio, DC-like wire sections are the same mesh)
    assert z2.real == pytest.approx(0.5 * z1.real, rel=2e-3)


# ------------------------------------------------------------------------------------------------ operator tests
def small_c1(n_wires=1):
    return c1_system(0, 3.0, 2, 2e7)


def test_wire_grid_pfft_vs_dense_kernel_adjoint_and_bound(monkeypatch):
    """The compressed wire<->grid operator vs the dense exact coupling: |y_pfft - y_dense| <= bound (|K||x|) elementwise,
    and (K x, y) = (x, K^T y) to round-off."""
    monkeypatch.setattr(L, "PFFT_NEAR", 8)
    monkeypatch.setattr(L, "PFFT_STENCIL", 4)
    sys_, _ = c1_system(0, 3.0, 2, 2e7)
    wg, g = sys_.wg, sys_.grid
    dense = L.WireGridDense(sys_.fs, g)
    rng = np.random.default_rng(1)
    x = rng.standard_normal(g.n_g)
    y = rng.standard_normal(sys_.nfil)
    a, b = wg.to_wires(x), dense.to_wires(x)
    ba = dense.to_wires(np.abs(x), absolute=True)
    assert np.all(np.abs(a - b) <= (wg.bound + wg.near_bound) * ba + 1e-14 * ba)
    assert np.isfinite(wg.bound)
    assert y @ wg.to_wires(x) == pytest.approx(x @ wg.to_grid(y), rel=1e-12)
    assert np.max(np.abs(wg.to_grid(y) - dense.to_grid(y))) <= (wg.bound + wg.near_bound) * np.max(
        dense.to_grid(np.abs(y), absolute=True)) * 1.0000001 + 1e-30


def test_wire_grid_pfft_production_parameters_vs_dense_within_stated_bound():
    """Production PFFT_NEAR / PFFT_STENCIL / disc-rule nodes on a 0.25 mm grid big enough to have far branches: the
    compressed operator vs the dense exact finite-radius coupling, elementwise within its stated bound (interpolation +
    Gauss + far disc rule) times the absolute coupling, in both directions."""
    s = 1e-3
    nx, ny = 64, 56
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, 2, L.F_MESH, SIG_CU, False), SIG_CU)
    g = L.Grid(-8 * s, -7 * s, 0.25 * s, 0.25 * s, nx, ny, [slab])
    pts = np.array([(0, 0, 0.3), (1.0, 0.3, 0.8), (2.0, 0.5, 0.4)], float) * s
    fs = L.build_filaments([L.WireIn("w", pts, 0.3 * s, SIG_AL)], 0)
    wg = L.WireGridPFFT(fs, g)
    assert wg.near == L.PFFT_NEAR and wg.n_far_branches > 0
    dense = L.WireGridDense(fs, g)
    tol = wg.bound + wg.near_bound + wg.bnd_far
    assert 0 < tol < 1e-4
    rng = np.random.default_rng(5)
    x, y = rng.standard_normal(g.n_g), rng.standard_normal(fs.nfil)
    assert np.all(np.abs(wg.to_wires(x) - dense.to_wires(x)) <= tol * dense.to_wires(np.abs(x), absolute=True) + 1e-30)
    assert np.all(np.abs(wg.to_grid(y) - dense.to_grid(y)) <= tol * dense.to_grid(np.abs(y), absolute=True) + 1e-30)


def dense_saddle_z(sys_, ports, f):
    """Independent dense solve of the full saddle system with the operator columns of the system: returns Z[i, j] =
    d_i^T phi_j (V_i / I_j), not symmetrised."""
    C, keep, _ = sys_.incidence()
    Cr = C[:, keep].toarray()
    n = sys_.n
    Ld = np.stack([sys_.lmul(np.eye(n)[:, i]).real for i in range(n)], 1)
    w = 2 * math.pi * f
    A = np.zeros((n + Cr.shape[1],) * 2, complex)
    A[:n, :n] = 1j * w * Ld + np.diag(sys_.R)
    A[:n, n:] = -Cr
    A[n:, :n] = Cr.T
    pos = {int(k): i for i, k in enumerate(keep)}
    D = np.zeros((len(keep), len(ports)))
    for j, (a, b) in enumerate(ports):
        for sgn, c in ((1, a), (-1, b)):  # a port end is a raw node id or a weighted ``Contact``
            for nd, wt in zip(*((c.nodes, c.weights) if isinstance(c, L.Contact) else ([c], [1.0])), strict=True):
                nd = int(sys_.lab[nd])
                if nd in pos:
                    D[pos[nd], j] += sgn * wt
    sol = np.linalg.solve(A, np.concatenate([np.zeros((n, len(ports))), D]))
    phi = sol[n:]
    return D.T @ phi, Ld


def two_port_system():
    """C1-like system plus a second free wire above the plane: ports (loop ends) and (wire ends)."""
    s = 1e-3
    nx, ny = 20, 18
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, 2, 2e7, SIG_CU, False), SIG_CU)
    g = L.Grid(-15 * s, -15 * s, 40 * s / nx, 35 * s / ny, nx, ny, [slab])
    loop = np.array([(0, 0, 1), (10, 0, 1), (10, 5, 1), (0, 5, 1), (0, 0, 1)], float) * s
    bar = np.array([(2, 8, 1.5), (9, 8, 1.5), (9, 10, 0.8)], float) * s
    fs = L.build_filaments([L.WireIn("loop", loop, 0.3 * s, SIG_AL), L.WireIn("bar", bar, 0.3 * s, SIG_AL)], 0)
    wg = L.WireGridPFFT(fs, g)
    nc = g.n_cell_nodes
    sys_ = L.LayoutSystem(fs, g, wg, np.array([[nc, nc + 1], [nc + 2, nc + 3]]), [], 4)
    sys_.set_stated()
    return sys_, [(nc, nc + 1), (nc + 2, nc + 3)]


def test_reciprocity_two_port_and_solver_agrees_with_dense_saddle():
    sys_, ports = two_port_system()
    f = 2e7
    Zd, _ = dense_saddle_z(sys_, ports, f)
    scale = np.abs(Zd).max()
    assert abs(Zd[0, 1] - Zd[1, 0]) <= 1e-9 * scale  # reciprocity of the assembled operator (not of the solver)
    assert abs(Zd[0, 1]) > 1e-3 * scale  # the ports are genuinely coupled
    out = L.solve_system(sys_, ports, [f], dense=False)
    assert np.max(np.abs(out.z[0] - Zd)) <= out.solver_tol * np.max(np.abs(np.diag(Zd))) + 1e-9 * scale
    assert np.max(np.abs(out.z[0] - out.z[0].T)) <= 1e-12 * scale


# ------------------------------------------------------------------------------------------------ layouts
def tiny_layout(wire_d=0.3e-3):
    """Hand-made half-bridge (1 die per switch): DC+ | PHASE | DC- columns, die on DC+ and PHASE.  Every trace edge, die
    footprint and the backside Cu (substrate -1..25 x -1..15 mm, inset 1 mm) lie on the 2 mm cells of ``coarse`` (origin
    -8 mm): the layout L2 refuses features off its lattice (T0075, founder re-scope I0039)."""
    mm = 1e-3
    st = default_dbc_stack()
    traces = [Trace(DC_PLUS, box(2 * mm, 2 * mm, 8 * mm, 8 * mm)), Trace(PHASE, box(10 * mm, 2 * mm, 16 * mm, 12 * mm)),
              Trace(DC_MINUS, box(18 * mm, 2 * mm, 22 * mm, 12 * mm))]

    def die(cx, cy, sw):
        s = 2 * mm
        hp = 0.35 * s
        pads = {"source": (cx - hp, cy - hp, cx + hp, cy + hp), "gate": (cx + 0.75 * mm, cy - 0.95 * mm, cx + 0.95 * mm, cy - 0.75 * mm)}
        return Die(cx, cy, s, s, sw, pads)

    d_hs, d_ls = die(5 * mm, 5 * mm, "HS"), die(13 * mm, 9 * mm, "LS")
    ztop = st.z_top("top_cu")
    zs = ztop + d_hs.attach_thickness + d_hs.thickness
    wires = []
    for dy in (-0.5, 0.5):
        wires.append(arc_wire((5.5 * mm, 5 * mm + dy * mm), (11.0 * mm, 5 * mm + dy * mm), zs, ztop, 0.8 * mm, wire_d, PHASE))
        wires.append(arc_wire((13.5 * mm, 9 * mm + dy * mm), (19.0 * mm, 9 * mm + dy * mm), zs, ztop, 0.8 * mm, wire_d, DC_MINUS))
    terms = {DC_PLUS: Terminal(DC_PLUS, 3 * mm, 6 * mm, 2 * mm, 2 * mm), DC_MINUS: Terminal(DC_MINUS, 21 * mm, 11 * mm, 2 * mm, 2 * mm),
             PHASE: Terminal(PHASE, 15 * mm, 11 * mm, 2 * mm, 2 * mm)}
    return Layout("tiny", 1, box(-1 * mm, -1 * mm, 25 * mm, 15 * mm), traces, [d_hs, d_ls], wires, terms,
                  box(-8 * mm, -8 * mm, 32 * mm, 22 * mm), st)


@pytest.fixture
def coarse(monkeypatch):
    n = L.MAX_REFINEMENT + 1
    monkeypatch.setattr(L, "CELL", (2e-3,) * n)
    monkeypatch.setattr(L, "LAYERS_TOP", (2,) * n)
    monkeypatch.setattr(L, "LAYERS_BACK", (2,) * n)
    monkeypatch.setattr(L, "LAYERS_BASE", (2,) * n)
    monkeypatch.setattr(L, "WIRE_EDGES", ((0, .6, 1),) * n)  # the coarse wire mesh these tests were written with


def test_reported_solver_tol_bounds_true_error_vs_dense_lu(coarse, monkeypatch):
    """D0004 consequence: reported solver_tol >= true relative Z error against a dense LU.  Oracle: the dense exact
    wire<->grid coupling and the dense saddle solve; subject: the compressed (precorrected FFT) operator and GMRES.  The
    near box is reduced so that the interpolation error is a real, non-zero contribution."""
    full = (L.PFFT_NEAR, L.PFFT_STENCIL)
    monkeypatch.setattr(L, "PFFT_NEAR", 8)
    monkeypatch.setattr(L, "PFFT_STENCIL", 4)
    lay, freqs = tiny_layout(), [5e6, 8e7]
    sys_o, port, _ = L.build_layout_system(lay, max(freqs), 0, coupling="dense")
    assert sys_o.n < 6000
    Zo = np.array([dense_saddle_z(sys_o, [port], f)[0][0, 0] for f in freqs])
    sys_c, port_c, _ = L.build_layout_system(lay, max(freqs), 0, coupling="pfft")
    out = L.solve_system(sys_c, [port_c], freqs, dense=False)
    zc = out.z[:, 0, 0]
    true_err = np.max(np.abs(zc - Zo) / np.abs(Zo))
    assert true_err <= out.solver_tol
    assert np.isfinite(out.solver_tol) and out.solver_tol > 0
    # the same layout with the full near box has a much smaller reported bound
    monkeypatch.setattr(L, "PFFT_NEAR", full[0])
    monkeypatch.setattr(L, "PFFT_STENCIL", full[1])
    sys_f, port_f, _ = L.build_layout_system(lay, max(freqs), 0, coupling="pfft")
    out_f = L.solve_system(sys_f, [port_f], freqs, dense=False)
    assert out_f.solver_tol < 1e-3 and out_f.solver_tol < out.solver_tol  # a smaller near box reports a larger bound
    assert np.max(np.abs(out_f.z[:, 0, 0] - Zo) / np.abs(Zo)) <= out_f.solver_tol


def test_layout_L_non_increasing_with_frequency_and_meta_contract(coarse):
    lay = tiny_layout()
    freqs = [1e5, 1e6, 5e6, 2e7, 8e7]
    r = L.loop_inductance(lay, freqs, refinement=0)
    Lh = np.asarray(r.L_H)
    assert Lh.shape == (5,) and np.all(np.isfinite(Lh)) and np.all(Lh > 0)
    assert np.all(Lh[:-1] >= Lh[1:] * (1 - 1e-9)), Lh
    assert np.all(np.asarray(r.R_ohm) > 0) and np.all(np.diff(r.R_ohm) > 0)
    m = r.meta
    for k in ("tool_version", "source_sha256", "n_unknowns", "mesh_params", "solver_tol", "wall_s", "cpu_s", "gmres_iters"):
        assert k in m, k
    assert "binary_path" not in m and "binary_sha256" not in m
    src = Path(L.__file__).read_bytes(), Path(L.core.__file__).read_bytes()
    h = hashlib.sha256()
    for p, b in zip((Path(L.__file__), Path(L.core.__file__)), src, strict=True):
        h.update(p.name.encode())
        h.update(b)
    assert m["source_sha256"] == h.hexdigest()
    assert m["n_unknowns"] > 0 and 0 <= m["solver_tol"] < 1e-3 and m["wall_s"] > 0 and m["cpu_s"] > 0
    assert len(m["gmres_iters"]) == 5
    with pytest.raises(ValueError):
        L.loop_inductance(lay, [0.0], 0)


def test_generated_two_die_half_bridge_between_1_and_100_nH():
    from moduleforge.generate.halfbridge import generate_layouts
    lay = generate_layouts(1, seed=7, dies_per_switch=2)[0]
    r = L.loop_inductance(lay, [2e7], refinement=0)
    assert 1e-9 < r.L_H[0] < 1e-7
    assert r.meta["solver_tol"] < 1e-3


def test_l_at_a_frequency_does_not_depend_on_the_frequency_list(coarse):
    """One mesh per call graded to max(F_MESH, max(freqs)): L(20 MHz) alone equals L(20 MHz) inside a 3-frequency call."""
    lay = tiny_layout()
    a = L.loop_inductance(lay, [2e7], 0)
    b = L.loop_inductance(lay, [5e6, 2e7, 8e7], 0)
    assert a.meta["mesh_params"]["mesh_graded_to_hz"] == b.meta["mesh_params"]["mesh_graded_to_hz"] == L.F_MESH
    assert abs(a.L_H[0] - b.L_H[1]) <= (a.meta["solver_tol"] + b.meta["solver_tol"]) * abs(b.L_H[1])


def strip_layout(stack=None, y0=2.0, y1=4.0, hs_x=11.0, dcp_x1=12.0, phase_x0=14.0):
    """In-line half-bridge on 2 mm wide strips aligned with the 2 mm cells of the ``coarse`` grid (origin -8 mm):
    DC+ x 0..12 | PHASE 14..26 | DC- 28..40 mm at y 2..4 mm; dies (2 mm, one cell each) on cells 11 (DC+) and 23 (PHASE);
    one wire per switch die -> landing cell 6 mm further (17 on PHASE, 29 on DC-); terminals on cells 1 (DC+) and 39 (DC-);
    substrate -1..41 x -1..7 mm, so the backside Cu (inset 1 mm) is 0..40 x 0..6 mm, on the lattice too."""
    mm = 1e-3
    st = default_dbc_stack() if stack is None else stack
    traces = [Trace(DC_PLUS, box(0, y0 * mm, dcp_x1 * mm, y1 * mm)), Trace(PHASE, box(phase_x0 * mm, y0 * mm, 26 * mm, y1 * mm)),
              Trace(DC_MINUS, box(28 * mm, y0 * mm, 40 * mm, y1 * mm))]

    def die(cx, sw):
        pads = {"source": (cx - 0.5 * mm, 2.5 * mm, cx + 0.5 * mm, 3.5 * mm),
                "gate": (cx + 0.55 * mm, 2.25 * mm, cx + 0.75 * mm, 2.45 * mm)}
        return Die(cx, 3 * mm, 2.0 * mm, 2.0 * mm, sw, pads)

    d_hs, d_ls = die(hs_x * mm, "HS"), die(23 * mm, "LS")
    ztop = st.z_top("top_cu")
    zs = ztop + d_hs.attach_thickness + d_hs.thickness
    wires = [arc_wire((hs_x * mm, 3 * mm), (17 * mm, 3 * mm), zs, ztop, 0.8 * mm, 0.3e-3, PHASE),
             arc_wire((23 * mm, 3 * mm), (29 * mm, 3 * mm), zs, ztop, 0.8 * mm, 0.3e-3, DC_MINUS)]
    terms = {DC_PLUS: Terminal(DC_PLUS, 1 * mm, 3 * mm, 1.5 * mm, 1.5 * mm),
             DC_MINUS: Terminal(DC_MINUS, 39 * mm, 3 * mm, 1.5 * mm, 1.5 * mm),
             PHASE: Terminal(PHASE, 25 * mm, 3 * mm, 1.5 * mm, 1.5 * mm)}
    return Layout("strip", 1, box(-1 * mm, -1 * mm, 41 * mm, 7 * mm), traces, [d_hs, d_ls], wires, terms,
                  box(-8 * mm, -8 * mm, 32 * mm, 22 * mm), st)


def test_layout_mapping_dc_resistance_closed_form(coarse):
    """Independent check of the Layout -> system mapping (net labels, die-short merges, wire-end nodes, port cells on the
    port's net).  At 100 Hz (skin depth 6.6 mm >> every conductor) the loop is a series DC path with a closed form:
    strips carry uniform current between cell centres (5 + 3 + 5 branches of 2 mm, R = l / (sigma w t) [RWV]), the die
    shorts are ideal, each wire is its filaments in parallel (R_f = length_f / (sigma A_f)).  A wrong landing cell, a
    missing die short or a port cell on the wrong net changes R by >= 2 % (one strip branch is 2.7 % of the total)."""
    lay = strip_layout()
    sys_, port, info = L.build_layout_system(lay, L.F_MESH, 0)
    assert info["cell_x"] == pytest.approx(2e-3) and info["cell_y"] == pytest.approx(2e-3)
    st = lay.stack
    z0, z1 = lay.top_cu_z()
    r_strip = 13 / (st.layer("top_cu").sigma * (z1 - z0))  # ax = ay: R per branch = 1 / (sigma t)
    fw = sys_.fs.fil_wire
    r_wires = sum(1.0 / np.sum(1.0 / sys_.Rw[fw == k]) for k in np.unique(fw))
    out = L.solve_system(sys_, [port], [100.0])
    z = out.z[0, 0, 0]
    assert z.real == pytest.approx(r_strip + r_wires, rel=1e-4)
    assert r_strip > 0.05 * (r_strip + r_wires)
    assert z.imag > 0 and out.solver_tol < 1e-3


@pytest.mark.parametrize("ref", range(L.MAX_REFINEMENT + 1))
def test_solver_tol_usable_at_every_refinement(ref):
    """Review T0082: solver_tol must stay a usable bound (< 1e-3) at every refinement.  Two inclined-polyline wires (inter-
    wire coupling) over a 20 x 16 mm plane meshed with the refinement's own cell, layer and filament counts; with cells
    below 0.5 mm part of the plane is beyond the pFFT near box, so the far-field interpolation and disc-rule bounds are
    exercised."""
    s = 1e-3
    cell = L.CELL[ref]
    nx, ny = round(20 * s / cell), round(16 * s / cell)
    nl = L.LAYERS_BACK[ref]
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, nl, L.F_MESH, SIG_CU, False), SIG_CU)
    g = L.Grid(-8 * s, -7 * s, 20 * s / nx, 16 * s / ny, nx, ny, [slab])
    a = np.array([(0, 0, 0.3), (1.5, 0.2, 0.9), (3, 0.4, 0.8), (3.2, 2, 0.6)], float) * s
    b = a + np.array([0.0, 0.0, 0.6 * s])
    fs = L.build_filaments([L.WireIn("a", a, 0.3 * s, SIG_AL), L.WireIn("b", b, 0.3 * s, SIG_AL)], ref)
    wg = L.WireGridPFFT(fs, g)
    nc = g.n_cell_nodes
    sys_ = L.LayoutSystem(fs, g, wg, np.array([[nc, nc + 1], [nc + 2, nc + 3]]), [], 4)
    out = L.solve_system(sys_, [(nc, nc + 1), (nc + 2, nc + 3)], [2e7])
    assert 0 < out.solver_tol < 1e-3, out.parts
    assert out.flags == [0, 0], out.flags
    if L.CELL[ref] < 0.5e-3:  # finer than 0.5 mm part of the plane is beyond the 18-cell near box
        assert wg.n_far_branches > 0 and wg.bound > 0


# ------------------------------------------------------------------------------------------------ T0075 fixes and oracle
def test_die_short_connects_only_its_own_net(coarse):
    """Review T0083: a die short took the cells of ANY net in its footprint.  Here the HS die (DC+ trace x 0..4 mm) is 8 mm
    wide (footprint 0..8 mm, on the 2 mm lattice), so it covers the DC+ cells at 1 and 3 mm, the empty gap cell at 5 mm and
    the PHASE cell at 7 mm (PHASE from 6 mm): the short must merge DC+ cells only."""
    from dataclasses import replace
    lay = strip_layout(hs_x=4.0, dcp_x1=4.0, phase_x0=6.0)
    lay.dies[0] = replace(lay.dies[0], w=8e-3)
    sys_, port, info = L.build_layout_system(lay, L.F_MESH, 0)
    assert info["die_short_nets"][0] == [DC_PLUS], info["die_short_nets"]
    assert info["die_short_nets"][1] == [PHASE]
    with pytest.raises(ValueError, match="net"):  # a die whose net has no trace is an error, not a silent re-anchor
        bad = strip_layout()
        bad.traces = [t for t in bad.traces if t.net != DC_PLUS]
        L.build_layout_system(bad, L.F_MESH, 0)


def test_cell_holding_two_nets_is_an_error(coarse):
    """One unknown per branch and layer: a cell with copper of two nets (gap 0.2 mm inside a 2 mm cell) cannot be carried
    with exact per-net areas, so it is refused instead of being given to one of the nets."""
    with pytest.raises(ValueError, match="nets"):
        L.build_layout_system(strip_layout(hs_x=2.15, dcp_x1=2.2, phase_x0=2.4), L.F_MESH, 0)


@pytest.mark.parametrize("seed,dies", [(7, 2), (11, 4)])
def test_every_net_area_exact_and_every_feature_on_the_lattice_at_every_refinement(seed, dies):
    """Founder decision on attempt 2 / re-scope I0039: the represented area of every net must be exact at every refinement
    (the cell-centre mask lost / gained whole cell rows: DC+ -4.2 % at 0.35 mm), now because every feature is ON the lattice
    (no partial cells).  Represented area = number of cells of the net x cell area; reference = shapely area of each trace
    polygon and of the plane outlines (independent of the rectangle route used by ``cell_fill``).  Seed 7 is interleaved,
    seed 11 u_shaped."""
    from shapely.geometry import Polygon

    from moduleforge.generate.halfbridge import generate_layouts
    lay = generate_layouts(1, seed=seed, dies_per_switch=dies)[0]
    cm = lay.to_conductors()
    exact = {t.net: t.polygon.area for t in lay.traces}
    exact.update({p.name: Polygon(p.outline).area for p in cm.planes})
    for ref in range(L.MAX_REFINEMENT + 1):
        xmin, ymin, ax, ay, nx, ny = L.layout_lattice(cm, ref)
        assert ax == pytest.approx(L.CELL[ref], rel=1e-12) and ay == pytest.approx(L.CELL[ref], rel=1e-12)
        fill = L.cell_fill(cm, xmin, ymin, ax, ay, nx, ny)
        frac, lab, nets = fill["top"]
        for k, net in enumerate(nets):
            got = float(np.sum(frac[lab == k + 1]) * ax * ay)
            assert abs(got - exact[net]) <= 1e-12 * exact[net], (ref, net, got, exact[net])
        for name in ("backside_cu", "baseplate"):
            got = float(fill[name].sum() * ax * ay)
            assert abs(got - exact[name]) <= 1e-12 * exact[name], (ref, name)
            assert set(np.unique(fill[name])) <= {0.0, 1.0}
        assert set(np.unique(frac)) <= {0.0, 1.0} and np.all(lab[frac == 0] == 0) and np.all(lab[frac > 0] > 0)
        for d in cm.shorts:  # die footprints on cell boundaries too
            L.check_on_lattice(d.x - d.w / 2, d.x + d.w / 2, d.y - d.h / 2, d.y + d.h / 2, xmin, ymin, ax, ay, "die")


def test_layout_off_the_lattice_is_refused(coarse):
    """Re-scope I0039 item (3): a trace edge, a plane edge or a die footprint inside a cell raises ValueError (attempt 3's
    fill-fraction cells read L 5-9 % low at non-aligned cells; nothing is approximated now)."""
    from dataclasses import replace
    with pytest.raises(ValueError, match="trace is not on the lattice"):  # 1.4 mm strips inside the 2 mm cell rows
        L.build_layout_system(strip_layout(y0=2.4, y1=3.8), L.F_MESH, 0)
    with pytest.raises(ValueError, match="trace is not on the lattice"):  # a trace narrower than one cell (review T0084)
        L.build_layout_system(strip_layout(y0=3.3, y1=3.9), L.F_MESH, 0)
    lay = strip_layout()
    lay.dies[0] = replace(lay.dies[0], w=1.6e-3)  # footprint 10.2..11.8 mm
    with pytest.raises(ValueError, match="die 0 footprint is not on the lattice"):
        L.build_layout_system(lay, L.F_MESH, 0)
    lay = strip_layout()
    lay.outline = box(-1e-3, -0.5e-3, 41e-3, 7e-3)  # backside Cu from y = 0.5 mm
    with pytest.raises(ValueError, match="backside_cu outline is not on the lattice"):
        L.build_layout_system(lay, L.F_MESH, 0)
    lay = strip_layout()
    lay.baseplate_outline = box(-8e-3, -8e-3, 32e-3, 23e-3)  # y extent 31 mm: not a whole number of 2 mm cells
    with pytest.raises(ValueError, match="whole number"):
        L.build_layout_system(lay, L.F_MESH, 0)
    with pytest.raises(ValueError, match="empty"):  # _nearest_cell on an empty mask (review T0084) is an error, not argmin
        L._nearest_cell(np.zeros((3, 3), bool), np.arange(3.0), np.arange(3.0), 0.0, 0.0)


def test_rect_cover_exact():
    """rect_cover: overlap areas of a rectangle with a lattice, by hand."""
    A = L.rect_cover([(0.5, 0.25, 2.0, 1.0)], np.array([0.0, 1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0]))
    assert np.allclose(A, [[0.375, 0.0], [0.75, 0.0], [0.0, 0.0]], rtol=0, atol=1e-15)


def test_gmres_iteration_cap_is_restart_times_cycles_and_restarted_gmres_converges(monkeypatch):
    """Re-scope I0039 item (4): the 0.125 mm solve stopped at the cap of 100 x 5 iterations with solver_tol 1.2e-3.  The cap
    is GMRES_RESTART x GMRES_MAXIT: with a restart of 4 and 2 cycles GMRES stops early (flag > 0, at most 8 iterations,
    a much larger bound), and with the same restart and enough cycles it converges through many restarts to the bound of
    the unrestarted solve."""
    s = 1e-3
    nx, ny = 20, 16
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, 3, L.F_MESH, SIG_CU, False), SIG_CU)
    g = L.Grid(-8 * s, -7 * s, s, s, nx, ny, [slab])
    a = np.array([(0, 0, 0.3), (1.5, 0.2, 0.9), (3, 0.4, 0.8), (3.2, 2, 0.6)], float) * s
    fs = L.build_filaments([L.WireIn("a", a, 0.3 * s, SIG_AL)], 0)
    nc = g.n_cell_nodes
    sys_ = L.LayoutSystem(fs, g, L.WireGridPFFT(fs, g), np.array([[nc, nc + 1]]), [], 2)
    sys_.set_stated()
    assert L.GMRES_RESTART * L.GMRES_MAXIT >= 2000
    full = L.solve_system(sys_, [(nc, nc + 1)], [2e7], dense=False)
    assert full.flags == [0] and full.solver_tol < 1e-3
    monkeypatch.setattr(L, "GMRES_RESTART", 4)
    monkeypatch.setattr(L, "GMRES_MAXIT", 2)
    capped = L.solve_system(sys_, [(nc, nc + 1)], [2e7], dense=False)
    assert capped.flags[0] > 0 and capped.iters[0] <= 8 and capped.solver_tol > 10 * full.solver_tol
    monkeypatch.setattr(L, "GMRES_MAXIT", 500)
    restarted = L.solve_system(sys_, [(nc, nc + 1)], [2e7], dense=False)
    assert restarted.flags == [0] and restarted.iters[0] > 8
    assert restarted.solver_tol < 1e-3 and restarted.solver_tol == pytest.approx(full.solver_tol, rel=1e-2)
    assert restarted.z[0, 0, 0] == pytest.approx(full.z[0, 0, 0], rel=full.solver_tol + restarted.solver_tol)


def test_wire_near_grid_edge_without_far_branches_does_not_raise():
    """Review T0084: WireGridPFFT raised for any wire node within ~4 cells of the grid edge.  On a grid small enough that
    every branch is in the near box of every wire the near correction replaces every pair: it must build and equal the
    dense exact operator; where far branches exist the interpolation bound would not hold and it must still raise."""
    s = 1e-3
    nx, ny = 10, 8
    slab = L.SlabSpec("gnd", np.ones((nx, ny), bool), L.graded_layers(-0.3 * s, 0.0, 2, L.F_MESH, SIG_CU, False), SIG_CU)
    g = L.Grid(0.0, 0.0, 1.0 * s, 1.0 * s, nx, ny, [slab])
    pts = np.array([(0.5, 0.5, 0.4), (2.0, 1.5, 0.7), (4.0, 3.0, 0.5)]) * s  # first node 0.5 cell from the grid edge
    fs = L.build_filaments([L.WireIn("a", pts, 0.1 * s, SIG_AL)], 0)
    wg = L.WireGridPFFT(fs, g)
    assert wg.stencil_shifted and wg.n_far_branches == 0
    ref = L.WireGridDense(fs, g)
    x = np.random.default_rng(0).normal(size=g.n_g)
    assert np.allclose(wg.to_wires(x), ref.to_wires(x), rtol=1e-9, atol=1e-9 * np.abs(ref.to_wires(x)).max())
    big = L.Grid(0.0, 0.0, 1.0 * s, 1.0 * s, 60, 50, [L.SlabSpec("gnd", np.ones((60, 50), bool), slab.layers, SIG_CU)])
    with pytest.raises(ValueError, match="edge"):
        L.WireGridPFFT(fs, big, near=10)


def _quad_segment_mutual(p0, p1, q0, q1):
    """Independent Neumann integral: 1-D adaptive quadrature of the analytic inner integral (asinh form)."""
    u, v = p1 - p0, q1 - q0
    l1, l2 = np.linalg.norm(u), np.linalg.norm(v)
    vh = v / l2

    def inner(s):
        d = p0 + s * u - q0
        ts = d @ vh
        rho = np.linalg.norm(d - ts * vh)
        if rho < 1e-30:
            return math.log(abs(l2 - ts) / abs(ts))
        return math.asinh((l2 - ts) / rho) - math.asinh(-ts / rho)

    val, _ = integrate.quad(inner, 0.0, 1.0, epsabs=0.0, epsrel=1e-13, limit=500)
    return K4 * (u @ v) / (l1 * l2) * val * l1


@pytest.mark.parametrize("geo", ["side", "skew", "touch", "gap", "anti"])
def test_segment_mutual_near_parallel_band_vs_quadrature(geo):
    """Review T0083: the closed form cancels like 1e-16 / sin^2 just above sin = 1e-6 (3.5e-5 error) and the old parallel
    substitution was O(sin) below.  Every sin from 1e-11 to 2e-3 (band edges 1e-12 / 1e-3 included) must agree with the
    independent quadrature within 1e-8, 10x inside the stated ``NEAR_PARALLEL_REL`` (touching pairs: the dperp floor of the
    parallel form, 7e-10, is the limit)."""
    ln = 2e-3
    for sin in (0.0, 1e-13, 1e-11, 1e-9, 1e-7, 1e-6, 3e-6, 1e-5, 1e-4, 5e-4, 9.9e-4, 1.1e-3, 2e-3):
        th = math.asin(sin)
        n = np.array([0.0, math.sin(0.7), math.cos(0.7)])
        v = math.cos(th) * np.array([1.0, 0, 0]) + math.sin(th) * n
        p0, p1 = np.zeros(3), ln * np.array([1.0, 0, 0])
        if geo == "side":
            q0 = np.array([0.3e-3, 0.2e-3, 0.0])
            q1 = q0 + ln * v
        elif geo == "skew":
            q0 = np.array([-0.5e-3, 0.05e-3, 0.1e-3])
            q1 = q0 + 1.3 * ln * v
        elif geo == "touch":  # consecutive segments of a polyline with a tiny bend
            q0 = p1.copy()
            q1 = q0 + ln * v
        elif geo == "gap":
            q0 = np.array([ln + 0.1e-3, 0.0, 0.0])
            q1 = q0 + ln * v
        else:  # antiparallel
            q1 = np.array([0.3e-3, 0.2e-3, 0.0])
            q0 = q1 - ln * v
            if sin == 0.0:
                q0 = q1 - ln * np.array([1.0, 0, 0])
        got = float(L.segment_mutual(p0, p1, q0, q1))
        ref = _quad_segment_mutual(p0, p1, q0, q1)
        assert abs(got - ref) <= 1e-8 * abs(ref), (geo, sin, got, ref)
    assert L.NEAR_PARALLEL_REL >= 10 * 1e-8


def test_near_parallel_pairs_are_counted_in_solver_tol():
    """A bend of 5e-4 rad between two segments of one wire lies in the band: wire_matrices adds NEAR_PARALLEL_REL |M| to the
    stated finite-radius remainder Ex (counted in solver_tol)."""
    s = 1e-3
    pts = np.array([(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (4.0, 2.0 * math.tan(5e-4), 1.0)]) * s
    fs = L.build_filaments([L.WireIn("a", pts, 0.1 * s, SIG_AL)], 0)
    _, _, _, _, ex, _ = L.wire_matrices(fs)
    assert ex.max() > 0.5 * L.NEAR_PARALLEL_REL * 1e-10 * 2  # |M| of the 2 mm segments ~ 1e-9 H


def test_solver_tol_is_also_reported_relative_to_L(coarse):
    """Item (4): solver_tol is relative to max|Z_ii|; meta carries it relative to L = Im Z / omega, which is larger by
    |Z| / Im Z (equal to |Z| / (omega L), large where R is comparable to omega L)."""
    lay = tiny_layout()
    r = L.loop_inductance(lay, [1e4, 2e7], 0)
    tl = r.meta["solver_tol_rel_L"]
    z = np.asarray(r.R_ohm) + 1j * 2 * np.pi * np.array([1e4, 2e7]) * np.asarray(r.L_H)
    parts = r.meta["tol_parts"]
    for k in range(2):
        assert tl[k] == pytest.approx(sum(parts[k].values()) * abs(z[k]) / z[k].imag, rel=1e-9)
    amp = [tl[k] / sum(parts[k].values()) for k in range(2)]  # |Z| / Im Z
    assert amp[0] > 3 * amp[1] and amp[0] > 1.5 and 1.0 <= amp[1] < 1.05, amp
    assert r.meta["solver_tol_rel_L_max"] == max(tl)


def _hl_mutual_collinear(blen, w, t, off):
    """[HL] mutual partial inductance (H) of two identical bars l x w x t on one axis, the second shifted by ``off`` along l
    (corner differences of the intervals [0, l] and [off, off + l])."""
    if off == 0:
        return hoer_love_self(blen, w, t)

    def f(x, y, z):
        r = math.sqrt(x * x + y * y + z * z)
        tot = (x ** 4 + y ** 4 + z ** 4 - 3 * x * x * y * y - 3 * y * y * z * z - 3 * z * z * x * x) * r / 60.0

        def lg(a, b, c):
            rho = math.hypot(b, c)
            return 0.0 if rho == 0 else a * (6 * b * b * c * c - b ** 4 - c ** 4) * math.asinh(a / rho) / 24.0

        def at(a, b, c):
            return 0.0 if c == 0 or r == 0 else a * b * c ** 3 * math.atan(a * b / (c * r)) / 6.0

        return tot + lg(x, y, z) + lg(y, x, z) + lg(z, x, y) - at(x, y, z) - at(x, z, y) - at(z, y, x)

    tot = 0.0
    for sel in itertools.product(range(4), repeat=3):
        sign, args = 1.0, []
        dx = ((off + blen, 1), (off, -1), (off, -1), (off - blen, 1))[sel[0]]
        args.append(dx[0])
        sign *= dx[1]
        for d, k in zip((w, t), sel[1:], strict=True):
            o, sg = ((d, 1), (0.0, -1), (0.0, -1), (-d, 1))[k]
            args.append(o)
            sign *= sg
        tot += sign * f(*args)
    return K4 * tot / (w * t) ** 2


def test_layout_loop_inductance_vs_independent_partial_inductance_sum(coarse):
    """Item (3): layout-level L against an independent oracle.  The strip layout carries one series current path: 13 strip
    branches (2 x 2 mm cross-section x 0.3 mm: bars on one axis, mutuals by the Hoer-Love closed form), and two bond wires.
    Planes are made non-conducting and the frequency is 2 kHz (skin depth 1.5 mm >> 0.3 mm), so the loop is the plain sum of
    the partial inductances of the series elements.  Wire <-> wire: Neumann integral of the centre lines (independent
    quadrature) + the round-rod self term (Grover: l (ln(2l/r) - 3/4)); wire <-> strip: the strip cross-section by a 4 x 3
    Gauss rule of filaments.  The wire feet are lifted like the model's landing clamp.  A wrong port, landing or die-short
    cell moves a strip branch (about 8 % of L each) in or out: the 1.5 % tolerance would catch it."""
    mm = 1e-3
    st0 = default_dbc_stack()
    from dataclasses import replace

    from moduleforge.geometry import LayerStack
    st = LayerStack(tuple(replace(la, sigma=1e-3) if la.name in ("backside_cu", "baseplate") else la for la in st0.layers),
                    kind=st0.kind)
    lay = strip_layout(stack=st)
    f = 2e3
    r = L.loop_inductance(lay, [f], 0)
    z0, z1 = lay.top_cu_z()
    t_cu, w_cell, l_cell = z1 - z0, 2 * mm, 2 * mm
    # strip branches: cell centres 1..11 (DC+), 17..23 (PHASE), 29..39 (DC-); bar k spans [c_k, c_k + 2 mm]
    starts = [x * mm for x in (1, 3, 5, 7, 9, 17, 19, 21, 29, 31, 33, 35, 37)]
    tot = 0.0
    for a in starts:
        for b in starts:
            tot += _hl_mutual_collinear(l_cell, w_cell, t_cu, abs(a - b))
    # wires
    d = lay.wires[0].diameter
    floor = z1 + L.LANDING_GAP * d
    wpts = []
    for w in lay.wires[:2]:
        p = np.array(w.points, float)
        p[:, 2] = np.maximum(p[:, 2], floor)
        wpts.append(p)
    gy = np.polynomial.legendre.leggauss(4)
    gz = np.polynomial.legendre.leggauss(3)
    segs = [(p[i], p[i + 1]) for p in wpts for i in range(len(p) - 1)]
    for i, (a0, a1) in enumerate(segs):
        for j, (b0, b1) in enumerate(segs):
            if i == j:
                tot += MU0 / (2 * math.pi) * np.linalg.norm(a1 - a0) * (math.log(2 * np.linalg.norm(a1 - a0) / (d / 2)) - 0.75)
            else:
                tot += _quad_segment_mutual(a0, a1, b0, b1)
    for (a0, a1) in segs:  # wire <-> strip bars (counted twice: M_ws + M_sw)
        for s0 in starts:
            m = 0.0
            for yy, wy in zip(*gy, strict=True):
                for zz, wz in zip(*gz, strict=True):
                    q0 = np.array([s0, 3 * mm + 0.5 * yy * w_cell, z0 + 0.5 * (zz + 1) * t_cu])
                    m += 0.5 * wy * 0.5 * wz * _quad_segment_mutual(a0, a1, q0, q0 + np.array([l_cell, 0, 0]))
            tot += 2 * m
    got = float(r.L_H[0])
    assert got == pytest.approx(tot, rel=1.5e-2), (got, tot)
    assert r.meta["solver_tol_rel_L"][0] < 1e-2


def test_half_spectrum_circulant_matches_core_and_dense_toeplitz():
    """``circulant_half`` / ``circulant_apply_half`` (real half spectrum, one real matmul) equal ``l2_core``'s full complex
    version for real and complex input, transposed products are the transpose, and both equal a dense block-Toeplitz product."""
    rng = np.random.default_rng(3)
    na, nb, n1, n2 = 3, 2, 5, 4
    T = rng.normal(size=(na, nb, n1, n2))
    X = rng.normal(size=(nb, n1, n2)) + 1j * rng.normal(size=(nb, n1, n2))
    th_core, th = L.core.circulant_fft(T), L.circulant_half(T)
    assert th.shape[0] == 2 * n1 * (n2 + 1) and th.nbytes < 0.7 * th_core.nbytes
    y_core = L.core.circulant_apply(th_core, X)
    for x in (X, X.real):
        y = L.circulant_apply_half(th, x)
        assert np.allclose(y, L.core.circulant_apply(th_core, x), rtol=1e-12, atol=1e-12 * np.abs(y_core).max())
    # dense reference: y[a, i, j] = sum_b sum_{k, l} T[a, b, |i - k|, |j - l|] x[b, k, l]
    ii = np.arange(n1)
    jj = np.arange(n2)
    D = T[:, :, np.abs(ii[:, None] - ii[None, :])][:, :, :, :, :]  # (na, nb, n1, n1, n2)
    dense = np.zeros((na, n1, n2), complex)
    for a in range(na):
        for b in range(nb):
            for i in range(n1):
                for k in range(n1):
                    dense[a, i] += T[a, b, abs(i - k)][np.abs(jj[:, None] - jj[None, :])] @ X[b, k]
    assert np.allclose(y_core, dense) and D.shape[0] == na
    # transposed: (na, nb) table applied to an (na, ...) field gives the (nb, ...) field of the transposed block matrix
    Z = rng.normal(size=(na, n1, n2))
    yt = L.circulant_apply_half(th, Z, transposed=True)
    tt = L.circulant_half(np.ascontiguousarray(T.transpose(1, 0, 2, 3)))
    assert np.allclose(yt, L.circulant_apply_half(tt, Z), rtol=1e-12, atol=1e-12 * np.abs(yt).max())


def test_layer_pair_tables_dedup_matches_direct_plane_table():
    """The geometry-keyed deduplication (mirror symmetry, equal thickness pairs) must reproduce the table and the summed bound
    of the direct evaluation of every pair."""
    mm = 1e-3
    layers = L.graded_layers(0.0, 0.6 * mm, 4, L.F_MESH, SIG_CU, True)  # symmetric: 4 distinct pairs share values
    layers = layers + [(0.6 * mm, 0.9 * mm)]  # contiguous, one asymmetric layer on top
    n1, n2 = 6, 5
    T, bound = L.layer_pair_tables(layers, 0.5 * mm, 0.4 * mm, n1, n2, group=2)
    ref, b_ref = L.core.plane_table(layers, layers, 0.5 * mm, 0.4 * mm, n1, n2)
    assert np.allclose(T, ref, rtol=1e-12, atol=0.0)
    assert bound == pytest.approx(sum(L.core.plane_table([layers[a]], [layers[b]], 0.5 * mm, 0.4 * mm, n1, n2)[1]
                                      for a in range(5) for b in range(a, 5)), rel=1e-12)
    assert b_ref > 0


@pytest.mark.parametrize("n1,n2", [(14, 11), (6, 5), (30, 3)])
def test_pair_table_equals_core_plane_table_and_bound(n1, n2):
    """``pair_table`` (single g evaluation per axial position, chunked) reproduces ``core.plane_table`` entries and the stated
    bound for thin, thick, equal and separated layer pairs; ``FAR_CHUNK_ELEMS`` forced tiny exercises the chunk loop."""
    mm = 1e-3
    cases = [((0.0, 0.003 * mm), (0.0, 0.003 * mm)), ((0.0, 0.01 * mm), (0.2 * mm, 0.5 * mm)),
             ((0.0, 0.3 * mm), (0.3 * mm, 0.6 * mm)), ((0.0, 0.3 * mm), (1.0 * mm, 4.0 * mm)),
             ((-3 * mm, -1 * mm), (0.0, 0.3 * mm))]
    old = L.FAR_CHUNK_ELEMS
    L.FAR_CHUNK_ELEMS = 2000.0
    try:
        for z1, z2 in cases:
            T, b = L.pair_table(z1, z2, 0.7 * mm, 0.5 * mm, n1, n2)
            ref, b_ref = L.core.plane_table([z1], [z2], 0.7 * mm, 0.5 * mm, n1, n2)
            assert b == pytest.approx(b_ref, rel=1e-12)
            assert np.allclose(T, ref[0, 0], rtol=1e-8, atol=1e-8 * np.abs(ref).max()), (z1, z2)
    finally:
        L.FAR_CHUNK_ELEMS = old


def test_wire_foot_between_cell_centres_gives_a_smooth_L(coarse):
    """A wire foot is a point contact: snapped to the nearest cell centre it moves the injection point by up to half a cell
    (L stepped by +-5 % when the layout was shifted by a fraction of a 1 mm cell).  With the bilinear contact, moving the foot
    along the strip by half a cell changes L half as much as moving it by a whole cell."""
    from moduleforge.geometry import BondWire
    lay = strip_layout()
    mm = 1e-3
    w0 = lay.wires[0]
    vals = []
    for xe in (17.0, 17.5, 18.0):
        p = np.array(w0.points, float)
        p[:, 0] = 11 * mm + np.linspace(0.0, 1.0, len(p)) * (xe * mm - 11 * mm)
        lay.wires[0] = BondWire(p, w0.diameter, w0.loop_height, w0.net)
        vals.append(float(L.loop_inductance(lay, [2e7], 0).L_H[0]))
    d = vals[2] - vals[0]
    assert abs(d) > 1e-11
    assert abs(vals[1] - 0.5 * (vals[0] + vals[2])) < 0.05 * abs(d), vals


def test_contact_weights_are_bilinear_and_sum_to_one(coarse):
    lay = strip_layout()
    mm = 1e-3
    lay.terminals[DC_PLUS] = Terminal(DC_PLUS, 2.0 * mm, 3 * mm, 1.5 * mm, 1.5 * mm)  # between cell centres 1 and 3 mm
    sys_, port, info = L.build_layout_system(lay, L.F_MESH, 0)
    pos = port[0]
    assert isinstance(pos, L.Contact) and pos.nodes.size == 2 and pos.weights.sum() == pytest.approx(1.0)
    assert np.allclose(sorted(pos.weights), [0.5, 0.5])


def test_slab_surface_impedance_limits_and_layered_convergence():
    """k_star (T0075) is chosen from the 1-D internal impedance of the top-Cu thickness layers.  Exact slab: DC limit
    1/(sigma t) + j omega mu0 t / 3 (uniform current, H linear across the slab) and thick limit (1 + j)/(sigma delta) [RWV];
    the layered 1-D PEEC is exact at low frequency for any layering and converges to the exact slab as the layers shrink."""
    t, f_lo, f_hi = 0.3e-3, 10.0, 2e7
    z = L.slab_surface_impedance(t, f_lo, SIG_CU)
    assert z.real == pytest.approx(1 / (SIG_CU * t), rel=1e-9)
    assert z.imag == pytest.approx(2 * math.pi * f_lo * MU0 * t / 3, rel=1e-6)
    delta = 1 / math.sqrt(math.pi * 1e9 * MU0 * SIG_CU)
    zt = L.slab_surface_impedance(t, 1e9, SIG_CU)  # t / delta = 143: coth = 1
    assert zt == pytest.approx((1 + 1j) / (SIG_CU * delta), rel=1e-12)
    lay = [3e-6, 50e-6, 247e-6]
    assert L.layered_surface_impedance(lay, f_lo, SIG_CU) == pytest.approx(z, rel=1e-6)
    ze = L.slab_surface_impedance(t, f_hi, SIG_CU)
    errs = [abs(L.layered_surface_impedance(np.full(n, t / n), f_hi, SIG_CU) / ze - 1) for n in (25, 50, 100, 200)]
    assert errs[-1] < 2e-3 and all(b < 0.3 * a for a, b in itertools.pairwise(errs)), errs  # O(h^2): / 4 per halving
    # the former refinement 0's 4-layer 3.3 / 146.7 um top-Cu layering (review T0083) misses the 20 MHz internal impedance by
    # > 100 %; the layering now held at every level (founder re-scope I0039) is within 2 % of the exact slab on both faces
    th0 = [b - a for a, b in L.graded_layers(0.0, t, 4, L.F_MESH, SIG_CU, True)]
    assert abs(L.layered_surface_impedance(th0, f_hi, SIG_CU) / ze - 1) > 1.0
    for n in L.LAYERS_TOP:
        th = [b - a for a, b in L.graded_layers(0.0, t, n, L.F_MESH, SIG_CU, True)]
        assert max(abs(L.layered_surface_impedance(o, f_hi, SIG_CU) / ze - 1) for o in (th, th[::-1])) < 0.02, n


def test_corner_lattice_potential_gradient_and_line_integral_equal_box_by_box():
    """The near field evaluates the closed-form corner functions once per lattice corner (``BoxLattice``); every box potential,
    box gradient and segment line integral must equal the box-by-box closed forms (``box_potential`` / ``box_grad`` /
    ``line_box_integral`` without the lattice) of the same boxes, for both branch directions and a slab gap in z."""
    mm = 1e-3
    nx, ny = 9, 7
    top = L.SlabSpec("t", np.ones((nx, ny), bool), L.graded_layers(0.0, 0.3 * mm, 4, L.F_MESH, SIG_CU, True), SIG_CU)
    m = np.ones((nx, ny), bool)
    m[2:4, 1:3] = False
    bot = L.SlabSpec("b", m, L.graded_layers(-1.0 * mm, -0.7 * mm, 3, L.F_MESH, SIG_CU, True), SIG_CU)
    g = L.Grid(-1.0 * mm, 0.5 * mm, 0.7 * mm, 0.6 * mm, nx, ny, [top, bot])
    pts = np.array([[1.1, 2.3, 0.9], [2.0, 1.0, 0.45], [4.4, 3.9, -0.3]]) * mm
    for lat, lo, hi in ((g.lat[0], g.bx_lo, g.bx_hi), (g.lat[1], g.by_lo, g.by_hi)):
        sub = np.arange(0, lat.ix0.size, 3)
        ls = lat.sub(sub)
        ref = np.array([L.box_potential(*p, lo[sub], hi[sub]) for p in pts])
        got = L.lattice_potential(pts, ls, chunk_elems=200.0).T
        assert np.allclose(got, ref, rtol=1e-11, atol=1e-12 * np.abs(ref).max())
        for p in pts:
            gr = L.box_grad(*p, lo[sub], hi[sub])
            assert np.allclose(L.lattice_grad(p, ls), gr, rtol=1e-10, atol=1e-11 * np.abs(gr).max())
        a, b = pts[0], pts[1]
        I0, b0, _ = L.line_box_integral(a, b, lo[sub], hi[sub])
        I1, b1, _ = L.line_box_integral(a, b, lo[sub], hi[sub], lat=ls)
        assert b1 == b0 and np.allclose(I1, I0, rtol=1e-11, atol=1e-12 * np.abs(I0).max())
