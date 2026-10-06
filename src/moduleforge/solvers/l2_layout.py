"""L2 layout path: Layout -> loop inductance of the finite-radius conductor model, precorrected-FFT wire <-> grid operator.

Model (SI, float64; quasi-static PEEC; skin / proximity effect through thickness layers and wire filaments; no image planes):

* Top-Cu traces, backside Cu and baseplate are three *slabs* on ONE shared lateral grid (cell-centred nodes, x- and
  y-branches).  A slab is a mask of that grid (traces: cells whose centre is inside a trace rectangle, labelled by net;
  backside / baseplate at their true extent) with graded thickness layers.  Every Cu-to-Cu block is block-Toeplitz and is
  applied by FFT with ``l2_core.plane_table`` / ``circulant_fft`` (Hoer-Love boxes near, Gauss beyond).
* A bond wire is a bundle of round filaments (centre disc + rings of WIRE_PHI sectors, each a round rod of its
  equivalent radius rho) along the wire polyline (mitred at the vertices).  Segment pairs use the closed-form Neumann
  integral of two straight filaments ([G], ``segment_mutual``).  Filaments of ONE wire are the mesh of its cross-section
  (thin-line mutuals, rod self term, joint correction: discretisation).  Filaments of DIFFERENT wires couple as
  finite-radius rods: centre line + ``rod_pair_correction`` (exact end-term identity for a harmonic kernel, [P]) with a
  stated remainder counted in solver_tol.
* Wire <-> grid: rod segment to branch box = line integral of the closed-form box potential [W] (composite Gauss) plus
  the finite-radius end correction ``rod_box_correction`` (stated remainder counted) for every branch within
  ``PFFT_NEAR`` cells of the wire; beyond, a precorrected FFT (``WireGridPFFT``): branch potentials on a virtual lattice
  (the shared grid laterally, z-levels of PFFT_DZ_CELLS cells) by the grid's FFT machinery, tensor-Lagrange
  interpolated to nodes = Gauss points x a degree-3 disc rule over each filament section; the near part of that
  projection is replaced by the exact values.  This operator is new here (``l2_core.wire_plane_op`` needs axis-parallel
  segments matching the lattice); its tests compare it with the dense exact coupling ``WireGridDense``.
  Memory and time ~ O(wires x near box + grid log grid).
* Dies are ideal shorts (node merge); port of ``Layout.to_conductors()``, port cells restricted to the DC+ / DC- nets.
* Solve: GMRES (``l2_core.block_gmres``, block preconditioner; small systems: dense direct) and the rigorous
  a-posteriori bound of ``l2_core.a_posteriori``.
* ``meta['solver_tol']`` (D0004 (i)) = a-posteriori + rounding + STATED bounds (derived, not measured), each applied
  to the block it bounds (``LayoutSystem.stated_parts``): plane tables; wire <-> grid operator (interpolation, Gauss,
  far disc rule); finite-radius remainders of near wire <-> grid and inter-wire pairs; rod-series truncation.
  The test layout reports ~5e-5 (refinement 0) and ~1e-4 (refinement 1); the DoD layout ~2e-5;
  ``test_solver_tol_usable_at_every_refinement`` checks < 1e-3 at refinements 0-4.

NOT in solver_tol (discretisation and model choices, D0004; convergence is gated by T0075):
* Mesh (CELL, LAYERS_*, WIRE_EDGES).  Refinement-0 values are NOT accurate.  24 x 14 mm test layout, 20 MHz: L = 6.257 /
  5.746 / 5.567 nH at refinement 0 / 1 / 2 (geometric extrapolation ~5.47 nH: refinement 0 ~14 % high, 2 ~2 %).
  DoD layout (seed 7, 2 dies/switch), 20 MHz: L = 11.649 nH at refinement 0, 11.279 nH at refinement 1 (-3.2 %).  R converges more slowly than L.
* Grading frequency: layers are graded to the skin depth at max(F_MESH, max(freqs)), F_MESH = 100 MHz, so L(f) does
  not depend on which other frequencies are requested (<= 100 MHz).  The grading is itself a mesh choice: attempt 1
  graded to max(freqs), and L(20 MHz) of the DoD layout moved 2.6 % between grading at 20 and at 80 MHz (review T0082).
* Landing clamp: filament vertices stay >= LANDING_GAP x diameter above the top Cu (the foot joins its landing cell by a
  node merge).  DoD layout, refinement 0, 20 MHz: L = 11.654 / 11.649 / 11.645 nH for LANDING_GAP = 0.25 / 0.5 / 1.0
  (+-0.04 %); at 0.25 the thickest filament's end disc reaches the copper and the finite-radius bound becomes infinite.
* Ideal die shorts: footprint cells and wire start nodes are one node, so the 0.23 mm path through attach + die has
  zero impedance; as a solid 5.2 x 5.2 x 0.23 mm block its partial self inductance is 0.003 nH per die [HL] (~0.03 %
  of L).  The equipotential footprint (lateral short under the die) is a model assumption and is not bounded.

Cost, seed 7, refinement 0, one frequency (10-core laptop): 2 dies/switch 56,712 unknowns, wall 33 s, CPU 33 s, peak RSS 0.73 GB,
120 GMRES iterations, L(20 MHz) = 11.649 nH; 6 dies/switch 56,880 unknowns, wall 74 s, CPU 72 s, peak RSS 0.98 GB, 125
iterations, 8.405 nH.  The DoD call (2 dies, 5 / 20 / 80 MHz) takes ~40 s.

References: [G] Grover, Inductance Calculations (1946) ch. 7 (filament Neumann integrals, line potential); [HL] Hoer & Love,
J. Res. NBS 69C (1965) 127; [MW] Maxwell / Weaver (round rod); [W] Waldvogel, ZAMP 27 (1976) 867 and Nagaoka (1911)
(potential of a uniform prism / rectangle); [P] Pizzetti's mean-value expansion (Courant-Hilbert vol. II ch. IV);
[AT] Trefethen, Approximation Theory and Approximation Practice (2013) Thm 19.3.
"""
# ruff: noqa: E741  (l = layer index, I = line integral: names follow the formulas cited above)
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import connected_components

from moduleforge.geometry import DC_MINUS, DC_PLUS
from moduleforge.solvers import l2_core as core

TOOL_NAME = "moduleforge-l2-layout"
TOOL_VERSION = "0.2.0"
MU0 = core.MU0
K4 = core.K4
PARALLEL_SIN = 1e-6  # |sin(angle)| below this: treat two segments as parallel (error O(sin) in the geometry)
MAX_REFINEMENT = 4

# per refinement 0..4: lateral cell [m]; thickness layers of top Cu / backside / baseplate; wire annulus edges (units of r)
CELL = (1.0e-3, 0.7e-3, 0.5e-3, 0.35e-3, 0.25e-3)
LAYERS_TOP = (4, 6, 8, 10, 12)
LAYERS_BACK = (3, 4, 5, 6, 7)
LAYERS_BASE = (3, 4, 5, 6, 7)
WIRE_EDGES = ((0, .6, 1), (0, .5, .8, 1), (0, .4, .7, .9, 1), (0, .35, .6, .8, .93, 1), (0, .3, .5, .7, .85, .95, 1))
WIRE_PHI = 6  # filaments per ring
LANDING_GAP = 0.5  # wire filaments are kept >= LANDING_GAP * diameter above the top-Cu surface (modelling clamp)
PFFT_NEAR = 18  # cells: branches within this Chebyshev distance of a wire are coupled exactly
PFFT_STENCIL = 8  # lateral Lagrange points per axis
PFFT_STENCIL_Z = 4
PFFT_DZ = 0.4e-3  # virtual z-level spacing (cap)
PFFT_DZ_CELLS = 0.4  # virtual z-level spacing in lateral cells
LINE_TOL = 1e-13  # target of the composite Gauss rule along a segment (stated bound, not measured)
UNIT_ROUNDOFF = core.UNIT_ROUNDOFF
F_MESH = 1.0e8  # Hz: thickness layers are graded to the skin depth at max(F_MESH, max(freqs)) (frequency-list independent)


# ---------------------------------------------------------------------------------------------- filament mutual
def _phi(S, T, c, h, h2, sg, sg2):
    """Antiderivative of 1/R with d^2/(dS dT) = 1/R, R^2 = S^2 + T^2 - 2 c S T + h^2 (Grover 1946 ch. 7, Neumann integral
    of two straight filaments; S, T measured from the closest-approach points, h the line distance, c = cos eps):
    Phi = S ln(R + T - cS) + T ln(R + S - cT) - (h / sin eps) atan[(h^2 c + S T sin^2 eps) / (h R sin eps)]."""
    R = np.sqrt(np.maximum(S * S + T * T - 2 * c * S * T + h2, 0.0))
    gt, gs = T - c * S, S - c * T
    # R + g computed without cancellation when g < 0: (R - g)(R + g) = R^2 - g^2
    a = np.where(gt >= 0, R + gt, (S * S * sg2 + h2) / np.maximum(R - gt, 1e-300))
    b = np.where(gs >= 0, R + gs, (T * T * sg2 + h2) / np.maximum(R - gs, 1e-300))
    la = np.where(S == 0, 0.0, S * np.log(np.maximum(a, 1e-300)))
    lb = np.where(T == 0, 0.0, T * np.log(np.maximum(b, 1e-300)))
    den = np.where(h > 0, h * R * sg, 1.0)
    at = np.where(h > 0, h / sg * np.arctan((h2 * c + S * T * sg2) / den), 0.0)
    return la + lb - at


