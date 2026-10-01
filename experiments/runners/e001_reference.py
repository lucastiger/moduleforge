"""E001 runner: validate the L2 reference solver against closed forms on canonical geometries.

Design (pre-registered in experiments/drafts/E001.yaml; rationale in research/notes/o001-l2-reference.md):
every case is a geometry whose closed form is exact for the *modeled* geometry (partial-inductance /
PEEC formulation with the same segment topology) up to a stated residual model error. The closed forms
are validated on every run before they are used (sanity checks closed_forms_*).

Modes:
  --analytic-only  closed-form self-checks only; never imports moduleforge.solvers; exit 1 if any fails.
  --smoke          smoke_cases (one or more per geometry class, all 7 classes) at 20 MHz; bars are compared at
                   their LF frequency and also solved at 20 MHz; refinement_min_levels (4) levels, the rule's minimum.
  (default)        full registered run.

Sources for formulas (all SI; mu0 per CODATA 2018):
  [HL]  C. Hoer, C. Love, "Exact inductance equations for rectangular conductors with applications to more
        complicated geometries", J. Res. NBS 69C(2):127-137, 1965 (6-fold integral of 1/R over two parallel
        boxes); same function as A. E. Ruehli, IBM J. Res. Dev. 16(5):470-481, 1972, and FastHenry joelself.c.
  [G]   F. W. Grover, Inductance Calculations, Van Nostrand 1946 (Dover 2004): parallel filaments with
        offset (Ch. 7), GMD of a rectangle (Ch. 3), rectangle of round wire (Ch. 14).
  [R]   E. B. Rosa, "The self and mutual inductances of linear conductors", Bull. Bur. Stand. 4:301-344, 1908.
  [RWV] Ramo, Whinnery, Van Duzer, Fields and Waves in Communication Electronics, 3rd ed., 1994, sec. 5.6:
        internal impedance of a round wire Z' = k J0(ka) / (2 pi a sigma J1(ka)), k = (1 - j)/delta.
  [AS]  Abramowitz & Stegun, Handbook of Mathematical Functions, 1964: 9.1.10 (J_n series), 9.2.5/9.2.9/
        9.2.10 (Hankel asymptotics), Table 9.12 (ber, bei).
  [W]   H. A. Wheeler, "Formulas for the skin effect", Proc. IRE 30(9):412-424, 1942 (incremental
        inductance rule: a thick good conductor acts as a perfect conductor whose surface is recessed by
        delta/2).
  [GU]  E. A. Guillemin, Synthesis of Passive Networks, Wiley 1957: RL driving-point impedances have
        Im Z / omega non-increasing in omega (Foster form).
  [RU]  V. H. Rumsey, "Reaction concept in electromagnetic theory", Phys. Rev. 94(6):1483-1491, 1954: the
        reaction <J, Z J> / <J, 1>^2 (unconjugated) is stationary about the true current distribution.
  [C]   J. R. Carson, "Wave propagation in overhead wires with ground return", Bell Syst. Tech. J. 5:539-554,
        1926: exact quasi-static impedance of a line current over a conducting half-space.
  [ROA] P. J. Roache, "Perspective: a method for uniform reporting of grid refinement studies", J. Fluids Eng.
        116(3):405-413, 1994: safety factor 1.25 with >= 3 grids (observed order), 3 with 2 grids.
  [MW]  E. W. Weisstein, "Disk Line Picking", MathWorld: mean distance of two uniform points in a disk
        128 r / (45 pi).
Derived here (research/notes/o001-l2-reference.md sec. 4.1-4.3; each verified by a self-check below): angular
mean of the distance between two coaxial circles (2/pi)(p + q) E(4pq/(p + q)^2) (complete elliptic integral of
the 2nd kind, parameter convention of scipy.special.ellipe); line-dipole response -J2(ka)/J0(ka) of a round
conductor in a uniform transverse field; finite cross-section of mutuals by the circle-mean expansion
<M(D + w)> = M(D) + <|w|^2>/4 Lap_T M + R with the Darboux/Taylor remainder bound (note sec. 4.2a; Courant & Hilbert
vol. II ch. VI, Pizzetti 1909).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import integrate, special

from mfos.evidence import ExperimentRun

MU0 = 1.25663706212e-6  # H/m, CODATA 2018


def mm_to_m(x):
    return np.asarray(x, dtype=np.float64) * 1e-3 if np.ndim(x) else float(x) * 1e-3


def mhz_to_hz(x: float) -> float:
    return float(x) * 1e6


def skin_depth(f_hz: float, sigma: float) -> float:
    """delta = 1/sqrt(pi f mu0 sigma) [RWV 5.4]."""
    return 1.0 / math.sqrt(math.pi * f_hz * MU0 * sigma)


# ============================================================ Bessel functions, internal impedance [AS][RWV]
def _j01_series(z: complex) -> tuple[complex, complex]:
    """J0, J1 by the ascending series [AS 9.1.10]; adequate in float64 for |z| <= 40 (cancellation < 1e6)."""
    q = -(z * z) / 4.0
    t0, t1 = 1.0 + 0j, 1.0 + 0j
    s0, s1 = t0, t1
    for m in range(1, 400):
        t0 *= q / (m * m)
        t1 *= q / (m * (m + 1))
        s0 += t0
        s1 += t1
        if abs(t0) < 1e-18 * abs(s0) and abs(t1) < 1e-18 * abs(s1) and m > 5:
            break
    return s0, s1 * z / 2.0


def _jn_hankel(n: int, z: complex, terms: int = 14) -> complex:
    """Hankel large-argument expansion [AS 9.2.5, 9.2.9, 9.2.10] (independent method for the self-check)."""
    mu = 4.0 * n * n
    p, qq, a = 0j, 0j, 1.0 + 0j
    for k in range(terms):
        if k > 0:
            a *= (mu - (2 * k - 1) ** 2) / (k * 8.0 * z)
        if k % 2 == 0:
            p += (-1) ** (k // 2) * a
        else:
            qq += (-1) ** ((k - 1) // 2) * a
    chi = z - (n / 2.0 + 0.25) * math.pi
    return np.sqrt(2.0 / (math.pi * z)) * (p * np.cos(chi) - qq * np.sin(chi))


def z_internal_per_m(f_hz: float, r: float, sigma: float) -> complex:
    """Exact internal impedance per unit length (ohm/m) of an isolated straight round wire [RWV 5.6]."""
    if f_hz <= 0.0:
        return 1.0 / (sigma * math.pi * r * r) + 0j
    k = (1.0 - 1.0j) / skin_depth(f_hz, sigma)
    if abs(k * r) <= 35.0:
        j0, j1 = _j01_series(k * r)
    else:
        j0, j1 = _jn_hankel(0, k * r), _jn_hankel(1, k * r)
    return k * j0 / (2.0 * math.pi * r * sigma * j1)


# ============================================================ partial inductances [G][R][HL]
def fil_mutual(a1: float, a2: float, b1: float, b2: float, d: float) -> float:
    """Mutual partial inductance (H) of two parallel filaments at transverse distance d > 0, spanning
    [a1, a2] and [b1, b2] along the common axis (Neumann integral in closed form) [G ch. 7]."""
    def g(u):
        return u * math.asinh(u / d) - math.sqrt(u * u + d * d)
    return MU0 / (4 * math.pi) * (g(b2 - a1) - g(b2 - a2) - g(b1 - a1) + g(b1 - a2))


def wire_ext_self(length: float, r: float) -> float:
    """External partial self-inductance of a straight round wire (current on its surface): filament
    formula at the GMD of a circle to itself, which is r [R eq. for tubes; G ch. 3]."""
    return fil_mutual(0.0, length, 0.0, length, r)


# ============================================================ round wire beyond the filament-at-r model (note 4.1-4.2)
def _radial_nodes(r: float, f_hz: float, sigma: float, npp: int = 12):
    """Gauss-Legendre nodes/weights on [0, r]; panels graded toward the surface on the skin-depth scale."""
    dl = skin_depth(f_hz, sigma) if f_hz > 0 else math.inf
    depth, step = [0.0], min(dl, r) / 8.0
    while depth[-1] + step < r:
        depth.append(depth[-1] + step)
        step *= 1.6
    edges = r - np.array([*depth, r])[::-1]
    xg, wg = np.polynomial.legendre.leggauss(npp)
    a, b = edges[:-1, None], edges[1:, None]
    return ((a + b) / 2 + (b - a) / 2 * xg).ravel(), ((b - a) / 2 * wg).ravel()


def wire_current_profile(rho, r: float, f_hz: float, sigma: float) -> np.ndarray:
    """J(rho)/I (1/m^2) of an isolated infinite round wire [RWV 5.6]: k J0(k rho) / (2 pi r J1(k r)),
    k = (1 - j)/delta; 1/(pi r^2) at DC. Exponentially scaled Bessel functions (jve) avoid overflow."""
    rho = np.asarray(rho, dtype=np.float64)
    if f_hz <= 0:
        return np.full(rho.shape, 1.0 / (math.pi * r * r), dtype=complex)
    k = (1.0 - 1.0j) / skin_depth(f_hz, sigma)
    scale = np.exp(np.abs((k * rho).imag) - abs((k * r).imag))
    return k * special.jve(0, k * rho) * scale / (2 * math.pi * r * special.jve(1, k * r))


@lru_cache(maxsize=None)
def wire_distance_moments(r: float, f_hz: float, sigma: float) -> tuple[complex, complex, complex, complex]:
    """Reaction-weighted moments <d^n> = int int J(p) J(q) |p - q|^n dA dA / I^2 over the cross-section
    (unconjugated weights: the reaction is stationary [RU]). Returns (<d>, <d^2>, <d^4>, int J dA / I).
    Limits: uniform (DC) 128 r/(45 pi) [MW], r^2, 5 r^4/3; surface current 4 r/pi, 2 r^2, 6 r^4."""
    rho, w = _radial_nodes(r, f_hz, sigma)
    jw = wire_current_profile(rho, r, f_hz, sigma) * 2 * math.pi * rho * w
    s2, s4 = np.sum(jw * rho**2), np.sum(jw * rho**4)
    ra, rb = rho[:, None], rho[None, :]
    mean_d = 2 / math.pi * (ra + rb) * special.ellipe(4 * ra * rb / (ra + rb) ** 2)  # angular mean of |p - q|
    return complex(jw @ mean_d @ jw), complex(2 * s2), complex(2 * s4 + 4 * s2 * s2), complex(np.sum(jw))


@lru_cache(maxsize=None)
def wire_radial_moments(r: float, f_hz: float, sigma: float) -> tuple[complex, float, float, float]:
    """Single-wire moments of the isolated-wire profile per unit current: (s2, a0, a2, a4), s2 = int J rho^2 dA / I
    (complex, unconjugated reaction weights [RU]; r^2/2 uniform, -> r^2 surface) and a_n = int |J| rho^n dA / |I|
    (absolute weights, used only by the remainder bound of fil_mutual_cross_section)."""
    rho, w = _radial_nodes(r, f_hz, sigma)
    jw = wire_current_profile(rho, r, f_hz, sigma) * 2 * math.pi * rho * w
    aw = np.abs(jw)
    return complex(np.sum(jw * rho**2)), float(np.sum(aw)), float(aw @ rho**2), float(aw @ rho**4)


def fil_mutual_lap(a1: float, a2: float, b1: float, b2: float, d: float) -> float:
    """Transverse (2-D) Laplacian (H/m^2) of fil_mutual with respect to the offset vector, at |offset| = d. Each term
    g(u, d) = u asinh(u/d) - sqrt(u^2 + d^2) of fil_mutual has Lap_T g = g'' + g'/d = -1/sqrt(u^2 + d^2) (note 4.2a);
    for equal aligned segments this is mu0/2pi (1/d - 1/sqrt(l^2 + d^2))."""
    def h(u):
        return -1.0 / math.sqrt(u * u + d * d)
    return MU0 / (4 * math.pi) * (h(b2 - a1) - h(b2 - a2) - h(b1 - a1) + h(b1 - a2))


def fil_mutual_lap2_bound(a1: float, a2: float, b1: float, b2: float, rho_lo: float) -> float:
    """Upper bound (H/m^4) on |Lap_T^2 fil_mutual| at every offset |x| >= rho_lo: Lap_T^2 g(u, rho) =
    (2u^2 - rho^2)/(u^2 + rho^2)^(5/2), and |2u^2 - rho^2| <= max(2u^2, rho^2) gives, termwise,
    max(2u^2/(u^2 + rho_lo^2)^(5/2), 1/(u^2 + rho_lo^2)^(3/2)) (note 4.2a)."""
    tot = 0.0
    for u in (b2 - a1, b2 - a2, b1 - a1, b1 - a2):
        q = u * u + rho_lo * rho_lo
        tot += max(2 * u * u / q**2.5, 1.0 / q**1.5)
    return MU0 / (4 * math.pi) * tot


def wire_self_correction(length: float, r: float, f_hz: float, sigma: float) -> complex:
    """Exact reaction average of the filament kernel minus the filament-at-r term (H, complex; multiply by j omega).
    M(l, d) = mu0/2pi [l ln(2l/d) - l + d - d^2/(4l) + d^4/(32 l^3) - d^6/(96 l^5) ...] ([G] ch. 7, expanded);
    the l ln(1/d) part averaged over J is the infinite-wire internal impedance (Bessel Z_int, kept separately), so
    what remains is mu0/2pi [(<d> - r) - (<d^2> - r^2)/(4l) + (<d^4> - r^4)/(32 l^3)] + O(r^6/l^5)."""
    m1, m2, m4, _ = wire_distance_moments(r, f_hz, sigma)
    return MU0 / (2 * math.pi) * ((m1 - r) - (m2 - r * r) / (4 * length) + (m4 - r**4) / (32 * length**3))


def prox_factor(r: float, f_hz: float, sigma: float) -> complex:
    """Line-dipole response of a round conductor in a uniform transverse field relative to a perfect conductor,
    chi = -J2(ka)/J0(ka), k = (1 - j)/delta (derived in the note, sec. 4.2): 0 at DC, -> 1 for a >> delta."""
    if f_hz <= 0:
        return 0j
    z = (1.0 - 1.0j) * r / skin_depth(f_hz, sigma)
    return complex(-special.jve(2, z) / special.jve(0, z))


def _grad_a(p0, p1, ax: int, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Transverse gradient of the axial vector potential (T/A) of a unit current along +ax on the filament p0-p1,
    at points pts (N x 3): A = mu0/4pi [asinh((z2 - z)/rho) - asinh((z1 - z)/rho)] differentiated in rho.
    Returns (gradient N x 3, rho N)."""
    z1, z2 = sorted((p0[ax], p1[ax]))
    tr = [d for d in range(3) if d != ax]
    dv = pts[:, tr] - np.array([p0[tr[0]], p0[tr[1]]])
    rho = np.hypot(dv[:, 0], dv[:, 1])
    if np.min(rho) <= 0:
        raise ValueError("proximity source on the receiver axis")
    u2, u1 = z2 - pts[:, ax], z1 - pts[:, ax]
    da = -MU0 / (4 * math.pi) / rho * (u2 / np.hypot(u2, rho) - u1 / np.hypot(u1, rho))
    g = np.zeros_like(pts)
    g[:, tr[0]], g[:, tr[1]] = da * dv[:, 0] / rho, da * dv[:, 1] / rho
    return g, rho


