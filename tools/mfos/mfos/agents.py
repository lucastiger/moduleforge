"""Run one agent session through Claude Code's headless mode.

Why the CLI (`claude -p`) and not the Python Agent SDK: the CLI is the same agent
loop, reads the same .claude/ configuration you use interactively, works with either
your Claude login or an API key, isolates every run in its own process, and gives us
--agent, --json-schema, --max-budget-usd, --session-id/--resume and
--permission-prompts none. See docs/ARCHITECTURE.md section 3.

Run records live in .mfos/runs/<run_id>/ :
  record.json   written at dispatch, updated at completion (source of recovery)
  stdout.json   the CLI's final JSON (result, structured_output, cost, session id)
  stderr.log
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import models as m
from .store import Store, now

# Environment variables that must never reach an agent: agents cannot push, merge,
# or act on GitHub. Only the orchestrator holds credentials.
_SCRUB = ("GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR", "SSH_AUTH_SOCK", "MFOS_BOT_TOKEN")


@dataclass
class RunRecord:
    run_id: str
    task_id: str
    role: str
    session_id: str
    cwd: str
    started: str
    status: str = "running"  # running | completed | error | interrupted | timeout
    pid: Optional[int] = None
    resumed_from: Optional[str] = None
    finished: Optional[str] = None
    cost_usd: float = 0.0
    num_turns: int = 0
    is_error: bool = False
    subtype: str = ""
    structured_output: Optional[dict[str, Any]] = None
    result_text: str = ""
    deadline: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def report_from_text(text: str) -> Optional[dict[str, Any]]:
    """The final report when the CLI returned it only as text (no `structured_output`).

    Accepted only when the whole message is one JSON object, bare or in a single ```json fence;
    JSON quoted inside prose is never taken as the report. Callers still validate it against the
    role's schema. An agent whose `tools:` allow-list omits StructuredOutput never sees the schema
    and ends up here (O000 canary, 2026-09-28; `mfos doctor` now checks the allow-lists).
    """
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", body, re.S)
    if fenced:
        body = fenced.group(1)
    try:
        obj = json.loads(body)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


class AgentRunner:
    def __init__(self, store: Store):
        self.s = store
        self.runs_dir = store.mfos / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.claude = shlex.split(os.environ.get("MFOS_CLAUDE_BIN", store.policy.get("claude_bin", "claude")))

    # ------------------------------------------------------------------ records
    def _rec_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "record.json"

    def save(self, rec: RunRecord) -> None:
        p = self._rec_path(rec.run_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec.__dict__, indent=2, default=str))
        os.replace(tmp, p)

    def load(self, run_id: str) -> RunRecord:
        return RunRecord(**json.loads(self._rec_path(run_id).read_text()))

    def extend_deadlines(self, seconds: float) -> int:
        """Shift running deadlines after the machine slept, so a closed laptop lid is not a timeout."""
        n = 0
        for rec in self.active():
            rec.deadline += seconds
            self.save(rec)
            n += 1
        return n

    def active(self) -> list[RunRecord]:
        out = []
        for p in self.runs_dir.glob("*/record.json"):
            rec = RunRecord(**json.loads(p.read_text()))
            if rec.status == "running":
                out.append(rec)
        return out

    # ------------------------------------------------------------------ dispatch
    def start(self, *, task: m.Task, role: str, cwd: Path, packet_rel: str,
              schema: dict[str, Any], budget_usd: float, max_turns: int,
              model: Optional[str] = None, resume_session: Optional[str] = None,
              settings_file: Optional[Path] = None, wall_minutes: Optional[int] = None) -> RunRecord:
        pol = self.s.policy
        run_id = f"{task.id}-{role}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:4]}"
        session_id = resume_session or str(uuid.uuid4())
        prompt = (
            f"You are the `{role}` agent working on {task.id} ({task.objective}). "
            f"Your complete instructions are in the task packet at `{packet_rel}`. Read it first and follow it. "
            "Finish by returning the final report as JSON that matches the required schema."
        )
        if resume_session:
            prompt = ("Your previous run on this task was interrupted before it finished. Re-check the current state "
                      f"of the working tree against the task packet `{packet_rel}`, then continue and finish. " + prompt)
        mode = pol.get("permission_modes", {}).get(role, "dontAsk")
        cmd = [*self.claude, "-p", prompt, "--agent", role, "--output-format", "json",
               "--json-schema", json.dumps(schema), "--max-turns", str(max_turns),
               "--max-budget-usd", f"{budget_usd:.2f}", "--permission-mode", mode,
               "--permission-prompts", "none"]
        cmd += ["--resume", session_id] if resume_session else ["--session-id", session_id]
        if model:
            cmd += ["--model", model]
        if settings_file:
            cmd += ["--settings", str(settings_file)]
        rdir = self.runs_dir / run_id
        rdir.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        env.update({
            "MFOS_ROLE": role, "MFOS_TASK_ID": task.id, "MFOS_RUN_ID": run_id,
            "MFOS_OBJECTIVE": task.objective, "MFOS_ROOT_MAIN": str(self.s.root),
            "MFOS_APPROVED_PROTECTED": "1" if task.protected_approved else "0",
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": str(30 * 60 * 1000),
        })
        dod = cwd / packet_rel.replace(".md", ".dod.json")
        if dod.exists():
            env["MFOS_DOD_FILE"] = str(dod)
        # Hooks run `python3`; put this interpreter's directory first so they get Python >= 3.11 (tomllib)
        # even under launchd or on macOS, whose /usr/bin/python3 is 3.9 and would make the guard fail closed.
        env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")])
        env.pop("MFOS_ROOT", None)  # hooks must resolve the worktree, not the main checkout
        with open(rdir / "stdout.json", "w") as out, open(rdir / "stderr.log", "w") as err:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, env=env, start_new_session=True)
        wall = wall_minutes or pol.get("limits", {}).get("run_wall_minutes", 90)
        rec = RunRecord(run_id=run_id, task_id=task.id, role=role, session_id=session_id, cwd=str(cwd),
                        started=now(), pid=proc.pid, resumed_from=resume_session,
                        deadline=time.time() + 60 * wall)
        self.save(rec)
        self.s.event("run_started", run=run_id, task=task.id, role=role, session=session_id)
        return rec

    # ------------------------------------------------------------------ polling
    @staticmethod
    def _alive(pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        # reap if it is our zombie child
        try:
            wpid, _ = os.waitpid(pid, os.WNOHANG)
            return wpid == 0
        except ChildProcessError:
            return True

    def poll(self, rec: RunRecord) -> RunRecord:
        """Advance a running record. Safe to call after an orchestrator restart."""
        if rec.status != "running":
            return rec
        if self._alive(rec.pid):
            if time.time() > rec.deadline:
                self._kill(rec.pid)
                rec.status, rec.finished = "timeout", now()
                self.save(rec)
                self.s.event("run_timeout", run=rec.run_id)
            return rec
        out = self.runs_dir / rec.run_id / "stdout.json"
        try:
            data = json.loads(out.read_text())
        except Exception:
            rec.status, rec.finished = "interrupted", now()
            self.save(rec)
            self.s.event("run_interrupted", run=rec.run_id)
            return rec
        rec.finished = now()
        rec.cost_usd = float(data.get("total_cost_usd") or 0.0)
        rec.num_turns = int(data.get("num_turns") or 0)
        rec.is_error = bool(data.get("is_error"))
        rec.subtype = str(data.get("subtype", ""))
        rec.structured_output = data.get("structured_output")
        if rec.structured_output is None:
            rec.structured_output = report_from_text(str(data.get("result") or ""))
            rec.extra["report_source"] = "result_text" if rec.structured_output is not None else "missing"
        rec.result_text = str(data.get("result") or "")[-4000:]
        rec.session_id = data.get("session_id", rec.session_id)
        rec.status = "error" if rec.is_error or rec.subtype.startswith("error") else "completed"
        self.save(rec)
        self.s.event("run_finished", run=rec.run_id, status=rec.status, cost=rec.cost_usd, subtype=rec.subtype,
                     report=rec.extra.get("report_source", "structured_output"))
        return rec

    @staticmethod
    def _kill(pid: Optional[int]) -> None:
        if not pid:
            return
        # macOS answers EPERM, not ESRCH, when the group is left with only the unreaped leader (it exited on SIGINT):
        # T0071's 90-minute timeout raised it on 2026-10-05, so the run was recorded as interrupted, not timed out.
        try:
            os.killpg(pid, signal.SIGINT)
            time.sleep(5)
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    def spent_since(self, since_epoch: float) -> float:
        total = 0.0
        for p in self.runs_dir.glob("*/record.json"):
            try:
                rec = json.loads(p.read_text())
            except Exception:
                continue
            if p.stat().st_mtime >= since_epoch:
                total += float(rec.get("cost_usd") or 0.0)
        return total
