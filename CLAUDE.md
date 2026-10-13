# PortalGuard

An AI QE agent that tests each release of a hospital patient portal. It compares accessibility
(aria) snapshots of the main page **and every iframe** against the last good release, writes and
runs Playwright tests, heals its own broken tests, reports real bugs, and runs in CI.

Context: take-home project for a Forward Deployed Engineer / QE / Azure DevOps role. The client is
a (fictional) top hospital. Keep the project **simple and readable**. No LangChain/LangGraph: a
custom harness is the point.

## Working style

- Build ONE step at a time, only when asked.
- After each step: explain how to verify it and suggest a commit message.
- Use `--mock` mode by default (no API key, $0).
- Briefly explain key design decisions so they can be explained in an interview.

## Stack

Python 3.12, Playwright (sync API), pytest (+ pytest-playwright), openai SDK, python-dotenv,
plain HTML/CSS/JS.

## Requirements to cover

- **QE loop with Playwright:** write -> run -> triage -> heal tests.
- **Agent:** `gpt-4.1-mini` with OpenAI tool calling.
- **Harness:** `MAX_STEPS=25`, `MAX_TOKENS=150000`, `MAX_COST_USD=0.25`, URL allowlist
  (localhost only), tool argument validation, JSONL trace log, `--mock` mode (scripted fake LLM,
  $0, no key).
- **Memory:**
  - Short-term: big snapshots saved to disk; only summaries are sent to the model.
  - Long-term: `memory/memory.json` (baseline path, working selectors, reported bugs, flaky tests).
