import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "mfos"))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A throwaway copy of the scaffold wired to the fake claude and local merges."""
    root = tmp_path / "repo"
    root.mkdir()
    for item in [".mfos/policy.toml", ".gitignore", "templates", "project/objectives/O000",
                 "experiments/drafts/E000.yaml", "experiments/runners", "src", "tools", ".claude"]:
        src = REPO / item
        dst = root / item
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    # The live O000 state (spend, replans, diagnoses) must not leak in: start from the bootstrap state.
    (root / "project" / "objectives" / "O000" / "state.yaml").write_text("status: draft\n")
    shutil.rmtree(root / "src" / "moduleforge" / "__pycache__", ignore_errors=True)
    (root / "src" / "moduleforge" / "canary.py").unlink(missing_ok=True)
    pol = (root / ".mfos" / "policy.toml").read_text()
    pol = pol.replace('claude_bin = "claude"', f'claude_bin = "{sys.executable} {REPO / "tests/mfos/fake_claude.py"}"')
    pol = pol.replace('worktree_root = "~/mf/wt"', f'worktree_root = "{tmp_path / "wt"}"')
    start = pol.index("[gates]")
    end = pol.index("[planning]")
    pol = pol[:start] + '[gates]\nfast = ["PYTHONPATH=src python3 -c \'import moduleforge\'"]\nfull = []\n\n' + pol[end:]
    (root / ".mfos" / "policy.toml").write_text(pol)
    spec = root / "experiments" / "drafts" / "E000.yaml"
    spec.write_text(spec.read_text().replace("uv run python", "python3"))
    env_path = os.pathsep.join([str(root / "tools" / "mfos"), str(root / "src")])
    monkeypatch.setenv("PYTHONPATH", env_path)
    monkeypatch.setenv("MFOS_ROOT", str(root))
    monkeypatch.chdir(root)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=root, check=True)
    return root
