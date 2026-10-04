"""E001 refinement rule at solver_err_budget = 1e-5 (T0063; reviews T0061/T0062 of T0060). Rule unchanged.

Measures, on the registered path (realized h, order_range = (order_min, order_max), steady_tol), with seeds of its own
(63, 64, ...; independent of the DoD seeds 20261003/20261004, the runner's self-check seed 20261004 and the sweep seed 99,
except part 4, which re-runs the seed-99 sweep generator on purpose):
  1. Power and safety on the founder DoD distribution (estimator_adversarial.py) with worst-case compliant noise
     (+-budget per value, floor 2 x budget) at budgets 1e-4 and 1e-5, on 3 further seeds.
  2. Power on the runner self-check's generator (_synthetic_sequence: random start, jitter <= 1.1, A down to 1e-4) as a
     function of the floor 2 x solver_tol x amplification (the runner uses the *reported* solver_tol, capped at the
     budget): values exact ("floor") or perturbed by +-floor/2 ("noisy"); power split by true remaining error.
  3. Review T0061 (1): same-sign sequences with true error in [conv_tol/10, conv_tol): acceptance by the T0057 rule
     (git f8976fc) and by the current rule; sequences T0057 accepted that the current rule refuses; T0061's hand example.
  4. Review T0061 (2): leading order 0.5 (outside the assumption) on the seed-99 sweep generator, T0057 vs current rule,
     noise 0, +-1e-5, +-1e-4.
  5. Review T0062 (minor 2): worst true/(est + budget) of declared-converged two-term opposite-sign sequences with
     noise +-budget (noise-limited branch), budgets 1e-4 and 1e-5.
  6. Power on the founder DoD distribution as a function of the floor (as part 2, seed 69).
Run: uv run python research/scripts/e001_rule_t0063_budget.py [--quick] [--part N]
"""
import importlib.util
import math
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, "experiments/runners")
sys.path.insert(0, "research/scripts")
import e001_reference as NEW  # noqa: E402

CFG = NEW.DEFAULT_CFG
TOL = float(CFG["conv_tol"])
ORD = (float(CFG["order_min"]), float(CFG["order_max"]))
KW = dict(order_range=ORD, steady_tol=float(CFG["steady_tol"]))
QUICK = "--quick" in sys.argv


