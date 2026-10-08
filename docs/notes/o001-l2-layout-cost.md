# O001: layout L2 cost and lateral convergence at E002 scale (T0075)

This note records engineering measurements, not evidence. It lives in `docs/notes/` because `research/notes/` is
outside the builder write scope (founder decision, attempt 3).

## Result (attempt 5 of 5, 2026-10-07)

- **k_star = 1 (0.25 mm cells).** The thickness layers are held at every level: top Cu 10, backside 6, baseplate 6. The
  top-Cu layers are 3.30, 7.44, 16.74, 37.69 and 84.83 µm from each face, against a skin depth of 14.8 µm at 20 MHz;
  their 1-D internal impedance is within 1.6 % of the exact slab. cost.json records `k_star`, `layer_thickness_um` and
  `skin_resolution`.
- **Cost gate at k_star: met on this laptop** (`--quick`, the DoD run, GMRES_TOL 1e-7, one fresh process per solve):
  - 2 dies/switch: 1162 CPU-s and 7.7 GB (48 % and 64 % of the gate);
  - 6 dies/switch: 2011 CPU-s and 8.9 GB (84 % and 74 %).

  The 6-die CPU margin depends on machine state. This run had 8.8 GB of swap in use on the machine, and the 6-die
  GMRES took 4.5 s per iteration, against 3.0 s in attempt 4. Attempt 4 measured the same solve at 2286 CPU-s with
  GMRES_TOL 1e-9.
- **solver_tol < 1e-3 on every solve:** 1.7-2.0e-5, GMRES flag 0, per-net area error 2.6e-16.
- **Convergence gate: not measured here.** It needs the 0.125 mm level (~35 GB), which does not fit in 16 GB. The founder
  runs it with `--vm` after merge. The measured step k*−1 → k* is −0.78 % (seed 7, 2 dies, this run) and −1.19 % (seed
  11, 2 dies, u_shaped, attempt 4). The founder diagnostic's contraction (0.61) would put k* → k*+1 at about −0.5 % and
  −0.7 %. That is an extrapolation, not a measurement.
- **Sensitivity at k_star.** +2 thickness layers per slab: −0.043 % (attempt 4, measured on this ladder). The finer
  wire filaments were not measured on this ladder; attempt 3 measured +0.02 % on its old ladder. Both solves are in
  `--vm`.
- **Projected E002:** about 0.44 CPU-h per layout at k_star (2-6 dies, measured), plus about 3 CPU-h per layout of the
  k*+1 refinement subset (extrapolated). See "Projected E002 CPU-h".

**Reproduce:**
- `uv run python benchmarks/l2_layout_cost.py --quick --out DIR` is the DoD run. Add `--sensitivity` for the two
  sensitivity solves.
- `uv run python benchmarks/l2_layout_cost.py --vm --jobs N --out DIR` is the burst-VM run (see below).

Each solve runs in a fresh interpreter. The child reports `getrusage(RUSAGE_SELF)` user+sys time over all threads, and
its peak RSS. Frequency: 20 MHz. Seeds: unsealed dev seeds only (7, 11, 3).

## Founder diagnostic I0039 (research/l2_layout_diag, GCP n2-highmem-32, not evidence)

The founder took the generator's own u_shaped 2-die layout, with every free parameter on the 0.5 mm grid. Thickness
layers and wire filaments were held at attempt 3's level 3 (top 10, backside 6, baseplate 6 layers; 25 filaments per
wire). Only the lateral cell changed:

| set | cells (mm) | L (nH) | steps |
|---|---|---|---|
| A, aligned | 0.5 / 0.25 / 0.125 | 12.8885 / 12.7662 / 12.6915 | −0.96 %, −0.59 % (contraction 0.61, order ≈ 0.7) |
| B, attempt 3's ladder | 1.0 / 0.7 / 0.5 / 0.35 / 0.25 | 12.811 / 11.787 / 12.889 / 12.193 / 12.766 | −8.7, +8.5, −5.7, +4.5 % |

