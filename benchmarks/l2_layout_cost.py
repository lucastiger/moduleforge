"""Measured cost and lateral-refinement convergence of the layout L2 (``moduleforge.solvers.l2_layout``) at E002 scale (T0075).

Each solve (generated layout -> ``loop_inductance`` at 20 MHz) runs in a fresh subprocess; the child reports its own
user+sys CPU time over all threads (``getrusage(RUSAGE_SELF)``) and peak RSS.  Output: ``DIR/cost.json`` =
``{'k_star', 'cells_mm', 'layer_thickness_um', 'solves': [...], 'steps': [...], 'convergence': [...], 'sensitivity': [...]}``.

Ladder (founder re-scope I0039): generated layouts are on a 0.5 mm design grid and the cells 0.5 / 0.25 / 0.125 mm
(refinement 0 / 1 / 2) divide it, so every level meshes the same copper; the thickness layers and the wire filaments are
held at the counts that resolve the 20 MHz skin depth at every level (checked here: top-Cu internal impedance within 2 %),
so a refinement step is purely lateral.  k_star = ``l2_layout.K_STAR`` = 1 (0.25 mm) is E002's level.

Gates (unchanged from the founder amendment of 2026-10-06): cost <= 2400 CPU-s and <= 12 GB per solve at k_star;
|L(k_star+1) - L(k_star)| / L(k_star+1) < 1 % with the k_star-1 -> k_star change larger and of the same sign (|change| <
1e-4 counts as converged); sensitivity of L at k_star to +2 thickness layers per slab and to the next finer wire filaments
< 0.2 % each.  R's convergence is reported, not gated.

Modes (dev seeds only: 7, 3, 11, 5; never a sealed seed):
* ``--quick`` (this 16 GB laptop; the DoD run; founder amendment for attempt 5): seed 7 / 2 dies (interleaved) at k_star-1
  and k_star, seed 7 / 6 dies at k_star (three solves).  ``--sensitivity`` adds the two sensitivity solves (seed 7 / 2 dies
  at k_star); the founder moved them, and the second-family layout, to ``--vm``.
* default (full, laptop): ``FULL_CASES`` at k_star-1 and k_star, plus the sensitivity solves.
* ``--vm`` (burst VM; k_star+1 needs ~35 GB): ``VM_CASES`` (3 families, 2 and 6 dies) at k_star-1, k_star, k_star+1 and the
  two sensitivity solves (always), ``--jobs`` at a time, each child limited to ``--threads`` BLAS / OpenMP threads
  (default: cores / jobs).  Everything (solves, steps, convergence gate, sensitivity) goes to cost.json.

Run: ``uv run python benchmarks/l2_layout_cost.py --out DIR [--quick [--sensitivity] | --vm --jobs N]``.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

F_HZ = 2.0e7
CPU_GATE_S, RSS_GATE_GB = 2400.0, 12.0
L_GATE, SENS_GATE, CONVERGED_BELOW = 0.01, 0.002, 1e-4
ZS_TOL = 0.02  # the held thickness layers must give the top-Cu internal impedance at F_HZ within this (every level)
DEV_SEEDS = (7, 3, 11, 5)  # unsealed development seeds
# (seed, dies per switch): seed 7 interleaved, 3 / 5 side_by_side, 11 u_shaped (generate_layouts(1, seed, dies_per_switch))
QUICK_CASES = ((7, 2),)  # at k_star - 1 and k_star; plus QUICK_K_STAR_ONLY at k_star (second family: VM_CASES)
QUICK_K_STAR_ONLY = ((7, 6),)
FULL_CASES = ((7, 2), (11, 2), (7, 6), (3, 3), (11, 4), (5, 5), (3, 6))
VM_CASES = ((7, 2), (11, 2), (3, 6))  # interleaved / u_shaped / side_by_side, 2 and 6 dies
SENS_CASE = (7, 2)
SENS_LAYERS_PLUS = 2  # sensitivity: every slab +2 thickness layers
WIRE_EDGES_FINER = (0, .3, .5, .7, .85, .95, 1)  # sensitivity: the next finer wire annuli (T0075 attempt 3's level 4)
K_STAR_CRITERION = ("founder re-scope I0039: k_star = l2_layout.K_STAR = 1, the 0.25 mm lateral level, on the nested ladder "
                    "0.5 / 0.25 / 0.125 mm that divides the generator's 0.5 mm design grid; the thickness layers (top 10, "
                    "backside 6, baseplate 6) and the wire filaments are held at every level at the counts that resolve the "
                    "20 MHz skin depth (top-Cu 1-D internal impedance within 2 % of the exact slab, "
                    "l2_layout.layered_surface_impedance vs slab_surface_impedance; T0075 attempt 3's level 3)")


def skin_resolution(refinement: int) -> dict:
    """Top-Cu / backside-Cu thickness layers (um, bottom-up) of ``refinement`` as l2_layout builds them (graded to F_MESH)
    and the error of their 1-D internal impedance at F_HZ against the exact slab (field on one face, worst face, [RWV] 5.6)."""
    from moduleforge.geometry import default_dbc_stack
    from moduleforge.solvers import l2_core as core, l2_layout as L
    st = default_dbc_stack()
    out = {}
    for name, counts in (("top_cu", L.LAYERS_TOP), ("backside_cu", L.LAYERS_BACK)):
        t, sg = st.layer(name).thickness, st.layer(name).sigma
        lay = L.graded_layers(0.0, t, counts[refinement], max(L.F_MESH, F_HZ), sg, True)
        th = [b - a for a, b in lay]
        ze = L.slab_surface_impedance(t, F_HZ, sg)
        errs = [L.layered_surface_impedance(order, F_HZ, sg) / ze - 1.0 for order in (th[::-1], th)]  # top face, bottom face
        worst = max(errs, key=abs)
        out[name] = dict(n_layers=len(th), layers_um=[x * 1e6 for x in th], zs_rel_err=abs(worst), R_s_rel_err=worst.real,
                         X_s_rel_err=worst.imag)
    delta = core.skin(F_HZ, st.layer("top_cu").sigma)
    return dict(cell_mm=L.CELL[refinement] * 1e3, delta_um=delta * 1e6, top_cu=out["top_cu"], backside_cu=out["backside_cu"],
                layers=[L.LAYERS_TOP[refinement], L.LAYERS_BACK[refinement], L.LAYERS_BASE[refinement]],
                wire_edges=list(L.WIRE_EDGES[refinement]), resolved=bool(out["top_cu"]["zs_rel_err"] <= ZS_TOL))


# ------------------------------------------------------------------------------------------------------------ child
def apply_variant(L, refinement: int, variant: str | None) -> None:
    """Sensitivity variants, patched into l2_layout's ladders in this child process only."""
    def put(seq, val):
        v = list(seq)
        v[refinement] = val
        return tuple(v)
    if variant is None:
        return
    if variant == "layers+2":
        L.LAYERS_TOP, L.LAYERS_BACK, L.LAYERS_BASE = (put(x, x[refinement] + SENS_LAYERS_PLUS)
                                                      for x in (L.LAYERS_TOP, L.LAYERS_BACK, L.LAYERS_BASE))
    elif variant == "wires_finer":
        L.WIRE_EDGES = put(L.WIRE_EDGES, WIRE_EDGES_FINER)
    else:
        raise ValueError(f"unknown variant {variant!r}")


