"""Code-path harness for experiments/runners/e002_ranking.py (T0076): full (non-smoke) mode at n = 30 under a DEV seed
(555, never sealed) with run_tasks replaced by synthetic L2 records on a contracting ladder (0.61), so every metric and
sanity branch runs in minutes. Tests code, not physics; not evidence. Run: uv run python research/scripts/e002_runner_harness.py
"""
import json, os, pickle, sys, yaml
from pathlib import Path
sys.path.insert(0, "experiments/runners")
spec = yaml.safe_load(open("experiments/drafts/E002.yaml"))
spec["config"].update(n_layouts=30, l1_hmax_fine_m=[2.0e-3, 1.0e-3])
os.environ["MFOS_SPEC_JSON"] = json.dumps(spec); os.environ["MFOS_SEED"] = "555"  # dev seed, harness only
import e002_ranking as E
from moduleforge.solvers import l2_layout
from moduleforge.physics.peec import loop_inductance as l1
sha = l2_layout.source_sha256()
def fake(tasks, work, jobs, threads):
    out = {}
    for t in tasks:
        if t["kind"] == "c1":
            out["C1"] = dict(L_H=[1.44e-8]*3, analytic_H=[1.4399e-8]*3, gmres_info=[[0]], tool_version="x", wall_s=1, peak_rss_gb=1, cpu_s=1)
            continue
        lay = pickle.loads(Path(t["layout"]).read_bytes()); k = t["refinement"]
        base = l1(lay, t["freqs"]).L_H * (1.10 + 0.01 * (lay.family == "u_shaped"))
        L = base * (1 + 0.03 * 0.61 ** k)
        out[t["task_id"]] = dict(L_H=list(L), R_ohm=[0.03]*len(L), gmres_flags=[0], gmres_iters=[200], solver_tol_rel_L_max=2e-5 if k < 2 else 1.4e-3,
            solver_tol=2e-5, n_unknowns=1, tool="t", tool_version=l2_layout.TOOL_VERSION, source_sha256=sha, fingerprint=t["fingerprint"],
            on_lattice=True, cpu_s=3600.0, wall_s=1.0, peak_rss_gb=1.0)
    return out
E.run_tasks = fake
orig = E.ExperimentRun
E.ExperimentRun = lambda experiment_id=None, run_dir=None, **kw: orig(experiment_id=experiment_id, run_dir="/tmp/e002-harness", **kw)
print("rc", E.main(False))
r = json.load(open("/tmp/e002-harness/result.json"))
print(r["status"], r["notes"][-600:])
for s in r["sanity"]: print("S", s["name"], s["passed"], s["value"], s["detail"][:160])
for k, v in r["metrics"].items(): print("M", k, round(v["value"], 4), v["ci"] and [round(x, 4) for x in v["ci"]], v["n"])
declared = {m["name"] for m in spec["metrics"]}; print("declared-not-reported", sorted(declared - set(r["metrics"]))); print("reported-not-declared", sorted(set(r["metrics"]) - declared))
