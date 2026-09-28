"""The only sanctioned way for an experiment to produce evidence.

Runner scripts do:

    from mfos.evidence import ExperimentRun
    with ExperimentRun() as run:                 # reads MFOS_* env set by `mfos exp run`
        seed = run.seed                          # sealed seed if the spec requests one
        ...
        run.sanity("l2_vs_analytic_two_bar", passed=err < 0.02, value=err, threshold=0.02)
        run.metric("spearman_rho_Lloop", rho, ci=(lo, hi), n=len(x))
        run.artifact("layouts.parquet", path)

Provenance (commit, dirty flag, lockfile hash, versions, host, times) is captured
automatically and cannot be edited by the runner. If the block raises, the result
is written with status "error". If any declared sanity check is missing or failed,
the evaluator will refuse the evidence.
"""
from __future__ import annotations

import datetime as dt
import importlib.metadata as md
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from . import models as m
from .store import file_sha256


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


class ExperimentRun:
    def __init__(self, experiment_id: Optional[str] = None, run_dir: Optional[str] = None,
                 config: Optional[dict[str, Any]] = None, tools: Optional[dict[str, str]] = None):
        self.experiment_id = experiment_id or os.environ.get("MFOS_EXPERIMENT_ID", "E_ADHOC")
        self.run_id = os.environ.get("MFOS_RUN_ID", f"{self.experiment_id}-adhoc")
        self.run_dir = Path(run_dir or os.environ.get("MFOS_RUN_DIR", f".mfos/adhoc/{self.run_id}"))
        self.run_dir.mkdir(parents=True, exist_ok=True)
        spec_env = os.environ.get("MFOS_SPEC_JSON")
        self.spec: dict[str, Any] = json.loads(spec_env) if spec_env else {}
        self.config: dict[str, Any] = {**self.spec.get("config", {}), **(config or {})}
        seed = os.environ.get("MFOS_SEED")
        self.seed: Optional[int] = int(seed) if seed else self.config.get("seed")
        self.tools = tools or {}
        self._metrics: dict[str, m.MetricValue] = {}
        self._sanity: list[m.SanityResult] = []
        self._artifacts: list[m.ArtifactRef] = []
        self._started = _now()
        self.notes = ""

    # ---------------------------------------------------------------- recording
    def metric(self, name: str, value: float, ci: Optional[tuple[float, float]] = None,
               n: Optional[int] = None, unit: str = "", level: float = 0.95) -> None:
        self._metrics[name] = m.MetricValue(value=float(value), ci=(float(ci[0]), float(ci[1])) if ci else None,
                                            n=n, unit=unit, level=level)

    def sanity(self, name: str, passed: bool, value: Optional[float] = None,
               threshold: Optional[float] = None, detail: str = "") -> None:
        self._sanity.append(m.SanityResult(name=name, passed=bool(passed), value=value,
                                           threshold=threshold, detail=detail))

    def artifact(self, name: str, path: str | Path) -> m.ArtifactRef:
        p = Path(path)
        digest = file_sha256(p)
        store_root = Path(os.environ.get("MFOS_ARTIFACT_STORE", ".mfos/artifacts"))
        dest = store_root / digest[:2] / digest
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(p, dest)
        ref = m.ArtifactRef(name=name, sha256=digest, bytes=p.stat().st_size)
        self._artifacts.append(ref)
        return ref

    # ---------------------------------------------------------------- provenance
    def _provenance(self) -> m.Provenance:
        lock = Path("uv.lock")
        pkgs = {}
        for name in ("numpy", "scipy", "jax", "pydantic", "shapely"):
            try:
                pkgs[name] = md.version(name)
            except md.PackageNotFoundError:
                pass
        return m.Provenance(
            git_commit=_git("rev-parse", "HEAD") or "unknown",
            git_dirty=bool(_git("status", "--porcelain", "--untracked-files=no")),
            git_branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
            spec_hash=os.environ.get("MFOS_SPEC_HASH"),
            lock_hash=file_sha256(lock) if lock.exists() else None,
            python=sys.version.split()[0], platform=platform.platform(), host=socket.gethostname(),
            packages=pkgs, tools=self.tools, started=self._started, finished=_now(),
        )

    def _write(self, status: str) -> Path:
        res = m.ExperimentResult(
            experiment_id=self.experiment_id, run_id=self.run_id, status=status,  # type: ignore[arg-type]
            seed=self.seed, config=self.config, provenance=self._provenance(),
            metrics=self._metrics, sanity=self._sanity, artifacts=self._artifacts, notes=self.notes,
        )
        out = self.run_dir / "result.json"
        tmp = out.with_suffix(".tmp")
        tmp.write_text(res.model_dump_json(indent=2))
        os.replace(tmp, out)
        return out

    def __enter__(self) -> "ExperimentRun":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.notes += "\n" + "".join(traceback.format_exception(exc_type, exc, tb))[-4000:]
            self._write("error")
            return False
        declared = {s["name"] for s in self.spec.get("sanity_checks", [])}
        reported = {s.name for s in self._sanity}
        status = "complete" if declared <= reported else "invalid"
        if status == "invalid":
            self.notes += f"\nMissing declared sanity checks: {sorted(declared - reported)}"
        self._write(status)
        return False
