"""E002 power analysis (T0076): decidability of A2/K1 (Spearman CI), A3, A4/K2 (MAPE CI) and A5/K3 (top-decile recall)
versus the sample size n, by simulation on the generator's own population structure.  Planning only, not evidence.

Population: POOL dev-seed layouts (unsealed seed POOL_SEED, never a sealed seed) from generate_layouts; their L1 values at
20 MHz (default mesh) stand in for the *structure* of the true L2 population (family clustering, die-count trend, CV).
Error model (log scale): log L1_i = log T_i + mu + a_fam(i) + c (dies_i - 4) + sigma eps_i,  eps ~ N(0, 1);
the reference read at k_star is L2_i = T_i (1 + beta_i), beta_i = b_fam(i) + U(-0.25, 0.25) %, b_fam = 1.3 / 1.9 / 1.8 %
(the founder's VM bias estimates).  a_fam = (+2, -2, 0) %, c = +0.3 % per die (an F3-like die-count bias of L1).
Sampling: stratified, n / 15 layouts per (family, dies) stratum, as generate_layouts does for n a multiple of 15.
Statistics exactly as the E002 runner: Spearman with average ranks, paired percentile bootstrap (n_boot 2000 in the runner,
N_BOOT here), MAPE relative to L2, top_decile_recall = mfos.stats.topk_recall(k_frac 0.1, within 0.2, lower is better).
Run: uv run python research/scripts/e002_power.py  ->  research/e002_design/power.json
"""
import json
import os
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
from scipy.stats import rankdata  # noqa: E402

from mfos.stats import topk_recall  # noqa: E402
from moduleforge.generate.halfbridge import DIE_COUNTS, FAMILIES, generate_layouts  # noqa: E402
from moduleforge.physics.peec import loop_inductance  # noqa: E402

POOL, POOL_SEED, SIM_SEED = 1500, 990_001, 4242
N_GRID = (30, 45, 60, 90, 120)
SIGMAS = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.13, 0.17)
MUS = (0.0, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25)
REPS, N_BOOT = 400, 1000
A_FAM = {"side_by_side": 0.02, "interleaved": -0.02, "u_shaped": 0.0}
B_FAM = {"side_by_side": 0.018, "interleaved": 0.013, "u_shaped": 0.019}
C_DIE = 0.003
OUT = Path("research/e002_design/power.json")


def pool():
    cache = OUT.with_name("pool_l1.json")
    if cache.exists():
        d = json.loads(cache.read_text())
        return np.array(d["L"]), np.array(d["fam"]), np.array(d["dies"])
    lays = generate_layouts(POOL, seed=POOL_SEED)
    L = np.array([loop_inductance(x, [2.0e7]).L_H[0] for x in lays])
    fam = np.array([x.family for x in lays])
    dies = np.array([x.dies_per_switch for x in lays])
    cache.write_text(json.dumps({"seed": POOL_SEED, "L": L.tolist(), "fam": fam.tolist(), "dies": dies.tolist()}))
    return L, fam, dies


def boot_spearman(x, y, idx):
    rx, ry = rankdata(x[idx], axis=1), rankdata(y[idx], axis=1)
    rx -= rx.mean(1, keepdims=True)
    ry -= ry.mean(1, keepdims=True)
    den = np.sqrt((rx**2).sum(1) * (ry**2).sum(1))
    return np.where(den > 0, (rx * ry).sum(1) / np.where(den > 0, den, 1), 0.0)


def spearman(x, y):
    return float(boot_spearman(x, y, np.arange(len(x))[None, :])[0])


def main():
    t0 = time.time()
    T, fam, dies = pool()
    rng = np.random.default_rng(SIM_SEED)
    strata = {(f, k): np.nonzero((fam == f) & (dies == k))[0] for f in FAMILIES for k in DIE_COUNTS}
    afam = np.array([A_FAM[f] for f in fam])
    bfam = np.array([B_FAM[f] for f in fam])
    out = {"pool": {"n": POOL, "seed": POOL_SEED, "cv": float(T.std(ddof=1) / T.mean())}, "rows": []}
    # population rho (large-sample truth) for each sigma, at mu = 0
    for sigma in SIGMAS:
        for mu in (MUS if sigma == 0.06 else (0.0,)):
            pr = []
            for _ in range(5):
                L1 = T * np.exp(mu + afam + C_DIE * (dies - 4) + sigma * rng.standard_normal(T.size))
                L2 = T * (1 + bfam + rng.uniform(-0.0025, 0.0025, T.size))
                pr.append((spearman(L1, L2), float(np.mean(np.abs(L1 - L2) / L2)), topk_recall(L1, L2)))
            rho_pop, mape_pop, rec_pop = (float(np.mean(v)) for v in zip(*pr, strict=True))
            for n in N_GRID:
                r = dict(sigma=sigma, mu=mu, n=n, rho_pop=rho_pop, mape_pop=mape_pop, recall_pop=rec_pop)
                a2 = a3 = k1 = a4 = k2 = a5 = k3 = 0
                rhos, los, his, mlo, mhi, recs = [], [], [], [], [], []
                for _ in range(REPS):
                    idx = np.concatenate([rng.choice(v, n // 15, replace=False) for v in strata.values()])
                    t, f_a, f_b, d = T[idx], afam[idx], bfam[idx], dies[idx]
                    L1 = t * np.exp(mu + f_a + C_DIE * (d - 4) + sigma * rng.standard_normal(n))
                    L2 = t * (1 + f_b + rng.uniform(-0.0025, 0.0025, n))
                    bi = rng.integers(0, n, (N_BOOT, n))
                    rho = spearman(L1, L2)
                    lo, hi = np.quantile(boot_spearman(L1, L2, bi), [0.025, 0.975])
                    ape = np.abs(L1 - L2) / L2
                    m_lo, m_hi = np.quantile(ape[bi].mean(1), [0.025, 0.975])
                    rec = topk_recall(L1, L2)
                    a2 += lo >= 0.85
                    a3 += rho >= 0.90
                    k1 += hi < 0.80
                    a4 += m_hi <= 0.12
                    k2 += m_lo > 0.20
                    a5 += rec >= 0.70
                    k3 += rec < 0.50
                    rhos.append(rho), los.append(lo), his.append(hi), mlo.append(m_lo), mhi.append(m_hi), recs.append(rec)
                r.update({k: v / REPS for k, v in dict(p_A2=a2, p_A3=a3, p_K1=k1, p_A4=a4, p_K2=k2, p_A5=a5,
                                                         p_K3=k3).items()})
                r.update(rho_med=float(np.median(rhos)), ci_lo_med=float(np.median(los)), ci_hi_med=float(np.median(his)),
                         ci_width_med=float(np.median(np.array(his) - np.array(los))), mape_hi_med=float(np.median(mhi)),
                         mape_lo_med=float(np.median(mlo)), recall_mean=float(np.mean(recs)))
                out["rows"].append(r)
                print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    out["settings"] = dict(reps=REPS, n_boot=N_BOOT, a_fam=A_FAM, b_fam=B_FAM, c_die=C_DIE, sim_seed=SIM_SEED,
                           seconds=time.time() - t0)
    OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
