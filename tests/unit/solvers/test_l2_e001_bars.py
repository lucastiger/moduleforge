"""Bar conductors of l2 (exact Hoer-Love kernel, T0071).

Closed forms (independent of the implementation under test):
[HL] Hoer & Love, J. Res. NBS 69C (1965) 127: mutual partial inductance of parallel boxes with uniform axial current;
[G]  Grover, Inductance Calculations (1946) ch. 7: filament mutual, integrated here by a tensor Gauss rule over the
     two cross-sections (no corner formula involved);
[R]  Rosa/Ruehli rectangular bar: L = mu0 l/(2 pi) [ln(2 l/(w+t)) + 1/2 + 0.2235 (w+t)/l] (loose cross-check, 1 %).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from moduleforge.solvers import l2, l2_core as core
from test_l2_core import _dec_box

MU0 = 4e-7 * math.pi
SIG_CU = 5.8e7
MM = 1e-3


def bar(name, x0, x1, y, z, w, t, sig=SIG_CU):
    return l2.Bar(name, (x0 * MM, y * MM, z * MM), (x1 * MM, y * MM, z * MM), w * MM, t * MM, sig)


def pt(name, b, rev=False):
    a, c = (1, 0) if rev else (0, 1)
    return l2.Port(name, l2.Terminal(b.name, a), l2.Terminal(b.name, c))


def ind(res, f_index=0):
    w = 2 * math.pi * res.freqs_hz[f_index]
    return res.z[f_index].imag / w


def box_gauss(lo1, hi1, lo2, hi2, n=14):
    """Independent mutual of two parallel boxes (axis x): tensor Gauss over both cross-sections of the exact filament
    double integral [G]; valid for separated cross-sections."""
    y1, wy1 = core.gq(n, lo1[1], hi1[1])
    z1, wz1 = core.gq(n, lo1[2], hi1[2])
    y2, wy2 = core.gq(n, lo2[1], hi2[1])
    z2, wz2 = core.gq(n, lo2[2], hi2[2])
    tot = 0.0
    for ya, wa in zip(y1, wy1, strict=True):
        for za, wza in zip(z1, wz1, strict=True):
            d = np.hypot(y2[:, None] - ya, z2[None, :] - za)
            tot += wa * wza * np.sum(core.fil_F(lo1[0], hi1[0], lo2[0], hi2[0], d) * np.outer(wy2, wz2))
    area = (hi1[1] - lo1[1]) * (hi1[2] - lo1[2]) * (hi2[1] - lo2[1]) * (hi2[2] - lo2[2])
    return core.K4 * tot / area


def hl_self(ln, w, t):
    lo, hi = np.zeros((1, 3)), np.array([[ln, w, t]])
    return float(core.hl_box(lo, hi, lo, hi, 0)[0])


# ---------------------------------------------------------------------------------------------------- self / mutual
def test_hl_self_vs_rosa_ruehli_and_cube_limit():
    ln, w, t = 20 * MM, 3 * MM, 0.3 * MM
    rr = MU0 * ln / (2 * math.pi) * (math.log(2 * ln / (w + t)) + 0.5 + 0.2235 * (w + t) / ln)
    assert hl_self(ln, w, t) == pytest.approx(rr, rel=1e-2)  # the closed form is itself a ~0.4 % approximation
    # unit cube self partial inductance (Ruehli / Hoer-Love): 1.9e-7 H per metre of side to 3 digits
    assert hl_self(1.0, 1.0, 1.0) == pytest.approx(1.9e-7, rel=2e-2)


@pytest.mark.parametrize("level", [1, 2])
def test_bar_self_inductance_vs_hoer_love(level):
    """A1/A2 of the contract: at 100 Hz (skin depth 6.6 mm >> section) the current is uniform, so Im Z / omega is the
    single-box Hoer-Love self inductance, whatever the cross-section mesh."""
    for ln, w, t in ((20, 3, 0.3), (10, 1, 1)):
        b = bar("b", 0, ln, 0, 0, w, t)
        r = l2.solve([b], [], [pt("p", b)], [100.0], level)
        ref = hl_self(ln * MM, w * MM, t * MM)
        assert ind(r)[0, 0] == pytest.approx(ref, rel=1e-4)  # contract tolerance for A1/A2
        # the residual is the physical skin redistribution ~ f^2, not a kernel error: it shrinks 100x for f / 10
        lo = l2.solve([b], [], [pt("p", b)], [10.0], level)
        assert abs(ind(lo)[0, 0] - ref) < 0.05 * abs(ind(r)[0, 0] - ref) + 1e-12 * ref
        assert r.z[0, 0, 0].real == pytest.approx(ln * MM / (SIG_CU * w * MM * t * MM), rel=1e-4)  # DC R (+ skin ~ f^2)
        assert r.meta["solver_tol"] < 1e-6


def test_bar_mutual_vs_independent_quadrature_and_hoer_love():
    """Two 20x3x0.3 bars, 4 mm centres: M12 against a tensor Gauss of [G] and against the corner formula [HL]."""
    b1, b2 = bar("a", 0, 20, 0, 0, 3, 0.3), bar("b", 0, 20, 4, 0, 3, 0.3)
    r = l2.solve([b1, b2], [], [pt("p1", b1), pt("p2", b2)], [100.0], 2)
    m = ind(r)[0, 1]
    lo1, hi1 = [0, -1.5 * MM, -0.15 * MM], [20 * MM, 1.5 * MM, 0.15 * MM]
    lo2, hi2 = [0, 2.5 * MM, -0.15 * MM], [20 * MM, 5.5 * MM, 0.15 * MM]
    assert m == pytest.approx(box_gauss(lo1, hi1, lo2, hi2), rel=1e-9)
    hl = core.hl_box(np.array([lo1]), np.array([hi1]), np.array([lo2]), np.array([hi2]), 0)[0]
    assert m == pytest.approx(hl, rel=1e-9)
    assert ind(r)[0, 0] == pytest.approx(hl_self(20 * MM, 3 * MM, 0.3 * MM), rel=1e-9)


def test_bar_stacked_offset_mutual_a4_geometry():
    """A4-like: 15x3x0.3 at z=0 and 10x2x0.3 at x in [5, 15], y=0.5, z=0.8 (axial offset, different widths)."""
    b1, b2 = bar("a", 0, 15, 0, 0, 3, 0.3), bar("b", 5, 15, 0.5, 0.8, 2, 0.3)
    r = l2.solve([b1, b2], [], [pt("p1", b1), pt("p2", b2)], [100.0], 2)
    lo1, hi1 = [0, -1.5 * MM, -0.15 * MM], [15 * MM, 1.5 * MM, 0.15 * MM]
    lo2, hi2 = [5 * MM, -0.5 * MM, 0.65 * MM], [15 * MM, 1.5 * MM, 0.95 * MM]
    assert ind(r)[0, 1] == pytest.approx(box_gauss(lo1, hi1, lo2, hi2), rel=1e-9)


def test_hl_f_translation_and_corner_symmetry():
    """The corner function is even in each argument (it is a function of |x|, |y|, |z|)."""
    v = core.hl_f(0.3, 0.7, 1.1)
    for s in ((-1, 1, 1), (1, -1, 1), (1, 1, -1), (-1, -1, -1)):
        assert core.hl_f(0.3 * s[0], 0.7 * s[1], 1.1 * s[2]) == pytest.approx(v, rel=1e-13)


def test_distinct_offset_reuse_is_exact():
    """Toeplitz reuse: bar_block equals the brute-force hl_box over every (segment, cell) pair of two bars."""
    sp1 = core.BarSpec("a", np.array([0.0, 0.0, 0.0]), np.array([4e-3, 0.0, 0.0]), 1e-3, 0.3e-3, SIG_CU, None)
    sp2 = core.BarSpec("b", np.array([1e-3, 2e-3, 0.5e-3]), np.array([6e-3, 2e-3, 0.5e-3]), 0.8e-3, 0.3e-3, SIG_CU, None)
    A, B = core.build_bar_mesh(sp1, 1, 1e6, 0), core.build_bar_mesh(sp2, 1, 1e6, 100)
    L, E = core.bar_block(A, B)

    def boxes(m):
        out = []
        t1, t2 = m.t
        for s in range(m.ns):
            for i in range(len(m.nodes[t1]) - 1):
                for j in range(len(m.nodes[t2]) - 1):
                    lo, hi = np.zeros(3), np.zeros(3)
                    lo[m.ax], hi[m.ax] = m.nodes[m.ax][s], m.nodes[m.ax][s + 1]
                    lo[t1], hi[t1] = m.nodes[t1][i], m.nodes[t1][i + 1]
                    lo[t2], hi[t2] = m.nodes[t2][j], m.nodes[t2][j + 1]
                    out.append((lo, hi))
        return out

    ba, bb = boxes(A), boxes(B)
    assert L.shape == (len(bb), len(ba))
    for k in (0, 7, len(bb) - 1):
        for m_ in (0, 3, len(ba) - 1):
            ref = _dec_box(ba[m_][0], ba[m_][1], bb[k][0], bb[k][1])  # independent 70-digit decimal corner sum
            assert abs(L[k, m_] - ref) <= float(E[k, m_]) + 1e-13 * abs(ref)
    assert np.all(E >= 0)


# ---------------------------------------------------------------------------------------------------- scaling
def test_exact_length_scaling_of_bars():
    """Scaling all lengths by s and the frequency by 1/s^2 (skin depth scales by s, so the graded mesh is the same up to
    s): L -> s L, R -> R / s, hence Z -> Z / s.  Hoer-Love is homogeneous of degree 1 in lengths."""
    def case(s):
        b1 = l2.Bar("a", (0, 0, 0), (20e-3 * s, 0, 0), 3e-3 * s, 0.3e-3 * s, SIG_CU)
        b2 = l2.Bar("b", (0, 4e-3 * s, 0), (20e-3 * s, 4e-3 * s, 0), 3e-3 * s, 0.3e-3 * s, SIG_CU)
        return l2.solve([b1, b2], [], [pt("p1", b1), pt("p2", b2)], [2e6 / s**2], 2).z[0]
    z1, z2 = case(1.0), case(2.5)
    assert z2 == pytest.approx(z1 / 2.5, rel=1e-9)
    # axial-only scaling of a self term: L(2 l) vs 2 L(l) differs by the known log, so just check monotone super-linearity
    assert hl_self(40 * MM, 3 * MM, 0.3 * MM) > 2 * hl_self(20 * MM, 3 * MM, 0.3 * MM)


def test_bar_hf_current_crowding_lowers_inductance():
    """At 80 MHz (skin depth 7.4 um << 300 um) the internal inductance vanishes and Im Z/omega drops below DC L."""
    b = bar("b", 0, 10, 0, 0, 2, 0.3)
    r = l2.solve([b], [], [pt("p", b)], [100.0, 80e6], 3)
    assert ind(r, 1)[0, 0] < ind(r, 0)[0, 0]
    assert r.z[1, 0, 0].real > 20 * r.z[0, 0, 0].real  # resistance rises ~ (t/2 delta) at HF
    assert r.meta["gmres_converged"] if "gmres_converged" in r.meta else True


# ---------------------------------------------------------------------------------------------------- mesh map / solve
def test_bar_map_is_one_fixed_map_with_skin_surface_cell():
    """bar_fractions samples ONE map at xi = i / n for every level (geometric similarity): the nodes of the n-cell mesh
    at xi = j / m coincide with the m-cell mesh's nodes whenever m divides n; the surface cell is skin depth / 2 at the
    finest count, the map is symmetric and monotone, and the surface cell shrinks with the cell-count ratio."""
    ext, f = 3e-3, 20e6
    tgt = 0.5 * core.skin(f, SIG_CU) / ext
    nf = core.BAR_FINEST[0]
    fine = core.bar_fractions(nf, nf, tgt)
    assert fine[1] == pytest.approx(tgt, rel=1e-12)
    a, b = core.bar_fractions(12, nf, tgt), core.bar_fractions(24, nf, tgt)
    assert np.allclose(b[::2], a, rtol=0, atol=1e-15)  # same map: nested where the counts nest
    for n in (core.BAR_NW[k] for k in range(1, core.MAX_REFINEMENT + 1)):
        fr = core.bar_fractions(n, nf, tgt)
        assert np.all(np.diff(fr) > 0) and fr[0] == 0.0 and fr[-1] == 1.0
        assert np.allclose(fr + fr[::-1], 1.0, atol=1e-15)  # symmetric about the centre
        assert fr[1] * n == pytest.approx(tgt * nf, rel=1e-3)  # surface cell ~ 1/n (a / n + O(n^-8))
    assert np.array_equal(core.bar_fractions(4, 8, 0.5), np.arange(5) / 4)  # uniform when already finer


def test_bar_gmres_agrees_with_dense_lu_within_solver_tol():
    """The iterative bar solve (real L, block preconditioner) against the dense complex LU on A3's geometry, at 100 Hz
    (R-dominated) and 20 MHz (wL-dominated): |Z_gmres - Z_dense| / |Z| <= the reported solver_tol, converged flags."""
    specs = [core.BarSpec("b1", np.array([0, 0, 0.]), np.array([20 * MM, 0, 0]), 3 * MM, 0.3 * MM, SIG_CU),
             core.BarSpec("b2", np.array([0, 4 * MM, 0.]), np.array([20 * MM, 4 * MM, 0]), 3 * MM, 0.3 * MM, SIG_CU)]
    pts = [((0, 0), (0, 1)), ((1, 0), (1, 1))]
    d, _ = core.solve_case(specs, None, pts, [100.0, 2e7], 1, dense=True)
    g, meta = core.solve_case(specs, None, pts, [100.0, 2e7], 1, dense=False)
    for fi in range(2):
        err = np.abs(g.z[fi] - d.z[fi]).max() / np.abs(d.z[fi]).max()
        assert err <= meta["solver_tol"]
    assert meta["gmres_info"] == [[0, 0], [0, 0]] and meta["gmres_converged"]
    assert all(it > 0 for it in meta["gmres_iters"])  # really iterated


def test_bar_dense_switch_by_memory():
    """Dense LU only while the complex matrix fits BAR_DENSE_BYTES; the real L is applied without a complex copy."""
    bm = core.build_bar_mesh(core.BarSpec("b", np.zeros(3), np.array([5 * MM, 0, 0]), 1 * MM, 0.3 * MM, SIG_CU), 1, 1e6, 0)
    s = core.BarSystem([bm])
    assert s.dense_ok == (16 * s.n**2 <= core.BAR_DENSE_BYTES)
    x = np.random.default_rng(1).standard_normal(s.n) + 1j * np.random.default_rng(2).standard_normal(s.n)
    assert np.allclose(s.lmul(x), s.L @ x.real + 1j * (s.L @ x.imag), rtol=1e-14, atol=0)
