# PortalGuard report: run eval-20261013-121521-r3-buggy

- **Release under test:** http://localhost:8000/buggy/
- **Baseline (last good release):** http://localhost:8000/good/
- **Model:** gpt-4.1-mini  |  **Stop reason:** `done`
- Synthetic test data only. Verdicts come from Playwright assertions run by the harness (release runs, reruns, baseline runs), not from the model.

## Summary

| Real bugs | New | Known | Healed tests | Flaky (not reported) | Unconfirmed | Broken tests left |
|---|---|---|---|---|---|---|
| 3 | 3 | 0 | 1 | 0 | 0 | 1 |

| LLM steps | Tool calls | Harness test runs | Tokens | Cost | Duration |
|---|---|---|---|---|---|
| 11 | 15 (0 blocked) | 11 | 36,965 | $0.0169 | 133.6s |

## Bugs found

### 1. [NEW] CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** Sign in
- **Evidence:**
  - Test `test_sign_in.py::test_sign_in`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 12: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`
  - Test `test_wrong_password.py::test_wrong_password`: passed on baseline, failed on release 2/2 runs (after healing)
  - Failure: `line 12: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`
  - Snapshot diff: `sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)`
- **Reproduce:** `python -m pytest tests/generated/test_sign_in.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-121521-r3-buggy/tests/`)

### 2. [NEW] REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_appointments.py::test_appointments`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 6: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Snapshot diff: `dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]`
- **Reproduce:** `python -m pytest tests/generated/test_appointments.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-121521-r3-buggy/tests/`)

### 3. [NEW] Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)

- **Status:** NEW
- **Type:** functional  |  **Journey:** Download lab results PDF
- **Evidence:**
  - Test `test_download_pdf.py::test_download_pdf`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 7: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest tests/generated/test_download_pdf.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-121521-r3-buggy/tests/`)

## Healed tests

| Test | Attempts | Original error | Now |
|---|---|---|---|
| `test_wrong_password.py::test_wrong_password` | 1/3 | `line 12: TimeoutError: Locator.click: Timeout 5000ms exceeded. \| waiting for get_by_role("button", name="Sign in")` | valid; fails on release (bug above) |

## Flaky tests (not reported as bugs)

None.

## Needs human review

- `test_lab_results.py::test_lab_results` (broken_test): fails on the baseline (last good release) too, so the test is wrong. Error: `line 9: AssertionError: Locator expected to have count '3' | Actual value: 0 | waiting for locator("#lab-results-frame").content_frame.get_by_role("listitem")`

## Journey coverage

- Covered: appointments, download_pdf, lab_results, sign_in, wrong_password
- Missing: none
- Coverage reminders sent to the model: 0; LLM API retries: 0

## Memory

Memory was off for this run (`--no-memory`).

## Snapshot diff (baseline -> release)

- **sign-in / main**
  - `CHANGED: button "Sign in"  ->  button (no accessible name)`
- **dashboard / main**
  - `REMOVED: heading "Upcoming appointments" [level=2]`
- **dashboard / lab-results-frame**
  - `REMOVED: heading "Lab results" [level=1]`

Trace: `runs/eval-20261013-121521-r3-buggy/trace.jsonl`