def tube_peec_segment(length: float, r: float, f_hz: float, sigma: float, n: int = 40) -> complex:
    """Independent reference for one isolated straight round segment (ohm): n coaxial annuli with uniform current
    each, R_i = l/(sigma A_i), finite-length Neumann kernel mu0/2pi [l ln(2l) - l - l <ln max(p, q)> + <h(d)>]
    with h(d) = l (asinh(l/d) - ln(2l/d)) - sqrt(l^2 + d^2) + l + d averaged numerically over angle and radius.
    Solves for the current distribution; uses no Bessel functions and no distance moments."""
    edges = r * (1 - (1 - np.arange(n + 1) / n) ** 2.5)
    xg, wg = np.polynomial.legendre.leggauss(4)
    a, b = edges[:-1, None], edges[1:, None]
    rho = (a + b) / 2 + (b - a) / 2 * xg
    wr = (b - a) / 2 * wg * rho
    wr = wr / wr.sum(1, keepdims=True)
    lnr = (wr * np.log(rho)).sum(1)
    cdf = (rho**2 - a**2) / (b**2 - a**2)
    same = ((b - a) / 2 * wg * np.log(rho) * 2 * cdf * 2 * rho / (b**2 - a**2)).sum(1)  # E ln max, same annulus
    idx = np.arange(n)
    g = np.where(idx[:, None] == idx[None, :], same[:, None], lnr[np.maximum.outer(idx, idx)])
    xp, wp = np.polynomial.legendre.leggauss(96)
    cphi = np.cos(math.pi / 2 * (xp + 1))
    rr = rho.ravel()
    d = np.sqrt(np.maximum(rr[:, None, None] ** 2 + rr[None, :, None] ** 2
                           - 2 * rr[:, None, None] * rr[None, :, None] * cphi, 0.0))
    hd = length * (np.arcsinh(length / d) - np.log(2 * length / d)) - np.hypot(length, d) + length + d
    hm = (hd @ (wp / 2)).reshape(n, 4, n, 4)
    h = np.einsum("ia,iajb,jb->ij", wr, hm, wr)
    kern = length * (math.log(2 * length) - 1) - length * g + h
    z = np.diag(length / (sigma * math.pi * (edges[1:] ** 2 - edges[:-1] ** 2))).astype(complex)
    z += 2j * math.pi * f_hz * MU0 / (2 * math.pi) * kern
    return complex(1.0 / np.sum(np.linalg.solve(z, np.ones(n))))


def _hl_f(x, y, z):
    """Hoer-Love function whose second derivative in each variable is 1/R [HL eq. 14]."""
    x, y, z = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    x2, y2, z2 = x * x, y * y, z * z
    r = np.sqrt(x2 + y2 + z2)
    out = (x2 * x2 + y2 * y2 + z2 * z2 - 3 * x2 * y2 - 3 * y2 * z2 - 3 * z2 * x2) * r / 60.0

    def logt(a, b2, c2):
        rho = np.sqrt(b2 + c2)
        safe = np.where(rho > 0, rho, 1.0)
        return np.where(rho > 0, (6 * b2 * c2 - b2 * b2 - c2 * c2) * a * np.arcsinh(a / safe), 0.0) / 24.0

    def tant(a, b, c, c2):
        den = c * r
        safe = np.where(den != 0, den, 1.0)
        return np.where(den != 0, a * b * c * c2 * np.arctan(a * b / safe), 0.0) / 6.0

    out = out + logt(x, y2, z2) + logt(y, x2, z2) + logt(z, x2, y2)
    out = out - tant(x, y, z, z2) - tant(x, z, y, y2) - tant(z, y, x, x2)
    return out


def box_mutual(lo1, hi1, lo2, hi2) -> float:
    """Mutual partial inductance (H) of two parallel boxes carrying uniform current along the same axis,
    per unit current in each [HL]; self-inductance when the boxes coincide. lo/hi are 3-vectors (m)."""
    lo1, hi1, lo2, hi2 = (np.asarray(v, dtype=np.float64) for v in (lo1, hi1, lo2, hi2))
    ext1, ext2 = hi1 - lo1, hi2 - lo2
    ref = 0.5 * (lo1 + hi1)  # shift origin to limit cancellation
    lo1, hi1, lo2, hi2 = lo1 - ref, hi1 - ref, lo2 - ref, hi2 - ref
    combos = []
    for d in range(3):
        combos.append([(hi2[d] - lo1[d], 1.0), (hi2[d] - hi1[d], -1.0), (lo2[d] - lo1[d], -1.0),
                       (lo2[d] - hi1[d], 1.0)])
    us, ss = [], []
    for (u, su), (v, sv), (w, sw) in itertools.product(*combos):
        us.append((u, v, w))
        ss.append(su * sv * sw)
    u = np.array(us)
    tot = float(np.dot(np.array(ss), _hl_f(u[:, 0], u[:, 1], u[:, 2])))
    # divide by the two cross-section areas (the dims transverse to the current axis)
    axis = int(np.argmax(ext1))
    tr = [d for d in range(3) if d != axis]
    s1 = ext1[tr[0]] * ext1[tr[1]]
    s2 = ext2[tr[0]] * ext2[tr[1]]
    return MU0 / (4 * math.pi) * tot / (s1 * s2)


def rect_gmd(a: float, b: float) -> float:
    """Exact GMD of a rectangle a x b to itself [G ch. 3, eq. for rectangular area]."""
    ln_g = (math.log(math.hypot(a, b)) - a * a / (6 * b * b) * math.log(math.sqrt(1 + b * b / (a * a)))
            - b * b / (6 * a * a) * math.log(math.sqrt(1 + a * a / (b * b)))
            + 2 * a / (3 * b) * math.atan(b / a) + 2 * b / (3 * a) * math.atan(a / b) - 25.0 / 12.0)
    return math.exp(ln_g)


def grover_rectangle_loop(a: float, b: float, r: float) -> float:
    """DC inductance of a rectangle a x b of round wire radius r (internal term mu/4 per unit length)
    [G ch. 14; R 1908]."""
    d = math.hypot(a, b)
    return MU0 / math.pi * (a * math.log(2 * a / r) + b * math.log(2 * b / r) + 2 * d
                            - a * math.asinh(a / b) - b * math.asinh(b / a) - 2 * (a + b) + (a + b) / 4.0)


