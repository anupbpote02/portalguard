# PortalGuard report: run eval-20261013-114206-r1-buggy

- **Release under test:** http://localhost:8000/buggy/
- **Baseline (last good release):** http://localhost:8000/good/
- **Model:** gpt-4.1-mini  |  **Stop reason:** `done`
- Synthetic test data only. Verdicts come from Playwright assertions run by the harness (release runs, reruns, baseline runs), not from the model.

## Summary

| Real bugs | New | Known | Healed tests | Flaky (not reported) | Unconfirmed | Broken tests left |
|---|---|---|---|---|---|---|
| 4 | 4 | 0 | 7 | 0 | 0 | 1 |

| LLM steps | Tool calls | Harness test runs | Tokens | Cost | Duration |
|---|---|---|---|---|---|
| 21 | 29 (0 blocked) | 27 | 122,362 | $0.0537 | 336.7s |

## Bugs found

### 1. [NEW] REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_appointments.py::test_appointments`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 7: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Test `test_diff_checks.py::test_dashboard_upcoming_appointments_heading`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 13: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Snapshot diff: `dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]`
- **Reproduce:** `python -m pytest tests/generated/test_appointments.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-114206-r1-buggy/tests/`)

### 2. [NEW] Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)

- **Status:** NEW
- **Type:** functional  |  **Journey:** Download lab results PDF
- **Evidence:**
  - Test `test_download_pdf.py::test_download_pdf`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 7: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest tests/generated/test_download_pdf.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-114206-r1-buggy/tests/`)

### 3. [NEW] CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)

- **Status:** NEW
- **Type:** accessibility
- **Evidence:**
  - Test `test_diff_checks.py::test_sign_in_button_name`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 8: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("button", name="Sign in")`
  - Test `test_sign_in.py::test_sign_in`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 12: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`
  - Snapshot diff: `sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)`
- **Reproduce:** `python -m pytest tests/generated/test_diff_checks.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-114206-r1-buggy/tests/`)

### 4. [NEW] REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame)

- **Status:** NEW
- **Type:** accessibility
- **Evidence:**
  - Test `test_diff_checks.py::test_lab_results_frame_heading`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 19: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for locator("#lab-results-frame").content_frame.get_by_role("heading", name="Lab results")`
  - Test `test_lab_results.py::test_lab_results`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 8: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for locator("#lab-results-frame").content_frame.get_by_role("heading", name="Lab results")`
  - Snapshot diff: `dashboard / lab-results-frame: REMOVED: heading "Lab results" [level=1]`
- **Reproduce:** `python -m pytest tests/generated/test_diff_checks.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-114206-r1-buggy/tests/`)

## Healed tests

| Test | Attempts | Original error | Now |
|---|---|---|---|
| `test_appointments.py::test_appointments` | 1/3 | `line 6: TypeError: Page.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_diff_checks.py::test_sign_in_button_name` | 1/3 | `line 8: TypeError: Page.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_diff_checks.py::test_dashboard_upcoming_appointments_heading` | 1/3 | `line 14: TypeError: Page.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_diff_checks.py::test_lab_results_frame_heading` | 1/3 | `line 21: TypeError: FrameLocator.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_download_pdf.py::test_download_pdf` | 1/3 | `line 8: TypeError: FrameLocator.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_lab_results.py::test_lab_results` | 1/3 | `line 7: TypeError: FrameLocator.get_by_role() takes 2 positional arguments but 3 were given` | valid; fails on release (bug above) |
| `test_sign_in.py::test_sign_in` | 3/3 | `line 7: TimeoutError: Locator.fill: Timeout 5000ms exceeded. \| waiting for get_by_label("Email address")` | valid; fails on release (bug above) |

## Flaky tests (not reported as bugs)

None.

## Needs human review

- `test_wrong_password.py::test_wrong_password` (gave_up): still fails on the baseline after 3 heal attempts. Error: `line 12: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`

## Memory

Memory was off for this run (`--no-memory`).

## Snapshot diff (baseline -> release)

- **sign-in / main**
  - `CHANGED: button "Sign in"  ->  button (no accessible name)`
- **dashboard / main**
  - `REMOVED: heading "Upcoming appointments" [level=2]`
- **dashboard / lab-results-frame**
  - `REMOVED: heading "Lab results" [level=1]`

Trace: `runs/eval-20261013-114206-r1-buggy/trace.jsonl`
