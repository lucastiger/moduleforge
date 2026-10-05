# D0004 — L2 rebuild: iterative solve under a rigorous a-posteriori bound; FastHenry optional
Date: 2026-10-04 · Status: accepted · Decider: founder (inbox I0031) · Amends: D0003

## Context
D0003 has the L2 port impedance come from a direct solve of the mesh system and keeps the pinned FastHenry (D0002)
for meshing "where convenient" and as a cross-check. The founder-approved spike T0067 (`research/diagnoses/T0067.md`,
review T0068) and its GCP benchmark (`research/spike_l2_results/`, n2-highmem-32, 2026-10-04) measured the
exact-kernel design at the sizes E001 needs: C1 at refinement level 4 has 134,484 unknowns and peaked at 16.0 GB
with the solve done iteratively. A dense LU of a system that size does not fit on this 17 GB machine, and neither
do the E002 layouts (T0068 finding 1). The spike solved with GMRES (block preconditioner, plane blocks applied by
FFT) and reported the a-posteriori bound |dZ| <= ||P(Mx)||^2 / r_min plus rounding. T0068 re-derived that bound and
checked it against a dense LU: the true error was inside the bound in 9 of 9 cases. On the VM every case reported
solver_tol <= 5.2e-11, against E001's registered budget of 1e-5.

## Decision
- **(i) Iterative solve with a rigorous bound.** Where a dense LU does not fit, the L2 solvers (T0070 onward, and
  the layout path) solve by GMRES. `meta['solver_tol']` is then the sum of the a-posteriori bound above, a rounding
  bound, and stated bounds (derived, not measured level-to-level changes) for kernel quadrature, proxy-filament
  truncation and the plane and wire-to-plane tables. Small systems keep the dense direct solve. Any compression
  of a coupling block counts its error bound in `solver_tol` the same way.
- **(ii) FastHenry optional.** It is no longer required for meshing or for the cross-check; `meta['fh_zc_rel_diff']`
  is optional. The layout path drops T0066's `binary_path`/`binary_sha256` assertions. Provenance is
  `tool_version` plus a sha256 of the solver source files, so a burst VM does not need FastHenry provisioned.

## Alternatives considered
- Confirm (i) only and keep FastHenry binary provenance in the layout meta — rejected: no reported value comes from
  FastHenry any more (D0003), so its binary hash would record a tool that produced nothing.
- Dense LU only — rejected: C1 level 4 and the E002 layouts would need a large-memory host for every solve and
  probably a re-registration of E001.

## Consequences
E001's registered evidence standard is unchanged: its contract accepts an iterative solve when `solver_tol` is a
forward-error bound, and the runner's `l2_solver_tolerance` check still holds it within 1e-5. The bound is only as
good as its derivation, so the L2 tests must show bound >= true error against a dense LU on cases small enough for
one. D0002's licence decision still applies wherever FastHenry is used.
