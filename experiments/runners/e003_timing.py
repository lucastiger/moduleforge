"""E003: single-core wall time of one L1 evaluation (Layout -> L_loop at 20 MHz, discretisation included) (O001 A6).

Design (pre-registered in experiments/drafts/E003.yaml; rationale in research/notes/o001-e002-e003-design.md):
* Threads: every BLAS / OpenMP thread variable is set to 1 and XLA_FLAGS to valid single-thread flags *before* numpy is
  imported (below); on Linux the process is also pinned to one CPU (os.sched_setaffinity).  macOS has no affinity API:
  the process cannot be pinned to a core, and the scheduler, not the runner, picks the P- or E-core type (an E-core only
  slows the loop, which is conservative for A6, a <= criterion); the core configuration is recorded.  single_thread_enforced verifies that this took effect: process CPU
  time / wall time over the timed loop <= cpu_wall_max (extra worker threads would raise it), one Python thread, and on
  Linux an affinity set of size 1.
* Sample: generate_layouts(n_layouts, sealed seed): n/15 layouts per (family, dies 2-6) stratum, each evaluated
  ``repeats`` times in a seeded shuffled order (n_evals = n_layouts x repeats).  Warm-up: the first ``n_warmup`` calls (on
  layouts from an unsealed dev seed) are excluded, declared in advance.  No other exclusion.
* Metrics: l1_eval_ms_p50 (A6, point) and p90, each with a cluster bootstrap 95 % CI over layouts (fixed seed); p50 at 6
  dies per switch (the slowest stratum) as a secondary.  The CPU model is recorded (run.tools and the notes).
--smoke: 15 layouts (one per stratum), 1 repeat, 1 warm-up call, an unsealed dev seed; /tmp/e003-smoke/result.json.
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "MF_L2_FFT_WORKERS"):
    os.environ[_v] = "1"
# Only real XLA flags, each with its "--" prefix.  "intra_op_parallelism_threads" is a TensorFlow session option, not an
# XLA flag: with a "--" prefix XLA aborts at JAX import ("Unknown flag in XLA_FLAGS"; checked with jax 0.11.2, T0076 note
# section 5); without one it was a malformed token.  L1 is numpy-only, so this guards a future JAX import.
XLA_FLAGS = "--xla_cpu_multi_thread_eigen=false"
os.environ["XLA_FLAGS"] = XLA_FLAGS
if hasattr(os, "sched_setaffinity"):
    os.sched_setaffinity(0, {sorted(os.sched_getaffinity(0))[0]})

import argparse  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from mfos.evidence import ExperimentRun  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CFG = {"n_layouts": 150, "repeats": 3, "n_warmup": 5, "freq_hz": 2.0e7, "cpu_wall_max": 1.1,
               "n_boot": 2000, "boot_seed": 20261008, "order_seed": 3, "warmup_seed": 7}
SMOKE = {"n_layouts": 15, "repeats": 1, "n_warmup": 1, "seed": 20261008}


def cpu_model() -> str:
    try:
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                  text=True).stdout.strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def core_config() -> str:
    """P/E core counts on Apple silicon (sysctl hw.perflevelN); the logical CPU count elsewhere."""
    if sys.platform == "darwin":
        out = []
        for lvl in (0, 1):
            r = [subprocess.run(["sysctl", "-n", f"hw.perflevel{lvl}.{k}"], capture_output=True, text=True).stdout.strip()
                 for k in ("name", "logicalcpu")]
            if r[0]:
                out.append(f"{r[1]} x {r[0]}")
        return ", ".join(out) + "; macOS: no core pinning, core type (P/E) chosen by the scheduler, not controlled"
    return f"{os.cpu_count()} logical CPUs; affinity pinned to one CPU"


def checked_config(over: dict) -> dict:
    unknown = sorted(set(over) - set(DEFAULT_CFG))
    if unknown:
        raise ValueError(f"config keys not in DEFAULT_CFG: {unknown}")
    cfg = {**DEFAULT_CFG, **over}
    for k, ref in DEFAULT_CFG.items():
        if not isinstance(cfg[k], (int, float)) or isinstance(cfg[k], bool) or (isinstance(ref, int)
                                                                                 and not isinstance(cfg[k], int)):
            raise TypeError(f"config[{k!r}] = {cfg[k]!r} has the wrong type (expected like {ref!r})")
    if cfg["n_layouts"] % 15:
        raise ValueError("n_layouts must be a multiple of 15 (balanced strata)")
    return cfg


def main(smoke: bool) -> int:
    if smoke:
        for p in (ROOT / "experiments/specs/E003.yaml", ROOT / "experiments/drafts/E003.yaml"):
            if p.exists():
                os.environ["MFOS_SPEC_JSON"] = json.dumps(yaml.safe_load(p.read_text()))
                break
        os.environ.pop("MFOS_SEED", None)
    from moduleforge.generate.halfbridge import generate_layouts
    from moduleforge.physics.peec import DEFAULT_HMAX, loop_inductance

    with ExperimentRun(experiment_id="E003", run_dir="/tmp/e003-smoke" if smoke else None) as run:
        cfg = checked_config(run.config)
        if smoke:
            cfg.update({k: v for k, v in SMOKE.items() if k != "seed"})
            seed = SMOKE["seed"]
            run.notes += "SMOKE (pipeline check only, unsealed dev seed): not evidence. "
        else:
            if not run.spec.get("sealed_seed") or run.seed is None:
                raise RuntimeError("E003 must run with the sealed seed under `mfos exp run`")
            seed = run.seed
        model = cpu_model()
        cores = core_config()
        run.tools.update({"cpu_model": model, "platform": platform.platform(), "cores": cores,
                          "core_pinning": "sched_setaffinity, 1 CPU" if hasattr(os, "sched_setaffinity") else
                          f"not available on {sys.platform} (no affinity API; P/E core type not selectable)"})
        f = float(cfg["freq_hz"])
        layouts = generate_layouts(cfg["n_layouts"], seed=seed)
        warm = generate_layouts(1, seed=cfg["warmup_seed"])[0]
        for _ in range(cfg["n_warmup"]):  # declared warm-up, excluded
            loop_inductance(warm, [f])
        order = np.random.default_rng(cfg["order_seed"]).permutation(np.repeat(np.arange(len(layouts)), cfg["repeats"]))
        ms = np.empty(order.size)
        vals = np.empty(order.size)
        c0, w0 = time.process_time(), time.perf_counter()
        for j, i in enumerate(order):
            t0 = time.perf_counter()
            vals[j] = loop_inductance(layouts[i], [f]).L_H[0]
            ms[j] = 1e3 * (time.perf_counter() - t0)
        ratio = (time.process_time() - c0) / (time.perf_counter() - w0)
        aff = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
        n_thr = threading.active_count()
        xla_ok = all(tok.startswith("--") for tok in os.environ.get("XLA_FLAGS", "").split())
        st_ok = ratio <= cfg["cpu_wall_max"] and n_thr == 1 and aff in (None, 1) and xla_ok and all(
            os.environ.get(v) == "1" for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"))
        run.sanity("single_thread_enforced", passed=st_ok, value=ratio, threshold=cfg["cpu_wall_max"],
                   detail=f"CPU/wall over the timed loop {ratio:.3f} (<= {cfg['cpu_wall_max']}); Python threads {n_thr}; "
                   f"CPU affinity set size {aff} (None: not available on {sys.platform}: no core pinning, P/E core type not "
                   f"controlled; cores {cores}); thread env set before import; XLA_FLAGS {os.environ.get('XLA_FLAGS')!r} "
                   f"(every token '--'-prefixed: {xla_ok})")
        fin = bool(np.all(np.isfinite(vals)) and np.all(vals > 0) and np.all(np.isfinite(ms)) and np.all(ms > 0))
        run.sanity("results_finite", passed=fin, value=float(np.sum(~np.isfinite(vals))), threshold=0.0,
                   detail=f"{vals.size} L values and timings finite and > 0")
        # cluster bootstrap over layouts (repeats of a layout stay together)
        by = [ms[order == i] for i in range(len(layouts))]
        rng = np.random.default_rng(cfg["boot_seed"])
        bs = np.empty((cfg["n_boot"], 2))
        for b in range(cfg["n_boot"]):
            pick = rng.integers(0, len(by), len(by))
            bs[b] = np.percentile(np.concatenate([by[i] for i in pick]), [50, 90])
        p50, p90 = np.percentile(ms, [50, 90])
        lo, hi = np.quantile(bs, [0.025, 0.975], axis=0)
        run.metric("l1_eval_ms_p50", float(p50), ci=(float(lo[0]), float(hi[0])), n=int(ms.size), unit="ms")
        run.metric("l1_eval_ms_p90", float(p90), ci=(float(lo[1]), float(hi[1])), n=int(ms.size), unit="ms")
        d6 = np.array([layouts[i].dies_per_switch == 6 for i in order])
        run.metric("l1_eval_ms_p50_6dies", float(np.percentile(ms[d6], 50)), n=int(d6.sum()), unit="ms")
        run.metric("cpu_wall_ratio", float(ratio), n=int(ms.size))
        run.notes += (f"CPU model: {model}; cores: {cores}; {platform.platform()}; n_layouts {len(layouts)} x repeats {cfg['repeats']}; "
                      f"warm-up {cfg['n_warmup']} calls excluded; L1 default hmax {DEFAULT_HMAX} m; f {f:g} Hz. ")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--smoke", action="store_true")
    sys.exit(main(ap.parse_args().smoke))
