"""Hooks are the in-session enforcement layer; they must deny the right things and nothing else."""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / ".claude" / "hooks" / "guard.py"
STOP = REPO / ".claude" / "hooks" / "stop_gate.py"


def run_guard(role, tool, tool_input):
    env = {**os.environ, "MFOS_ROLE": role, "CLAUDE_PROJECT_DIR": str(REPO)} if role else \
          {k: v for k, v in os.environ.items() if k != "MFOS_ROLE"} | {"CLAUDE_PROJECT_DIR": str(REPO)}
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
                       capture_output=True, text=True, env=env)
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "allow"


def test_builder_scope():
    assert run_guard("builder", "Write", {"file_path": "src/moduleforge/x.py"}) == "allow"
    assert run_guard("builder", "Edit", {"file_path": "tests/acceptance/test_a.py"}) == "deny"
    assert run_guard("builder", "Edit", {"file_path": ".mfos/policy.toml"}) == "deny"
    assert run_guard("builder", "Read", {"file_path": "data/holdout/seeds.json"}) == "deny"


def test_read_only_roles_and_tmp():
    assert run_guard("critic", "Write", {"file_path": "src/x.py"}) == "deny"
    assert run_guard("critic", "Write", {"file_path": "/tmp/scratch.py"}) == "allow"
    assert run_guard("planner", "Write", {"file_path": "project/tasks/T0001.yaml"}) == "deny"


def test_shell_rules():
    assert run_guard("builder", "Bash", {"command": "uv run pytest tests/acceptance -q 2>&1 | tail"}) == "allow"
    assert run_guard("builder", "Bash", {"command": "git push origin HEAD"}) == "deny"
    assert run_guard("builder", "Bash", {"command": "sed -i s/0.9/0.5/ experiments/specs/E002.yaml"}) == "deny"
    assert run_guard("builder", "Bash", {"command": "gh pr merge 3"}) == "deny"


def test_founder_session_not_blocked():
    assert run_guard("", "Write", {"file_path": ".claude/settings.json"}) == "allow"


def test_stop_gate_blocks_until_dod_passes(tmp_path):
    dod = tmp_path / "T1-a1.dod.json"
    target = tmp_path / "done.txt"
    dod.write_text(json.dumps({"checks": [{"cmd": f"test -f {target}"}], "deliverables": [], "gate": []}))
    env = {**os.environ, "MFOS_ROLE": "builder", "MFOS_DOD_FILE": str(dod), "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, str(STOP)], input="{}", capture_output=True, text=True, env=env)
    assert json.loads(r.stdout)["decision"] == "block"
    target.write_text("ok")
    r = subprocess.run([sys.executable, str(STOP)], input="{}", capture_output=True, text=True, env=env)
    assert r.stdout.strip() == ""


def _load_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mfos_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_temp_paths_on_macos_layout(monkeypatch):
    """macOS: /tmp -> /private/tmp and $TMPDIR=/var/folders/.../T -> /private/var/folders/.../T.
    The guard sees resolved paths, so both forms must count as temporary (this failed on a real Mac)."""
    guard = _load_guard()
    monkeypatch.setenv("TMPDIR", "/var/folders/ab/cd1234/T")
    monkeypatch.setattr(guard.tempfile, "tempdir", "/var/folders/ab/cd1234/T")
    assert guard.is_temp_path("/private/tmp/scratch.py")
    assert guard.is_temp_path("/tmp/scratch.py")
    assert guard.is_temp_path("/private/var/folders/ab/cd1234/T/tmpxyz/check.py")
    assert guard.is_temp_path("/var/folders/ab/cd1234/T/check.py")
    # path boundaries, and nothing outside temp
    assert not guard.is_temp_path("/tmpfoo/x.py")
    assert not guard.is_temp_path("/private/tmpx/y.py")
    assert not guard.is_temp_path("/private/var/db/x")
    assert not guard.is_temp_path("/Users/me/.ssh/id_ed25519")
    assert not guard.is_temp_path("/private/etc/hosts")


def test_symlinked_temp_dir_end_to_end(tmp_path):
    """A temp dir reached through a symlink (the macOS situation) is writable for a read-only role."""
    real = tmp_path / "private_tmp"
    real.mkdir()
    link = tmp_path / "tmp_link"
    link.symlink_to(real)
    env = {**os.environ, "MFOS_ROLE": "critic", "CLAUDE_PROJECT_DIR": str(REPO), "TMPDIR": str(link)}
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(link / "scratch.py")}})
    r = subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, env=env)
    assert r.stdout.strip() == ""  # allowed
