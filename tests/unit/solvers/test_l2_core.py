"""Tests of the L2 core (moduleforge.solvers.l2_core) and public API (l2).

Closed forms used (cited, not copied from the implementation):
[G] Grover, Inductance Calculations (1946) ch. 7: filament mutual int int dz dz' / R = sum of g(u, d) terms;
[HL] Hoer & Love (1965): uniform-current box mutual; checked here against tensor Gauss of the filament formula;
[RWV]/[MW] straight round wire at DC (uniform current): L = mu0/(2 pi) [l (ln(2l/r) - 3/4) + <d> - <d^2>/(4 l)] with the
mean distance <d> = 128 r / (45 pi) and <d^2> = r^2 of a uniform disc (Maxwell/Weaver), from the series of [G] ch. 7.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from scipy import integrate

from moduleforge.solvers import l2, l2_core as core

MU0 = 4e-7 * math.pi
SIG_AL, SIG_CU = 3.77e7, 5.8e7


@pytest.fixture
def tiny(monkeypatch):
    """Level 1 with tiny counts so plane problems are a few hundred unknowns."""
    monkeypatch.setitem(core.COUNTS, 1, 3)
    monkeypatch.setitem(core.SEGMENTS, 1, 4)
    monkeypatch.setitem(core.LAYERS, 1, 2)
    monkeypatch.setitem(core.COUNTS, 2, 4)
    monkeypatch.setitem(core.SEGMENTS, 2, 5)
    monkeypatch.setitem(core.LAYERS, 2, 3)


def wire(name, pts_mm, d_mm=0.3, sig=SIG_AL):
    return l2.RoundWire(name, tuple(tuple(1e-3 * c for c in p) for p in pts_mm), 1e-3 * d_mm, sig)


def port(name, w, a=0, b=-1, n=None):
    return l2.Port(name, l2.Terminal(w.name, a), l2.Terminal(w.name, len(w.points) - 1 if b < 0 else b))


def staple(name, y, span=8.0, hgt=1.5):
    return wire(name, [(0, y, 0), (0, y, hgt), (span, y, hgt), (span, y, 0)])


def loop_case(h=0.5, a=2.0, b=1.0, margin=1.0, t=0.1):
    lp = wire("loop", [(0, 0, h), (a, 0, h), (a, b, h), (0, b, h), (0, 0, h)])
    pl = l2.Plane("gnd", -margin * 1e-3, -margin * 1e-3, (a + margin) * 1e-3, (b + margin) * 1e-3, 0.0, t * 1e-3,
                  SIG_CU)
    return lp, pl


# ------------------------------------------------------------------------------------------------ kernel entries
def test_fil_F_vs_independent_double_integral():
    """[G] closed form vs scipy dblquad of 1/R for two parallel filaments."""
    a1, a2, b1, b2, d = 0.0, 1.0, 1.7, 2.5, 0.3
    ref, _ = integrate.dblquad(lambda y, x: 1.0 / math.sqrt((x - y) ** 2 + d * d), a1, a2, b1, b2,
                               epsabs=1e-13, epsrel=1e-13)
    assert core.fil_F(a1, a2, b1, b2, d) == pytest.approx(ref, rel=1e-10)


def _box_gauss(lo1, hi1, lo2, hi2, n=16):
    """Independent mutual of two parallel x-directed boxes: tensor Gauss over both (y, z) cross-sections of the
    filament formula (exact along x), divided by the cross-section areas."""
    y1, wy1 = core.gq(n, lo1[1], hi1[1])
    z1, wz1 = core.gq(n, lo1[2], hi1[2])
    y2, wy2 = core.gq(n, lo2[1], hi2[1])
    z2, wz2 = core.gq(n, lo2[2], hi2[2])
    tot = 0.0
    for ya, wa in zip(y1, wy1, strict=True):
        for za, wza in zip(z1, wz1, strict=True):
            d = np.hypot(y2[:, None] - ya, z2[None, :] - za)
            f = core.fil_F(lo1[0], hi1[0], lo2[0], hi2[0], d)
            tot += wa * wza * np.sum(f * np.outer(wy2, wz2))
    area = (hi1[1] - lo1[1]) * (hi1[2] - lo1[2]) * (hi2[1] - lo2[1]) * (hi2[2] - lo2[2])
    return core.K4 * tot / area


def test_hoer_love_box_vs_tensor_gauss():
    lo1, hi1 = np.array([[0.0, 0.0, 0.0]]), np.array([[1e-3, 0.4e-3, 0.1e-3]])
    lo2, hi2 = np.array([[1.5e-3, 1.2e-3, 0.05e-3]]), np.array([[2.5e-3, 1.6e-3, 0.15e-3]])
    ref = _box_gauss(lo1[0], hi1[0], lo2[0], hi2[0])
    assert core.hl_box(lo1, hi1, lo2, hi2, 0)[0] == pytest.approx(ref, rel=1e-9)


_THICK = ([(0.3e-3, 0.4e-3), (0.0, 0.3e-3)], 0.5e-3, 0.3e-3)
# R3 (review T0080): the 1-7 um graded surface layers of real plane meshes (C1-like), where the float64 Hoer-Love corner
# sum cancels like (cell / thickness)^4; the entries must still match the independent quadrature to 1e-9.
_THIN = ([(6e-6, 7e-6), (4e-6, 6e-6), (1e-6, 4e-6), (0.0, 1e-6)], 0.35e-3, 0.28e-3)


@pytest.mark.parametrize("stack", [_THICK, _THIN], ids=["0.1-0.3mm", "1-7um"])
@pytest.mark.parametrize("di,dj", [(1, 2), (2, 3), (6, 1), (3, 7), (9, 9)])
def test_plane_table_entries_vs_independent_quadrature(di, dj, stack):
    """Near (Hoer-Love) and far (Gauss) table entries vs a tensor Gauss of the filament formula (<= 1e-9)."""
    lay, ax, ay = stack
    T, bound = core.plane_table(lay, lay, ax, ay, 12, 12)
    assert bound < 1e-9
    for la, lb in itertools.combinations_with_replacement(range(len(lay)), 2):
        lo1, hi1 = [0.0, 0.0, lay[la][0]], [ax, ay, lay[la][1]]
        lo2, hi2 = [di * ax, dj * ay, lay[lb][0]], [di * ax + ax, dj * ay + ay, lay[lb][1]]
        ref = _box_gauss(lo1, hi1, lo2, hi2)
        assert T[la, lb, di, dj] == pytest.approx(ref, rel=1e-9)


@pytest.mark.parametrize("k,a,b,m", [(1, 0, 1, 0), (1, 0, 1, 2), (0, 0, 1, 1), (2, 1, 1, 0), (2, 0, 0, 2)])
def test_coax_table_entries_vs_independent_quadrature(k, a, b, m):
    """F[k, a, b, m] = int_a int_b rho rho' int cos(m th) F_k(d) dth vs a tensor Gauss of the filament formula."""
    r, s = 0.15e-3, 0.4e-3
    edges = np.array([0.0, 0.4 * r, r])
    F = core.coax_tables(edges, s, 4, 3)
    ann = [(edges[0], edges[1]), (edges[1], edges[2])]
    n = 48
    rho1, w1 = core.gq(n, *ann[a])
    rho2, w2 = core.gq(n, *ann[b])
    th, wth = core.gq(n, 0.0, 2 * math.pi)
    d = np.sqrt(np.maximum(rho1[:, None, None] ** 2 + rho2[None, :, None] ** 2
                           - 2 * rho1[:, None, None] * rho2[None, :, None] * np.cos(th)[None, None, :], 1e-300))
    f = core.fil_F(0.0, s, k * s, (k + 1) * s, d) * np.cos(m * th)[None, None, :]
    ref = np.einsum("ijt,i,j,t,i,j->", f, w1, w2, wth, rho1, rho2)
    assert F[k, a, b, m] == pytest.approx(ref, rel=1e-8)


