"""L1 PEEC model: image theory, network solve, SPD, scaling, sqrt(f) resistance, frequency trends."""
import dataclasses

import numpy as np
import pytest
import shapely.affinity as aff

from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry import BondWire, Die, Layout, Terminal, Trace
from moduleforge.geometry.layout import arc_wire
from moduleforge.geometry.stack import LayerStack
from moduleforge.physics.peec import LoopResult, loop_inductance
from moduleforge.physics.peec import model as pm
from moduleforge.physics.peec.kernels import MU0, filament_mutual_parallel, skin_depth


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
    # module docstring "Mesh bias": below 2 mm L decreases monotonically; default (4 mm) vs 1 mm is +0.5 .. +2.4 %
    lay = layouts[2]
    l4, l2, l1 = (loop_inductance(lay, [2e7], hmax=h).L_H[0] for h in (4e-3, 2e-3, 1e-3))
    assert l1 < l2 and l1 < l4
    assert 0.0 < l4 / l1 - 1 < 0.025


@pytest.mark.parametrize("family", ["side_by_side", "interleaved", "u_shaped"])
def test_default_mesh_within_documented_bias_of_1mm_mesh(family):
    # module docstring: over 60 layouts the default (4 mm) mesh reads +0.47 .. +2.41 % above the 1 mm mesh
    lay = generate_layouts(1, seed=5, family=family, dies_per_switch=6)[0]
    default = loop_inductance(lay, [2e7]).L_H[0]
    fine = loop_inductance(lay, [2e7], hmax=1e-3).L_H[0]
    assert 0.0 < default / fine - 1 < 0.025


def test_resistance_does_not_fall_without_bound_under_refinement(layouts):
    # the old perimeter skin area counted the shared walls of every cell, so R fell as cells shrank
    r = [loop_inductance(layouts[2], [2e7], hmax=h).R_ohm[0] for h in (8e-3, 4e-3, 2e-3)]
    assert r[2] == pytest.approx(r[1], rel=0.10) and r[1] == pytest.approx(r[0], rel=0.15)


# ---- bond-wire segmentation -----------------------------------------------------------------------
def _wire_partial_inductance(lay, npts):
    """External partial inductance [H] of wire 0 alone (self + all its segments' mutuals)."""
    wires = [arc_wire(w.points[0, :2], w.points[-1, :2], w.points[0, 2], w.points[-1, 2], w.loop_height, w.diameter,
                      w.net, npts=npts) for w in lay.wires]
    d = pm._discretize(dataclasses.replace(lay, wires=wires), 4e-3)
    return d.assemble(None)[d.nb, d.nb]


def test_wire_inductance_converges_with_point_count():
    # regime the model runs in: 0.3 mm wires, 4-7 mm span -> a / l_seg = 0.15 (7 pts) .. 0.6 (25 pts)
    lay = generate_layouts(1, seed=5, dies_per_switch=2)[0]
    seg = lambda n: lay.wires[0].length / (n - 1)  # noqa: E731
    assert 0.1 < lay.wires[0].diameter / 2 / seg(7) < 0.25
    ls = {n: _wire_partial_inductance(lay, n) for n in (7, 13, 25, 49)}
    assert max(ls.values()) / min(ls.values()) - 1 < 0.005
    # converged against a 4x finer polyline
    assert ls[7] == pytest.approx(ls[49], rel=0.005)


def test_polygon_ring_converges_to_thin_ring_closed_form():
    # curved wire: N-gon of radius R with the finite-radius same-wire kernel -> mu0 R (ln(8R/a) - 2), the
    # external inductance of a thin ring with surface current (Rosa 1908; Grover 1946 ch. 13), a/R = 0.05
    big_r, a = 3e-3, 0.15e-3
    exact = MU0 * big_r * (np.log(8 * big_r / a) - 2)
    err = []
    for n in (24, 48, 96):  # a / l_seg = 0.19 .. 0.76
        th = np.linspace(0, 2 * np.pi, n + 1)
        p = np.column_stack([big_r * np.cos(th), big_r * np.sin(th), np.full(n + 1, 1e-3)])
        v = p[1:] - p[:-1]
        sl = np.linalg.norm(v, axis=1)
        m = pm._seg_matrix(p[:-1], v / sl[:, None], sl, p[:-1], v / sl[:, None], np.zeros(n, int), np.full(n, a))
        m[np.diag_indices(n)] = filament_mutual_parallel(sl, sl, a, 0.0)
        err.append(m.sum() / exact - 1)
    assert abs(err[0]) < 0.01 and abs(err[1]) < abs(err[0]) and abs(err[2]) < 0.002