def segment_mutual(p0, p1, q0, q1):
    """Mutual partial inductance (H) of two straight filaments p0->p1 and q0->q1 (broadcasting (..., 3) arrays) carrying
    unit current in the direction of travel: K4 cos(eps) int int ds dt / R  (Neumann).  Non-parallel: closed form of
    Grover (1946); sin(eps) < PARALLEL_SIN: the parallel-filament form (``core.fil_F``), which also covers collinear
    filaments.  Touching filaments (shared end point) are finite and handled."""
    p0, p1, q0, q1 = (np.asarray(v, dtype=np.float64) for v in (p0, p1, q0, q1))
    u, v, d = p1 - p0, q1 - q0, q0 - p0
    l1, l2 = np.linalg.norm(u, axis=-1), np.linalg.norm(v, axis=-1)
    u, v = u / l1[..., None], v / l2[..., None]
    c = np.sum(u * v, axis=-1)
    sg2 = 1.0 - c * c
    par = sg2 < PARALLEL_SIN ** 2
    sg2s = np.where(par, 1.0, sg2)
    sg = np.sqrt(sg2s)
    p = -np.sum(d * u, axis=-1)
    q = np.sum(d * v, axis=-1)
    w = np.sum(d * d, axis=-1)
    s0 = -(p + c * q) / sg2s
    t0 = -(q + c * p) / sg2s
    h2 = np.maximum(w + p * s0 + q * t0, 0.0)
    h2 = np.where(h2 < 1e-24 * np.maximum(w, 1e-300) + 1e-40, 0.0, h2)  # exact touching (round-off level)
    h = np.sqrt(h2)
    S1, S2, T1, T2 = -s0, l1 - s0, -t0, l2 - t0
    gen = np.zeros_like(c)
    if not np.all(par):
        f = lambda S, T: _phi(S, T, c, h, h2, sg, sg2s)  # noqa: E731
        gen = f(S2, T2) - f(S1, T2) - f(S2, T1) + f(S1, T1)
    e0 = np.sum(d * u, axis=-1)
    dperp = np.linalg.norm(d - e0[..., None] * u, axis=-1)
    dperp = np.maximum(dperp, 1e-9 * np.maximum(l1, l2))
    b1 = np.where(c > 0, e0, e0 - l2)
    b2 = b1 + l2
    parv = core.fil_F(0.0, l1, b1, b2, dperp)
    return K4 * c * np.where(par, parv, gen)


def rod_self(length, rho):
    """Self partial inductance of a straight round rod (uniform current), length >> rho: with F(d) = 2 [l asinh(l/d) -
    sqrt(l^2 + d^2) + d] the filament mutual of two parallel full-length filaments at distance d [Grover 1946 ch. 7]
    and its series F/2 = l (ln(2l/d) - 1) + d - d^2/(4 l) + d^4/(32 l^3) - d^6/(96 l^5) + ..., averaged over two uniform
    points of a disc (<ln d> = ln rho - 1/4, <d> = 128 rho / (45 pi), <d^2> = rho^2, <d^4> = 5 rho^4 / 3):
    mu0/(2 pi) [l (ln(2l/rho) - 3/4) + <d> - rho^2/(4 l) + 5 rho^4/(96 l^3)] (Maxwell / Weaver form plus the d^4 term)."""
    length, rho = np.asarray(length, float), np.asarray(rho, float)
    return MU0 / (2 * math.pi) * (length * (np.log(2 * length / rho) - 0.75) + 128 * rho / (45 * math.pi)
                                  - rho * rho / (4 * length) + 5 * rho ** 4 / (96 * length ** 3))


def rod_self_bound(length, rho):
    """Stated absolute bound (H) of the truncation of ``rod_self``: the first omitted term is d^6/(96 l^5) with d <= 2 rho,
    the following terms shrink by (d/l)^2 <= (2 rho/l)^2 (inf if that is >= 1)."""
    length, rho = np.asarray(length, float), np.asarray(rho, float)
    q2 = (2 * rho / length) ** 2
    geo = np.where(q2 < 1.0, 1.0 / np.maximum(1.0 - q2, 1e-300), np.inf)
    return MU0 / (2 * math.pi) * (2 * rho) ** 6 / (96.0 * length ** 5) * geo


def joint_correction(rho, cos_joint):
    """Finite-section correction of the mutual of two consecutive segments of one filament: the rod of length l1 + l2 has
    ONE mean-distance term <d> = 128 rho / (45 pi) in its self inductance, the two segment self terms carry two, so the
    thin-filament mutual of the pair is reduced by mu0/(4 pi) <d> cos (exact for collinear segments)."""
    return K4 * 128.0 * np.asarray(rho) / (45.0 * math.pi) * cos_joint


def segment_distance(p0, p1, q0, q1):
    """Minimum distance of segments p0-p1 and q0-q1 (broadcasting (..., 3) arrays; closest points of two segments,
    Ericson, Real-Time Collision Detection 5.1.9)."""
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e = np.sum(d1 * d1, -1), np.sum(d2 * d2, -1)
    b, c, f = np.sum(d1 * d2, -1), np.sum(d1 * r, -1), np.sum(d2 * r, -1)
    den = a * e - b * b
    ok = den > 1e-12 * a * e
    s = np.where(ok, np.clip((b * f - c * e) / np.where(ok, den, 1.0), 0.0, 1.0), 0.0)
    t = (b * s + f) / e
    s = np.where(t < 0, np.clip(-c / a, 0, 1), np.where(t > 1, np.clip((b - c) / a, 0, 1), s))
    t = np.clip(t, 0.0, 1.0)
    return np.linalg.norm(p0 + s[..., None] * d1 - q0 - t[..., None] * d2, axis=-1)


# ---------------------------------------------------------------------------------------------- finite radius
def line_pot_grad(x, q0, q1):
    """Gradient of the line potential psi(x) = int dt / |x - q(t)| = ln((R1 + R2 + l) / (R1 + R2 - l)) of the straight
    segment q0 -> q1 [G] ch. 7 (broadcasting (..., 3)): grad psi = -2 l / ((R1 + R2)^2 - l^2) ((x - q0)/R1 + (x - q1)/R2)."""
    d0, d1 = x - q0, x - q1
    r1, r2 = np.linalg.norm(d0, axis=-1), np.linalg.norm(d1, axis=-1)
    ln = np.linalg.norm(q1 - q0, axis=-1)
    sm = r1 + r2
    fac = -2.0 * ln / np.maximum((sm - ln) * (sm + ln), 1e-300)
    return fac[..., None] * (d0 / r1[..., None] + d1 / r2[..., None])


def rod_pair_correction(p0, p1, a, q0, q1, b):
    """Finite-radius correction of the mutual of two straight round rods (radii a, b, uniform current, end discs normal to
    the axes) relative to the centre-line Neumann integral ``segment_mutual`` (broadcasting).

    Identity (1/R harmonic off the source): the mean over a disc of radius a normal to u of a harmonic f is
    f(0) + int_disc W Delta_perp f, W(r) = (a^2 ln(a/r) / 2 - a^2/4 + r^2/4) / (pi a^2) >= 0, int W = a^2/8 (Pizzetti), and
    Delta_perp f = -d_u^2 f, so along a straight rod only end terms survive: int ds M_a f = int ds f - int_disc W [d_u f]_ends.
    Applied to both rods: M = K4 (u.v) [N - (a^2/8) [u.grad psi_q]_{p0}^{p1} - (b^2/8) [v.grad psi_p]_{q0}^{q1} + E], psi the line
    potentials (``line_pot_grad``).  Stated remainder, from |d_u^n (1/r)| <= n!/r^(n+1) (Legendre), |u^T grad grad(1/r) v| <=
    2/r^3, the circle-mean bound |m(rho) - f(0)| <= rho^2/4 sup|Delta_perp f| (so the second-order weight is a^4/192) and
    D = gap between the two cylinders: |E| <= a^4/16 min(l_q/D^4, pi/(2D^3)) + b^4/16 min(l_p/D^4, pi/(2D^3)) + a^2 b^2/(8D^3).
    Returns (correction (H), remainder bound (H)); D <= 0 (touching cylinders) gives an infinite bound."""
    p0, p1, q0, q1 = (np.asarray(v, dtype=np.float64) for v in (p0, p1, q0, q1))
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(all="ignore"):
        u, v = p1 - p0, q1 - q0
        lp, lq = np.linalg.norm(u, axis=-1), np.linalg.norm(v, axis=-1)
        u, v = u / lp[..., None], v / lq[..., None]
        c = np.sum(u * v, axis=-1)
        ga = np.sum(u * (line_pot_grad(p1, q0, q1) - line_pot_grad(p0, q0, q1)), axis=-1)
        gb = np.sum(v * (line_pot_grad(q1, p0, p1) - line_pot_grad(q0, p0, p1)), axis=-1)
        corr = -K4 * c * (a * a / 8.0 * ga + b * b / 8.0 * gb)
        gap = segment_distance(p0, p1, q0, q1) - a - b
        g = np.where(gap > 0, gap, 1.0)
        tail = (np.minimum(lq / g ** 4, 0.5 * math.pi / g ** 3) * a ** 4 / 16.0
                + np.minimum(lp / g ** 4, 0.5 * math.pi / g ** 3) * b ** 4 / 16.0 + a * a * b * b / (8.0 * g ** 3))
        rem = np.where(gap > 0, K4 * np.abs(c) * tail, np.inf)
    return corr, rem


# ---------------------------------------------------------------------------------------------- box potential
def _G(x, y, z):
    """Triple antiderivative of 1/R (d^3 G / dx dy dz = 1/R) of the uniform rectangular prism [W]:
    G = xy ln(z+R) + yz ln(x+R) + zx ln(y+R) - x^2/2 atan(yz/(xR)) - y^2/2 atan(xz/(yR)) - z^2/2 atan(xy/(zR))."""
    r = np.sqrt(x * x + y * y + z * z)

    def lg(a, b, c, rr):  # ln(c + R) with c the variable, a, b the other two
        rest = a * a + b * b
        arg = np.where(c >= 0, c + rr, rest / np.maximum(rr - c, 1e-300))
        return np.log(np.maximum(arg, 1e-300))

    def at(a, b, c):  # a^2/2 atan(bc/(aR))
        den = a * r
        safe = np.where(den != 0, den, 1.0)
        return np.where(den != 0, 0.5 * a * a * np.arctan(b * c / safe), 0.0)

    return x * y * lg(x, y, z, r) + y * z * lg(y, z, x, r) + z * x * lg(z, x, y, r) - at(x, y, z) - at(y, x, z) - at(z, x, y)