# ------------------------------------------------------------------------------------------------ convergence
def test_coax_quadrature_order_convergence():
    edges = np.array([0.0, 0.5, 0.8, 1.0]) * 0.15e-3
    base, g, rel = core.coax_tables_scaled(edges, 0.2e-3, 3, 4)
    fine, _ = core._coax_tables(edges, 0.2e-3, 3, 4, 20, 512, 140, 120)
    # stated: every entry of the second-difference table is accurate to 4 rel max_k|gamma_k| of its own (a, b, m)
    assert np.all(np.abs(base - fine).max(axis=0) <= 4 * rel * g)
    assert np.max(rel) < 1e-8
    coarse, _ = core._coax_tables(edges, 0.2e-3, 3, 4, 5, 64, 12, 20)
    assert np.max(np.abs(coarse - fine)) > 10 * np.max(np.abs(base - fine))  # the order matters: it converges


def test_plane_and_wire_plane_quadrature_convergence(monkeypatch, tiny):
    lay = [(0.3e-3, 0.4e-3), (0.0, 0.3e-3)]
    ref, _ = core.plane_table(lay, lay, 0.5e-3, 0.3e-3, 10, 10)
    monkeypatch.setattr(core, "QUAD_TOL", 1e-6)
    lo, b_lo = core.plane_table(lay, lay, 0.5e-3, 0.3e-3, 10, 10)
    monkeypatch.setattr(core, "QUAD_TOL", 1e-14)
    assert np.max(np.abs(lo - ref)) <= b_lo * np.max(np.abs(ref))
    assert np.max(np.abs(lo - ref)) > 1e-14 * np.max(np.abs(ref))  # the looser rule really is looser
    # wire to plane
    spec = core.WireSpec("w", np.array([[0, 0, 0.5e-3], [2e-3, 0, 0.5e-3]]), 0.3e-3, SIG_AL)
    pl = core.PlaneSpec("p", -1e-3, -1e-3, 3e-3, 1e-3, 0.0, 0.1e-3, SIG_CU)
    wm = core.build_wire_mesh(spec, 1, 1e7, 3, 0)
    pm = core.build_plane_mesh(pl, [wm], 1, 1e7)
    op_ref = core.wire_plane_op(wm, wm.edges[0], pm)
    monkeypatch.setattr(core, "QUAD_TOL", 1e-6)
    op_lo = core.wire_plane_op(wm, wm.edges[0], pm)
    x = np.random.default_rng(1).standard_normal((len(pm.layers), pm.nx - 1, pm.ny))
    a, b = op_ref.to_wire(x), op_lo.to_wire(x)
    assert np.max(np.abs(a - b)) <= op_lo.bound * np.max(np.abs(a)) * 10