@pytest.mark.parametrize("nseg", [2, 4, 8])
def test_collinear_segments_reproduce_grover_whole_wire(nseg):
    # exact limit: a straight wire cut into nseg pieces has the self inductance of the whole wire
    # (Grover 1946 ch. 2, surface-current tube), here with a / l_seg = 0.1 .. 0.4
    length, a = 4e-3, 0.15e-3
    sl = np.full(nseg, length / nseg)
    sp = np.column_stack([np.arange(nseg) * sl, np.zeros(nseg), np.full(nseg, 2e-3)])
    su = np.tile([1.0, 0.0, 0.0], (nseg, 1))
    wid, rad = np.zeros(nseg, int), np.full(nseg, a)
    ms = pm._seg_matrix(sp, su, sl, sp, su, wid, rad)
    ms[np.diag_indices(nseg)] = filament_mutual_parallel(sl, sl, a, 0.0)  # Grover tube self, as in assemble
    whole = filament_mutual_parallel(length, length, a, 0.0)
    assert ms.sum() == pytest.approx(whole, rel=0.01)


# ---- trace-cell current layer (internal inductance) -----------------------------------------------
def test_bar_current_layer_is_the_skin_layer_on_the_plane_facing_side(layouts):
    lay = layouts[0]
    f = np.array([5e6, 2e7, 8e7])
    r = loop_inductance(lay, f)
    sig = lay.stack.layer("top_cu").sigma
    assert np.allclose(r.meta["bar_layer_thickness_m"], skin_depth(f, sig), rtol=1e-12)
    # low frequency: the layer saturates at the Cu thickness (uniform current)
    t_cu = lay.top_cu_z()[1] - lay.top_cu_z()[0]
    assert loop_inductance(lay, [1e3]).meta["bar_layer_thickness_m"][0] == pytest.approx(t_cu)


def test_hf_layer_removes_dc_internal_inductance_and_plane_offset(layouts):
    # uniform current through the full thickness (T0023 model) carries the DC internal inductance and sits
    # t/2 above the plane-facing face; the skin-layer model is lower by ~5 .. 12 % (module docstring)
    lay = layouts[0]
    f = [2e7]
    skin, uni = loop_inductance(lay, f).L_H[0], loop_inductance(lay, f, uniform_bars=True).L_H[0]
    assert 0.03 < 1 - skin / uni < 0.15


def test_bar_branches_stop_at_die_footprint_edges(layouts):
    # a bar that ends in a die footprint (one equipotential node) must not reach into the footprint
    lay = layouts[0]
    d = pm._discretize(lay, pm.DEFAULT_HMAX)
    for die in lay.dies:
        x0, y0, x1, y1 = die.bounds
        for c, dd, ax in ((d.cx, d.ddx, 0), (d.cy, d.ddy, 1)):
            lo, hi = c[:, ax] - dd[:, ax] / 2, c[:, ax] + dd[:, ax] / 2
            ot = 1 - ax
            inside_t = (c[:, ot] > (y0, x0)[ax] + 1e-9) & (c[:, ot] < (y1, x1)[ax] - 1e-9)
            lo_f, hi_f = ((x0, x1), (y0, y1))[ax]
            overlap = np.minimum(hi, hi_f) - np.maximum(lo, lo_f)
            assert not np.any(inside_t & (overlap > 1e-9))


def test_centred_cell_lines():
    # isolated values get a cell of size 2*half centred on them; values closer than 2*half form one group whose
    # cell is centred on the group; a neighbouring group limits the half-width to half the gap
    lines = np.sort(pm._centred_cell_lines([0.0, 1.0, 1.5, 10.0], 0.5))
    assert lines == pytest.approx([-0.5, 2.0, 9.5, 10.5])  # 0 / 1 / 1.5 are one group (gaps <= 1.0)
    assert np.sort(pm._centred_cell_lines([0.0, 1.2], 0.5)) == pytest.approx([-0.5, 0.5, 0.7, 1.7])
    assert np.sort(pm._centred_cell_lines([0.0, 1.0], 0.25)) == pytest.approx([-0.25, 0.25, 0.75, 1.25])


