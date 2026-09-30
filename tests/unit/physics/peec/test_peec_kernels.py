"""Closed-form kernels of the L1 PEEC model against independent analytic / brute-force values."""
import numpy as np
import pytest

from moduleforge.physics.peec.kernels import (
    MU0,
    bar_mutual_hoer_love,
    bar_resistance,
    filament_mutual_parallel,
    round_wire_self,
    segment_mutual,
    skin_depth,
    wire_resistance,
)


def _grover_parallel(length, d):
    """Grover (1946) ch. 3: equal-length parallel filaments, aligned ends."""
    return MU0 * length / (2 * np.pi) * (np.arcsinh(length / d) - np.sqrt(1 + (d / length) ** 2) + d / length)


def _brute_bar_mutual(c1, d1, c2, d2, axis, n=6):
    """Bars as n x n grids of filaments; mutual by averaging the (independent) Grover filament formula."""
    o = [(axis + 1) % 3, (axis + 2) % 3]
    g = (np.arange(n) + 0.5) / n - 0.5
    ga, gb = np.meshgrid(g, g)

    def fil_pos(c, d):
        p = np.tile(np.asarray(c, float), (n * n, 1))
        p[:, o[0]] += ga.ravel() * d[o[0]]
        p[:, o[1]] += gb.ravel() * d[o[1]]
        return p

    p1, p2 = fil_pos(c1, d1), fil_pos(c2, d2)
    dist = np.linalg.norm((p1[:, None, o] - p2[None, :, o]), axis=-1)
    off = (c2[axis] - d2[axis] / 2) - (c1[axis] - d1[axis] / 2)
    return filament_mutual_parallel(d1[axis], d2[axis], dist, off).mean()


# ---- analytic / published-value checks ----------------------------------------------------------------
def test_filament_formula_matches_grover_equal_length():
    length, d = 12e-3, 1.7e-3
    assert filament_mutual_parallel(length, length, d, 0.0) == pytest.approx(_grover_parallel(length, d), rel=1e-12)


def test_filament_formula_far_field_and_offset_symmetry():
    # Neumann limit of two short filaments a long way apart: M -> mu0 l1 l2 / (4 pi r)
    l1, l2, r = 1e-3, 2e-3, 0.5
    assert filament_mutual_parallel(l1, l2, r, 0.0) == pytest.approx(MU0 * l1 * l2 / (4 * np.pi * r), rel=1e-5)
    # swapping the roles of the two filaments (reference start moves to filament 2) must not change M
    assert filament_mutual_parallel(3e-3, 5e-3, 1e-3, 2e-3) == pytest.approx(
        filament_mutual_parallel(5e-3, 3e-3, 1e-3, -2e-3), rel=1e-12)


@pytest.mark.parametrize(
    "c2,d2",
    [
        ([5e-3, 1e-3, 1e-3], [2e-3, 0.3e-3, 4e-3]),  # offset, different length
        ([0, 0.8e-3, 3.5e-3], [3e-3, 0.3e-3, 3e-3]),  # stacked, end to end offset
        ([0, 4e-3, 0.3e-3], [3e-3, 0.3e-3, 3e-3]),
    ],
)
def test_hoer_love_mutual_vs_filament_brute_force(c2, d2):
    c1, d1 = np.zeros(3), np.array([3e-3, 0.3e-3, 3e-3])
    c2, d2 = np.array(c2), np.array(d2)
    got = bar_mutual_hoer_love(c1, d1, c2, d2, 2)
    ref = _brute_bar_mutual(c1, d1, c2, d2, 2)
    assert got == pytest.approx(ref, rel=5e-3)


def test_hoer_love_self_inductance_vs_grover_bar_formula():
    # Grover (1946) / Ruehli (1972): L = mu0 length/(2 pi) [ln(2l/(w+t)) + 1/2 + 0.2235 (w+t)/length], length >> w, t
    w, t, length = 3e-3, 0.3e-3, 60e-3
    c, d = np.zeros(3), np.array([w, t, length])
    ref = MU0 * length / (2 * np.pi) * (np.log(2 * length / (w + t)) + 0.5 + 0.2235 * (w + t) / length)
    assert bar_mutual_hoer_love(c, d, c, d, 2) == pytest.approx(ref, rel=3e-3)


