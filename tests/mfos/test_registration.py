"""Pre-registration freezes the runner code, not only the spec YAML."""
import hashlib

import pytest

from mfos import experiments
from mfos.cli import main as cli
from mfos.store import Store

RUNNER = "experiments/runners/e000_canary.py"


def test_registration_freezes_the_runner_file(sandbox):
    """T0029, 2026-09-30: registration hashed only the YAML, so a case list, tolerance or error model in the runner
    could change after registration (and after seeing results) while the spec hash still matched."""
    assert cli(["exp", "register", "E000"]) == 0
    s = Store()
    spec = s.spec("E000")
    assert spec.runner_files == {RUNNER: hashlib.sha256((sandbox / RUNNER).read_bytes()).hexdigest()}
    assert cli(["doctor", "--ci"]) == 0
    with open(sandbox / RUNNER, "a") as f:
        f.write("\n# edited after registration\n")
    s.git("commit", "-qam", "edit the runner after registration", as_founder=True)
    assert cli(["doctor", "--ci"]) == 1
    with pytest.raises(RuntimeError, match="changed since registration"):
        experiments.run(Store(), "E000", force=True)


def test_the_recorded_runner_hashes_are_themselves_covered_by_the_spec_hash(sandbox):
    assert cli(["exp", "register", "E000"]) == 0
    s = Store()
    spec = s.spec("E000")
    tampered = spec.model_copy(update={"runner_files": {RUNNER: "0" * 64}})
    assert s.spec_hash(tampered) != spec.spec_hash


def test_a_spec_registered_before_runner_freezing_keeps_its_hash(sandbox):
    """E000 was registered on 2026-09-29 without runner_files; its recorded hash must still verify."""
    s = Store()
    spec = s.read_yaml(s.spec_path("E000", draft=True), experiments.m.ExperimentSpec)
    legacy = spec.model_dump(mode="json", exclude={"status", "registered_by", "registered_at", "spec_hash",
                                                   "runner_files"})
    from mfos.store import canonical_hash
    assert s.spec_hash(spec) == canonical_hash(legacy)


def test_a_runner_without_a_repository_file_cannot_be_registered(sandbox):
    s = Store()
    p = s.spec_path("E000", draft=True)
    p.write_text(p.read_text().replace(RUNNER, "experiments/runners/missing.py"))
    with pytest.raises(RuntimeError, match="cannot freeze"):
        experiments.register(s, "E000")
