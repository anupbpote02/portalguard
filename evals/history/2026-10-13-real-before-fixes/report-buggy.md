# PortalGuard report: run eval-20261013-113033-r1-buggy

- **Release under test:** http://localhost:8000/buggy/
- **Baseline (last good release):** http://localhost:8000/good/
- **Model:** gpt-4.1-mini  |  **Stop reason:** `done`
- Synthetic test data only. Verdicts come from Playwright assertions run by the harness (release runs, reruns, baseline runs), not from the model.

## Summary

| Real bugs | New | Known | Healed tests | Flaky (not reported) | Unconfirmed | Broken tests left |
|---|---|---|---|---|---|---|
| 5 | 5 | 0 | 0 | 0 | 0 | 1 |

| LLM steps | Tool calls | Harness test runs | Tokens | Cost | Duration |
|---|---|---|---|---|---|
| 9 | 9 (0 blocked) | 15 | 19,450 | $0.0095 | 79.6s |

## Bugs found

### 1. [NEW] CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** Sign in
- **Evidence:**
  - Test `test_sign_in.py::test_sign_in_page_ui`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 13: assert False | +  where False = is_visible() | +    where is_visible = <Locator frame=<Frame name= url='http://localhost:8000/buggy/'> selector='internal:role=button[name="Sign in"i]'>.is_visible`
  - Snapshot diff: `sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)`
- **Reproduce:** `python -m pytest tests/generated/test_sign_in.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-113033-r1-buggy/tests/`)

### 2. [NEW] REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_diff_appointments_labresults.py::test_missing_upcoming_appointments_heading`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 9: assert False | +  where False = is_visible() | +    where is_visible = <Locator frame=<Frame name= url='http://localhost:8000/buggy/dashboard.html'> selector='internal:role=heading[name="Upcoming appointments"i]'>.is_visible`
  - Test `test_upcoming_appointments.py::test_upcoming_appointments_visible`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 9: assert False | +  where False = is_visible() | +    where is_visible = <Locator frame=<Frame name= url='http://localhost:8000/buggy/dashboard.html'> selector='internal:role=heading[name="Upcoming appointments"i]'>.is_visible`
  - Snapshot diff: `dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]`
- **Reproduce:** `python -m pytest tests/generated/test_diff_appointments_labresults.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-113033-r1-buggy/tests/`)

### 3. [NEW] REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame)

- **Status:** NEW
- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_diff_appointments_labresults.py::test_missing_lab_results_heading`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 16: assert False | +  where False = is_visible() | +    where is_visible = <Locator frame=<Frame name= url='http://localhost:8000/buggy/dashboard.html'> selector='#lab-results-frame >> internal:control=enter-frame >> internal:role=heading[name="Lab results"i]'>.is_visible`
  - Test `test_lab_results.py::test_lab_results_heading_and_button`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 10: assert False | +  where False = is_visible() | +    where is_visible = <Locator frame=<Frame name= url='http://localhost:8000/buggy/dashboard.html'> selector='#lab-results-frame >> internal:control=enter-frame >> internal:role=heading[name="Lab results"i]'>.is_visible`
  - Snapshot diff: `dashboard / lab-results-frame: REMOVED: heading "Lab results" [level=1]`
- **Reproduce:** `python -m pytest tests/generated/test_diff_appointments_labresults.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-113033-r1-buggy/tests/`)

### 4. [NEW] See upcoming appointments journey broken (test_diff_appointments_labresults.py::test_sign_in_button_accessible_name)

- **Status:** NEW
- **Type:** functional  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_diff_appointments_labresults.py::test_sign_in_button_accessible_name`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 24: AssertionError: assert (None == 'Sign in' or None == 'Sign in' or '\n          ...   \n        ' == 'Sign in' | +  where None = get_attribute('name') | +    where get_attribute = <Locator frame=<Frame name= url='http://localhost:8000/buggy/'> selector='internal:role=button'>.get_attribute | +  and   None = get_attribute('aria-label') | +    where get_attribute = <Locator frame=<Frame name`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest tests/generated/test_diff_appointments_labresults.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-113033-r1-buggy/tests/`)

### 5. [NEW] View lab results journey broken (test_lab_results.py::test_lab_results_download_pdf)

- **Status:** NEW
- **Type:** functional  |  **Journey:** View lab results
- **Evidence:**
  - Test `test_lab_results.py::test_lab_results_download_pdf`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 18: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest tests/generated/test_lab_results.py --base-url http://localhost:8000/buggy/` (a copy of the test is kept in `runs/eval-20261013-113033-r1-buggy/tests/`)

## Healed tests

None.

## Flaky tests (not reported as bugs)

None.

## Needs human review

- `test_sign_in.py::test_sign_in_functionality` (broken_test): fails on the baseline (last good release) too, so the test is wrong. Error: `line 20: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`

## Memory

Memory was off for this run (`--no-memory`).

## Snapshot diff (baseline -> release)

- **sign-in / main**
  - `CHANGED: button "Sign in"  ->  button (no accessible name)`
- **dashboard / main**
  - `REMOVED: heading "Upcoming appointments" [level=2]`
- **dashboard / lab-results-frame**
  - `REMOVED: heading "Lab results" [level=1]`

Trace: `runs/eval-20261013-113033-r1-buggy/trace.jsonl`