def test_hoer_love_axis_permutation_invariance():
    d = np.array([3e-3, 0.3e-3, 20e-3])
    m_z = bar_mutual_hoer_love(np.zeros(3), d, np.array([0, 1e-3, 2e-3]), d, 2)
    dx, cx = d[[2, 0, 1]], np.array([2e-3, 0, 1e-3])  # same bars with the current along x
    assert bar_mutual_hoer_love(np.zeros(3), dx, cx, dx, 0) == pytest.approx(m_z, rel=1e-12)
    dy, cy = d[[1, 2, 0]], np.array([1e-3, 2e-3, 0])
    assert bar_mutual_hoer_love(np.zeros(3), dy, cy, dy, 1) == pytest.approx(m_z, rel=1e-12)


def test_round_wire_self_vs_grover_asymptote():
    # Grover: L = mu0 length/(2 pi) [ln(2 length / a) - 3/4] (DC, length >> a) and ln(2l/a) - 1 at high frequency
    length, a = 0.1, 1e-4
    dc = round_wire_self(length, a)
    assert dc == pytest.approx(MU0 * length / (2 * np.pi) * (np.log(2 * length / a) - 0.75), rel=2e-3)
    hf = round_wire_self(length, a, delta=1e-9)
    assert hf == pytest.approx(MU0 * length / (2 * np.pi) * (np.log(2 * length / a) - 1.0), rel=2e-3)
    assert hf < dc


def test_skin_depth_copper():
    assert skin_depth(20e6, 5.8e7) == pytest.approx(14.8e-6, rel=0.02)  # 66.1 um / sqrt(f/MHz)
    assert skin_depth(100e6, 5.8e7) == pytest.approx(6.6e-6, rel=0.02)


# ---- segments (Neumann) --------------------------------------------------------------------------------
def test_segment_mutual_parallel_matches_grover():
    length, d = 5e-3, 0.7e-3
    p1, p2 = np.array([0, 0, 0.0]), np.array([0, d, 0.0])
    u = np.array([1.0, 0, 0])
    assert segment_mutual(p1, u, length, p2, u, length, n=8) == pytest.approx(_grover_parallel(length, d), rel=1e-5)


def test_segment_mutual_orthogonal_is_zero_and_reciprocal():
    ux, uy = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    assert segment_mutual(np.zeros(3), ux, 1e-3, np.array([0, 0, 1e-3]), uy, 1e-3) == 0.0
    # skew segments: reciprocity
    pa, ua = np.array([0.0, 0, 0]), np.array([1.0, 0, 0])
    ub = np.array([0.6, 0.0, 0.8])
    pb = np.array([0.5e-3, 1e-3, 0.3e-3])
    m_ab = segment_mutual(pa, ua, 2e-3, pb, ub, 1.5e-3, n=8)
    m_ba = segment_mutual(pb, ub, 1.5e-3, pa, ua, 2e-3, n=8)
    assert m_ab == pytest.approx(m_ba, rel=1e-6)


def test_segment_mutual_skew_vs_double_integral():
    pa, ua, la = np.array([0.0, 0, 0]), np.array([1.0, 0, 0]), 2e-3
    ub = np.array([0.6, 0.0, 0.8])
    pb, lb = np.array([0.5e-3, 1e-3, 0.3e-3]), 1.5e-3
    n = 400
    s = (np.arange(n) + 0.5) / n * la
    t = (np.arange(n) + 0.5) / n * lb
    r = np.linalg.norm((pa + s[:, None] * ua)[:, None, :] - (pb + t[:, None] * ub)[None, :, :], axis=-1)
    ref = MU0 / (4 * np.pi) * (ua @ ub) * (la / n) * (lb / n) * np.sum(1.0 / r)
    assert segment_mutual(pa, ua, la, pb, ub, lb, n=8) == pytest.approx(ref, rel=1e-4)


def test_segment_mutual_touching_collinear_segments_finite_and_additive():
    # a straight filament split in two: L(length) = L1 + L2 + 2 M12 with Grover self of the same thin wire
    a, length = 1e-5, 4e-3  # thin wire: the filament mutual of touching segments ignores O(a/length) radius effects
    u, p = np.array([1.0, 0, 0]), np.zeros(3)
    m12 = segment_mutual(p, u, length / 2, p + u * length / 2, u, length / 2, n=8)
    ext = lambda ll: MU0 * ll / (2 * np.pi) * (np.arcsinh(ll / a) - np.sqrt(1 + (a / ll) ** 2) + a / ll)  # noqa: E731
    assert ext(length / 2) * 2 + 2 * m12 == pytest.approx(ext(length), rel=2e-3)