# ============================================================ case geometry (plain data, SI)
CU, AL = "cu", "al"


def bar(name, p0, p1, w, t, mat=CU):
    return {"kind": "bar", "name": name, "pts": [list(mm_to_m(p0)), list(mm_to_m(p1))],
            "width": mm_to_m(w), "thickness": mm_to_m(t), "mat": mat}


def wire(name, pts, d, mat=AL):
    return {"kind": "wire", "name": name, "pts": [list(mm_to_m(p)) for p in pts], "diameter": mm_to_m(d),
            "mat": mat}


def staple(name, y, span=8.0, hgt=1.5, d=0.3):
    return wire(name, [(0, y, 0), (0, y, hgt), (span, y, hgt), (span, y, 0)], d)


def loop_rect(name, h, a=10.0, b=5.0, d=0.3):
    return wire(name, [(0, 0, h), (a, 0, h), (a, b, h), (0, b, h), (0, 0, h)], d)


def end_port(name, c):
    return {"name": name, "plus": [c["name"], 0], "minus": [c["name"], len(c["pts"]) - 1]}


def build_cases(cfg: dict, ids=None) -> list[dict]:
    """Registered case set; `ids` defaults to cfg["cases"] (self-checks pass ALL_CASES)."""
    lf, hf = [cfg["f_lf_hz"]], list(cfg["freqs_hf_hz"])
    m = cfg["plane_margin_mm"]
    a1 = bar("b", (0, 0, 0), (20, 0, 0), 3.0, 0.3)
    a2 = bar("b", (0, 0, 0), (10, 0, 0), 1.0, 1.0)
    a3 = [bar("b1", (0, 0, 0), (20, 0, 0), 3.0, 0.3), bar("b2", (0, 4, 0), (20, 4, 0), 3.0, 0.3)]
    a4 = [bar("b1", (0, 0, 0), (15, 0, 0), 3.0, 0.3), bar("b2", (5, 0.5, 0.8), (15, 0.5, 0.8), 2.0, 0.3)]
    b3 = [staple("w1", 0.0), staple("w2", 1.5)]
    loop = loop_rect("loop", 1.0)
    plane = {"name": "gnd", "x_min": mm_to_m(-m), "y_min": mm_to_m(-m), "x_max": mm_to_m(10 + m),
             "y_max": mm_to_m(5 + m), "z_top": 0.0, "thickness": mm_to_m(0.3), "mat": CU}
    one = [("L11", 0, 0)]
    two = [("L11", 0, 0), ("M12", 0, 1)]
    cases = [
        dict(id="A1", cls="bar_self", conductors=[a1], ports=[end_port("p", a1)], compare=one, cmp_freqs=lf),
        dict(id="A2", cls="bar_self", conductors=[a2], ports=[end_port("p", a2)], compare=one, cmp_freqs=lf),
        dict(id="A3", cls="bar_mutual", conductors=a3, ports=[end_port("p1", a3[0]), end_port("p2", a3[1])],
             compare=two, cmp_freqs=lf),
        dict(id="A4", cls="bar_mutual", conductors=a4, ports=[end_port("p1", a4[0]), end_port("p2", a4[1])],
             compare=two + [("L22", 1, 1)], cmp_freqs=lf),
        dict(id="B1", cls="wire_chain", conductors=[wire("w", [(0, 0, 0), (10, 0, 0)], 0.3)], compare=one,
             cmp_freqs=lf + hf),
        dict(id="B2", cls="wire_chain", conductors=[staple("w", 0.0)], compare=one, cmp_freqs=lf + hf),
        dict(id="B3", cls="wire_mutual", conductors=b3, ports=[end_port("p1", b3[0]), end_port("p2", b3[1])],
             compare=two, cmp_freqs=lf + hf),
        dict(id="B4", cls="wire_parallel_tied", conductors=b3, ports=[end_port("p", b3[0])],
             ties=[[["w1", 0], ["w2", 0]], [["w1", 3], ["w2", 3]]], compare=one, cmp_freqs=hf),
        dict(id="C0", cls="loop_free", conductors=[loop], compare=one, cmp_freqs=hf),
        dict(id="C1", cls="loop_over_plane", conductors=[loop], planes=[plane], compare=one, cmp_freqs=hf),
    ]
    for c in cases:
        c.setdefault("ports", [end_port("p", c["conductors"][0])])
        c.setdefault("planes", [])
        c.setdefault("ties", [])
        # bars are compared at LF only (DC closed form); their HF solves feed the monotonicity check
        c["info_freqs"] = hf if c["cls"].startswith("bar") else []
        c["trunc_allow"] = float(cfg["tol_truncation"]) if c["planes"] else 0.0
    ids = list(cfg["cases"] if ids is None else ids)
    unknown = sorted(set(ids) - {c["id"] for c in cases})
    if unknown:
        raise ValueError(f"unknown case ids {unknown}")
    return [c for c in cases if c["id"] in ids]


ALL_CASES = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C0", "C1"]


def scale_case(case: dict, s: float) -> dict:
    """All lengths x s and all frequencies / s^2: an exact similarity of the quasi-static problem
    (omega mu sigma l^2 invariant), so every inductance scales by exactly s."""
    c = json.loads(json.dumps(case))
    for k in c["conductors"]:
        k["pts"] = [[s * v for v in p] for p in k["pts"]]
        for key in ("width", "thickness", "diameter"):
            if key in k:
                k[key] *= s
    for p in c["planes"]:
        for key in ("x_min", "y_min", "x_max", "y_max", "z_top", "thickness"):
            p[key] *= s
    c["cmp_freqs"] = [f / s**2 for f in c["cmp_freqs"]]
    c["info_freqs"] = [f / s**2 for f in c["info_freqs"]]
    return c


# ============================================================ analytic assembly (partial-inductance network)
def _segments(case):
    segs = []
    for ci, c in enumerate(case["conductors"]):
        for k in range(len(c["pts"]) - 1):
            p0, p1 = np.array(c["pts"][k]), np.array(c["pts"][k + 1])
            dv = p1 - p0
            ax = int(np.argmax(np.abs(dv)))
            if np.count_nonzero(np.abs(dv) > 1e-15) != 1:
                raise ValueError("E001 closed forms need axis-aligned segments")
            segs.append(dict(c=c, ci=ci, k=k, p0=p0, p1=p1, ax=ax, sgn=float(np.sign(dv[ax])),
                             length=float(abs(dv[ax]))))
    return segs


def _box(s):
    c = s["c"]
    lo, hi = np.minimum(s["p0"], s["p1"]).astype(float), np.maximum(s["p0"], s["p1"]).astype(float)
    wdir = 1 if s["ax"] == 0 else 0  # width in-plane perpendicular to a horizontal axis; thickness along z
    for d, ext in ((wdir, c["width"]), (2, c["thickness"])):
        lo[d] -= ext / 2
        hi[d] += ext / 2
    return lo, hi


def _pair_geom(si, sj, zmirror=None):
    """Geometry of a parallel pair (segment si, segment sj or sj's mirror image about z = zmirror): returns
    (a, b, dist, sign, p0, p1) with a, b the sorted axial spans, dist the axis-to-axis distance, sign the product of
    the current directions and p0, p1 the (mirrored) end points of sj; None for orthogonal segments."""
    if si["ax"] != sj["ax"]:
        return None
    p0, p1 = sj["p0"].copy(), sj["p1"].copy()
    sgn_j = sj["sgn"]
    if zmirror is not None:
        p0[2], p1[2] = 2 * zmirror - p0[2], 2 * zmirror - p1[2]
        if sj["ax"] != 2:
            sgn_j = -sgn_j  # image of a horizontal current is reversed; a vertical one keeps its direction
    ax = si["ax"]
    tr = [d for d in range(3) if d != ax]
    dist = math.hypot(si["p0"][tr[0]] - p0[tr[0]], si["p0"][tr[1]] - p0[tr[1]])
    return sorted((si["p0"][ax], si["p1"][ax])), sorted((p0[ax], p1[ax])), dist, si["sgn"] * sgn_j, p0, p1


def _pair_mutual(si, sj, zmirror=None):
    """Mutual partial inductance between segment si and sj (or sj's mirror image about z = zmirror); round wires as
    filaments on their axes (the finite cross-section is added by _pair_cross_section)."""
    g = _pair_geom(si, sj, zmirror)
    if g is None:
        return 0.0
    a, b, dist, sgn, p0, p1 = g
    kinds = (si["c"]["kind"], sj["c"]["kind"])
    if kinds == ("wire", "wire"):
        if dist == 0.0:
            raise ValueError("collinear distinct wire segments are not in the E001 case set")
        m = fil_mutual(a[0], a[1], b[0], b[1], dist)
    elif kinds == ("bar", "bar"):
        m = box_mutual(*_box(si), *_box(dict(sj, p0=p0, p1=p1)))
    else:
        raise ValueError("bar-wire mutual not needed in E001")
    return sgn * m


def _pair_cross_section(si, sj, f_hz: float, sig: dict, zmirror=None) -> tuple[complex, float]:
    """Finite cross-section of a parallel wire-wire (or wire-image) pair (note sec. 4.2a). The relative position w of
    two points of the two axisymmetric current distributions is isotropic, so the reaction average of the filament
    kernel is <M(D + w)> = M(D) + <|w|^2>/4 Lap_T M(D) + R (mean-value expansion), <|w|^2> = s2_i + s2_j, and
    |R| <= <|w|^4>_abs / 64 * sup |Lap_T^2 M| over |x| >= D - r_i - r_j (Taylor remainder of the circle mean),
    <|w|^4>_abs <= a4_i a0_j + a0_i a4_j + 4 a2_i a2_j. Returns (correction in H, complex; bound on |R| in H)."""
    if si["c"]["kind"] != "wire" or sj["c"]["kind"] != "wire":
        return 0j, 0.0
    g = _pair_geom(si, sj, zmirror)
    if g is None:
        return 0j, 0.0
    a, b, dist, sgn, _, _ = g
    ri, rj = si["c"]["diameter"] / 2, sj["c"]["diameter"] / 2
    s2i, a0i, a2i, a4i = wire_radial_moments(ri, f_hz, sig[_mat(si["c"])])
    s2j, a0j, a2j, a4j = wire_radial_moments(rj, f_hz, sig[_mat(sj["c"])])
    rho_lo = dist - (ri + rj)
    if rho_lo <= 0:
        raise ValueError("overlapping wire cross-sections: the mean-value expansion does not apply")
    shift = sgn * (s2i + s2j) / 4 * fil_mutual_lap(a[0], a[1], b[0], b[1], dist)
    w4 = a4i * a0j + a0i * a4j + 4 * a2i * a2j
    return complex(shift), w4 / 64 * fil_mutual_lap2_bound(a[0], a[1], b[0], b[1], rho_lo)


