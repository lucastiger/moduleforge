"""Independent validation of E001's refinement rule after T0060 (research/notes/o001-l2-reference.md sec. 4.4).

Compares the T0057 rule (git f8976fc) with the T0060 rule (working tree) on the registered path (realized h,
order_range = (order_min, order_max), steady_tol, noise floor 2 x solver_err_budget |L|). Seeds here (31, 32, ...) are
independent of the founder's DoD seed (20261003), of the runner's frozen self-check seed and of T0057's sweep (99).

Parts (each prints a table; run: uv run python research/scripts/e001_rule_t0060_validation.py [--quick]):
  1. DoD generator (estimator_adversarial.py's distribution) on 5 other seeds: safety and power per leading order.
  2. Random families with continuous parameters: e = A h^p + B h^(p+dp1) [+ C h^(p+dp2)], p ~ U[1, 2],
     dp ~ U[0.05, 3], every sign combination, nominal ratio q ~ U[1.25, 2] jittered per level by U[1, 1.1]
     (realized ratios in [1.25, 2.2]), 4-5 levels, random start; without and with uniform solver noise +/- 1e-4 |L|.
     Reports false convergences (true discretization error > conv_tol, estimate < conv_tol), per-value coverage
     (estimate + budget |L| >= |L_finest - L_exact| among declared-converged), worst true/estimate, power (fraction of
     sequences with true error < conv_tol / 10 that are declared converged) and which path accepted.
  3. Adversarial search (scipy differential evolution, 4 seeds per configuration) for the largest true/estimate
     among declared-converged sequences, and for false convergences: two terms with constant ratio, two terms with
     free per-level jitter, three terms with constant ratio, three terms with jitter.
  4. Integer-count schedules: smallest base count n0 for which round-half-up(n0 q^k) keeps every realized ratio in a
     band that composes with any other parameter under the contract's ratio checks.
"""
import importlib.util
import math
import subprocess
import sys
import tempfile

import numpy as np
from scipy.optimize import differential_evolution

sys.path.insert(0, "experiments/runners")
import e001_reference as NEW  # noqa: E402

T0057_COMMIT = "f8976fc"