# ---- limiting cases ------------------------------------------------------------------------------------
def test_far_field_bar_mutual_tends_to_filament_formula():
    d1 = np.array([3e-3, 0.3e-3, 4e-3])
    c1 = np.zeros(3)
    for k in (10, 30):
        r = k * 4e-3
        c2 = np.array([r, 0.0, 0.0])
        bar = bar_mutual_hoer_love(c1, d1, c2, d1, 2)
        fil = filament_mutual_parallel(4e-3, 4e-3, r, 0.0)
        assert bar == pytest.approx(fil, rel=2e-3 if k == 10 else 1e-3)


# ---- symmetry ------------------------------------------------------------------------------------------
def test_bar_mutual_reciprocity_and_positive_matrix():
    rng = np.random.default_rng(3)
    n = 8
    c = rng.uniform(0, 6e-3, (n, 3))
    d = np.tile([1e-3, 0.3e-3, 3e-3], (n, 1)) * rng.uniform(0.7, 1.4, (n, 3))
    M = np.array([[bar_mutual_hoer_love(c[i], d[i], c[j], d[j], 2) for j in range(n)] for i in range(n)])
    assert np.allclose(M, M.T, rtol=1e-9)
    assert np.all(np.linalg.eigvalsh(0.5 * (M + M.T)) > 0)


# ---- scaling -------------------------------------------------------------------------------------------
def test_inductance_kernels_scale_linearly_with_length():
    c, d = np.array([0.0, 0.0, 0.0]), np.array([1e-3, 0.3e-3, 4e-3])
    c2 = np.array([1.5e-3, 0.7e-3, 1e-3])
    assert bar_mutual_hoer_love(2 * c, 2 * d, 2 * c2, 2 * d, 2) == pytest.approx(
        2 * bar_mutual_hoer_love(c, d, c2, d, 2), rel=1e-9)
    assert filament_mutual_parallel(6e-3, 4e-3, 2e-3, 1e-3) == pytest.approx(
        0.5 * filament_mutual_parallel(12e-3, 8e-3, 4e-3, 2e-3), rel=1e-9)
    assert round_wire_self(2e-2, 2e-4) == pytest.approx(2 * round_wire_self(1e-2, 1e-4), rel=1e-9)
    pa, ua, pb, ub = np.zeros(3), np.array([1.0, 0, 0]), np.array([0.5e-3, 1e-3, 0.3e-3]), np.array([0.6, 0, 0.8])
    assert segment_mutual(2 * pa, ua, 4e-3, 2 * pb, ub, 3e-3) == pytest.approx(
        2 * segment_mutual(pa, ua, 2e-3, pb, ub, 1.5e-3), rel=1e-9)


# ---- resistance ----------------------------------------------------------------------------------------
def test_bar_resistance_scales_as_sqrt_f_when_skin_depth_small():
    w, t, length, sig = 3e-3, 0.3e-3, 5e-3, 5.8e7
    f1 = 1e9  # delta = 2.1 um << t
    r1 = bar_resistance(length, w, t, sig, skin_depth(f1, sig))
    r4 = bar_resistance(length, w, t, sig, skin_depth(4 * f1, sig))
    assert r4 / r1 == pytest.approx(2.0, rel=0.02)
    # DC limit: delta >> t -> R = length / (sigma w t)
    assert bar_resistance(length, w, t, sig, 1.0) == pytest.approx(length / (sig * w * t), rel=1e-12)


def test_wire_resistance_sqrt_f_and_dc_limit():
    a, length, sig = 1.5e-4, 3e-3, 3.5e7
    r1 = wire_resistance(length, a, sig, skin_depth(1e9, sig))
    r4 = wire_resistance(length, a, sig, skin_depth(4e9, sig))
    assert r4 / r1 == pytest.approx(2.0, rel=0.02)
    assert wire_resistance(length, a, sig, 1.0) == pytest.approx(length / (sig * np.pi * a * a), rel=1e-12)
