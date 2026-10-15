"""L2 layout path: Layout -> loop inductance of the finite-radius conductor model, precorrected-FFT wire <-> grid operator.

Model (SI, float64; quasi-static PEEC; skin / proximity effect through thickness layers and wire filaments; no image planes):

* Top-Cu traces, backside Cu and baseplate are three *slabs* on ONE shared lateral grid (cell-centred nodes, x- and
  y-branches) with graded thickness layers.  Every Cu-to-Cu block is block-Toeplitz and is applied by FFT with
  ``l2_core.plane_table`` / ``circulant_fft`` (Hoer-Love boxes near, Gauss beyond).
* Lattice alignment (``cell_fill``, T0075 founder re-scope I0039): every top-Cu rectangle of ``to_conductors()``, the
  backside-Cu and baseplate outlines and every die footprint must lie on cell boundaries of the requested refinement; a
  cell is then either full or empty, and the represented area of every net equals its copper area to rounding (test:
  <= 1e-12 at every refinement).  A layout that is not on the lattice raises ValueError (it is not approximated).  The
  generator puts every free parameter on its 0.5 mm design grid (``generate.halfbridge.DESIGN_GRID_MM``), the housing
  constants and the baseplate box -8..78 x -8..48 mm are on it too, and CELL = 0.5 / 0.25 / 0.125 mm divides it, so every
  generated layout is aligned at every level.  History: before attempt 3 a cell belonged to a trace when its centre was
  inside (DC+ area -4.2 % at 0.35 mm, exact at 0.25 mm); attempt 3 weighted partial cells by their fill fraction but kept
  their full inductive box, which read L 5-9 % low at the non-aligned 0.7 / 0.35 mm cells (founder diagnostic I0039,
  research/l2_layout_diag); both are gone.  A cell holding copper of two nets is refused (ValueError).
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
  segments matching the lattice); its tests compare it with the dense exact coupling ``WireGridDense``.  The exact near
  integrals evaluate the closed-form corner functions once per corner of the branch-box lattice (``BoxLattice``,
  neighbouring boxes share corners) and sum the 8 corners in ``box_potential``'s order: bit-identical values, ~3-8 x
  fewer transcendental evaluations.  Memory and time ~ O(wires x near box + grid log grid).
* Dies are ideal shorts (node merge of the footprint cells of ``DieShort.bottom_net`` only); a wire end on a die joins the
  die's node.  Bilinear point contacts (``Contact``, a model change made in T0075 attempt 2): a wire foot on a trace and the
  two port terminals of ``Layout.to_conductors()`` (on the DC+ / DC- nets) inject their current at their true lateral
  position, split over the four surrounding cell centres with bilinear weights (only cells of the contact's net; weights
  renormalised to sum 1; the nearest cell of the net if none of the four is).  Snapping a foot to the nearest cell centre
  moved the injection point by up to half a cell and stepped L by +-5 % under sub-cell shifts of the layout.
* Solve: GMRES (``l2_core.block_gmres``, block preconditioner; small systems: dense direct) and the rigorous
  a-posteriori bound of ``l2_core.a_posteriori``.  Restart GMRES_RESTART = 100, at most GMRES_MAXIT = 40 cycles (cap 4000
  iterations; the former 100 x 5 cap stopped the 0.125 mm solve of the founder diagnostic I0039 at solver_tol 1.2e-3).
* ``meta['solver_tol']`` (D0004 (i)) = a-posteriori + rounding + STATED bounds (derived, not measured), each applied
  to the block it bounds (``LayoutSystem.stated_parts``): plane tables; wire <-> grid operator (interpolation, Gauss,
  far disc rule); finite-radius remainders of near wire <-> grid and inter-wire pairs; rod-series truncation.
  The test layout reports ~5e-5 (refinement 0) and ~1e-4 (refinement 1); the DoD layout ~2e-5;
  ``test_solver_tol_usable_at_every_refinement`` checks < 1e-3 at every refinement (0.5 / 0.25 / 0.125 mm cells).

NOT in solver_tol (discretisation and model choices, D0004; convergence measured by T0075, docs/notes/o001-l2-layout-cost.md):
* Mesh (CELL, LAYERS_*, WIRE_EDGES).  The thickness layers (top Cu 10: Z_s within 1.6 % of the exact slab at 20 MHz,
  ``layered_surface_impedance`` vs ``slab_surface_impedance``) and the wire filaments are the same at every level; the
  ladder refines laterally only, on cells that divide the 0.5 mm design grid.  E002's level is K_STAR = 1 (0.25 mm).  Seed
  7 / 2 dies (interleaved), 20 MHz: L = 11.115 / 11.029 nH at 0.5 / 0.25 mm (-0.78 %); seed 11 / 2 dies (u_shaped) 12.835 /
  12.683 nH (-1.19 %).  Founder diagnostic I0039 (aligned u_shaped layout): 12.889 / 12.766 / 12.692 nH at 0.5 / 0.25 /
  0.125 mm (-0.96 %, -0.59 %: contracting).  The k_star -> k_star + 1 gate needs the 0.125 mm level (~35 GB): burst VM,
  ``benchmarks/l2_layout_cost.py --vm``.  R converges more slowly than L and is not a reference value.
* Grading frequency: layers are graded to the skin depth at max(F_MESH, max(freqs)), F_MESH = 100 MHz, so L(f) does
  not depend on which other frequencies are requested (<= 100 MHz).  The grading is itself a mesh choice: attempt 1
  graded to max(freqs), and L(20 MHz) of the DoD layout moved 2.6 % between grading at 20 and at 80 MHz (review T0082).
* Landing clamp: filament vertices stay >= LANDING_GAP x diameter above the top Cu (the foot joins its landing cell by a
  node merge).  DoD layout, refinement 0, 20 MHz: L = 11.654 / 11.649 / 11.645 nH for LANDING_GAP = 0.25 / 0.5 / 1.0
  (+-0.04 %); at 0.25 the thickest filament's end disc reaches the copper and the finite-radius bound becomes infinite.
* Ideal die shorts: footprint cells and wire start nodes are one node, so the 0.23 mm path through attach + die has
  zero impedance; as a solid 5.2 x 5.2 x 0.23 mm block its partial self inductance is 0.003 nH per die [HL] (~0.03 %
  of L).  The equipotential footprint (lateral short under the die) is a model assumption and is not bounded.

Cost (benchmarks/l2_layout_cost.py --quick, T0075 attempt 5, one solve per fresh process, 10-core 16 GB laptop; CPU = user
+ sys over all threads, +-25 % with machine load, memory pressure and core placement; GMRES_TOL 1e-7): seed 7 / 2 dies
0.5 mm 180 CPU-s, 2.3 GB, 133 GMRES iterations; 0.25 mm (k_star) 1162 CPU-s, 7.7 GB, 238 iterations; 6 dies at k_star
2011 CPU-s, 8.9 GB, 249 iterations.  At GMRES_TOL 1e-9 (attempt 4) the same solves took 216 / 1618 / 2286 CPU-s and 222 /
399 / 415 iterations with L equal to 5 digits.  See docs/notes/o001-l2-layout-cost.md (sensitivity, projections).

References: [G] Grover, Inductance Calculations (1946) ch. 7 (filament Neumann integrals, line potential); [HL] Hoer & Love,
J. Res. NBS 69C (1965) 127; [MW] Maxwell / Weaver (round rod); [W] Waldvogel, ZAMP 27 (1976) 867 and Nagaoka (1911)
(potential of a uniform prism / rectangle); [P] Pizzetti's mean-value expansion (Courant-Hilbert vol. II ch. IV);
[AT] Trefethen, Approximation Theory and Approximation Practice (2013) Thm 19.3.
"""
# ruff: noqa: E741  (l = layer index, I = line integral: names follow the formulas cited above)
from __future__ import annotations

import hashlib
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.fft as sfft
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import connected_components

from moduleforge.geometry import DC_MINUS, DC_PLUS
from moduleforge.solvers import l2_core as core

