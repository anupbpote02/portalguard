"""The agent loop. "The model proposes, the harness decides."

The model only chooses which tool to call with which arguments. The harness:
  - enforces budgets (steps, tokens, cost) before every LLM call,
  - validates every tool call (known tool, JSON args, schema, localhost-only URLs),
  - binds the arguments the model must not control (output folders, release under test),
  - writes every event to runs/<timestamp>/trace.jsonl.
"""

import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import tools

MAX_STEPS = 25            # LLM calls per run
MAX_TOKENS = 150_000      # prompt + completion, summed over all calls
MAX_COST_USD = 0.25
MAX_BLOCKED_CALLS = 3     # off-allowlist URLs before the run is stopped as a policy violation
MAX_TOOL_RESULT_CHARS = 6_000

# USD per 1M tokens (input, output). Check current OpenAI pricing before relying on these.
PRICES_PER_1M = {"gpt-4.1-mini": (0.40, 1.60), "mock": (0.0, 0.0)}

SYSTEM_PROMPT = """You are PortalGuard, a QE agent testing a new release of the Harbor General patient portal.
All data is synthetic. You may only open localhost URLs.

Do this, in order:
1. snapshot_page the baseline (label "baseline") and the release (label "release").
2. compare_snapshots("baseline", "release").
3. write_test one file per key journey: sign in, see upcoming appointments, view lab results
   (inside iframe #lab-results-frame), download the lab results PDF. Add a test for each diff.
4. run_tests (it runs against the release). Then reply with a short summary and stop.

Test rules: Python, pytest + Playwright sync API, only import from playwright.sync_api / pytest / re / json.
Fixtures: page, base_url (ends with "/"), patient (dict: email, password, name, mrn, appointments,
labResults), signed_in (page already on the dashboard). Use get_by_role / get_by_label locators.
Use page.frame_locator("#lab-results-frame") for the lab results. Check downloads with
page.expect_download() and suggested_filename == f"lab-results-{patient['mrn']}.pdf".
Use signed_in unless the test is about signing in, so each test fails for one reason only."""

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "snapshot_page",
        "description": "Sign in to a portal release and save aria snapshots of every page and iframe. Returns a summary.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["url", "label"], "properties": {
            "url": {"type": "string", "maxLength": 200, "description": "Release base URL, localhost only"},
            "label": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,40}$"},
        }}}},
    {"type": "function", "function": {
        "name": "compare_snapshots",
        "description": "Diff two saved snapshots by label. Returns REMOVED/ADDED/CHANGED lines per page and frame.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["baseline", "new"], "properties": {
            "baseline": {"type": "string", "maxLength": 200},
            "new": {"type": "string", "maxLength": 200},
        }}}},
    {"type": "function", "function": {
        "name": "write_test",
        "description": "Write a pytest + Playwright test file into tests/generated/.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["filename", "code"], "properties": {
            "filename": {"type": "string", "pattern": "^test_[a-z0-9_]{1,60}\\.py$"},
            "code": {"type": "string", "maxLength": 20_000},
        }}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "Run generated tests against the release under test. Omit filename to run all.",
        "parameters": {"type": "object", "additionalProperties": False, "required": [], "properties": {
            "filename": {"type": "string", "pattern": "^test_[a-z0-9_]{1,60}\\.py$"},
        }}}},
]
SCHEMAS_BY_NAME = {s["function"]["name"]: s["function"]["parameters"] for s in TOOL_SCHEMAS}


class Trace:
    """Append-only JSONL log: one event per line, flushed immediately so a crash keeps the history."""

    def __init__(self, path: Path):
        self.path = path
        self.file = open(path, "a", encoding="utf-8", newline="\n")

    def write(self, event: str, **data) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event, **data}
        self.file.write(json.dumps(record) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def validate_args(schema: dict, args) -> str | None:
    """Minimal JSON-schema check for our flat string-only tool schemas. Returns an error or None."""
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    properties = schema["properties"]
    unknown = sorted(set(args) - set(properties))
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}; allowed: {', '.join(properties) or 'none'}"
    missing = [name for name in schema["required"] if name not in args]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    for name, value in args.items():
        rules = properties[name]
        if not isinstance(value, str):
            return f"'{name}' must be a string"
        if len(value) > rules.get("maxLength", 10_000):
            return f"'{name}' is longer than {rules['maxLength']} characters"
        if "pattern" in rules and not re.fullmatch(rules["pattern"], value):
            return f"'{name}' must match {rules['pattern']}"
    return None


