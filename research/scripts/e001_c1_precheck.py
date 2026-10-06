"""Readiness pre-check for one E001 case (default C1). Not evidence.

Runs the frozen runner's own refinement loop (`l2_converged_solve`) on the case at its registered frequencies with
the registered config (experiments/specs/E001.yaml), exactly as `l2_phase` does in full mode, and records per level
the compared L, the rule's remaining-error estimate, the error against the closed form, solver_tol, time and memory.
Founder-approved 2026-10-06 (I0036): C1 had been solved under the frozen rule at 20 MHz only, never at 5 and 80 MHz
on the shared mesh. The check changes nothing in the spec or the rule; a failure here means an implementation fix
before the registered run, never a different criterion.

    uv run python research/scripts/e001_c1_precheck.py --out research/e001_precheck [--case C1]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_runner():
    s = importlib.util.spec_from_file_location("e001r", ROOT / "experiments" / "runners" / "e001_reference.py")
    e = importlib.util.module_from_spec(s)
    sys.modules["e001r"] = e
    s.loader.exec_module(e)
    return e


def peak_rss_gb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**30 if sys.platform == "darwin" else r / 2**20  # bytes on macOS, KiB on Linux


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="research/e001_precheck")
    ap.add_argument("--case", default="C1")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)

    e = load_runner()
    from moduleforge.solvers import l2

    spec = yaml.safe_load((ROOT / "experiments" / "specs" / "E001.yaml").read_text())
    cfg = e.checked_config(spec.get("config") or {})
    sig = {e.CU: float(cfg["sigma_cu"]), e.AL: float(cfg["sigma_al"])}
    case = e.build_cases(cfg, ids=[a.case])[0]
    freqs = sorted(set(case["cmp_freqs"]) | set(case["info_freqs"]))
    analytic = e.analytic_values(case, case["cmp_freqs"], sig)

    levels = []
    solve = e.l2_solve

    def recording_solve(l2_, case_, freqs_, k, sig_):  # the runner's own solve, timed and recorded per level
        t0 = time.time()
        z, meta = solve(l2_, case_, freqs_, k, sig_)
        row = {"level": k, "wall_s": time.time() - t0, "peak_rss_gb_process": peak_rss_gb(), "L_H": {}}
        for lab, i, j in case_["compare"]:
            for f in case_["cmp_freqs"]:
                v = float(np.imag(z[freqs_.index(f), i, j]) / (2 * math.pi * f))
                ref = analytic[(lab, f)]
                row["L_H"][f"{lab}@{f:g}"] = {"L": v, "analytic": ref, "rel_err": abs(v - ref) / abs(ref)}
        row["meta"] = {k_: meta.get(k_) for k_ in ("solver_tol", "n_filaments", "mesh_params", "gmres_info",
                                                     "gmres_converged", "peak_rss_mb", "wall_s")}
        levels.append(row)
        (out / f"{a.case}_levels.json").write_text(json.dumps(levels, indent=1, default=str))
        print(f"{a.case} level {k}: {row['wall_s']:.0f} s, {row['peak_rss_gb_process']:.1f} GB, "
              + ", ".join(f"{key} err {d['rel_err']:.2e}" for key, d in row["L_H"].items()), flush=True)
        return z, meta

    e.l2_solve = recording_solve
    t0 = time.time()
    z, rem, k_stop, metas = e.l2_converged_solve(l2, case, freqs, sig, cfg)
    total = time.time() - t0
    summary = {
        "case": a.case, "freqs": freqs, "cmp_freqs": case["cmp_freqs"], "stopped_at_level": k_stop,
        "refinement_max": cfg["refinement_max"], "conv_tol": cfg["conv_tol"],
        "rule_rem_rel": {str(key): v for key, v in rem.items()},
        "converged": max(rem.values()) < cfg["conv_tol"] and len(metas) >= cfg["refinement_min_levels"],
        "tol_ratio": max(float(m["solver_tol"]) for m in metas) / e.solver_tol_required(case, sig, cfg),
        "ratio_violation": e.refinement_ratio_violation(metas, cfg, e.required_mesh_keys(case)),
        "mesh_violations": e.one_mesh_violations(metas, len(freqs)),
        "max_rel_err_at_stop": max(d["rel_err"] for d in levels[-1]["L_H"].values()),
        "total_s": total, "final_level_s": levels[-1]["wall_s"], "peak_rss_gb_process": peak_rss_gb(),
        "host": platform.node(), "platform": platform.platform(),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
    }
    (out / f"{a.case}_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
