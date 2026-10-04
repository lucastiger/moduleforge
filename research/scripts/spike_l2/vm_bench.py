"""T0067 L2 feasibility benchmark (Q1-Q4). Runs the modal-wire / FFT-plane prototype (l2proto.py) on the
frozen E001 cases level by level, applies the frozen refinement rule (runner functions, unchanged), and
records error vs closed form, unknowns, wall time and peak memory per (case, level). Each (case, level)
runs in a fresh process so its peak RSS is its own.

  uv run python research/scripts/spike_l2/vm_bench.py --out research/spike_l2_results          # full
  uv run python research/scripts/spike_l2/vm_bench.py --out /tmp/spike --quick                  # levels 1-2
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import platform
import resource
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PLAN_FULL = {"B1": [1, 2, 3, 4, 5], "B2": [1, 2, 3, 4], "C0": [1, 2, 3, 4], "C1": [1, 2, 3, 4]}
PLAN_QUICK = {"B1": [1, 2, 3, 4], "B2": [1, 2], "C0": [1, 2], "C1": [1]}


def _job(cid: str, k: int, out: str) -> dict:
    import numpy as np

    import l2proto as P
    E = P.E
    cfg = E.checked_config({})
    sig = {E.CU: cfg["sigma_cu"], E.AL: cfg["sigma_al"]}
    c = E.build_cases(cfg, [cid])[0]
    freqs = sorted(set(c["cmp_freqs"]) | set(c["info_freqs"]))
    t0 = time.perf_counter()
    z, meta = P.solve_case(c, freqs, k, sig)
    wall = time.perf_counter() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_gb = rss / 2**30 if platform.system() == "Darwin" else rss / 2**20
    L = (z.imag / (2 * math.pi * np.asarray(freqs))).tolist()
    rec = dict(case=cid, level=k, freqs=freqs, L=L, wall_s=wall, peak_rss_gb=rss_gb, cpu=os.cpu_count(),
               **{kk: v for kk, v in meta.items() if kk not in ("infos", "wall_s")},
               infos=[{kk: (float(v) if isinstance(v, (int, float)) else v) for kk, v in i.items()}
                      for i in meta["infos"]])
    Path(out, f"{cid}_k{k}.json").write_text(json.dumps(rec, indent=1, default=float))
    return rec


def verdict(cid: str, recs: list[dict]) -> dict:
    """Frozen E001 rule on the measured sequence (runner's own functions and config)."""
    import l2proto as P
    E = P.E
    cfg = E.checked_config({})
    sig = {E.CU: cfg["sigma_cu"], E.AL: cfg["sigma_al"]}
    c = E.build_cases(cfg, [cid])[0]
    ana = E.analytic_values(c, c["cmp_freqs"], sig)
    amp = cfg["solver_err_budget"] / E.solver_tol_required(c, sig, cfg)
    metas = [dict(mesh_params=r["mesh_params"], solver_tol=r["solver_tol"]) for r in recs]
    hseq = E.mesh_sequence(metas, E.required_mesh_keys(c))
    ratio_v = E.refinement_ratio_violation(metas, cfg, E.required_mesh_keys(c)) if len(recs) > 1 else None
    out = {"ratio_violation": ratio_v, "rows": []}
    noise_rel = 2 * min(cfg["solver_err_budget"], max(r["solver_tol"] for r in recs) * amp)
    stop = None
    for n in range(cfg["refinement_min_levels"], len(recs) + 1):
        rem = []
        for f in c["cmp_freqs"]:
            seq = [r["L"][r["freqs"].index(f)] for r in recs[:n]]
            est = E.remaining_discretization_error(seq, noise=noise_rel * abs(seq[-1]), h=hseq[:n],
                                                   order_range=(cfg["order_min"], cfg["order_max"]),
                                                   steady_tol=cfg["steady_tol"])
            rem.append(est / abs(seq[-1]))
        if max(rem) < cfg["conv_tol"] and stop is None:
            stop = n
    for f in c["cmp_freqs"]:
        seq = [r["L"][r["freqs"].index(f)] for r in recs]
        n_use = stop or len(recs)
        est = E.remaining_discretization_error(seq[:n_use], noise=noise_rel * abs(seq[n_use - 1]), h=hseq[:n_use],
                                               order_range=(cfg["order_min"], cfg["order_max"]),
                                               steady_tol=cfg["steady_tol"]) if n_use >= 4 else math.inf
        d = [b - a for a, b in zip(seq[:-1], seq[1:], strict=True)]
        out["rows"].append(dict(f=f, L=seq, err_vs_closed_form=[x / ana[("L11", f)] - 1 for x in seq],
                                changes_rel=[x / seq[-1] for x in d], rule_est_rel=est / abs(seq[n_use - 1]),
                                level_used=recs[n_use - 1]["level"]))
    out.update(converged_at=(recs[stop - 1]["level"] if stop else None), noise_rel=noise_rel, amp=amp,
               max_err_at_stop=max(abs(r["err_vs_closed_form"][(stop or len(recs)) - 1]) for r in out["rows"]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="research/spike_l2_results", help="output directory (JSON per job + summary)")
    ap.add_argument("--quick", action="store_true", help="small levels only (minutes on a laptop)")
    ap.add_argument("--cases", default=None, help="comma list, default B1,B2,C0,C1")
    ap.add_argument("--jobs", type=int, default=1, help="parallel (case, level) processes (BLAS threads share cores)")
    a = ap.parse_args(argv)
    plan = dict(PLAN_QUICK if a.quick else PLAN_FULL)
    if a.cases:
        plan = {c: plan.get(c, PLAN_FULL[c]) for c in a.cases.split(",")}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(c, k) for c, ks in plan.items() for k in ks]
    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    recs: dict[str, list] = {c: [] for c in plan}
    with ctx.Pool(a.jobs, maxtasksperchild=1) as pool:
        res = [pool.apply_async(_job, (c, k, str(out))) for c, k in jobs]
        for (c, k), r in zip(jobs, res, strict=True):
            try:
                rec = r.get()
                recs[c].append(rec)
                print(f"{c} k={k} n={rec['n_filaments']} wall={rec['wall_s']:.1f}s rss={rec['peak_rss_gb']:.2f}GB "
                      f"tol={rec['solver_tol']:.1e} {rec['infos'][0].get('method')} it={rec['infos'][0].get('iters')}",
                      flush=True)
            except Exception as exc:  # record and continue (a level that does not fit is a result)
                print(f"{c} k={k} FAILED: {exc!r}", flush=True)
    summary = {"host": platform.platform(), "cpu": os.cpu_count(), "total_s": time.perf_counter() - t0, "cases": {}}
    for c, rs in recs.items():
        rs.sort(key=lambda r: r["level"])
        summary["cases"][c] = dict(levels=[dict(level=r["level"], n=r["n_filaments"], wall_s=r["wall_s"],
                                                rss_gb=r["peak_rss_gb"], solver_tol=r["solver_tol"],
                                                timings=r["timings"]) for r in rs],
                                   verdict=verdict(c, rs) if len(rs) >= 2 else None)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print(json.dumps({c: v["verdict"] and {k: v["verdict"][k] for k in ("converged_at", "max_err_at_stop")}
                      for c, v in summary["cases"].items()}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
