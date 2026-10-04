"""Stand-in plumbing test of the E001 runner (T0063): run with `uv run python research/scripts/e001_t0063_standin.py ERR_H2 TOL_FACTOR ERR_H3`.

Replaces l2_solve (bypassing the not-yet-built moduleforge.solvers.l2) with the closed form x (1 + ERR_H2 h^2 + ERR_H3 h^3),
h = 1.5^-(k-1), meta with every required mesh_params key (size ~ the case L, so length_scaling doubles it), per-frequency
mesh_hash, and solver_tol = TOL_FACTOR x solver_tol_required. Runs main("smoke") and prints failed sanity checks and the
first metric (checks level = 0.0, review T0062). Not evidence; plumbing only.
"""
import hashlib
import json
import sys
import types
import numpy as np
sys.path.insert(0, "experiments/runners")
import e001_reference as R
fake = types.ModuleType("moduleforge.solvers")
fake.l2 = types.SimpleNamespace(MAX_REFINEMENT=5)
sys.modules["moduleforge.solvers"] = fake
ERR, TOLF, ERR3 = (float(x) for x in sys.argv[1:4])
def l2_solve(l2, case, freqs, k, sig):
    h = 1.5 ** -(k - 1)
    z = np.array([R.analytic_z(case, f, sig) for f in freqs]) * (1 + ERR * h**2 + ERR3 * h**3)
    scale = abs(np.imag(R.analytic_z(case, case["cmp_freqs"][0], sig)[0, 0]) / case["cmp_freqs"][0])
    mp = {key: scale * h for key in R.required_mesh_keys(case)}
    hsh = hashlib.sha256(f"{case['id']}{k}".encode()).hexdigest()
    return z, {"solver_tol": TOLF * R.solver_tol_required(case, sig, R.DEFAULT_CFG), "n_filaments": 10 * 4**k, "mesh_hash": [hsh] * len(freqs), "mesh_params": mp}
R.l2_solve = l2_solve
rc = R.main("smoke")
res = json.load(open("/tmp/e001-smoke/result.json"))
print("main ->", rc, "| failed sanity:", [s["name"] for s in res["sanity"] if not s["passed"]])
for k, v in list(res["metrics"].items())[:1]:
    print(k, v)