def _load_t0057():
    src = subprocess.run(["git", "show", "f8976fc:experiments/runners/e001_reference.py"], capture_output=True,
                         text=True, check=True).stdout
    f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    f.write(src)
    f.close()
    spec = importlib.util.spec_from_file_location("e001_t0057", f.name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD = _load_t0057()


def est(mod, v, h, floor_rel):
    return float(mod.remaining_discretization_error(v, noise=floor_rel * abs(v[-1]), h=h, **KW))


def cp_lower(k, n):
    return NEW._clopper_pearson_lower(k, n)


def part1():
    print("\n## 1. DoD distribution, worst-case noise +-budget, floor 2 x budget (power = declared converged among "
          "same-sign true < conv_tol/10)")
    print("budget | seed | false conv / hidden | power p=1 | p=1.5 | p=2")
    for budget in (1e-4, 1e-5):
        for seed in (63, 64, 65):
            rng = np.random.default_rng(seed)
            fc = hid = 0
            pw = {1.0: [0, 0], 1.5: [0, 0], 2.0: [0, 0]}
            for i in range(4000 if QUICK else 16000):
                sign = 1.0 if i % 2 == 0 else -1.0
                p, q, n = float(rng.choice([1.0, 1.5, 2.0])), float(rng.choice([1.25, 1.5, 2.0])), int(rng.choice([4, 5]))
                a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
                b = abs(rng.uniform(0.005, 0.4)) * (1.0 if a > 0 else -1.0) * sign
                h = q ** -np.arange(n, dtype=float)
                exact = 1.0 + a * h**p + b * h ** (p + 1)
                v = exact * (1 + rng.uniform(-budget, budget, n))
                true = abs(exact[-1] - 1.0)
                e = est(NEW, v, h, 2 * budget)
                if sign > 0 and true < TOL / 10:
                    pw[p][0] += e < TOL
                    pw[p][1] += 1
                if sign < 0 and true > TOL:
                    hid += 1
                    fc += e < TOL
            cells = [f"{a_}/{t_} ({a_ / t_:.0%})" if t_ else "-" for a_, t_ in pw.values()]
            print(f"{budget:g} | {seed} | {fc} / {hid} | " + " | ".join(cells))


def selfcheck_seq(rng, p):
    dp = rng.uniform(0.25, ORD[1] + 1.0 - p)
    return NEW._synthetic_sequence(rng, p, [(dp, 1)], a_exp=(-4.0, -1.0), c_exp=(-3.0, 1.5), spread=1.1)


def part2():
    print("\n## 2. Runner self-check generator (same-sign, true < conv_tol/10): power vs floor = 2 x solver_tol x amp")
    n = 100 if QUICK else 400
    rng = np.random.default_rng(66)
    seqs = {}
    for p in (1.0, 1.5, 2.0):
        lst = []
        while len(lst) < n:
            hh, exact = selfcheck_seq(rng, p)
            if abs(exact[-1] - 1.0) < TOL / 10:
                lst.append((hh, exact, rng.uniform(-1.0, 1.0, exact.size)))
        seqs[p] = lst
    print("floor | mode | power p=1 | p=1.5 | p=2 | pooled power, true in [1e-4, 1e-3) | true in [1e-5, 1e-4) | "
          "true < 1e-5")
    for floor in (2e-4, 2e-5, 2e-6, 2e-7, 2e-8, 2e-9, 2e-10, 0.0):
        for mode in ("floor", "noisy"):
            if floor == 0.0 and mode == "noisy":
                continue
            per_p, bins = [], {0: [0, 0], 1: [0, 0], 2: [0, 0]}
            for p in (1.0, 1.5, 2.0):
                acc = 0
                for hh, exact, u in seqs[p]:
                    v = exact * (1 + u * floor / 2) if mode == "noisy" else exact
                    ok = est(NEW, v, hh, floor) < TOL
                    acc += ok
                    t = abs(exact[-1] - 1.0)
                    b = 0 if t >= 1e-4 else 1 if t >= 1e-5 else 2
                    bins[b][0] += ok
                    bins[b][1] += 1
                per_p.append(f"{acc / n:.2f}")
            cells = [f"{a_ / t_:.2f} ({t_})" if t_ else "-" for a_, t_ in bins.values()]
            print(f"{floor:g} | {mode} | " + " | ".join(per_p) + " | " + " | ".join(cells))


def part3():
    print("\n## 3. Same-sign sequences with conv_tol/10 <= true < conv_tol: T0057 vs current rule (review T0061 (1))")
    print("generator | floor | n | T0057 accepts | current accepts | T0057 yes, current no | T0057 no, current yes")
    rng = np.random.default_rng(67)
    for gen in ("DoD", "self-check"):
        for floor in (0.0, 2e-5):
            n = 0
            cnt = [0, 0, 0, 0]
            while n < (500 if QUICK else 3000):
                p = float(rng.choice([1.0, 1.5, 2.0]))
                if gen == "DoD":
                    q, k = float(rng.choice([1.25, 1.5, 2.0])), int(rng.choice([4, 5]))
                    a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
                    b = abs(rng.uniform(0.005, 0.4)) * np.sign(a)
                    hh = q ** -np.arange(k, dtype=float)
                    exact = 1.0 + a * hh**p + b * hh ** (p + 1)
                else:
                    hh, exact = selfcheck_seq(rng, p)
                t = abs(exact[-1] - 1.0)
                if not TOL / 10 <= t < TOL:
                    continue
                n += 1
                o, c = est(OLD, exact, hh, floor) < TOL, est(NEW, exact, hh, floor) < TOL
                cnt[0] += o
                cnt[1] += c
                cnt[2] += o and not c
                cnt[3] += c and not o
            print(f"{gen} | {floor:g} | {n} | " + " | ".join(f"{x} ({x / n:.1%})" for x in cnt))
    h = 2.0 ** -np.arange(1, 6, dtype=float)
    v = 1.0 + 1.076 * (h**1.5 + 0.3 * h**2.5)
    print(f"T0061 example A (h^1.5 + 0.3 h^2.5), A = 1.076, q = 2, h = 1/2 .. 1/32: true {abs(v[-1] - 1):.4f}, "
          f"T0057 est {est(OLD, v, h / h[0], 0.0):.4f}, current est {est(NEW, v, h / h[0], 0.0):.4f}")
    h4 = 2.0 ** -np.arange(4, dtype=float)
    for scale in (1.0, 0.04):
        v = 1.0 + scale * (h4**0.5 + h4**2.5)
        print(f"T0061 example {scale:g} (h^0.5 + h^2.5), q = 2, 4 levels: true {abs(v[-1] - 1):.4f}, T0057 est "
              f"{est(OLD, v, h4, 0.0):.4f}, current est {est(NEW, v, h4, 0.0):.4f}")


def part4():
    import e001_refinement_rule_sweep as S

    print("\n## 4. Leading order 0.5 (outside the assumption), seed-99 sweep generator (7 families x 2000), "
          "review T0061 (2)")
    print("rule | noise | false conv / declared converged | coverage | worst true/est")
    for name, mod in (("T0057", OLD), ("current", NEW)):
        S.R = mod
        for nz in (0.0, 1e-5, 1e-4):
            fc, conv, c, w, _ = S.sweep([0.5], True, nz, n=300 if QUICK else 2000)
            print(f"{name} | {nz:g} | {fc} / {conv} | {c:.4f} | {w:.2f}")
    S.R = NEW


def part5():
    print("\n## 5. Two-term opposite-sign sequences with noise +-budget (review T0062 minor 2): worst true/(est+budget)")
    print("budget | sequences | declared converged | under-covered (true > est + budget) | worst true/(est+budget)")
    for budget in (1e-4, 1e-5):
        rng = np.random.default_rng(68)
        nseq = 10000 if QUICK else 100000
        conv = bad = 0
        worst = 0.0
        for _ in range(nseq):
            p, dp = rng.uniform(1.0, 2.0), rng.uniform(0.05, 3.0)
            q, k = rng.uniform(1.25, 2.0), int(rng.choice([4, 5]))
            h = q ** -rng.uniform(0, 4) / np.concatenate([[1.0], np.cumprod(q * np.exp(rng.uniform(0, math.log(1.1),
                                                                                                     k - 1)))])
            a = 10 ** rng.uniform(-3, -0.5) * rng.choice([-1.0, 1.0])
            exact = 1.0 + a * h**p - np.sign(a) * 10 ** rng.uniform(-3, 0.5) * h ** (p + dp)
            v = exact * (1 + rng.uniform(-budget, budget, k))
            e = est(NEW, v, h / h[0], 2 * budget)
            if e < TOL:
                conv += 1
                tot = abs(v[-1] - 1.0)
                ratio = tot / (e + budget * abs(v[-1]))
                worst = max(worst, ratio)
                bad += ratio > 1
        print(f"{budget:g} | {nseq} | {conv} | {bad} | {worst:.3f}")


def part6():
    print("\n## 6. Founder DoD distribution (same-sign, true < conv_tol/10): power vs floor = 2 x solver_tol x amp")
    n = 100 if QUICK else 400
    rng = np.random.default_rng(69)
    seqs = {}
    for p in (1.0, 1.5, 2.0):
        lst = []
        while len(lst) < n:
            q, k = float(rng.choice([1.25, 1.5, 2.0])), int(rng.choice([4, 5]))
            a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
            b = rng.uniform(0.005, 0.4) * np.sign(a)
            hh = q ** -np.arange(k, dtype=float)
            exact = 1.0 + a * hh**p + b * hh ** (p + 1)
            if abs(exact[-1] - 1.0) < TOL / 10:
                lst.append((hh, exact, rng.uniform(-1.0, 1.0, exact.size)))
        seqs[p] = lst
    print("floor | mode | power p=1 | p=1.5 | p=2 (n per p = %d)" % n)
    for floor in (2e-4, 2e-5, 2e-6, 2e-7, 2e-8, 2e-9, 2e-10, 0.0):
        for mode in ("floor", "noisy"):
            if floor == 0.0 and mode == "noisy":
                continue
            per_p = []
            for p in (1.0, 1.5, 2.0):
                acc = sum(est(NEW, exact * (1 + u * floor / 2) if mode == "noisy" else exact, hh, floor) < TOL
                          for hh, exact, u in seqs[p])
                per_p.append(f"{acc / n:.3f}")
            print(f"{floor:g} | {mode} | " + " | ".join(per_p))


if __name__ == "__main__":
    print(f"rule: runner working tree (solver_err_budget in DEFAULT_CFG = {CFG['solver_err_budget']:g}); "
          f"T0057 rule from git f8976fc; quick = {QUICK}")
    parts = (part1, part2, part3, part4, part5, part6)
    only = int(sys.argv[sys.argv.index("--part") + 1]) if "--part" in sys.argv else None
    for i, part in enumerate(parts, 1):
        if only is None or i == only:
            part()
        sys.stdout.flush()
