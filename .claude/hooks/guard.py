#!/usr/bin/env python3
"""PreToolUse guard. Standard library only. Fails closed for agent roles.

Role resolution: MFOS_ROLE (set by the orchestrator for headless runs) or the hook's
`agent_type` (a named subagent inside an interactive session). With neither, the
session belongs to the founder and nothing is blocked here; permission rules in
.claude/settings.json still apply.

Enforces, per role, from .mfos/policy.toml:
  * writes only inside the role's write scope; never into protected paths
    (unless the orchestrator set MFOS_APPROVED_PROTECTED=1 after founder approval)
  * no writes outside the checkout except the system temp directory
  * no reads of sealed holdout data for roles listed under [read_deny]
  * no git/GitHub integration commands and no destructive shell patterns
The orchestrator re-checks every changed file after the run, so this hook is the
first line of defence, not the last.
"""
import fnmatch
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROLES = {"planner", "builder", "scientist", "critic", "scout", "scribe"}

BASH_DENY = [
    (r"\bgit\s+push\b", "agents never push; the orchestrator integrates"),
    (r"(^|[;&|]\s*)gh\s", "agents never use the GitHub CLI"),
    (r"\bgit\s+(merge|rebase|filter-branch|filter-repo)\b", "history rewriting/merging is the orchestrator's job"),
    (r"\bgit\s+reset\s+--hard\b", "destructive reset"),
    (r"\bgit\s+(checkout|switch)\s+(main|master)\b", "stay on your task branch"),
    (r"\bgit\s+(clean\s+-[a-z]*f|stash\s+drop)\b", "destructive git operation"),
    (r"\bsudo\b", "no privilege escalation"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)", "destructive delete"),
    (r"(curl|wget)[^|]*\|\s*(ba|z)?sh\b", "no piping downloads into a shell"),
    (r"\b(pip|pip3)\s+install\b", "dependencies change only through uv and an approved task"),
    (r"\bchmod\s+-R\b|\bchown\b", "permission changes are not allowed"),
]
REDIRECT = re.compile(r"(?:^|[^0-9&<>])>{1,2}\s*([^\s;&|<>]+)")
TEE = re.compile(r"\btee\s+(?:-a\s+)?([^\s;&|]+)")
MUTATORS = re.compile(r"\b(mv|cp|rm|truncate|touch|install|ln)\b|\bsed\s+-i|\bgit\s+(rm|mv|checkout\s+--|restore)\b")


def write_targets(cmd: str) -> list[str]:
    """Best-effort list of paths a shell command may write. False positives are acceptable."""
    targets = REDIRECT.findall(cmd) + TEE.findall(cmd)
    for segment in re.split(r"[;&|]+", cmd):
        if MUTATORS.search(segment):
            targets += [tok for tok in segment.split()[1:] if not tok.startswith("-")]
    return [t.strip("'\"") for t in targets if t and not t.startswith("&")]


def emit(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": f"[mfos guard] {reason}"}}))
    sys.exit(0)


def load_policy(root: Path) -> dict:
    import tomllib  # Python >= 3.11
    with open(root / ".mfos" / "policy.toml", "rb") as f:
        return tomllib.load(f)


def rel_to(path: str, root: Path) -> tuple[str, bool]:
    """Return (relative path, inside_checkout)."""
    p = Path(path)
    p = (root / p) if not p.is_absolute() else p
    try:
        p = p.resolve()
    except OSError:
        pass
    try:
        return str(p.relative_to(root)), True
    except ValueError:
        return str(p), False


def temp_roots() -> set:
    """Temporary directories in raw, resolved and macOS forms. On macOS /tmp, /var and /etc are symlinks
    into /private and $TMPDIR is /var/folders/..., so a resolved target path never starts with the raw
    names; all three forms are accepted."""
    roots = set()
    for base in {tempfile.gettempdir(), "/tmp", "/var/tmp", os.environ.get("TMPDIR", "")}:
        base = base.rstrip("/")
        if not base:
            continue
        for form in (base, str(Path(base).resolve())):
            roots.add(form)
            if form in ("/tmp", "/var") or form.startswith(("/tmp/", "/var/")):
                roots.add("/private" + form)
    roots.discard("")
    return roots


def is_temp_path(path: str) -> bool:
    """True if an absolute, resolved path lies inside a temporary directory (path-boundary match)."""
    return any(path == r or path.startswith(r + "/") for r in temp_roots())


def matches(rel: str, globs: list) -> bool:
    return any(fnmatch.fnmatch(rel, g) or rel == g.rstrip("/*") for g in globs)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    role = os.environ.get("MFOS_ROLE") or data.get("agent_type") or ""
    if role not in ROLES:
        sys.exit(0)  # founder session: governed by permission rules only
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    try:
        pol = load_policy(root)
    except Exception as e:  # fail closed for agents
        emit("deny", f"cannot read .mfos/policy.toml ({e}); refusing all tool use for role {role}")
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    protected = pol.get("protected_paths", [])
    scope = pol.get("role_write_scopes", {}).get(role, [])
    approved = os.environ.get("MFOS_APPROVED_PROTECTED") == "1"

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        target = ti.get("file_path") or ti.get("notebook_path") or ""
        rel, inside = rel_to(target, root)
        if not inside:
            if is_temp_path(rel):
                sys.exit(0)
            emit("deny", f"{role} may not write outside its checkout: {rel}")
        if rel.startswith(".mfos/packets/"):
            emit("deny", "task packets are read-only")
        if matches(rel, protected) and not approved:
            emit("deny", f"{rel} is a protected path (founder approval required)")
        if not scope or not matches(rel, scope):
            emit("deny", f"{rel} is outside the {role} write scope {scope or '(read-only role)'}")
        sys.exit(0)

    if tool == "Read":
        rel, _ = rel_to(ti.get("file_path", ""), root)
        if matches(rel, pol.get("read_deny", {}).get(role, [])):
            emit("deny", f"{role} may not read {rel} (sealed evaluation data)")
        sys.exit(0)

    if tool == "Bash":
        cmd = ti.get("command", "")
        for pat, why in BASH_DENY:
            if re.search(pat, cmd):
                emit("deny", f"blocked shell command: {why}")
        for g in pol.get("read_deny", {}).get(role, []):
            if g.split("*")[0].rstrip("/") and g.split("*")[0].rstrip("/") in cmd:
                emit("deny", f"{role} may not access {g}")
        if not approved:
            for target in write_targets(cmd):
                rel, inside = rel_to(target, root)
                if inside and matches(rel, protected):
                    emit("deny", f"shell command would modify protected path {rel}")
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
