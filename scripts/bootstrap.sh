#!/usr/bin/env bash
# Bootstrap the ModuleForge operating system in the current directory.
# Usage: scripts/bootstrap.sh <your-github-username>
set -euo pipefail
FOUNDER="${1:?usage: scripts/bootstrap.sh <your-github-username>}"
STEP="checking prerequisites"
trap 'echo; echo "bootstrap STOPPED while ${STEP}. Nothing was committed. Fix the problem above and re-run" \
      "scripts/bootstrap.sh ${FOUNDER} (safe to re-run). Do not continue with the next setup steps yet." >&2' ERR

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 — $2" >&2; exit 1; }; }
need git    "install git"
need uv     "curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v gh > /dev/null 2>&1 || echo "note: gh not installed (only needed to create the GitHub repo and in Phase 4)"
need claude "install Claude Code: https://code.claude.com/docs/en/setup"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "interactive Claude sessions need python3 >= 3.11 on PATH for the hooks." >&2
       echo "macOS ships 3.9 at /usr/bin/python3: run 'brew install python' (Homebrew's python3 comes first on PATH)." >&2
       exit 1; }

STEP="personalizing CODEOWNERS and policy"
python3 - "$FOUNDER" << 'PY'
import sys, pathlib
user = sys.argv[1]
p = pathlib.Path(".github/CODEOWNERS")
p.write_text(p.read_text().replace("@FOUNDER", "@" + user))
p = pathlib.Path(".mfos/policy.toml")
p.write_text(p.read_text().replace('"FOUNDER"', f'"{user}"').replace('"FOUNDER@', f'"{user}@'))
PY

STEP="creating the Python environment (uv sync; Python version pinned by .python-version)"
uv sync --all-groups
STEP="running the test suite"
uv run pytest -q tests
STEP="creating the git repository and first commit"
[ -d .git ] || git init -q -b main
git config user.name "$FOUNDER"                              # your commits in ~/mf/main are yours;
git config user.email "$FOUNDER@users.noreply.github.com"    # the orchestrator always commits as mfos-bot
git add -A
git commit -qm "Bootstrap ModuleForge operating system" || true
mkdir -p "$HOME/mf/wt" "$HOME/.config/mfos"
uv run mfos doctor || true
trap - ERR
echo "bootstrap OK: $(git log --oneline | head -1)"

cat << NEXT

Bootstrap complete. Next (docs/INFRASTRUCTURE.md §12 has the full procedure):
  1. claude                                  # log in once; accept the workspace trust prompt; /exit
  2. uv run mfos exp register E000           # pre-register the canary experiment (your approval)
  3. uv run mfos objective approve O000      # freeze and activate the canary objective
  4. uv run mfos loop --cycles 60 --poll 20  # watch the canary run end to end (~15–30 min, ~\$2–5)
  5. uv run mfos status                      # expect O000: passed, claim C001
  6. run permanently: macOS -> scripts/com.moduleforge.mfos.plist (launchd); Linux -> scripts/mfos.service
NEXT
