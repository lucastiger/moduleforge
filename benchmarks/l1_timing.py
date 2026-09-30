"""Single-core timing benchmark of the L1 PEEC model (O001 criterion A6: median <= 50 ms per evaluation).

One evaluation = ``Layout -> loop_inductance(layout, [20 MHz])`` including discretisation, on 6 dies per
switch. Threads are pinned to one *before* numpy is imported. One declared warm-up call is excluded.
Run: ``uv run python benchmarks/l1_timing.py``; exit status 1 if p50 > 50 ms.
"""
import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS"):
    os.environ[_v] = "1"
os.environ["XLA_FLAGS"] = "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"

import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

from moduleforge.generate.halfbridge import generate_layouts  # noqa: E402
from moduleforge.physics.peec import loop_inductance  # noqa: E402

SEED = 20240611  # fixed dev seed
N_LAYOUTS = 36
DIES_PER_SWITCH = 6
FREQ_HZ = 2.0e7
LIMIT_MS = 50.0


def main() -> int:
    layouts = generate_layouts(N_LAYOUTS, seed=SEED, dies_per_switch=DIES_PER_SWITCH)
    loop_inductance(layouts[0], [FREQ_HZ])  # declared warm-up call (excluded from the statistics)
    ms = []
    for lay in layouts:
        t0 = time.perf_counter()
        loop_inductance(lay, [FREQ_HZ])
        ms.append(1e3 * (time.perf_counter() - t0))
    p50, p90 = np.percentile(ms, [50, 90])
    print(f"L1 timing: n={len(ms)} layouts, {DIES_PER_SWITCH} dies/switch, f={FREQ_HZ:.3g} Hz, 1 thread, seed={SEED}")
    print(f"l1_eval_ms_p50={p50:.2f} l1_eval_ms_p90={p90:.2f} (limit p50 <= {LIMIT_MS} ms)")
    if p50 > LIMIT_MS:
        print("FAIL: median above limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