With partial-cell weighting, the non-aligned 0.7 and 0.35 mm cells read 5-9 % low. A partial cell carries its current
over its full box. That inductive footprint, not the conducting area, was the error source. Attempt 3's fill-fraction
conductance made the area exact, but it could not fix the footprint. The generator also placed dies at continuous x, so
die footprints never aligned with any cell.

The diagnostic's 0.125 mm solve hit the GMRES cap of 100 × 5 iterations, giving solver_tol 1.2e-3. It needed 35 GB and
69,000 CPU-s, with 32 threads and two jobs sharing the VM.

## What changed under the re-scope (I0039, attempts 4 and 5)

1. **Generator on a 0.5 mm design grid** (`generate/halfbridge.py`, `DESIGN_GRID_MM`). The values snapped are the die
   size s, the gaps g and dg, the extensions e, and the die-row start xs (the start, not the centre). The housing
   constants were already on the grid, so every trace edge and die footprint now lies on it.
   - What is unchanged: the random stream (one draw per parameter, then rounding), the families, the die counts and
     the DRC check.
   - Wire positions, loop height and wire diameter stay as drawn. They are not lateral copper features, and the
     bilinear foot contacts handle them.
   - Before this, s, g, dg and e were rounded to 0.1 mm and xs was continuous.
2. **Lateral ladder.** CELL = 0.5 / 0.25 / 0.125 mm at refinements 0 / 1 / 2. The lattice is the baseplate box
   (−8..78 × −8..48 mm), so every cell edge lies on the design grid. Thickness layers are held at top 10, backside 6
   and baseplate 6 at every level, and wire filaments at the annuli (0, .35, .6, .8, .93, 1) × 6 sectors (25 per
   wire). A refinement step is purely lateral. **k_star = 1 (0.25 mm)** is E002's level (`l2_layout.K_STAR`).
3. **ValueError off the lattice.** This replaces the partial-cell weighting, which is removed (`branch_weights`, the
   per-branch preconditioner blocks, the sliver merge). The error is raised in these cases:
   - a cell is partly covered by a trace, backside Cu or the baseplate;
   - a die footprint edge is not on a cell boundary;
   - the lattice box is not a whole number of cells.

   A cell with copper of two nets is still refused. The exact per-net area test is now the alignment check.
4. **GMRES at the finest level.** Restart 100 (the Krylov basis is the largest memory term, so it stays). The cycle
   cap goes from 5 to 40, for a cap of 4000 iterations. The a-posteriori bound never relies on convergence, and every
   solve records scipy's flag (`gmres_flags`).
5. **Benchmark modes.**
   - `--quick` (this laptop, the DoD run; founder amendment for attempt 5): seed 7 / 2 dies (interleaved) at k_star−1
     and k_star, plus seed 7 / 6 dies at k_star. Three solves.
   - `--sensitivity`: the two sensitivity solves at k_star. The founder moved them, and the second-family layout, to
     `--vm`; the quick run does not include them.
   - `--vm`: k_star−1, k_star and k_star+1 for seeds 7 / 2 dies (interleaved), 11 / 2 dies (u_shaped) and 3 / 6 dies
     (side_by_side), plus the sensitivity solves. Use `--jobs` for concurrency. Each child is limited to `--threads`
     BLAS/OpenMP/FFT threads, by default cores // jobs.
   - cost.json adds `steps` (every measured lateral step), `sensitivity`, `cells_mm`, `k_star_criterion` and
     `layer_thickness_um`.

Attempt 5 (final, founder amendment of 2026-10-07) changed only these:
- **GMRES_TOL 1e-9 → 1e-7** (see "Measurements"). solver_tol is unchanged in definition and stays the rigorous bound.
- **`--quick` is three solves:** seed 7 / 2 dies at k*−1 and k*, and seed 7 / 6 dies at k*.
- **`--vm` starts every 0.125 mm solve first.** Before, with `--jobs 3`, the first three jobs were one layout's three
  levels.
- **The child records `cpu_user_s` and `cpu_sys_s`** besides `cpu_s`.

Kept from attempts 1-3:
- the correctness fixes: die shorts limited to their own net (`DieShort.bottom_net`), the near-parallel
  `segment_mutual` band counted in solver_tol, `_nearest_cell` on an empty mask, the pFFT grid edge;