def _load_old():
    src = subprocess.run(["git", "show", f"{T0057_COMMIT}:experiments/runners/e001_reference.py"],
                         capture_output=True, text=True, check=True).stdout
    f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    f.write(src)
    f.close()
    spec = importlib.util.spec_from_file_location("e001_t0057", f.name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD = _load_old()
CFG = NEW.DEFAULT_CFG
TOL = float(CFG["conv_tol"])
ORD = (float(CFG["order_min"]), float(CFG["order_max"]))
STEADY = float(CFG["steady_tol"])
BUDGET = float(CFG["solver_err_budget"])


def est_of(mod, v, h, nz):
    return float(mod.remaining_discretization_error(v, noise=2 * nz * abs(v[-1]), h=h / h[0], order_range=ORD,
                                                    steady_tol=STEADY))


def path_of(v, h, nz):
    """'A', 'B' or '-' for the T0060 rule (B = same-sign path decided the estimate)."""
    e = est_of(NEW, v, h, nz)
    if not math.isfinite(e):
        return "-"
    hh = h / h[0]
    d = np.diff(v)
    a = np.abs(d)
    noise = max(2 * nz * abs(v[-1]), 4 * np.finfo(float).eps * np.max(np.abs(v)))
    if np.all(a[-3:] <= noise):
        return "A"
    o = NEW._observed_orders(hh, a, noise)
    s = np.sign(d[a > noise])
    fall = all(lt[2] < er[1] for er, lt in zip(o[:-1], o[1:], strict=True))
    return "B" if s.size == a.size and s.min() == s.max() and fall and o[-1][1] >= ORD[0] * (1 - 1e-9) else "A"


# ------------------------------------------------------------------ part 1: DoD distribution, other seeds
def part1(n_seq):
    print("\n## 1. DoD generator (A h^p + B h^(p+1), q in {1.25, 1.5, 2}, 4-5 levels), other seeds, T0060 rule")
    print("seed | opposite-sign: false conv / true > tol | same-sign accurate declared converged: p=1 | p=1.5 | p=2")
    import random
    for seed in (1, 2, 3, 4, 5):
        rng = random.Random(seed)

        def sample(sign, rng=rng):
            p, q, n = rng.choice([1.0, 1.5, 2.0]), rng.choice([1.25, 1.5, 2.0]), rng.choice([4, 5])
            a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
            b = abs(rng.uniform(0.005, 0.4)) * (1.0 if a > 0 else -1.0) * sign
            h = np.array([q ** -k for k in range(n)])
            v = 1.0 + a * h**p + b * h ** (p + 1)
            return p, abs(v[-1] - 1.0), est_of(NEW, v, h, 0.0)

        fc = hid = 0
        for _ in range(n_seq):
            _, true, est = sample(-1.0)
            if true > TOL:
                hid += 1
                fc += est < TOL
        acc = {}
        while min((t for _, t in acc.values()), default=0) < 100 or len(acc) < 3:
            p, true, est = sample(+1.0)
            if true < TOL / 10:
                x, t = acc.get(p, (0, 0))
                acc[p] = (x + (est < TOL), t + 1)
        print(f"{seed} | {fc} / {hid} | " + " | ".join(f"{acc[p][0]}/{acc[p][1]}" for p in (1.0, 1.5, 2.0)))


# ------------------------------------------------------------------ part 2: random continuous families
def gen(rng, n_terms, signs):
    q = rng.uniform(1.25, 2.0)
    nlev = int(rng.choice([4, 5]))
    k0 = rng.uniform(0.0, 4.0)
    qs = q * np.exp(rng.uniform(0.0, math.log(1.1), nlev - 1))
    h = q ** -k0 / np.concatenate([[1.0], np.cumprod(qs)])
    p = rng.uniform(*ORD)
    a0 = 10 ** rng.uniform(-3.0, -0.5) * rng.choice([-1.0, 1.0])
    e = a0 * h**p
    dps = np.sort(rng.uniform(0.05, 3.0, n_terms - 1))
    for dp, sg in zip(dps, signs, strict=True):
        e = e + np.sign(a0) * sg * 10 ** rng.uniform(-3.0, 0.5) * h ** (p + dp)
    return h, 1.0 + e


def part2(n_seq):
    print("\n## 2. Continuous families (p ~ U[1,2], dp ~ U[0.05,3], q ~ U[1.25,2] x jitter <= 1.1, 4-5 levels)")
    print("family | noise | rule | false conv / declared | coverage | worst true/est | power (true < tol/10) | "
          "accepted by B")
    fams = {"2 terms, opposite": (2, [-1]), "2 terms, same": (2, [1]), "3 terms, random signs": (3, None),
            "4 terms, same": (4, [1, 1, 1])}
    rows = {}
    for fi, (name, (nt, signs)) in enumerate(fams.items()):
        for nz in (0.0, BUDGET):
            rng = np.random.default_rng(31 + fi)
            stats = {"old": [0, 0, 0, 1.0, 0, 0], "new": [0, 0, 0, 1.0, 0, 0]}
            via_b = 0
            for _ in range(n_seq):
                sg = signs if signs is not None else list(rng.choice([-1.0, 1.0], nt - 1))
                h, exact = gen(rng, nt, sg)
                v = exact + rng.uniform(-nz, nz, exact.size) * np.abs(exact)
                true = abs(exact[-1] - 1.0)
                tot = abs(v[-1] - 1.0)
                for key, mod in (("old", OLD), ("new", NEW)):
                    est = est_of(mod, v, h, nz)
                    st = stats[key]
                    if est < TOL:
                        st[1] += 1
                        st[0] += true > TOL
                        st[2] += est + nz * abs(v[-1]) >= tot
                        st[3] = max(st[3], tot / max(est + nz * abs(v[-1]), 1e-300))
                        if key == "new" and path_of(v, h, nz) == "B":
                            via_b += 1
                    if true < TOL / 10:
                        st[5] += 1
                        st[4] += est < TOL
            for key in ("old", "new"):
                fc, conv, cov, worst, pw, pn = stats[key]
                rows[(name, nz, key)] = stats[key]
                print(f"{name} | {nz:.0e} | {'T0057' if key == 'old' else 'T0060'} | {fc} / {conv} | "
                      f"{cov / max(conv, 1):.4f} | {worst:.2f} | {pw}/{pn} = {pw / max(pn, 1):.3f} | "
                      f"{via_b if key == 'new' else '-'}")
    return rows


# ------------------------------------------------------------------ part 3: adversarial search
def adversary(n_terms, jitter, nlev, seed, mod, maxiter):
    """Maximize true/estimate over declared-converged sequences (est < conv_tol). x = [p, q, k0, log|A|, sA,
    (dp_i, log|c_i|, s_i) per extra term, jitter_1..jitter_(nlev-1)]; signs are continuous in [-1, 1] -> sign()."""
    bounds = [ORD, (1.25, 2.0), (0.0, 4.0), (-3.0, -0.5), (-1, 1)]
    for _ in range(n_terms - 1):
        bounds += [(0.05, 3.0), (-3.0, 0.5), (-1, 1)]
    if jitter:
        bounds += [(0.0, math.log(1.1))] * (nlev - 1)

    def build(x):
        p, q, k0, la, sa = x[:5]
        qs = q * np.exp(np.array(x[5 + 3 * (n_terms - 1):]) if jitter else np.zeros(nlev - 1))
        h = q ** -k0 / np.concatenate([[1.0], np.cumprod(qs)])
        a0 = 10**la * (1.0 if sa >= 0 else -1.0)
        e = a0 * h**p
        for i in range(n_terms - 1):
            dp, lc, sc = x[5 + 3 * i:8 + 3 * i]
            e = e + 10**lc * (1.0 if sc >= 0 else -1.0) * h ** (p + dp)
        return h, 1.0 + e

    def obj(x):
        h, v = build(x)
        est = est_of(mod, v, h, 0.0)
        true = abs(v[-1] - 1.0)
        if not est < TOL:
            return 1.0  # not declared converged: no loss
        return -true / max(est, 1e-300) - (10.0 if true > TOL else 0.0)

    r = differential_evolution(obj, bounds, seed=seed, maxiter=maxiter, popsize=25, tol=1e-12, polish=False)
    h, v = build(r.x)
    est = est_of(mod, v, h, 0.0)
    true = abs(v[-1] - 1.0)
    path = path_of(v, h, 0.0) if mod is NEW else "A"
    return true, est, path, r.x


def part3(maxiter, seeds):
    print("\n## 3. Adversarial search (differential evolution; worst true/estimate among declared-converged)")
    print("configuration | levels | rule | worst true/est | at true, est | false convergence found | path")
    for n_terms, jitter in ((2, False), (2, True), (3, False), (3, True)):
        for nlev in (4, 5):
            for key, mod in (("T0057", OLD), ("T0060", NEW)):
                best = None
                fc_any = False
                for s in seeds:
                    true, est, path, x = adversary(n_terms, jitter, nlev, s, mod, maxiter)
                    if est < TOL:
                        fc_any |= true > TOL
                        if best is None or true / est > best[0]:
                            best = (true / est, true, est, path)
                lab = f"{n_terms} terms, {'jitter <= 1.1' if jitter else 'constant ratio'}"
                if best is None:
                    print(f"{lab} | {nlev} | {key} | none declared converged | - | - | -")
                else:
                    print(f"{lab} | {nlev} | {key} | {best[0]:.3f} | {best[1]:.2e}, {best[2]:.2e} | "
                          f"{'yes' if fc_any else 'no'} | {best[3]}")


# ------------------------------------------------------------------ part 4: integer counts
def schedule_ok(counts_list, cfg):
    q = np.concatenate([np.asarray(c[1:], float) / np.asarray(c[:-1], float) for c in counts_list])
    return q.min() >= cfg["refinement_ratio_min"] and q.max() / q.min() <= cfg["refinement_ratio_spread"] and \
        q.max() <= cfg.get("refinement_ratio_max", math.inf)


def part4():
    """Composable rule: if every parameter's realized ratios lie in [max(r_min, q / sqrt(spread)), q sqrt(spread)],
    any mix of such parameters (and exact real-valued sizes at q) passes the shared spread check."""
    lo_f, hi_f = 1 / math.sqrt(CFG["refinement_ratio_spread"]), math.sqrt(CFG["refinement_ratio_spread"])
    print("\n## 4. Integer counts n_k = floor(n0 q^k + 0.5), k = 0..4: smallest n0 such that every n0' >= n0 (to 400) "
          "keeps all realized ratios in [max(1.25, q/sqrt(1.1)), min(2.2, q sqrt(1.1))] (composable)")
    print("nominal q | smallest n0 | example | realized ratios")
    for q in (1.25, 1.3, 1.35, 1.4, 1.5, 1.6, 1.75, 2.0):
        lo, hi = max(CFG["refinement_ratio_min"], q * lo_f), min(CFG["refinement_ratio_max"], q * hi_f)
        found = None
        for n0 in range(1, 401):
            c = [math.floor(n0 * q**k + 0.5) for k in range(5)]
            r = [c[i + 1] / c[i] for i in range(4)]
            if min(r) >= lo and max(r) <= hi:
                found = n0 if found is None else found
            else:
                found = None
        if found is None:
            print(f"{q} | none <= 400 | - | -")
        else:
            c = [math.floor(found * q**k + 0.5) for k in range(5)]
            print(f"{q} | {found} | {c} | {[round(c[i + 1] / c[i], 3) for i in range(4)]}")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    if "--counts-only" not in sys.argv:
        part1(1000 if quick else 4000)
        part2(400 if quick else 3000)
        part3(maxiter=40 if quick else 200, seeds=(1, 2) if quick else (1, 2, 3, 4))
    part4()