TOOL_NAME = "moduleforge-l2-layout"
TOOL_VERSION = "0.3.0"
MU0 = core.MU0
K4 = core.K4
PARALLEL_SIN_EXACT = 1e-12  # |sin(angle)| below this: parallel-filament form (geometry error O(sin), <= 2e-12 relative)
NEAR_PARALLEL_SIN = 1e-3  # |sin| below this (and above PARALLEL_SIN_EXACT): tilt-family interpolation (``segment_mutual``)
NEAR_PARALLEL_THETA0 = 1.5e-3  # rad: interpolation nodes at 0, +-1, 2, 3 x this (closed form accurate there)
PARALLEL_REL = 1e-9  # stated relative bound of the parallel-filament form (dperp floor 1e-9 l for touching collinear pairs)
NEAR_PARALLEL_REL = 1e-7  # stated relative bound of ``segment_mutual`` in the near-parallel band (counted in solver_tol)
MAX_REFINEMENT = 2

# Lateral ladder (founder re-scope I0039): nested cells that divide the generator's 0.5 mm design grid, so every feature of
# a generated layout lies on cell boundaries at every level; the thickness layers and the wire filaments are held at the
# counts that resolve the 20 MHz skin depth (T0075 attempt 3's level 3: top-Cu Z_s within 1.6 %, benchmarks/l2_layout_cost.py)
# at every level, so a refinement step is purely lateral.
# per refinement 0..2: lateral cell [m]; thickness layers of top Cu / backside / baseplate; wire annulus edges (units of r)
CELL = (0.5e-3, 0.25e-3, 0.125e-3)
LAYERS_TOP = (10, 10, 10)
LAYERS_BACK = (6, 6, 6)
LAYERS_BASE = (6, 6, 6)
WIRE_EDGES = ((0, .35, .6, .8, .93, 1),) * 3
K_STAR = 1  # E002's level (0.25 mm cells): the gates of T0075 apply here; k_star - 1 / k_star + 1 measure convergence
ALIGN_TOL = 1e-9  # a cell's covered fraction must be within this of 0 or 1 (round-off where an edge meets a cell edge)
WIRE_PHI = 6  # filaments per ring
LANDING_GAP = 0.5  # wire filaments are kept >= LANDING_GAP * diameter above the top-Cu surface (modelling clamp)
PFFT_NEAR = 18  # cells: branches within this Chebyshev distance of a wire are coupled exactly (minimum; see PFFT_NEAR_RADII)
PFFT_NEAR_RADII = 20.0  # c: the near box is also >= c x the largest filament radius wide, D_f = (near - 1) cells >= c rmax (stated
# choice: far disc-rule bound 2 q^4 / (1 - q) with q = rmax / (D_f - 2 rmax) <= 2 / (c - 2)^4 = 1.9e-5, independent of refinement)
NODE_GAUSS_TOL = 1e-6  # target of the node Gauss bound of the far field (stated choice; was a fixed order 4)
PFFT_STENCIL = 8  # lateral Lagrange points per axis
PFFT_STENCIL_Z = 4
PFFT_DZ = 0.4e-3  # virtual z-level spacing (cap)
PFFT_DZ_CELLS = 0.4  # virtual z-level spacing in lateral cells
CHUNK_ELEMS = 4e5  # boxes x Gauss points evaluated at once in ``line_box_integral`` (memory of ~20 temporaries each)
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


def _mutual_general_or_parallel(p0, p1, q0, q1, par):
    """Closed form of Grover (1946) for the pairs with ``par`` False, the parallel-filament form (``core.fil_F``; also
    collinear / touching filaments) where ``par`` is True.  All arguments broadcast; ``par`` is a bool array."""
    u, v, d = p1 - p0, q1 - q0, q0 - p0
    l1, l2 = np.linalg.norm(u, axis=-1), np.linalg.norm(v, axis=-1)
    u, v = u / l1[..., None], v / l2[..., None]
    c = np.sum(u * v, axis=-1)
    sg2 = np.sum(np.cross(u, v) ** 2, axis=-1)  # sin^2 without the cancellation of 1 - c^2
    sg2s = np.where(par, 1.0, sg2)
    sg = np.sqrt(sg2s)
    p = -np.sum(d * u, axis=-1)
    q = np.sum(d * v, axis=-1)
    w = np.sum(d * d, axis=-1)
    s0 = -(p + c * q) / sg2s
    t0 = -(q + c * p) / sg2s
    # line distance h = |d . (u x v)| / sin: w + p s0 + q t0 cancels like 1e-16 / sin^2 and gives h ~ 1e-8 l / sin for touching
    # near-parallel filaments (error 5e-6 at sin = 1.5e-3, review T0083 band), this form has no such cancellation
    h2 = np.sum(d * np.cross(u, v), axis=-1) ** 2 / sg2s
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


def segment_sin(p0, p1, q0, q1):
    """|sin| of the angle between the segments p0->p1 and q0->q1 (cross product: accurate for nearly parallel pairs)."""
    u, v = p1 - p0, q1 - q0
    cr = np.linalg.norm(np.cross(u, v), axis=-1)
    return cr / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1))


def _closest_params(p0, p1, q0, q1):
    """Parameters (s, t) in [0, 1] of the closest points of segments p0-p1 and q0-q1 (Ericson 5.1.9); (s, t) = a closest pair
    also for parallel segments."""
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e = np.sum(d1 * d1, -1), np.sum(d2 * d2, -1)
    b, c, f = np.sum(d1 * d2, -1), np.sum(d1 * r, -1), np.sum(d2 * r, -1)
    den = a * e - b * b
    ok = den > 1e-12 * a * e
    s = np.where(ok, np.clip((b * f - c * e) / np.where(ok, den, 1.0), 0.0, 1.0), 0.0)
    t = (b * s + f) / e
    s = np.where(t < 0, np.clip(-c / a, 0, 1), np.where(t > 1, np.clip((b - c) / a, 0, 1), s))
    t = np.clip(t, 0.0, 1.0)
    return s, t


def _lagrange_at(x, nodes, vals):
    """Value at x (n,) of the polynomial through (nodes (m,), vals (m, n))."""
    out = np.zeros_like(x)
    for k, xk in enumerate(nodes):
        w = np.ones_like(x)
        for j, xj in enumerate(nodes):
            if j != k:
                w = w * (x - xj) / (xk - xj)
        out = out + w * vals[k]
    return out


def segment_mutual(p0, p1, q0, q1):
    """Mutual partial inductance (H) of two straight filaments p0->p1 and q0->q1 (broadcasting (..., 3) arrays) carrying
    unit current in the direction of travel: K4 cos(eps) int int ds dt / R  (Neumann).

    * |sin eps| >= NEAR_PARALLEL_SIN: closed form of Grover (1946).  Its corner terms cancel like 1e-16 / sin^2 (relative
      error 4.8e-9 at sin = 1e-5, <= 1e-11 at 1e-3, review T0083).
    * |sin eps| < PARALLEL_SIN_EXACT: the parallel-filament form (``core.fil_F``; also covers collinear and touching
      filaments), geometry error O(sin) <= 2e-12 relative.
    * in between (the near-parallel band): the pair is the member eps of the one-parameter family obtained by tilting q
      about its point closest to p, M(theta), which is analytic in theta (also for touching filaments, whose pivot is the
      shared point).  M is evaluated at theta = 0 by the parallel form and at theta = +-1.5, 3, 4.5 mrad by the closed form
      (accurate there) and interpolated by the degree-6 Lagrange polynomial at the pair's own theta (test: <= 1e-8 relative
      against adaptive quadrature, ``NEAR_PARALLEL_REL`` is the stated bound counted in solver_tol)."""
    p0, p1, q0, q1 = (np.asarray(v, dtype=np.float64) for v in np.broadcast_arrays(*(np.asarray(v, dtype=np.float64)
                                                                                      for v in (p0, p1, q0, q1))))
    sin = segment_sin(p0, p1, q0, q1)
    band = (sin < NEAR_PARALLEL_SIN) & (sin >= PARALLEL_SIN_EXACT)
    par = sin < PARALLEL_SIN_EXACT
    out = _mutual_general_or_parallel(p0, p1, q0, q1, par | band)
    out = np.where(band, 0.0, out)
    if np.any(band):
        P0, P1, Q0, Q1 = (a[band] for a in (p0, p1, q0, q1))
        out[band] = _near_parallel_band(P0, P1, Q0, Q1)
    return out


