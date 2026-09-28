---
name: thesis-review
description: Re-evaluate the ModuleForge thesis against accumulated technical and customer evidence.
disable-model-invocation: true
allowed-tools: Bash(uv run mfos *) Read Grep Glob Write
model: opus
effort: high
---

Read `project/charter.md` (the current thesis and its explicit assumptions), `project/claims/`,
the latest `EVIDENCE.md` of each objective, `project/customers/` notes, and
`project/memory/literature/INDEX.md`.

Write `docs/reports/thesis-review-<today>.md`:
1. Each thesis assumption → status (supported / weakened / refuted / untested) with the exact
   evidence files. Customer statements are quoted and attributed to the note they came from.
2. The strongest case AGAINST continuing, argued as a skeptical investor would.
3. What changed since the last review.
4. Recommended changes: objectives to add, kill, or re-prioritize; thesis wording changes.
Then summarize it to me in 10 lines. Recommendations are proposals; I decide.
