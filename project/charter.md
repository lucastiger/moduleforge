# ModuleForge charter (founder-owned)

## Thesis (current)
Power-module makers and automotive OEMs re-lay out wire-bonded SiC/IGBT half-bridge and six-pack
modules whenever the die generation, die supplier, or die count changes inside an existing housing.
Each derivative costs several design–manufacture–test iterations. A physics-first compiler that takes
the reference layout, housing, stack, design rules, and new dies, and returns manufacturable layouts
with lower loop inductance, better current sharing and gate-loop symmetry, and bounded junction
temperature — together with customer-runnable verification decks — removes iterations and weeks.

## Assumptions (each must be tested by an objective; update statuses via /thesis-review)
| id | assumption | tested by | status |
|---|---|---|---|
| A-T1 | A fast L1 electromagnetic model ranks layouts faithfully enough to drive search | O001 | untested |
| A-T2 | A fast L1 thermal model is faithful enough for Tj max and spread | O002 | untested |
| A-T3 | Real derivative problems have ≥20% loop-inductance or ≥50% current-mismatch headroom at ≤ +2 K Tj | O003 | untested |
| A-T4 | Customers will accept software-generated layouts verified in their own Q3D/Icepak flow | customer interviews | untested |
| A-T5 | Paid "derivative layout sprints" can start within 90 days | customer interviews | untested |
| A-T6 | No incumbent or academic tool already delivers this commercially | scout research | partially tested |

## Constraints
Solo founder, AI-leveraged; no wet or fab lab; cash-constrained compute; customer data is confidential
and may require on-prem execution later.

## Non-goals (first 90 days)
Board-level power stages, data-center power, full-wave RF, reliability lifetime prediction beyond
proxies, a GUI.

## Kill criteria
Day 30: O001 FAIL with no credible fix path. Day 45: no customer willing to share a reference layout
under NDA. Day 60: O003 shows < 10% headroom on public benchmarks. Day 90: no paid or LOI-backed sprint.