def _near_parallel_band(p0, p1, q0, q1):
    """``segment_mutual`` of the pairs in the near-parallel band (1-D arrays of pairs): see its docstring."""
    u, v = p1 - p0, q1 - q0
    l1, l2 = np.linalg.norm(u, axis=-1), np.linalg.norm(v, axis=-1)
    u, v = u / l1[:, None], v / l2[:, None]
    flip = np.sum(u * v, axis=-1) < 0  # antiparallel: reverse q (M changes sign)
    q0f, q1f = np.where(flip[:, None], q1, q0), np.where(flip[:, None], q0, q1)
    v = np.where(flip[:, None], -v, v)
    _, t = _closest_params(p0, p1, q0f, q1f)
    pivot = q0f + t[:, None] * (q1f - q0f)
    vperp = v - np.sum(v * u, axis=-1)[:, None] * u
    n = vperp / np.linalg.norm(vperp, axis=-1)[:, None]
    eps = np.arctan2(np.linalg.norm(vperp, axis=-1), np.sum(v * u, axis=-1))

    def tilted(theta):
        vt = np.cos(theta)[:, None] * u + np.sin(theta)[:, None] * n
        return pivot - (t * l2)[:, None] * vt, pivot + ((1.0 - t) * l2)[:, None] * vt

    nodes = NEAR_PARALLEL_THETA0 * np.arange(-3, 4)
    vals = []
    for th in nodes:
        a0, a1 = tilted(np.full(p0.shape[0], th))
        if th == 0.0:
            vals.append(_mutual_general_or_parallel(p0, p1, a0, a1, np.ones(p0.shape[0], bool)))
        else:
            vals.append(_mutual_general_or_parallel(p0, p1, a0, a1, np.zeros(p0.shape[0], bool)))
    m = _lagrange_at(eps, nodes, np.array(vals))
    return np.where(flip, -m, m)


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


def _corner_sum(F, corners, grad_form: bool = False):
    """[[[F]]] of corner values F (ncorner, ...) for boxes whose 8 corners are the rows ``corners`` (8 index arrays, in
    ``np.ndindex(2, 2, 2)`` order of (x, y, z) = (lo, hi)): the signed sum over the corners (hi minus lo in x, y and z),
    taken in the corner order and with the arithmetic of ``box_potential`` (tot + s F) or, ``grad_form``, of ``box_grad``
    (g - s F), so the values are the same to the last bit."""
    tot = 0.0
    for (ia, ib, ic), rows in zip(np.ndindex(2, 2, 2), corners, strict=True):
        s = (-1.0) ** (3 - ia - ib - ic)
        f = np.take(F, rows, axis=0)
        tot = tot - s * f if grad_form else tot + s * f
    return tot


@dataclass
class BoxLattice:
    """Boxes whose corners lie on a lattice X (nX,) x Y (nY,) x Z (nZ,): box b spans X[ix0[b]]..X[ix0[b]+1], Y[iy0[b]]..
    Y[iy0[b]+1], Z[iz0[b]]..Z[iz1[b]].  The branch boxes of one direction of the shared grid are such a family, and
    neighbouring boxes share corners, so a closed-form corner function evaluated once per lattice corner (and differenced)
    gives every box: ~8 x fewer transcendental evaluations than box by box (``box_potential``, ``box_grad``), same values
    up to rounding."""
    X: np.ndarray
    Y: np.ndarray
    Z: np.ndarray
    ix0: np.ndarray
    iy0: np.ndarray
    iz0: np.ndarray
    iz1: np.ndarray

    def lo_hi(self):
        lo = np.stack([self.X[self.ix0], self.Y[self.iy0], self.Z[self.iz0]], 1)
        hi = np.stack([self.X[self.ix0 + 1], self.Y[self.iy0 + 1], self.Z[self.iz1]], 1)
        return lo, hi

    def sub(self, idx):
        return BoxLattice(self.X, self.Y, self.Z, self.ix0[idx], self.iy0[idx], self.iz0[idx], self.iz1[idx])

    def window(self):
        """(slices of the corner lattice covering the boxes, the 8 corner index arrays of every box into the flattened
        window, ``np.ndindex(2, 2, 2)`` order)."""
        bx0, bx1 = int(self.ix0.min()), int(self.ix0.max()) + 2
        by0, by1 = int(self.iy0.min()), int(self.iy0.max()) + 2
        bz0, bz1 = int(self.iz0.min()), int(self.iz1.max()) + 1
        ny, nz = by1 - by0, bz1 - bz0
        ix, iy, iz0, iz1 = self.ix0 - bx0, self.iy0 - by0, self.iz0 - bz0, self.iz1 - bz0
        corners = [((ix + ia) * ny + iy + ib) * nz + (iz1 if ic else iz0) for ia, ib, ic in np.ndindex(2, 2, 2)]
        return (slice(bx0, bx1), slice(by0, by1), slice(bz0, bz1)), corners


