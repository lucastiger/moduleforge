"""Reproduce the T0057 validation of E001's refinement rule (research/notes/o001-l2-reference.md sec. 4.4).

Calls the runner's remaining_discretization_error on synthetic refinement sequences e(h) = A h^p + B h^(p+dp) (+ a third
term), A, B of opposite or equal sign, constant ratio q in {1.25, 1.5, 2} jittered by up to 10 % per level, 4-5 levels,
random start, optional uniform solver noise +/- 1e-4 |L|. Seed 99 (independent of the runner's self-check seed and of
the founder's DoD seed). Prints, per mode: false convergences (true > conv_tol, estimate < conv_tol), per-value coverage
among declared-converged sequences, worst true/estimate, and the cost (true < conv_tol/3 but not declared converged).
Run: uv run python research/scripts/e001_refinement_rule_sweep.py
"""
import math
import sys

import numpy as np

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

TOL = R.DEFAULT_CFG["conv_tol"]
FAM = {"opp+0.5": ([0.5], -1), "opp+1": ([1.0], -1), "opp+2": ([2.0], -1), "same+0.5": ([0.5], 1),
       "same+1": ([1.0], 1), "three": ([1.0, 2.0], 0), "geometric": ([], 1)}


def sweep(orders, h_known, noise_rel, n=2000, seed=99):
    rng = np.random.default_rng(seed)
    fc = conv = cov = cost = cost_n = 0
    worst = 1.0
    for extra, sign in FAM.values():
        for _ in range(n):
            q, nlev, k0 = rng.choice([1.25, 1.5, 2.0]), int(rng.choice([4, 5])), rng.uniform(0, 4)
            qs = q * np.exp(rng.uniform(0, math.log(1.1), nlev - 1))
            h = q ** -k0 / np.concatenate([[1.0], np.cumprod(qs)])
            p = float(rng.choice(orders))
            a0 = 10 ** rng.uniform(-3, -0.5) * rng.choice([-1.0, 1.0])
            e = a0 * h**p
            for dp in extra:
                e = e + np.sign(a0) * (sign or rng.choice([-1.0, 1.0])) * 10 ** rng.uniform(-3, 0.5) * h ** (p + dp)
            exact = 1.0 + e
            v = exact + rng.uniform(-noise_rel, noise_rel, nlev) * np.abs(exact)
            kw = dict(h=h / h[0], order_range=(1.0, 2.0)) if h_known else {}
            est = R.remaining_discretization_error(v, noise=2 * noise_rel * abs(v[-1]), **kw)
            true = abs(exact[-1] - 1.0)
            if est < TOL:
                conv += 1
                tot = abs(v[-1] - 1.0)
                cov += est + noise_rel * abs(v[-1]) >= tot
                worst = max(worst, tot / max(est + noise_rel * abs(v[-1]), 1e-300))
                fc += true > TOL
            if true < TOL / 3:
                cost_n += 1
                cost += not est < TOL
    return fc, conv, cov / max(conv, 1), worst, cost / max(cost_n, 1)


if __name__ == "__main__":
    print("mode | leading orders | noise | false conv / declared converged | coverage | worst true/est | cost")
    for label, orders, hk in (("runner (h known, orders [1, 2])", [1.0, 1.5, 2.0], True),
                              ("runner, leading order 0.5 (outside the assumption)", [0.5], True),
                              ("values-only fallback", [1.0, 1.5, 2.0], False)):
        for nz in (0.0, 1e-4):
            fc, conv, c, w, cost = sweep(orders, hk, nz)
            print(f"{label} | {orders} | {nz:g} | {fc} / {conv} | {c:.4f} | {w:.2f} | {cost:.2f}")
