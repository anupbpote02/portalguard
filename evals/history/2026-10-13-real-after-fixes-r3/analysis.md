# Real eval after fixes: gpt-4.1-mini, 3 repeats

Run: 2026-10-13, `python -m evals.run_eval --real --repeat 3` (memory off). Total cost $0.194 for
6 agent runs (3 x buggy + 3 x good).

| Metric | Before fixes (1 run) | After fixes (1 run) | After fixes (mean of 3) |
|---|---|---|---|
| Recall | 75% | 100% | 92% (100%, 100%, 75%) |
| Precision | 60% | 100% | 100% |
| False alarms on good | 0 | 0 | 0 |
| Cost per buggy + good pair | $0.018 | $0.068 | $0.065 |

## Remaining problems (model behaviour + harness robustness, not labelling)

1. **Repeat 1 missed BUG-4 because the model never wrote a download test.** Its files were
   sign_in, appointments, lab_results and diff_check (see `repeat1-buggy-agent-tests/`); the lab test
   only checks the Download PDF button is visible. The harness accepted the final answer without
   checking that every required journey had a test.
2. **Repeat 3 on the good release ended with `llm_error` (APIConnectionError) at step 23.** A
   transient network error; the harness has no retry. It still reported 0 bugs, but the run was
   cut short.
3. **Runs are close to the budget.** Repeat 3 on buggy used exactly 25/25 steps and 122k/150k
   tokens. Most of the cost is healing first-draft tests (e.g. `get_by_role("button", "Sign in")`
   with the name passed positionally) and guessing form labels that `baseline_has` doesn't list.
