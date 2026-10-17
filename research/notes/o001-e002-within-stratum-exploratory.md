# O001 / E002 — within-stratum ranking: an exploratory post-hoc analysis

**Status: exploratory, post hoc, not pre-registered.** It was written on 2026-10-16, after evaluation EV-O001-01,
on the sealed E002 sample that evaluation had already seen. It does not change the registered verdict and is not
confirmatory evidence. A confirmatory test needs a pre-registered experiment on fresh sealed seeds.

## Why
The blinded reviews of EV-O001-01 (T0106 and T0107, in `project/reviews/EV-O001-01/`) showed that E002's pooled
metrics (A2, A3, A5) are dominated by the (family, dies-per-switch) strata. A predictor that knows only the stratum
mean would pass them. Derivative re-layout ranks layouts *within* a fixed family and die count, so the question is
whether L1 also orders layouts within a stratum.

## Method
`research/scripts/e002_within_stratum_exploratory.py` reads run `E002-20261016T054426-b69a`: per-layout L1 at
20 MHz (`e002_rows.json`) and the Richardson-extrapolated reference L2_inf (`e002_reference.json`), for 90 layouts
in 15 strata of 6. The main statistic is the Spearman correlation of log L1 and log L2_inf after removing each
stratum's mean, which pools the within-stratum ordering of all strata. Its 95 % interval comes from a percentile
bootstrap (2000 resamples, seed 20261017 fixed before the first run) that resamples layouts within each stratum.
Per-stratum Spearman values (n = 6 each) and the stratum-mean-only baseline are reported for context. Raw output:
`research/notes/o001-e002-within-stratum-exploratory.json`.

## Results
| quantity | value |
|---|---|
| pooled Spearman, L1 vs L2_inf (equals the registered spearman_rho_Lloop) | 0.996 |
| stratum-mean-only predictor, pooled Spearman | 0.972 |
| **within-stratum Spearman (demeaned log L)** | **0.977, 95 % CI [0.940, 0.983]** |
| per-stratum Spearman, size-weighted mean (n = 6 per stratum) | 0.924 (min 0.771) |
| within-stratum CV of L2 | 0.018-0.094 |

## Reading
The reviewers are right that the pooled metrics cannot tell stratum-level from layout-level ranking: the
stratum-only baseline reaches 0.972. On this sample, though, L1 also orders layouts within their stratum closely
(0.977). That is better than the reviewers' inferred value (about 0.89 from a pooled-rho noise model). Per-stratum
values with n = 6 are noisy, and the lowest (0.771, interleaved:3 and side_by_side:5) are strata whose L2 spread is
small (CV 2-5 %).

## Limits
- Post hoc, on already-evaluated sealed data, so it is hypothesis-generating only.
- One DBC Al2O3 0.38 mm stack and one 70 x 40 mm housing.
- The reference is solvers.l2_layout, validated by E002's in-run C1 check and its unit tests rather than by E001.
- A pre-registered within-stratum criterion on fresh sealed seeds is the natural first experiment of the
  derivative-re-layout objective.
