"""E002 sizing (T0100): CPU-h and wall-h of the extrapolated-reference design from the measured VM unit costs.

Reads research/l2_layout_vm/cost.json and research/l2_layout_vm2/cost.json (GCP n2-highmem-32, 4 jobs x 8 threads,
CPU = user + sys of each child over all threads).  Fits per-level cost and wall as linear in dies per switch (least
squares over the measured layouts), then simulates the runner's scheduler (longest task first, ``jobs`` slots, phase 1
= checked layouts at k*+1 / k* / k*-1 + the two C1 references, phase 2 = every other layout at k* and k*-1) for the
candidate designs.  Writes research/e002_design/sizing.json.  Planning only (dev data); no sealed data involved.

Run: uv run python research/scripts/e002_sizing.py
"""
from __future__ import annotations

import heapq
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ["research/l2_layout_vm/cost.json", "research/l2_layout_vm2/cost.json"]
JOBS = 4
C1_CPU_H, C1_WALL_H = 0.05, 0.02  # C1 via l2 (refinement 2) and via the l2_layout internals: ~31 s / 13 s on a laptop
L1_PARENT_CPU_H_PER_LAYOUT = 0.012  # L1 default + fine meshes (2 / 1 / 0.5 mm at 20 MHz) in the parent: <= ~45 s each


def load():
    rows = []
    for p in SRC:
        d = json.loads((ROOT / p).read_text())
        for s in d["solves"]:
            rows.append(dict(src=p, seed=s["seed"], dies=s["dies_per_switch"], family=s["family"], k=s["refinement"],
                             cpu_h=s["cpu_s"] / 3600, wall_h=s["wall_s"] / 3600, rss_gb=s["peak_rss_gb"]))
    return rows


def fit(rows, k, key):
    x = np.array([r["dies"] for r in rows if r["k"] == k], float)
    y = np.array([r[key] for r in rows if r["k"] == k], float)
    a = np.vstack([np.ones_like(x), x - 2]).T
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    return float(coef[0]), float(coef[1]), float(np.max(np.abs(a @ coef - y)))


def simulate(n, check, models, jobs=JOBS, scale=1.0):
    """Wall hours of phase 1 and phase 2 under longest-first scheduling on ``jobs`` slots (each task's wall from the
    per-dies model times ``scale``) and the total CPU-h."""
    def cw(k, d):
        (c0, c1, _), (w0, w1, _) = models[k]
        return c0 + c1 * (d - 2), (w0 + w1 * (d - 2)) * scale

    per = n // 15
    dies = [d for _fam in range(3) for d in range(2, 7) for _ in range(per)]
    chk_dies = [int(s.split(":")[1]) for s in check]
    ph1, ph2, cpu = [], [], 0.0
    for d in chk_dies:
        for k in (2, 1, 0):
            c, w = cw(k, d)
            ph1.append(w)
            cpu += c
    ph1 += [C1_WALL_H, C1_WALL_H]
    cpu += 2 * C1_CPU_H
    rest = list(dies)
    for d in chk_dies:
        rest.remove(d)
    for d in rest:
        for k in (1, 0):
            c, w = cw(k, d)
            ph2.append(w)
            cpu += c
    cpu += L1_PARENT_CPU_H_PER_LAYOUT * n

    def makespan(ws):
        slots = [0.0] * jobs
        heapq.heapify(slots)
        for w in sorted(ws, reverse=True):
            t = heapq.heappop(slots)
            heapq.heappush(slots, t + w)
        return max(slots)

    w1, w2 = makespan(ph1), makespan(ph2)
    return dict(n=n, m=len(check), check=check, cpu_h=cpu, wall_phase1_h=w1, wall_phase2_h=w2, wall_h=w1 + w2,
                cpu_h_phase1=sum(cw(k, d)[0] for d in chk_dies for k in (2, 1, 0)) + 2 * C1_CPU_H)


def main():
    rows = load()
    models = {k: (fit(rows, k, "cpu_h"), fit(rows, k, "wall_h")) for k in (0, 1, 2)}
    check = ["u_shaped:6", "interleaved:6", "side_by_side:6", "side_by_side:2"]
    designs = []
    for n in (60, 90, 120):
        for scale in (1.0, 1.15, 1.25):
            r = simulate(n, check, models, scale=scale)
            r["wall_scale"] = scale
            designs.append(r)
    check6 = check + ["interleaved:2", "u_shaped:2"]
    for n in (60, 90):
        r = simulate(n, check6, models)
        r["wall_scale"] = 1.0
        designs.append(r)
    out = dict(source=SRC, jobs=JOBS, measured=rows,
               model={str(k): dict(cpu_h=dict(at2=v[0][0], per_die=v[0][1], max_abs_resid=v[0][2]),
                                   wall_h=dict(at2=v[1][0], per_die=v[1][1], max_abs_resid=v[1][2]))
                      for k, v in models.items()},
               designs=designs,
               notes="k: 0 = 0.5 mm (k*-1), 1 = 0.25 mm (k*), 2 = 0.125 mm (k*+1). Wall per task as measured at 4 jobs x 8 "
                     "threads (concurrent solves); wall_scale inflates every task's wall to test the timeout margin.")
    p = ROOT / "research/e002_design/sizing.json"
    p.write_text(json.dumps(out, indent=1))
    for k, v in models.items():
        print(f"level {k}: cpu_h = {v[0][0]:.3f} + {v[0][1]:.4f}(d-2) (max resid {v[0][2]:.3f}); "
              f"wall_h = {v[1][0]:.3f} + {v[1][1]:.4f}(d-2) (max resid {v[1][2]:.3f})")
    for r in designs:
        print(f"n={r['n']:3d} m={r['m']} wall x{r['wall_scale']:.2f}: CPU {r['cpu_h']:.1f} h (phase 1 "
              f"{r['cpu_h_phase1']:.1f}); wall {r['wall_h']:.1f} h (phase 1 {r['wall_phase1_h']:.1f}, phase 2 "
              f"{r['wall_phase2_h']:.1f})")


if __name__ == "__main__":
    main()
