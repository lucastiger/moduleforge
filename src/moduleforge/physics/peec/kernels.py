"""Vectorised closed-form partial-inductance kernels (SI, float64, numpy only).

Sources
-------
* Hoer & Love, "Exact inductance equations for rectangular conductors with applications to more complicated
  geometries", J. Res. NBS 69C (1965) 127-137 -> ``bar_mutual_hoer_love`` (parallel rectangular bars,
  uniform current density; self inductance is the coincident-bar limit). The 6-fold difference of the
  antiderivative ``_hl_f`` is the form given by Ruehli, IBM J. Res. Dev. 16 (1972) 470-481, and Paul,
  "Inductance: Loop and Partial" (Wiley 2010) ch. 5.
* Grover, "Inductance Calculations" (Dover 1962/1946): eq. for parallel filaments (ch. 3), general
  straight-filament Neumann integral (ch. 8) and the round-wire self inductance (ch. 2, eq. 7/8), with the
  internal-inductance term scaled by the skin effect.
* Neumann formula M = mu0/(4 pi) * int int (dl1 . dl2) / R for arbitrary straight filaments; the inner
  integral over one segment is analytic (asinh), the outer one uses a Gauss-Legendre rule on a smoothstep
  mapping so the integrable log singularity at touching segment ends is resolved.
"""
from __future__ import annotations

import numpy as np

MU0 = 4e-7 * np.pi  # H/m (classical exact-by-definition value; CODATA 2018 differs by 1e-10 relative)
_EPS = 1e-12  # m, regularisation of the filament distance


# ------------------------------------------------------------------------------------------------------
# Hoer-Love rectangular bars
# ------------------------------------------------------------------------------------------------------
def _hl_f(x, y, z):
    """Sixth antiderivative of 1/R (Hoer & Love 1965 / Ruehli 1972), R = sqrt(x^2+y^2+z^2)."""
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    x2, y2, z2 = x * x, y * y, z * z
    r = np.sqrt(x2 + y2 + z2)

    def lnp(a, bc2):  # ln(a + R), bc2 = b^2 + c^2, cancellation-free form for a < 0; 0 where R == 0
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.log(np.where(a >= 0, a + r, bc2 / (r - a)))
        return np.where(np.isfinite(v), v, 0.0)  # coefficient multiplying it vanishes when v is singular

    def atn(num, den):
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.arctan(num / den)
        return np.where(den == 0.0, 0.0, v)  # multiplied by a coefficient that vanishes with den

    out = (y2 * z2 / 4 - y2 * y2 / 24 - z2 * z2 / 24) * x * lnp(x, y2 + z2)
    out += (x2 * z2 / 4 - x2 * x2 / 24 - z2 * z2 / 24) * y * lnp(y, x2 + z2)
    out += (x2 * y2 / 4 - x2 * x2 / 24 - y2 * y2 / 24) * z * lnp(z, x2 + y2)
    out += (x2 * x2 + y2 * y2 + z2 * z2 - 3 * x2 * y2 - 3 * y2 * z2 - 3 * x2 * z2) * r / 60
    out -= x * y * z2 * z * atn(x * y, z * r) / 6
    out -= x * y2 * y * z * atn(x * z, y * r) / 6
    out -= x2 * x * y * z * atn(y * z, x * r) / 6
    return out


