"""LLM clients behind one tiny interface: complete(messages, tools) -> LLMReply.

OpenAILLM calls gpt-4.1-mini with tool calling. MockLLM replays a scripted list of tool calls, so the
whole harness runs for $0 with no API key (CI, demos, evals).
"""

import itertools
import json
import os
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string, exactly as the model sent it (the harness validates it)


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class OpenAILLM:
    def __init__(self, model: str = "gpt-4.1-mini", max_completion_tokens: int = 4000):
        from openai import OpenAI  # imported here so --mock never needs the package configured

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Put it in .env (see .env.example) or use --mock.")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_completion_tokens = max_completion_tokens

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """Transient API problems the harness should retry (the SDK's own 2 retries already failed)."""
        import openai

        return isinstance(error, (openai.APIConnectionError, openai.APITimeoutError,
                                  openai.RateLimitError, openai.InternalServerError))

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_completion_tokens=self.max_completion_tokens,  # bounds how far one call can overshoot
        )
        message = response.choices[0].message
        return LLMReply(
            content=message.content,
            tool_calls=[ToolCall(tc.id, tc.function.name, tc.function.arguments) for tc in message.tool_calls or []],
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )


class MockLLM:
    """Scripted fake model. Each turn is a list of (tool_name, args) or a final text message.
    Token counts are estimated (~4 chars per token) so the token budget is exercised; cost is $0."""

    model = "mock"

    def __init__(self, turns):
        self.turns = iter(turns)
        self.call_ids = itertools.count(1)

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        turn = next(self.turns, "Mock script finished.")
        if callable(turn):
            turn = turn(messages)
        prompt_tokens = len(json.dumps(messages)) // 4 + len(json.dumps(tools)) // 4

        if isinstance(turn, str):
            return LLMReply(content=turn, prompt_tokens=prompt_tokens, completion_tokens=len(turn) // 4)

        calls = [ToolCall(f"call_{next(self.call_ids)}", name, json.dumps(args)) for name, args in turn]
        completion_tokens = sum(len(c.arguments) for c in calls) // 4
        return LLMReply(content=None, tool_calls=calls, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


# ---------------------------------------------------------------- mock scenarios

# Journey tests a model would write. They use conftest fixtures: page, base_url, patient, signed_in.
TEST_JOURNEYS = {
    "test_sign_in.py": "sign_in",
    "test_wrong_password.py": "wrong_password",
    "test_appointments.py": "appointments",
    "test_lab_results.py": "lab_results",
    "test_download_pdf.py": "download_pdf",
}
JOURNEY_TESTS = {
    "test_sign_in.py": '''\
from playwright.sync_api import Page, expect


def test_sign_in_with_valid_credentials(page: Page, base_url: str, patient: dict):
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(base_url + "dashboard.html")
    expect(page.get_by_role("heading", name=f"Welcome, {patient['name']}")).to_be_visible()
''',
    "test_wrong_password.py": '''\
from playwright.sync_api import Page, expect


def test_wrong_password_shows_alert(page: Page, base_url: str, patient: dict):
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_label("Password").press("Enter")
    expect(page.get_by_role("alert")).to_have_text("Incorrect email or password. Please try again.")
    expect(page).to_have_url(base_url + "index.html")
''',
    "test_appointments.py": '''\
from playwright.sync_api import Page, expect


def test_upcoming_appointments_listed(signed_in: Page):
    expect(signed_in.get_by_role("heading", name="Upcoming appointments")).to_be_visible()
    expect(signed_in.get_by_role("listitem")).to_have_count(2)
''',
    "test_lab_results.py": '''\
from playwright.sync_api import Page, expect


def test_lab_results_shown_in_iframe(signed_in: Page, patient: dict):
    lab = signed_in.frame_locator("#lab-results-frame")
    expect(lab.get_by_role("heading", name="Lab results")).to_be_visible()
    expect(lab.get_by_role("row")).to_have_count(4)  # header + 3 results
    expect(lab.get_by_role("cell", name=patient["labResults"][0]["test"])).to_be_visible()
''',
    "test_download_pdf.py": '''\
from playwright.sync_api import Page, expect


def test_download_lab_results_pdf(signed_in: Page, patient: dict):
    lab = signed_in.frame_locator("#lab-results-frame")
    with signed_in.expect_download() as download_info:
        lab.get_by_role("button", name="Download PDF").click()
    assert download_info.value.suggested_filename == f"lab-results-{patient['mrn']}.pdf"
    expect(lab.get_by_role("status")).to_have_text("Download started")
''',
}


def _with_frame(code: str, frame_selector: str) -> str:
    """The lab results test with a different iframe selector (to script broken versions)."""
    return code.replace('"#lab-results-frame"', f'"{frame_selector}"')


def _summarize_triage(messages: list[dict]) -> str:
    """Mock's final message, built from every triage verdict it was shown (latest wins)."""
    verdicts = {}
    for message in messages:
        if message["role"] == "tool" and '"triage"' in message["content"]:
            for test, info in json.loads(message["content"])["triage"].items():
                verdicts[test] = info["verdict"]
    if not verdicts:
        return "Mock QE run complete: all tests passed."
    counts = {v: sum(x == v for x in verdicts.values()) for v in sorted(set(verdicts.values()))}
    return "Mock QE run complete. Triage: " + ", ".join(f"{n} {v}" for v, n in counts.items()) + "."


def qe_scenario(baseline_url: str, release_url: str):
    """Snapshot, diff, write journey tests (one with a wrong iframe selector), run, heal, summarize.

    The lab results test is always written with "#labs-frame" (wrong). On a first run the harness sees it
    fail on the baseline too and asks for a fix: heal 1 guesses "#lab_results_frame" (still wrong), heal 2
    uses the frame id from baseline_has ("lab-results-frame"). On later runs long-term memory swaps the
    bad selector before the test is written, so no healing is needed.
    The script reacts like a model would: it skips the baseline snapshot if memory says it's saved,
    and only heals while triage says broken_test.
    """
    lab_test = JOURNEY_TESTS["test_lab_results.py"]
    first_tests = {**JOURNEY_TESTS, "test_lab_results.py": _with_frame(lab_test, "#labs-frame")}
    heals = [_with_frame(lab_test, "#lab_results_frame"), lab_test]

    def snapshots(messages):
        release = ("snapshot_page", {"url": release_url, "label": "release"})
        if 'already saved as label "baseline"' in messages[1]["content"]:
            return [release]
        return [("snapshot_page", {"url": baseline_url, "label": "baseline"}), release]

    def heal_or_finish(messages):
        last_call = next(m for m in reversed(messages) if m["role"] == "assistant")["tool_calls"][0]["function"]
        if last_call["name"] == "write_test":
            return [("run_tests", {"filename": "test_lab_results.py"})]
        last_triage = json.loads(next(m for m in reversed(messages) if m["role"] == "tool")["content"]).get("triage", {})
        broken = any(t.startswith("test_lab_results.py") and v["verdict"] == "broken_test" for t, v in last_triage.items())
        heals_done = sum(1 for m in messages if m["role"] == "assistant" and m.get("tool_calls")
                         and m["tool_calls"][0]["function"]["name"] == "write_test") - 1
        if broken and heals_done < len(heals):
            return [("write_test", {"filename": "test_lab_results.py", "code": heals[heals_done], "journey": "lab_results"})]
        return _summarize_triage(messages)

    yield snapshots
    yield [("compare_snapshots", {"baseline": "baseline", "new": "release"})]
    yield [("write_test", {"filename": name, "code": code, "journey": TEST_JOURNEYS[name]})
           for name, code in first_tests.items()]
    yield [("run_tests", {})]
    while True:
        yield heal_or_finish


def guardrails_scenario(baseline_url: str, release_url: str) -> list:
    """A misbehaving model: bad arguments, then off-site URLs until the harness stops the run."""
    return [
        [("compare_snapshots", {"baseline": "baseline"})],                                   # missing arg
        [("write_test", {"filename": "../conftest.py", "code": "def test_x(): pass", "journey": "sign_in"})],  # bad filename
        [("run_tests", {"base_url": "https://evil.example.com/"})],                          # not the model's to set
        [("delete_everything", {})],                                                        # unknown tool
        [("snapshot_page", {"url": "https://example.com/", "label": "offsite"})],
        [("snapshot_page", {"url": "http://localhost.evil.com:8000/good/", "label": "lookalike"})],
        [("snapshot_page", {"url": "http://169.254.169.254/latest/meta-data/", "label": "metadata"})],
        "This line is never reached: the harness stops after 3 blocked URLs.",
    ]


def runaway_scenario(baseline_url: str, release_url: str):
    """A model stuck in a loop: compares the same snapshots forever until MAX_STEPS stops it."""
    yield [("snapshot_page", {"url": baseline_url, "label": "baseline"}),
           ("snapshot_page", {"url": release_url, "label": "release"})]
    while True:
        yield [("compare_snapshots", {"baseline": "baseline", "new": "release"})]


MOCK_SCENARIOS = {"qe": qe_scenario, "guardrails": guardrails_scenario, "runaway": runaway_scenario}