def test_proxy_order_convergence_and_stated_bound(tiny):
    """Z at P = 3, 5, 7 against P = 9: the differences shrink and stay inside the reported solver_tol (stated bounds)."""
    lp, pl = loop_case()
    zs, tols = {}, {}
    for P in (3, 5, 7, 9):
        out, meta = core.solve_case([core.WireSpec("loop", np.asarray(lp.points), lp.diameter, lp.sigma)],
                                    core.PlaneSpec("gnd", pl.x_min, pl.y_min, pl.x_max, pl.y_max, 0.0, pl.thickness,
                                                   pl.sigma), [((0, 0), (0, 4))], [2e7], 1, P=P)
        zs[P], tols[P] = out.z[0, 0, 0], meta["solver_tol"]
    err = {P: abs(zs[P] - zs[9]) for P in (3, 5, 7)}
    assert err[3] > err[5] > err[7]
    for P in (3, 5, 7):
        assert err[P] <= tols[P] * abs(zs[9])


def test_harmonics_above_proxy_order_within_stated_bound(tiny):
    """Current basis with M = 9 harmonics, far couplings (plane) at proxy order P = 3, 5, 7: harmonics m > P get zero
    far weight, and that truncation stays inside the reported solver_tol (the stated tail q^(P+1) / (1 - q))."""
    lp, pl = loop_case()
    zs, tols = {}, {}
    for P in (3, 5, 7, 9):
        out, meta = core.solve_case([core.WireSpec("loop", np.asarray(lp.points), lp.diameter, lp.sigma)],
                                    core.PlaneSpec("gnd", pl.x_min, pl.y_min, pl.x_max, pl.y_max, 0.0, pl.thickness,
                                                   pl.sigma), [((0, 0), (0, 4))], [2e7], 1, P=P, harm=9)
        assert meta["harmonics"] == 9 and meta["P"] == P
        zs[P], tols[P] = out.z[0, 0, 0], meta["solver_tol"]
    for P in (3, 5, 7):
        assert 0 < abs(zs[P] - zs[9]) <= tols[P] * abs(zs[9])


