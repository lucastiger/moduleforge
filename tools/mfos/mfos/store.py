"""File-backed project state. The repository is the database.

Layout (all paths relative to the repo root):
  project/objectives/<OID>/objective.yaml   founder-owned, frozen after approval
  project/objectives/<OID>/state.yaml       orchestrator-owned
  project/objectives/<OID>/evaluations/*.json
  project/tasks/<TID>.yaml
  project/inbox/<IID>.yaml
  project/claims/<CID>.yaml
  project/events.jsonl                      append-only event log
  experiments/specs/<EID>.yaml              registered (immutable) specs
  experiments/drafts/<EID>.yaml             drafts written by the scientist
  experiments/results/<EID>/<RUN>/result.json
  .mfos/policy.toml                         operating policy (founder-owned; stdlib-parseable by hooks)
  .mfos/runs/<RUN>/                         agent run records (gitignored)
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Iterator, Optional, TypeVar

import yaml
from pydantic import BaseModel

from . import models as m

T = TypeVar("T", bound=BaseModel)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def find_root(start: Optional[Path] = None) -> Path:
    env = os.environ.get("MFOS_ROOT")
    if env:
        return Path(env).resolve()
    p = (start or Path.cwd()).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".mfos" / "policy.toml").exists():
            return cand
    raise FileNotFoundError("No .mfos/policy.toml found above the current directory")


def canonical_hash(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Optional[Path] = None):
        self.root = find_root(root)
        self.project = self.root / "project"
        self.mfos = self.root / ".mfos"
        self.policy = self._load_policy()
        g = self.policy.get("git", {})
        name, email = g.get("identity_name", "mfos-bot"), g.get("identity_email", "mfos-bot@users.noreply.github.com")
        # The orchestrator always commits under its own identity, independent of machine config.
        self.git_env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
                        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
        fname, femail = g.get("founder_name", "founder"), g.get("founder_email", "founder@users.noreply.github.com")
        # Founder-authored files (objectives, charter, decisions) are committed under the founder's identity.
        self.founder_env = {**os.environ, "GIT_AUTHOR_NAME": fname, "GIT_AUTHOR_EMAIL": femail,
                            "GIT_COMMITTER_NAME": fname, "GIT_COMMITTER_EMAIL": femail}

    # ------------------------------------------------------------------ generic IO
    def _load_policy(self) -> dict[str, Any]:
        with open(self.root / ".mfos" / "policy.toml", "rb") as f:
            return tomllib.load(f)

    def read_yaml(self, path: Path, model: type[T]) -> T:
        return model.model_validate(yaml.safe_load(path.read_text()) or {})

    def write_yaml(self, path: Path, obj: BaseModel) -> None:
        data = obj.model_dump(mode="json", exclude_none=False)
        _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    def write_json(self, path: Path, obj: Any) -> None:
        data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
        _atomic_write(path, json.dumps(data, indent=2, sort_keys=False, default=str) + "\n")

    @contextlib.contextmanager
    def lock(self, name: str = "state") -> Iterator[None]:
        self.mfos.mkdir(exist_ok=True)
        with open(self.mfos / f"{name}.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ------------------------------------------------------------------ events
    def event(self, event: str, /, actor: str = "orchestrator", **data: Any) -> None:
        rec = {"ts": now(), "event": event, "actor": actor, **data}
        path = self.project / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        path = self.project / "events.jsonl"
        if not path.exists():
            return []
        lines = path.read_text().splitlines()[-limit:]
        return [json.loads(x) for x in lines if x.strip()]

    # ------------------------------------------------------------------ ids
    def next_id(self, prefix: str, directory: Path, width: int = 4) -> str:
        directory.mkdir(parents=True, exist_ok=True)
        pat = re.compile(rf"^{prefix}(\d+)")
        nums = [int(mt.group(1)) for p in directory.iterdir() if (mt := pat.match(p.name))]
        return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"

    # ------------------------------------------------------------------ objectives
    def objective_dir(self, oid: str) -> Path:
        return self.project / "objectives" / oid

    def objective(self, oid: str) -> m.Objective:
        return self.read_yaml(self.objective_dir(oid) / "objective.yaml", m.Objective)

    def objective_state(self, oid: str) -> m.ObjectiveState:
        p = self.objective_dir(oid) / "state.yaml"
        return self.read_yaml(p, m.ObjectiveState) if p.exists() else m.ObjectiveState()

    def save_objective_state(self, oid: str, st: m.ObjectiveState) -> None:
        self.write_yaml(self.objective_dir(oid) / "state.yaml", st)

    def objective_ids(self) -> list[str]:
        d = self.project / "objectives"
        return sorted(p.name for p in d.iterdir() if (p / "objective.yaml").exists()) if d.exists() else []

    def criteria_hash(self, obj: m.Objective) -> str:
        return canonical_hash(obj.acceptance.model_dump(mode="json"))

    # ------------------------------------------------------------------ tasks
    def task_path(self, tid: str) -> Path:
        return self.project / "tasks" / f"{tid}.yaml"

    def task(self, tid: str) -> m.Task:
        return self.read_yaml(self.task_path(tid), m.Task)

    def save_task(self, t: m.Task) -> None:
        self.write_yaml(self.task_path(t.id), t)

    def tasks(self, objective: Optional[str] = None) -> list[m.Task]:
        d = self.project / "tasks"
        if not d.exists():
            return []
        out = [self.read_yaml(p, m.Task) for p in sorted(d.glob("T*.yaml"))]
        return [t for t in out if objective is None or t.objective == objective]

    def new_task_id(self) -> str:
        return self.next_id("T", self.project / "tasks")

    # ------------------------------------------------------------------ experiments
    def spec_path(self, eid: str, draft: bool = False) -> Path:
        return self.root / "experiments" / ("drafts" if draft else "specs") / f"{eid}.yaml"

    def spec(self, eid: str) -> m.ExperimentSpec:
        return self.read_yaml(self.spec_path(eid), m.ExperimentSpec)

    def spec_hash(self, spec: m.ExperimentSpec) -> str:
        exclude = {"status", "registered_by", "registered_at", "spec_hash"}
        if not spec.runner_files:  # specs registered before runner freezing keep their original hash
            exclude.add("runner_files")
        return canonical_hash(spec.model_dump(mode="json", exclude=exclude))

    def results(self, eid: str) -> list[m.ExperimentResult]:
        d = self.root / "experiments" / "results" / eid
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*/result.json")):
            if not (p.parent / "run.json").exists():  # `mfos exp run` has not finalized it (exit-code check) yet
                continue
            try:
                out.append(m.ExperimentResult.model_validate_json(p.read_text()))
            except Exception:  # corrupted results are ignored, never trusted
                continue
        return out

    # ------------------------------------------------------------------ inbox / claims
    def inbox(self, status: Optional[str] = "open") -> list[m.InboxItem]:
        d = self.project / "inbox"
        if not d.exists():
            return []
        items = [self.read_yaml(p, m.InboxItem) for p in sorted(d.glob("I*.yaml"))]
        return [i for i in items if status is None or i.status == status]

    def add_inbox(self, **kw: Any) -> m.InboxItem:
        iid = self.next_id("I", self.project / "inbox")
        item = m.InboxItem(id=iid, created_at=now(), **kw)
        self.write_yaml(self.project / "inbox" / f"{iid}.yaml", item)
        self.event("inbox_opened", id=iid, kind=item.kind, subject=item.subject)
        return item

    def save_inbox(self, item: m.InboxItem) -> None:
        self.write_yaml(self.project / "inbox" / f"{item.id}.yaml", item)

    def add_claim(self, **kw: Any) -> m.Claim:
        cid = self.next_id("C", self.project / "claims", width=3)
        c = m.Claim(id=cid, created_at=now(), **kw)
        self.write_yaml(self.project / "claims" / f"{cid}.yaml", c)
        self.event("claim_recorded", id=cid, status=c.status)
        return c

    # ------------------------------------------------------------------ git helpers
    def git(self, *args: str, cwd: Optional[Path] = None, check: bool = True, as_founder: bool = False) -> str:
        env = self.founder_env if as_founder else self.git_env
        r = subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def stop_requested(self) -> bool:
        return (self.project / "STOP").exists() or (self.mfos / "STOP").exists()
