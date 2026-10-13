"""Triage decisions with a fake test runner: no browser, no server.  python -m pytest tests/unit"""

import pytest

from agent import triage as triage_module
from agent.triage import MAX_HEAL_ATTEMPTS, Triage

BASELINE, RELEASE = "http://localhost:8000/good/", "http://localhost:8000/buggy/"
DIFF = {"baseline": "baseline", "changes": {
    "dashboard / main": ['REMOVED: heading "Upcoming appointments" [level=2]']}}
NOT_FOUND = 'line 5: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")'


class FakeRunner:
    """Returns scripted outcomes per (release, test name), in order; last one repeats."""

    def __init__(self, script):
        self.script = {key: list(outcomes) for key, outcomes in script.items()}
        self.calls = []

    def __call__(self, base_url, filename, test_name):
        key = ("baseline" if base_url == BASELINE else "release", test_name)
        self.calls.append(key)
        outcomes = self.script[key]
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        return {"results": [{"test": f"{filename}::{test_name}[chromium]", "outcome": outcome,
                             **({"message": NOT_FOUND} if outcome != "passed" else {})}]}


@pytest.fixture(autouse=True)
def file_versions(monkeypatch):
    """Pretend each write_test changes the file, so triage re-evaluates rewritten tests."""
    versions = {}
    monkeypatch.setattr(triage_module, "_file_hash", lambda filename: versions.get(filename, 0))
    return versions


def failed(test_id):
    return {"results": [{"test": f"{test_id}[chromium]", "outcome": "failed", "message": NOT_FOUND}]}


def passed(test_id):
    return {"results": [{"test": f"{test_id}[chromium]", "outcome": "passed"}]}


def make(script):
    runner = FakeRunner(script)
    triage = Triage(runner, BASELINE, RELEASE)
    triage.record_diff(DIFF)
    return triage, runner


def test_regression_matching_diff_is_real_bug():
    triage, runner = make({("baseline", "test_list"): ["passed"], ("release", "test_list"): ["failed"]})
    verdict = triage.process(failed("test_appointments.py::test_list"))["test_appointments.py::test_list"]
    assert verdict["verdict"] == "real_bug"
    assert verdict["evidence"] == ['dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]']
    assert runner.calls == [("baseline", "test_list"), ("release", "test_list")]


def test_fails_then_passes_on_rerun_is_flaky_and_not_a_bug():
    triage, _ = make({("baseline", "test_list"): ["passed"], ("release", "test_list"): ["passed"]})
    verdict = triage.process(failed("test_appointments.py::test_list"))["test_appointments.py::test_list"]
    assert verdict["verdict"] == "flaky"
    assert triage.records("real_bug") == []


def test_fails_on_baseline_is_broken_test_and_skips_release_rerun():
    triage, runner = make({("baseline", "test_list"): ["failed"]})
    verdict = triage.process(failed("test_appointments.py::test_list"))["test_appointments.py::test_list"]
    assert verdict["verdict"] == "broken_test"
    assert verdict["heal_attempts_left"] == MAX_HEAL_ATTEMPTS
    assert runner.calls == [("baseline", "test_list")]


def test_heal_then_real_bug_is_recorded_as_healed(file_versions):
    triage, _ = make({("baseline", "test_list"): ["failed", "passed"], ("release", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    assert triage.before_write("test_appointments.py") is None      # heal attempt 1
    file_versions["test_appointments.py"] = 1
    verdict = triage.process(failed("test_appointments.py::test_list"))["test_appointments.py::test_list"]
    assert verdict["verdict"] == "real_bug"
    assert [r["test"] for r in triage.healed()] == ["test_appointments.py::test_list"]


def test_heal_limit_gives_up_and_refuses_a_fourth_write(file_versions):
    triage, _ = make({("baseline", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    for attempt in range(1, MAX_HEAL_ATTEMPTS + 1):
        assert triage.before_write("test_appointments.py") is None
        file_versions["test_appointments.py"] = attempt
        triage.process(failed("test_appointments.py::test_list"))
    assert triage.records("gave_up")
    assert "heal limit" in triage.before_write("test_appointments.py")


def test_refuses_to_rewrite_a_test_that_proves_a_bug():
    triage, _ = make({("baseline", "test_list"): ["passed"], ("release", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    assert "would hide the bug" in triage.before_write("test_appointments.py")


def test_regression_without_diff_or_journey_is_unconfirmed():
    triage, _ = make({("baseline", "test_misc"): ["passed"], ("release", "test_misc"): ["failed"]})
    triage.record_diff({"baseline": "baseline", "changes": {}})
    verdict = triage.process(failed("test_footer.py::test_misc"))["test_footer.py::test_misc"]
    assert verdict["verdict"] == "unconfirmed"


def test_decided_test_is_not_rerun_when_code_is_unchanged():
    triage, runner = make({("baseline", "test_list"): ["passed"], ("release", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    calls = len(runner.calls)
    triage.process(failed("test_appointments.py::test_list"))
    assert len(runner.calls) == calls


def test_passing_tests_cost_no_extra_runs():
    triage, runner = make({})
    assert triage.process(passed("test_appointments.py::test_list")) == {}
    assert runner.calls == []
