"""Journey coverage, the finish check, LLM retries and snapshot hints. No browser.  python -m pytest tests/unit"""

from pathlib import Path

import pytest

from agent import harness as harness_module
from agent import tools
from agent import triage as triage_module
from agent.coverage import check_journey, missing_journeys
from agent.harness import Harness
from agent.llm import JOURNEY_TESTS, TEST_JOURNEYS, LLMReply, MockLLM

HISTORY = Path(__file__).resolve().parents[2] / "evals" / "history"

VISIBLE_ONLY_DOWNLOAD = '''
def test_download_button(signed_in):
    lab = signed_in.frame_locator("#lab-results-frame")
    expect(lab.get_by_role("button", name="Download PDF")).to_be_visible()
'''
REAL_DOWNLOAD = '''
def test_download(signed_in, patient):
    lab = signed_in.frame_locator("#lab-results-frame")
    with signed_in.expect_download() as info:
        lab.get_by_role("button", name="Download PDF").click()
    assert info.value.suggested_filename == f"lab-results-{patient['mrn']}.pdf"
'''


# ---------------------------------------------------------------- coverage rules

def test_visibility_only_download_test_is_rejected():
    message = check_journey(VISIBLE_ONLY_DOWNLOAD, "download_pdf")
    assert "expect_download" in message and "suggested_filename" in message


def test_real_download_test_is_accepted():
    assert check_journey(REAL_DOWNLOAD, "download_pdf") is None


def test_the_real_model_test_that_missed_bug_4_is_rejected_as_a_download_test():
    code = (HISTORY / "2026-10-13-real-after-fixes-r3" / "repeat1-buggy-agent-tests" / "test_lab_results.py").read_text()
    assert check_journey(code, "download_pdf") is not None


def test_visibility_only_appointments_test_is_rejected():
    code = 'def test_a(signed_in):\n    expect(signed_in.get_by_role("heading", name="Upcoming appointments")).to_be_visible()\n'
    assert "to_have_count" in check_journey(code, "appointments")


@pytest.mark.parametrize("filename", list(JOURNEY_TESTS))
def test_mock_journey_tests_all_pass_coverage(filename):
    assert check_journey(JOURNEY_TESTS[filename], TEST_JOURNEYS[filename]) is None


def test_diff_check_and_syntax_errors_are_not_coverage_problems():
    assert check_journey("def test_x(): pass", "diff_check") is None
    assert check_journey("def test_x(:", "download_pdf") is None  # write_test reports the syntax error


def test_missing_journeys_ignores_diff_check():
    assert missing_journeys({"test_a.py": "sign_in", "test_d.py": "diff_check"}) == [
        "wrong_password", "appointments", "lab_results", "download_pdf"]


# ---------------------------------------------------------------- harness: finish check and retries

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Harness runs in a temp folder: no real tests/generated, runs/ or portal needed."""
    generated = tmp_path / "generated"
    generated.mkdir()
    monkeypatch.setattr(tools, "GENERATED_TESTS_DIR", generated)
    monkeypatch.setattr(triage_module, "GENERATED_TESTS_DIR", generated)
    monkeypatch.setattr(tools, "REPO_ROOT", tmp_path)
    return tmp_path


def make_harness(llm, tmp_path):
    h = Harness(llm, "http://localhost:8000/good/", "http://localhost:8000/buggy/", run_dir=tmp_path / "run")
    h.sleep = lambda seconds: None
    return h


def test_final_answer_without_journeys_is_sent_back_then_accepted(isolated):
    llm = MockLLM(["done", "done again", "really done"])
    h = make_harness(llm, isolated)
    summary = h.run()
    assert summary["stop_reason"] == "done" and summary["final_message"] == "really done"
    assert summary["coverage"]["nudges"] == harness_module.MAX_COVERAGE_NUDGES
    assert summary["coverage"]["missing"] == ["sign_in", "wrong_password", "appointments", "lab_results", "download_pdf"]
    assert summary["steps"] == 3


def test_write_test_rejects_a_journey_file_that_exercises_nothing(isolated):
    llm = MockLLM([[("write_test", {"filename": "test_download_pdf.py", "code": VISIBLE_ONLY_DOWNLOAD,
                                    "journey": "download_pdf"})], "x", "x", "x"])
    h = make_harness(llm, isolated)
    h.run()
    assert not (isolated / "generated" / "test_download_pdf.py").exists()
    assert h.triage.file_journeys == {}


class FlakyAPI:
    """Fails with a transient error a few times, then answers."""
    model = "mock"

    def __init__(self, failures, retryable=True):
        self.failures, self.retryable, self.calls = failures, retryable, 0

    def is_retryable(self, error):
        return self.retryable

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("Connection error.")
        return LLMReply(content="done")


def test_transient_llm_errors_are_retried_without_extra_steps(isolated):
    llm = FlakyAPI(failures=2)
    h = make_harness(llm, isolated)
    summary = h.run()
    assert summary["stop_reason"] == "done" and summary["llm_retries"] == 2 + 0  # 2 retries on step 1
    assert summary["steps"] == 1 + harness_module.MAX_COVERAGE_NUDGES


def test_retries_give_up_after_the_limit(isolated):
    llm = FlakyAPI(failures=99)
    summary = make_harness(llm, isolated).run()
    assert summary["stop_reason"] == "llm_error"
    assert llm.calls == harness_module.LLM_RETRIES + 1


def test_non_transient_errors_are_not_retried(isolated):
    llm = FlakyAPI(failures=1, retryable=False)
    summary = make_harness(llm, isolated).run()
    assert summary["stop_reason"] == "llm_error" and llm.calls == 1


# ---------------------------------------------------------------- snapshot hints

def test_snapshot_summary_lists_textbox_labels():
    aria = '- main:\n  - textbox "Email"\n  - textbox "Password"\n  - button "Sign in"\n  - link "Help"'
    summary = tools._summarize_frame(aria)
    assert summary["textboxes"] == ["Email", "Password"] and summary["links"] == ["Help"]
