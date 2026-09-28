"""Run registered experiments reproducibly. No LLM is in this path.

Rules enforced here:
  * only `registered` specs whose content hash still matches may run;
  * runs happen in a clean detached checkout of main (so results cite a merged commit);
  * sealed-seed specs get a fresh unseen seed per run, recorded in the result;
  * a complete result for the same (spec_hash, commit, seed policy) is reused unless forced;
  * the runner must write result.json through mfos.evidence.ExperimentRun.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from typing import Optional

from . import models as m
from .gitops import GitOps
from .store import Store, now


def register(store: Store, eid: str, by: str = "founder") -> m.ExperimentSpec:
    draft = store.spec_path(eid, draft=True)
    src = draft if draft.exists() else store.spec_path(eid)
    spec = store.read_yaml(src, m.ExperimentSpec)
    spec.status = "registered"
    spec.registered_by = by
    spec.registered_at = now()
    spec.spec_hash = store.spec_hash(spec)
    store.write_yaml(store.spec_path(eid), spec)
    if draft.exists():
        draft.unlink()
    store.event("experiment_registered", id=eid, hash=spec.spec_hash, by=by)
    return spec


def _cached(store: Store, spec: m.ExperimentSpec, commit: str) -> Optional[m.ExperimentResult]:
    if spec.sealed_seed:
        return None  # every sealed run must use a new seed
    for r in reversed(store.results(spec.id)):
        if r.status == "complete" and r.provenance.git_commit == commit and r.provenance.spec_hash == spec.spec_hash:
            return r
    return None


def run(store: Store, eid: str, *, ref: Optional[str] = None, force: bool = False,
        here: bool = False) -> m.ExperimentResult:
    spec = store.spec(eid)
    if spec.status != "registered" or spec.spec_hash != store.spec_hash(spec):
        raise RuntimeError(f"{eid} is not a registered, unmodified spec; refusing to run")
    git = GitOps(store)
    if here:
        cwd = store.root
    else:
        cwd = git.detached_worktree(f"exp-{eid}", ref or git.main)
    commit = store.git("rev-parse", "HEAD", cwd=cwd)
    if not force and not here:
        hit = _cached(store, spec, commit)
        if hit:
            store.event("experiment_cached", id=eid, run=hit.run_id)
            git.remove_worktree(cwd)
            return hit
    run_id = f"{eid}-{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(2)}"
    run_dir = store.root / "experiments" / "results" / eid / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ,
           "MFOS_EXPERIMENT_ID": eid, "MFOS_RUN_ID": run_id, "MFOS_RUN_DIR": str(run_dir),
           "MFOS_SPEC_HASH": spec.spec_hash or "", "MFOS_SPEC_JSON": spec.model_dump_json(),
           "MFOS_ARTIFACT_STORE": str(store.mfos / "artifacts"),
           "PYTHONPATH": os.pathsep.join(filter(None, [str(cwd / "tools" / "mfos"), str(cwd / "src"),
                                                       os.environ.get("PYTHONPATH", "")]))}
    if spec.sealed_seed:
        env["MFOS_SEED"] = str(secrets.randbelow(2**31 - 1))
    store.event("experiment_started", id=eid, run=run_id, commit=commit)
    t0 = time.time()
    with open(run_dir / "runner.log", "w") as log:
        try:
            proc = subprocess.run(spec.runner, shell=True, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=spec.timeout_min * 60)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = -9
    res_path = run_dir / "result.json"
    if res_path.exists():
        res = m.ExperimentResult.model_validate_json(res_path.read_text())
    else:
        res = m.ExperimentResult(experiment_id=eid, run_id=run_id, status="error",
                                 provenance=m.Provenance(git_commit=commit, git_dirty=False, spec_hash=spec.spec_hash),
                                 notes=f"runner exit code {code}; no result.json written")
        store.write_json(res_path, res)
    if code != 0 and res.status == "complete":
        res.status = "error"
        res.notes += f"\nrunner exited with code {code} after writing a result; downgraded to error"
        store.write_json(res_path, res)
    (run_dir / "run.json").write_text(json.dumps({"exit_code": code, "seconds": round(time.time() - t0, 1),
                                                  "cwd_commit": commit}, indent=2))
    store.event("experiment_finished", id=eid, run=run_id, status=res.status, seconds=round(time.time() - t0, 1))
    if not here:
        git.remove_worktree(cwd)
    return res


def validate_draft(store: Store, eid: str) -> list[str]:
    """Static checks the orchestrator runs on a scientist's draft before asking for registration."""
    problems: list[str] = []
    p = store.spec_path(eid, draft=True)
    if not p.exists():
        return [f"draft {p} missing"]
    try:
        spec = store.read_yaml(p, m.ExperimentSpec)
    except Exception as e:  # schema violation
        return [f"schema: {e}"]
    if not spec.metrics:
        problems.append("no metrics declared")
    if not spec.sanity_checks:
        problems.append("no sanity checks declared (every experiment needs at least one)")
    obj = store.objective(spec.objective)
    needed = {c.metric.split(".", 1)[1] for c in obj.acceptance.pass_all + obj.acceptance.fail_any
              if c.metric.startswith(eid + ".")}
    missing = needed - {x.name for x in spec.metrics}
    if missing:
        problems.append(f"metrics required by acceptance criteria not declared: {sorted(missing)}")
    runner_file = spec.runner.split()[-1] if spec.runner else ""
    if runner_file.endswith(".py") and not (store.root / runner_file).exists():
        problems.append(f"runner script {runner_file} not found")
    return problems


def artifacts_gc(store: Store, keep_days: int = 60) -> int:
    root = store.mfos / "artifacts"
    if not root.exists():
        return 0
    cutoff, n = time.time() - keep_days * 86400, 0
    for p in root.glob("*/*"):
        if p.stat().st_atime < cutoff:
            p.unlink()
            n += 1
    shutil.rmtree(root / "tmp", ignore_errors=True)
    return n