def run_child(seed: int, dies: int, refinement: int, out: Path, variant: str | None = None) -> None:
    from moduleforge.generate.halfbridge import generate_layouts
    from moduleforge.solvers import l2_layout as L
    apply_variant(L, refinement, variant)
    t0 = time.perf_counter()
    lay = generate_layouts(1, seed=seed, dies_per_switch=dies)[0]
    r = L.loop_inductance(lay, [F_HZ], refinement=refinement)
    wall = time.perf_counter() - t0
    ru = resource.getrusage(resource.RUSAGE_SELF)
    rss = ru.ru_maxrss * (1.0 if sys.platform == "darwin" else 1024.0)  # bytes
    m = r.meta
    mp = m["mesh_params"]
    rec = dict(seed=seed, dies_per_switch=dies, family=lay.family, refinement=refinement, f_hz=F_HZ, L_H=float(r.L_H[0]),
               R_ohm=float(r.R_ohm[0]), wall_s=wall, cpu_s=ru.ru_utime + ru.ru_stime, cpu_user_s=ru.ru_utime,
               cpu_sys_s=ru.ru_stime, peak_rss_gb=rss / 1e9,
               n_unknowns=int(m["n_unknowns"]), gmres_iters=int(m["gmres_iters"][0]), gmres_flags=m["gmres_flags"],
               gmres_max_iters=int(m["gmres_max_iters"]), solver_tol=float(m["solver_tol"]),
               solver_tol_rel_L=float(m["solver_tol_rel_L"][0]), build_s=float(m["build_s"]),
               stage_s=dict(grid=float(mp["grid_build_s"]), wire_grid=float(mp["wire_grid_build_s"]),
                            wire_matrices=float(mp["wire_matrices_s"]), **m["solve_s"]),
               n_near_pairs=int(mp["n_near_pairs"]), n_filaments=int(m["n_filaments"]),
               n_grid_unknowns=int(mp["n_grid_unknowns"]), layers=mp["layers"], cell_m=float(mp["cell_x"]),
               cell_y_m=float(mp["cell_y"]), tol_parts=m["tol_parts"][0], n_cpu=os.cpu_count(),
               threads={k: os.environ.get(k) for k in THREAD_VARS}, area_rel_err_max=float(max(mp["area_rel_err"].values())),
               on_lattice=bool(mp["on_lattice"]), filaments_per_wire=int(mp["filaments_per_wire"]),
               wire_edges=list(L.WIRE_EDGES[refinement]))
    if variant:
        rec["variant"] = variant
    out.write_text(json.dumps(rec))


THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MF_L2_FFT_WORKERS")


def solve_in_subprocess(seed: int, dies: int, refinement: int, tmp: Path, variant: str | None = None,
                        threads: int | None = None, timeout_s: float | None = None) -> dict:
    """One solve in a fresh interpreter.  Returns the child's record, or {'did_not_fit': reason, ...} when the child fails
    (out of memory, crash) or exceeds ``timeout_s``."""
    tag = "" if not variant else "_" + variant.replace("+", "p")
    f = tmp / f"solve_s{seed}_d{dies}_r{refinement}{tag}.json"
    f.unlink(missing_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child", str(seed), str(dies), str(refinement), str(f)]
    if variant:
        cmd += ["--variant", variant]
    env = dict(os.environ)
    if threads:
        env.update({k: str(threads) for k in THREAD_VARS})
    print("solve", seed, dies, refinement, variant or "", flush=True)
    t0 = time.perf_counter()
    try:
        subprocess.run(cmd, check=True, timeout=timeout_s, env=env)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        rec = dict(seed=seed, dies_per_switch=dies, refinement=refinement, variant=variant,
                   did_not_fit=type(e).__name__ + ": " + str(e)[:200], wall_s=time.perf_counter() - t0)
        print("  -> did not fit:", rec["did_not_fit"], flush=True)
        return rec
    rec = json.loads(f.read_text())
    print("  ->", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items() if not isinstance(v, (dict, list))},
          flush=True)
    return rec


# ------------------------------------------------------------------------------------------------------------ analysis
def _by_level(solves: list[dict]) -> dict:
    return {(s["seed"], s["dies_per_switch"], s["refinement"]): s for s in solves}


