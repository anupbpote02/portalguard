# Real eval after the second round of fixes: gpt-4.1-mini, 5 repeats

Run: 2026-10-13, `python -m evals.run_eval --real --repeat 5` (memory off). Fixes in this round:
journey coverage check (write_test + final answer), retries for transient API errors, textbox/link
labels in snapshot hints, `name=` keyword guidance. Answer key and scoring rules unchanged.
Total cost $0.340 for 10 agent runs (5 x buggy + 5 x good).

| Metric | Before fixes (1 run) | Round 1 (mean of 3) | Round 2 (mean of 5) |
|---|---|---|---|
| Recall | 75% | 92% | **95%** (100, 100, 75, 100, 100) |
| Precision | 60% | 100% | **100%** |
| False alarms on good | 0 | 0 | **0** |
| BUG-4 (download) found | 0/1 | 2/3 | **5/5** |
| Runs ended by an API error | 0 | 1 | **0** |
| Cost per buggy + good pair | $0.018 | $0.065 | $0.068 |

The coverage check fixed the BUG-4 miss (5/5). No runs hit an API error.

## Remaining problems

1. **Repeat 3 missed BUG-3: the model healed the evidence away.** Its first lab test asserted the
   "Lab results" heading (correct, and would have caught BUG-3) but also used
   `get_by_role("listitem")`; the results are table rows, so it failed on the baseline -> broken_test.
   The model misread the cause, removed the heading assertion ("missing in baseline, so do not check
   it"), still failed on listitem, then tried a visibility-only test (rejected by the coverage check)
   and finished with the test still broken. See `repeat3-lab-results-test-versions.md`.
   - The coverage check counted lab_results as covered because a file had been accepted, even though
     its test never passed on the baseline. "Covered" should mean "has a test that passed on the
     baseline".
   - The lock only protects tests that already proved a bug. A broken test's valid assertions
     (the heading) can still be deleted during healing.
2. **Coverage rules cost steps when the model doesn't know the page structure.** 41 rejections across
   10 runs: appointments 21, lab_results 14, wrong_password 6. The model guessed data shapes
   (`appt['date']`, listitems for lab rows) because the prompt doesn't say that appointments are list
   items of plain strings and lab results are table rows with test/result/range/date. Repeat 5 on
   buggy hit max_steps (25) with appointments and lab_results still uncovered, but its diff_check
   tests had already caught all 4 bugs.
3. **Good-release runs use the most steps** (20 to 21 in 4 of 5 repeats) satisfying coverage, with
   0 bugs to find. Fine for correctness, but it's where the cost goes.
