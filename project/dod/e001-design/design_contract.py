"""E001 design DoD: smoke coverage, live config keys, independent self-checks, L2 contract.

Findings of reviews T0029/T0030 of T0020: --smoke skipped 2 of 7 geometry classes; `tol_independent` and `cases`
did nothing; no self-check exercised the 3-D image code, the Wheeler recession or the tied-branch formula;
the L2 contract allowed a different mesh per frequency and never reported the solver tolerance; the license
table dated FastHenry2's notice to 1996 (the header says 1992). Review T0052 of T0041: the contract must also fix a
constant refinement ratio, or the remaining-error estimate does not hold. Reviews T0055/T0056: the one-mesh and
constant-ratio checks must not rest on single self-reported scalars (meta['mesh_params'], meta['mesh_hash']).
"""
import json
import re
import subprocess
import sys

import yaml

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

problems = []
cases = R.build_cases(dict(R.DEFAULT_CFG))
classes = {c["cls"] for c in cases}
smoke = {c["cls"] for c in cases if c["id"] in R.DEFAULT_CFG["smoke_cases"]}
if smoke != classes:
    problems.append(f"--smoke misses geometry classes {sorted(classes - smoke)}")

src = open("experiments/runners/e001_reference.py").read()
draft = yaml.safe_load(open("experiments/drafts/E001.yaml"))
keys = set(draft.get("config") or {})
if keys != set(R.DEFAULT_CFG):
    problems.append(f"draft config keys differ from DEFAULT_CFG: {sorted(keys ^ set(R.DEFAULT_CFG))}")
dead = sorted(k for k in keys if not re.search(r"""cfg\[\s*["']%s["']\s*\]|cfg\.get\(\s*["']%s["']""" % (k, k), src))
if dead:
    problems.append(f"config keys the runner never reads: {dead}")
if "solver_tol" not in src:
    problems.append("the runner never checks the solver tolerance L2 reports (meta['solver_tol'])")

r = subprocess.run([sys.executable, "experiments/runners/e001_reference.py", "--analytic-only"],
                   capture_output=True, text=True)
if r.returncode != 0:
    problems.append(f"--analytic-only exited {r.returncode}: {(r.stdout + r.stderr)[-300:]}")
else:
    res = json.load(open("/tmp/e001-analytic/result.json"))
    sanity = {x["name"]: x["passed"] for x in res.get("sanity", [])}
    for need in ("image_plane_independent", "wheeler_recession_independent", "tied_branch_independent"):
        if sanity.get(need) is not True:
            problems.append(f"analytic self-check {need} is missing or failing")

note = open("research/notes/o001-l2-reference.md").read()
contract = note.split("## 3.", 1)[-1].split("## 4.", 1)[0]
if not re.search(r"\b(same|one|single) mesh\b", contract, re.I):
    problems.append("the L2 contract (note section 3) does not fix one mesh per refinement level for all frequencies")
if not re.search(r"refinement ratio|constant ratio|fixed ratio", contract, re.I):
    problems.append("the L2 contract does not fix a constant refinement ratio between levels (review T0052)")
for key, why in (("mesh_params", "every refined discretization parameter, so the runner can verify the common ratio"),
                 ("mesh_hash", "the mesh identity per frequency, so the runner can verify one mesh per solve")):
    if key not in contract or key not in src:
        problems.append(f"contract and runner must use meta['{key}'] ({why}; review T0056 of T0041)")
if "solver_tol" not in contract:
    problems.append("the L2 contract does not require meta['solver_tol']")
if "1992" not in note:
    problems.append("the license table still dates FastHenry2's MIT notice to 1996 (the header says 1992)")
assert not problems, "\n  - ".join(["E001 design problems:", *problems])
print("E001 design contract checks pass")