class Harness:
    def __init__(self, llm, baseline_url: str, release_url: str, run_dir: Path | None = None,
                 max_steps: int = MAX_STEPS, max_tokens: int = MAX_TOKENS, max_cost_usd: float = MAX_COST_USD):
        tools.check_url(baseline_url)
        tools.check_url(release_url)
        self.llm = llm
        self.baseline_url = baseline_url
        self.release_url = release_url
        self.run_dir = run_dir or tools.REPO_ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.max_steps, self.max_tokens, self.max_cost_usd = max_steps, max_tokens, max_cost_usd

        self.steps = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0
        self.blocked_calls = 0
        self.tool_calls = 0

    # ------------------------------------------------------------ budgets

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def _budget_exceeded(self) -> str | None:
        """Checked BEFORE each LLM call. One call can overshoot by at most its own size."""
        if self.steps >= self.max_steps:
            return "max_steps"
        if self.total_tokens >= self.max_tokens:
            return "max_tokens"
        if self.cost_usd >= self.max_cost_usd:
            return "max_cost"
        if self.blocked_calls >= MAX_BLOCKED_CALLS:
            return "policy_violation"
        return None

    def _add_usage(self, reply) -> float:
        input_price, output_price = PRICES_PER_1M.get(self.llm.model, PRICES_PER_1M["gpt-4.1-mini"])
        call_cost = (reply.prompt_tokens * input_price + reply.completion_tokens * output_price) / 1_000_000
        self.prompt_tokens += reply.prompt_tokens
        self.completion_tokens += reply.completion_tokens
        self.cost_usd += call_cost
        return call_cost

    # ------------------------------------------------------------ tools

    def _execute(self, call) -> tuple[str, dict]:
        """Run one tool call. Returns (status, result). Never raises: errors go back to the model."""
        if call.name not in SCHEMAS_BY_NAME:
            return "invalid", {"error": f"unknown tool '{call.name}'; available: {', '.join(SCHEMAS_BY_NAME)}"}
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError as e:
            return "invalid", {"error": f"arguments are not valid JSON: {e}"}
        problem = validate_args(SCHEMAS_BY_NAME[call.name], args)
        if problem:
            return "invalid", {"error": problem}
        if "url" in args:
            try:
                tools.check_url(args["url"])
            except ValueError as e:
                self.blocked_calls += 1
                return "blocked", {"error": f"BLOCKED by harness: {e}"}

        # Arguments the model never controls: where files go, and which release tests run against.
        snapshots = self.run_dir / "snapshots"
        bound = {
            "snapshot_page": lambda: tools.snapshot_page(args["url"], args["label"], snapshot_dir=snapshots),
            "compare_snapshots": lambda: tools.compare_snapshots(args["baseline"], args["new"], snapshot_dir=snapshots),
            "write_test": lambda: tools.write_test(args["filename"], args["code"]),
            "run_tests": lambda: tools.run_tests(self.release_url, args.get("filename"),
                                                 results_dir=self.run_dir / "test-results"),
        }
        try:
            result = bound[call.name]()
        except ValueError as e:
            return "invalid", {"error": str(e)}
        except Exception as e:  # a tool bug must not crash the run
            return "error", {"error": f"{type(e).__name__}: {e}"}
        return ("error" if result.get("error") else "ok"), result

    # ------------------------------------------------------------ loop

    def run(self) -> dict:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        trace = Trace(self.run_dir / "trace.jsonl")
        started = time.monotonic()

        # Each run starts with an empty tests/generated/ (conftest.py is kept).
        removed = [p.name for p in tools.GENERATED_TESTS_DIR.glob("test_*.py")]
        for name in removed:
            (tools.GENERATED_TESTS_DIR / name).unlink()

        trace.write("run_start", model=self.llm.model, baseline_url=self.baseline_url,
                    release_url=self.release_url, run_dir=str(self.run_dir),
                    budgets={"max_steps": self.max_steps, "max_tokens": self.max_tokens,
                             "max_cost_usd": self.max_cost_usd, "max_blocked_calls": MAX_BLOCKED_CALLS},
                    cleared_old_tests=removed)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Baseline (last good release): {self.baseline_url}\n"
                                        f"Release under test: {self.release_url}"},
        ]
        stop_reason, final_message = None, None

        while True:
            stop_reason = self._budget_exceeded()
            if stop_reason:
                trace.write("budget_stop", step=self.steps, reason=stop_reason, **self._totals())
                break

            self.steps += 1
            try:
                reply = self.llm.complete(messages, TOOL_SCHEMAS)
            except Exception as e:
                stop_reason = "llm_error"
                trace.write("llm_error", step=self.steps, error=f"{type(e).__name__}: {e}")
                break
            call_cost = self._add_usage(reply)
            trace.write("llm_call", step=self.steps, prompt_tokens=reply.prompt_tokens,
                        completion_tokens=reply.completion_tokens, cost_usd=round(call_cost, 6),
                        content=reply.content, tool_calls=[c.name for c in reply.tool_calls], **self._totals())

            messages.append({
                "role": "assistant",
                "content": reply.content,
                **({"tool_calls": [{"id": c.id, "type": "function",
                                    "function": {"name": c.name, "arguments": c.arguments}}
                                   for c in reply.tool_calls]} if reply.tool_calls else {}),
            })
            if not reply.tool_calls:
                stop_reason, final_message = "done", reply.content
                break

            for call in reply.tool_calls:
                self.tool_calls += 1
                tool_started = time.monotonic()
                status, result = self._execute(call)
                content = json.dumps(result)
                if len(content) > MAX_TOOL_RESULT_CHARS:
                    content = content[:MAX_TOOL_RESULT_CHARS] + '... [truncated by harness]'
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                trace.write("tool_call", step=self.steps, tool=call.name, call_id=call.id,
                            arguments=call.arguments, status=status, result=result,
                            duration_ms=round((time.monotonic() - tool_started) * 1000))

        # Keep a copy of the tests this run wrote next to its trace.
        written = sorted(tools.GENERATED_TESTS_DIR.glob("test_*.py"))
        if written:
            (self.run_dir / "tests").mkdir(exist_ok=True)
            for path in written:
                shutil.copy2(path, self.run_dir / "tests" / path.name)

        summary = {
            "stop_reason": stop_reason,
            "final_message": final_message,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "blocked_calls": self.blocked_calls,
            **self._totals(),
            "duration_s": round(time.monotonic() - started, 1),
            "run_dir": str(self.run_dir),
            "trace": str(self.run_dir / "trace.jsonl"),
        }
        trace.write("run_end", **summary)
        trace.close()
        return summary

    def _totals(self) -> dict:
        return {"total_tokens": self.total_tokens, "total_cost_usd": round(self.cost_usd, 6)}