- the corner-lattice near-field speed-up;
- the layout-level independent oracle (`test_layout_loop_inductance_vs_independent_partial_inductance_sum`);
- `solver_tol_rel_L`;
- the bilinear wire-foot contacts.

**Bilinear wire-foot contacts** are a model change made in attempt 2, beyond the original packet. A wire foot on a
trace, and each of the two port terminals, injects its current at its true lateral position. The current is split over
the four surrounding cell centres with bilinear weights, using only cells of the contact's net, renormalised to sum
to 1. If none of the four cells is on the net, the nearest cell of the net is used. Snapping a foot to the nearest cell
centre moved the injection point by up to half a cell, and L stepped by ±5 % under sub-cell shifts of the layout
(`test_wire_foot_between_cell_centres_gives_a_smooth_L`). Generated wire feet are not on the cell grid: they sit at the
die centre + k × 1 mm. The bilinear contact is what keeps them smooth across levels.

## Layers held at every level (skin depth δ = 14.8 µm at 20 MHz)

| slab | layers | thicknesses from the face (µm) | 1-D Z_s error at 20 MHz |
|---|---|---|---|
| top Cu (300 µm) | 10 | 3.3, 7.4, 16.7, 37.7, 84.8 (per face) | 1.6 % |
| backside Cu (300 µm) | 6 | graded the same way, 3 per face | 8.3 % |
| baseplate (3 mm) | 6 | graded from the top face | – |

The layers are graded to F_MESH = 100 MHz. The Z_s error compares `layered_surface_impedance` with the exact
(k/σ)·coth(kt) [RWV 5.6]; it is recorded in cost.json under `skin_resolution`.

## Measurements: the DoD run (`--quick`, attempt 5, GMRES_TOL 1e-7)

Hardware: 10-core Apple laptop (4P + 6E cores), 16 GB. 20 MHz. Cell 0.5 mm is refinement 0 (k*−1); 0.25 mm is
refinement 1 (k*). The raw cost.json of this run is `docs/notes/o001-l2-layout-cost.json`.

| seed | family | dies/switch | cell (mm) | L (nH) | R (mΩ) | CPU-s | wall s | peak RSS GB | unknowns | GMRES it. | solver_tol |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 | interleaved | 2 | 0.5 | 11.1150 | 36.4 | 180 | 156 | 2.28 | 490,214 | 133 | 1.8e-05 |
| 7 | interleaved | 2 | **0.25 (k*)** | **11.0292** | 36.3 | **1162** | 926 | **7.69** | 1,977,168 | 238 | 1.7e-05 |
| 7 | interleaved | 6 | **0.25 (k*)** | **8.0069** | 25.8 | **2011** | 1861 | **8.92** | 1,977,768 | 249 | 2.0e-05 |

- Every solve: GMRES flag 0, every feature on the lattice, per-net area error 2.6e-16.
- solver_tol is dominated by the stated pFFT wire↔grid operator bound (1.7-2.0e-5). The a-posteriori residual term is
  3.3e-10 / 2.0e-9 / 4.7e-10. `solver_tol_rel_L` equals solver_tol to three digits.
- Stage times at k* (grid tables / wire-grid operator / GMRES, in s): 2 dies 281 / 136 / 501; 6 dies 319 / 388 / 1126.
  Six dies triple the wires (36 × 25 filaments) and the exact near pairs (82.8 M against 27.6 M).
- The parent's `time` recorded 2553 s user and 801 s system over the whole run. A large system share points to paging
  under memory pressure. The child now also records `cpu_user_s` and `cpu_sys_s` separately (added after this run).
  A standalone re-run of the 0.5 mm child, with the machine less loaded, gave the same L to every digit, 198 s user and
  1.7 s sys, and a peak RSS of 3.58 GB. Under memory pressure macOS compresses or swaps pages, so peak RSS reads low:
  2.28 GB in the quick run, 2.74 GB in attempt 4. The 12 GB gate should be read against the higher values. Attempt 4's
  6-die k* solve peaked at 9.28 GB, 77 % of the gate.