@pytest.mark.parametrize("len_a,len_b,off,rev_a,rev_b", [(10, 10, 0.0, False, False), (10, 10, 3.3, True, False),
                                                         (10, 10, -2.0, True, True), (10, 7.5, 2.0, False, True)])
def test_far_pair_toeplitz_fft_equals_dense_kernel(len_a, len_b, off, rev_a, rev_b):
    """FarPair (one block per axial offset, FFT along the edge) reproduces the dense proxy-filament matrix of [G] ch. 7
    (System._far) for K x and K^T x, for either flow direction and an axial offset that is not a multiple of the
    segment; unequal segment lengths fall back to the dense matrix."""
    def edge(name, x0, ln, y, rev, base):
        pts = np.array([[x0, y, 0.0], [x0 + ln, y, 0.0]])[::-1 if rev else 1] * 1e-3
        wm = core.build_wire_mesh(core.WireSpec(name, pts, 0.3e-3, SIG_CU), 1, 1e6, 5, base)
        return wm, wm.edges[0]

    wa, ea = edge("a", off, len_a, 0.0, rev_a, 0)
    wb, eb = edge("b", 0.0, len_b, 1.5, rev_b, 100)
    fp = core.FarPair(wa, ea, wb, eb)
    assert fp.toeplitz == (len_a == len_b)
    K = core.System._far(wa, ea, wb, eb)
    assert np.all(K > 0)  # Neumann integrals of 1/R: |K| = K (used by the absolute products of the bounds)
    rng = np.random.default_rng(3)
    xb = rng.standard_normal((eb.n, K.shape[1] // eb.n)) + 1j * rng.standard_normal((eb.n, K.shape[1] // eb.n))
    xa = rng.standard_normal((ea.n, K.shape[0] // ea.n))
    y_ref, z_ref = K @ xb.reshape(-1), K.T @ xa.reshape(-1)
    assert np.abs(fp.apply(xb).reshape(-1) - y_ref).max() <= 1e-13 * np.abs(y_ref).max()
    assert np.abs(fp.apply_t(xa).reshape(-1) - z_ref).max() <= 1e-13 * np.abs(z_ref).max()
    assert not np.iscomplexobj(fp.apply_t(xa))


# ------------------------------------------------------------------------------------------------ operators
def test_wire_plane_operator_vs_dense_kernel_and_adjoint(tiny):
    """Compressed (axially Toeplitz FFT) wire-to-plane operator equals the dense kernel built independently from the
    four-term filament formula, and its transpose is its adjoint."""
    spec = core.WireSpec("w", np.array([[0, 0, 0.5e-3], [2e-3, 0, 0.5e-3]]), 0.3e-3, SIG_AL)
    pl = core.PlaneSpec("p", -1e-3, -1e-3, 3e-3, 1e-3, 0.0, 0.1e-3, SIG_CU)
    wm = core.build_wire_mesh(spec, 1, 1e7, 3, 0)
    pm = core.build_plane_mesh(pl, [wm], 1, 1e7)
    e = wm.edges[0]
    op = core.wire_plane_op(wm, e, pm)
    nl, n1, n2 = len(pm.layers), pm.nx - 1, pm.ny
    rng = np.random.default_rng(3)
    X = rng.standard_normal((nl, n1, n2)) + 1j * rng.standard_normal((nl, n1, n2))
    w = rng.standard_normal((e.n, wm.pts.shape[0]))
    got = op.to_wire(X)
    yq, wy = core.gq(24, 0.0, pm.ay)
    ref = np.zeros((e.n, wm.pts.shape[0]), complex)
    for s in range(e.n):
        a1 = e.p0[0] + s * e.hs
        for q in range(wm.pts.shape[0]):
            for li, (z0, z1) in enumerate(pm.layers):
                zq, wz = core.gq(10, z0, z1)
                for j in range(n2):
                    dyy = wm.pts[q, 0] - (pm.spec.y_min + j * pm.ay + yq)
                    dz = wm.pts[q, 1] + e.p0[2] - zq
                    d = np.hypot(dyy[:, None], dz[None, :])
                    alpha = pm.spec.x_min + pm.ax * (0.5 + np.arange(n1))
                    f = core.fil_F(a1, a1 + e.hs, alpha[:, None, None], alpha[:, None, None] + pm.ax, d[None])
                    kern = core.K4 * np.einsum("iyz,y,z->i", f, wy / pm.ay, wz / (z1 - z0))
                    ref[s, q] += kern @ X[li, :, j]
    assert np.max(np.abs(got - ref)) <= 1e-9 * np.max(np.abs(ref))
    lhs = np.sum(w * op.to_wire(X.real))
    rhs = np.sum(op.to_plane(w) * X.real)
    assert lhs == pytest.approx(rhs, rel=1e-12)


def test_operator_symmetry_with_plane(tiny):
    lp, pl = loop_case()
    spec = core.WireSpec("loop", np.asarray(lp.points), lp.diameter, lp.sigma)
    plane = core.PlaneSpec("gnd", pl.x_min, pl.y_min, pl.x_max, pl.y_max, 0.0, pl.thickness, pl.sigma)
    P, eps = core.select_P([spec], plane)
    wm = core.build_wire_mesh(spec, 1, 2e7, P, 0)
    sysm = core.System([wm], core.build_plane_mesh(plane, [wm], 1, 2e7), core.Stated(proxy=eps))
    rng = np.random.default_rng(0)
    x, y = rng.standard_normal(sysm.n), rng.standard_normal(sysm.n)
    assert (x @ sysm.lmul(y)).real == pytest.approx((y @ sysm.lmul(x)).real, rel=1e-10)


# ------------------------------------------------------------------------------------------------ solve and bounds
def test_a_posteriori_bound_exceeds_true_error(tiny):
    """Loose GMRES vs dense LU on a small plane case: |Z_gmres - Z_dense| <= the reported residual bound."""
    lp, pl = loop_case()
    spec = [core.WireSpec("loop", np.asarray(lp.points), lp.diameter, lp.sigma)]
    plane = core.PlaneSpec("gnd", pl.x_min, pl.y_min, pl.x_max, pl.y_max, 0.0, pl.thickness, pl.sigma)
    pts = [((0, 0), (0, 4))]
    dense, _ = core.solve_case(spec, plane, pts, [2e7], 1, dense=True)
    for tol in (1e-1, 1e-3):
        loose, meta = core.solve_case(spec, plane, pts, [2e7], 1, gmres_tol=tol, dense=False)
        zref = abs(dense.z[0, 0, 0])
        true_err = abs(loose.z[0, 0, 0] - dense.z[0, 0, 0])
        bound = meta["tol_parts"][0]["resid"] * zref
        assert true_err <= bound + 1e-14 * zref + meta["solver_tol"] * zref
        assert bound < 1.0 * zref  # not vacuous
    assert true_err < 1e-3 * zref
    assert dense.parts[0]["resid"] < 1e-12 and dense.parts[0]["round"] < 1e-9


def test_reciprocity_two_port_wires(tiny):
    w1, w2 = staple("w1", 0.0), staple("w2", 1.5)
    res = l2.solve([w1, w2], [], [port("p1", w1), port("p2", w2)], [1e6, 2e7], 1)
    z = res.z
    assert z.shape == (2, 2, 2)
    for k in range(2):
        assert abs(z[k, 0, 1] - z[k, 1, 0]) <= 1e-9 * abs(z[k, 0, 1])
    # parallel conductors with ports pointing the same way: Im Z12 > 0 (contract port convention)
    assert np.all(z[:, 0, 1].imag > 0)


def test_mesh_params_double_with_lengths(tiny):
    s = 2.0
    w, ws = staple("w", 0.0), staple("w", 0.0)
    ws = l2.RoundWire("w", tuple(tuple(s * c for c in p) for p in w.points), s * w.diameter, w.sigma)
    a = l2.solve([w], [], [port("p", w)], [8e7], 1)
    b = l2.solve([ws], [], [port("p", ws)], [8e7 / s**2], 1)
    assert a.meta["n_filaments"] == b.meta["n_filaments"]
    assert set(a.meta["mesh_params"]) == set(b.meta["mesh_params"])
    for k, v in a.meta["mesh_params"].items():
        assert b.meta["mesh_params"][k] == pytest.approx(s * v, rel=1e-9), k
    assert b.z[0, 0, 0].imag / (2 * math.pi * 8e7 / s**2) == pytest.approx(
        s * a.z[0, 0, 0].imag / (2 * math.pi * 8e7), rel=1e-9)


def test_plane_mesh_scales_exactly(tiny):
    lp, pl = loop_case()
    s = 2.0
    lp2 = l2.RoundWire("loop", tuple(tuple(s * c for c in p) for p in lp.points), s * lp.diameter, lp.sigma)
    pl2 = l2.Plane("gnd", s * pl.x_min, s * pl.y_min, s * pl.x_max, s * pl.y_max, 0.0, s * pl.thickness, pl.sigma)
    a = l2.solve([lp], [pl], [port("p", lp)], [2e7], 1)
    b = l2.solve([lp2], [pl2], [port("p", lp2)], [2e7 / s**2], 1)
    assert a.meta["n_filaments"] == b.meta["n_filaments"]
    for k, v in a.meta["mesh_params"].items():
        assert b.meta["mesh_params"][k] == pytest.approx(s * v, rel=1e-9), k
    assert {"plane_x:gnd", "plane_y:gnd", "plane_layer:gnd", "seg:loop", "fil_w:loop", "fil_h:loop",
            "surf:loop"} <= set(a.meta["mesh_params"])


def test_meta_contract_and_levels():
    w = wire("w", [(0, 0, 0), (10, 0, 0)])
    res = [l2.solve([w], [], [port("p", w)], [1e2, 5e6, 8e7], k) for k in (1, 2, 3)]
    nf = [r.meta["n_filaments"] for r in res]
    assert nf == sorted(set(nf))
    for r in res:
        m = r.meta
        assert len(m["mesh_hash"]) == 3 and len(set(m["mesh_hash"])) == 1
        assert m["tool"] and m["version"] and m["wall_s"] >= 0
        assert m["solver_tol"] < 1e-9
    assert len({r.meta["mesh_hash"][0] for r in res}) == 3
    assert l2.MAX_REFINEMENT >= 5


def test_L_non_increasing_with_frequency():
    w = wire("w", [(0, 0, 0), (10, 0, 0)])
    f = np.logspace(2, 8, 9)
    res = l2.solve([w], [], [port("p", w)], list(f), 2)
    L = res.z[:, 0, 0].imag / (2 * np.pi * f)
    assert np.all(np.diff(L) <= 1e-12 * L[0])
    assert L[-1] < L[0]


def test_B1_dc_closed_form():
    """B1 (Al wire, d = 0.3 mm, l = 10 mm) at 100 Hz vs the uniform-current closed form (docstring), <= 1e-4."""
    w = wire("w", [(0, 0, 0), (10, 0, 0)])
    res = l2.solve([w], [], [port("p", w)], [100.0], 3)
    r, ell = 0.15e-3, 10e-3
    ref = MU0 / (2 * math.pi) * (ell * (math.log(2 * ell / r) - 0.75) + 128 * r / (45 * math.pi) - r * r / (4 * ell))
    L = res.z[0, 0, 0].imag / (2 * math.pi * 100.0)
    assert L == pytest.approx(ref, rel=1e-4)
    R = res.z[0, 0, 0].real
    assert R == pytest.approx(ell / (SIG_AL * math.pi * r * r), rel=1e-6)  # DC resistance


def test_unsupported_scope_raises():
    """Bars and ties are implemented since T0071; what is still out of scope must raise, not silently mis-solve."""
    w = wire("w", [(0, 0, 0), (10, 0, 0)])
    bar = l2.Bar("b", (0, 0, 0), (1e-2, 0, 0), 1e-3, 1e-3, SIG_CU)
    with pytest.raises(NotImplementedError):  # bars mixed with round wires
        l2.solve([bar, w], [], [port("p", w)], [1e6], 1)
    inclined = l2.Bar("i", (0, 0, 0), (1e-2, 1e-2, 0), 1e-3, 1e-3, SIG_CU)
    with pytest.raises(NotImplementedError):  # inclined bar
        l2.solve([inclined], [], [], [1e6], 1)


_PI2 = "1.5707963267948966192313216916397514420985846996875529104874722961"


def _dec_atan(t):
    """arctan of a non-negative Decimal: reciprocal for t > 1, three halvings, Maclaurin series (60-digit context)."""
    from decimal import Decimal
    big = t > 1
    if big:
        t = 1 / t
    for _ in range(3):
        t = t / (1 + (1 + t * t).sqrt())
    s, p, t2 = Decimal(0), t, t * t
    for j in range(70):
        s += (-1) ** j * p / (2 * j + 1)
        p *= t2
    return Decimal(_PI2) - 8 * s if big else 8 * s


def _dec_hl_f(x, y, z):
    """Independent 70-digit evaluation of the Hoer-Love function [HL eq. 14] with Python decimals (no numpy, no l2_dd)."""
    from decimal import Decimal
    x, y, z = (abs(Decimal(float(v))) for v in (x, y, z))
    x2, y2, z2 = x * x, y * y, z * z
    r = (x2 + y2 + z2).sqrt()
    out = (x2 * x2 + y2 * y2 + z2 * z2 - 3 * (x2 * y2 + y2 * z2 + z2 * x2)) * r / 60

    def logt(a, b2, c2):
        if b2 + c2 == 0 or a == 0:
            return Decimal(0)
        return (6 * b2 * c2 - b2 * b2 - c2 * c2) * a * ((a + r) / (b2 + c2).sqrt()).ln() / 24

    def tant(a, b, c, c2):
        if c == 0 or a == 0 or b == 0:
            return Decimal(0)
        return a * b * c * c2 * _dec_atan(a * b / (c * r)) / 6

    out += logt(x, y2, z2) + logt(y, x2, z2) + logt(z, x2, y2)
    return out - tant(x, y, z, z2) - tant(x, z, y, y2) - tant(z, y, x, x2)


def _dec_box(lo1, hi1, lo2, hi2):
    """Hoer-Love 64-corner sum in 70-digit decimals, divided by the transverse areas, times K4."""
    from decimal import Decimal, getcontext
    getcontext().prec = 70
    tot = Decimal(0)
    for s0, i0 in ((1, 0), (-1, 1), (-1, 2), (1, 3)):
        for s1, i1 in ((1, 0), (-1, 1), (-1, 2), (1, 3)):
            for s2, i2 in ((1, 0), (-1, 1), (-1, 2), (1, 3)):
                u = []
                for d, ii in zip(range(3), (i0, i1, i2), strict=True):
                    D = Decimal
                    u.append([D(hi2[d]) - D(lo1[d]), D(hi2[d]) - D(hi1[d]), D(lo2[d]) - D(lo1[d]),
                              D(lo2[d]) - D(hi1[d])][ii])
                tot += s0 * s1 * s2 * _dec_hl_f(*u)
    a1 = (Decimal(hi1[1]) - Decimal(lo1[1])) * (Decimal(hi1[2]) - Decimal(lo1[2]))
    a2 = (Decimal(hi2[1]) - Decimal(lo2[1])) * (Decimal(hi2[2]) - Decimal(lo2[2]))
    return float(Decimal(core.K4) * tot / (a1 * a2))


def test_dd_hoer_love_function_vs_decimal():
    """l2_dd.hl_f agrees with a 70-digit decimal evaluation to ~1e-30 relative, also for thin / zero arguments."""
    from decimal import Decimal, getcontext
    from moduleforge.solvers import l2_dd as dd
    getcontext().prec = 70
    pts = [(0.3, 0.7, 1.1), (1e-3, 2e-6, 3e-5), (2.9e-3, 7.4e-6, 7.4e-6), (0.0, 1e-3, 2e-3), (5e-3, 0.0, 0.0),
           (1e-3, 1e-3, 1e-3), (2e-3, 1.0000001e-3, 1e-6), (-2e-3, 1e-3, -3e-4)]
    for p in pts:
        h, lo = dd.hl_f(*(dd.dd(np.array([v])) for v in p))
        ref = _dec_hl_f(*p)
        got = Decimal(float(h[0])) + Decimal(float(lo[0]))
        assert abs(got - ref) <= Decimal("1e-29") * abs(ref) + Decimal("1e-60")


@pytest.mark.parametrize("di,dj", [(0, 0), (0, 1), (1, 1), (1, 2), (3, 1), (4, 4)])
def test_plane_table_thin_layers_rounding_bound_vs_decimal(di, dj):
    """R3: on the 1-7 um surface layers of real meshes the 64-term Hoer-Love corner sum cancels like (length/thickness)^4
    in float64 (measured 1.8e-7 here).  plane_table_full evaluates it in double-double: every near entry matches an
    independent 70-digit decimal evaluation, within the stated rounding bound (and ~1e-13 in practice)."""
    um = 1e-6
    lay = [(6 * um, 7 * um), (4 * um, 6 * um), (1 * um, 4 * um), (0.0, 1 * um)]
    ax, ay = 0.35e-3, 0.28e-3
    T, quad, rnd = core.plane_table_full(lay, lay, ax, ay, 8, 8)
    assert quad < 1e-9 and 0.0 < rnd < 1e-12
    for la in range(len(lay)):
        for lb in range(len(lay)):
            lo1, hi1 = [0.0, 0.0, lay[la][0]], [ax, ay, lay[la][1]]
            x0, y0 = core.snap(di * ax), core.snap(dj * ay)
            lo2 = [float(x0), float(y0), lay[lb][0]]
            hi2 = [float(core.snap((di + 1) * ax)), float(core.snap((dj + 1) * ay)), lay[lb][1]]
            lo1[:2] = [0.0, 0.0]
            hi1[:2] = [float(core.snap(ax)), float(core.snap(ay))]
            ref = _dec_box(lo1, hi1, lo2, hi2)
            assert abs(T[la, lb, di, dj] - ref) <= (1e-13 + rnd) * abs(ref)