def cross_section_average_mutual(si, sj, f_hz: float, sig: dict, zmirror=None, npp: int = 8,
                                 nang: int = 20) -> complex:
    """Independent reference for one parallel wire pair (H, complex): the filament mutual averaged over both
    cross-sections with the Bessel profile (unconjugated weights) by brute force - Gauss panels in radius (npp nodes
    per panel, not the moments' 12) and the trapezoid rule in both angles. Uses no moments and no Laplacians."""
    a, b, dist, sgn, _, _ = _pair_geom(si, sj, zmirror)

    def disk(c):
        r = c["diameter"] / 2
        rho, wq = _radial_nodes(r, f_hz, sig[_mat(c)], npp)
        jw = wire_current_profile(rho, r, f_hz, sig[_mat(c)]) * 2 * math.pi * rho * wq
        th = 2 * math.pi * np.arange(nang) / nang
        pts = np.stack([np.outer(rho, np.cos(th)), np.outer(rho, np.sin(th))], -1).reshape(-1, 2)
        return pts, np.repeat(jw / nang, nang)

    pu, wu = disk(si["c"])
    pv, wv = disk(sj["c"])
    dx = dist + pv[None, :, 0] - pu[:, None, 0]
    dd = np.hypot(dx, pv[None, :, 1] - pu[:, None, 1])

    def g(u):
        return u * np.arcsinh(u / dd) - np.sqrt(u * u + dd * dd)

    fm = MU0 / (4 * math.pi) * (g(b[1] - a[0]) - g(b[1] - a[1]) - g(b[0] - a[0]) + g(b[0] - a[1]))
    return complex(sgn * (wu @ fm @ wv))


def _mat(c):
    return c["mat"]


def _prox_terms(case: dict, segs: list, f_hz: float, sig: dict, nq: int = 48) -> list:
    """Leading-order proximity correction (note sec. 4.2): for every round-wire segment s, the line dipole induced by
    the parallel currents of the other segments and of all images changes the segment impedance matrix by
    D_s[t, u] = -j omega chi_s (2 pi r_s^2 / mu0) int_s g_t . g_u dz, g_t = transverse gradient of the axial vector
    potential of segment t (with its image) per unit current. Orthogonal segments do not couple in the PEEC model.
    Returns [(s, D_s, p_min_s)], p_min_s = smallest source-to-axis distance seen by s."""
    n, w = len(segs), 2 * math.pi * f_hz
    xg, wg = np.polynomial.legendre.leggauss(nq)
    zms = [pl["z_top"] - skin_depth(f_hz, sig[pl["mat"]]) / 2.0 for pl in case["planes"]]
    out = []
    for si, s in enumerate(segs):
        c = s["c"]
        if c["kind"] != "wire":
            continue
        r = c["diameter"] / 2
        chi = prox_factor(r, f_hz, sig[_mat(c)])
        pts = s["p0"] + np.outer((xg + 1) / 2, s["p1"] - s["p0"])
        g, pmin = np.zeros((n, nq, 3)), math.inf
        for ti, t in enumerate(segs):
            if t["ax"] != s["ax"]:
                continue
            srcs = [] if ti == si else [(t["p0"], t["p1"], t["sgn"])]
            for zm in zms:  # image: horizontal current reversed, vertical kept [W]
                q0, q1 = t["p0"].copy(), t["p1"].copy()
                q0[2], q1[2] = 2 * zm - q0[2], 2 * zm - q1[2]
                srcs.append((q0, q1, t["sgn"] if t["ax"] == 2 else -t["sgn"]))
            for q0, q1, sg in srcs:
                gg, rho = _grad_a(q0, q1, t["ax"], pts)
                g[ti] += sg * gg
                pmin = min(pmin, float(rho.min()))
        if chi == 0 or not math.isfinite(pmin):
            continue
        q = np.einsum("tak,uak,a->tu", g, g, wg / 2 * s["length"])
        out.append((si, -1j * w * chi * (2 * math.pi * r * r / MU0) * q, pmin))
    return out


def _assemble(case: dict, f_hz: float, sig: dict, prox: bool = True, xsec: bool = True):
    """Closed-form port impedance matrix (ohm) of a case at one frequency, plus what the residual bound needs:
    (Z_ports, segments, proximity terms, excitation vectors u_p = segment currents per unit port-p current,
    xrem = segment-pair matrix of the cross-section remainder bounds in H). xsec=False drops the finite cross-section
    of wire-wire and wire-image mutuals (filaments on the axes), for the self-checks of the filament geometry code."""
    segs = _segments(case)
    n = len(segs)
    w = 2 * math.pi * f_hz
    zp = np.zeros((n, n), dtype=complex)
    xrem = np.zeros((n, n))
    for i, si in enumerate(segs):
        c = si["c"]
        if c["kind"] == "wire":
            r, sg = c["diameter"] / 2, sig[_mat(c)]
            zp[i, i] = (1j * w * (wire_ext_self(si["length"], r) + wire_self_correction(si["length"], r, f_hz, sg))
                        + si["length"] * z_internal_per_m(f_hz, r, sg))
        else:
            zp[i, i] = si["length"] / (sig[_mat(c)] * c["width"] * c["thickness"]) + 1j * w * _pair_mutual(si, si)
        for j in range(i + 1, n):
            sh, bd = _pair_cross_section(si, segs[j], f_hz, sig) if xsec else (0j, 0.0)
            zp[i, j] = zp[j, i] = 1j * w * (_pair_mutual(si, segs[j]) + sh)
            xrem[i, j] = xrem[j, i] = bd
    for pl in case["planes"]:  # thick floating plane: image about the Wheeler-recessed surface [W]
        zs = pl["z_top"] - skin_depth(f_hz, sig[pl["mat"]]) / 2.0
        for i, si in enumerate(segs):
            for j, sj in enumerate(segs):
                sh, bd = _pair_cross_section(si, sj, f_hz, sig, zmirror=zs) if xsec else (0j, 0.0)
                zp[i, j] += 1j * w * (_pair_mutual(si, sj, zmirror=zs) + sh)
                xrem[i, j] += bd
    pt = _prox_terms(case, segs, f_hz, sig) if prox else []
    for _, d, _ in pt:
        zp += d
    # port incidence: each port runs along one conductor from vertex `plus` to vertex `minus`
    cmat = np.zeros((len(case["ports"]), n))
    for pi, p in enumerate(case["ports"]):
        (cn, v0), (cn2, v1) = p["plus"], p["minus"]
        assert cn == cn2 and v1 > v0
        for i, s in enumerate(segs):
            if s["c"]["name"] == cn and v0 <= s["k"] < v1:
                cmat[pi, i] = 1.0
    zb, exc = cmat @ zp @ cmat.T, [row.astype(complex) for row in cmat]
    if case["ties"]:  # E001 ties short all branch ends pairwise: parallel combination of the branches
        full = np.zeros((len(case["conductors"]), n))
        for ci in range(len(case["conductors"])):
            full[ci] = [1.0 if s["ci"] == ci else 0.0 for s in segs]
        yb = np.linalg.solve(full @ zp @ full.T, np.ones(len(case["conductors"])))
        zt = 1.0 / np.sum(yb)
        zb, exc = np.array([[zt]]), [full.T @ (yb * zt)]
    return zb, segs, pt, exc, xrem


def analytic_z(case: dict, f_hz: float, sig: dict) -> np.ndarray:
    """Closed-form port impedance matrix (ohm) of a case at one frequency."""
    return _assemble(case, f_hz, sig)[0]


def analytic_values(case: dict, freqs, sig: dict) -> dict:
    out = {}
    for f in freqs:
        z = analytic_z(case, f, sig)
        for lab, i, j in case["compare"]:
            out[(lab, f)] = float(np.imag(z[i, j]) / (2 * math.pi * f))
    return out


# ============================================================ 2-D PEC strip BEM (plane truncation estimate)
def strip_truncation_2d(h: float, sep: float, r: float, half_width: float) -> float:
    """Relative error of the infinite-image formula for a two-wire line (separation sep, height h, radius r)
    over a floating PEC strip of half-width half_width. Piecewise-constant surface current, graded panels,
    A_z constant on the strip, zero net strip current. Returns (L'_strip - L'_inf) / L'_inf."""
    # panels: uniform (h/40) over the wires' neighbourhood, then geometric growth (ratio 1.02) to the edges
    core = min(sep / 2 + 5 * h, half_width)
    xs = list(np.linspace(0.0, core, int(math.ceil(core / (h / 40))) + 1))
    step = h / 40
    while xs[-1] < half_width:
        step *= 1.02
        xs.append(min(xs[-1] + step, half_width))
    xs = np.array(xs)
    xe = np.concatenate([-xs[:0:-1], xs])
    n = len(xe) - 1
    xc, dx = 0.5 * (xe[:-1] + xe[1:]), np.diff(xe)

    def pint(x, y, x1, x2):  # integral of ln sqrt((x - x')^2 + y^2) dx' over [x1, x2] (exact)
        def a(u):
            rr = u * u + y * y
            lg = np.where(rr > 0, 0.5 * np.log(np.where(rr > 0, rr, 1.0)), 0.0)
            at = np.where(y != 0, y * np.arctan(u / np.where(y != 0, y, 1.0)), 0.0)
            return u * lg - u + at
        return a(x2 - x) - a(x1 - x)

    g = -(MU0 / (2 * math.pi)) * pint(xc[:, None], 0.0, xe[None, :-1], xe[None, 1:])
    wires = [(-sep / 2, h, 1.0), (sep / 2, h, -1.0)]
    rhs = np.zeros(n + 1)
    for xw, yw, cur in wires:
        rhs[:n] -= -(MU0 / (2 * math.pi)) * cur * np.log(np.hypot(xc - xw, yw))
    a = np.zeros((n + 1, n + 1))
    a[:n, :n], a[:n, n], a[n, :n] = g, -1.0, dx
    sol = np.linalg.solve(a, rhs)
    k = sol[:n]

    def a_at(xp, yp):
        val = 0.0
        for xw, yw, cur in wires:
            dist = max(math.hypot(xp - xw, yp - yw), r)
            val += -(MU0 / (2 * math.pi)) * cur * math.log(dist)
        val += float(np.sum(-(MU0 / (2 * math.pi)) * k * pint(xp, yp, xe[:-1], xe[1:])))
        return val

    # external sources evaluated at the wire centre (mean-value property of harmonic A_z), self term at radius r
    l_strip = a_at(-sep / 2, h) - a_at(sep / 2, h)
    l_inf = MU0 / math.pi * (math.log(sep / r) - 0.5 * math.log(1 + sep**2 / (4 * h * h)))
    return (l_strip - l_inf) / l_inf


# ============================================================ analytic self-checks
# ber x, bei x to 12 significant digits from the defining series [AS 9.9.10] evaluated in exact rational
# arithmetic (independent of the float64 code below); A&S Table 9.12 tabulates the same function.
KELVIN_REF = {1.0: (0.984381781213, 0.249566040037), 2.0: (0.751734182714, 0.972291627307),
              5.0: (-6.23008247867, 0.116034381550)}


