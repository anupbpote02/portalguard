"""Deterministic eval matching against the real answer key.  python -m pytest tests/unit"""

import json

from evals.run_eval import EXPECTED_FILE, match_bugs

EXPECTED = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["bugs"]


def bug(title, category="accessibility", journey=None, diff=(), errors=()):
    return {"title": title, "category": category, "journey": journey,
            "diff_evidence": list(diff), "errors": list(errors)}


SIGN_IN = bug("sign in", journey="Sign in",
              diff=['sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)'])
APPOINTMENTS = bug("appointments", journey="See upcoming appointments",
                   diff=['dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]'])
LAB = bug("lab", journey="View lab results",
          diff=['dashboard / lab-results-frame: REMOVED: heading "Lab results" [level=1]'])
DOWNLOAD = bug("download", category="functional", journey="Download lab results PDF",
               errors=['line 6: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"'])


def test_all_four_found_is_full_recall_and_precision():
    result = match_bugs([SIGN_IN, APPOINTMENTS, LAB, DOWNLOAD], EXPECTED)
    assert result["recall"] == 1.0 and result["precision"] == 1.0 and result["type_accuracy"] == 1.0
    assert set(result["found"]) == {"BUG-1", "BUG-2", "BUG-3", "BUG-4"}


def test_missed_bug_lowers_recall_only():
    result = match_bugs([SIGN_IN, APPOINTMENTS, LAB], EXPECTED)
    assert result["missed"] == ["BUG-4"] and result["recall"] == 0.75 and result["precision"] == 1.0


def test_unmatched_report_is_a_false_positive():
    footer = bug("footer link color changed", journey=None, diff=["dashboard / main: CHANGED: link"])
    result = match_bugs([SIGN_IN, footer], EXPECTED)
    assert result["false_positives"] == ["footer link color changed"] and result["precision"] == 0.5


def test_second_report_of_same_bug_is_a_duplicate_not_a_false_positive():
    again = bug("lab again", journey="View lab results", errors=['waiting for get_by_role("heading", name="Lab results")'])
    result = match_bugs([LAB, again], EXPECTED)
    assert result["duplicates"] == ["BUG-3: lab again"] and result["false_positives"] == []
    assert result["precision"] == 1.0


def test_wrong_type_lowers_type_accuracy():
    result = match_bugs([{**DOWNLOAD, "category": "accessibility"}], EXPECTED)
    assert result["found"] == {"BUG-4": "download"} and result["type_accuracy"] == 0.0


def test_same_heading_name_in_wrong_frame_does_not_match_bug_3():
    wrong_place = bug("lab heading on main page", diff=['dashboard / main: REMOVED: heading "Lab results" [level=2]'])
    assert match_bugs([wrong_place], EXPECTED)["false_positives"] == ["lab heading on main page"]


def test_nothing_reported_on_good_release_is_perfect():
    result = match_bugs([], [])
    assert result["recall"] == 1.0 and result["false_positives"] == []
