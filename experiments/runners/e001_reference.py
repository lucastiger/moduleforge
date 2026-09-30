"""E001 runner: validate the L2 reference solver against closed forms on canonical geometries.

Design (pre-registered in experiments/drafts/E001.yaml; rationale in research/notes/o001-l2-reference.md):
every case is a geometry whose closed form is exact for the *modeled* geometry (partial-inductance /
PEEC formulation with the same segment topology) up to a stated residual model error. The closed forms
are validated on every run before they are used (sanity checks closed_forms_*).

Modes:
  --analytic-only  closed-form self-checks only; never imports moduleforge.solvers; exit 1 if any fails.
  --smoke          one case per geometry class at 20 MHz (bars also at their LF comparison frequency).
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
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

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


def build_cases(cfg: dict) -> list[dict]:
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
    return cases


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


def _pair_mutual(si, sj, zmirror=None):
    """Mutual partial inductance between segment si and sj (or sj's mirror image about z = zmirror)."""
    if si["ax"] != sj["ax"]:
        return 0.0
    p0, p1 = sj["p0"].copy(), sj["p1"].copy()
    sgn_j = sj["sgn"]
    if zmirror is not None:
        p0[2], p1[2] = 2 * zmirror - p0[2], 2 * zmirror - p1[2]
        if sj["ax"] != 2:
            sgn_j = -sgn_j  # image of a horizontal current is reversed; a vertical one keeps its direction
    ax = si["ax"]
    kinds = (si["c"]["kind"], sj["c"]["kind"])
    if kinds == ("wire", "wire"):
        tr = [d for d in range(3) if d != ax]
        dist = math.hypot(si["p0"][tr[0]] - p0[tr[0]], si["p0"][tr[1]] - p0[tr[1]])
        a = sorted((si["p0"][ax], si["p1"][ax]))
        b = sorted((p0[ax], p1[ax]))
        if dist == 0.0:
            raise ValueError("collinear distinct wire segments are not in the E001 case set")
        m = fil_mutual(a[0], a[1], b[0], b[1], dist)
    elif kinds == ("bar", "bar"):
        sj2 = dict(sj, p0=p0, p1=p1)
        m = box_mutual(*_box(si), *_box(sj2))
    else:
        raise ValueError("bar-wire mutual not needed in E001")
    return si["sgn"] * sgn_j * m


def _mat(c):
    return c["mat"]


def analytic_z(case: dict, f_hz: float, sig: dict) -> np.ndarray:
    """Closed-form port impedance matrix (ohm) of a case at one frequency."""
    segs = _segments(case)
    n = len(segs)
    w = 2 * math.pi * f_hz
    zp = np.zeros((n, n), dtype=complex)
    for i, si in enumerate(segs):
        c = si["c"]
        if c["kind"] == "wire":
            r = c["diameter"] / 2
            zp[i, i] = 1j * w * wire_ext_self(si["length"], r) + si["length"] * z_internal_per_m(f_hz, r, sig[_mat(c)])
        else:
            zp[i, i] = si["length"] / (sig[_mat(c)] * c["width"] * c["thickness"]) + 1j * w * _pair_mutual(si, si)
        for j in range(i + 1, n):
            zp[i, j] = zp[j, i] = 1j * w * _pair_mutual(si, segs[j])
    for pl in case["planes"]:  # thick floating plane: image about the Wheeler-recessed surface [W]
        zs = pl["z_top"] - skin_depth(f_hz, sig[pl["mat"]]) / 2.0
        for i, si in enumerate(segs):
            for j, sj in enumerate(segs):
                zp[i, j] += 1j * w * _pair_mutual(si, sj, zmirror=zs)
    # port incidence: each port runs along one conductor from vertex `plus` to vertex `minus`
    cmat = np.zeros((len(case["ports"]), n))
    for pi, p in enumerate(case["ports"]):
        (cn, v0), (cn2, v1) = p["plus"], p["minus"]
        assert cn == cn2 and v1 > v0
        for i, s in enumerate(segs):
            if s["c"]["name"] == cn and v0 <= s["k"] < v1:
                cmat[pi, i] = 1.0
    zb = cmat @ zp @ cmat.T
    if case["ties"]:  # E001 ties short all branch ends pairwise: parallel combination of the branches
        full = np.zeros((len(case["conductors"]), n))
        for ci in range(len(case["conductors"])):
            full[ci] = [1.0 if s["ci"] == ci else 0.0 for s in segs]
        zbb = full @ zp @ full.T
        zb = np.array([[1.0 / np.sum(np.linalg.inv(zbb))]])
    return zb


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
    e["HL mutual vs Gauss-Legendre 6D"] = (abs(box_mutual(lo1, hi1, lo2, hi2) / quad - 1), 1e-6)
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
    c0 = json.loads(json.dumps(next(c for c in cases if c["id"] == "C0")))
    c0["conductors"][0]["diameter"] = 2e-6  # Grover's closed form drops O(r/a) terms: compare in the thin limit
    lc0 = analytic_values(c0, [1e-3], sig)[("L11", 1e-3)]
    e["rect loop: partial sum vs Grover closed form (r=1um)"] = (
        abs(lc0 / grover_rectangle_loop(10e-3, 5e-3, 1e-6) - 1), 1e-6 / 5e-3)
    rep("closed_forms_independent_check", e)

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
def residual_model_error(case: dict, f: float, sig: dict) -> float:
    """Stated bound on (closed form - exact modeled geometry)/closed form; see the research note, sec. 4."""
    if case["cls"].startswith("bar"):
        return 1e-4
    rw = case["conductors"][0]["diameter"] / 2
    lmin = min(abs(np.subtract(p1, p0)).max() for c in case["conductors"]
               for p0, p1 in zip(c["pts"][:-1], c["pts"][1:], strict=True))
    err = 0.5 * (rw / lmin) ** 2  # tube-GMD substitution in non-log terms, O((r/l)^2)
    if len(case["conductors"]) > 1:
        pitch = 1.5e-3
        err += (rw / pitch) ** 2 / math.log(pitch / rw)  # proximity: exact 2-wire HF result arccosh(p/2r) vs
        # ln(p/r) differs by ~(r/p)^2 in a term of size ln(p/r) (RWV 4.x two-wire line)
    for pl in case["planes"]:
        h = case["conductors"][0]["pts"][0][2] - pl["z_top"]
        err += (skin_depth(f, sig[pl["mat"]]) / (2 * h)) ** 2 + (rw / (2 * h)) ** 2 + 1e-3  # 2nd-order Wheeler,
        # wire-plane proximity, truncation allowance (checked by plane_truncation_bound)
    return err


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


def l2_solve(l2, case: dict, freqs, k: int, sig: dict) -> np.ndarray:
    conds, planes, ports, ties = _to_l2(l2, case, sig)
    res = l2.solve(conductors=conds, planes=planes, ports=ports, freqs_hz=list(freqs), refinement=k, ties=ties)
    z = np.asarray(res.z, dtype=complex)
    if z.shape != (len(freqs), len(ports), len(ports)):
        raise RuntimeError(f"l2.solve returned shape {z.shape} for case {case['id']}")
    return z


def l2_converged_solve(l2, case, freqs, sig, cfg):
    """Pre-registered refinement rule: levels k0, k0+1, ...; stop at the first k with max relative change of
    every compared/driving-point L between k and k+1 below conv_tol; report level k+1 values."""
    k = cfg["refinement_start"]
    kmax = min(cfg["refinement_max"], getattr(l2, "MAX_REFINEMENT", cfg["refinement_max"]))
    z_prev = l2_solve(l2, case, freqs, k, sig)
    while True:
        z = l2_solve(l2, case, freqs, k + 1, sig)
        w = 2 * math.pi * np.asarray(freqs)[:, None, None]
        lz, lp = np.imag(z) / w, np.imag(z_prev) / w
        idx = [(i, j) for _, i, j in case["compare"]]
        change = max(float(np.max(np.abs(lz[:, i, j] - lp[:, i, j]) / np.abs(lz[:, i, j]))) for i, j in idx)
        if change < cfg["conv_tol"] or k + 1 >= kmax:
            return z, z_prev, change, k + 1
        z_prev, k = z, k + 1


def l2_phase(run: ExperimentRun, cases: list[dict], sig: dict, cfg: dict) -> None:
    from moduleforge.solvers import l2  # lazy: only the L2 path needs it

    rows, conv_changes, recip, mono = [], {}, {}, {}
    for c in cases:
        freqs = sorted(set(c["cmp_freqs"]) | set(c["info_freqs"]))
        z, zp, change, kfin = l2_converged_solve(l2, c, freqs, sig, cfg)
        conv_changes[c["id"]] = change
        c["_k"] = kfin
        ana = analytic_values(c, c["cmp_freqs"], sig)
        for lab, i, j in c["compare"]:
            for f in c["cmp_freqs"]:
                fi = freqs.index(f)
                l2v = float(np.imag(z[fi, i, j]) / (2 * math.pi * f))
                l2p = float(np.imag(zp[fi, i, j]) / (2 * math.pi * f))
                la = ana[(lab, f)]
                rows.append(dict(case=c["id"], cls=c["cls"], quantity=lab, f_hz=f, l2=l2v, analytic=la,
                                 rel_err=abs(l2v - la) / abs(la), disc_unc=abs(l2v - l2p) / abs(la),
                                 model_err=residual_model_error(c, f, sig), refinement=kfin))
        if len(c["ports"]) > 1:
            recip[c["id"]] = float(np.max(np.abs(z[:, 0, 1] - z[:, 1, 0]) / np.abs(z[:, 0, 1])))
        if len(freqs) > 1:
            l11 = np.imag(z[:, 0, 0]) / (2 * math.pi * np.asarray(freqs))
            mono[c["id"]] = float(np.max(np.diff(l11) / l11[1:]))  # > 0 means L increased with f

    run.sanity("l2_converged", passed=max(conv_changes.values()) < cfg["conv_tol"],
               value=max(conv_changes.values()), threshold=cfg["conv_tol"],
               detail=json.dumps(conv_changes))
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
        z1 = l2_solve(l2, c, [f0], c["_k"], sig)
        z2 = l2_solve(l2, scale_case(c, 2.0), [f0 / 4], c["_k"], sig)
        ratio = (np.imag(z2[0, 0, 0]) / (2 * math.pi * f0 / 4)) / (np.imag(z1[0, 0, 0]) / (2 * math.pi * f0))
        scal[cid] = abs(ratio / 2 - 1)
    run.sanity("length_scaling", passed=bool(scal) and max(scal.values()) <= cfg["scaling_tol"],
               value=max(scal.values()) if scal else None, threshold=cfg["scaling_tol"], detail=json.dumps(scal))

    errs = np.array([r["rel_err"] for r in rows])
    unc = np.array([r["disc_unc"] + r["model_err"] for r in rows])
    lo, hi = float(np.max(np.maximum(errs - unc, 0.0))), float(np.max(errs + unc))
    run.metric("max_rel_err_vs_analytic", float(errs.max()), ci=(lo, hi), n=len(rows))
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
    "plane_margin_mm": 15.0, "refinement_start": 1, "refinement_max": 5, "conv_tol": 0.01,
    "recip_tol": 1.0e-3, "monotone_tol": 1.0e-3, "scaling_tol": 0.01, "scaling_cases": ["A1", "B2", "C1"],
    "tol_published": 1.0e-9, "tol_independent": 1.0e-3, "tol_truncation": 1.0e-3,
    "smoke_cases": ["A1", "A3", "B2", "B4", "C1"],
}


def main(mode: str) -> int:
    run_dir = {"analytic": "/tmp/e001-analytic", "smoke": "/tmp/e001-smoke"}.get(mode)
    with ExperimentRun(experiment_id="E001" if run_dir else None, run_dir=run_dir) as run:
        cfg = {**DEFAULT_CFG, **run.config}
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
            cfg["refinement_max"] = cfg["refinement_start"] + 1
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