def analytic_checks(run: ExperimentRun, cases: list[dict], sig: dict, cfg: dict) -> bool:
    ok_all = True

    def rep(name, errs: dict):
        """errs: label -> (error, tolerance). Value reported = worst error/tolerance; passes if <= 1."""
        nonlocal ok_all
        worst = max(v / t for v, t in errs.values())
        passed = bool(np.isfinite(worst) and worst <= 1.0)
        ok_all &= passed
        run.sanity(name, passed=passed, value=float(worst), threshold=1.0,
                   detail="; ".join(f"{k}: {v:.3e} (tol {t:.0e})" for k, (v, t) in errs.items()))

    tp = cfg["tol_published"]
    # (1) published tabulated / limit values
    e = {}
    for x, (ber, bei) in KELVIN_REF.items():
        j0, _ = _j01_series(x * np.exp(-0.25j * math.pi))  # ber x + j bei x = J0(x e^{-j pi/4}) (J0 even)
        e[f"ber_bei({x:g}) vs exact series"] = (abs(j0 - complex(ber, bei)) / abs(complex(ber, bei)), 1e-10)
    e["GMD square = 0.44705 a [G]"] = (abs(rect_gmd(1.0, 1.0) / 0.44705 - 1), 2e-5)
    e["GMD thin strip -> e^-1.5 w [G]"] = (abs(rect_gmd(1.0, 1e-5) / math.exp(-1.5) - 1), 1e-4)
    r, sg = 1e-4, 3.77e7
    lint_dc = np.imag(z_internal_per_m(1.0, r, sg)) / (2 * math.pi)
    e["L_int(DC) = mu0/8pi"] = (abs(lint_dc / (MU0 / (8 * math.pi)) - 1), tp)
    e["R(DC) = 1/(sigma pi r^2)"] = (abs(np.real(z_internal_per_m(1.0, r, sg)) * sg * math.pi * r * r - 1), tp)
    for f_hi in (1e9, 1e11):  # HF limit (1+j)/(2 pi r sigma delta), correction O(delta/r)
        dl = skin_depth(f_hi, sg)
        zhf = (1 + 1j) / (2 * math.pi * r * sg * dl)
        e[f"Z_int HF limit r/delta={r / dl:.0f}"] = (abs(z_internal_per_m(f_hi, r, sg) / zhf - 1), dl / r)
    m_dc = wire_distance_moments(r, 0.0, sg)
    e["<d> uniform = 128 r/(45 pi) [MW]"] = (abs(m_dc[0] / (128 * r / (45 * math.pi)) - 1), 1e-6)
    e["<d^2>, <d^4> uniform = r^2, 5r^4/3"] = (max(abs(m_dc[1] / r**2 - 1), abs(m_dc[2] / (5 * r**4 / 3) - 1)), 1e-9)
    f_thin = 1e11
    dl = skin_depth(f_thin, sg)
    m_hf = wire_distance_moments(r, f_thin, sg)
    e[f"<d> surface -> 4r/pi, r/delta={r / dl:.0f}"] = (abs(m_hf[0] / (4 * r / math.pi) - 1), dl / r)
    e["int J dA = I (current profile normalisation)"] = (abs(m_hf[3] - 1), 1e-9)
    e["chi(DC) = j (r/delta)^2/4"] = (abs(prox_factor(r, 1.0, sg) / (0.25j * (r / skin_depth(1.0, sg)) ** 2) - 1), 1e-6)
    e[f"chi -> 1 (perfect conductor), r/delta={r / dl:.0f}"] = (abs(prox_factor(r, f_thin, sg) - 1), 2 * dl / r)
    rep("closed_forms_published_values", e)

    # (2) limits and independent methods
    e = {}
    for qm in (30.0, 34.0):
        q = qm * np.exp(-0.25j * math.pi)
        s0, s1 = _j01_series(q)
        e[f"J0/J1 series vs Hankel |z|={qm:g}"] = (abs((s0 / s1) / (_jn_hankel(0, q) / _jn_hankel(1, q)) - 1), 1e-9)
    for lw in (100.0, 300.0):  # long square bar vs GMD formula; neglected terms are O(w/l)/ln(2l/g)
        wb = 1e-3
        lb = lw * wb
        g = rect_gmd(wb, wb)
        lhl = box_mutual([0, 0, 0], [lb, wb, wb], [0, 0, 0], [lb, wb, wb])
        e[f"HL self vs GMD formula l={lw:g}w"] = (abs(lhl / fil_mutual(0, lb, 0, lb, g) - 1),
                                                  1.0 / lw / math.log(2 * lw / 0.447))
    lo1, hi1 = np.array([0, 0, 0.0]), np.array([2e-3, 1e-3, 0.5e-3])
    lo2, hi2 = np.array([1e-3, 2.5e-3, 1e-3]), np.array([2.5e-3, 3.3e-3, 1.6e-3])
    xg, wg = np.polynomial.legendre.leggauss(10)

    def nodes(lo, hi):
        pts = [(lo[d] + hi[d]) / 2 + (hi[d] - lo[d]) / 2 * xg for d in range(3)]
        ws = [(hi[d] - lo[d]) / 2 * wg for d in range(3)]
        p = np.stack(np.meshgrid(*pts, indexing="ij"), -1).reshape(-1, 3)
        return p, np.einsum("i,j,k->ijk", *ws).ravel()

    pa, wa = nodes(lo1, hi1)
    pb, wb2 = nodes(lo2, hi2)
    dist = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=-1)
    quad = MU0 / (4 * math.pi) * float(wa @ (1 / dist) @ wb2) / (1e-3 * 0.5e-3 * 0.8e-3 * 0.6e-3)
    ti = cfg["tol_independent"]
    e["HL mutual vs Gauss-Legendre 6D"] = (abs(box_mutual(lo1, hi1, lo2, hi2) / quad - 1), ti)
    e["HL mutual symmetric"] = (abs(box_mutual(lo1, hi1, lo2, hi2) / box_mutual(lo2, hi2, lo1, hi1) - 1), 1e-9)
    xs, ws = np.polynomial.legendre.leggauss(200)
    a0, a1_, b0, b1_, dd = 0.0, 3e-3, 1e-3, 5e-3, 0.7e-3
    xa, xb = (a0 + a1_) / 2 + (a1_ - a0) / 2 * xs, (b0 + b1_) / 2 + (b1_ - b0) / 2 * xs
    kern = 1 / np.sqrt((xa[:, None] - xb[None, :]) ** 2 + dd * dd)
    nq = MU0 / (4 * math.pi) * (a1_ - a0) / 2 * (b1_ - b0) / 2 * float(ws @ kern @ ws)
    e["filament mutual vs quadrature"] = (abs(fil_mutual(a0, a1_, b0, b1_, dd) / nq - 1), 1e-9)
    tw = 2e-5
    thin = box_mutual([0, 0, 0], [5e-3, tw, tw], [0, 2e-3, 0], [5e-3, 2e-3 + tw, tw])
    e["HL thin-bar limit -> filament"] = (abs(thin / fil_mutual(0, 5e-3, 0, 5e-3, 2e-3) - 1), 1e-4)
    everything = build_cases(cfg, ALL_CASES)
    c0 = json.loads(json.dumps(next(c for c in everything if c["id"] == "C0")))
    c0["conductors"][0]["diameter"] = 2e-6  # Grover's closed form drops O(r/a) terms: compare in the thin limit
    lc0 = analytic_values(c0, [1e-3], sig)[("L11", 1e-3)]
    e["rect loop: partial sum vs Grover closed form (r=1um)"] = (
        abs(lc0 / grover_rectangle_loop(10e-3, 5e-3, 1e-6) - 1), 1e-6 / 5e-3)
    # round-wire self term: Bessel Z_int equals the reaction integral with the log kernel [RU]; corrected closed form
    # vs the independent axisymmetric tube PEEC (solves the distribution) within the stated bound (a) of the note.
    # Reaction: <ln d> = int int j(p) j(q) ln max(p, q) dp dq = 2 int j(p) ln(p) C(p) dp (angular mean of ln|p - q|
    # for coaxial circles is ln max), C(p) = int_0^p j = p J1(kp) / (r J1(kr)) by d/dz[z J1(z)] = z J0(z) [AS 9.1.30].
    # The 1-D form has no kink at p = q, so plain Gauss panels reach ~1e-12 (T0041; the 2-D form stalled at 7.5e-5).
    ra, sa = 1.5e-4, sig[AL]
    for f in (5e6, 8e7):
        rho, wq = _radial_nodes(ra, f, sa)
        jw = wire_current_profile(rho, ra, f, sa) * 2 * math.pi * rho * wq
        kk = (1.0 - 1.0j) / skin_depth(f, sa)
        cum = (rho * special.jve(1, kk * rho) * np.exp(np.abs((kk * rho).imag) - abs((kk * ra).imag))
               / (ra * special.jve(1, kk * ra)))
        lnmax = 2.0 * np.sum(jw * np.log(rho) * cum)
        zr = (np.sum(jw * wire_current_profile(rho, ra, f, sa)) / sa
              + 2j * math.pi * f * MU0 / (2 * math.pi) * (math.log(ra) - lnmax))
        e[f"Bessel Z_int vs reaction integral @{f / 1e6:g} MHz"] = (abs(zr / z_internal_per_m(f, ra, sa) - 1),
                                                                   cfg["tol_independent"])
    for ln in (1.5e-3, 5e-3, 10e-3):
        for f in [cfg["f_lf_hz"], *cfg["freqs_hf_hz"]]:
            w = 2 * math.pi * f
            la = (w * (wire_ext_self(ln, ra) + wire_self_correction(ln, ra, f, sa).real)
                  + ln * z_internal_per_m(f, ra, sa).imag) / w
            lt = tube_peec_segment(ln, ra, f, sa, 80).imag / w
            bound = MU0 / (2 * math.pi) * (ra * ra / ln + (2 * ra) ** 6 / (48 * ln**5)) / la
            e[f"wire self vs tube PEEC l={ln * 1e3:g}mm @{f:.3g} Hz"] = (abs(la / lt - 1), bound)
    # proximity dipole (PEC geometric part) vs the exact two-wire line (mu0/pi)[arccosh(p/2r) - ln(p/r)] [RWV]
    lw, pw = 1.0, 1.5e-3
    pair = {"conductors": [wire("a", [(0, 0, 0), (lw * 1e3, 0, 0)], 0.3), wire("b", [(lw * 1e3, 1.5, 0), (0, 1.5, 0)], 0.3)],
            "planes": []}
    sg = _segments(pair)
    tot = sum(d for _, d, _ in _prox_terms(pair, sg, 2e7, sig))
    geo = np.real(np.ones(2) @ tot @ np.ones(2) / (-2j * math.pi * 2e7 * prox_factor(ra, 2e7, sa)))
    exact = MU0 / math.pi * (math.log(pw / ra) - math.acosh(pw / (2 * ra))) * lw
    e["proximity dipole vs exact two-wire line (PEC)"] = (abs(geo / exact - 1), 2.5 * (ra / pw) ** 2 + 4 * pw / lw)
    # finite cross-section of mutuals (note sec. 4.2a), through the assembly: closed form (filament + mean-value term,
    # prox off) vs the brute-force average of the filament kernel over both Bessel-profile cross-sections, summed over
    # the parallel pairs; tolerance = the stated remainder bound (d) of the same terms
    b3c = next(c for c in everything if c["id"] == "B3")
    c1c = next(c for c in everything if c["id"] == "C1")
    sg3 = _segments(b3c)
    pairs3 = [(p, q) for p in sg3 for q in sg3 if p["ci"] == 0 and q["ci"] == 1 and p["ax"] == q["ax"]]
    for f in (cfg["f_lf_hz"], cfg["freqs_hf_hz"][-1]):  # B3 M12: wire 1 - wire 2 pairs
        zb, _, _, ex, xr = _assemble(b3c, f, sig, prox=False)
        got = zb[0, 1] / (2j * math.pi * f)
        ref = sum(cross_section_average_mutual(p, q, f, sig) for p, q in pairs3)
        fil = sum(_pair_mutual(p, q) for p, q in pairs3)
        e[f"B3 M12 cross-section average @{f:.3g} Hz (shift {abs(ref - fil) / abs(ref):.1e})"] = (
            abs(got - ref), float(np.abs(ex[0]) @ xr @ np.abs(ex[1])))
    f1 = cfg["freqs_hf_hz"][1]  # C1: every segment-image pair of the loop
    pl1 = c1c["planes"][0]
    zm1 = pl1["z_top"] - skin_depth(f1, sig[pl1["mat"]]) / 2
    sg1 = _segments(c1c)
    zc, _, _, ex1, xr1 = _assemble(c1c, f1, sig, prox=False)
    zf, _, _, exf, xrf = _assemble(dict(c1c, planes=[]), f1, sig, prox=False)
    got = (zc[0, 0] - zf[0, 0]) / (2j * math.pi * f1)
    ipairs = [(p, q) for p in sg1 for q in sg1 if p["ax"] == q["ax"]]
    ref = sum(cross_section_average_mutual(p, q, f1, sig, zmirror=zm1) for p, q in ipairs)
    fil = sum(_pair_mutual(p, q, zmirror=zm1) for p, q in ipairs)
    e[f"C1 image term cross-section average @{f1 / 1e6:g} MHz (shift {abs(ref - fil) / abs(ref):.1e})"] = (
        abs(got - ref), float(np.abs(ex1[0]) @ xr1 @ np.abs(ex1[0]) - np.abs(exf[0]) @ xrf @ np.abs(exf[0])))
    rep("closed_forms_independent_check", e)

    # (2b) image code: runner's 3-D image term vs a generic Neumann quadrature over explicitly mirrored polylines
    def neumann(pa_, pb_, nq=64):
        xg_, wg_ = np.polynomial.legendre.leggauss(nq)
        tot_ = 0.0
        for a0, a1 in zip(pa_[:-1], pa_[1:], strict=True):
            for b0, b1 in zip(pb_[:-1], pb_[1:], strict=True):
                da, db = a1 - a0, b1 - b0
                if abs(da @ db) == 0.0:
                    continue
                qa, qb = a0 + np.outer((xg_ + 1) / 2, da), b0 + np.outer((xg_ + 1) / 2, db)
                rr = np.linalg.norm(qa[:, None, :] - qb[None, :, :], axis=-1)
                tot_ += (da @ db) * float((wg_ / 2) @ (1 / rr) @ (wg_ / 2))
        return MU0 / (4 * math.pi) * tot_

    c1 = next(c for c in everything if c["id"] == "C1")
    upath = dict(c1, conductors=[wire("u", [(0, 0, 0.5), (6, 0, 0.5), (6, 4, 0.5), (0, 4, 0.5)], 0.3)],
                 ports=[{"name": "p", "plus": ["u", 0], "minus": ["u", 3]}])
    upath["ports"] = [end_port("p", upath["conductors"][0])]
    e = {}
    for cc, fl in ((c1, c1["cmp_freqs"]), (upath, [2e7])):
        free = dict(cc, planes=[])
        for f in fl:
            w = 2 * math.pi * f
            img = np.imag(_assemble(cc, f, sig, prox=False, xsec=False)[0][0, 0]
                          - _assemble(free, f, sig, prox=False, xsec=False)[0][0, 0]) / w
            pl = cc["planes"][0]
            zm = pl["z_top"] - skin_depth(f, sig[pl["mat"]]) / 2
            path = np.array(cc["conductors"][0]["pts"])
            mirror = path * np.array([1, 1, -1]) + np.array([0, 0, 2 * zm])
            ref = -neumann(path, mirror)  # image current = -(mirrored path element) for a horizontal path
            e[f"{cc['conductors'][0]['name']} image term @{f / 1e6:g} MHz"] = (abs(img / ref - 1), ti)
    rep("image_plane_independent", e)

    # (2c) Wheeler recession vs Carson's exact half-space integral: per-unit-length inductance increment over a
    # perfect plane, |runner - Carson| <= mu0/2pi (delta/2h)^2 (second-order term, note sec. 4.3)
    hw, lw = 1e-3, 100.0
    e = {}
    for f in (5e5, *[x for x in cfg["freqs_hf_hz"]]):
        w = 2 * math.pi * f
        plane = dict(c1["planes"][0], x_min=-1.0, x_max=lw + 1, y_min=-1.0, y_max=1.0)
        line = {"id": "W", "cls": "check", "conductors": [wire("w", [(0, 0, hw * 1e3), (lw * 1e3, 0, hw * 1e3)], 0.002)],
                "planes": [plane], "ties": [], "compare": [("L11", 0, 0)]}
        line["ports"] = [end_port("p", line["conductors"][0])]
        lp = np.imag(_assemble(line, f, sig, prox=False, xsec=False)[0][0, 0]) / w
        lf_ = np.imag(_assemble(dict(line, planes=[]), f, sig, prox=False, xsec=False)[0][0, 0]) / w
        runner = (lp - lf_ + fil_mutual(0, lw, 0, lw, 2 * hw)) / lw  # increment over the unrecessed PEC image
        gam2 = 1j * w * MU0 * sig[plane["mat"]]
        car = integrate.quad(lambda t, g2=gam2: (np.exp(-t) / (t / (2 * hw) + np.sqrt((t / (2 * hw)) ** 2 + g2))).real,
                             0, np.inf, epsabs=0, epsrel=1e-11, limit=200)[0] / (2 * hw) * MU0 / math.pi
        dl = skin_depth(f, sig[plane["mat"]])
        e[f"Wheeler vs Carson @{f / 1e6:g} MHz (delta/2h={dl / (2 * hw):.3f})"] = (
            abs(runner - car) / (MU0 / (2 * math.pi)), (dl / (2 * hw)) ** 2)
    rep("wheeler_recession_independent", e)

    # (2d) tie assembly vs the explicit parallel formula (Z11 Z22 - Z12 Z21)/(Z11 + Z22 - Z12 - Z21) of the two-port
    b3 = next(c for c in everything if c["id"] == "B3")
    b4 = next(c for c in everything if c["id"] == "B4")
    asym = [staple("w1", 0.0), staple("w2", 1.5, span=7.0, hgt=1.2, d=0.25)]
    b3a = dict(b3, conductors=asym, ports=[end_port("p1", asym[0]), end_port("p2", asym[1])])
    b4a = dict(b4, conductors=asym, ports=[end_port("p", asym[0])])
    e = {}
    for two, tied, tag in ((b3, b4, "B4"), (b3a, b4a, "asymmetric")):
        for f in cfg["freqs_hf_hz"]:
            z2 = analytic_z(two, f, sig)
            zpar = (z2[0, 0] * z2[1, 1] - z2[0, 1] * z2[1, 0]) / (z2[0, 0] + z2[1, 1] - z2[0, 1] - z2[1, 0])
            e[f"{tag} @{f / 1e6:g} MHz"] = (abs(analytic_z(tied, f, sig)[0, 0] / zpar - 1), 1e-10)
    rep("tied_branch_independent", e)

    # (3) exact similarity scaling of every closed-form case value
    e = {}
    for c in cases:
        f0 = c["cmp_freqs"][-1]
        v1 = analytic_values(c, [f0], sig)
        v2 = analytic_values(scale_case(c, 2.0), [f0 / 4], sig)
        e[c["id"]] = (max(abs(v2[(lab, f0 / 4)] / (2 * v1[(lab, f0)]) - 1) for lab, _, _ in c["compare"]), 1e-9)
    rep("analytic_length_scaling", e)

    # (4) regime assumptions behind each closed form hold for the registered geometry
    e = {}
    f_lf = cfg["f_lf_hz"]
    for c in cases:
        if c["cls"].startswith("bar"):
            for k in c["conductors"]:  # round wire of the bar's half-diagonal: conservative skin-effect bound
                rb = 0.5 * math.hypot(k["width"], k["thickness"])
                lint = np.imag(z_internal_per_m(f_lf, rb, sig[k["mat"]])) / (2 * math.pi * f_lf)
                e[f"{c['id']}:{k['name']} LF skin deficit"] = (abs(1 - lint / (MU0 / (8 * math.pi))), 1e-3)
    pl_cases = [c for c in cases if c["planes"]]
    for c in pl_cases:
        pl = c["planes"][0]
        h = c["conductors"][0]["pts"][0][2] - pl["z_top"]
        for f in c["cmp_freqs"]:
            dl = skin_depth(f, sig[pl["mat"]])
            e[f"{c['id']} delta/t_plane @{f / 1e6:g} MHz"] = (dl / pl["thickness"], 0.2)
            e[f"{c['id']} (delta/2h)^2 @{f / 1e6:g} MHz"] = ((dl / (2 * h)) ** 2, 1e-3)
    rep("regime_valid", e)

    # (5) finite-plane truncation (2-D bound), with the 2-D BEM validated against the infinite-plane limit
    e = {}
    for c in pl_cases:
        pl = c["planes"][0]
        h = c["conductors"][0]["pts"][0][2] - pl["z_top"]
        rw = c["conductors"][0]["diameter"] / 2
        short = min(pl["x_max"] - pl["x_min"], pl["y_max"] - pl["y_min"])
        e[f"{c['id']} 2-D truncation estimate"] = (abs(strip_truncation_2d(h, 5e-3, rw, short / 2)),
                                                   cfg["tol_truncation"])
        e["BEM vs infinite plane (W=400h)"] = (abs(strip_truncation_2d(h, 5e-3, rw, 400 * h)), 2e-4)
    rep("plane_truncation_bound", e)
    return ok_all