**GMRES_TOL 1e-9 → 1e-7.** GMRES_TOL is a stopping rule, not the accuracy statement. solver_tol is the rigorous
a-posteriori bound (D0004), and its residual term is quadratic in the residual (|dZ| ≤ ‖P(Mx)‖² / r_min,
`l2_core.a_posteriori`). At 1e-9 that term was ~4e-15; at 1e-7 it is 3e-10 to 2e-9, at most about 1e-4 of the
stated bounds that make up solver_tol. L agrees with attempt 4's 1e-9 values to the five digits recorded (11.1150 / 11.0292 /
8.0069 nH). The iterations fell by 40 % (222 / 399 / 415 → 133 / 238 / 249), and the CPU-s by 17 % / 28 % / 12 %.

### Attempt 4's measurements (GMRES_TOL 1e-9, same ladder and model)

| seed | family | dies/switch | cell (mm) | L (nH) | R (mΩ) | CPU-s | wall s | peak RSS GB | unknowns | GMRES it. | solver_tol |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 | interleaved | 2 | 0.5 | 11.1150 | 36.4 | 216 | 173 | 2.74 | 490,214 | 222 | 1.8e-05 |
| 7 | interleaved | 2 | 0.25 (k*) | 11.0292 | 36.3 | 1618 | 1203 | 7.86 | 1,977,168 | 399 | 1.7e-05 |
| 11 | u_shaped | 2 | 0.5 | 12.8345 | 41.0 | 248 | 200 | 3.36 | 464,344 | 229 | 1.3e-05 |
| 11 | u_shaped | 2 | 0.25 (k*) | 12.6832 | 40.8 | 1639 | 1188 | 7.67 | 1,873,268 | 392 | 1.4e-05 |
| 7 | interleaved | 6 | 0.25 (k*) | 8.0069 | 25.8 | 2286 | 1963 | 9.28 | – | 415 | 2.0e-05 |

Stage times at k* (grid / wire-grid / GMRES, s): 2 dies 299 / 137 / 759; 6 dies 315 / 391 / 1231. The founder moved
the seed-11 layout out of the quick set for attempt 5; it is in `--vm`.

## Lateral steps k*−1 → k* (0.5 → 0.25 mm)

| seed / dies | ΔL / L(0.25) | ΔR / R(0.25) |
|---|---|---|
| 7 / 2 (interleaved) | −0.78 % | −0.20 % |
| 11 / 2 (u_shaped) | −1.19 % | −0.60 % |
| founder diagnostic, u_shaped 2 (aligned by hand) | −0.96 % | −0.35 % |

Both steps have the diagnostic's sign and size. In the diagnostic, the next step (0.25 → 0.125 mm) was −0.59 %, a
contraction of 0.61. If the generated layouts contract the same way, k*→k*+1 is about −0.5 % (seed 7) and −0.7 %
(seed 11). That would pass the < 1 % gate. **This is an extrapolation, not a measurement.** The convergence gate is
applied to the VM run.

## Sensitivity at k_star (seed 7, 2 dies, 0.25 mm; gate |ΔL| < 0.2 %)

| variant | layers top / back / base | filaments per wire | L (nH) | ΔL / L | ΔR / R | CPU-s | RSS GB |
|---|---|---|---|---|---|---|---|
| k* as used (attempt 4, 1e-9) | 10 / 6 / 6 | 25 | 11.0292 | – | – | 1618 | 7.86 |
| +2 thickness layers per slab (attempt 4, 1e-9) | 12 / 8 / 8 | 25 | 11.0245 | **−0.043 %** | +8.2 % | 2277 | 9.88 |
| next finer wire annuli (0, .3, .5, .7, .85, .95, 1) | 10 / 6 / 6 | 31 | not measured on this ladder | | | | |

- **Thickness layers:** converged for L at k_star (−0.043 %, gate 0.2 %).
- **Wire filaments:** not measured here. Attempt 4 timed out before this solve, and the founder moved it to `--vm`.
  Attempt 3 measured +0.02 % for the same refinement of the wire annuli, but on its old ladder (0.35 mm cells).
- R is not converged in the layers (+8 %). R is reported, not gated, and is not a reference value.

## Cost per layout vs dies per switch and refinement

