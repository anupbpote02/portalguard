# PortalGuard eval (real, 5 repeat(s), 2026-10-13T12:15:21)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 95% |
| Precision (reported bugs that are real) | 100% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed (buggy + good) | 14 |
| LLM steps (buggy + good) | 175 |
| Tokens (buggy + good) | 758,498 |
| Cost (buggy + good) | $0.3399 |
| Duration (buggy + good) | 1408.5s |
| Gate (recall >= 1.0, false alarms <= 0) | FAIL |

## Per planted bug

| Bug | Type | Found in | Reported as |
|---|---|---|---|
| BUG-1 "Sign in" button has no accessible name (icon only) | accessibility | 5/5 runs | CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main) |
| BUG-2 "Upcoming appointments" heading removed | accessibility | 5/5 runs | REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main) |
| BUG-3 "Lab results" heading removed (inside the iframe) | accessibility | 4/5 runs | REMOVED: heading "Lab results" [level=1] (dashboard / lab-results-frame) |
| BUG-4 "Download PDF" does nothing (no file, no message) | functional | 5/5 runs | Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf) |

## Per run

| Repeat | Release | Stop | Bugs reported | Recall | Precision | Healed | Steps | Tokens | Cost | Duration |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | buggy | `done` | 4 | 100% | 100% | 1 | 16 | 54,324 | $0.0244 | 178.7s |
| 1 | good | `done` | 0 | n/a | n/a | 3 | 20 | 114,014 | $0.0504 | 135.8s |
| 2 | buggy | `done` | 4 | 100% | 100% | 2 | 17 | 58,529 | $0.0257 | 187.8s |
| 2 | good | `done` | 0 | n/a | n/a | 1 | 20 | 96,744 | $0.0431 | 126.0s |
| 3 | buggy | `done` | 3 | 75% | 100% | 1 | 11 | 36,965 | $0.0169 | 133.6s |
| 3 | good | `done` | 0 | n/a | n/a | 2 | 9 | 25,671 | $0.0122 | 63.6s |
| 4 | buggy | `done` | 4 | 100% | 100% | 0 | 16 | 55,466 | $0.0258 | 134.5s |
| 4 | good | `done` | 0 | n/a | n/a | 1 | 21 | 84,119 | $0.0366 | 122.3s |
| 5 | buggy | `max_steps` | 4 | 100% | 100% | 1 | 25 | 128,631 | $0.0585 | 184.1s |
| 5 | good | `done` | 0 | n/a | n/a | 2 | 20 | 104,035 | $0.0462 | 142.1s |

## Misses and false alarms

- repeat 3, missed: BUG-3

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
