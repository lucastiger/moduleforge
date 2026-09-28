---
name: mf-conventions
description: ModuleForge engineering and physics conventions - units, coordinates, numerics, code layout, testing standard, licensing. Use whenever writing or reviewing ModuleForge code or physics.
user-invocable: false
---

# ModuleForge conventions

## Units and coordinates
- All internal quantities are SI and float64: m, A, V, H, Ω, K, W, s, Pa. Convert only at I/O
  boundaries with named helpers (`mm_to_m`, `m_to_mm`, `c_to_k`); never inline `* 1e-3`.
- Temperatures are kelvin internally; °C appears only in reports and customer-facing files.
- Right-handed coordinates: x–y is the substrate plane, z points up, z = 0 at the bottom of the
  baseplate. Layer stacks are listed bottom-up.
- Inductance is always reported with its frequency and port definition: `L_loop(f)` for the
  commutation loop DC+ → high-side switch → phase node → low-side switch → DC−, measured between
  the DC terminals with the phase node treated as specified by the experiment.
- Copper skin depth at 20 MHz ≈ 14.6 µm and at 100 MHz ≈ 6.5 µm; state explicitly whether a model
  is DC, quasi-static with skin/proximity effect, or full-wave.

## Numerics
- `jax.config.update("jax_enable_x64", True)` in any module using JAX.
- Every stochastic procedure takes an explicit seed argument; no global RNG state.
- Tolerances: algebraic identities rtol ≤ 1e-9; physical comparisons use tolerances set by the
  objective or experiment spec, never loosened to make a test pass.
- Hot paths are vectorized; no Python loops over mesh cells or filaments.

## Code layout (`src/moduleforge/`)
`geometry/` layout IR and stacks · `drc/` manufacturing rules · `physics/peec/`, `physics/thermal/`
fast (L1) models · `solvers/` adapters to reference tools (L2) · `generate/` layout generators ·
`optimize/` search · `io/` DXF/STEP/CSV/SPICE. Tests mirror the tree under `tests/unit/`.

## Testing standard for physics code
Each physics function gets at least: (1) an analytic or published-value check, (2) a limiting-case
check, (3) a symmetry/reciprocity or conservation check (e.g. mutual inductance matrix symmetric and
positive definite; steady-state heat in = heat out), (4) a units/scaling check (doubling all lengths
scales partial inductance by 2). Cite the source of every closed-form formula in a comment.

## Licensing
Runtime dependencies must be permissive (MIT, BSD, Apache-2.0, PSF, ISC; MPL-2.0 acceptable as an
unmodified dependency). GPL/AGPL code must never be vendored or imported. External reference tools
(e.g. FastHenry) are invoked as separate executables for internal research only; their status is
recorded in a decision record.
