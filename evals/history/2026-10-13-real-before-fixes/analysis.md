# First real eval: gpt-4.1-mini, before harness fixes

Run: 2026-10-13, `python -m evals.run_eval --real` (1 repeat, memory off). Commit `1f50f92`.
Files here: `results.json` / `results.md` (eval output), `report-buggy.md` (agent report on the buggy
release), `agent-tests/` (the tests gpt-4.1-mini wrote).

| Metric | Value |
|---|---|
| Recall | 75% (BUG-1, BUG-2, BUG-3 found; BUG-4 "missed") |
| Precision | 60% (5 reported, 3 matched, 2 false positives) |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Steps / tokens / cost | 17 / 36,547 / $0.0176 |
| Gate | FAIL |

## What actually happened

The model's tests caught all four planted bugs. The points were lost in the harness's deterministic
labelling around those tests, not in the model's testing.

1. **Journey guessed from the file name (cost: BUG-4 missed + 1 false positive).**
   The model put its download test in `test_lab_results.py`. It failed exactly as BUG-4 should
   (`waiting for event "download"`), but triage labelled the journey "View lab results" from the
   filename, so the answer key's BUG-4 rule (journey "Download lab results PDF") didn't match.
2. **Diff evidence only read from the error text (cost: 1 false positive).**
   `test_sign_in_button_accessible_name` asserted `button.get_attribute("name") == "Sign in"`. The
   error has no `name="..."`, so it wasn't linked to the BUG-1 diff line and became a separate,
   unmatched "functional" bug instead of a duplicate of BUG-1.
3. **Real-bug lock was per file (cost: a test left broken).**
   `test_sign_in_functionality` was correctly triaged `broken_test` (it fails on the baseline). The
   heal was refused because another test in the same file proves BUG-1, so it stayed broken.
4. **Prompt didn't require auto-waiting assertions (cause of the broken test).**
   The model wrote `assert locator.is_visible()`, which checks once without waiting, so the
   "Welcome" heading (rendered after a fetch) wasn't there yet even on the good release.

## Fixes (answer key and scoring rules unchanged)

1. `write_test` takes a required `journey` from a fixed list (`sign_in`, `wrong_password`,
   `appointments`, `lab_results`, `download_pdf`, `diff_check`); triage uses it instead of guessing.
2. Diff evidence also uses quoted strings on the test's failing line (only that line, so a test that
   signs in with the button and then fails on download isn't blamed on BUG-1).
3. The lock is per test function: a rewrite is refused only if it changes or removes a test that
   proves a real bug; other tests in the same file can still be healed.
4. System prompt requires `expect(...)` assertions (auto-wait) and one journey per file.
