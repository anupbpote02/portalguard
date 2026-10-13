# PortalGuard eval (real, 3 repeat(s), 2026-10-13T11:49:09)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 92% |
| Precision (reported bugs that are real) | 100% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed (buggy + good) | 23 |
| LLM steps (buggy + good) | 104 |
| Tokens (buggy + good) | 437,771 |
| Cost (buggy + good) | $0.1940 |
| Duration (buggy + good) | 1053.2s |
| Gate (recall >= 1.0, false alarms <= 0) | FAIL |

## Per planted bug

| Bug | Type | Found in | Reported as |
|---|---|---|---|
| BUG-1 "Sign in" button has no accessible name (icon only) | accessibility | 3/3 runs | CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main) |
| BUG-2 "Upcoming appointments" heading removed | accessibility | 3/3 runs | REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main) |
| BUG-3 "Lab results" heading removed (inside the iframe) | accessibility | 3/3 runs | REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame) |
| BUG-4 "Download PDF" does nothing (no file, no message) | functional | 2/3 runs | Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf) |

## Per run

| Repeat | Release | Stop | Bugs reported | Recall | Precision | Healed | Steps | Tokens | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | buggy | `done` | 3 | 75% | 100% | 6 | 15 | 54,081 | $0.0240 | 164.0s |
| 1 | good | `done` | 0 | n/a | n/a | 3 | 12 | 49,695 | $0.0227 | 75.8s |
| 2 | buggy | `done` | 4 | 100% | 100% | 7 | 12 | 54,002 | $0.0252 | 225.1s |
| 2 | good | `done` | 0 | n/a | n/a | 4 | 17 | 66,993 | $0.0300 | 97.5s |
| 3 | buggy | `done` | 4 | 100% | 100% | 1 | 25 | 122,288 | $0.0524 | 329.1s |
| 3 | good | `llm_error` | 0 | n/a | n/a | 2 | 23 | 90,712 | $0.0397 | 161.7s |

## Misses and false alarms

- repeat 1, missed: BUG-4

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
