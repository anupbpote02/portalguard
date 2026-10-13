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
    """Pretend each write_test changes the test, so triage re-evaluates rewritten tests.
    Also keeps unit tests away from whatever is in tests/generated/ (no file reads)."""
    versions = {}
    monkeypatch.setattr(triage_module, "_test_hash", lambda filename, name: versions.get(filename, 0))
    monkeypatch.setattr(triage_module, "_read", lambda filename: "")
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
    assert triage.before_write("test_appointments.py", "def test_list(): pass") is None      # heal attempt 1
    file_versions["test_appointments.py"] = 1
    verdict = triage.process(failed("test_appointments.py::test_list"))["test_appointments.py::test_list"]
    assert verdict["verdict"] == "real_bug"
    assert [r["test"] for r in triage.healed()] == ["test_appointments.py::test_list"]


def test_heal_limit_gives_up_and_refuses_a_fourth_write(file_versions):
    triage, _ = make({("baseline", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    for attempt in range(1, MAX_HEAL_ATTEMPTS + 1):
        assert triage.before_write("test_appointments.py", "def test_list(): pass") is None
        file_versions["test_appointments.py"] = attempt
        triage.process(failed("test_appointments.py::test_list"))
    assert triage.records("gave_up")
    assert "heal limit" in triage.before_write("test_appointments.py", "def test_list(): pass")


def test_refuses_to_rewrite_a_test_that_proves_a_bug():
    triage, _ = make({("baseline", "test_list"): ["passed"], ("release", "test_list"): ["failed"]})
    triage.process(failed("test_appointments.py::test_list"))
    assert "evidence of a confirmed bug" in triage.before_write("test_appointments.py", "def test_list(): pass")


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


# ---------------------------------------------------------------- fixes from the first real eval

SIGN_IN_DIFF = {"baseline": "baseline", "changes": {
    "sign-in / main": ['CHANGED: button "Sign in"  ->  button (no accessible name)']}}


def with_sources(monkeypatch, sources: dict):
    monkeypatch.setattr(triage_module, "_read", lambda filename: sources.get(filename, ""))


def test_journey_comes_from_write_test_not_the_filename():
    """Before: a download test inside test_lab_results.py was labelled 'View lab results'."""
    triage, _ = make({("baseline", "test_download"): ["passed"], ("release", "test_download"): ["failed"]})
    triage.record_diff({"baseline": "baseline", "changes": {}})
    triage.record_write("test_lab_results.py", "download_pdf")
    triage.process(failed("test_lab_results.py::test_download"))
    assert triage.tests["test_lab_results.py::test_download"]["journey"] == "Download lab results PDF"


def test_diff_check_without_diff_evidence_is_unconfirmed():
    triage, _ = make({("baseline", "test_misc"): ["passed"], ("release", "test_misc"): ["failed"]})
    triage.record_diff({"baseline": "baseline", "changes": {}})
    triage.record_write("test_diff_checks.py", "diff_check")
    verdict = triage.process(failed("test_diff_checks.py::test_misc"))["test_diff_checks.py::test_misc"]
    assert verdict["verdict"] == "unconfirmed"


def test_quoted_strings_on_failing_line_link_to_the_diff(monkeypatch):
    """Before: assert button.get_attribute("name") == "Sign in" had no name="..." in the error."""
    with_sources(monkeypatch, {"test_diff_checks.py": 'def test_name(page):\n'
                                                      '    button = page.get_by_role("button")\n'
                                                      '    assert button.get_attribute("name") == "Sign in"\n'})
    triage = Triage(FakeRunner({("baseline", "test_name"): ["passed"], ("release", "test_name"): ["failed"]}),
                    BASELINE, RELEASE)
    triage.record_diff(SIGN_IN_DIFF)
    triage.record_write("test_diff_checks.py", "diff_check")
    triage.process({"results": [{"test": "test_diff_checks.py::test_name[chromium]", "outcome": "failed",
                                 "message": "line 3: AssertionError: assert None == 'Sign in'"}]})
    record = triage.tests["test_diff_checks.py::test_name"]
    assert record["verdict"] == "real_bug"
    assert record["diff_evidence"] == ['sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)']


def test_only_the_failing_line_counts_not_the_whole_test(monkeypatch):
    """A test that signs in with the button and then fails on download is not about BUG-1."""
    with_sources(monkeypatch, {"test_download_pdf.py": 'def test_dl(page):\n'
                                                       '    page.get_by_role("button", name="Sign in").click()\n'
                                                       '    with page.expect_download():\n'
                                                       '        page.get_by_role("button", name="Download PDF").click()\n'})
    triage = Triage(FakeRunner({("baseline", "test_dl"): ["passed"], ("release", "test_dl"): ["failed"]}),
                    BASELINE, RELEASE)
    triage.record_diff(SIGN_IN_DIFF)
    triage.record_write("test_download_pdf.py", "download_pdf")
    triage.process({"results": [{"test": "test_download_pdf.py::test_dl[chromium]", "outcome": "failed",
                                 "message": 'line 3: TimeoutError: waiting for event "download"'}]})
    record = triage.tests["test_download_pdf.py::test_dl"]
    assert record["diff_evidence"] == [] and record["journey"] == "Download lab results PDF"


BUG_TEST = 'def test_bug(page):\n    assert page.title() == "x"\n'
BROKEN_TEST = 'def test_broken(page):\n    assert page.title() == "y"\n'


def test_lock_is_per_test_other_tests_in_the_file_can_be_healed(monkeypatch):
    """Before: a broken test couldn't be healed because another test in its file proved a bug."""
    with_sources(monkeypatch, {"test_sign_in.py": BUG_TEST + "\n\n" + BROKEN_TEST})
    triage = Triage(FakeRunner({("baseline", "test_bug"): ["passed"], ("release", "test_bug"): ["failed"],
                                ("baseline", "test_broken"): ["failed"]}), BASELINE, RELEASE)
    triage.record_diff(DIFF)
    triage.record_write("test_sign_in.py", "sign_in")
    triage.process({"results": [{"test": f"test_sign_in.py::{n}[chromium]", "outcome": "failed", "message": "x"}
                                for n in ("test_bug", "test_broken")]})
    assert triage.tests["test_sign_in.py::test_bug"]["verdict"] == "real_bug"
    assert triage.tests["test_sign_in.py::test_broken"]["verdict"] == "broken_test"

    healed = BUG_TEST + "\n\n# fixed\n" + BROKEN_TEST.replace('"y"', '"z"')
    assert triage.before_write("test_sign_in.py", healed) is None
    changed_bug_test = BUG_TEST.replace('"x"', '"anything"') + "\n\n" + BROKEN_TEST
    assert "test_bug" in triage.before_write("test_sign_in.py", changed_bug_test)
    assert "test_bug" in triage.before_write("test_sign_in.py", BROKEN_TEST)  # removing it is refused too


def test_test_hash_is_per_function(tmp_path, monkeypatch):
    monkeypatch.undo()  # use the real _read/_test_hash on a temp folder
    monkeypatch.setattr(triage_module, "GENERATED_TESTS_DIR", tmp_path)
    (tmp_path / "test_a.py").write_text(BUG_TEST + "\n\n" + BROKEN_TEST)
    before = triage_module._test_hash("test_a.py", "test_bug")
    (tmp_path / "test_a.py").write_text(BUG_TEST + "\n\n# a comment\n" + BROKEN_TEST.replace('"y"', '"z"'))
    assert triage_module._test_hash("test_a.py", "test_bug") == before
    assert triage_module._test_hash("test_a.py", "test_broken") != ""
