# PortalGuard eval (real, 1 repeat(s), 2026-10-13T11:30:33)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 75% |
| Precision (reported bugs that are real) | 60% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed (buggy + good) | 2 |
| LLM steps (buggy + good) | 17 |
| Tokens (buggy + good) | 36,547 |
| Cost (buggy + good) | $0.0176 |
| Duration (buggy + good) | 112.6s |
| Gate (recall >= 1.0, false alarms <= 0) | FAIL |

## Per planted bug

| Bug | Type | Found in | Reported as |
|---|---|---|---|
| BUG-1 "Sign in" button has no accessible name (icon only) | accessibility | 1/1 runs | CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main) |
| BUG-2 "Upcoming appointments" heading removed | accessibility | 1/1 runs | REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main) |
| BUG-3 "Lab results" heading removed (inside the iframe) | accessibility | 1/1 runs | REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame) |
| BUG-4 "Download PDF" does nothing (no file, no message) | functional | 0/1 runs | missed |

## Per run

| Repeat | Release | Stop | Bugs reported | Recall | Precision | Healed | Steps | Tokens | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | buggy | `done` | 5 | 75% | 60% | 0 | 9 | 19,450 | $0.0095 | 79.6s |
| 1 | good | `done` | 0 | n/a | n/a | 2 | 8 | 17,097 | $0.0081 | 33.0s |

## Misses and false alarms

- repeat 1, missed: BUG-4
- repeat 1, false positive (buggy): See upcoming appointments journey broken (test_diff_appointments_labresults.py::test_sign_in_button_accessible_name)
- repeat 1, false positive (buggy): View lab results journey broken (test_lab_results.py::test_lab_results_download_pdf)

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
