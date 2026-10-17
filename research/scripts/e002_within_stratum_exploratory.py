"""EXPLORATORY, post hoc (not pre-registered): within-stratum ranking fidelity of L1 against E002's reference.

Reviews T0106/T0107 of EV-O001-01 (2026-10-16) found that E002's pooled metrics are dominated by the
(family, dies-per-switch) strata: a predictor knowing only the stratum would pass A2/A3/A5. Derivative re-layout ranks
layouts within a fixed family and die count. This script measures that within-stratum agreement on the E002 run's own
per-layout rows (L1 at 20 MHz vs the Richardson-extrapolated L2_inf). It was written after the evaluation, on data
the evaluation has already seen, so it cannot change the registered verdict and is not confirmatory evidence; a
pre-registered experiment on fresh sealed seeds is needed for that.

    uv run python research/scripts/e002_within_stratum_exploratory.py [--run E002-20261016T054426-b69a]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261017  # bootstrap seed, fixed before the first run of this script


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="E002-20261016T054426-b69a")
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()
    rd = ROOT / "experiments" / "results" / "E002" / a.run
    rows = json.loads((rd / "e002_rows.json").read_text())
    rows = rows["rows"] if isinstance(rows, dict) and "rows" in rows else rows
    inf = {p["i"]: p["L2_inf"] for p in json.loads((rd / "e002_reference.json").read_text())["per_layout"]}
    L1 = np.array([r["L1_H"]["20000000.0"] for r in rows])
    L2 = np.array([inf[r["i"]] for r in rows])
    keys = [(r["family"], int(r["dies"])) for r in rows]
    strata = defaultdict(list)
    for j, k in enumerate(keys):
        strata[k].append(j)

    def demeaned_spearman(idx_by_stratum):
        a1, b1 = [], []
        for idx in idx_by_stratum:
            x, y = np.log(L1[idx]), np.log(L2[idx])
            a1.append(x - x.mean())
            b1.append(y - y.mean())
        return float(spearmanr(np.concatenate(a1), np.concatenate(b1))[0])

    within = demeaned_spearman(list(strata.values()))
    rng = np.random.default_rng(SEED)
    boot = [demeaned_spearman([rng.choice(idx, len(idx)) for idx in strata.values()]) for _ in range(a.n_boot)]
    per = {f"{f}:{d}": dict(n=len(idx), rho=float(spearmanr(L1[idx], L2[idx])[0]),
                             cv_L2=float(np.std(L2[idx]) / np.mean(L2[idx])))
           for (f, d), idx in sorted(strata.items())}
    stratum_only = np.empty_like(L2)
    for idx in strata.values():
        stratum_only[idx] = L1[idx].mean()
    w = np.array([v["n"] for v in per.values()])
    r = np.array([v["rho"] for v in per.values()])
    out = dict(
        run=a.run, exploratory=True, n=len(rows), strata=len(strata),
        pooled_spearman=float(spearmanr(L1, L2)[0]),
        within_stratum_spearman_demeaned_log=within,
        within_stratum_ci95=[float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        per_stratum=per, per_stratum_rho_weighted_mean=float((w * r).sum() / w.sum()), per_stratum_rho_min=float(r.min()),
        stratum_mean_only_pooled_spearman=float(spearmanr(stratum_only, L2)[0]),
        bootstrap=dict(seed=SEED, n=a.n_boot, scheme="resample layouts within each stratum"),
    )
    dest = ROOT / "research" / "notes" / "o001-e002-within-stratum-exploratory.json"
    dest.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "per_stratum"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