- **Evals:** score agent vs planted bugs (recall, precision, false alarms, tests healed, steps, cost).
- **iFrame a11y DOM comparison:** Playwright `aria_snapshot()` of body + every frame, diffed vs baseline.
- **CI:** GitHub Actions (live) + `azure-pipelines.yml` (for the client's Azure DevOps).
- **README:** decisions, tradeoffs, known limitations, next steps.

## Healthcare rules

- Synthetic data only: patient **"Jordan Rivera"**, MRN **"TEST-000123"**.
- The agent can only open `localhost` URLs.
- API key only from `.env` (gitignored).
- README notes that a real deployment would use Azure OpenAI under a HIPAA BAA with no data sharing.

## Structure

```
portal/
  good/     index.html (sign-in), dashboard.html, lab-results.html (loaded in iframe)
  buggy/    same pages, with 4 planted bugs
agent/
  harness.py   loop, budgets, allowlist, arg validation, trace log, tool schemas, system prompt
  llm.py       OpenAILLM (gpt-4.1-mini) + MockLLM and mock scenarios (qe, guardrails, runaway)
  triage.py    deterministic verdicts per failing test (baseline = oracle), heal limits
  report.py    runs/<id>/report.md from harness state, never from model text
  tools.py     snapshot_page, compare_snapshots, write_test, run_tests
  memory.py    long-term memory/memory.json: baseline, selectors, selector fixes, known bugs, flaky
  main.py      CLI entry point (--mock, --release ...)
  diff_releases.py  no-LLM helper: snapshot good + buggy and print the diff
  demo_tools.py     no-LLM helper: write one sample test, run it on good (pass) + buggy (fail)
tests/generated/        tests written by the agent (test_*.py only, gitignored)
tests/generated/conftest.py  human-written: patient + signed_in fixtures, localhost-only route guard, 5s timeouts
tests/unit/             triage, memory and eval-matching unit tests (no browser): python -m pytest tests/unit
pytest.ini              pythonpath=., default base_url = good release
memory/memory.json      long-term memory (gitignored runtime state; memory/baselines/ holds the
                        saved baseline snapshot; CI persists memory/ as a cache/artifact)
runs/<timestamp>/       trace.jsonl, snapshots/, test-results/, tests/ (copy), report.md   (gitignored)
evals/expected_bugs.json  answer key: 4 bugs, each with deterministic substring match rules
evals/run_eval.py         python -m evals.run_eval [--real] [--repeat N]; writes results.json/.md (gitignored)
.github/workflows/qe.yml
azure-pipelines.yml
requirements.txt, .env.example, README.md
```

## Portal

Served with: `python -m http.server 8000 --directory portal`
(good release at `http://localhost:8000/good/`, buggy at `http://localhost:8000/buggy/`).

"Harbor General Patient Portal":

- `portal/test-users.json`: single source of truth for 3 synthetic test users (Jordan Rivera
  `TEST-000123`, Casey Morgan `TEST-000456`, Riley Nguyen `TEST-000789`), each with email,
  password, name, MRN, 2 appointments and 3 lab results. Used by both releases and by tests.
- `index.html`: labeled email + password fields, "Sign in" button. Client-side demo login (not real
  auth): valid test user -> dashboard (email kept in sessionStorage); wrong credentials -> error in
  `role="alert"`, stays on sign-in.
- `dashboard.html`: "Welcome, <name>", MRN, "Upcoming appointments" heading + 2 appointments,
  `<iframe id="lab-results-frame" title="Lab results">` loading `lab-results.html`. No session ->
  redirect to sign-in.
- `lab-results.html`: "Lab results" heading, table of the user's 3 results, "Download PDF" button
  that downloads a small client-generated PDF `lab-results-<MRN>.pdf` (marked DEMO DATA /
  NOT A REAL PATIENT) **and** shows "Download started" in a `role="status"` region. iframe is tall
  enough to show all of it without scrolling.
- Content is rendered by JS after a fetch, so snapshots/tests must sign in first and wait for content.
- Download tests must use Playwright `page.expect_download()` and check `suggested_filename`;
  the status text alone is not proof of a download.
- Snapshot coverage: the aria diff of the signed-in dashboard (+ iframe) only catches BUG-2/BUG-3.
  `snapshot_page` must also snapshot the sign-in page (BUG-1), and BUG-4 is functional, so it's only
  caught by a test (it doesn't change the aria tree).

### Planted bugs (buggy release only)

| ID    | Bug                                                     | Type       | File                          |
|-------|---------------------------------------------------------|------------|-------------------------------|
| BUG-1 | "Sign in" button has no accessible name (icon only)     | a11y       | index.html                    |
| BUG-2 | "Upcoming appointments" heading removed                 | a11y       | dashboard.html                |
| BUG-3 | "Lab results" heading removed                           | a11y       | lab-results.html (in iframe)  |
| BUG-4 | "Download PDF" does nothing (no file, no message)       | functional | lab-results.html (in iframe)  |

`diff -r portal/good portal/buggy` shows exactly these 4 changes and nothing else. The buggy
files carry no "BUG" comments, so they look like a real release.

## Harness (agent/harness.py, run with `python -m agent.main --mock [--scenario qe|guardrails|runaway]`)

- Budgets checked BEFORE every LLM call: MAX_STEPS=25 (LLM calls), MAX_TOKENS=150000 (prompt +
  completion summed), MAX_COST_USD=0.25, MAX_BLOCKED_CALLS=3 (policy_violation). One call can
  overshoot by its own size; `max_completion_tokens=4000` bounds that.
- Every tool call: known tool -> JSON args -> schema (no unknown/missing args, strings, maxLength,
  pattern) -> localhost allowlist on `url`. Rejections go back to the model as `{"error": ...}`;
  the run continues (except 3 blocked URLs). Tool exceptions never crash the run.
- Harness binds what the model must not control: snapshot/results folders, and run_tests' base_url
  (= release under test). Tool results over 6000 chars are truncated.
- Trace events (JSONL, flushed per line): run_start, llm_call (tokens, cost, totals), tool_call
  (args, status ok/invalid/blocked/error, result, duration_ms), budget_stop, llm_error, run_end.
- Each run clears tests/generated/test_*.py first and copies the written tests into the run folder.
- Exit codes: 0 done, 1 llm_error / missing key, 2 portal not reachable, 3 budget or policy stop.
- Prices: gpt-4.1-mini $0.40 in / $1.60 out per 1M tokens (verify); mock is $0 with ~4 chars/token.

## Triage + healing (agent/triage.py)

After every model `run_tests` on the release, the harness triages each failing test itself:
1. Run it on the **baseline**. Fails there too -> `broken_test` (the test is wrong). The model gets
   baseline_error + baseline_has (frame ids, headings, buttons) and heals with write_test. Max 3
   attempts per file, then `gave_up` (Needs human review) and further writes are refused.
2. Passes on baseline -> rerun on release (FLAKY_RERUNS=1). Passes now -> `flaky`, not reported.
3. Fails 2/2 on release -> `real_bug` if a diff line mentions a name the locator waited for
   (accessibility) or the file maps to a journey (functional); else `unconfirmed`.
- write_test on a file proving a real_bug is refused (the agent can't heal a bug away).
- Same code + decided verdict -> no extra runs. Passing tests cost no extra runs.
- Why baseline first: a wrong selector like `#labs-frame` waits for name="Lab results", which also
  matches the BUG-3 diff line. Name matching alone would call a broken test a bug.
- Mock qe: lab results test starts with `#labs-frame`, heal 1 `#lab_results_frame` (still wrong),
  heal 2 `#lab-results-frame` -> valid -> real_bug BUG-3. Result: 4 real bugs, 1 healed (2/3).
- report.md: summary counts, bugs (type, journey, test, failure, diff line, repro command), healed,
  flaky, needs-review, full snapshot diff, steps/tool calls/harness runs/tokens/cost/duration.

## Memory (agent/memory.py)

- Short-term: snapshots and pytest logs on disk in runs/<id>/; the model only sees summaries.
- Long-term `memory/memory.json`, written by the harness at run end, only from harness-verified
  facts: `baselines` (copy of the baseline snapshot in memory/baselines/ + `passing_tests`: test id ->
  code hash that passed on that baseline), `working_selectors`, `selector_fixes` (bad -> good,
  learned by diffing a healed test's failing versions vs its final version: exactly one locator
  removed + one added), `reported_bugs` (fingerprint = diff line, or journey + error shape with
  digits normalized), `flaky_tests`, `run_count`, `runs` (last 20).
- On a later run: the saved baseline is pre-loaded as label "baseline" and any snapshot_page of the
  baseline URL is served from memory (no browser); triage skips the baseline run for a test whose
  code hash already passed on that baseline; write_test swaps known-bad locators (result has
  `memory_fixes`; triage still verifies on the baseline); real bugs matching a fingerprint are
  KNOWN (report shows first run + times seen) vs NEW. The model also gets a short briefing in the
  first user message.
- Flags: `--no-memory` (evals: reproducible), `--reset-memory`, `--refresh-baseline`. Known
  limitation: baseline is keyed by URL only; a real pipeline should key it by the good build id.
- Mock qe is reactive: skips the baseline snapshot when briefed, heals only while broken_test.
  Run 1: 9 steps, ~100s, 4 new bugs, 1 healed. Run 2: 5 steps, ~54s, 4 known bugs, 0 heals.

## Evals (evals/run_eval.py)

- Per repeat: agent on buggy, then on good, both with memory OFF (cold, comparable runs). Calls
  Harness directly; starts the portal on a thread if it isn't running.
- Matching (no LLM judge): a reported bug (harness `summary["bugs"]`: title, category, journey,
  diff_evidence, errors) matches an expected bug if any rule holds: `where` + `diff` substrings in
  one diff line, or exact `journey` + `error` substring. First match in answer-key order wins;
  second hit on the same bug = duplicate (not a false positive); no hit = false positive.
- Metrics: recall, precision ((TP + duplicates) / reported), type accuracy, false alarms on good,
  tests healed, steps, tokens, cost, duration. Mean over repeats; misses listed per run.
- Gate: exit 1 if recall < --min-recall (1.0) or false alarms > --max-false-alarms (0); exit 2 if
  --real has no key. Mock result: 100% recall/precision/type, 0 false alarms, 2 healed, 18 steps.

## Tools (exposed to the model)

- `snapshot_page(url, label)`: signs in as the first test user and snapshots the `sign-in` and
  `dashboard` pages (body + every iframe, keyed by iframe id). Waits for networkidle, then until two
  aria snapshots in a row match. Navigates by stable ids + Enter (not role/name) so a11y bugs can't
  block capture. Saves full JSON to disk; returns per-frame summary (node count, headings, buttons),
  JS errors, and any error (HTTP 404, connection refused, timeout) instead of raising.
- `compare_snapshots(baseline, new)`: labels or .json paths. Returns REMOVED / ADDED / CHANGED lines
  per `page / frame` (max 20 each), flags controls with no accessible name, new JS errors.
- `write_test(filename, code)`: only `test_[a-z0-9_]+.py`, only inside `tests/generated/`. AST checks
  before writing: syntax, imports limited to re/json/pytest/playwright.sync_api, no exec/eval/open/
  __import__/dunder access, must define a test_* function, max 20 KB. A guardrail, not a sandbox.
- `run_tests(filename=None)`: model-facing arg is only the optional filename; `base_url` (release
  under test) is bound by the harness. Runs pytest with `--base-url`, 120s timeout, reads JUnit XML
  for pass/fail. Each failure is one line: test line number, error, and the locator Playwright was
  waiting for. Full log saved to the run folder.
- Tool convention: bad arguments raise ValueError (harness returns it to the model as an error);
  environment problems (server down, timeout) come back in an `error` field.
- Generated tests use fixtures `page`, `base_url`, `patient` (first test user), `patients`, and should
  sign in by label + Enter unless the test is about the sign-in button, so each test fails for one reason.

## QE loop

1. Snapshot baseline (good) + release (buggy).
2. Compare snapshots.
3. Write tests for key journeys (sign in, see appointments, view lab results, download PDF) and
   for each diff.
4. Run tests.
5. Triage failures:
   - Test is wrong -> heal it (max 3 tries).
   - Fails then passes -> flaky (record in memory, don't report).
   - Fails consistently -> real bug.
6. Write `report.md`.

**Principle: "the model proposes, the harness decides."** Pass/fail comes from Playwright
assertions, not from the LLM.

In mock mode, write one test with a wrong selector first so healing is visible.

## Build steps

1. Setup: CLAUDE.md, folder structure, requirements.txt, .env.example, .gitignore. ✅
2. Portal (good). ✅
3. Portal (buggy, 4 planted bugs). ✅
4. Tools: snapshot_page, compare_snapshots, write_test, run_tests + demo scripts. ✅
4b. Harness + mock LLM + main.py. ✅
5. Memory. ✅
6. Healing / triage loop + report.md. ✅
7. Evals. ✅
8. CI (GitHub Actions + Azure Pipelines).
9. README.
