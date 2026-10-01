"""E001 design DoD: B3's stated model error must bound its mutual inductance error against an exact reference.

B3 = two Al staples (Ø0.3 mm, 1.5 mm legs, 8 mm top) 1.5 mm apart. Perpendicular segment pairs couple with exactly
zero (dl1 . dl2 = 0), so the exact M12 is the signed sum over the five parallel, axially aligned segment pairs of
the exact filament mutual M(l, d) (Grover 1946) averaged over both cross-sections: uniform current at DC, surface
current in the thin-skin limit. The relative position of two points in the two discs is isotropic, so the average
is over the centre distance D shifted by w, |w| distributed as disc line picking (DC) or a circle chord (surface).
Reviews T0051/T0052 of T0041: the closed form keeps every inter-wire mutual at the centre distance and states
<= 1e-6, but the finite cross-section shifts M12 by ~4-8e-4 (the same <d> mechanism as the self terms).
"""
import math
import sys

from scipy import integrate

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

MU0 = 4e-7 * math.pi
TIGHT = {"epsabs": 0.0, "epsrel": 1e-11, "limit": 400}
cfg = dict(R.DEFAULT_CFG)
sig = {R.CU: float(cfg["sigma_cu"]), R.AL: float(cfg["sigma_al"])}
case = next(c for c in R.build_cases(cfg) if c["id"] == "B3")
w1, w2 = case["conductors"]
a = w1["diameter"] / 2


def segs(w):
    return [(p0, p1) for p0, p1 in zip(w["pts"][:-1], w["pts"][1:], strict=True)]


def M(length, d):
    return MU0 / (2 * math.pi) * (length * math.asinh(length / d) - math.hypot(length, d) + d)


def disc_pdf(r):
    u = r / (2 * a)
    return 4 * r / (math.pi * a * a) * (math.acos(u) - u * math.sqrt(1 - u * u))


def averaged(length, D, surface):
    def over_angle(rho):
        return integrate.quad(lambda th: M(length, math.sqrt(D * D + rho * rho + 2 * D * rho * math.cos(th))),
                              0, math.pi, **TIGHT)[0] / math.pi
    if surface:  # chord of the surface circle: rho = 2a sin(phi/2), phi uniform on [0, pi]
        return integrate.quad(lambda phi: over_angle(2 * a * math.sin(phi / 2)), 0, math.pi, **TIGHT)[0] / math.pi
    return integrate.quad(lambda rho: over_angle(rho) * disc_pdf(rho), 0, 2 * a, **TIGHT)[0]


def exact_m12(surface):
    total = 0.0
    for p0, p1 in segs(w1):
        for q0, q1 in segs(w2):
            u = [b - c for b, c in zip(p1, p0, strict=True)]
            v = [b - c for b, c in zip(q1, q0, strict=True)]
            lu, lv = math.hypot(*u), math.hypot(*v)
            dot = sum(x * y for x, y in zip(u, v, strict=True)) / (lu * lv)
            if abs(dot) < 1e-12:
                continue  # perpendicular: exactly zero
            assert abs(abs(dot) - 1) < 1e-12 and abs(lu - lv) < 1e-15, "B3 geometry changed; update this check"
            axis = [x / lu for x in u]
            off = [b - c for b, c in zip(q0 if dot > 0 else q1, p0, strict=True)]
            along = sum(x * y for x, y in zip(off, axis, strict=True))
            assert abs(along) < 1e-15, "B3 parallel segments are no longer axially aligned; update this check"
            D = math.sqrt(max(sum(x * x for x in off) - along * along, 0.0))
            total += math.copysign(averaged(lu, D, surface), dot)
    return total


problems = []
for f, surface in ((100.0, False), (1e10, True)):
    ref = exact_m12(surface)
    ana = R.analytic_values(case, [f], sig)[("M12", f)]
    err, bound = abs(ana - ref) / abs(ref), R.residual_model_error(case, f, sig, "M12")  # the bound recorded for M12
    print(f"B3 M12 f={f:.0e} Hz: runner {ana * 1e12:.4f} pH, exact {ref * 1e12:.4f} pH, error {err:.2e}, bound {bound:.2e}")
    if err > bound:
        problems.append(f"f={f:.0e}: error {err:.2e} exceeds the stated bound {bound:.2e}")
    if bound > 2e-3:
        problems.append(f"f={f:.0e}: bound {bound:.2e} is not well below the 2 % criterion (need <= 2e-3)")
assert not problems, "; ".join(problems)
print("B3's stated model error bounds its exact mutual-inductance error in both limits")
