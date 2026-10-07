"""Founder diagnostic for inbox I0039 (not evidence): does the layout L2 converge smoothly under pure lateral refinement
when every layout feature lies on every cell grid?

T0075 (three attempts) found L(refinement) oscillating (odd levels low, even high) and attributed the 3->4 step to the
lateral grid (thickness layers -0.04 %, wire filaments +0.02 %). Generated layouts put die x-positions anywhere
(continuous u) and other edges on a 0.1 mm grid, so trace edges, die footprints and port cells are quantized
differently at each cell size. This script builds the generator's own u_shaped 2-die layout with every free parameter
on the 0.5 mm grid (s = 5.0, g = dg = 2.0, e = 1.0, x_die = 10.0, two wires at +-0.5 mm), so all features sit on the
0.5 / 0.25 / 0.125 mm lattices, and solves it at 20 MHz with the thickness layers and wire filaments held at k_star = 3:

  set A (aligned, pure lateral): cells 0.5, 0.25, 0.125 mm
  set B (original ladder, same layout): cells 1.0, 0.7, 0.35 mm (0.5 and 0.25 shared with A)

Rule fixed before the run (I0039): A smooth (both changes one sign, the second smaller) -> the oscillation is feature
quantization; A not smooth -> something else is non-smooth.

    uv run python research/scripts/l2_layout_lateral_diag.py --out research/l2_layout_diag [--jobs 2]
"""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
K_STAR = 3
CELLS_MM = {"A": (0.5, 0.25, 0.125), "B": (1.0, 0.7, 0.35)}


class AlignedRng:
    """Stands in for the generator's numpy Generator: every free draw lands on the 0.5 mm grid."""

    def uniform(self, lo, hi):
        table = {(4.0, 5.5): 5.0, (1.5, 2.5): 2.0, (0.6, 1.5): 1.0}
        if (lo, hi) in table:
            return table[(lo, hi)]
        if lo == 0.0 and hi in (1.5, 2.0):  # trace extensions e
            return 1.0
        if hi in (1.0, 0.15):  # die-row position u -> x_die = X_DIE_MIN
            return lo
        raise ValueError(f"unexpected draw uniform({lo}, {hi})")

    def integers(self, lo, hi):
        return 2  # wires per die: offsets +-0.5 mm

    def choice(self, xs):
        return xs[0]  # 0.3 mm wire


def aligned_layout():
    from moduleforge.generate import halfbridge as hb
    return hb._build("u_shaped", 2, AlignedRng())


def child(cell_mm: float, out: Path) -> None:
    from moduleforge.solvers import l2_layout as L
    L.CELL = (cell_mm * 1e-3,) + tuple(L.CELL[1:])
    L.LAYERS_TOP, L.LAYERS_BACK, L.LAYERS_BASE = ((x[K_STAR],) + tuple(x[1:]) for x in
                                                  (L.LAYERS_TOP, L.LAYERS_BACK, L.LAYERS_BASE))
    L.WIRE_EDGES = (L.WIRE_EDGES[K_STAR],) + tuple(L.WIRE_EDGES[1:])
    lay = aligned_layout()
    t0 = time.perf_counter()
    r = L.loop_inductance(lay, [2.0e7], refinement=0)
    ru = resource.getrusage(resource.RUSAGE_SELF)
    m = r.meta
    rec = dict(cell_mm=cell_mm, L_H=float(r.L_H[0]), R_ohm=float(r.R_ohm[0]), wall_s=time.perf_counter() - t0,
               cpu_s=ru.ru_utime + ru.ru_stime,
               peak_rss_gb=ru.ru_maxrss * (1.0 if sys.platform == "darwin" else 1024.0) / 1e9,
               n_unknowns=int(m["n_unknowns"]), gmres_iters=[int(x) for x in m["gmres_iters"]],
               solver_tol=float(m["solver_tol"]), cell_x=float(m["mesh_params"]["cell_x"]),
               cell_y=float(m["mesh_params"].get("cell_y", m["mesh_params"]["cell_x"])),
               layers=m["mesh_params"]["layers"], partial_cells=m["mesh_params"]["partial_cells"],
               area_rel_err=m["mesh_params"]["area_rel_err"],
               dies=[(d.cx, d.cy, d.w, d.h) for d in lay.dies])
    out.write_text(json.dumps(rec, indent=1, default=str))


def run_one(cell_mm: float, outdir: Path) -> dict:
    f = outdir / f"cell_{cell_mm:g}mm.json"
    if f.exists():
        return json.loads(f.read_text())
    print(f"solve cell {cell_mm} mm", flush=True)
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(cell_mm), str(f)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        rec = {"cell_mm": cell_mm, "failed": (r.stdout + r.stderr)[-3000:]}
        f.write_text(json.dumps(rec, indent=1))
        return rec
    rec = json.loads(f.read_text())
    print(f"cell {cell_mm} mm: L = {rec['L_H'] * 1e9:.4f} nH, {rec['cpu_s']:.0f} CPU-s, {rec['peak_rss_gb']:.1f} GB, "
          f"partial cells {rec['partial_cells']}", flush=True)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="research/l2_layout_diag")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--child", nargs=2)
    ap.add_argument("--only", type=float, nargs="*")
    a = ap.parse_args()
    if a.child:
        child(float(a.child[0]), Path(a.child[1]))
        return 0
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    cells = a.only or sorted({c for v in CELLS_MM.values() for c in v} | {0.5, 0.25}, reverse=True)
    with ThreadPoolExecutor(a.jobs) as ex:  # the 0.125 mm solve starts first; the rest run beside it
        recs = {r["cell_mm"]: r for r in ex.map(lambda c: run_one(c, out), sorted(cells))}

    def seq(cs):
        vals = [recs[c].get("L_H") for c in cs]
        if any(v is None for v in vals):
            return {"cells_mm": cs, "L_nH": None}
        d = [(vals[i + 1] - vals[i]) / vals[i + 1] for i in range(len(vals) - 1)]
        smooth = len(d) >= 2 and all(x * d[0] > 0 for x in d) and all(abs(d[i + 1]) < abs(d[i]) for i in range(len(d) - 1))
        return {"cells_mm": cs, "L_nH": [v * 1e9 for v in vals], "rel_changes": d, "smooth": smooth}

    summary = {"A_aligned_lateral": seq([0.5, 0.25, 0.125]) if not a.only else None,
               "B_original_ladder": seq([1.0, 0.7, 0.5, 0.35, 0.25]) if not a.only else None,
               "solves": recs}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "solves"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