def steps(solves: list[dict]) -> list[dict]:
    """Every measured lateral step r -> r + 1 of one layout: rel_change = (L(r+1) - L(r)) / L(r+1), and the same for R."""
    by = _by_level(solves)
    return [dict(seed=s, dies_per_switch=d, from_refinement=r, to_refinement=r + 1,
                 cells_mm=[by[(s, d, r)]["cell_m"] * 1e3, by[(s, d, r + 1)]["cell_m"] * 1e3],
                 rel_change=(by[(s, d, r + 1)]["L_H"] - by[(s, d, r)]["L_H"]) / by[(s, d, r + 1)]["L_H"],
                 R_rel_change=(by[(s, d, r + 1)]["R_ohm"] - by[(s, d, r)]["R_ohm"]) / by[(s, d, r + 1)]["R_ohm"])
            for (s, d, r) in sorted(by) if (s, d, r + 1) in by]


def convergence(solves: list[dict], k: int) -> list[dict]:
    """The gate at k_star for every layout with a k_star + 1 solve (rel_change = (L_k+1 - L_k) / L_k+1)."""
    by = _by_level(solves)
    out = []
    for (seed, dies, ref) in sorted(by):
        if ref != k or (seed, dies, k + 1) not in by:
            continue
        a, b = by[(seed, dies, k)], by[(seed, dies, k + 1)]
        rec = dict(seed=seed, dies_per_switch=dies, k_star=k, rel_change=(b["L_H"] - a["L_H"]) / b["L_H"],
                   R_rel_change=(b["R_ohm"] - a["R_ohm"]) / b["R_ohm"], prev_change=None, R_prev_change=None)
        if (seed, dies, k - 1) in by:
            p = by[(seed, dies, k - 1)]
            rec["prev_change"] = (a["L_H"] - p["L_H"]) / a["L_H"]
            rec["R_prev_change"] = (a["R_ohm"] - p["R_ohm"]) / a["R_ohm"]
        c, pc = rec["rel_change"], rec["prev_change"]
        rec["converged"] = bool(abs(c) < CONVERGED_BELOW or
                                (abs(c) < L_GATE and pc is not None and abs(c) < abs(pc) and c * pc > 0))
        out.append(rec)
    return out


def sensitivity(solves: list[dict], variants: list[dict]) -> list[dict]:
    by = _by_level(solves)
    out = []
    for v in variants:
        base = by.get((v["seed"], v["dies_per_switch"], v["refinement"]))
        if base is None:
            continue
        ch = (v["L_H"] - base["L_H"]) / base["L_H"]
        out.append(dict(seed=v["seed"], dies_per_switch=v["dies_per_switch"], refinement=v["refinement"],
                        variant=v["variant"], L_H=v["L_H"], base_L_H=base["L_H"], rel_change=ch,
                        R_rel_change=(v["R_ohm"] - base["R_ohm"]) / base["R_ohm"], layers=v["layers"],
                        wire_edges=v["wire_edges"], cpu_s=v["cpu_s"], peak_rss_gb=v["peak_rss_gb"],
                        solver_tol=v["solver_tol"], ok=bool(abs(ch) < SENS_GATE)))
    return out