@pytest.mark.parametrize("hmax", [4e-3, 1e-3])
def test_attachment_points_sit_at_their_cell_centres(layouts, hmax):
    # wire feet and port terminals enter where the cell's bars meet (no implicit short across a cell)
    lay = layouts[0]
    grids = {g.net: g for g in pm._mesh_traces(lay, hmax)[0]}
    pts = [(w.net, w.points[-1, :2], w) for w in lay.wires]
    pts += [(n, np.array([lay.terminals[n].cx, lay.terminals[n].cy]), None) for n in ("DC+", "DC-")]
    feet_per_cell = {}
    for net, (x, y), w in pts:
        g = grids[net]
        j, i = pm._locate(g.xs, g.ys, np.array([x]), np.array([y]))
        cx, cy = g.xc[i[0]], g.yc[j[0]]
        if w is not None:
            feet_per_cell.setdefault((net, i[0], j[0]), []).append((x, y))
        else:
            assert (cx, cy) == pytest.approx((x, y), abs=1e-9)
    for (net, i, j), feet in feet_per_cell.items():  # one foot, or a group of close feet centred in the cell
        g = grids[net]
        assert (g.xc[i], g.yc[j]) == pytest.approx(tuple(0.5 * (np.min(feet, 0) + np.max(feet, 0))), abs=1e-9)
        if hmax <= 1e-3:  # 1 mm mesh: every foot (1 mm pitch) is its own node
            assert len(feet) == 1


def test_edge_lanes_capture_strip_edge_crowding():
    # straight 8 mm strip, 0.38 mm over the image plane, HF layer: lanes in parallel between common end nodes.
    # Reference = 48 cosine-graded lanes (independent fine discretisation of the same kernel)
    d, g, w, ln = skin_depth(2e7, 5.8e7), 0.38e-3, 8e-3, 40e-3

    def strip(edges):
        yc, wy = 0.5 * (edges[1:] + edges[:-1]), np.diff(edges)
        c = np.column_stack([np.full_like(yc, ln / 2), yc, np.full_like(yc, g + d / 2)])
        dd = np.column_stack([np.full_like(yc, ln), wy, np.full_like(yc, d)])
        m = pm._bar_block(c, dd, 0, [(None, 1.0, pm._NEAR), (0.0, -1.0, pm._NEAR_IMG)])
        return 1 / np.sum(np.linalg.inv(m))

    ref = strip(w / 2 * (1 - np.cos(np.linspace(0, np.pi, 49))))
    cells = np.array([0.0, w / 2, w])  # 4 mm cells
    c = np.column_stack([np.full(2, ln / 2), 0.5 * (cells[1:] + cells[:-1]), np.full(2, g + d / 2)])
    dd = np.column_stack([np.full(2, ln), np.diff(cells), np.full(2, d)])
    lane = pm.EDGE_LANE_FRAC * g
    lc, ldd, n1, _ = pm._edge_lanes(c, dd, np.arange(2), np.arange(2), np.array([True, False]),
                                    np.array([False, True]), lane, 1)
    assert ldd[:, 1].sum() == pytest.approx(w) and len(lc) == 4 and sorted(n1) == [0, 0, 1, 1]
    lanes_edges = np.sort(np.concatenate([lc[:, 1] - ldd[:, 1] / 2, [w]]))
    plain, laned = strip(cells), strip(lanes_edges)
    assert 0.02 < plain / ref - 1 < 0.035  # cell-wide bars miss the edge crowding (module docstring: +2.7 %)
    assert 0.0 < laned / ref - 1 < 0.01


def test_edge_lanes_option_lowers_loop_inductance_by_documented_amount(layouts):
    lay = layouts[0]
    base, laned = (loop_inductance(lay, [2e7], edge_lanes=e).L_H[0] for e in (False, True))
    assert 0.005 < 1 - laned / base < 0.025


def test_mesh_analysis_equals_nodal_analysis(layouts):
    lay = layouts[1]
    d = pm._discretize(lay, pm.DEFAULT_HMAX)
    X = 2 * np.pi * 2e7 * d.assemble(planes=[(lay.stack.z_top("backside_cu"), 1.0)])
    n1, n2 = np.concatenate([d.bn1, d.wn1]), np.concatenate([d.bn2, d.wn2])
    _, inv = np.unique(np.concatenate([n1, n2, [d.pos_node, d.neg_node]]), return_inverse=True)
    nk, nn = n1.size, inv.max() + 1
    r = np.random.default_rng(0).uniform(1e-4, 1e-3, nk)
    z_mesh = pm._mesh_port_impedance(X, r, inv[:nk], inv[nk:2 * nk], nn, inv[-2], inv[-1])
    A = pm._incidence(inv[:nk], inv[nk:2 * nk], nn)
    Y = A.T @ np.linalg.solve(1j * X + np.diag(r), A)
    keep = np.arange(nn) != inv[-1]
    s = np.zeros(nn)
    s[inv[-2]] = 1.0
    v = np.linalg.solve(Y[np.ix_(keep, keep)], s[keep])
    assert z_mesh == pytest.approx(v[inv[-2] - (inv[-2] > inv[-1])], rel=1e-9)


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
