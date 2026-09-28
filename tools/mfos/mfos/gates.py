"""Deterministic checks. An agent saying "tests pass" counts for nothing; these do.

Gate tiers (policy.gates):
  fast  run on every task before it may leave `verify` (seconds–minutes)
  full  run in CI on every PR and nightly (may include slow numerical regressions)
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import models as m
from .store import Store


@dataclass
class CheckResult:
    name: str
    ok: bool
    output: str


def run_cmd(cmd: str, cwd: Path, timeout_s: int = 900) -> CheckResult:
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
        out = (r.stdout + "\n" + r.stderr)[-6000:]
        return CheckResult(cmd, r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return CheckResult(cmd, False, f"TIMEOUT after {timeout_s}s")


def run_gate(store: Store, cwd: Path, tier: str = "fast") -> list[CheckResult]:
    cmds = store.policy.get("gates", {}).get(tier, [])
    return [run_cmd(c, cwd) for c in cmds]


def run_dod(store: Store, t: m.Task, cwd: Path, include_gate: bool = True) -> list[CheckResult]:
    results: list[CheckResult] = []
    for d in t.definition_of_done:
        if d.cmd:
            results.append(run_cmd(d.cmd, cwd, d.timeout_s))
        if d.exists:
            results.append(CheckResult(f"exists:{d.exists}", (cwd / d.exists).exists(), ""))
    for dl in t.deliverables:
        if not any(ch in dl for ch in "*?[") and not dl.endswith("/"):
            results.append(CheckResult(f"deliverable:{dl}", (cwd / dl).exists(), ""))
    if include_gate:
        results.extend(run_gate(store, cwd, "fast"))
    return results


def summarize(results: list[CheckResult]) -> tuple[bool, str]:
    ok = all(r.ok for r in results)
    failed = [r for r in results if not r.ok]
    text = "\n".join(f"FAIL {r.name}\n{r.output[-1500:]}" for r in failed)
    return ok, text