def plan(mode: str, k: int, with_sens: bool) -> list[tuple]:
    if mode == "quick":
        jobs = [(s, d, r, None) for s, d in QUICK_CASES for r in (k - 1, k)] + [(s, d, k, None) for s, d in QUICK_K_STAR_ONLY]
    elif mode == "vm":
        jobs = [(s, d, r, None) for r in (k + 1, k, k - 1) for s, d in VM_CASES]  # every long k_star + 1 solve starts first
    else:
        jobs = [(s, d, r, None) for s, d in FULL_CASES for r in (k - 1, k)]
    if with_sens:
        jobs += [(*SENS_CASE, k, "layers+2"), (*SENS_CASE, k, "wires_finer")]
    assert all(s in DEV_SEEDS for s, *_ in jobs)
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="the laptop / DoD set (see the module docstring)")
    g.add_argument("--vm", action="store_true", help="burst VM: k_star-1, k_star, k_star+1 of VM_CASES and the sensitivity")
    ap.add_argument("--sensitivity", action="store_true", help="quick mode: add the two sensitivity solves at k_star")
    ap.add_argument("--jobs", type=int, default=1, help="solves run concurrently (each in its own process; mind the memory)")
    ap.add_argument("--threads", type=int, default=None,
                    help="BLAS / OpenMP / FFT threads per child (default: unset, except --vm: cores // jobs)")
    ap.add_argument("--timeout-s", type=float, default=None, help="a solve running longer than this is recorded as not fitting")
    ap.add_argument("--child", nargs=4, metavar=("SEED", "DIES", "REF", "FILE"))
    ap.add_argument("--variant", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.child:
        run_child(int(a.child[0]), int(a.child[1]), int(a.child[2]), Path(a.child[3]), a.variant)
        return 0
    if a.out is None:
        ap.error("--out is required")
    from moduleforge.solvers import l2_layout as L
    a.out.mkdir(parents=True, exist_ok=True)
    k = L.K_STAR
    if not 1 <= k < L.MAX_REFINEMENT:
        raise RuntimeError(f"k_star {k} needs a level below and above it (0..{L.MAX_REFINEMENT})")
    info = {r: skin_resolution(r) for r in range(L.MAX_REFINEMENT + 1)}
    if not all(v["resolved"] for v in info.values()):
        raise RuntimeError(f"thickness layers do not resolve the skin depth at every level: {info}")
    mode = "vm" if a.vm else "quick" if a.quick else "full"
    threads = a.threads if a.threads else (max(1, (os.cpu_count() or 1) // max(1, a.jobs)) if a.vm else None)
    jobs = plan(mode, k, with_sens=(a.sensitivity or mode != "quick"))
    print("mode", mode, "k_star", k, "cells_mm", [c * 1e3 for c in L.CELL], "jobs", len(jobs), "threads", threads, flush=True)
    solves, variants, not_fitted = [], [], []

    def dump():
        res = dict(k_star=k, mode=mode, f_hz=F_HZ, cells_mm=[c * 1e3 for c in L.CELL], skin_depth_um=info[k]["delta_um"],
                   k_star_criterion=K_STAR_CRITERION, design_grid_mm=0.5,
                   layer_thickness_um={str(r): v["top_cu"]["layers_um"] for r, v in info.items()},
                   skin_resolution={str(r): v for r, v in info.items()},
                   gates=dict(cpu_s=CPU_GATE_S, rss_gb=RSS_GATE_GB, l_rel_change=L_GATE, converged_below=CONVERGED_BELOW,
                              sensitivity=SENS_GATE),
                   threads_per_child=threads, jobs=a.jobs, solves=solves, not_fitted=not_fitted, steps=steps(solves),
                   convergence=convergence(solves, k), sensitivity=sensitivity(solves, variants),
                   sensitivity_solves=variants)
        (a.out / "cost.json").write_text(json.dumps(res, indent=1))
        return res

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = [ex.submit(solve_in_subprocess, seed, dies, ref, a.out, var, threads, a.timeout_s)
                for seed, dies, ref, var in jobs]
        for fu in as_completed(futs):
            rec = fu.result()
            (not_fitted if "did_not_fit" in rec else variants if rec.get("variant") else solves).append(rec)
            for lst in (solves, variants):
                lst.sort(key=lambda r: (r["seed"], r["dies_per_switch"], r["refinement"], r.get("variant") or ""))
            dump()
    res = dump()
    bad = [s for s in solves if s["refinement"] == k and (s["cpu_s"] > CPU_GATE_S or s["peak_rss_gb"] > RSS_GATE_GB)]
    print("cost gate at k_star:", "FAIL" if bad else "ok", flush=True)
    print("steps:", json.dumps([(s["seed"], s["dies_per_switch"], s["from_refinement"], round(s["rel_change"], 5))
                                for s in res["steps"]]))
    print("convergence:", json.dumps(res["convergence"]))
    print("sensitivity:", json.dumps([(s["variant"], s["rel_change"]) for s in res["sensitivity"]]))
    ok = (not bad and not not_fitted and all(c["converged"] for c in res["convergence"])
          and all(s["ok"] for s in res["sensitivity"]) and all(s["solver_tol"] < 1e-3 for s in solves + variants))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
