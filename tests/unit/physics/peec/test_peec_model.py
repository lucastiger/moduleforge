"""L1 PEEC model: image theory, network solve, SPD, scaling, sqrt(f) resistance, frequency trends."""
import dataclasses

import numpy as np
import pytest
import shapely.affinity as aff

from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import BondWire, Die, Layout, Terminal, Trace
from moduleforge.geometry.stack import LayerStack
from moduleforge.physics.peec import LoopResult, loop_inductance
from moduleforge.physics.peec import model as pm
from moduleforge.physics.peec.kernels import MU0, filament_mutual_parallel


@pytest.fixture(scope="module")
def layouts():
    return generate_layouts(3, seed=11, dies_per_switch=3)


# ---- image theory ----------------------------------------------------------------------------------
def test_wire_over_plane_matches_image_theory():
    length, a, h = 100e-3, 0.1e-3, 1e-3
    sp, su, sl = np.array([[0.0, 0.0, h]]), np.array([[1.0, 0.0, 0.0]]), np.array([length])
    p2, u2 = pm._reflect(sp, su, 0.0)
    m_img = pm._seg_matrix(sp, su, sl, p2, u2)[0, 0]
    ext = MU0 * length / (2 * np.pi) * (np.arcsinh(length / a) - np.sqrt(1 + (a / length) ** 2) + a / length)
    l_eff = ext - m_img
    # (1) image theory, finite length (Grover): image filament at distance 2h with reversed current
    assert l_eff == pytest.approx(ext - filament_mutual_parallel(length, length, 2 * h, 0.0), rel=2e-3)
    # (2) infinite wire above a ground plane: L' = mu0/(2 pi) acosh(h/a); end effects ~ 1 %
    assert l_eff == pytest.approx(MU0 * length / (2 * np.pi) * np.arccosh(h / a), rel=0.02)
    assert l_eff < ext


def test_vertical_wire_image_current_has_same_direction():
    # a vertical wire has an image current in the same direction: mutual to the image adds (L_eff > L_self)
    length, h = 2e-3, 1e-3
    sp, su, sl = np.array([[0.0, 0.0, h]]), np.array([[0.0, 0.0, 1.0]]), np.array([length])
    p2, u2 = pm._reflect(sp, su, 0.0)
    m_img = pm._seg_matrix(sp, su, sl, p2, u2)[0, 0]
    assert m_img < 0.0  # mirrored direction vector is -z; the image *current* is +z, so L_eff = L - m_img > L


def test_plane_weights_follow_skin_depth(layouts):
    lay = layouts[0]
    names, w, z = pm._plane_weights(lay, np.array([1e5, 5e6, 2e7, 8e7]))
    assert names == ["backside_cu", "baseplate"]
    # delta << t (>= 5 MHz): only the backside Cu is imaged, weight 1 to < 1e-4; baseplate shielded
    assert np.all(w[0, 1:] > 1 - 1e-4) and np.all(w[1, 1:] < 1e-4)
    # at 100 kHz delta = 0.21 mm ~ t_backside: flux leaks to the baseplate; weights sum to <= 1
    assert w[1, 0] > 0.1 and w[:, 0].sum() <= 1.0 + 1e-12
    assert z[0] == pytest.approx(lay.stack.z_top("backside_cu"))


# ---- network solve ---------------------------------------------------------------------------------
def test_port_impedance_series_and_parallel_with_mutual():
    w = 2 * np.pi * 1e6
    r1, r2, l1, l2, m = 0.01, 0.02, 5e-9, 7e-9, 2e-9
    L = np.array([[l1, m], [m, l2]])
    Z = 1j * w * L + np.diag([r1, r2])
    # series chain 0 -> 1 -> 2, port 0 to 2: Z1 + Z2 + 2 jwM
    A = pm._incidence(np.array([0, 1]), np.array([1, 2]), 3)
    z = pm._port_impedance(Z, A, 0, 2)
    assert z == pytest.approx(r1 + r2 + 1j * w * (l1 + l2 + 2 * m), rel=1e-9)
    # two branches in parallel between nodes 0 and 1: (Z1 Z2 - Zm^2) / (Z1 + Z2 - 2 Zm)
    A = pm._incidence(np.array([0, 0]), np.array([1, 1]), 2)
    z = pm._port_impedance(Z, A, 0, 1)
    z1, z2, zm = r1 + 1j * w * l1, r2 + 1j * w * l2, 1j * w * m
    assert z == pytest.approx((z1 * z2 - zm**2) / (z1 + z2 - 2 * zm), rel=1e-9)
    # reciprocity: swapping pos/neg flips the sign only
    assert pm._port_impedance(Z, A, 1, 0) == pytest.approx(z, rel=1e-9)


