"""Double-double (about 106-bit) evaluation of the Hoer-Love corner function (R3, T0071).

The Hoer-Love box formula [HL] is a signed sum of 64 values of ``hl_f``.  For thin boxes (a graded skin-depth layer of a few
micrometres next to millimetre lengths) the terms are larger than the sum by a factor ~ (length / thickness)^4, so float64
loses up to 1e-6 relative (measured 1.8e-6 on 1 um layers against a tensor Gauss rule).  Here every term is evaluated with
unevaluated sums of two float64 (Dekker / Knuth error-free transforms [DH]: relative error of one operation <= ~4 u^2,
u = 2^-53) and the corner sum is accumulated in the same arithmetic, so the sum is exact to ~ u^2 x (sum of |terms|).

[DH] Hida, Li, Bailey, "Library for double-double and quad-double arithmetic" (2008) / Dekker (1971), Knuth TAOCP 2, 4.2.2.
A value is a pair (hi, lo) of float64 arrays, |lo| <= ulp(hi)/2.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

_SPLIT = 134217729.0  # 2^27 + 1 (Veltkamp split of a float64)
LN2 = (0.6931471805599453, 2.3190468138462996e-17)
HALF_PI = (1.5707963267948966, 6.123233995736766e-17)
U2 = 2.0 ** -106  # unit roundoff of the double-double format
_J_LOG, _J_ATAN = 23, 18  # series lengths: |z|^2 <= 0.0295 (log), a^2 <= 0.0097 (atan after three halvings)


def _two_sum(a, b):
    s = a + b
    bb = s - a
    return s, (a - (s - bb)) + (b - bb)


def _qts(a, b):
    s = a + b
    return s, b - (s - a)


def _split(a):
    t = _SPLIT * a
    hi = t - (t - a)
    return hi, a - hi


def _two_prod(a, b):
    p = a * b
    ah, al = _split(a)
    bh, bl = _split(b)
    return p, ((ah * bh - p) + ah * bl + al * bh) + al * bl


def dd(x):
    x = np.asarray(x, dtype=np.float64)
    return x, np.zeros_like(x)


def dd_diff(a, b):
    """Exact a - b of two float64 arrays as a double-double."""
    return _two_sum(np.asarray(a, np.float64), -np.asarray(b, np.float64))


def add(x, y):
    s1, s2 = _two_sum(x[0], y[0])
    t1, t2 = _two_sum(x[1], y[1])
    s2 = s2 + t1
    s1, s2 = _qts(s1, s2)
    s2 = s2 + t2
    return _qts(s1, s2)


def neg(x):
    return -x[0], -x[1]


def sub(x, y):
    return add(x, neg(y))


def mul(x, y):
    p1, p2 = _two_prod(x[0], y[0])
    return _qts(p1, p2 + (x[0] * y[1] + x[1] * y[0]))


def mulf(x, f):
    p1, p2 = _two_prod(x[0], f)
    return _qts(p1, p2 + x[1] * f)


def div(x, y):
    q1 = x[0] / y[0]
    r = sub(x, mulf(y, q1))
    q2 = r[0] / y[0]
    r = sub(r, mulf(y, q2))
    q3 = r[0] / y[0]
    s, e = _qts(q1, q2)
    return add((s, e), (q3, np.zeros_like(q3)))


def sqrt(x):
    """sqrt of a non-negative double-double (0 -> 0)."""
    pos = x[0] > 0
    s = np.sqrt(np.where(pos, x[0], 1.0))
    p = _two_prod(s, s)
    r = sub(x, p)
    h, lo = _qts(s, r[0] / (2.0 * s))
    return np.where(pos, h, 0.0), np.where(pos, lo, 0.0)


def _inv_odd(n_terms: int):
    out = []
    for j in range(n_terms):
        f = Fraction(1, 2 * j + 1)
        h = float(f)
        out.append((h, float(f - Fraction(h))))
    return out


_INV = _inv_odd(max(_J_LOG, _J_ATAN) + 1)


def _series(z2, n_terms: int):
    """sum_{j < n_terms} z2^j / (2 j + 1) (Horner, double-double)."""
    one = np.ones_like(z2[0])
    acc = (_INV[n_terms - 1][0] * one, _INV[n_terms - 1][1] * one)
    for j in range(n_terms - 2, -1, -1):
        acc = add(mul(acc, z2), (_INV[j][0] * one, _INV[j][1] * one))
    return acc


def log(x):
    """Natural logarithm of a positive double-double: x = X 2^e, X in [sqrt(1/2), sqrt 2), log X = 2 atanh((X-1)/(X+1))."""
    m, e = np.frexp(x[0])
    low = m < 0.7071067811865476
    e = np.where(low, e - 1, e)
    X = (np.ldexp(x[0], -e), np.ldexp(x[1], -e))
    one = (np.ones_like(X[0]), np.zeros_like(X[0]))
    z = div(sub(X, one), add(X, one))
    s = _series(mul(z, z), _J_LOG)
    lg = mulf(mul(z, s), 2.0)
    return add(lg, mulf((LN2[0] * np.ones_like(X[0]), LN2[1] * np.ones_like(X[0])), e.astype(np.float64)))


def atan_pos(t):
    """arctan of a non-negative double-double: big arguments by pi/2 - atan(1/t), then three halvings
    atan t = 2 atan(t / (1 + sqrt(1 + t^2))) and the Maclaurin series."""
    one = (np.ones_like(t[0]), np.zeros_like(t[0]))
    big = t[0] > 1.0
    safe = (np.where(big, t[0], 1.0), np.where(big, t[1], 0.0))
    inv = div(one, safe)
    a = (np.where(big, inv[0], t[0]), np.where(big, inv[1], t[1]))
    for _ in range(3):
        a = div(a, add(one, sqrt(add(one, mul(a, a)))))
    a2 = mul(a, a)
    s = _series((-a2[0], -a2[1]), _J_ATAN)
    res = mulf(mul(a, s), 8.0)
    hp = (HALF_PI[0] * np.ones_like(t[0]), HALF_PI[1] * np.ones_like(t[0]))
    alt = sub(hp, res)
    return np.where(big, alt[0], res[0]), np.where(big, alt[1], res[1])


def _abs(x):
    s = np.where(x[0] < 0, -1.0, 1.0)
    return x[0] * s, x[1] * s


def hl_f(x, y, z):
    """Double-double Hoer-Love function (same function as ``l2_core.hl_f``; even in each argument)."""
    x, y, z = _abs(x), _abs(y), _abs(z)
    x2, y2, z2 = mul(x, x), mul(y, y), mul(z, z)
    r = sqrt(add(add(x2, y2), z2))
    xy, yz, zx = mul(x2, y2), mul(y2, z2), mul(z2, x2)
    quart = add(add(mul(x2, x2), mul(y2, y2)), mul(z2, z2))
    poly = sub(quart, mulf(add(add(xy, yz), zx), 3.0))
    out = _scale_div(mul(poly, r), 60.0)

    def logt(a, b2, c2, b2c2):
        rho2 = add(b2, c2)
        ok = (rho2[0] > 0) & (a[0] > 0)
        sr = (np.where(ok, rho2[0], 1.0), np.where(ok, rho2[1], 0.0))
        rho = sqrt(sr)
        ra = add(a, r)
        ra = (np.where(ok, ra[0], 1.0), np.where(ok, ra[1], 0.0))
        ash = log(div(ra, rho))
        coef = sub(mulf(b2c2, 6.0), add(mul(b2, b2), mul(c2, c2)))
        t = _scale_div(mul(mul(coef, a), ash), 24.0)
        return np.where(ok, t[0], 0.0), np.where(ok, t[1], 0.0)

    def tant(a, b, c, c2):
        den = mul(c, r)
        ok = (den[0] > 0) & (a[0] > 0) & (b[0] > 0)
        sd = (np.where(ok, den[0], 1.0), np.where(ok, den[1], 0.0))
        at = atan_pos(div(mul(a, b), sd))
        t = _scale_div(mul(mul(mul(mul(a, b), c), c2), at), 6.0)
        return np.where(ok, t[0], 0.0), np.where(ok, t[1], 0.0)

    out = add(out, logt(x, y2, z2, yz))
    out = add(out, logt(y, x2, z2, zx))
    out = add(out, logt(z, x2, y2, xy))
    out = sub(out, tant(x, y, z, z2))
    out = sub(out, tant(x, z, y, y2))
    out = sub(out, tant(z, y, x, x2))
    return out


def _scale_div(x, d: float):
    """x / d for a float d, to double-double accuracy."""
    q1 = x[0] / d
    r = sub(x, _two_prod(q1, np.full_like(q1, d)))
    return _qts(q1, r[0] / d)