# ============================================================ residual model error per case (inference)
def residual_model_error(case: dict, f: float, sig: dict, label: str | None = None) -> float:
    """Stated bound on |closed form - exact modeled geometry| / |closed form| for one compared quantity (worst over
    the case's quantities if label is None). Derivations: research note sec. 4.3. Terms, each per unit port current
    through the excitation vectors u_p (for ties, the branch split):
      (a) wire self term: the reaction with the infinite-wire distribution is stationary [RU], so the finite-length
          redistribution error is second order: <= mu0/2pi r^2/l per segment (perturbation potential varies by
          <= r/2 across the section; stiffness >= l/4 in mu0/2pi units), plus the moment-series remainder
          <= mu0/2pi (2r)^6/(48 l^5) (twice the first omitted term at d = 2r);
      (b) proximity: the dipole correction is leading order; its error is <= (2.5 (r/p)^2 + 8 r/l) of it per receiving
          segment (next multipole 1.5 (r/p)^2 from the exact two-wire line, axial non-locality (r/p)^2, end regions
          2 x 2r at each end with a factor-2 allowance for non-uniform density);
      (c) plane: second-order Wheeler/complex-image error (delta/2h)^2 relative [C] and the truncation allowance
          tol_truncation certified by plane_truncation_bound;
      (d) finite cross-section of every wire-wire and wire-image mutual (T0041, reviews T0051/T0052): the closed form
          carries the first-order mean-value term <|w|^2>/4 Lap M; the remainder is bounded rigorously by the Taylor
          remainder of the circle mean, <|w|^4>_abs/64 sup|Lap^2 M| (_pair_cross_section).
    Bars: DC Hoer-Love is exact for uniform current; 1e-4 covers the LF skin deficit (bounded by regime_valid)."""
    if case["cls"].startswith("bar"):
        return 1e-4
    w = 2 * math.pi * f
    zb, segs, pt, exc, xrem = _assemble(case, f, sig)
    worst = 0.0
    for lab, i, j in case["compare"]:
        if label is not None and lab != label:
            continue
        ui, uj = exc[i], exc[j]
        err = 0.0
        for k, s in enumerate(segs):
            if s["c"]["kind"] == "wire":
                r, ln = s["c"]["diameter"] / 2, s["length"]
                err += abs(ui[k] * uj[k]) * MU0 / (2 * math.pi) * (r * r / ln + (2 * r) ** 6 / (48 * ln**5))
        for si, d, pmin in pt:
            r = segs[si]["c"]["diameter"] / 2
            err += (2.5 * (r / pmin) ** 2 + 8 * r / segs[si]["length"]) * abs(ui @ d @ uj) / w
        err += float(np.abs(ui) @ xrem @ np.abs(uj))  # (d) cross-section remainder of wire-wire/-image mutuals
        err /= abs(np.imag(zb[i, j]) / w)
        for pl in case["planes"]:
            h = min(min(s["p0"][2], s["p1"][2]) for s in segs) - pl["z_top"]
            err += (skin_depth(f, sig[pl["mat"]]) / (2 * h)) ** 2 + case["trunc_allow"]
        worst = max(worst, err)
    return worst


