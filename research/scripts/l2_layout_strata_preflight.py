"""Founder pre-flight (not evidence): the convergence gate on the two E002 check strata never solved at k_star + 1.

Reviews of T0076 (T0095) found the l2_converged margin thin on dev data (|d2| + tolerances 0.63-0.88 % against 1 %)
while interleaved:6 and u_shaped:6 had never been solved at k_star + 1. This runs dev seeds 7 (interleaved) and 11
(u_shaped) at 6 dies per switch at k_star - 1, k_star and k_star + 1 with benchmarks/l2_layout_cost.py's own child
solver and gate functions, on the burst VM. Dev seeds only; never a sealed seed.

    uv run python research/scripts/l2_layout_strata_preflight.py --out research/l2_layout_vm2 --jobs 4
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ((7, 6), (11, 6))  # interleaved:6, u_shaped:6 (dev seeds)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("research/l2_layout_vm2"))
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("l2cost", ROOT / "benchmarks" / "l2_layout_cost.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    from moduleforge.generate.halfbridge import generate_layouts
    from moduleforge.solvers import l2_layout as L
    k = L.K_STAR
    assert all(s in b.DEV_SEEDS for s, _ in CASES)
    families = {f"{s}/{d}": generate_layouts(1, seed=s, dies_per_switch=d)[0].family for s, d in CASES}
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    threads = max(1, (os.cpu_count() or 1) // max(1, a.jobs))
    jobs = [(s, d, r) for r in (k + 1, k, k - 1) for s, d in CASES]  # the long k_star + 1 solves start first
    print("k_star", k, "families", families, "jobs", jobs, "threads", threads, flush=True)
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        solves = list(ex.map(lambda j: b.solve_in_subprocess(*j, out, None, threads), jobs))
    ok = [x for x in solves if "L_H" in x]
    res = dict(k_star=k, families=families, threads_per_child=threads, jobs=a.jobs, solves=solves,
               not_fitted=[x for x in solves if "L_H" not in x], steps=b.steps(ok), convergence=b.convergence(ok, k),
               gate=dict(l_rel_change=b.L_GATE, converged_below=b.CONVERGED_BELOW))
    (out / "cost.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"families": families, "convergence": res["convergence"], "not_fitted": res["not_fitted"]},
                     indent=1), flush=True)
    return 0 if res["convergence"] and all(c.get("converged") for c in res["convergence"]) else 1


if __name__ == "__main__":
    sys.exit(main())
