"""L1 fidelity DoD (reviews T0044/T0045 of T0023): discretisation must not drive the loop inductance.

Measured on the merged L1 (founder session, 2026-09-30), 20 MHz, seed 5:
  * bond-wire polyline 7 -> 25 points raises L by +1.1 .. +5.1 % and keeps rising (divergent segmentation);
  * default mesh (4 mm) vs 1 mm: +0.3 .. +12.0 %, growing with die count (the F3 missing-physics signature).
Requirements: across 7/13/25 wire points L varies by <= 0.5 %; the default mesh is within 3 % of the 1 mm mesh.
The single-core timing limit (p50 <= 50 ms) is checked separately by the L1 benchmark.
"""
import dataclasses

from moduleforge.generate.halfbridge import generate_layouts
from moduleforge.geometry.layout import arc_wire
from moduleforge.physics.peec import loop_inductance

F = [2e7]


def with_npts(lay, n):
    return dataclasses.replace(lay, wires=[arc_wire(w.points[0, :2], w.points[-1, :2], w.points[0, 2], w.points[-1, 2],
                                                    w.loop_height, w.diameter, w.net, npts=n) for w in lay.wires])


problems = []
for fam in ("side_by_side", "interleaved", "u_shaped"):
    for dps in (2, 6):
        lay = generate_layouts(1, seed=5, family=fam, dies_per_switch=dps)[0]
        wl = [float(loop_inductance(with_npts(lay, n), F).L_H[0]) for n in (7, 13, 25)]
        spread = (max(wl) - min(wl)) / min(wl)
        default = float(loop_inductance(lay, F).L_H[0])
        fine = float(loop_inductance(lay, F, hmax=1e-3).L_H[0])
        bias = default / fine - 1
        print(f"{fam:13s} dps={dps}: wire-point spread {spread:.2%}, default mesh vs 1 mm {bias:+.2%}")
        if spread > 0.005:
            problems.append(f"{fam}/{dps}: L varies {spread:.2%} across 7/13/25 wire points (> 0.5 %)")
        if abs(bias) > 0.03:
            problems.append(f"{fam}/{dps}: default mesh differs {bias:+.2%} from the 1 mm mesh (> 3 %)")
assert not problems, "\n  - ".join(["L1 discretisation problems:", *problems])
print("L1 is converged in wire segmentation and within 3 % of the 1 mm mesh")
