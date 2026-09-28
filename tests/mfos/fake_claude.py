#!/usr/bin/env python3
"""Stand-in for `claude -p` in tests. Emits the same JSON envelope the real CLI does.

Behaviour by --agent:
  planner  -> plan for O000: implement canary, then run experiment E000
  builder  -> writes src/moduleforge/canary.py (wrong on the first attempt if FAKE_BUILDER_FAIL_FIRST=1)
  critic   -> accepts with one independent check
  scientist-> writes the diagnosis notes it was asked for
"""
import json
import os
import re
import sys
import uuid
from pathlib import Path

args = sys.argv[1:]
if os.environ.get("FAKE_RECORD_PATH"):  # lets tests see which python3 the hooks would get
    Path(os.environ["FAKE_RECORD_PATH"]).write_text(os.environ.get("PATH", "").split(os.pathsep)[0])
role = args[args.index("--agent") + 1]
prompt = args[args.index("-p") + 1]
sid = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1]
packet = re.search(r"`([^`]*\.mfos/packets/[^`]+\.md)`", prompt)
text = Path(packet.group(1)).read_text() if packet else ""

if role == "planner":
    out = {
        "assessment": "Canary: implement harmonic(), then run the pre-registered E000.",
        "create_tasks": [
            {"local_id": "n1", "title": "Implement moduleforge.canary.harmonic", "type": "implement",
             "agent": "builder", "description": "Return the n-th harmonic number in float64 using math.fsum.",
             "deliverables": ["src/moduleforge/canary.py"], "touches": ["src/moduleforge/canary.py"],
             "definition_of_done": [{"cmd": "PYTHONPATH=src python3 -c \"from moduleforge.canary import harmonic; assert harmonic(2) == 1.5\""}],
             "risk": "low", "budget_usd": 1.0, "max_turns": 20},
            {"local_id": "n2", "title": "Run E000", "type": "experiment", "agent": "none",
             "experiment": "E000", "depends_on": ["n1"], "description": "orchestrator runs E000"},
        ],
        "evidence_complete": True,
    }
elif role == "builder":
    marker = Path(os.environ["MFOS_ROOT_MAIN"]) / ".mfos" / "runs" / f"fake-marker-{os.environ['MFOS_TASK_ID']}"
    wrong = os.environ.get("FAKE_BUILDER_FAIL_FIRST") == "1" and not marker.exists()
    marker.write_text("x")
    subtle = Path(os.environ["MFOS_ROOT_MAIN"]) / ".mfos" / "runs" / "fake-subtle-used"
    if os.environ.get("FAKE_SUBTLE_BUG_ONCE") == "1" and not subtle.exists() and not wrong:
        subtle.write_text("x")  # passes the unit check (harmonic(2) == 1.5) but is wrong for large n
        body = "    s = math.fsum(1.0 / k for k in range(1, n + 1))\n    return s + (1e-3 if n > 100 else 0.0)\n"
    else:
        body = "    return float(n)\n" if wrong else "    return math.fsum(1.0 / k for k in range(1, n + 1))\n"
    Path("src/moduleforge/canary.py").write_text(
        "import math\n\n\ndef harmonic(n: int) -> float:\n" + body)
    marker.unlink() if not wrong else None
    out = {"status": "completed", "summary": "wrote canary" + (" (wrong)" if wrong else ""),
           "files_changed": ["src/moduleforge/canary.py"], "checks_run": []}
elif role == "critic":
    out = {"verdict": "accept", "findings": [], "independent_checks_performed": ["recomputed H_10 exactly"]}
elif role == "scientist":
    notes = re.search(r"(research/diagnoses/T\d+\.md)", text)
    if notes:
        Path(notes.group(1)).parent.mkdir(parents=True, exist_ok=True)
        Path(notes.group(1)).write_text("# diagnosis\nimplementation error\n")
    out = {"summary": "diagnosed", "failure_class": "implementation", "confidence": 0.8,
           "root_cause": "wrong formula", "evidence": ["test output"],
           "alternative_explanations": [{"explanation": "bad reference", "how_to_discriminate": "check H_10"}],
           "discriminating_tests": ["compare with exact fractions"], "recommended_actions": ["fix formula"]}
else:
    out = {"summary": "ok", "notes_file": "none"}

print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done",
                  "structured_output": out, "session_id": sid or str(uuid.uuid4()),
                  "total_cost_usd": 0.02, "num_turns": 3}))
