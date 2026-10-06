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
        a, b = int(sys_.lab[a]), int(sys_.lab[b])
        if a in pos:
            D[pos[a], j] += 1
        if b in pos:
            D[pos[b], j] -= 1
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
    """Hand-made 24 x 14 mm half-bridge (1 die per switch): DC+ | PHASE | DC- columns, die on DC+ and PHASE."""
    mm = 1e-3
    st = default_dbc_stack()
    traces = [Trace(DC_PLUS, box(1 * mm, 1 * mm, 9 * mm, 8 * mm)), Trace(PHASE, box(11 * mm, 1 * mm, 17 * mm, 13 * mm)),
              Trace(DC_MINUS, box(19 * mm, 1 * mm, 23 * mm, 13 * mm))]

    def die(cx, cy, sw):
        s = 3 * mm
        hp = 0.35 * s
        pads = {"source": (cx - hp, cy - hp, cx + hp, cy + hp), "gate": (cx + 0.9 * mm, cy - 1.4 * mm, cx + 1.4 * mm, cy - 0.9 * mm)}
        return Die(cx, cy, s, s, sw, pads)

    d_hs, d_ls = die(5 * mm, 4.5 * mm, "HS"), die(14 * mm, 9 * mm, "LS")
    ztop = st.z_top("top_cu")
    zs = ztop + d_hs.attach_thickness + d_hs.thickness
    wires = []
    for dy in (-0.5, 0.5):
        wires.append(arc_wire((5.5 * mm, 4.5 * mm + dy * mm), (11.8 * mm, 4.5 * mm + dy * mm), zs, ztop, 0.8 * mm, wire_d, PHASE))
        wires.append(arc_wire((14.5 * mm, 9 * mm + dy * mm), (19.8 * mm, 9 * mm + dy * mm), zs, ztop, 0.8 * mm, wire_d, DC_MINUS))
    terms = {DC_PLUS: Terminal(DC_PLUS, 3 * mm, 6 * mm, 3 * mm, 3 * mm), DC_MINUS: Terminal(DC_MINUS, 21 * mm, 11 * mm, 3 * mm, 3 * mm),
             PHASE: Terminal(PHASE, 14 * mm, 12 * mm, 3 * mm, 2 * mm)}
    return Layout("tiny", 1, box(0, 0, 24 * mm, 14 * mm), traces, [d_hs, d_ls], wires, terms,
                  box(-8 * mm, -8 * mm, 32 * mm, 22 * mm), st)


@pytest.fixture
def coarse(monkeypatch):
    monkeypatch.setattr(L, "CELL", (2e-3,) * 5)
    monkeypatch.setattr(L, "LAYERS_TOP", (2,) * 5)
    monkeypatch.setattr(L, "LAYERS_BACK", (2,) * 5)
    monkeypatch.setattr(L, "LAYERS_BASE", (2,) * 5)


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


def strip_layout():
    """In-line half-bridge on 2 mm wide strips aligned with the 2 mm cells of the ``coarse`` grid (origin -8 mm):
    DC+ x 0..12 | PHASE 14..26 | DC- 28..40 mm at y 2..4 mm; dies (1.6 mm) on cells 11 (DC+) and 23 (PHASE); one wire per
    switch die -> landing cell 6 mm further (17 on PHASE, 29 on DC-); terminals on cells 1 (DC+) and 39 (DC-)."""
    mm = 1e-3
    st = default_dbc_stack()
    traces = [Trace(DC_PLUS, box(0, 2 * mm, 12 * mm, 4 * mm)), Trace(PHASE, box(14 * mm, 2 * mm, 26 * mm, 4 * mm)),
              Trace(DC_MINUS, box(28 * mm, 2 * mm, 40 * mm, 4 * mm))]

    def die(cx, sw):
        pads = {"source": (cx - 0.5 * mm, 2.5 * mm, cx + 0.5 * mm, 3.5 * mm),
                "gate": (cx + 0.55 * mm, 2.25 * mm, cx + 0.75 * mm, 2.45 * mm)}
        return Die(cx, 3 * mm, 1.6 * mm, 1.6 * mm, sw, pads)

    d_hs, d_ls = die(11 * mm, "HS"), die(23 * mm, "LS")
    ztop = st.z_top("top_cu")
    zs = ztop + d_hs.attach_thickness + d_hs.thickness
    wires = [arc_wire((11 * mm, 3 * mm), (17 * mm, 3 * mm), zs, ztop, 0.8 * mm, 0.3e-3, PHASE),
             arc_wire((23 * mm, 3 * mm), (29 * mm, 3 * mm), zs, ztop, 0.8 * mm, 0.3e-3, DC_MINUS)]
    terms = {DC_PLUS: Terminal(DC_PLUS, 1 * mm, 3 * mm, 1.5 * mm, 1.5 * mm),
             DC_MINUS: Terminal(DC_MINUS, 39 * mm, 3 * mm, 1.5 * mm, 1.5 * mm),
             PHASE: Terminal(PHASE, 25 * mm, 3 * mm, 1.5 * mm, 1.5 * mm)}
    return Layout("strip", 1, box(-1 * mm, 0, 41 * mm, 6 * mm), traces, [d_hs, d_ls], wires, terms,
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
    """Review T0082: solver_tol must stay a usable bound (< 1e-3) at refinements 0-4.  Two inclined-polyline wires (inter-
    wire coupling) over a 20 x 16 mm plane meshed with the refinement's own cell, layer and filament counts; at refinements
    3-4 part of the plane is beyond the pFFT near box, so the far-field interpolation and disc-rule bounds are exercised."""
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
    if ref >= 3:
        assert wg.n_far_branches > 0 and wg.bound > 0