Measured on this laptop (CPU-s = user + sys over all threads of the child; GMRES_TOL 1e-7 unless marked).

| level | 2 dies/switch | 6 dies/switch | peak RSS |
|---|---|---|---|
| 0.5 mm (k*−1) | 180 CPU-s (seed 11 at 1e-9: 248) | – | 2.3 GB (seed 11: 3.4) |
| **0.25 mm (k*)** | **1162 CPU-s** (1e-9: 1618-1639) | **2011 CPU-s** (1e-9: 2286) | 7.7 / 8.9 GB |
| 0.125 mm (k*+1) | VM only; ~2.5 CPU-h extrapolated (below) | ~3 CPU-h extrapolated | ~35 GB (founder diagnostic) |

- **Dies.** At k_star the cost is about linear in die count: c(d) ≈ 1162 + 212·(d − 2) CPU-s. The mean over 2-6 dies is
  about 1590 CPU-s = 0.44 CPU-h. The memory barely grows (7.7 → 8.9 GB): the grid dominates it, not the wires.
- **Refinement.** One lateral level (0.5 → 0.25 mm, 2 dies) costs 6.5× the CPU and 3.4× the memory. The cell count is
  ×4, the GMRES iterations ×1.8, and the plane tables ×7.6 (grid stage 37 → 281 s). GMRES time is ×11.7, because the
  time per iteration grows faster than the unknowns (0.32 → 2.10 s).
- **k*+1 (extrapolation).** Applying the same factors per stage for 2 dies gives grid ~2250 s, wire-grid ~250 s and
  GMRES ~4700 s (~430 iterations). That is ~7300 s wall, or ~9000 CPU-s ≈ 2.5 CPU-h. Six dies add roughly another
  0.5 CPU-h. I use 3 CPU-h per k*+1 layout for planning; the VM run replaces it.

