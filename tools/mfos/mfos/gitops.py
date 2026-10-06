"""Git/GitHub operations. Only the orchestrator runs these; agents never push or merge.

merge_mode (policy.git.merge_mode):
  local   squash-merge task branches into local main (bootstrap / offline / tests)
  github  push branch, open PR, request auto-merge; branch protection + CI decide
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

from . import models as m
from .store import Store


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "task"


class GitOps:
    def __init__(self, store: Store):
        self.s = store
        cfg = store.policy.get("git", {})
        self.main = cfg.get("main_branch", "main")
        self.mode = cfg.get("merge_mode", "local")
        self.remote = cfg.get("remote", "origin")
        self.wt_root = Path(os.path.expanduser(cfg.get("worktree_root", str(store.root.parent / "mf-wt"))))
        self.last_error = ""
        self.gh_env = {**store.git_env}
        if cfg.get("gh_config_dir"):
            self.gh_env["GH_CONFIG_DIR"] = os.path.expanduser(cfg["gh_config_dir"])

    # ------------------------------------------------------------------ worktrees
    def task_worktree(self, t: m.Task) -> Path:
        path = self.wt_root / t.id
        if path.exists():
            return path
        self.wt_root.mkdir(parents=True, exist_ok=True)
        branch = t.branch or f"task/{t.id}-{slug(t.title)}"
        exists = self.s.git("rev-parse", "--verify", "--quiet", branch, check=False)
        if exists:
            self.s.git("worktree", "add", str(path), branch)
        else:
            self.s.git("worktree", "add", "-b", branch, str(path), self.main)
        t.branch = branch
        return path

    def detached_worktree(self, name: str, ref: Optional[str] = None) -> Path:
        path = self.wt_root / name
        if path.exists():
            self.remove_worktree(path)
        self.wt_root.mkdir(parents=True, exist_ok=True)
        self.s.git("worktree", "add", "--detach", str(path), ref or self.main)
        return path

    def review_checkout(self, name: str, ref: str) -> Path:
        """Blinded snapshot of ``ref`` for a critic: its tree minus the blinded paths, committed once into a new,
        unrelated repository. None of this repository's history, branches or objects is reachable from it, so
        `git show HEAD:<path>` or `git log -p` cannot recover a blinded file (T0028, 2026-09-30)."""
        path = self.wt_root / name
        if path.exists():
            self.remove_worktree(path)
        path.mkdir(parents=True)
        tree = subprocess.run(["git", "archive", "--format=tar", ref], cwd=self.s.root, capture_output=True,
                              check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tree)) as tar:
            tar.extractall(path, filter="data")
        for pattern in self.s.policy.get("blinding", {}).get("remove_paths", []):
            for p in path.glob(pattern):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
        self.s.git("init", "-q", "-b", "review", cwd=path)
        self.s.git("add", "-A", cwd=path)
        self.s.git("-c", "user.name=review", "-c", "user.email=review@invalid", "-c", "commit.gpgsign=false",
                   "commit", "-q", "--no-verify", "-m", "review snapshot", cwd=path)
        return path

    def remove_worktree(self, path: Path) -> None:
        self.s.git("worktree", "remove", "--force", str(path), check=False)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        self.s.git("worktree", "prune", check=False)

    # ------------------------------------------------------------------ commits & diffs
    def commit_all(self, path: Path, message: str) -> bool:
        self.s.git("add", "-A", cwd=path)
        if not self.s.git("status", "--porcelain", cwd=path):
            return False
        self.s.git("commit", "-m", message, cwd=path)
        return True

    def changed_files(self, path: Path) -> list[str]:
        out = self.s.git("diff", "--name-only", f"{self.main}...HEAD", cwd=path, check=False)
        return [x for x in out.splitlines() if x]

    def diff(self, path: Path, max_chars: int = 60000) -> str:
        d = self.s.git("diff", f"{self.main}...HEAD", cwd=path, check=False)
        return d if len(d) <= max_chars else d[:max_chars] + "\n...[diff truncated]"

    def head(self, path: Optional[Path] = None) -> str:
        return self.s.git("rev-parse", "HEAD", cwd=path)

    STATE_PATHS = ("project/", "experiments/specs/", "experiments/results/", "experiments/drafts/")

    def main_code_moved(self, path: Path) -> bool:
        """Whether main changed anything but orchestrator state since this branch last took it in."""
        base = self.s.git("merge-base", self.main, "HEAD", cwd=path, check=False)
        if not base:
            return True
        out = self.s.git("diff", "--name-only", base, self.main, cwd=path, check=False)
        return any(f and not f.startswith(self.STATE_PATHS) for f in out.splitlines())

    def update_from_main(self, path: Path) -> tuple[bool, str]:
        """Merge current main into the task branch; on a conflict, abort and return the output."""
        r = subprocess.run(["git", "merge", "--no-edit", self.main], cwd=path, capture_output=True, text=True,
                           env=self.s.git_env)
        if r.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], cwd=path, capture_output=True, env=self.s.git_env)
            return False, (r.stdout + r.stderr)[-2000:]
        return True, ""

    # ------------------------------------------------------------------ policy checks
    def scope_violations(self, role: str, files: list[str], approved_protected: bool = False) -> list[str]:
        pol = self.s.policy
        allowed = pol.get("role_write_scopes", {}).get(role, [])
        protected = pol.get("protected_paths", [])
        bad = []
        for f in files:
            if any(fnmatch.fnmatch(f, g) for g in protected) and not approved_protected:
                bad.append(f"{f} (protected)")
            elif allowed and not any(fnmatch.fnmatch(f, g) for g in allowed):
                bad.append(f"{f} (outside {role} write scope)")
        return bad

    # ------------------------------------------------------------------ integration
    def integrate(self, t: m.Task, path: Path, body: str, auto: bool) -> tuple[str, Optional[int]]:
        """Returns (state, pr_number). state in {'merged', 'pending', 'needs_founder', 'conflict'}."""
        if self.mode == "local":
            if not auto:
                return "needs_founder", None
            self.s.git("checkout", self.main)
            r = subprocess.run(["git", "merge", "--squash", t.branch or ""], cwd=self.s.root,
                               capture_output=True, text=True, env=self.s.git_env)
            if r.returncode != 0:
                self.last_error = (r.stdout + r.stderr)[-2000:]
                self.s.git("merge", "--abort", check=False)
                self.s.git("reset", "--hard", "HEAD", check=False)
                # Only a genuine content conflict is the agent's problem; anything else is infrastructure.
                return ("conflict" if "CONFLICT" in self.last_error else "error"), None
            msg = ["-m", f"[{t.id}] {t.title}"]
            if t.approval:
                msg += ["-m", f"Founder-Approved: {t.approval}"]
            self.s.git("commit", "--allow-empty", *msg)
            return "merged", None
        # github mode
        subprocess.run(["git", "push", "-u", self.remote, t.branch or ""], cwd=path, check=True,
                       env=self.gh_env, capture_output=True)
        pr = t.pr
        if pr is None:
            labels = ["mfos", f"risk:{t.risk}"] + ([] if auto else ["needs-founder"])
            out = subprocess.run(
                ["gh", "pr", "create", "--base", self.main, "--head", t.branch or "",
                 "--title", f"[{t.id}] {t.title}", "--body", body, *sum((["--label", x] for x in labels), [])],
                cwd=path, capture_output=True, text=True, env=self.gh_env, check=True).stdout
            pr = int(out.strip().rsplit("/", 1)[-1])
        if auto:
            subprocess.run(["gh", "pr", "merge", str(pr), "--squash", "--auto", "--delete-branch"],
                           cwd=path, capture_output=True, text=True, env=self.gh_env)
            return "pending", pr
        return "needs_founder", pr

    def pr_state(self, pr: int) -> str:
        out = subprocess.run(["gh", "pr", "view", str(pr), "--json", "state,mergeable"],
                             cwd=self.s.root, capture_output=True, text=True, env=self.gh_env)
        if out.returncode != 0:
            return "unknown"
        data = json.loads(out.stdout)
        if data.get("state") == "MERGED":
            return "merged"
        if data.get("mergeable") == "CONFLICTING":
            return "conflict"
        return data.get("state", "unknown").lower()

    def sync_main(self) -> None:
        if not self.s.git("remote", "get-url", self.remote, check=False).strip():
            return
        self.s.git("checkout", self.main, check=False)
        self.s.git("pull", "-q", "--ff-only", self.remote, self.main, check=False)

    def is_ancestor(self, commit: str) -> bool:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", commit, self.main], cwd=self.s.root)
        return r.returncode == 0
