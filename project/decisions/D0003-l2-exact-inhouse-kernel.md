# D0003 — L2 inductance matrix from an exact in-house kernel; FastHenry for meshing and cross-check
Date: 2026-10-04 · Status: accepted · Decider: founder · Amends: D0002 (how the pinned FastHenry is used)

## Context
E001 is registered (spec sha256:1c60eaaf…, runner frozen) with a solver error budget of 1e-5: the L2 adapter must
report `meta['solver_tol']` as an honest bound on the relative error of the port impedance, and the runner's
`l2_solver_tolerance` check holds it within that budget. T0022 (the L2 adapter) found, in its second attempt, that
FastHenry's partial-inductance kernel cannot meet this:
- per-entry kernel error against a 6-D Gauss quadrature converged to ~1e-15: up to 1.6e-6 for close filament pairs,
  4.8e-7 at 15–45 widths and up to 2.6e-5 at >= 45 widths; it comes from FastHenry's far-field approximations, not
  round-off (a translated copy of a pair changes by 1.8e-15). Script: `benchmarks/infra/fh_kernel_accuracy.py`
  (T0022 commit 2e1d2bb); measured by T0022's builder, not re-run by the founder session;
- worst-case bounds on the summed error exceed the per-case allowance (bars ~5.2e-7 vs 1–2e-7 allowed; wires at
  20 MHz ~1.5–3e-5 vs 1e-5), although the actual error is ~1e-6 because opposite-sign errors cancel;
- FastHenry's multipole solve either re-meshes with the multipole order (breaking one mesh per solve) or moves C1 by
  up to 1.7 % across orders 2–8.

## Decision
The L2 adapter computes the partial-inductance (and resistance) matrices itself with exact closed forms: Hoer & Love
(1965) for rectangular bars, the exact filament mutual (Grover 1946) where filaments are used, each entry exact to
~1e-9 or better, so `meta['solver_tol']` is a rigorous bound well inside the 1e-5 budget. The port impedance comes
from a direct solve of the mesh system. FastHenry (D0002 pin) remains in use for geometry meshing where convenient
and as an independent cross-check of the assembled result (`meta['fh_zc_rel_diff']`); its own kernel and solve no
longer produce reported values. Planes are meshed finely enough for C1 (T0022: 0.5–1 mm cells give 15.423 →
15.416 nH, and a direct solve at 1 mm fits in 16 GB).

## Alternatives considered
- (a) Report a cancellation-aware estimate of FastHenry's kernel error: cheapest, but the frozen contract treats
  `solver_tol` as a bound; E001's evidence could later be judged INVALID on that.
- (b) Keep FastHenry's kernel with worst-case bounds: E001 cannot pass; a larger budget needs a new experiment id.

## Consequences
E001's registered evidence standard is unchanged. L2 now shares closed-form kernels (exact mathematics, not
approximations) with L1; independence rests on E001 validating L2 against independent closed forms and on L2's
discretization (fine volume filaments, skin-resolved, finite meshed planes) differing from L1's (coarse cells, image
planes, Grover wires). D0002's licence decision still applies to FastHenry as used here.