def lattice_potential(pts, lat: BoxLattice, chunk_elems: float = 4e5):
    """``box_potential`` of every box of ``lat`` at the points ``pts`` (np, 3): (nb, np) C-ordered, from corner values of
    ``_G`` (one evaluation per lattice corner instead of 8 per box)."""
    (sx, sy, sz), corners = lat.window()
    X, Y, Z = lat.X[sx], lat.Y[sy], lat.Z[sz]
    ncor = X.size * Y.size * Z.size
    step = max(1, int(chunk_elems // max(ncor, 1)))
    out = np.empty((lat.ix0.size, pts.shape[0]))
    for s in range(0, pts.shape[0], step):
        p = pts[s:s + step]
        G = _G(X[:, None, None, None] - p[None, None, None, :, 0], Y[None, :, None, None] - p[None, None, None, :, 1],
               Z[None, None, :, None] - p[None, None, None, :, 2])  # (nX, nY, nZ, npc)
        out[:, s:s + step] = _corner_sum(G.reshape(ncor, -1), corners)
    return out


def lattice_grad(p, lat: BoxLattice):
    """``box_grad`` of every box of ``lat`` at the point p (3,): (nb, 3), from corner values of ``_H``."""
    (sx, sy, sz), corners = lat.window()
    x = (lat.X[sx] - p[0])[:, None, None]
    y = (lat.Y[sy] - p[1])[None, :, None]
    z = (lat.Z[sz] - p[2])[None, None, :]
    x, y, z = np.broadcast_arrays(x, y, z)
    g = [_corner_sum(_H(a, b, c).ravel(), corners, True) for a, b, c in ((x, y, z), (y, z, x), (z, x, y))]
    return np.stack(np.broadcast_arrays(*g), axis=-1)


def rod_box_correction(p0, p1, a, lo, hi, grad0=None, grad1=None):
    """Finite-radius correction of int_seg ds M_a[phi] (rod of radius a on the axis p0 -> p1, phi = ``box_potential`` of the
    boxes lo..hi (nb, 3), harmonic in the rod) relative to the centre-line integral of ``line_box_integral``: by the identity
    of ``rod_pair_correction``, -(a^2/8) [u.grad phi]_{p0}^{p1} (``box_grad``); stated remainder (a^4/192) sum_ends sup_disc
    |d_u^3 phi| <= (a^4/32) sum_ends B with B >= int_box dV/r^4 for every point of the end disc: B = min(V/D^4, pi (1/h0 -
    1/h1)) (D = point-box distance - a; h0 = vertical gap - a, h1 = h0 + box height: the slab integral of 1/r^4).
    Returns (correction, remainder bound), both (nb,) in the units of the line integral (m^3); an end disc that reaches a
    box gives an infinite bound.  ``grad0`` / ``grad1``: precomputed ``box_grad`` at p0 / p1 (``lattice_grad``)."""
    p0, p1, lo, hi = (np.asarray(v, float) for v in (p0, p1, lo, hi))
    u = (p1 - p0) / np.linalg.norm(p1 - p0)
    g0 = box_grad(*p0, lo, hi) if grad0 is None else grad0
    g1 = box_grad(*p1, lo, hi) if grad1 is None else grad1
    corr = -(a * a / 8.0) * (g1 @ u - g0 @ u)
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


def line_box_integral(a, b, lo, hi, tol: float = LINE_TOL, chunk: int = 4096, lat: BoxLattice | None = None):
    """I[k] = int_a^b ds int_box_k dV' / R  (box potential integrated along the straight segment a -> b), composite Gauss
    with an order and panel count chosen per distance class so that the stated Gauss bound [AT Thm 19.3, assumption
    ``core.ELLIPSE_M``] is <= tol.  Returns (I, bound, d_lb) with bound the largest stated relative bound used and d_lb the
    per-box lower bound of the distance to the segment.  With ``lat`` (the same boxes as a ``BoxLattice``) the box
    potentials of each distance class come from shared corner values (``lattice_potential``): same rule, same bound."""
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
        if lat is not None:
            out[idx] = lattice_potential(pts, lat.sub(idx), CHUNK_ELEMS) @ ws
            continue
        step = max(32, min(chunk, int(CHUNK_ELEMS // xs.size)))  # bounded temporaries (boxes x Gauss points)
        for s in range(0, idx.size, step):
            ii = idx[s:s + step]
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
        sn = segment_sin(fs.seg_p0[sl, None, :], fs.seg_p1[sl, None, :], fs.seg_p0[None, :, :], fs.seg_p1[None, :, :])
        kern = np.where(sn >= NEAR_PARALLEL_SIN, 0.0, np.where(sn < PARALLEL_SIN_EXACT, PARALLEL_REL, NEAR_PARALLEL_REL))
        eb = np.where(inter, rem, 0.0) + kern * np.abs(m)  # + stated kernel bound of the near-parallel / parallel forms
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


def _overlap_1d(lo: float, hi: float, edges: np.ndarray) -> np.ndarray:
    """Length of [lo, hi] inside every interval [edges[i], edges[i + 1]]."""
    return np.maximum(0.0, np.minimum(hi, edges[1:]) - np.maximum(lo, edges[:-1]))


def rect_cover(rects, xe: np.ndarray, ye: np.ndarray) -> np.ndarray:
    """Covered area (m^2) of every cell of the lattice with cell edges xe (nx + 1,), ye (ny + 1,) by DISJOINT axis-aligned
    rectangles (x0, y0, x1, y1): the overlap of a rectangle with a cell is the product of the two 1-D overlaps, so the sum
    over rectangles is exact up to rounding (the 1-D overlaps of one rectangle telescope to its side lengths)."""
    A = np.zeros((xe.size - 1, ye.size - 1))
    for x0, y0, x1, y1 in rects:
        ox, oy = _overlap_1d(x0, x1, xe), _overlap_1d(y0, y1, ye)
        i, j = np.flatnonzero(ox), np.flatnonzero(oy)
        A[np.ix_(i, j)] += np.outer(ox[i], oy[j])
    return A


def _snap_aligned(F: np.ndarray, what: str, xe: np.ndarray, ye: np.ndarray) -> np.ndarray:
    """Covered fractions F (nx, ny) of the cells of the lattice with edges xe, ye -> exactly 0 or 1.  A fraction farther than
    ALIGN_TOL from both means that ``what`` has an edge inside a cell, i.e. it is not on the lattice: ValueError (no partial
    cells, founder re-scope I0039)."""
    bad = (F > ALIGN_TOL) & (F < 1.0 - ALIGN_TOL)
    if np.any(bad):
        i, j = (int(v[0]) for v in np.nonzero(bad))
        raise ValueError(f"{what} is not on the lattice: cell ({i}, {j}) at x {xe[i] * 1e3:.4f}..{xe[i + 1] * 1e3:.4f} mm, "
                         f"y {ye[j] * 1e3:.4f}..{ye[j + 1] * 1e3:.4f} mm is {F[i, j]:.6f} covered; every feature must lie on "
                         f"cell boundaries (cell {(xe[1] - xe[0]) * 1e3:.4g} x {(ye[1] - ye[0]) * 1e3:.4g} mm)")
    return (F >= 0.5).astype(float)


def check_on_lattice(x0: float, x1: float, y0: float, y1: float, xmin: float, ymin: float, ax: float, ay: float,
                     what: str) -> None:
    """ValueError unless the rectangle [x0, x1] x [y0, y1] has its edges on cell boundaries (within ALIGN_TOL of a cell)."""
    for v, o, a, ax_name in ((x0, xmin, ax, "x"), (x1, xmin, ax, "x"), (y0, ymin, ay, "y"), (y1, ymin, ay, "y")):
        u = (v - o) / a
        if abs(u - round(u)) > ALIGN_TOL * max(1.0, abs(u)):
            raise ValueError(f"{what} is not on the lattice: its {ax_name} edge {v * 1e3:.4f} mm is {u - math.floor(u):.4f} "
                             f"cells past a cell boundary (cell {a * 1e3:.4g} mm)")


def cell_fill(cm, xmin: float, ymin: float, ax: float, ay: float, nx: int, ny: int) -> dict:
    """Cells of the lattice carrying the conductors of ``cm`` (``Layout.to_conductors()``): per cell the fraction of its
    area covered by top Cu (per net) / backside Cu / baseplate (``rect_cover`` of the disjoint top-Cu rectangles and of the
    rectangle decomposition of each plane outline), which must be 0 or 1 (``_snap_aligned``: ValueError when a feature is
    not on the lattice).  Returns {'top': (frac, label, nets), 'backside_cu': frac, 'baseplate': frac, 'area': {name:
    (represented, exact)}}, frac in {0., 1.}, label = net index + 1 (0: no copper).  A cell that holds copper of two nets
    cannot be represented (one unknown per branch and layer): ValueError (checked first)."""
    from shapely.geometry import Polygon

    from moduleforge.geometry.conductors import decompose_polygon
    xe = xmin + np.arange(nx + 1) * ax
    ye = ymin + np.arange(ny + 1) * ay
    ca = ax * ay
    nets = sorted({r.net for r in cm.rects})
    per = []
    area = {}
    for net in nets:
        rr = [(r.x0, r.y0, r.x1, r.y1) for r in cm.rects if r.net == net]
        per.append(rect_cover(rr, xe, ye) / ca)
        area[net] = (0.0, float(sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rr)))
    P = np.array(per) if per else np.zeros((0, nx, ny))
    occ = (P > ALIGN_TOL).sum(axis=0)
    if np.any(occ > 1):
        i, j = (int(v[0]) for v in np.nonzero(occ > 1))
        both = [nets[k] for k in range(len(nets)) if P[k, i, j] > ALIGN_TOL]
        raise ValueError(f"cell ({i}, {j}) holds copper of nets {both}: the gap between them is narrower than one cell "
                         f"({ax * 1e3:.3f} x {ay * 1e3:.3f} mm); refine")
    P = np.array([_snap_aligned(F, f"the {net} trace", xe, ye) for F, net in zip(P, nets, strict=True)]) if per else P
    for F, net in zip(P, nets, strict=True):
        area[net] = (float(F.sum() * ca), area[net][1])
    occ = (P > 0).sum(axis=0)
    frac = P.sum(axis=0) if per else np.zeros((nx, ny))
    label = np.where(occ > 0, np.argmax(P > 0, axis=0) + 1, 0) if per else np.zeros((nx, ny), np.int64)
    out = dict(top=(frac, label.astype(np.int64), nets), area=area)
    for p in cm.planes:
        poly = Polygon(p.outline)
        try:
            rr = decompose_polygon(poly)
            F = rect_cover(rr, xe, ye) / ca
        except ValueError:  # not rectilinear: exact polygon clipping per cell
            import shapely
            cells = shapely.box(xe[:-1, None], ye[None, :-1], xe[1:, None], ye[None, 1:])
            F = shapely.area(shapely.intersection(cells, poly)) / ca
        F = _snap_aligned(F, f"the {p.name} outline", xe, ye)
        out[p.name] = F
        area[p.name] = (float(F.sum() * ca), float(poly.area))
    return out


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


def slab_surface_impedance(thickness: float, f: float, sigma: float) -> complex:
    """Exact internal impedance per square (Ohm) of a conducting slab of ``thickness`` with the field on one face only (the
    other face field-free): Z = (k / sigma) coth(k t), k = (1 + j) / delta [RWV] 5.6.  Low-frequency limit 1/(sigma t) +
    j omega mu0 t / 3; thick limit (1 + j) / (sigma delta)."""
    k = (1.0 + 1.0j) / core.skin(f, sigma)
    return complex(k / sigma / np.tanh(k * thickness))


def layered_surface_impedance(thick_from_face, f: float, sigma: float) -> complex:
    """The same internal impedance for the slab cut into layers of uniform current density (the thickness layers of a
    slab here, listed from the excited face): the 1-D PEEC of the layers.  Layer i, depths [e_i, e_i+1], density J_i:
    J_i / sigma + j omega <Phi>_i = E (equal for all layers, parallel), sum t_i J_i = I, Z = E / I, with Phi(z) = mu0
    int_0^z H the flux per unit length between the face and depth z and H(z) = int_z^T J (field-free far face).  Layer
    averages of Phi in closed form (piecewise quadratic): <Phi_j>_i / mu0 = t_j (e_i + e_i+1)/2 (i above j), t_j (e_j +
    t_j/2) (i below j), t_j (e_j + t_j/3) (i = j).  Converges to ``slab_surface_impedance`` as the layers shrink."""
    t = np.asarray(thick_from_face, float)
    e = np.concatenate([[0.0], np.cumsum(t)])
    n = t.size
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    G = np.where(i < j, t[j] * 0.5 * (e[i] + e[i + 1]), np.where(i > j, t[j] * (e[j] + 0.5 * t[j]), t[j] * (e[j] + t[j] / 3.0)))
    A = np.zeros((n + 1, n + 1), complex)
    A[:n, :n] = np.eye(n) / sigma + 1j * 2.0 * math.pi * f * MU0 * G
    A[:n, n] = -1.0
    A[n, :n] = t
    rhs = np.zeros(n + 1, complex)
    rhs[n] = 1.0
    return complex(np.linalg.solve(A, rhs)[n])


# Assembly threads: the kernel assembly is many mid-size numpy calls that hold the GIL between them; measured on the DoD layout
# (refinement 0) 4 threads gave wall 31 s vs 28 s and CPU 72 s vs 28 s, so the default is serial (CPU-s is the gated cost).
# FFT workers: pocketfft threads do not spin; the CPU cost is the same as serial.
NTHREADS = max(1, int(os.environ.get("MF_L2_THREADS", 1)))
FFT_WORKERS = max(1, int(os.environ.get("MF_L2_FFT_WORKERS", min(4, os.cpu_count() or 1))))
TABLE_TEMP_BUDGET = 2.5e9  # bytes: concurrent plane-table temporaries (``layer_pair_tables``) are kept under this


def _pool_map(fn, items, workers: int):
    """Thread map (numpy / scipy.fft release the GIL on large arrays); serial for one worker."""
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        return [fn(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def circulant_half(T: np.ndarray) -> np.ndarray:
    """Half spectrum, real, laid out (ij, a, b), of the (2 n1, 2 n2) symmetric circulant embedding of the offset table
    T[a, b, di, dj].  The embedding is even in both axes, so its DFT is real and the ``rfft2`` half (2 n1 x (n2 + 1)) carries
    all of it: half the memory of ``l2_core.circulant_fft`` and no complex copy.  Built one output layer at a time."""
    na, nb, n1, n2 = T.shape
    out = np.empty((2 * n1 * (n2 + 1), na, nb))
    for a in range(na):
        full = np.zeros((nb, 2 * n1, 2 * n2))
        full[:, :n1, :n2] = T[a]
        full[:, n1 + 1:, :n2] = T[a][:, :0:-1, :]
        full[:, :n1, n2 + 1:] = T[a][:, :, :0:-1]
        full[:, n1 + 1:, n2 + 1:] = T[a][:, :0:-1, :0:-1]
        out[:, a, :] = sfft.rfft2(full, axes=(1, 2), workers=FFT_WORKERS).real.reshape(nb, -1).T
    return out


def circulant_apply_half(Th: np.ndarray, X: np.ndarray, transposed: bool = False) -> np.ndarray:
    """y = T x for ``circulant_half`` tables (X (nb, n1, n2), real or complex).  The multiplication is one real batched
    matmul over (re, im) columns (``l2_core.circulant_apply`` casts the whole table to complex at every call)."""
    nb, n1, n2 = X.shape
    cplx = np.iscomplexobj(X)
    Xs = np.stack([X.real, X.imag]) if cplx else X[None]
    c = Xs.shape[0]
    Xh = sfft.rfft2(Xs, s=(2 * n1, 2 * n2), axes=(2, 3), workers=FFT_WORKERS).reshape(c, nb, -1)  # (c, nb, F)
    V = np.empty((Xh.shape[2], nb, 2 * c))
    V[:, :, 0::2] = Xh.real.transpose(2, 1, 0)
    V[:, :, 1::2] = Xh.imag.transpose(2, 1, 0)
    Y = np.matmul(Th.transpose(0, 2, 1) if transposed else Th, V)  # (F, na, 2c)
    na = Y.shape[1]
    Yc = (Y[:, :, 0::2] + 1j * Y[:, :, 1::2]).transpose(2, 1, 0).reshape(c, na, 2 * n1, n2 + 1)
    y = sfft.irfft2(Yc, s=(2 * n1, 2 * n2), axes=(2, 3), workers=FFT_WORKERS)[:, :, :n1, :n2]
    return y[0] + 1j * y[1] if cplx else y[0]


FAR_CHUNK_ELEMS = 6e6  # doubles per chunk of the far-field table tensor (memory ~ 10 x this x 8 B)


def pair_table(z1, z2, a_al, a_tr, n1, n2, near: int | None = None):
    """``core.plane_table([z1], [z2], a_al, a_tr, n1, n2)[0, 0]`` and its stated bound, evaluated with two changes that leave
    every value and the stated bound unchanged:
    * the far entries (beyond ``near`` cells; same Gauss rule over both cross-sections, same stated bound) need the
      antiderivative g(u, d) of ``core.gfun`` at the axial positions u_m = m a_al only once per m = -1..n1 (the second
      difference g(u_{di+1}) + g(u_{di-1}) - 2 g(u_di) of the core evaluates it three times), summed over the Gauss points
      first and differenced afterwards (linear, the same cancellation per point);
    * the tensors are built in chunks of lateral offsets (bounded memory: the core builds the whole
      (n1 n2, 2 order_y, order_z^2) tensor at once, ~1 GB per pair at refinement 2).
    The near block (Hoer-Love, double-double) is the core's own, taken from a ``near + 1`` sized call."""
    near = core.N_NEAR if near is None else near
    mn1, mn2 = min(n1, near + 1), min(n2, near + 1)
    T0, bound0, _ = core.plane_table_full([z1], [z2], a_al, a_tr, mn1, mn2, near)
    if n1 <= near + 1 and n2 <= near + 1:
        return T0[0, 0], bound0
    dmin = near * min(a_al, a_tr)
    h_y = 0.5 * a_tr
    ny_ord = core.gauss_order(1.0 + dmin / h_y)
    tn, wn = core.gq(ny_ord, -a_tr, 0.0)
    tp_, wp_ = core.gq(ny_ord, 0.0, a_tr)
    tt = np.concatenate([tn, tp_])
    wt = np.concatenate([wn * (a_tr + tn), wp_ * (a_tr - tp_)]) / (a_tr * a_tr)
    za, wza, bza, _ = core.z_rule(*z1, dmin)
    zb, wzb, bzb, _ = core.z_rule(*z2, dmin)
    dz = (zb[None, :] - za[:, None]).ravel()
    w_tz = np.outer(wt, np.outer(wza, wzb).ravel())  # (nt, nzz)
    bound = core.gauss_bound(ny_ord, 1.0 + dmin / h_y) + bza + bzb
    u = a_al * np.arange(-1, n1 + 1)  # axial positions m = -1 .. n1
    T = np.zeros((n1, n2))
    cj = int(max(1, FAR_CHUNK_ELEMS // ((n1 + 2) * tt.size * dz.size)))
    for j0 in range(0, n2, cj):
        dj = np.arange(j0, min(n2, j0 + cj))
        dtr = dj[:, None] * a_tr + tt[None, :]  # (cj, nt)
        d = np.maximum(np.hypot(dtr[:, :, None], dz[None, None, :]), 1e-300)  # (cj, nt, nzz)
        G = np.einsum("mjtz,tz->mj", core.gfun(u[:, None, None, None], d[None]), w_tz)  # (n1 + 2, cj)
        T[:, dj] = K4 * (G[2:] + G[:-2] - 2.0 * G[1:-1])
    T[:mn1, :mn2] = T0[0, 0]
    return T, bound


def layer_pair_tables(layers, a_al, a_tr, n1, n2, group: int | None = None):
    """``core.plane_table(layers, layers, ...)`` for the upper triangle of layer pairs; the lower triangle by reciprocity (the
    mutual of two parallel boxes is symmetric under exchange of the boxes).  Pairs are deduplicated by their geometry: the
    mutual of two boxes with the same lateral footprint depends only on the two thicknesses and |z-centre distance| (mirror
    symmetry z -> -z), so symmetric stacks and repeated layer pairs are evaluated once (the stated bound is still summed over
    every pair, as before).  Distinct pairs run in threads, ``group`` at a time (default: as many as ``TABLE_TEMP_BUDGET``
    bytes of Gauss temporaries allow).  Returns (T, summed stated bound)."""
    nL = len(layers)
    thick = np.array([z1 - z0 for z0, z1 in layers])
    zc = np.array([0.5 * (z0 + z1) for z0, z1 in layers])
    keys = {}
    pairs = []
    for la in range(nL):
        for lb in range(la, nL):
            k = (*sorted((round(thick[la] * 1e12), round(thick[lb] * 1e12))), round(abs(zc[la] - zc[lb]) * 1e12))
            pairs.append((la, lb, keys.setdefault(k, (la, lb))))
    uniq = sorted(set(v for v in keys.values()))
    if group is None:
        temp = 8.0 * n1 * n2 * 24 * 6  # nfar x (2 order_y) x (nz^2) doubles x ~6 live arrays, order of magnitude
        group = int(max(1, min(NTHREADS, TABLE_TEMP_BUDGET // max(temp, 1.0))))

    def one(pr):
        la, lb = pr
        t, b = pair_table(layers[la], layers[lb], a_al, a_tr, n1, n2)
        return pr, t, b

    res = {pr: (t, b) for pr, t, b in _pool_map(one, uniq, group)}
    T = np.zeros((nL, nL, n1, n2))
    bound = 0.0
    for la, lb, rep in pairs:
        t, b = res[rep]
        T[la, lb] = T[lb, la] = t
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
            self.thr.append(circulant_half(T))
            self.plane_bound = max(self.plane_bound, b)
        self._boxes()

    def cell_xy(self):
        return (self.x0 + (np.arange(self.nx) + 0.5) * self.ax, self.y0 + (np.arange(self.ny) + 0.5) * self.ay)

    def _boxes(self):
        xc, yc = self.cell_xy()
        z0 = np.array([z[0] for z in self.layers])
        z1 = np.array([z[1] for z in self.layers])
        # branch boxes as corner lattices (``BoxLattice``): x-branch (l, i, j) spans cell centres i..i+1 in x, the cell edges
        # of row j in y; y-branch (l, j, i) the cell edges of column i in x, cell centres j..j+1 in y; z = layer faces
        zu = np.unique(np.concatenate([z0, z1]))
        zi0, zi1 = np.searchsorted(zu, z0), np.searchsorted(zu, z1)
        xe = self.x0 + np.arange(self.nx + 1) * self.ax
        ye = self.y0 + np.arange(self.ny + 1) * self.ay
        l, i, j = np.nonzero(self.valid[0])
        self.bx_lij = (l, i, j)
        self.lat = [BoxLattice(xc, ye, zu, i, j, zi0[l], zi1[l])]
        self.bx_lo, self.bx_hi = self.lat[0].lo_hi()
        self.bx_A = self.ay * self.thick[l]
        l, j, i = np.nonzero(self.valid[1])
        self.by_lij = (l, j, i)
        self.lat.append(BoxLattice(xe, yc, zu, i, j, zi0[l], zi1[l]))
        self.by_lo, self.by_hi = self.lat[1].lo_hi()
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
            y = circulant_apply_half(self.thr[d], full)
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

    NG = 4  # minimum node order along a segment; raised per instance until the node Gauss bound is <= NODE_GAUSS_TOL

    def __init__(self, fs: FilamentSet, grid: Grid, near: int | None = None):
        if near is None:
            near = max(PFFT_NEAR, math.ceil(PFFT_NEAR_RADII * float(fs.rho.max()) / min(grid.ax, grid.ay)) + 1)
        self.fs, self.grid, self.near = fs, grid, near
        g = grid
        nx, ny = g.nx, g.ny
        ns = fs.seg_p0.shape[0]
        d = fs.seg_p1 - fs.seg_p0
        ell = np.linalg.norm(d, axis=1)
        # node order: the far field is smooth on the scale D_f = (near - 1) cells, so the Bernstein parameter of a segment
        # is rho = 1 + (D_f - rmax) / (ell / 2); the order grows when the cells shrink the near box below the segment length
        rho_n = 1.0 + ((near - 1.0) * min(g.ax, g.ay) - float(fs.rho.max())) / (0.5 * float(ell.max()))
        self.NG = next((n for n in range(WireGridPFFT.NG, 13) if rho_n > 1.0 and core.gauss_bound(n, rho_n) <= NODE_GAUSS_TOL), 12)
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
        self.stencil_shifted = False
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
            nla, nlb = min(nl, na_), min(nl, nb_)  # a lattice smaller than the stencil: smaller stencil (no far branch then)
            a0 = np.floor(ua).astype(int) - (nla // 2 - 1)
            b0 = np.floor(ub).astype(int) - (nlb // 2 - 1)
            if a0.min() < 0 or b0.min() < 0 or (a0 + nla).max() > na_ or (b0 + nlb).max() > nb_ or nla < nl or nlb < nl:
                # stencil sticks out of the lattice: shift it inside (extrapolating weights).  Harmless when every branch
                # is in the near box of every wire (the near correction replaces the whole pair); an error otherwise,
                # because the far-field interpolation bound does not hold (checked after the near correction)
                self.stencil_shifted = True
                a0, b0 = np.clip(a0, 0, na_ - nla), np.clip(b0, 0, nb_ - nlb)
            Wa, Wb = lagrange_weights(ua - a0, nla), lagrange_weights(ub - b0, nlb)
            coef = w * t[np.repeat(np.arange(ns), self.NQ), dd]
            val = (coef[:, None, None, None] * Wa[:, :, None, None] * Wb[:, None, :, None] * Wz[:, None, None, :])
            ia = a0[:, None, None, None] + np.arange(nla)[None, :, None, None]
            ib = b0[:, None, None, None] + np.arange(nlb)[None, None, :, None]
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
        if self.stencil_shifted and self.n_far_branches > 0:
            raise ValueError("wire too close to the edge of the shared grid for the interpolation stencil "
                             "(branches beyond the near box exist, so the far-field interpolation bound would not hold)")
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
            if dd == 1:  # y-branch: lateral offset along x, axial along y; box ax (x) by ay (y)
                lo[..., 0], hi[..., 0] = -g.ax / 2, g.ax / 2
                lo[..., 1], hi[..., 1] = -g.ay / 2, g.ay / 2

            def level(k, dd=dd, di=di, dj=dj, lo=lo, hi=hi, A=A):  # one z-level: bounded temporaries, threads
                pz = zv[k:k + 1, None, None, None]
                # field point (axial di, lateral dj) relative to the branch box centred at the origin
                P = box_potential(di, dj, pz, lo, hi) if dd == 0 else box_potential(dj, di, pz, lo, hi)
                return K4 * P / A[None, :, None, None]

            T = np.concatenate(_pool_map(level, range(self.nzv), NTHREADS), axis=0)
            self.Tv.append(T)
            self.Thr.append(circulant_half(T))  # (F, nzv, nL)
        self.ThrT = None  # transposed products use views of Thr

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

                lat = g.lat[dd].sub(idx)
                grads = {}  # box gradients at filament vertices: consecutive segments of a filament share them

                def grad_at(p, lat=lat, grads=grads):
                    key = p.tobytes()
                    if key not in grads:
                        grads[key] = lattice_grad(p, lat)
                    return grads[key]

                def seg_task(s, dd=dd, lo=lo, hi=hi, A=A, lat=lat):
                    p0, p1 = fs.seg_p0[s], fs.seg_p1[s]
                    I, bd, _ = line_box_integral(p0, p1, lo, hi, lat=lat)
                    corr, rem = rod_box_correction(p0, p1, fs.rho[fs.seg_fil[s]], lo, hi, grad_at(p0), grad_at(p1))
                    return s, K4 * self.t[s, dd] * (I + corr) / A, K4 * abs(self.t[s, dd]) * rem / A, bd

                for s, e_s, eb_s, bd in _pool_map(seg_task, [s for s in segs if abs(self.t[s, dd]) >= 1e-15], NTHREADS):
                    self.near_bound = max(self.near_bound, bd)
                    ex[loc[int(fs.seg_fil[s])]] += e_s
                    exb[loc[int(fs.seg_fil[s])]] += eb_s
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
        return circulant_apply_half(self.Thr[dd], Xfull, transposed=transposed)

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
        if sp.issparse(ends):  # (n_wires, n_raw): +weights at the start contact nodes, -weights at the end contact nodes
            self.E = ends.tocsr()
        else:  # (n_wires, 2) raw node ids: start / end node of every wire
            ends = np.asarray(ends, np.int64)
            nw = ends.shape[0]
            self.E = sp.csr_matrix((np.concatenate([np.ones(nw), -np.ones(nw)]),
                                    (np.tile(np.arange(nw), 2), np.concatenate([ends[:, 0], ends[:, 1]]))), shape=(nw, n_raw))
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
        n_raw = self.E.shape[1]
        Mlab = sp.csr_matrix((np.ones(n_raw), (np.arange(n_raw), lab)), shape=(n_raw, nn))  # raw node -> merged node
        self.Cf = (self.E[self.fs.fil_wire] @ Mlab).tocsr()  # (nfil, nn): the wire (filament) rows of the incidence matrix
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
        Cg = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows) - self.nfil, np.concatenate(cols))),
                           shape=(self.n_g, nn))
        C = sp.vstack([self.Cf, Cg]).tocsr()
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
        Cf = sys_.Cf  # built by ``incidence`` (the caller has run it: Cr comes from it)
        nodes = np.unique(Cf.nonzero()[1])
        Cw = Cf[:, nodes].toarray()
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
                ysum = np.full(c_s, Bi.sum())
                a, b = np.nonzero(vk)
                i, j = (a, b) if d == 0 else (b, a)
                n1 = lab[g.node_id[k][i, j]]
                n2 = lab[g.node_id[k][i + (d == 0), j + (d == 1)]]
                rows += [n1, n2, n1, n2]
                cols += [n1, n2, n2, n1]
                vals += [ysum, ysum, -ysum, -ysum]
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


@dataclass(frozen=True)
class Contact:
    """A current injected over several cell nodes (raw ids) with weights summing to 1 (bilinear: a point contact at a position
    inside a cell, instead of snapping it to one cell centre, which moves the injection point by up to half a cell)."""
    nodes: np.ndarray
    weights: np.ndarray


@dataclass
class SolveOut:
    z: np.ndarray  # (nf, np, np)
    solver_tol: float
    parts: list = field(default_factory=list)
    iters: list = field(default_factory=list)
    tol_rel_L: list = field(default_factory=list)  # per frequency: solver_tol relative to L = Im Z / omega
    t_pre: float = 0.0  # seconds: preconditioner setup / GMRES / a-posteriori bound (summed over frequencies)
    t_gmres: float = 0.0
    t_post: float = 0.0
    flags: list = field(default_factory=list)  # scipy GMRES flag per (frequency, port); 0 = converged


DENSE_MAX = 2500
# GMRES stops at a preconditioned relative residual of GMRES_TOL.  It is a stopping rule, not an accuracy statement: the
# reported solver_tol is the rigorous a-posteriori bound, whose residual term is QUADRATIC in the residual (||P M x||^2 /
# r_min).  At 1e-9 that term was ~4e-15 on every T0075 layout, 1e-10 of the stated operator bounds (~2e-5) that make up
# solver_tol; 1e-7 keeps it orders below them and saves ~2 decades of iterations (~20 % of GMRES time; 6 dies/switch at
# 0.25 mm spent 1231 of 2286 CPU-s in GMRES at 1e-9).
GMRES_TOL = 1e-7
# Restarted GMRES(GMRES_RESTART), at most GMRES_MAXIT cycles.  The Krylov basis (GMRES_RESTART vectors of the saddle size)
# is the largest memory term, so the restart stays at 100 and the cycle cap grows instead: the founder diagnostic I0039 hit
# the former cap of 100 x 5 iterations at 0.125 mm cells (solver_tol 1.2e-3, residual-dominated); iterations grew 191 / 398
# at 0.5 / 0.25 mm, ~2x per halving of the cell, so 0.125 mm needs ~800-1000.  The a-posteriori bound never relies on
# convergence (``l2_core.a_posteriori``), and the scipy flag of every solve is in meta['gmres_flags'].
GMRES_RESTART = 100
GMRES_MAXIT = 40


def solve_system(sys_: LayoutSystem, port_nodes, freqs, tol: float = GMRES_TOL, dense: bool | None = None) -> SolveOut:
    """Z[f, i, j] = V_i / I_j (other ports open) with the D0004 forward-error bound ``solver_tol`` = max over freqs of
    (a-posteriori ||P(Mx)||^2 / r_min  +  rounding  +  stated bounds) / max|Z_ii|."""
    C, keep, nn = sys_.incidence()
    Cr = C[:, keep].tocsc()
    pos = {int(k): i for i, k in enumerate(keep)}
    npt = len(port_nodes)
    D = np.zeros((len(keep), npt))
    for j, (a, b) in enumerate(port_nodes):
        for sgn, c in ((1.0, a), (-1.0, b)):
            nodes_c, w_c = (c.nodes, c.weights) if isinstance(c, Contact) else ([c], [1.0])
            for nd, wt in zip(nodes_c, w_c, strict=True):
                nd = int(sys_.lab[nd])
                if nd in pos:
                    D[pos[nd], j] += sgn * wt
    n, R = sys_.n, sys_.R
    rmin = float(R.min())
    if dense is None:
        dense = n + Cr.shape[1] <= DENSE_MAX
    if dense:
        Ld = np.stack([sys_.lmul(np.eye(n)[:, i]).real for i in range(n)], 1)
        Ld = 0.5 * (Ld + Ld.T)
    zs, tols, iters, parts, flags = [], [], [], [], []
    t_pre = t_gmres = t_post = 0.0
    tols_l = []
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
            t_a = time.perf_counter()
            pre = LayoutPreconditioner(sys_, w, Cr, keep, nn)
            t_pre += time.perf_counter() - t_a
            t_a = time.perf_counter()
            X = np.zeros((n, npt), complex)
            it = 0
            for j in range(npt):
                X[:, j], k, info = core.block_gmres(apply_M, pre, Cr, D[:, j], n, tol, restart=GMRES_RESTART,
                                                    maxit=GMRES_MAXIT)
                it += k
                flags.append(info)
            iters.append(it)
            t_gmres += time.perf_counter() - t_a
        t_a = time.perf_counter()
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
        # the same absolute bound read as a bound on L_i = Im Z_ii / omega:  tol * max|Z_jj| / min_i Im Z_ii  (relative to L)
        zd = np.diag(Z)
        tols_l.append(tols[-1] * zref / float(np.min(zd.imag)) if np.all(zd.imag > 0) else float("inf"))
        zs.append(Z)
        t_post += time.perf_counter() - t_a
    return SolveOut(z=np.array(zs), solver_tol=float(max(tols)), parts=parts, iters=iters, flags=flags, tol_rel_L=tols_l,
                    t_pre=t_pre, t_gmres=t_gmres, t_post=t_post)


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


def _nearest_cell(mask, xc, yc, x, y):
    """Index (i, j) of the masked cell nearest to (x, y)."""
    ii, jj = np.nonzero(mask)
    if ii.size == 0:
        raise ValueError("no cell to attach to: the mask is empty")
    d2 = (xc[ii] - x) ** 2 + (yc[jj] - y) ** 2
    k = int(np.argmin(d2))
    return int(ii[k]), int(jj[k])


def layout_lattice(cm, refinement: int):
    """Shared lateral lattice (xmin, ymin, ax, ay, nx, ny) of the conductor model ``cm`` at ``refinement``: the bounding box
    of the baseplate and the top-Cu rectangles, divided into cells of exactly CELL[refinement] (ValueError when the box is
    not a whole number of cells: the cell would be stretched off the design grid and no feature would stay aligned)."""
    if not 0 <= refinement <= MAX_REFINEMENT:
        raise ValueError(f"refinement must be in 0..{MAX_REFINEMENT}")
    bp = {p.name: p for p in cm.planes}["baseplate"]
    xmin, ymin, xmax, ymax = bp.bounds
    for r in cm.rects:
        xmin, ymin, xmax, ymax = min(xmin, r.x0), min(ymin, r.y0), max(xmax, r.x1), max(ymax, r.y1)
    a = CELL[refinement]
    nx, ny = max(8, round((xmax - xmin) / a)), max(8, round((ymax - ymin) / a))
    for n, ext, name in ((nx, xmax - xmin, "x"), (ny, ymax - ymin, "y")):
        if abs(ext / a - n) > ALIGN_TOL * n:
            raise ValueError(f"lattice {name} extent {ext * 1e3:.4f} mm is not a whole number of {a * 1e3:.4g} mm cells "
                             f"(baseplate / trace bounding box); features would not lie on cell boundaries")
    return float(xmin), float(ymin), (xmax - xmin) / nx, (ymax - ymin) / ny, int(nx), int(ny)


def layout_cell_fill(layout, refinement: int) -> dict:
    """``cell_fill`` of ``layout`` on its lattice at ``refinement`` (cheap: no system is built)."""
    cm = layout.to_conductors()
    return cell_fill(cm, *layout_lattice(cm, refinement))


def build_layout_system(layout, fmax: float, refinement: int, coupling: str = "pfft"):
    """(LayoutSystem, port raw nodes, info dict) of ``layout`` (see module docstring)."""
    cm = layout.to_conductors()
    st = cm.stack
    planes = {p.name: p for p in cm.planes}
    xmin, ymin, ax, ay, nx, ny = layout_lattice(cm, refinement)
    xc = xmin + (np.arange(nx) + 0.5) * ax
    yc = ymin + (np.arange(ny) + 0.5) * ay
    X, Y = np.meshgrid(xc, yc, indexing="ij")
    # every trace, plane and die footprint on cell boundaries (ValueError otherwise): cells are full or empty
    fill = cell_fill(cm, xmin, ymin, ax, ay, nx, ny)
    for d in cm.shorts:
        check_on_lattice(d.x - d.w / 2, d.x + d.w / 2, d.y - d.h / 2, d.y + d.h / 2, xmin, ymin, ax, ay,
                         f"die {d.die_index} footprint")
    top_frac, top_lab, nets = fill["top"]
    top_mask = top_frac > 0
    z0t, z1t = layout.top_cu_z()
    top_sigma = st.layer("top_cu").sigma
    slabs = [SlabSpec("top_cu", top_mask, graded_layers(z0t, z1t, LAYERS_TOP[refinement], fmax, top_sigma, True),
                      top_sigma, top_lab)]
    for name, nlay, two in (("backside_cu", LAYERS_BACK[refinement], True), ("baseplate", LAYERS_BASE[refinement], False)):
        p = planes[name]
        F = fill[name]
        slabs.append(SlabSpec(name, F > 0, graded_layers(p.z_bottom, p.z_bottom + p.thickness, nlay, fmax, p.sigma, two),
                              p.sigma))
    area_err = {k: abs(rep - ex) / ex for k, (rep, ex) in fill["area"].items()}
    t_g = time.perf_counter()
    grid = Grid(xmin, ymin, ax, ay, nx, ny, slabs)
    t_grid = time.perf_counter() - t_g
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
    shorts, die_node, short_nets = [], [], []
    for d in cm.shorts:
        if d.bottom_net not in nets:
            raise ValueError(f"die {d.die_index}: no trace of its net {d.bottom_net!r}")
        lab = nets.index(d.bottom_net) + 1  # a die shorts the cells of ITS net only (DieShort.bottom_net), not the nearest trace's
        ci, cj = _nearest_cell(top_mask & (top_lab == lab), xc, yc, d.x, d.y)
        m = top_mask & (top_lab == lab) & (np.abs(X - d.x) < d.w / 2) & (np.abs(Y - d.y) < d.h / 2)
        m[ci, cj] = True
        shorts.append(nid[m])
        short_nets.append(sorted({nets[int(k) - 1] for k in top_lab[m]}))
        die_node.append(int(nid[ci, cj]))

    def contact_at(p, net):
        """Raw nodes and weights of a point contact at p on ``net``: bilinear weights over the four cell centres around p that
        belong to the net's cells (renormalised when some are not; the nearest cell if none)."""
        lab = nets.index(net) + 1
        u, v = (p[0] - xmin) / ax - 0.5, (p[1] - ymin) / ay - 0.5
        i0, j0 = int(np.floor(u)), int(np.floor(v))
        fx, fy = u - i0, v - j0
        nodes, wts = [], []
        for di, wx in ((0, 1.0 - fx), (1, fx)):
            for dj, wy in ((0, 1.0 - fy), (1, fy)):
                i, j = i0 + di, j0 + dj
                if wx * wy > 1e-12 and 0 <= i < nx and 0 <= j < ny and top_mask[i, j] and top_lab[i, j] == lab:
                    nodes.append(int(nid[i, j]))
                    wts.append(wx * wy)
        if not nodes:
            i, j = _nearest_cell(top_mask & (top_lab == lab), xc, yc, p[0], p[1])
            return Contact(np.array([int(nid[i, j])]), np.ones(1))
        w = np.array(wts)
        return Contact(np.array(nodes), w / w.sum())

    def end_contact(p, net):
        for k, d in enumerate(cm.shorts):  # a wire end on a die joins the die's (merged) node
            if abs(p[0] - d.x) <= d.w / 2 and abs(p[1] - d.y) <= d.h / 2 and p[2] >= d.z_top - 1e-9:
                return Contact(np.array([die_node[k]]), np.ones(1))
        return contact_at(p, net)

    n_raw = grid.n_cell_nodes
    er, ec, ev = [], [], []
    for wi, (w, n) in enumerate(zip(wires, wnet, strict=True)):
        for sgn, pt in ((1.0, w.points[0]), (-1.0, w.points[-1])):
            c = end_contact(pt, n)
            er += [wi] * c.nodes.size
            ec += list(c.nodes)
            ev += list(sgn * c.weights)
    ends = sp.csr_matrix((ev, (er, ec)), shape=(len(wires), n_raw))
    pp, pn = cm.port.p_pos, cm.port.p_neg
    port = (contact_at(pp, DC_PLUS), contact_at(pn, DC_MINUS))
    t0 = time.perf_counter()
    wg = WireGridPFFT(fs, grid) if coupling == "pfft" else WireGridDense(fs, grid)
    t_wg = time.perf_counter() - t0
    t0 = time.perf_counter()
    sys_ = LayoutSystem(fs, grid, wg, ends, shorts)
    t_sys = time.perf_counter() - t0
    sys_.set_stated()
    info = dict(nx=nx, ny=ny, cell_x=ax, cell_y=ay, layers=[len(s.layers) for s in slabs], n_wires=len(wires),
                filaments_per_wire=fs.nfil // len(wires), n_segments=int(fs.seg_p0.shape[0]), n_grid_unknowns=grid.n_g,
                clamped_vertices=fs.clamped, coupling=coupling, die_short_nets=short_nets, wire_grid_build_s=t_wg,
                grid_build_s=t_grid, wire_matrices_s=t_sys, area_rel_err=area_err, on_lattice=True,
                n_near_pairs=int(getattr(wg, "near_pairs", 0)), pfft_near_cells=int(getattr(wg, "near", PFFT_NEAR)))
    return sys_, port, info


def _peak_rss_gb() -> float:
    import resource
    import sys
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r * (1.0 if sys.platform == "darwin" else 1024.0) / 1e9


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
                solver_tol=out.solver_tol, solver_tol_rel_L=out.tol_rel_L, solver_tol_rel_L_max=float(max(out.tol_rel_L)),
                tol_parts=out.parts, gmres_flags=out.flags, solve_s=dict(preconditioner=out.t_pre, gmres=out.t_gmres,
                                                                         a_posteriori=out.t_post),
                peak_rss_gb=_peak_rss_gb(), stated=sys_.stated, gmres_iters=out.iters,
                gmres_tol=GMRES_TOL, gmres_restart=GMRES_RESTART, gmres_max_iters=GMRES_RESTART * GMRES_MAXIT, build_s=t1 - t0, wall_s=time.perf_counter() - t0, cpu_s=time.process_time() - c0,
                layout_fingerprint=layout.fingerprint())
    return LoopResult(L_H=np.imag(z) / (2.0 * np.pi * freqs), R_ohm=np.real(z), meta=meta)