# ============================================================ L2 path (lazy import)
def _to_l2(l2, case: dict, sig: dict):
    conds = []
    for c in case["conductors"]:
        if c["kind"] == "bar":
            conds.append(l2.Bar(name=c["name"], start=tuple(c["pts"][0]), end=tuple(c["pts"][1]),
                                width=c["width"], thickness=c["thickness"], sigma=sig[c["mat"]]))
        else:
            conds.append(l2.RoundWire(name=c["name"], points=tuple(tuple(p) for p in c["pts"]),
                                      diameter=c["diameter"], sigma=sig[c["mat"]]))
    planes = [l2.Plane(name=p["name"], x_min=p["x_min"], y_min=p["y_min"], x_max=p["x_max"], y_max=p["y_max"],
                       z_top=p["z_top"], thickness=p["thickness"], sigma=sig[p["mat"]]) for p in case["planes"]]
    ports = [l2.Port(name=p["name"], plus=l2.Terminal(*p["plus"]), minus=l2.Terminal(*p["minus"]))
             for p in case["ports"]]
    ties = [l2.Tie(l2.Terminal(*a), l2.Terminal(*b)) for a, b in case["ties"]]
    return conds, planes, ports, ties


def l2_solve(l2, case: dict, freqs, k: int, sig: dict) -> tuple[np.ndarray, dict]:
    conds, planes, ports, ties = _to_l2(l2, case, sig)
    res = l2.solve(conductors=conds, planes=planes, ports=ports, freqs_hz=list(freqs), refinement=k, ties=ties)
    z = np.asarray(res.z, dtype=complex)
    if z.shape != (len(freqs), len(ports), len(ports)):
        raise RuntimeError(f"l2.solve returned shape {z.shape} for case {case['id']}")
    return z, dict(getattr(res, "meta", {}) or {})


def _algebraic_tail(v) -> float:
    """Remaining error |L_n - L_inf| of the additive-refinement model L_k = L_inf + C k^-p (k = 1-based position in
    the refinement sequence, h ~ 1/k), fitted exactly to the last three values; inf if the data imply p <= 0."""
    n = len(v)
    ka, kb, kc = float(n - 2), float(n - 1), float(n)
    d1, d2 = abs(v[-2] - v[-3]), abs(v[-1] - v[-2])
    if d2 == 0.0:
        return 0.0
    if d1 == 0.0:
        return math.inf

    def q(p):  # d2/d1 implied by order p; decreases from ln(kc/kb)/ln(kb/ka) (p -> 0) to 0 (p -> inf)
        return (kb**-p - kc**-p) / (ka**-p - kb**-p)

    target = d2 / d1
    if target >= math.log(kc / kb) / math.log(kb / ka):
        return math.inf
    lo, hi = 1e-12, 1.0
    while q(hi) > target and hi < 256.0:
        lo, hi = hi, 2.0 * hi
    if q(hi) > target:
        return 0.0  # order > 256: the tail is negligible
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if q(mid) > target else (lo, mid)
    p = lo  # q(lo) > target: the smaller-order (heavier-tail) side of the converged bracket
    return d2 * kc**-p / (kb**-p - kc**-p)


def remaining_discretization_error(values, noise: float = 0.0, rho_min: float = 0.5, fs: float = 1.25,
                                   fs_unverified: float = 3.0, rho_two: float = 0.9) -> float:
    """Estimated |L_finest - L_converged| from L at successive refinement levels (finest last), same units.
    The L2 contract fixes a constant refinement ratio, so in the asymptotic range the changes d_k contract
    geometrically with a constant ratio rho = |d_k/d_(k-1)| (note sec. 4.4):
      * >= 4 levels, steady ratio (the last observed ratio does not exceed the previous one beyond what the noise
        floor can produce): geometric tail fs |d| rho/(1 - rho), rho = max(last two ratios, rho_min), Roache's
        three-grid factor fs = 1.25 [ROA];
      * >= 4 levels, decelerating ratio (asymptotic range not established, e.g. additive refinement with error
        ~ k^-p, review T0052): the larger of the geometric tail and the additive-refinement tail (_algebraic_tail),
        both with Roache's factor 3 for an unverified asymptotic range;
      * 3 levels (one ratio, cannot be checked): geometric tail with factor 3; the pre-registered rule never decides
        convergence on fewer than refinement_min_levels = 4 levels;
      * 2 levels: assume rho = 0.9 with factor 3 (27 x the change); 1 level: inf.
    Small-step guard (T0041): the tail base is max(|d_last|, rho_min |d_prev|), so one coincidentally small step
    cannot declare convergence. rho >= 1 -> inf. `noise` (absolute, on a change) is the change two levels can show
    from the solver alone (2 x solver_err_budget x |L| in the runner): a change at or below it gives no evidence of
    slow contraction. A constant sequence gives 0."""
    v = np.asarray(values, dtype=np.float64)
    if v.size < 2:
        return math.inf
    d = np.abs(np.diff(v))
    if v.size == 2:
        return fs_unverified * float(d[-1]) * rho_two / (1 - rho_two)

    def ratio(k):  # d[k] / d[k - 1]
        if d[k] <= noise:
            return 0.0
        den = max(float(d[k - 1]), noise)
        return math.inf if den == 0.0 else float(d[k] / den)

    r_last = ratio(-1)
    r_prev = ratio(-2) if v.size >= 4 else None
    rho = max(r_last, r_prev or 0.0, rho_min)
    base = max(float(d[-1]), rho_min * float(d[-2]))

    def geometric(factor):
        return math.inf if rho >= 1.0 else factor * base * rho / (1 - rho)

    if r_prev is None:
        return geometric(fs_unverified)
    jitter = 1e-9 * r_prev  # floating-point rounding of an exactly geometric sequence
    if noise > 0 and r_prev > 0 and math.isfinite(r_last) and math.isfinite(r_prev):
        jitter += (r_last * (noise / d[-1] + noise / d[-2])
                   + r_prev * (noise / d[-2] + noise / max(float(d[-3]), noise)))
    if d[-1] <= noise or r_last <= r_prev + jitter:
        return geometric(fs)
    return max(geometric(fs_unverified), fs_unverified * _algebraic_tail(v))


def l2_converged_solve(l2, case, freqs, sig, cfg):
    """Pre-registered refinement rule: solve levels k0, k0+1, ...; from the refinement_min_levels-th level on, stop at
    the first level where the estimated remaining discretization error of every L (all solved frequencies, compared
    entries) is below conv_tol relative, or at refinement_max. Returns (Z finest, {(fi, i, j): relative remaining
    error}, finest level, list of meta dicts)."""
    k0 = cfg["refinement_start"]
    kmax = min(cfg["refinement_max"], getattr(l2, "MAX_REFINEMENT", cfg["refinement_max"]))
    nmin = cfg["refinement_min_levels"]
    if nmin < 4 or kmax - k0 + 1 < nmin:
        raise ValueError("the refinement rule needs >= 4 levels (deceleration test) within refinement_max")
    w = 2 * math.pi * np.asarray(freqs)[:, None, None]
    keys = [(fi, i, j) for fi in range(len(freqs)) for _, i, j in case["compare"]]
    hist, metas = [], []
    for k in range(k0, kmax + 1):
        z, meta = l2_solve(l2, case, freqs, k, sig)
        hist.append(np.imag(z) / w)
        metas.append(meta)
        rem = {key: remaining_discretization_error([h[key] for h in hist],
                                                   noise=2 * cfg["solver_err_budget"] * abs(hist[-1][key]))
               / abs(hist[-1][key]) for key in keys}
        if len(hist) >= nmin and max(rem.values()) < cfg["conv_tol"]:
            break
    return z, rem, k, metas