# ---- symmetry / SPD --------------------------------------------------------------------------------
def test_partial_inductance_matrix_symmetric_positive_definite(layouts):
    d = pm._discretize(layouts[0], pm.DEFAULT_HMAX)
    L = d.assemble(None)
    assert np.allclose(L, L.T, rtol=1e-9, atol=1e-18)
    assert np.all(np.linalg.eigvalsh(0.5 * (L + L.T)) > 0)
    # with a perfect image plane the effective inductance matrix is still SPD (stored field energy > 0)
    zp = layouts[0].stack.z_top("backside_cu")
    Leff = L - d.assemble(zp)
    assert np.allclose(Leff, Leff.T, rtol=1e-9, atol=1e-18)
    assert np.all(np.linalg.eigvalsh(0.5 * (Leff + Leff.T)) > 0)
    assert np.all(np.diag(Leff) < np.diag(L))  # every branch loses inductance to its image


# ---- length scaling --------------------------------------------------------------------------------
def _scaled(lay: Layout, k: float) -> Layout:
    sc = lambda g: aff.scale(g, k, k, origin=(0, 0))  # noqa: E731
    stack = LayerStack(tuple(dataclasses.replace(la, thickness=la.thickness * k) for la in lay.stack.layers),
                       kind=lay.stack.kind)
    dies = [Die(d.cx * k, d.cy * k, d.w * k, d.h * k, d.switch, {n: tuple(v * k for v in r) for n, r in d.pads.items()},
                d.thickness * k, d.attach_thickness * k) for d in lay.dies]
    wires = [BondWire(w.points * k, w.diameter * k, w.loop_height * k, w.net) for w in lay.wires]
    terms = {n: Terminal(t.net, t.cx * k, t.cy * k, t.w * k, t.h * k) for n, t in lay.terminals.items()}
    return Layout(lay.family, lay.dies_per_switch, sc(lay.outline), [Trace(t.net, sc(t.polygon)) for t in lay.traces],
                  dies, wires, terms, sc(lay.baseplate_outline), stack, lay.backside_inset * k, lay.wire_sigma)


def test_partial_inductance_matrix_scales_with_length(layouts):
    lay = layouts[0]
    d1 = pm._discretize(lay, 4e-3)
    d2 = pm._discretize(_scaled(lay, 2.0), 8e-3)
    assert d1.nb == d2.nb
    assert np.allclose(d2.assemble(None), 2 * d1.assemble(None), rtol=1e-6, atol=0)
    zp = lay.stack.z_top("backside_cu")
    assert np.allclose(d2.assemble(2 * zp), 2 * d1.assemble(zp), rtol=1e-6, atol=0)


# ---- end-to-end trends ------------------------------------------------------------------------------
def test_loop_result_shapes_and_frequency_trends(layouts):
    for lay in layouts:
        r = loop_inductance(lay, [5e6, 2e7, 8e7])
        assert isinstance(r, LoopResult)
        L, R = np.asarray(r.L_H), np.asarray(r.R_ohm)
        assert L.shape == R.shape == (3,) and np.all(np.isfinite(L)) and np.all(R > 0)
        assert np.all((L > 1e-9) & (L < 1e-7))
        assert L[0] >= L[1] * (1 - 1e-6) >= L[2] * (1 - 1e-6) ** 2  # skin effect only lowers L
        assert set(r.meta["imaged_planes"]) == {"backside_cu"}


def test_loop_resistance_grows_as_sqrt_f(layouts):
    r = loop_inductance(layouts[0], [5e6, 2e7, 8e7])
    ratio = np.asarray(r.R_ohm)[1:] / np.asarray(r.R_ohm)[:-1]
    assert ratio == pytest.approx([2.0, 2.0], rel=0.04)  # bond wires (delta/a ~ 0.13) and Cu bars, delta << t


def test_loop_inductance_deterministic_and_batched_frequencies_consistent(layouts):
    a = loop_inductance(layouts[1], [2e7]).L_H
    b = loop_inductance(layouts[1], [5e6, 2e7]).L_H
    assert a[0] == b[1]
    assert loop_inductance(layouts[1], [2e7]).L_H[0] == a[0]


def test_loop_inductance_converges_with_mesh_refinement(layouts):
    lay = layouts[2]
    coarse, mid, fine = (loop_inductance(lay, [2e7], hmax=h).L_H[0] for h in (8e-3, 4e-3, 2e-3))
    assert abs(mid - fine) < abs(coarse - fine) + 0.02 * fine  # refining moves toward the fine answer
    assert mid == pytest.approx(fine, rel=0.10)


def test_more_wire_height_gives_more_inductance():
    lay = generate_layouts(1, seed=5, dies_per_switch=2)[0]
    taller = dataclasses.replace(lay, wires=[
        BondWire(np.column_stack([w.points[:, :2], w.points[:, 2]
                                  + 1.0e-3 * np.sin(np.pi * np.linspace(0, 1, len(w.points)))]),
                 w.diameter, w.loop_height + 1e-3, w.net) for w in lay.wires])
    base = loop_inductance(lay, [2e7]).L_H[0]
    assert loop_inductance(taller, [2e7]).L_H[0] > base


def test_rejects_bad_frequency(layouts):
    with pytest.raises(ValueError):
        loop_inductance(layouts[0], [0.0])
