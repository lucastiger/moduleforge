"""Multi-port Z, sign convention, ties, mesh_meta and GMRES bookkeeping of l2 (T0071).

Closed forms: two coupled branches V = Z I with Z = [[Z11, Z12], [Z12, Z22]] (reciprocal); a tie of both ends of two
branches is the parallel connection Z_par = (Z11 Z22 - Z12^2) / (Z11 + Z22 - 2 Z12) (two-port algebra: impose V1 = V2 and
I = I1 + I2, V = Z_par I).  Sign: I_j enters at plus_j, so the mutual of two parallel same-direction branches is
+jwM, M > 0 [Grover ch. 3]; reversing one port flips the sign of Z12.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from moduleforge.solvers import l2, l2_core as core

SIG_CU, SIG_AL = 5.8e7, 3.77e7
MM = 1e-3


def bar(name, x0, x1, y, z, w=3.0, t=0.3):
    return l2.Bar(name, (x0 * MM, y * MM, z * MM), (x1 * MM, y * MM, z * MM), w * MM, t * MM, SIG_CU)


def port(name, c, rev=False):
    a, b = (1, 0) if rev else (0, 1)
    return l2.Port(name, l2.Terminal(c, a), l2.Terminal(c, b))


def three_bars():
    return [bar("a", 0, 20, 0, 0), bar("b", 0, 20, 4, 0), bar("c", 5, 18, 1.5, 1.0, 2.0)]


@pytest.mark.parametrize("f", [100.0, 20e6])
def test_sign_convention_and_positive_mutual(f):
    bs = three_bars()
    r = l2.solve(bs, [], [port("p1", "a"), port("p2", "b"), port("p3", "c")], [f], 2)
    w = 2 * math.pi * f
    z = r.z[0]
    assert np.all(np.diag(z).imag > 0)
    assert z[0, 1].imag > 0 and z[0, 2].imag > 0 and z[1, 2].imag > 0  # parallel, same direction
    assert np.all(np.diag(z).real > 0)
    # reversing port 2 flips every term of row/column 2 and leaves the rest
    r2 = l2.solve(bs, [], [port("p1", "a"), port("p2", "b", rev=True), port("p3", "c")], [f], 2)
    z2 = r2.z[0]
    assert z2[0, 1] == pytest.approx(-z[0, 1], rel=1e-9)
    assert z2[1, 2] == pytest.approx(-z[1, 2], rel=1e-9)
    assert z2[1, 1] == pytest.approx(z[1, 1], rel=1e-9)
    assert z2[0, 2] == pytest.approx(z[0, 2], rel=1e-9)
    assert z[0, 1].imag / w < z[0, 0].imag / w  # |M| < L for separated bars


def test_reciprocity_with_every_port_column():
    bs = three_bars()
    r = l2.solve(bs, [], [port("p1", "a"), port("p2", "b"), port("p3", "c", rev=True)], [100.0, 5e6, 80e6], 2)
    for k in range(3):
        z = r.z[k]
        assert np.max(np.abs(z - z.T)) <= 1e-9 * np.max(np.abs(z))
    assert r.z.shape == (3, 3, 3)
    assert r.meta["solver_tol"] < 1e-6


def test_tie_assembly_vs_explicit_parallel_formula():
    """Ties at both ends of bars a and b = parallel connection of the two-port: (Z11 Z22 - Z12^2) / (Z11 + Z22 - 2 Z12)."""
    a, b = bar("a", 0, 20, 0, 0), bar("b", 0, 20, 4, 0)
    for f in (100.0, 20e6):
        two = l2.solve([a, b], [], [port("p1", "a"), port("p2", "b")], [f], 2).z[0]
        zp = (two[0, 0] * two[1, 1] - two[0, 1] ** 2) / (two[0, 0] + two[1, 1] - 2 * two[0, 1])
        ties = [l2.Tie(l2.Terminal("a", 0), l2.Terminal("b", 0)), l2.Tie(l2.Terminal("a", 1), l2.Terminal("b", 1))]
        tied = l2.solve([a, b], [], [port("p", "a")], [f], 2, ties=ties)
        assert tied.z[0, 0, 0] == pytest.approx(zp, rel=1e-9)


def test_tie_is_zero_impedance_series_connection():
    """Tie of the end of bar a to the start of bar b: a series connection, Z = Z11 + Z22 + 2 Z12 for the port across the
    free ends (current enters a at 0, leaves b at its far end)."""
    a, b = bar("a", 0, 10, 0, 0), bar("b", 10, 20, 0, 0)
    two = l2.solve([a, b], [], [port("p1", "a"), port("p2", "b")], [100.0], 2).z[0]
    ser = l2.Port("s", l2.Terminal("a", 0), l2.Terminal("b", 1))
    tie = l2.Tie(l2.Terminal("a", 1), l2.Terminal("b", 0))
    z = l2.solve([a, b], [], [ser], [100.0], 2, ties=[tie]).z[0, 0, 0]
    assert z == pytest.approx(two[0, 0] + two[1, 1] + 2 * two[0, 1], rel=1e-9)


def test_disconnected_port_is_refused():
    a, b = bar("a", 0, 10, 0, 0), bar("b", 0, 10, 4, 0)
    bad = l2.Port("p", l2.Terminal("a", 0), l2.Terminal("b", 1))
    with pytest.raises(ValueError):
        l2.solve([a, b], [], [bad], [100.0], 1)


# ------------------------------------------------------------------------------------------ meta bookkeeping
@pytest.fixture
def tiny(monkeypatch):
    monkeypatch.setitem(core.COUNTS, 1, 3)
    monkeypatch.setitem(core.SEGMENTS, 1, 4)
    monkeypatch.setitem(core.LAYERS, 1, 2)


def wire_plane_case():
    um = 1e-3
    w = l2.RoundWire("loop", tuple((x * um, y * um, 0.5 * um) for x, y in ((0, 0), (2, 0), (2, 1), (0, 1), (0, 0))),
                     0.3 * um, SIG_AL)
    pl = l2.Plane("gnd", -1e-3, -1e-3, 3e-3, 2e-3, 0.0, 0.1e-3, SIG_CU)
    return [w], [pl], [l2.Port("p", l2.Terminal("loop", 0), l2.Terminal("loop", 4))]


def test_mesh_meta_equals_solve_meta_wires_plane(tiny):
    c, p, po = wire_plane_case()
    freqs = [5e6, 20e6]
    r = l2.solve(c, p, po, freqs, 1)
    m = l2.mesh_meta(c, p, po, freqs, 1)
    for k in ("mesh_params", "n_filaments", "mesh_hash"):
        assert m[k] == r.meta[k], k
    assert len(m["mesh_hash"]) == len(freqs) and len(set(m["mesh_hash"])) == 1
    assert "gmres_info" in r.meta and all(i == 0 for row in r.meta["gmres_info"] for i in row)


def test_mesh_meta_equals_solve_meta_bars():
    bs = three_bars()
    po = [port("p1", "a"), port("p2", "b")]
    for k in (1, 2):
        r = l2.solve(bs, [], po, [100.0, 20e6], k)
        m = l2.mesh_meta(bs, [], po, [100.0, 20e6], k)
        for key in ("mesh_params", "n_filaments", "mesh_hash"):
            assert m[key] == r.meta[key]


def test_mesh_params_are_real_sizes_with_one_refinement_ratio():
    """R1/R2: wires + plane, graded to 80 MHz: every real mesh size refines by a ratio inside the runner's spread (1.1)."""
    c, p, _ = wire_plane_case()
    po = [l2.Port("p", l2.Terminal("loop", 0), l2.Terminal("loop", 4))]
    ms = [l2.mesh_meta(c, p, po, [5e6, 20e6, 80e6], k) for k in (1, 2, 3, 4)]
    keys = [k for k in ms[0]["mesh_params"] if not k.startswith(("nx", "ny"))]
    assert keys
    for k0, k1 in zip(ms[:-1], ms[1:], strict=True):
        ratios = [k0["mesh_params"][k] / k1["mesh_params"][k] for k in keys if k0["mesh_params"][k] > 0]
        assert min(ratios) > 1.0
        assert max(ratios) / min(ratios) <= 1.1 + 1e-12, dict(zip(keys, ratios, strict=True))
    # bars: sizes strictly shrink, hash changes with the level
    bs = three_bars()
    b1 = l2.mesh_meta(bs, [], [], [100.0, 80e6], 1)
    b2 = l2.mesh_meta(bs, [], [], [100.0, 80e6], 2)
    assert b1["mesh_hash"] != b2["mesh_hash"]
    assert all(b2["mesh_params"][k] < b1["mesh_params"][k] for k in b1["mesh_params"])


def test_solver_tol_covers_gmres_vs_dense_lu(tiny):
    """The reported solver_tol bounds |Z_gmres - Z_dense| / |Z| for a plane problem solved both ways."""
    c, p, po = wire_plane_case()
    specs = [core.WireSpec("loop", np.asarray(c[0].points, float), c[0].diameter, c[0].sigma)]
    pl = core.PlaneSpec("gnd", p[0].x_min, p[0].y_min, p[0].x_max, p[0].y_max, p[0].z_top, p[0].thickness, p[0].sigma)
    pts = [((0, 0), (0, 4))]
    dense, _ = core.solve_case(specs, pl, pts, [2e7], 1, dense=True)
    it, meta = core.solve_case(specs, pl, pts, [2e7], 1, gmres_tol=1e-9, dense=False)
    zref = abs(dense.z[0, 0, 0])
    assert abs(it.z[0, 0, 0] - dense.z[0, 0, 0]) / zref <= meta["solver_tol"]
    assert meta["gmres_info"] == [[0]]