def box_potential(px, py, pz, lo, hi):
    """int_box dV' / |p - r'| for the box lo..hi (arrays (..., 3), broadcasting with the point coordinates) [W]."""
    tot = 0.0
    for ia, ib, ic in np.ndindex(2, 2, 2):
        x = (hi if ia else lo)[..., 0] - px
        y = (hi if ib else lo)[..., 1] - py
        z = (hi if ic else lo)[..., 2] - pz
        tot = tot + (-1.0) ** (3 - ia - ib - ic) * _G(x, y, z)
    return tot


def _H(x, y, z):
    """Potential of a uniform rectangle, int int dy dz / R = y ln(z + R) + z ln(y + R) - x atan(yz/(xR)) [W] (x the normal
    offset); d/dx of the prism antiderivative ``_G`` up to terms that cancel in the corner sum."""
    r = np.sqrt(x * x + y * y + z * z)

    def lg(c, rest):
        return np.log(np.maximum(np.where(c >= 0, c + r, rest / np.maximum(r - c, 1e-300)), 1e-300))

    den = x * r
    at = np.where(den != 0, x * np.arctan(y * z / np.where(den != 0, den, 1.0)), 0.0)
    return y * lg(z, x * x + y * y) + z * lg(y, x * x + z * z) - at


def box_grad(px, py, pz, lo, hi):
    """grad_p int_box dV' / |p - r'| (closed form: minus the corner sum of ``_H``) as (..., 3)."""
    g = [0.0, 0.0, 0.0]
    for ia, ib, ic in np.ndindex(2, 2, 2):
        x = (hi if ia else lo)[..., 0] - px
        y = (hi if ib else lo)[..., 1] - py
        z = (hi if ic else lo)[..., 2] - pz
        s = (-1.0) ** (3 - ia - ib - ic)
        g[0] = g[0] - s * _H(x, y, z)
        g[1] = g[1] - s * _H(y, z, x)
        g[2] = g[2] - s * _H(z, x, y)
    return np.stack(np.broadcast_arrays(*g), axis=-1)


def rod_box_correction(p0, p1, a, lo, hi):
    """Finite-radius correction of int_seg ds M_a[phi] (rod of radius a on the axis p0 -> p1, phi = ``box_potential`` of the
    boxes lo..hi (nb, 3), harmonic in the rod) relative to the centre-line integral of ``line_box_integral``: by the identity
    of ``rod_pair_correction``, -(a^2/8) [u.grad phi]_{p0}^{p1} (``box_grad``); stated remainder (a^4/192) sum_ends sup_disc
    |d_u^3 phi| <= (a^4/32) sum_ends B with B >= int_box dV/r^4 for every point of the end disc: B = min(V/D^4, pi (1/h0 -
    1/h1)) (D = point-box distance - a; h0 = vertical gap - a, h1 = h0 + box height: the slab integral of 1/r^4).
    Returns (correction, remainder bound), both (nb,) in the units of the line integral (m^3); an end disc that reaches a
    box gives an infinite bound."""
    p0, p1, lo, hi = (np.asarray(v, float) for v in (p0, p1, lo, hi))
    u = (p1 - p0) / np.linalg.norm(p1 - p0)
    corr = -(a * a / 8.0) * (box_grad(*p1, lo, hi) @ u - box_grad(*p0, lo, hi) @ u)
    vol = np.prod(hi - lo, axis=-1)
    rem = np.zeros(lo.shape[0])
    with np.errstate(all="ignore"):
        for p in (p0, p1):
            dist = np.linalg.norm(np.maximum(np.maximum(lo - p, p - hi), 0.0), axis=-1) - a
            h0 = np.maximum(lo[:, 2] - p[2], p[2] - hi[:, 2]) - a
            h1 = h0 + (hi[:, 2] - lo[:, 2])
            dd = np.where(dist > 0, dist, 1.0)
            bb = vol / dd ** 4
            slab = math.pi * (1.0 / np.where(h0 > 0, h0, 1.0) - 1.0 / np.where(h0 > 0, h1, 2.0))
            bb = np.where(h0 > 0, np.minimum(bb, slab), bb)
            rem = rem + np.where(dist > 0, bb, np.inf)
    return corr, a ** 4 / 32.0 * rem


def _seg_dist_lb(a, b, lo, hi):
    """Lower bound of the distance of segment a-b to boxes lo..hi (nb, 3): gap of the axis-aligned bounding boxes."""
    smin, smax = np.minimum(a, b), np.maximum(a, b)
    gap = np.maximum(np.maximum(lo - smax, smin - hi), 0.0)
    return np.linalg.norm(gap, axis=-1)