The diagnostic's VM CPU-s are not comparable with these. Its 0.25 mm solve of a similar layout took 17,260 CPU-s on
the VM against ~1,600 here (at 1e-9). It ran 32 BLAS/OpenMP threads per process with two solves at once, and their
overhead counts as CPU time. `--vm` therefore sets the thread limit of each child (`--threads`, by default
cores // jobs). E002 should run the same way.

## GMRES iterations

| cell | 0.5 mm | 0.25 mm | 0.125 mm |
|---|---|---|---|
| seed 7 / 2 dies, 1e-7 (attempt 5) | 133 | 238 | VM |
| seed 7 / 6 dies, 1e-7 (attempt 5) | – | 249 | VM |
| seed 7 / 2 dies, 1e-9 (attempt 4) | 222 | 399 | – |
| seed 11 / 2 dies, 1e-9 (attempt 4) | 229 | 392 | – |
| seed 7 / 6 dies, 1e-9 (attempt 4) | – | 415 | – |
| founder diagnostic | 191 | 398 | > 500 (cap 100 × 5) |

- **Growth per level:** about ×1.8 per halving of the cell at both tolerances (133 → 238, 222 → 399), roughly
  ∝ cell^−0.85. The count barely depends on the die count (238 against 249 at k*).
- **0.125 mm:** I expect about 430 iterations at 1e-7, far below the new cap of 100 × 40 = 4000.
  `test_solver_tol_usable_at_every_refinement` runs a two-wire plane system at 0.125 mm on this laptop: flag 0,
  solver_tol < 1e-3. **The production 0.125 mm solve has not run here.** It does not fit in 16 GB, so the VM run is the
  check.

## Projected E002 CPU-h

n layouts at k_star cost about 0.44 CPU-h each (2-6 dies, measured). A refinement subset of m layouts at k*+1 costs
about 3 CPU-h each (extrapolated, ~35 GB each, VM only). The k*−1 solves cost 0.05 CPU-h each, if E002 wants them.

CPU-h(n, m) ≈ 0.44·n + 3·m

| n | m = 3 | m = 6 | m = 10 |
|---|---|---|---|
| 60 | 35 | 44 | 56 |
| 75 | 42 | 51 | 63 |
| 90 | 49 | 58 | 70 |

O001's 60 CPU-h covers n = 60 with up to 11 refinement layouts, n = 75 with up to 9, or n = 90 with up to 6. Three
caveats:
- These are laptop CPU-s at one solve per machine. On the VM they hold only if each child's threads are limited; with
  unthrottled threads the diagnostic's CPU-s were ~10× higher.
- The k*+1 cost carries the largest uncertainty. The VM run measures it.
- The per-solve CPU-s varies ±25 % with machine load and memory pressure (6 dies: 2011 here, 2286 in attempt 4).

## Burst-VM run (founder, after merge)

`uv run python benchmarks/l2_layout_cost.py --vm --jobs 3 --out DIR` runs 0.5 / 0.25 / 0.125 mm for seeds 7 / 2 dies
(interleaved), 11 / 2 dies (u_shaped) and 3 / 6 dies (side_by_side), plus the two sensitivity solves at k_star: 11
solves. The three 0.125 mm solves (~35 GB each) start first. Each child gets cores // jobs threads.

cost.json then carries:
- `convergence`: the gate for each layout. It passes when |ΔL| < 1 %, contracting with the same sign as the k*−1 → k*
  step, or when |ΔL| < 1e-4.
- `sensitivity`: both variants against the k_star solve of seed 7 / 2 dies, gate |ΔL| < 0.2 %.
- `steps`, every solve record (with `cpu_user_s` / `cpu_sys_s`), and `not_fitted` for any solve that crashed or timed
  out.

The script exits 1 if any gate fails or any solve does not finish. I have **not** run any of these on the VM. Seed 3 /
6 dies has not been solved at any level, and no 0.125 mm production solve has run.

## Tests changed under the re-scope (attempt 4, tests/unit)

Forced by the generator change: none of the existing generator tests pin values. They check DRC validity, determinism,
coverage, fixed terminals, the area-proxy spread, and a hand-built proxy. All pass unchanged. One test is new:
`test_every_trace_edge_and_die_footprint_on_the_design_grid`.

`tests/unit/solvers/test_l2_layout.py` changed because the model now refuses features off the lattice, and because the
ladder has three levels:
- **Fixtures.**
  - `tiny_layout` was moved onto the 2 mm `coarse` lattice: traces at even mm, 2 mm dies, substrate −1..25 × −1..15 mm.
  - `strip_layout` dies changed from 1.6 to 2.0 mm, which covers the same single cell, and the substrate from −1..41 ×
    0..6 to −1..41 × −1..7 mm, so the backside Cu (inset 1 mm) is on the lattice.
  - `coarse` sizes its tuples to MAX_REFINEMENT+1 and pins the coarse wire annuli (0, .6, 1) these tests were written
    with.
  - All assertions are unchanged.
- **Die-short test.** It now uses an 8 mm die over DC+ (0..4 mm), a gap cell, and a PHASE cell (from 6 mm). The old
  4.4 mm die is off the lattice.
- **Replaced (the feature was removed):**
  - `test_partial_cells_represent_every_net_area_exactly_at_every_refinement` became
    `test_every_net_area_exact_and_every_feature_on_the_lattice_at_every_refinement`: seeds 7 and 11, levels 0-2,
    ≤ 1e-12, fractions exactly 0/1, die footprints on the lattice.
  - `test_fill_fraction_conductance_dc_resistance_closed_form` and the narrow-trace test became
    `test_layout_off_the_lattice_is_refused`: a partial trace, a sub-cell trace, a die, the backside outline, the
    lattice extent, and the `_nearest_cell` empty-mask error.
  - `test_branch_weights_series_halves_and_rect_cover_exact` became `test_rect_cover_exact`.
- **New:** `test_gmres_iteration_cap_is_restart_times_cycles_and_restarted_gmres_converges`.
- **`test_solver_tol_usable_at_every_refinement`** now runs at 0.5 / 0.25 / 0.125 mm and also requires GMRES flag 0.
  The far-branch assertion applies below 0.5 mm, where part of the plane lies beyond the near box.
- **`test_slab_surface_impedance_limits_and_layered_convergence`.** The "> 100 % off" check now names the former
  4-layer layering explicitly. It also checks that the held 10-layer layering is within 2 % on both faces.
