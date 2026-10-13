"""Long-term memory rules, no browser.  python -m pytest tests/unit"""

import json
from types import SimpleNamespace

from agent.memory import Memory, bug_fingerprint, selectors_in

BASELINE, RELEASE = "http://localhost:8000/good/", "http://localhost:8000/buggy/"
WRONG = 'lab = signed_in.frame_locator("#labs-frame")\nlab.get_by_role("heading", name="Lab results")'
RIGHT = 'lab = signed_in.frame_locator("#lab-results-frame")\nlab.get_by_role("heading", name="Lab results")'
SUMMARY = {"stop_reason": "done", "steps": 5, "duration_s": 1.0}


def fake_triage(records):
    return SimpleNamespace(tests={r["test"]: r for r in records},
                           healed=lambda: [r for r in records if r.get("healed")],
                           records=lambda verdict: [r for r in records if r["verdict"] == verdict])


def lab_record(**extra):
    return {"test": "test_lab_results.py::test_lab", "file": "test_lab_results.py", "verdict": "real_bug",
            "code_hash": "abc", "baseline_outcome": "passed", "category": "accessibility",
            "journey": "View lab results", "release_error": "line 6: not found",
            "diff_evidence": ['dashboard / lab-results-frame: REMOVED: heading "Lab results" [level=1]'], **extra}


def test_selectors_are_extracted_from_test_code():
    assert selectors_in(RIGHT) == {'frame_locator("#lab-results-frame")',
                                   'get_by_role("heading", name="Lab results")'}


def test_heal_teaches_a_selector_fix_that_is_applied_next_time(tmp_path):
    memory = Memory(tmp_path / "memory.json")
    learned = memory.learn("run1", RELEASE, BASELINE, fake_triage([lab_record(healed=True)]),
                           {"test_lab_results.py": [WRONG, RIGHT]}, SUMMARY)
    assert learned["selector_fixes"] == ['frame_locator("#labs-frame") -> frame_locator("#lab-results-frame")']
    memory.save()

    code, fixes = Memory(tmp_path / "memory.json").apply_selector_fixes(WRONG)
    assert code == RIGHT and len(fixes) == 1


def test_same_bug_is_known_on_the_next_run(tmp_path):
    memory = Memory(tmp_path / "memory.json")
    assert memory.known_bug(lab_record()) is None
    memory.learn("run1", RELEASE, BASELINE, fake_triage([lab_record()]), {}, SUMMARY)
    memory.save()

    reloaded = Memory(tmp_path / "memory.json")
    assert reloaded.known_bug(lab_record())["first_reported_run"] == 1
    assert reloaded.run_count == 1


def test_functional_fingerprint_ignores_line_numbers_and_timeouts():
    a = {"journey": "Download lab results PDF", "diff_evidence": [],
         "release_error": 'line 6: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"'}
    b = {**a, "release_error": 'line 9: TimeoutError: Timeout 7000ms exceeded while waiting for event "download"'}
    assert bug_fingerprint(a) == bug_fingerprint(b)


def test_baseline_is_saved_with_tests_that_passed_on_it(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.memory.REPO_ROOT", tmp_path)
    snapshot = tmp_path / "baseline.json"
    snapshot.write_text(json.dumps({"pages": {}}))
    memory = Memory(tmp_path / "memory" / "memory.json")
    memory.save_baseline(BASELINE, snapshot, {"label": "baseline", "pages": {}})
    memory.learn("run1", RELEASE, BASELINE, fake_triage([lab_record()]), {}, SUMMARY)
    assert memory.cached_baseline(BASELINE) is not None
    assert memory.baseline_passes(BASELINE) == {"test_lab_results.py::test_lab": "abc"}


def test_disabled_memory_reads_and_writes_nothing(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"run_count": 7}))
    memory = Memory(path, enabled=False)
    assert memory.run_count == 0
    memory.learn("run1", RELEASE, BASELINE, fake_triage([lab_record()]), {}, SUMMARY)
    memory.save()
    assert json.loads(path.read_text()) == {"run_count": 7}