def line_box_integral(a, b, lo, hi, tol: float = LINE_TOL, chunk: int = 4096):
    """I[k] = int_a^b ds int_box_k dV' / R  (box potential integrated along the straight segment a -> b), composite Gauss
    with an order and panel count chosen per distance class so that the stated Gauss bound [AT Thm 19.3, assumption
    ``core.ELLIPSE_M``] is <= tol.  Returns (I, bound, d_lb) with bound the largest stated relative bound used and d_lb the
    per-box lower bound of the distance to the segment."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    lo, hi = np.atleast_2d(lo), np.atleast_2d(hi)
    ell = float(np.linalg.norm(b - a))
    out = np.zeros(lo.shape[0])
    d_lb = _seg_dist_lb(a, b, lo, hi)
    if np.any(d_lb <= 1e-9 * ell):
        raise ValueError("wire segment touches or intersects a grid branch box")
    cls = np.floor(np.log2(d_lb / ell)).astype(int)
    bound = 0.0
    for k in np.unique(cls):
        idx = np.flatnonzero(cls == k)
        dmin = ell * 2.0 ** k
        panels = max(1, int(math.ceil(ell / (2.0 * dmin))))
        rho = 1.0 + dmin / (0.5 * ell / panels)
        n = core.gauss_order(rho, tol, nmin=4, nmax=60)
        bound = max(bound, core.gauss_bound(n, rho))
        xs, ws = [], []
        for pn in range(panels):
            x, w = core.gq(n, pn / panels, (pn + 1) / panels)
            xs.append(x)
            ws.append(w)
        xs, ws = np.concatenate(xs), np.concatenate(ws) * ell
        pts = a[None, :] + xs[:, None] * (b - a)[None, :]  # (np, 3)
        for s in range(0, idx.size, chunk):
            ii = idx[s:s + chunk]
            pot = box_potential(pts[None, :, 0], pts[None, :, 1], pts[None, :, 2], lo[ii][:, None, :], hi[ii][:, None, :])
            out[ii] = pot @ ws
    return out, bound, d_lb


# ---------------------------------------------------------------------------------------------- wires
@dataclass
class WireIn:
    name: str
    points: np.ndarray  # (nv, 3) polyline (m)
    diameter: float
    sigma: float


@dataclass
class FilamentSet:
    """All filaments of all wires: ``seg_p0/seg_p1`` (Ns, 3) are the filament segments, ``seg_fil`` their filament index,
    ``fil_wire`` the wire of each filament, ``area`` / ``rho`` the filament cross-section (m^2) / equivalent radius."""
    seg_p0: np.ndarray
    seg_p1: np.ndarray
    seg_fil: np.ndarray
    fil_wire: np.ndarray
    area: np.ndarray
    rho: np.ndarray
    sigma: np.ndarray
    clamped: int = 0

    @property
    def nfil(self) -> int:
        return self.area.size


def _frames(t):
    """Transverse frames (e1, e2) of unit directions t (n, 3): e1 horizontal (z x t), e2 = t x e1."""
    z = np.array([0.0, 0.0, 1.0])
    e1 = np.cross(z, t)
    nrm = np.linalg.norm(e1, axis=1)
    alt = np.cross(np.array([1.0, 0.0, 0.0]), t)
    e1 = np.where(nrm[:, None] > 1e-9, e1, alt)
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(t, e1)
    return e1, e2


def filament_offsets(edges_r, r: float):
    """Equal-area partition of the round section into annuli (centre disc, rings of WIRE_PHI sectors at the area-mean
    radius): returns offsets (nf, 2) and areas (nf,)."""
    off, area = [], []
    for k in range(len(edges_r) - 1):
        a, b = edges_r[k] * r, edges_r[k + 1] * r
        A = math.pi * (b * b - a * a)
        if k == 0:
            off.append((0.0, 0.0))
            area.append(A)
        else:
            rm = math.sqrt(0.5 * (a * a + b * b))
            ph0 = 0.5 * math.pi / WIRE_PHI * (k % 2)
            for m in range(WIRE_PHI):
                ph = ph0 + 2 * math.pi * m / WIRE_PHI
                off.append((rm * math.cos(ph), rm * math.sin(ph)))
                area.append(A / WIRE_PHI)
    return np.array(off), np.array(area)


def build_filaments(wires: list[WireIn], refinement: int, z_floor: float | None = None) -> FilamentSet:
    """Filament polylines of every wire: each filament follows the wire polyline offset by its transverse position in the
    local frames, mitred at the vertices (least squares of the offset conditions of both adjacent segments).  Vertices
    below ``z_floor`` are lifted to it (modelling clamp at the landing foot; counted in ``clamped``)."""
    P0, P1, SF, FW, AR, RH, SG = [], [], [], [], [], [], []
    base, clamped = 0, 0
    for wi, w in enumerate(wires):
        pts = np.asarray(w.points, float)
        r = w.diameter / 2
        off, area = filament_offsets(WIRE_EDGES[refinement], r)
        nvx = len(pts)
        t = np.diff(pts, axis=0)
        t /= np.linalg.norm(t, axis=1)[:, None]
        e1, e2 = _frames(t)
        nf = len(off)
        V = np.empty((nf, nvx, 3))
        for j in range(nvx):
            if j == 0 or j == nvx - 1:
                k = 0 if j == 0 else nvx - 2
                V[:, j] = pts[j] + off[:, 0:1] * e1[k] + off[:, 1:2] * e2[k]
            else:
                A = np.stack([e1[j - 1], e2[j - 1], e1[j], e2[j]])  # (4, 3)
                rhs = np.stack([off[:, 0], off[:, 1], off[:, 0], off[:, 1]])  # (4, nf)
                o = np.linalg.lstsq(A, rhs, rcond=None)[0]  # (3, nf)
                V[:, j] = pts[j] + o.T
        if z_floor is not None:
            low = V[:, :, 2] < z_floor
            clamped += int(low.sum())
            V[:, :, 2] = np.maximum(V[:, :, 2], z_floor)
        for f in range(nf):
            P0.append(V[f, :-1])
            P1.append(V[f, 1:])
            SF.append(np.full(nvx - 1, base + f))
        FW += [wi] * nf
        AR.append(area)
        RH.append(np.sqrt(area / math.pi))
        SG += [w.sigma] * nf
        base += nf
    return FilamentSet(np.concatenate(P0), np.concatenate(P1), np.concatenate(SF), np.array(FW),
                       np.concatenate(AR), np.concatenate(RH), np.array(SG), clamped)


def wire_matrices(fs: FilamentSet):
    """(Lww (nf, nf) H, |Lww| (entrywise sum of absolute segment-pair terms), Rw (nf,) Ohm, rod self L per filament,
    Ex (nf, nf) H = stated remainder of the finite-radius inter-wire couplings, rod_err (nf,) H = stated truncation bound of the
    self terms).  L from the closed-form segment mutuals (self: ``rod_self`` of the filament's equivalent radius; consecutive
    segments of a filament get ``joint_correction``); R = sum(length) / (sigma area) (DC per filament; skin effect is carried
    by the filament mesh).  Filaments of one wire are the mesh of its cross-section (discretisation, not bounded here);
    filaments of different wires are round rods of their equivalent radius: centre-line mutual + ``rod_pair_correction``
    (remainder in Ex, counted in solver_tol)."""
    n = fs.nfil
    ns = fs.seg_p0.shape[0]
    ln = np.linalg.norm(fs.seg_p1 - fs.seg_p0, axis=1)
    tn = (fs.seg_p1 - fs.seg_p0) / ln[:, None]
    A = sp.csr_matrix((np.ones(ns), (np.arange(ns), fs.seg_fil)), shape=(ns, n))
    rho_s = fs.rho[fs.seg_fil]
    wire_s = fs.fil_wire[fs.seg_fil]
    Lw, La, Ex = np.zeros((n, n)), np.zeros((n, n)), np.zeros((n, n))
    chunk = max(1, 1_000_000 // max(ns, 1))
    idx_all = np.arange(ns)
    for s in range(0, ns, chunk):
        sl = slice(s, min(ns, s + chunk))
        m = segment_mutual(fs.seg_p0[sl, None, :], fs.seg_p1[sl, None, :], fs.seg_p0[None, :, :], fs.seg_p1[None, :, :])
        rows = idx_all[sl][:, None]
        same = rows == idx_all[None, :]
        m = np.where(same, rod_self(ln[sl, None], rho_s[sl, None]), m)
        adj = (np.abs(rows - idx_all[None, :]) == 1) & (fs.seg_fil[sl, None] == fs.seg_fil[None, :])
        cosj = np.sum(tn[sl, None, :] * tn[None, :, :], axis=-1)
        m = np.where(adj, m - joint_correction(rho_s[sl, None], cosj), m)
        inter = wire_s[sl, None] != wire_s[None, :]
        corr, rem = rod_pair_correction(fs.seg_p0[sl, None, :], fs.seg_p1[sl, None, :], rho_s[sl, None],
                                        fs.seg_p0[None, :, :], fs.seg_p1[None, :, :], rho_s[None, :])
        m = np.where(inter, m + corr, m)
        eb = np.where(inter, rem, 0.0)
        As = A[sl]
        Lw += As.T @ (A.T @ m.T).T
        La += As.T @ (A.T @ np.abs(m).T).T
        Ex += As.T @ (A.T @ eb.T).T
    Rw = np.bincount(fs.seg_fil, weights=ln, minlength=n) / (fs.sigma * fs.area)
    self_l = np.bincount(fs.seg_fil, weights=rod_self(ln, rho_s), minlength=n)
    rod_err = np.bincount(fs.seg_fil, weights=rod_self_bound(ln, rho_s), minlength=n)
    return 0.5 * (Lw + Lw.T), 0.5 * (La + La.T), Rw, self_l, 0.5 * (Ex + Ex.T), rod_err


# ---------------------------------------------------------------------------------------------- grid slabs
@dataclass
class SlabSpec:
    name: str
    mask: np.ndarray  # (nx, ny) bool: cells carrying current
    layers: list  # [(z0, z1)] bottom-up
    sigma: float
    label: np.ndarray | None = None  # (nx, ny) int: branches only join cells of equal label (separate traces)


def graded_layers(z0: float, z1: float, n: int, fmax: float, sigma: float, two_sided: bool):
    """n thickness layers of [z0, z1], first layer = min(0.5 skin depth, uniform) at the top face (and at the bottom face
    too when ``two_sided``: n // 2 layers from each face)."""
    t = z1 - z0
    d = core.skin(fmax, sigma)

    def half(thick, m):
        g = core.grading_rate(0.5 * d / thick, m)
        return thick * core.graded_fractions(m, g)

    if not two_sided:
        dep = half(t, n)
        return [(z1 - dep[i + 1], z1 - dep[i]) for i in range(n)][::-1]
    n_lo = n // 2
    n_hi = n - n_lo
    hi_t, lo_t = t * n_hi / n, t * n_lo / n
    dh, dl = half(hi_t, n_hi), half(lo_t, n_lo)
    zm = z0 + lo_t
    lo = [(z0 + dl[i], z0 + dl[i + 1]) for i in range(n_lo)]
    hi = [(z1 - dh[i + 1], z1 - dh[i]) for i in range(n_hi)][::-1]
    lo[-1] = (lo[-1][0], zm)
    hi[0] = (zm, hi[0][1])
    return lo + hi


PLANE_GROUP = 1  # layer pairs of ``core.plane_table`` evaluated concurrently (bounds the temporaries of its Gauss tensors)


def layer_pair_tables(layers, a_al, a_tr, n1, n2, group: int = PLANE_GROUP):
    """``core.plane_table(layers, layers, ...)`` evaluated for the upper triangle of layer pairs in groups of ``group``
    concurrent pairs (peak memory ~ group x the temporaries of one pair instead of nL x), the lower triangle by reciprocity
    (the mutual of two parallel boxes is symmetric under exchange of the boxes).  Returns (T, summed stated bound)."""
    nL = len(layers)
    T = np.zeros((nL, nL, n1, n2))
    bound = 0.0
    for la in range(nL):
        for s in range(la, nL, group):
            lbs = list(range(s, min(nL, s + group)))
            t, b = core.plane_table([layers[la]], [layers[lb] for lb in lbs], a_al, a_tr, n1, n2)
            for k, lb in enumerate(lbs):
                T[la, lb] = T[lb, la] = t[0, k]
            bound += b
    return T, bound


class Grid:
    """Shared lateral lattice (nx x ny cells, cell sizes ax, ay, origin x0, y0) carrying the slabs.  Unknowns: x-branches
    (nL, nx-1, ny) then y-branches (nL, ny-1, nx) restricted to the slabs' masks (both end cells present)."""

    def __init__(self, x0, y0, ax, ay, nx, ny, slabs: list[SlabSpec]):
        self.x0, self.y0, self.ax, self.ay, self.nx, self.ny = x0, y0, ax, ay, nx, ny
        self.slabs = slabs
        self.layers, self.slab_of, self.sigma = [], [], []
        for s, sl in enumerate(slabs):
            for lay in sl.layers:
                self.layers.append(lay)
                self.slab_of.append(s)
                self.sigma.append(sl.sigma)
        self.slab_of = np.array(self.slab_of)
        self.sigma_arr = np.array(self.sigma)
        self.nL = nL = len(self.layers)
        self.thick = np.array([z1 - z0 for z0, z1 in self.layers])
        vx = np.zeros((nL, nx - 1, ny), bool)
        vy = np.zeros((nL, ny - 1, nx), bool)
        for li in range(nL):
            m = slabs[self.slab_of[li]].mask
            lab = slabs[self.slab_of[li]].label
            same_x = np.ones((nx - 1, ny), bool) if lab is None else lab[:-1, :] == lab[1:, :]
            same_y = np.ones((nx, ny - 1), bool) if lab is None else lab[:, :-1] == lab[:, 1:]
            vx[li] = m[:-1, :] & m[1:, :] & same_x
            vy[li] = (m[:, :-1] & m[:, 1:] & same_y).T
        self.valid = [vx, vy]
        self.uidx = []
        off = 0
        for v in self.valid:
            u = np.full(v.shape, -1, np.int64)
            u[v] = off + np.arange(int(v.sum()))
            self.uidx.append(u)
            off += int(v.sum())
        self.n_gx, self.n_gy = int(vx.sum()), int(vy.sum())
        self.n_g = self.n_gx + self.n_gy
        sg = np.array(self.sigma)
        self.R = np.concatenate([
            np.broadcast_to((ax / (sg * ay * self.thick))[:, None, None], vx.shape)[vx],
            np.broadcast_to((ay / (sg * ax * self.thick))[:, None, None], vy.shape)[vy]])
        # node ids per slab cell
        self.node_id, nn = [], 0
        for sl in slabs:
            ids = np.full((nx, ny), -1, np.int64)
            ids[sl.mask] = nn + np.arange(int(sl.mask.sum()))
            nn += int(sl.mask.sum())
            self.node_id.append(ids)
        self.n_cell_nodes = nn
        self.tabs, self.thr, self.plane_bound = [], [], 0.0
        for a_al, a_tr, n1, n2 in ((ax, ay, nx - 1, ny), (ay, ax, ny - 1, nx)):
            T, b = layer_pair_tables(self.layers, a_al, a_tr, n1, n2)
            self.tabs.append(T[:, :, 0, 0].copy())
            self.thr.append(core.circulant_fft(T))
            self.plane_bound = max(self.plane_bound, b)
        self._boxes()

    def cell_xy(self):
        return (self.x0 + (np.arange(self.nx) + 0.5) * self.ax, self.y0 + (np.arange(self.ny) + 0.5) * self.ay)

    def _boxes(self):
        xc, yc = self.cell_xy()
        z0 = np.array([z[0] for z in self.layers])
        z1 = np.array([z[1] for z in self.layers])
        l, i, j = np.nonzero(self.valid[0])
        self.bx_lij = (l, i, j)
        self.bx_lo = np.stack([xc[i], yc[j] - self.ay / 2, z0[l]], 1)
        self.bx_hi = np.stack([xc[i + 1], yc[j] + self.ay / 2, z1[l]], 1)
        self.bx_A = self.ay * self.thick[l]
        l, j, i = np.nonzero(self.valid[1])
        self.by_lij = (l, j, i)
        self.by_lo = np.stack([xc[i] - self.ax / 2, yc[j], z0[l]], 1)
        self.by_hi = np.stack([xc[i] + self.ax / 2, yc[j + 1], z1[l]], 1)
        self.by_A = self.ax * self.thick[l]

    def apply(self, xg):
        """y = L_gg x (H), FFT block-Toeplitz per direction; works for real or complex x."""
        out = np.zeros(self.n_g, dtype=complex if np.iscomplexobj(xg) else float)
        off = 0
        for d in (0, 1):
            v = self.valid[d]
            n = int(v.sum())
            full = np.zeros(v.shape, dtype=xg.dtype)
            full[v] = xg[off:off + n]
            y = core.circulant_apply(self.thr[d], full)
            out[off:off + n] = y[v] if np.iscomplexobj(out) else y[v].real
            off += n
        return out

    def uid_of(self, d, l, a, b):
        return self.uidx[d][l, a, b]


# ---------------------------------------------------------------------------------------------- wire <-> grid
def lagrange_weights(xi, n):
    """Weights (len(xi), n) of the n-point Lagrange interpolation on nodes 0..n-1 at positions xi."""
    xi = np.asarray(xi, float)
    w = np.ones((xi.size, n))
    for m in range(n):
        for q in range(n):
            if q != m:
                w[:, m] *= (xi - q) / (m - q)
    return w


def _omega_leb(n):
    """Max over the central interval of |prod (u - node)| (unit spacing) and the Lebesgue constant of n equispaced nodes
    (nodes at -(n-1)/2 .. (n-1)/2, evaluation in the central interval [-1/2, 1/2])."""
    nodes = np.arange(n) - (n - 1) / 2.0
    u = np.linspace(-0.5, 0.5, 2001)
    om = np.abs(np.prod(u[:, None] - nodes[None, :], axis=1)).max()
    leb = 0.0
    for m in range(n):
        lm = np.ones_like(u)
        for q in range(n):
            if q != m:
                lm *= (u - nodes[q]) / (nodes[m] - nodes[q])
        leb += np.abs(lm)
    return float(om), float(leb.max())


class _WireGridBase:
    bound = 0.0  # stated relative bound of the compressed coupling (interpolation + Gauss), all counted in solver_tol
    near_bound = 0.0  # stated Gauss bound of the exact near-field integrals


class WireGridDense(_WireGridBase):
    """Exact dense coupling K (nfil x n_g) (test oracle and tiny problems): K[f, b] = sum_seg t_axis K4 / A_b
    int_seg int_box 1/R."""

    def __init__(self, fs: FilamentSet, grid: Grid):
        self.fs, self.grid = fs, grid
        K = np.zeros((fs.nfil, grid.n_g))
        Kx = np.zeros((fs.nfil, grid.n_g))
        t = fs.seg_p1 - fs.seg_p0
        ell = np.linalg.norm(t, axis=1)
        t = t / ell[:, None]
        nb = 0
        for d, (lo, hi, A) in enumerate(((grid.bx_lo, grid.bx_hi, grid.bx_A), (grid.by_lo, grid.by_hi, grid.by_A))):
            if lo.shape[0] == 0:
                continue
            for s in range(fs.seg_p0.shape[0]):
                if abs(t[s, d]) < 1e-15:
                    continue
                I, bd, _ = line_box_integral(fs.seg_p0[s], fs.seg_p1[s], lo, hi)
                corr, rem = rod_box_correction(fs.seg_p0[s], fs.seg_p1[s], fs.rho[fs.seg_fil[s]], lo, hi)
                K[fs.seg_fil[s], nb:nb + lo.shape[0]] += K4 * t[s, d] * (I + corr) / A
                Kx[fs.seg_fil[s], nb:nb + lo.shape[0]] += K4 * abs(t[s, d]) * rem / A
                self.near_bound = max(self.near_bound, bd)
            nb += lo.shape[0]
        self.K = K
        self.Cx = sp.csr_matrix(Kx)
        self.bnd_far = 0.0  # every pair is counted in Cx

    def to_wires(self, xg, absolute=False):
        return (np.abs(self.K) if absolute else self.K) @ xg

    def to_grid(self, xw, absolute=False):
        return (np.abs(self.K) if absolute else self.K).T @ xw


class WireGridPFFT(_WireGridBase):
    """Precorrected-FFT wire <-> grid coupling (see module docstring).  ``far_error`` returns the stated relative bound of
    the interpolation of the far field (all branches outside the near box of a wire), ``bound`` adds the node Gauss bound."""

    NG = 4

    def __init__(self, fs: FilamentSet, grid: Grid, near: int | None = None):
        near = PFFT_NEAR if near is None else near
        self.fs, self.grid, self.near = fs, grid, near
        g = grid
        nx, ny = g.nx, g.ny
        ns = fs.seg_p0.shape[0]
        d = fs.seg_p1 - fs.seg_p0
        ell = np.linalg.norm(d, axis=1)
        t = d / ell[:, None]
        xg_, wg_ = core.gq(self.NG, 0.0, 1.0)
        # nodes: NG Gauss points along the axis x a degree-3 disc rule over the filament's cross-section (4 points at
        # radius rho / sqrt(2), weights 1/4: exact for transverse polynomials of degree <= 3), so the far field sees the
        # finite-radius rod, not its centre line
        e1, e2 = _frames(t)
        ang = 0.5 * math.pi * np.arange(4)
        rad = fs.rho[fs.seg_fil] / math.sqrt(2.0)
        off = rad[:, None, None] * (np.cos(ang)[None, :, None] * e1[:, None, :] + np.sin(ang)[None, :, None] * e2[:, None, :])
        axis_pts = fs.seg_p0[:, None, :] + xg_[None, :, None] * d[:, None, :]  # (ns, NG, 3)
        self.NQ = 4 * self.NG
        self.node_pos = (axis_pts[:, :, None, :] + off[:, None, :, :]).reshape(ns, self.NQ, 3)
        self.node_w = np.repeat(ell[:, None] * wg_[None, :] / 4.0, 4, axis=1)  # (ns, NQ)
        self.t = t
        hz = min(PFFT_DZ, PFFT_DZ_CELLS * min(g.ax, g.ay))  # scales with the cell: interpolation bound refinement-invariant
        zmin, zmax = float(self.node_pos[..., 2].min()), float(self.node_pos[..., 2].max())
        self.hz = hz
        self.zlo = zmin - 2.0 * hz
        self.nzv = int(math.ceil((zmax - self.zlo) / hz)) + 3
        nl, nzs = PFFT_STENCIL, PFFT_STENCIL_Z
        pos = self.node_pos.reshape(-1, 3)
        w = self.node_w.reshape(-1)
        fil = np.repeat(fs.seg_fil, self.NQ)
        # lateral / vertical stencils
        zu = (pos[:, 2] - self.zlo) / hz
        k0 = np.floor(zu).astype(int) - 1
        Wz = lagrange_weights(zu - k0, nzs)
        self.S, self.nodes_idx = [], None
        self.n_virt = []
        n1x, n2x, n1y, n2y = nx - 1, ny, ny - 1, nx
        self.dims = [(n1x, n2x), (n1y, n2y)]
        for dd in (0, 1):
            if dd == 0:  # x-lattice: axial index i (branch centre x0 + (i+1) ax), lateral row j (y0 + (j+.5) ay)
                ua = (pos[:, 0] - g.x0) / g.ax - 1.0
                ub = (pos[:, 1] - g.y0) / g.ay - 0.5
                na_, nb_ = n1x, n2x
            else:
                ua = (pos[:, 1] - g.y0) / g.ay - 1.0
                ub = (pos[:, 0] - g.x0) / g.ax - 0.5
                na_, nb_ = n1y, n2y
            a0 = np.floor(ua).astype(int) - (nl // 2 - 1)
            b0 = np.floor(ub).astype(int) - (nl // 2 - 1)
            if a0.min() < 0 or b0.min() < 0 or (a0 + nl).max() > na_ or (b0 + nl).max() > nb_:
                raise ValueError("wire too close to the edge of the shared grid for the interpolation stencil")
            Wa, Wb = lagrange_weights(ua - a0, nl), lagrange_weights(ub - b0, nl)
            coef = w * t[np.repeat(np.arange(ns), self.NQ), dd]
            val = (coef[:, None, None, None] * Wa[:, :, None, None] * Wb[:, None, :, None] * Wz[:, None, None, :])
            ia = a0[:, None, None, None] + np.arange(nl)[None, :, None, None]
            ib = b0[:, None, None, None] + np.arange(nl)[None, None, :, None]
            ik = k0[:, None, None, None] + np.arange(nzs)[None, None, None, :]
            flat = (ik * na_ + ia) * nb_ + ib
            rows = np.broadcast_to(fil[:, None, None, None], flat.shape)
            n_virt = self.nzv * na_ * nb_
            self.S.append(sp.csr_matrix((val.ravel(), (rows.ravel(), flat.ravel())), shape=(fs.nfil, n_virt)))
            self.n_virt.append(n_virt)
        self.S_abs = []
        for S in self.S:
            Sa = S.copy()
            Sa.data = np.abs(Sa.data)
            self.S_abs.append(Sa)
        self._tables()
        self._near_correction()
        self._bounds(ell)

    # virtual-lattice tables
    def _tables(self):
        g = self.grid
        zv = self.zlo + self.hz * np.arange(self.nzv)
        z0 = np.array([z[0] for z in g.layers])
        z1 = np.array([z[1] for z in g.layers])
        self.Tv, self.Thr, self.ThrT = [], [], []
        for dd in (0, 1):
            n1, n2 = self.dims[dd]
            a_al, a_tr = (g.ax, g.ay) if dd == 0 else (g.ay, g.ax)
            A = a_tr * g.thick  # (nL,)
            di = (np.arange(n1) * a_al)[None, None, :, None]
            dj = (np.arange(n2) * a_tr)[None, None, None, :]
            lo = np.zeros((1, g.nL, 1, 1, 3))
            hi = np.zeros((1, g.nL, 1, 1, 3))
            lo[..., 0], hi[..., 0] = -a_al / 2, a_al / 2
            lo[..., 1], hi[..., 1] = -a_tr / 2, a_tr / 2
            lo[..., 2] = z0[None, :, None, None]
            hi[..., 2] = z1[None, :, None, None]
            pz = zv[:, None, None, None]
            # field point (axial di, lateral dj) relative to the branch box centred at the origin
            if dd == 0:
                P = box_potential(di, dj, pz, lo, hi)
            else:  # y-branch: lateral offset along x, axial along y; box ax (x) by ay (y)
                lo2, hi2 = lo.copy(), hi.copy()
                lo2[..., 0], hi2[..., 0] = -g.ax / 2, g.ax / 2
                lo2[..., 1], hi2[..., 1] = -g.ay / 2, g.ay / 2
                P = box_potential(dj, di, pz, lo2, hi2)
            T = K4 * P / A[None, :, None, None]
            T = np.ascontiguousarray(T)
            self.Tv.append(T)
            th = core.circulant_fft(T)  # (F, nzv, nL)
            self.Thr.append(th)
            self.ThrT.append(np.ascontiguousarray(th.transpose(0, 2, 1)))

    def _near_correction(self):
        g, fs = self.grid, self.fs
        near = self.near
        nx, ny = g.nx, g.ny
        rows_all, cols_all, vals_all, vals_x = [], [], [], []
        nb_max = 0
        wires = np.unique(fs.fil_wire)
        fil_of_wire = {w: np.flatnonzero(fs.fil_wire == w) for w in wires}
        seg_of_fil = {}
        for s, f in enumerate(fs.seg_fil):
            seg_of_fil.setdefault(int(f), []).append(s)
        n_far_branches = 0
        self.near_bound = 0.0
        for w in wires:
            fl = fil_of_wire[w]
            segs = np.concatenate([seg_of_fil[int(f)] for f in fl])
            pos = self.node_pos[segs].reshape(-1, 3)
            ci = np.floor((pos[:, 0] - g.x0) / g.ax).astype(int)
            cj = np.floor((pos[:, 1] - g.y0) / g.ay).astype(int)
            i_lo, i_hi = max(ci.min() - near, 0), min(ci.max() + near, nx - 1)
            j_lo, j_hi = max(cj.min() - near, 0), min(cj.max() + near, ny - 1)
            sel = []
            for dd in (0, 1):
                l, a, b = (g.bx_lij if dd == 0 else g.by_lij)
                # x-branch: a = i (axial, cells i..i+1), b = j; y-branch: a = j (axial), b = i
                ii, jj = (a, b) if dd == 0 else (b, a)
                inreg = (ii >= i_lo - 1) & (ii <= i_hi) & (jj >= j_lo) & (jj <= j_hi) if dd == 0 else \
                    (ii >= i_lo) & (ii <= i_hi) & (jj >= j_lo - 1) & (jj <= j_hi)
                sel.append(np.flatnonzero(inreg))
                n_far_branches += (l.size - sel[-1].size)
            # exact part
            for dd in (0, 1):
                idx = sel[dd]
                if idx.size == 0:
                    continue
                lo, hi, A = (g.bx_lo, g.bx_hi, g.bx_A) if dd == 0 else (g.by_lo, g.by_hi, g.by_A)
                lo, hi, A = lo[idx], hi[idx], A[idx]
                ex = np.zeros((fl.size, idx.size))
                exb = np.zeros((fl.size, idx.size))
                loc = {int(f): k for k, f in enumerate(fl)}
                for s in segs:
                    if abs(self.t[s, dd]) < 1e-15:
                        continue
                    I, bd, _ = line_box_integral(fs.seg_p0[s], fs.seg_p1[s], lo, hi)
                    self.near_bound = max(self.near_bound, bd)
                    corr, rem = rod_box_correction(fs.seg_p0[s], fs.seg_p1[s], fs.rho[fs.seg_fil[s]], lo, hi)
                    ex[loc[int(fs.seg_fil[s])]] += K4 * self.t[s, dd] * (I + corr) / A
                    exb[loc[int(fs.seg_fil[s])]] += K4 * abs(self.t[s, dd]) * rem / A
                # approximate (what the FFT path produces for the same pairs)
                Ssub = self.S[dd][fl]
                cols = np.unique(Ssub.indices)
                Sd = Ssub[:, cols].toarray()
                n1, n2 = self.dims[dd]
                kk, rem = np.divmod(cols, n1 * n2)
                pa, pb = np.divmod(rem, n2)
                l, a, b = (g.bx_lij if dd == 0 else g.by_lij)
                lb, ab_, bb = l[idx], a[idx], b[idx]
                ap = np.zeros_like(ex)
                for s0 in range(0, idx.size, 4096):
                    sl = slice(s0, s0 + 4096)
                    Tg = self.Tv[dd][kk[:, None], lb[None, sl], np.abs(pa[:, None] - ab_[None, sl]),
                                     np.abs(pb[:, None] - bb[None, sl])]
                    ap[:, sl] = Sd @ Tg
                corr = ex - ap
                gid = idx + (0 if dd == 0 else g.n_gx)
                rows_all.append(np.repeat(fl, idx.size))
                cols_all.append(np.tile(gid, fl.size))
                vals_all.append(corr.ravel())
                vals_x.append(exb.ravel())
                nb_max = max(nb_max, idx.size)
        self.n_far_branches = n_far_branches
        self.near_pairs = int(sum(r.size for r in rows_all))
        if rows_all:
            shp = (fs.nfil, g.n_g)
            rc = (np.concatenate(rows_all), np.concatenate(cols_all))
            self.C = sp.csr_matrix((np.concatenate(vals_all), rc), shape=shp)
            self.Cx = sp.csr_matrix((np.concatenate(vals_x), rc), shape=shp)
        else:
            self.C = sp.csr_matrix((fs.nfil, g.n_g))
            self.Cx = sp.csr_matrix((fs.nfil, g.n_g))

    def _bounds(self, ell):
        """Stated relative bound of the far-field interpolation: tensor Lagrange, error per axis <= omega_max
        /(D_s^n) (D_f/D_s) with the n-th derivative bound |d^n (1/r)/dx^n| <= n!/r^(n+1) (Legendre), D_f = (near - 1) cells,
        D_s = D_f - hull radius of the stencil; combined sequentially with the Lebesgue constants."""
        g = self.grid
        nl, nz = PFFT_STENCIL, PFFT_STENCIL_Z
        om_l, le_l = _omega_leb(nl)
        om_z, le_z = _omega_leb(nz)
        a = min(g.ax, g.ay)
        amax = max(g.ax, g.ay)
        Df = (self.near - 1.0) * a
        hull = math.sqrt(2 * ((nl / 2.0) * amax) ** 2 + ((nz / 2.0) * self.hz) ** 2)
        Ds = Df - hull
        # disc-rule bound of the far pairs: every branch beyond the near box is >= Df from every node, so >= Df - rho from
        # the axis point of the node; in the Legendre expansion of 1/R about that point, disc mean and rule agree for
        # degrees <= 3 and each differ by <= q^n for n >= 4 (q = rho / (Df - rho)): relative bound 2 q^4 / (1 - q)
        # (counted in solver_tol)
        rmax = float(self.fs.rho.max())
        q = rmax / max(Df - 2.0 * rmax, 1e-300)
        self.bnd_far = 2.0 * q ** 4 / (1.0 - q) if q < 1.0 else float("inf")
        if self.n_far_branches == 0:
            self.far_bound, self.bound = 0.0, 0.0
            return
        if Ds <= 0:
            self.far_bound = float("inf")
            self.bound = float("inf")
            return
        fac = Df / Ds
        e_l = om_l * amax ** nl / Ds ** nl * fac
        e_z = om_z * self.hz ** nz / Ds ** nz * fac
        far = 2 * e_l * le_l * le_z + e_l * le_z + e_z  # x, y lateral then z (sequential tensor bound)
        rho = 1.0 + (Df - float(self.fs.rho.max())) / (0.5 * float(ell.max()))
        gq_b = core.gauss_bound(self.NG, rho)
        self.far_bound = far
        self.bound = far + gq_b

    def _fft_x(self, Xfull, dd, transposed=False):
        return core.circulant_apply(self.ThrT[dd] if transposed else self.Thr[dd], Xfull)

    def to_wires(self, xg, absolute=False):
        g = self.grid
        S = self.S_abs if absolute else self.S
        y = np.zeros(self.fs.nfil, dtype=complex if np.iscomplexobj(xg) else float)
        off = 0
        for dd in (0, 1):
            v = g.valid[dd]
            n = int(v.sum())
            full = np.zeros(v.shape, dtype=xg.dtype)
            full[v] = xg[off:off + n]
            A = self._fft_x(full, dd)
            y = y + S[dd] @ (A.ravel() if np.iscomplexobj(y) else A.real.ravel())
            off += n
        C = abs(self.C) if absolute else self.C
        return y + C @ xg

    def to_grid(self, xw, absolute=False):
        g = self.grid
        S = self.S_abs if absolute else self.S
        out = np.zeros(g.n_g, dtype=complex if np.iscomplexobj(xw) else float)
        off = 0
        for dd in (0, 1):
            v = g.valid[dd]
            n = int(v.sum())
            n1, n2 = self.dims[dd]
            sx = (S[dd].T @ xw).reshape(self.nzv, n1, n2)
            Y = self._fft_x(sx, dd, transposed=True)
            out[off:off + n] = Y[v] if np.iscomplexobj(out) else Y[v].real
            off += n
        C = abs(self.C) if absolute else self.C
        return out + C.T @ xw


# ---------------------------------------------------------------------------------------------- the linear system
class LayoutSystem:
    """Unknowns x = [filament currents (nfil), grid branch currents (n_g)];  M = R + j w L,  L = [[Lww, K], [K^T, Lgg]].

    ``ends[w] = (start, end)`` are the raw node ids of wire w (cell nodes of ``grid`` or extra free nodes >= grid
    .n_cell_nodes); ``shorts`` are groups of raw nodes merged into one node (ideal die shorts)."""

    def __init__(self, fs: FilamentSet, grid: Grid, wg, ends: np.ndarray, shorts: list, n_extra: int = 0):
        self.fs, self.grid, self.wg = fs, grid, wg
        self.nfil, self.n_g = fs.nfil, grid.n_g
        self.n = self.nfil + self.n_g
        self.Lw, self.Lw_abs, self.Rw, self.self_l, self.Ex, self.rod_err = wire_matrices(fs)
        self.R = np.concatenate([self.Rw, grid.R])
        n_raw = grid.n_cell_nodes + n_extra
        rows, cols = [], []
        for grp in shorts:
            grp = np.asarray(grp, np.int64)
            rows.append(np.full(grp.size, grp[0]))
            cols.append(grp)
        adj = sp.coo_matrix((np.ones(sum(r.size for r in rows)), (np.concatenate(rows), np.concatenate(cols))),
                            shape=(n_raw, n_raw)) if rows else sp.coo_matrix((n_raw, n_raw))
        _, self.lab = connected_components(adj, directed=False)
        self.ends = np.asarray(ends, np.int64)
        self.stated_total = 0.0
        self.stated = {}

    def set_stated(self):
        """Register the stated relative bounds of the tables and of the wire-to-grid operator (counted in solver_tol)."""
        wg, g = self.wg, self.grid
        self.stated = dict(plane_tables=g.plane_bound, wire_grid_interp_gauss=wg.bound, wire_grid_near_gauss=wg.near_bound,
                           wire_grid_far_disc_rule=wg.bnd_far, wire_rod_series_max_h=float(self.rod_err.max()))
        self.stated_total = g.plane_bound + wg.bound + wg.near_bound

    def stated_parts(self, xa, w):
        """Stated absolute error bounds (npt, npt) of Z = x^T M x (Ohm) for |x| = xa (n, npt), each applied to the block
        it bounds (all counted in solver_tol, D0004 (i)): plane tables (relative, on w |xg|^T Lgg |xg|); wire<->grid
        operator (pFFT interpolation + node / near-field Gauss + far centre-line tail, relative, on 2 w |xf|^T |K| |xg|);
        finite-radius remainders of the near wire<->grid pairs (Cx) and of the inter-wire pairs (Ex); rod-series truncation
        of the filament self terms."""
        xf, xg = xa[:self.nfil], xa[self.nfil:]
        g, wg = self.grid, self.wg
        npt = xa.shape[1]
        e_gg = w * (xg.T @ np.stack([g.apply(xg[:, j]) for j in range(npt)], 1))
        e_wg = 2.0 * w * (xf.T @ np.stack([wg.to_wires(xg[:, j], True) for j in range(npt)], 1))
        return dict(plane_tables=g.plane_bound * e_gg,
                    wire_grid_operator=(wg.bound + wg.near_bound + wg.bnd_far) * e_wg,
                    wire_grid_finite_radius=2.0 * w * (xf.T @ (wg.Cx @ xg)),
                    inter_wire_finite_radius=w * (xf.T @ (self.Ex @ xf)),
                    rod_series=w * (xf.T @ (self.rod_err[:, None] * xf)))

    # operator
    def lmul(self, x, absolute: bool = False):
        xw, xg = x[:self.nfil], x[self.nfil:]
        Lw = self.Lw_abs if absolute else self.Lw
        yw = Lw @ xw + self.wg.to_wires(xg, absolute)
        yg = self.grid.apply(xg) + self.wg.to_grid(xw, absolute)
        return np.concatenate([yw, yg])

    def incidence(self):
        g = self.grid
        lab = self.lab
        nn = int(lab.max()) + 1
        rows, cols, vals = [], [], []
        f_w = self.fs.fil_wire
        ar = np.arange(self.nfil)
        rows += [ar, ar]
        cols += [lab[self.ends[f_w, 0]], lab[self.ends[f_w, 1]]]
        vals += [np.ones(self.nfil), -np.ones(self.nfil)]
        off = self.nfil
        for d in (0, 1):
            l, a, b = np.nonzero(g.valid[d])
            s = g.slab_of[l]
            i, j = (a, b) if d == 0 else (b, a)
            n1 = np.empty(l.size, np.int64)
            n2 = np.empty(l.size, np.int64)
            for k in range(len(g.slabs)):
                m = s == k
                n1[m] = g.node_id[k][i[m], j[m]]
                n2[m] = g.node_id[k][i[m] + (d == 0), j[m] + (d == 1)]
            idx = off + np.arange(l.size)
            rows += [idx, idx]
            cols += [lab[n1], lab[n2]]
            vals += [np.ones(l.size), -np.ones(l.size)]
            off += l.size
        C = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(self.n, nn))
        pat = abs(C).T @ abs(C)
        ncomp, comp = connected_components(pat, directed=False)
        first = np.array([np.flatnonzero(comp == c)[0] for c in range(ncomp)])
        keep = np.setdiff1d(np.arange(nn), first)
        return C, keep, nn


class LayoutPreconditioner:
    """Block preconditioner of the saddle system (as ``l2_core.Preconditioner``): inverse of the dense wire block and of
    every slab's layer block at zero lateral offset; nodal Schur complement S = C^T M_b^-1 C factorised sparse."""

    def __init__(self, sys_: LayoutSystem, w: float, Cr, keep, nn):
        self.s, self.Cr = sys_, Cr
        g = sys_.grid
        lab = sys_.lab
        self.Mi = np.linalg.inv(sys_.Rw * np.eye(sys_.nfil) + 1j * w * sys_.Lw)
        rows, cols, vals = [], [], []
        nodes = np.unique(np.concatenate([lab[sys_.ends[:, 0]], lab[sys_.ends[:, 1]]]))
        pos = {int(v): k for k, v in enumerate(nodes)}
        Cw = np.zeros((sys_.nfil, nodes.size))
        fw = sys_.fs.fil_wire
        for f in range(sys_.nfil):
            Cw[f, pos[int(lab[sys_.ends[fw[f], 0]])]] += 1.0
            Cw[f, pos[int(lab[sys_.ends[fw[f], 1]])]] -= 1.0
        Sw = Cw.T @ (self.Mi @ Cw)
        ii, jj = np.meshgrid(nodes, nodes, indexing="ij")
        rows.append(ii.ravel())
        cols.append(jj.ravel())
        vals.append(Sw.ravel())
        self.blocks = []  # (lo, hi, nlay, Bi)
        off = sys_.nfil
        for d in (0, 1):
            v = g.valid[d]
            a_al, a_tr = (g.ax, g.ay) if d == 0 else (g.ay, g.ax)
            for k in range(len(g.slabs)):
                Ls = np.flatnonzero(g.slab_of == k)
                vk = v[Ls[0]]
                c_s = int(vk.sum())
                cnt = int(v[:Ls[0]].sum())
                if c_s == 0:
                    continue
                Rl = a_al / (g.sigma_arr[Ls] * a_tr * g.thick[Ls])
                Bi = np.linalg.inv(1j * w * g.tabs[d][np.ix_(Ls, Ls)] + np.diag(Rl))
                self.blocks.append((off + cnt, off + cnt + Ls.size * c_s, Ls.size, Bi))
                ysum = Bi.sum()
                a, b = np.nonzero(vk)
                i, j = (a, b) if d == 0 else (b, a)
                n1 = lab[g.node_id[k][i, j]]
                n2 = lab[g.node_id[k][i + (d == 0), j + (d == 1)]]
                rows += [n1, n2, n1, n2]
                cols += [n1, n2, n2, n1]
                vals += [np.full(n1.size, ysum), np.full(n1.size, ysum), np.full(n1.size, -ysum), np.full(n1.size, -ysum)]
            off += int(v.sum())
        S = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(nn, nn)).tocsr()
        self.Slu = spla.splu(S[keep][:, keep].tocsc())

    def minv(self, v):
        out = np.zeros_like(v)
        nf = self.s.nfil
        out[:nf] = self.Mi @ v[:nf]
        for lo, hi, nlay, Bi in self.blocks:
            out[lo:hi] = (Bi @ v[lo:hi].reshape(nlay, -1)).reshape(-1)
        return out

    def __call__(self, v):
        n = self.s.n
        f, gg = v[:n], v[n:]
        mf = self.minv(f)
        phi = self.Slu.solve(gg - self.Cr.T @ mf)
        return np.concatenate([self.minv(f + self.Cr @ phi), phi])


@dataclass
class SolveOut:
    z: np.ndarray  # (nf, np, np)
    solver_tol: float
    parts: list = field(default_factory=list)
    iters: list = field(default_factory=list)


DENSE_MAX = 2500
GMRES_TOL = 1e-9


def solve_system(sys_: LayoutSystem, port_nodes, freqs, tol: float = GMRES_TOL, dense: bool | None = None) -> SolveOut:
    """Z[f, i, j] = V_i / I_j (other ports open) with the D0004 forward-error bound ``solver_tol`` = max over freqs of
    (a-posteriori ||P(Mx)||^2 / r_min  +  rounding  +  stated bounds) / max|Z_ii|."""
    C, keep, nn = sys_.incidence()
    Cr = C[:, keep].tocsc()
    pos = {int(k): i for i, k in enumerate(keep)}
    npt = len(port_nodes)
    D = np.zeros((len(keep), npt))
    for j, (a, b) in enumerate(port_nodes):
        a, b = int(sys_.lab[a]), int(sys_.lab[b])
        if a in pos:
            D[pos[a], j] += 1.0
        if b in pos:
            D[pos[b], j] -= 1.0
    n, R = sys_.n, sys_.R
    rmin = float(R.min())
    if dense is None:
        dense = n + Cr.shape[1] <= DENSE_MAX
    if dense:
        Ld = np.stack([sys_.lmul(np.eye(n)[:, i]).real for i in range(n)], 1)
        Ld = 0.5 * (Ld + Ld.T)
    zs, tols, iters, parts = [], [], [], []
    for f in freqs:
        w = 2 * math.pi * f

        def apply_M(v, w=w):
            return R * v + 1j * w * sys_.lmul(v)

        if dense:
            A = np.zeros((n + Cr.shape[1], n + Cr.shape[1]), complex)
            A[:n, :n] = 1j * w * Ld + np.diag(R)
            A[:n, n:] = -Cr.toarray()
            A[n:, :n] = Cr.T.toarray()
            X = np.linalg.solve(A, np.concatenate([np.zeros((n, npt)), D]))[:n]
            iters.append(0)
        else:
            pre = LayoutPreconditioner(sys_, w, Cr, keep, nn)
            X = np.zeros((n, npt), complex)
            it = 0
            for j in range(npt):
                X[:, j], k, info = core.block_gmres(apply_M, pre, Cr, D[:, j], n, tol)
                it += k
            iters.append(it)
        Xt, MX, Z, resid = core.a_posteriori(apply_M, Cr, X, D, rmin)
        xa = np.abs(Xt)
        Lx = np.stack([sys_.lmul(xa[:, j], absolute=True).real for j in range(npt)], 1)
        e_l = w * (xa.T @ Lx)
        e_r = xa.T @ (R[:, None] * xa)
        rnd = 2.0 * UNIT_ROUNDOFF * n * (e_l + e_r)
        zref = float(np.max(np.abs(np.diag(Z))))
        pt = dict(resid=float(resid.max() / zref), round=float(rnd.max() / zref))
        pt.update({k: float(v.max() / zref) for k, v in sys_.stated_parts(xa, w).items()})
        parts.append(pt)
        tols.append(sum(pt.values()))
        zs.append(Z)
    return SolveOut(z=np.array(zs), solver_tol=float(max(tols)), parts=parts, iters=iters)


# ---------------------------------------------------------------------------------------------- Layout -> system
@dataclass(frozen=True)
class LoopResult:
    L_H: np.ndarray
    R_ohm: np.ndarray
    meta: dict = field(default_factory=dict)


def source_sha256() -> str:
    """sha256 over the solver source files this path executes (D0004 provenance; no external binary)."""
    h = hashlib.sha256()
    for p in (Path(__file__), Path(core.__file__)):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _cells_in(poly_or_rect, X, Y):
    import shapely
    return shapely.contains_xy(poly_or_rect, X, Y)


def _nearest_cell(mask, xc, yc, x, y):
    """Index (i, j) of the masked cell nearest to (x, y)."""
    ii, jj = np.nonzero(mask)
    d2 = (xc[ii] - x) ** 2 + (yc[jj] - y) ** 2
    k = int(np.argmin(d2))
    return int(ii[k]), int(jj[k])


def build_layout_system(layout, fmax: float, refinement: int, coupling: str = "pfft"):
    """(LayoutSystem, port raw nodes, info dict) of ``layout`` (see module docstring)."""
    from shapely.geometry import Polygon
    if not 0 <= refinement <= MAX_REFINEMENT:
        raise ValueError(f"refinement must be in 0..{MAX_REFINEMENT}")
    cm = layout.to_conductors()
    st = cm.stack
    planes = {p.name: p for p in cm.planes}
    bp = planes["baseplate"]
    xmin, ymin, xmax, ymax = bp.bounds
    for r in cm.rects:
        xmin, ymin, xmax, ymax = min(xmin, r.x0), min(ymin, r.y0), max(xmax, r.x1), max(ymax, r.y1)
    a = CELL[refinement]
    nx, ny = max(8, round((xmax - xmin) / a)), max(8, round((ymax - ymin) / a))
    ax, ay = (xmax - xmin) / nx, (ymax - ymin) / ny
    xc = xmin + (np.arange(nx) + 0.5) * ax
    yc = ymin + (np.arange(ny) + 0.5) * ay
    X, Y = np.meshgrid(xc, yc, indexing="ij")
    # top Cu: rectangles of to_conductors(); label = net index + 1 (0 = no copper)
    nets = sorted({r.net for r in cm.rects})
    top_mask = np.zeros((nx, ny), bool)
    top_lab = np.zeros((nx, ny), np.int64)
    for r in cm.rects:
        m = (X > r.x0) & (X < r.x1) & (Y > r.y0) & (Y < r.y1)
        top_mask |= m
        top_lab[m] = nets.index(r.net) + 1
    z0t, z1t = layout.top_cu_z()
    top_sigma = st.layer("top_cu").sigma
    slabs = [SlabSpec("top_cu", top_mask, graded_layers(z0t, z1t, LAYERS_TOP[refinement], fmax, top_sigma, True),
                      top_sigma, top_lab)]
    for name, nlay, two in (("backside_cu", LAYERS_BACK[refinement], True), ("baseplate", LAYERS_BASE[refinement], False)):
        p = planes[name]
        m = _cells_in(Polygon(p.outline), X, Y)
        slabs.append(SlabSpec(name, m, graded_layers(p.z_bottom, p.z_bottom + p.thickness, nlay, fmax, p.sigma, two),
                              p.sigma))
    grid = Grid(xmin, ymin, ax, ay, nx, ny, slabs)
    # wires
    by_w: dict[int, list] = {}
    for s in cm.wires:
        by_w.setdefault(s.wire_index, []).append(s)
    wires, wnet = [], []
    for wi in sorted(by_w):
        sg = by_w[wi]
        pts = np.array([sg[0].p0] + [s.p1 for s in sg], float)
        wires.append(WireIn(f"w{wi}", pts, sg[0].diameter, sg[0].sigma))
        wnet.append(sg[0].net)
    dmax = max(w.diameter for w in wires)
    fs = build_filaments(wires, refinement, z_floor=z1t + LANDING_GAP * dmax)
    # nodes: dies are ideal shorts of their footprint cells; wire ends join the die or the landing cell
    nid = grid.node_id[0]
    shorts, die_node = [], []
    for d in cm.shorts:
        ci, cj = _nearest_cell(top_mask, xc, yc, d.x, d.y)
        lab = top_lab[ci, cj]
        m = top_mask & (top_lab == lab) & (np.abs(X - d.x) < d.w / 2) & (np.abs(Y - d.y) < d.h / 2)
        m[ci, cj] = True
        shorts.append(nid[m])
        die_node.append(int(nid[ci, cj]))

    def node_at(p, net):
        for k, d in enumerate(cm.shorts):
            if abs(p[0] - d.x) <= d.w / 2 and abs(p[1] - d.y) <= d.h / 2 and p[2] >= d.z_top - 1e-9:
                return die_node[k]
        lab = nets.index(net) + 1
        i = int(np.clip(np.floor((p[0] - xmin) / ax), 0, nx - 1))
        j = int(np.clip(np.floor((p[1] - ymin) / ay), 0, ny - 1))
        if not (top_mask[i, j] and top_lab[i, j] == lab):
            i, j = _nearest_cell(top_mask & (top_lab == lab), xc, yc, p[0], p[1])
        return int(nid[i, j])

    ends = np.array([[node_at(w.points[0], n), node_at(w.points[-1], n)] for w, n in zip(wires, wnet, strict=True)])
    pp, pn = cm.port.p_pos, cm.port.p_neg
    m_pos, m_neg = (top_mask & (top_lab == nets.index(n) + 1) for n in (DC_PLUS, DC_MINUS))
    port = (int(nid[_nearest_cell(m_pos, xc, yc, pp[0], pp[1])]), int(nid[_nearest_cell(m_neg, xc, yc, pn[0], pn[1])]))
    t0 = time.perf_counter()
    wg = WireGridPFFT(fs, grid) if coupling == "pfft" else WireGridDense(fs, grid)
    t_wg = time.perf_counter() - t0
    sys_ = LayoutSystem(fs, grid, wg, ends, shorts)
    sys_.set_stated()
    info = dict(nx=nx, ny=ny, cell_x=ax, cell_y=ay, layers=[len(s.layers) for s in slabs], n_wires=len(wires),
                filaments_per_wire=fs.nfil // len(wires), n_segments=int(fs.seg_p0.shape[0]), n_grid_unknowns=grid.n_g,
                clamped_vertices=fs.clamped, coupling=coupling, wire_grid_build_s=t_wg,
                n_near_pairs=int(getattr(wg, "near_pairs", 0)), pfft_near_cells=PFFT_NEAR)
    return sys_, port, info


def loop_inductance(layout, freqs_hz, refinement: int = 0) -> LoopResult:
    """Commutation-loop L(f) and R(f) at the port of ``Layout.to_conductors()`` (see the module docstring: refinement-0
    values carry discretisation errors of several percent that solver_tol does not cover).  One mesh per call, graded
    to max(F_MESH, max(freqs_hz)); provenance (tool_version, source_sha256), D0004 bounds and cost in meta."""
    freqs = np.asarray([float(f) for f in freqs_hz], float)
    if freqs.size == 0 or np.any(freqs <= 0):
        raise ValueError("freqs_hz must be non-empty and positive")
    t0, c0 = time.perf_counter(), time.process_time()
    fmesh = max(F_MESH, float(freqs.max()))
    sys_, port, info = build_layout_system(layout, fmesh, refinement)
    info["mesh_graded_to_hz"] = fmesh
    t1 = time.perf_counter()
    out = solve_system(sys_, [port], list(freqs))
    z = out.z[:, 0, 0]
    meta = dict(tool=TOOL_NAME, tool_version=TOOL_VERSION, source_sha256=source_sha256(),
                n_unknowns=int(sys_.n), n_filaments=int(sys_.nfil), mesh_params=info, refinement=int(refinement),
                solver_tol=out.solver_tol, tol_parts=out.parts, stated=sys_.stated, gmres_iters=out.iters,
                gmres_tol=GMRES_TOL, build_s=t1 - t0, wall_s=time.perf_counter() - t0, cpu_s=time.process_time() - c0,
                layout_fingerprint=layout.fingerprint())
    return LoopResult(L_H=np.imag(z) / (2.0 * np.pi * freqs), R_ohm=np.real(z), meta=meta)
