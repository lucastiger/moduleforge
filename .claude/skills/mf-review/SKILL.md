---
name: mf-review
description: Adversarial review checklists by lens (general, physics, numerics, statistics) and evidence-provenance checks. Use when acting as a critic.
user-invocable: false
---

# Adversarial review

Always: restate the claim and its implied scope; name the three likeliest failure routes; perform
independent checks; report findings with severity and evidence. Test the tests: a test that
recomputes the implementation's own formula proves nothing.

## general / software
Behavior vs implementation tests · edge cases (empty, degenerate geometry, zero current) · swallowed
exceptions · tolerances loose enough to pass wrong answers · changes outside the stated scope ·
deleted or weakened tests · hidden global state · performance regressions in hot paths.

## physics
Units and dimensional consistency · sign/orientation conventions · boundary conditions · limiting
cases (thin wire, widely separated conductors → dipole-like mutual coupling, DC vs high frequency,
skin depth vs copper thickness) · reciprocity (M_ij = M_ji) and passivity (inductance matrix positive
definite; resistances non-negative) · complete current return paths including baseplate and
eddy/image currents · bond-wire models and their validity ranges · thermal: energy balance, boundary
conditions, temperature-dependent properties.

## numerics
Convergence under refinement (show the numbers) · discretization dependence of rankings, not only of
values · conditioning of linear solves · float32 vs float64 · seed sensitivity · agreement with an
independent method on a case neither was tuned on.

## statistics
Sample size and the width of the intervals · representativeness and diversity of the sample ·
leakage between development and evaluation data · number of evaluations performed (forking paths) ·
appropriateness of the CI method for n · whether the metric matches the decision it supports
(ranking vs absolute accuracy vs top-k selection) · pre-registration respected.

## evidence provenance (for evaluation reviews)
Result commits are on main and clean · spec hashes match registered specs · seeds recorded and
sealed where required · sanity checks are real (could have failed) · artifacts exist · evaluator
verdict reproduces from the result files.
