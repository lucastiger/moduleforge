"""E001 design DoD: the stated residual model error for B1 must bound its error against exact references.

B1 is a straight 10 mm Al round wire, r = 0.15 mm. Exact partial self-inductance, by averaging the exact
filament mutual inductance M(l, d) (Grover 1946; Ruehli 1972) over the current distribution:
  * DC (uniform current): over the distance distribution of two uniform points in a disk (disk line picking);
  * thin skin (10 GHz, delta/r ~ 5e-3): over chords of the surface circle, plus the surface-impedance internal
    inductance l * sqrt(mu0 / (2 sigma omega)) / (2 pi a).
Reviews T0029/T0030 of T0020 found the stated bound too small by ~3x (DC) and ~9x (HF).
"""
import math
import sys

from scipy import integrate

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

MU0 = 4e-7 * math.pi
cfg = dict(R.DEFAULT_CFG)
sig = {R.CU: float(cfg["sigma_cu"]), R.AL: float(cfg["sigma_al"])}
case = next(c for c in R.build_cases(cfg) if c["id"] == "B1")
(p0, p1), a = case["conductors"][0]["pts"], case["conductors"][0]["diameter"] / 2
length = math.dist(p0, p1)
s = sig[case["conductors"][0]["mat"]]


def M(d):
    return MU0 / (2 * math.pi) * (length * math.asinh(length / d) - math.hypot(length, d) + d)


def disk_pdf(d):
    u = d / (2 * a)
    return 4 * d / (math.pi * a * a) * (math.acos(u) - u * math.sqrt(1 - u * u))


L_dc = integrate.quad(lambda d: M(d) * disk_pdf(d), 0, 2 * a, limit=400, points=[1e-9 * a])[0]
f_hi = 1e10
L_hi = (integrate.quad(lambda th: M(2 * a * math.sin(th / 2)), 0, math.pi, limit=400)[0] / math.pi
        + length * math.sqrt(MU0 / (2 * s * 2 * math.pi * f_hi)) / (2 * math.pi * a))
problems = []
for f, ref in ((100.0, L_dc), (f_hi, L_hi)):
    ana = R.analytic_values(case, [f], sig)[("L11", f)]
    err, bound = abs(ana - ref) / ref, R.residual_model_error(case, f, sig)
    print(f"B1 f={f:.0e} Hz: runner {ana * 1e9:.5f} nH, exact {ref * 1e9:.5f} nH, error {err:.2e}, bound {bound:.2e}")
    if err > bound:
        problems.append(f"f={f:.0e}: error {err:.2e} exceeds the stated bound {bound:.2e}")
    if bound > 2e-3:
        problems.append(f"f={f:.0e}: bound {bound:.2e} is not well below the 2 % criterion (need <= 2e-3)")
assert not problems, "; ".join(problems)
print("B1's stated model error bounds its exact error in both limits")