def refinement_ratio_violation(mesh_h, cfg) -> float:
    """Constant-refinement-ratio check of one solve sequence (contract sec. 3, review T0052): the realized ratios
    h_k/h_(k+1) of meta['mesh_h'] must all be >= refinement_ratio_min and agree within refinement_ratio_spread
    (max/min). Returns the worst of min-shortfall and spread/allowed (<= 1 passes); inf if mesh_h is missing."""
    if len(mesh_h) < 2 or not all(isinstance(h, (int, float)) and not isinstance(h, bool) and h > 0 for h in mesh_h):
        return math.inf
    q = np.asarray(mesh_h[:-1], dtype=float) / np.asarray(mesh_h[1:], dtype=float)
    return float(max(cfg["refinement_ratio_min"] / q.min(), (q.max() / q.min()) / cfg["refinement_ratio_spread"]))


def solver_tol_required(case: dict, sig: dict, cfg: dict) -> float:
    """Relative port-Z accuracy the linear solve must reach so that L carries at most solver_err_budget relative
    error: a residual eps |Z|max becomes eps |Z|max / (omega |L|min) in L (amplification ~100 at 100 Hz for the
    bars, R >> omega L)."""
    amp = 1.0
    for f in case["cmp_freqs"]:
        z = analytic_z(case, f, sig)
        lmin = min(abs(np.imag(z[i, j])) for _, i, j in case["compare"])
        amp = max(amp, float(np.max(np.abs(np.diag(z)))) / lmin)
    return cfg["solver_err_budget"] / amp


def l2_phase(run: ExperimentRun, cases: list[dict], sig: dict, cfg: dict) -> None:
    from moduleforge.solvers import l2  # lazy: only the L2 path needs it

    rows, conv, recip, mono, tol_ratio, mesh_bad, h_ratio = [], {}, {}, {}, {}, {}, {}
    for c in cases:
        freqs = sorted(set(c["cmp_freqs"]) | set(c["info_freqs"]))
        z, rem, kfin, metas = l2_converged_solve(l2, c, freqs, sig, cfg)
        conv[c["id"]] = max(rem.values())
        c["_k"] = kfin
        need = solver_tol_required(c, sig, cfg)
        tols = [m.get("solver_tol") for m in metas]
        tol_ratio[c["id"]] = (max(float(t) for t in tols) / need
                              if all(isinstance(t, (int, float)) and not isinstance(t, bool) and t >= 0 for t in tols)
                              else math.inf)
        mesh_bad[c["id"]] = sum(not (isinstance(m.get("n_filaments"), int) and not isinstance(m["n_filaments"], bool)
                                      and m["n_filaments"] > 0) for m in metas)
        h_ratio[c["id"]] = refinement_ratio_violation([m.get("mesh_h") for m in metas], cfg)
        ana = analytic_values(c, c["cmp_freqs"], sig)
        for lab, i, j in c["compare"]:
            for f in c["cmp_freqs"]:
                fi = freqs.index(f)
                l2v = float(np.imag(z[fi, i, j]) / (2 * math.pi * f))
                la = ana[(lab, f)]
                rows.append(dict(case=c["id"], cls=c["cls"], quantity=lab, f_hz=f, l2=l2v, analytic=la,
                                 rel_err=abs(l2v - la) / abs(la), disc_unc=rem[(fi, i, j)] * abs(l2v / la),
                                 model_err=residual_model_error(c, f, sig, lab), refinement=kfin))
        if len(c["ports"]) > 1:
            recip[c["id"]] = float(np.max(np.abs(z[:, 0, 1] - z[:, 1, 0]) / np.abs(z[:, 0, 1])))
        if len(freqs) > 1:
            l11 = np.imag(z[:, 0, 0]) / (2 * math.pi * np.asarray(freqs))
            mono[c["id"]] = float(np.max(np.diff(l11) / l11[1:]))  # > 0 means L increased with f

    run.sanity("l2_converged", passed=max(conv.values()) < cfg["conv_tol"], value=max(conv.values()),
               threshold=cfg["conv_tol"], detail=json.dumps(conv))
    run.sanity("l2_solver_tolerance", passed=max(tol_ratio.values()) <= 1.0, value=max(tol_ratio.values()),
               threshold=1.0, detail="meta['solver_tol'] / required (solver_err_budget / amplification): "
               + json.dumps(tol_ratio))
    run.sanity("l2_one_mesh_per_solve", passed=sum(mesh_bad.values()) == 0, value=float(sum(mesh_bad.values())),
               threshold=0.0, detail="solves without a single integer meta['n_filaments']: " + json.dumps(mesh_bad))
    run.sanity("l2_constant_refinement_ratio", passed=max(h_ratio.values()) <= 1.0, value=max(h_ratio.values()),
               threshold=1.0, detail="worst of min ratio shortfall and ratio spread over refinement_ratio_spread, "
               "from meta['mesh_h'] (<= 1 passes): " + json.dumps(h_ratio))
    run.sanity("reciprocity", passed=bool(recip) and max(recip.values()) <= cfg["recip_tol"],
               value=max(recip.values()) if recip else None, threshold=cfg["recip_tol"], detail=json.dumps(recip))
    run.sanity("l_monotone_in_frequency", passed=bool(mono) and max(mono.values()) <= cfg["monotone_tol"],
               value=max(mono.values()) if mono else None, threshold=cfg["monotone_tol"], detail=json.dumps(mono))

    scal = {}
    for cid in cfg["scaling_cases"]:
        c = next((x for x in cases if x["id"] == cid), None)
        if c is None:
            continue
        f0 = c["cmp_freqs"][-1]
        z1, _ = l2_solve(l2, c, [f0], c["_k"], sig)
        z2, _ = l2_solve(l2, scale_case(c, 2.0), [f0 / 4], c["_k"], sig)
        ratio = (np.imag(z2[0, 0, 0]) / (2 * math.pi * f0 / 4)) / (np.imag(z1[0, 0, 0]) / (2 * math.pi * f0))
        scal[cid] = abs(ratio / 2 - 1)
    run.sanity("length_scaling", passed=bool(scal) and max(scal.values()) <= cfg["scaling_tol"],
               value=max(scal.values()) if scal else None, threshold=cfg["scaling_tol"], detail=json.dumps(scal))

    errs = np.array([r["rel_err"] for r in rows])
    unc = np.array([r["disc_unc"] + r["model_err"] for r in rows])
    lo, hi = float(np.max(np.maximum(errs - unc, 0.0))), float(np.max(errs + unc))
    # estimated error band, not a sampling CI and not a guaranteed bound (review T0052): the discretization part is a
    # GCI-type estimate (Roache's Fs, ~95 % empirical coverage), the model part a stated bound (note sec. 4.3)
    run.metric("max_rel_err_vs_analytic", float(errs.max()), ci=(lo, hi), n=len(rows), level=0.95)
    hf = [r["rel_err"] for r in rows if r["f_hz"] >= 1e6]
    lf = [r["rel_err"] for r in rows if r["f_hz"] < 1e6]
    run.metric("max_rel_err_hf", max(hf) if hf else float("nan"), n=len(hf))
    run.metric("max_rel_err_lf", max(lf) if lf else float("nan"), n=len(lf))
    ana = np.array([abs(r["analytic"]) for r in rows])
    run.metric("analytic_value_span", float(ana.max() / ana.min()), n=len(rows))  # diversity statistic
    run.metric("n_geometry_classes", float(len({r["cls"] for r in rows})), n=len(rows))
    out = Path(run.run_dir) / "e001_rows.json"
    out.write_text(json.dumps(rows, indent=1))
    run.artifact("e001_rows.json", out)


# ============================================================ main
DEFAULT_CFG = {
    "f_lf_hz": 100.0, "freqs_hf_hz": [5.0e6, 2.0e7, 8.0e7], "sigma_cu": 5.8e7, "sigma_al": 3.77e7,
    "plane_margin_mm": 15.0, "refinement_start": 1, "refinement_max": 5, "refinement_min_levels": 4,
    "refinement_ratio_min": 1.25, "refinement_ratio_spread": 1.1, "conv_tol": 0.01,
    "solver_err_budget": 1.0e-4, "recip_tol": 1.0e-3, "monotone_tol": 1.0e-3, "scaling_tol": 0.01,
    "scaling_cases": ["A1", "B2", "C1"], "tol_published": 1.0e-9, "tol_independent": 1.0e-6,
    "tol_truncation": 1.0e-3, "smoke_cases": ["A1", "A3", "B2", "B3", "B4", "C0", "C1"], "cases": list(ALL_CASES),
}


def checked_config(overrides: dict) -> dict:
    """DEFAULT_CFG updated by the spec's config, with every value type-checked against DEFAULT_CFG. Guards against
    YAML 1.1 (PyYAML, used by mfos) reading an unsigned exponent such as 5.0e6 as the string '5.0e6'."""
    unknown = sorted(set(overrides) - set(DEFAULT_CFG))
    if unknown:
        raise ValueError(f"config keys not in DEFAULT_CFG: {unknown}")
    cfg = {**DEFAULT_CFG, **overrides}

    def num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    for key, ref in DEFAULT_CFG.items():
        v = cfg[key]
        if num(ref):
            ok = num(v) and (isinstance(ref, float) or isinstance(v, int))
        elif isinstance(ref, list):
            ok = isinstance(v, list) and all(num(x) if num(ref[0]) else isinstance(x, str) for x in v)
        else:
            ok = isinstance(v, type(ref))
        if not ok:
            raise TypeError(f"config[{key!r}] = {v!r} has the wrong type (expected like {ref!r}); "
                            "write exponents with a sign (5.0e+6) in the YAML spec")
    return cfg


def main(mode: str) -> int:
    run_dir = {"analytic": "/tmp/e001-analytic", "smoke": "/tmp/e001-smoke"}.get(mode)
    with ExperimentRun(experiment_id="E001" if run_dir else None, run_dir=run_dir) as run:
        cfg = checked_config(run.config)
        sig = {CU: float(cfg["sigma_cu"]), AL: float(cfg["sigma_al"])}
        cases = build_cases(cfg)
        ok = analytic_checks(run, cases, sig, cfg)
        if mode == "analytic":
            run.notes += "analytic-only mode: L2 checks and metrics intentionally not produced (not evidence)"
            return 0 if ok else 1
        if mode == "smoke":
            cases = [c for c in cases if c["id"] in cfg["smoke_cases"]]
            for c in cases:
                c["cmp_freqs"] = [cfg["f_lf_hz"]] if c["cls"].startswith("bar") else [2.0e7]
                c["info_freqs"] = [2.0e7] if c["cls"].startswith("bar") else []
            cfg["refinement_max"] = cfg["refinement_start"] + cfg["refinement_min_levels"] - 1  # rule minimum
            cfg["scaling_cases"] = ["B2"]
        l2_phase(run, cases, sig, cfg)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--analytic-only", action="store_true")
    g.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    sys.exit(main("analytic" if a.analytic_only else "smoke" if a.smoke else "full"))