def bar_mutual_hoer_love(c1, d1, c2, d2, axis):
    """Mutual (or self, if identical) partial inductance [H] of parallel rectangular bars.

    ``c*`` (..., 3) centres, ``d*`` (..., 3) full extents (x, y, z) [m]; current flows along ``axis``
    (0, 1 or 2; scalar) in both bars, uniform current density.
    Returns M = -mu0/(4 pi A1 A2) * sum(+-F(dx, dy, dz)) over the 64 edge combinations (Hoer & Love 1965).
    """
    c1, d1, c2, d2 = (np.asarray(v, float) for v in (c1, d1, c2, d2))
    ax = int(axis)
    perm = [(ax + 1) % 3, (ax + 2) % 3, ax]  # -> (transverse 1, transverse 2, current axis)
    c1, d1, c2, d2 = (v[..., perm] for v in (c1, d1, c2, d2))
    lo1, hi1 = c1 - d1 / 2, c1 + d1 / 2
    lo2, hi2 = c2 - d2 / 2, c2 + d2 / 2
    # 64 edge combinations, evaluated in one batched call: per dimension, code = 2*u + v with u/v selecting
    # the upper (1) or lower (0) edge of bar 2 / bar 1; sign + if u == v else -
    codes = np.array(np.meshgrid(*[np.arange(4)] * 3, indexing="ij")).reshape(3, -1)  # (3, 64)
    u, v = (codes >> 1) & 1, codes & 1
    sgn = np.prod(np.where(u == v, 1.0, -1.0), axis=0)  # (64,)
    e2 = np.where(u == 1, hi2[..., :, None], lo2[..., :, None])  # (..., 3, 64)
    e1 = np.where(v == 1, hi1[..., :, None], lo1[..., :, None])
    dl = e2 - e1
    tot = np.sum(sgn * _hl_f(dl[..., 0, :], dl[..., 1, :], dl[..., 2, :]), axis=-1)
    a1 = d1[..., 0] * d1[..., 1]
    a2 = d2[..., 0] * d2[..., 1]
    # sign: three second-difference dimensions each carry (-1) relative to the +/- pattern above
    return -MU0 / (4 * np.pi) * tot / (a1 * a2)


# ------------------------------------------------------------------------------------------------------
# Parallel filaments (Grover) and general straight filaments (Neumann)
# ------------------------------------------------------------------------------------------------------
def filament_mutual_parallel(l1, l2, d, offset):
    """Mutual partial inductance [H] of two parallel straight filaments (Grover 1946, ch. 3, general case).

    ``l1``, ``l2`` lengths, ``d`` perpendicular distance, ``offset`` = (start of 2) - (start of 1) along the
    common axis (all >= 0 lengths, any-sign offset). Reduces to the equal-length formula
    mu0 l/(2 pi) [asinh(l/d) - sqrt(1+d^2/l^2) + d/l] for l1=l2, offset=0.
    """
    d = np.maximum(np.asarray(d, float), _EPS)

    def h(z):
        return z * np.arcsinh(z / d) - np.sqrt(z * z + d * d)

    o = np.asarray(offset, float)
    # int_0^l1 int_o^(o+l2) dz2 dz1 / sqrt(d^2+(z2-z1)^2) = -[h(o+l2-l1) - h(o+l2) - h(o-l1) + h(o)]
    val = -(h(o + l2 - l1) - h(o + l2) - h(o - l1) + h(o))
    return MU0 / (4 * np.pi) * val


_GL_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _smooth_gl(n):
    if n not in _GL_CACHE:
        u, w = np.polynomial.legendre.leggauss(n)
        u = 0.5 * (u + 1.0)
        w = 0.5 * w
        t = u * u * (3.0 - 2.0 * u)  # smoothstep clusters nodes at both ends
        _GL_CACHE[n] = (t, w * 6.0 * u * (1.0 - u))
    return _GL_CACHE[n]


