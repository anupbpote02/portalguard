# PortalGuard eval (real, 1 repeat(s), 2026-10-13T11:42:06)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 100% |
| Precision (reported bugs that are real) | 100% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed (buggy + good) | 7 |
| LLM steps (buggy + good) | 30 |
| Tokens (buggy + good) | 152,009 |
| Cost (buggy + good) | $0.0683 |
| Duration (buggy + good) | 385.5s |
| Gate (recall >= 1.0, false alarms <= 0) | PASS |

## Per planted bug

| Bug | Type | Found in | Reported as |
|---|---|---|---|
| BUG-1 "Sign in" button has no accessible name (icon only) | accessibility | 1/1 runs | CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main) |
| BUG-2 "Upcoming appointments" heading removed | accessibility | 1/1 runs | REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main) |
| BUG-3 "Lab results" heading removed (inside the iframe) | accessibility | 1/1 runs | REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame) |
| BUG-4 "Download PDF" does nothing (no file, no message) | functional | 1/1 runs | Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf) |

## Per run

| Repeat | Release | Stop | Bugs reported | Recall | Precision | Healed | Steps | Tokens | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | buggy | `done` | 4 | 100% | 100% | 7 | 21 | 122,362 | $0.0537 | 336.7s |
| 1 | good | `done` | 0 | n/a | n/a | 0 | 9 | 29,647 | $0.0146 | 48.8s |

## Misses and false alarms

None.

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
