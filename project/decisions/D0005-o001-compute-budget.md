# D0005 — O001 compute budget: 400 burst-VM CPU-hours
Date: 2026-10-12 · Status: accepted · Decider: founder (founder session, 2026-10-12)

## Context
O001's objective sets `budget.cpu_hours: 60`, chosen at approval (2026-09-29) before the L2 reference's cost was known.
mfos tracks only USD, so the figure was never enforced. The measured costs on a GCP n2-highmem-32 (32 vCPU, 251 GB),
counted as user+sys CPU over all threads:
- the layout L2 at k_star (0.25 mm): 1.0-1.45 CPU-h per layout;
- at k_star+1 (0.125 mm): 8.7-9.3 CPU-h per layout, 35-39 GB.

The measurement campaign has already used roughly 150 VM CPU-hours, about $40: the T0067 spike, the C1 pre-check,
E001, the I0039 diagnostic, the T0075 convergence run (research/l2_layout_vm) and the strata pre-flight
(research/l2_layout_vm2). E002 needs about 150-200 more (design T0076; reviews T0096/T0097 flagged the 60 CPU-h
figure as already exceeded).

## Decision
O001's compute budget is **400 burst-VM CPU-hours, about $80-100 of VM time**. It is counted in VM accounting
(user+sys over all threads), cumulatively over the objective. Laptop runs are not counted.
`project/objectives/O001/objective.yaml` stays frozen, with its 60 CPU-h figure. This record supersedes that figure
for planning, sizing and registration (`cpu_hours_est`).

## Consequences
E002 may be sized up to the remaining envelope: about 250 CPU-h after the campaign, with margin kept for a repair
run. VM spend stays a founder-visible cost in the Google Cloud console; it is not part of O001's LLM budget. Any
further increase is a new decision.