def segment_mutual(p1, u1, l1, p2, u2, l2, n=6, core=0.0):
    """Neumann mutual partial inductance [H] of straight filaments, broadcast over leading dims.

    Segment k runs from ``pk`` along unit vector ``uk`` for length ``lk``. Current direction = ``uk``
    (the sign of (u1.u2) is kept). Inner integral analytic, outer Gauss-Legendre with ``n`` nodes.

    ``core`` (m, broadcastable) is a finite-radius core: the kernel 1/R becomes 1/sqrt(R^2 + core^2). With
    core = a (wire radius, surface current) every pair of segments of one round wire is coupled as thick
    (tube) conductors: the parallel/collinear limit is exactly Grover's tube formula
    mu0 l/(2 pi) [asinh(l/a) - sqrt(1 + (a/l)^2) + a/l] (= GMD a for a surface-current tube), and the
    polyline inductance stays finite and converges as the polyline is refined (no zero-radius singularity
    between touching/near segments).
    """
    t, w = _smooth_gl(n)
    p1, u1, p2, u2 = (np.asarray(v, float) for v in (p1, u1, p2, u2))
    l1 = np.asarray(l1, float)[..., None]
    l2 = np.asarray(l2, float)
    pa = p1[..., None, :] + (t * l1)[..., None] * u1[..., None, :]  # (..., n, 3) points on segment 1
    r = pa - p2[..., None, :]
    u2b = u2[..., None, :]
    m = np.sum(r * u2b, axis=-1)
    q2 = np.maximum(np.sum(r * r, axis=-1) - m * m, 0.0) + _EPS * _EPS + np.asarray(core, float)[..., None] ** 2
    q = np.sqrt(q2)
    inner = np.arcsinh((l2[..., None] - m) / q) - np.arcsinh(-m / q)
    dot = np.sum(u1 * u2, axis=-1)
    return MU0 / (4 * np.pi) * dot * np.sum(inner * w * l1, axis=-1)


def round_wire_self(length, radius, delta=None):
    """Self partial inductance [H] of a straight round wire (Grover 1946, ch. 2).

    L = mu0 l/(2 pi) [asinh(l/a) - sqrt(1+(a/l)^2) + a/l + xi/4], xi = internal-inductance factor:
    xi = 1 at DC (uniform current, the classical ln(2l/a) - 3/4), and xi = min(1, 2 delta/a) under the skin
    effect (internal reactance equals R_ac: L_int = mu0 l delta/(4 pi a)).
    """
    length = np.asarray(length, float)
    a = np.asarray(radius, float)
    xi = 1.0 if delta is None else np.minimum(1.0, 2.0 * np.asarray(delta, float) / a)
    return MU0 * length / (2 * np.pi) * (np.arcsinh(length / a) - np.sqrt(1 + (a / length) ** 2) + a / length
                                         + xi / 4.0)


# ------------------------------------------------------------------------------------------------------
# Resistance with skin effect
# ------------------------------------------------------------------------------------------------------
def skin_depth(freq_hz, sigma, mu_r=1.0):
    """delta = 1/sqrt(pi f mu sigma) [m] (Jackson, Classical Electrodynamics, 3rd ed., sec. 5.18)."""
    return 1.0 / np.sqrt(np.pi * np.asarray(freq_hz, float) * MU0 * mu_r * np.asarray(sigma, float))


def bar_resistance(length, width, thickness, sigma, delta):
    """AC resistance [Ohm] of a rectangular bar, current confined to a skin layer around the perimeter.

    Wheeler (Proc. IRE 1942)/Paul (Inductance: Loop and Partial, 2010) approximation: A_eff = w t - (w - 2 delta)(t - 2 delta) for
    delta < min(w, t)/2 else w t. Gives R = R_dc (w t)/A_eff -> R ~ sqrt(f) for delta << t.
    """
    w, t = np.asarray(width, float), np.asarray(thickness, float)
    inner = np.maximum(w - 2 * delta, 0.0) * np.maximum(t - 2 * delta, 0.0)
    a_eff = np.where(delta < 0.5 * np.minimum(w, t), w * t - inner, w * t)
    return np.asarray(length, float) / (sigma * a_eff)


def wire_resistance(length, radius, sigma, delta):
    """AC resistance [Ohm] of a round wire: skin annulus pi (a^2 - (a-delta)^2) for delta < a (Grover/Smythe)."""
    a = np.asarray(radius, float)
    inner = np.maximum(a - delta, 0.0)
    a_eff = np.pi * (a * a - inner * inner)
    return np.asarray(length, float) / (sigma * a_eff)
