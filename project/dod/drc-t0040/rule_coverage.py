"""DRC DoD: removing any rule from check() must make some test in tests/unit/drc fail by assertion.

A crash, collection error or fixture error does not count as coverage (review T0036 of T0034).
"""
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

RULES = ["min_trace_width", "min_spacing", "edge_margin", "die_off_trace", "die_wrong_net", "die_edge_margin",
         "die_spacing", "die_on_terminal", "die_unbonded", "die_no_source_pad", "die_bad_switch", "missing_switch",
         "net_split", "wire_length", "wire_landing", "wire_landing_keepout", "wire_start", "wire_net", "wire_pitch",
         "wire_diameter", "terminal_off_trace"]
PROG = ("import moduleforge.drc as d, moduleforge.drc.rules as r; o = r.check; "
        "d.check = r.check = lambda *a, **k: [v for v in o(*a, **k) if v.rule != {rule!r}]; "
        "import pytest, sys; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '--junitxml={xml}', "
        "'tests/unit/drc']))")


def killed(xml: Path) -> bool:
    return xml.exists() and any("AssertionError" in (f.text or "") + (f.get("message") or "")
                                for f in ET.parse(xml).iter("failure"))


survivors = []
with tempfile.TemporaryDirectory() as tmp:
    for rule in RULES:
        xml = Path(tmp) / "r.xml"
        subprocess.run([sys.executable, "-c", PROG.format(rule=rule, xml=xml)], capture_output=True)
        if not killed(xml):
            survivors.append(rule)
assert not survivors, f"no test in tests/unit/drc fails by assertion when these rules are removed: {survivors}"
print(f"all {len(RULES)} rules are covered by an assertion failure")
