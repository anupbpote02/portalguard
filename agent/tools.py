"""Tools the agent can call.

Each tool saves big data to disk and returns only a short summary (short-term memory):
the model never sees a full aria snapshot or pytest log, only what matters.

Convention: bad arguments raise ValueError (the harness turns that into an error message for the
model); problems in the environment (server down, test timeout) come back in an "error" field.
"""

import ast
import difflib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_USERS_FILE = REPO_ROOT / "portal" / "test-users.json"
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "runs" / "adhoc" / "snapshots"
DEFAULT_RESULTS_DIR = REPO_ROOT / "runs" / "adhoc" / "test-results"
GENERATED_TESTS_DIR = REPO_ROOT / "tests" / "generated"

ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
PAGE_TIMEOUT_MS = 10_000
MAX_CHANGES_PER_FRAME = 20

# write_test guardrails. Not a sandbox: CI runners are the real isolation boundary.
TEST_FILENAME = re.compile(r"test_[a-z0-9_]{1,60}\.py")
MAX_TEST_BYTES = 20_000
ALLOWED_IMPORTS = {"re", "json", "pytest", "playwright.sync_api"}
BLOCKED_CALLS = {"exec", "eval", "compile", "__import__", "open", "getattr", "setattr", "delattr",
                 "globals", "locals", "vars", "breakpoint", "input"}
TEST_RUN_TIMEOUT_S = 120
MAX_ERROR_CHARS = 400

# Lines like:  - heading "Lab results" [level=1]   or   - button
ARIA_LINE = re.compile(r'^\s*- (?P<role>[a-z]+)(?: "(?P<name>[^"]*)")?')
NEEDS_NAME = {"button", "link", "textbox", "checkbox", "combobox", "iframe", "img"}


# ---------------------------------------------------------------- helpers

def check_url(url: str) -> None:
    """Healthcare rule: the agent may only open localhost. Raises ValueError otherwise."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"URL not allowed (localhost only): {url}")


def load_test_users() -> list[dict]:
    return json.loads(TEST_USERS_FILE.read_text(encoding="utf-8"))["users"]


def release_base(url: str) -> str:
    """'http://localhost:8000/buggy/index.html' -> 'http://localhost:8000/buggy/'"""
    if url.endswith(".html"):
        url = url.rsplit("/", 1)[0]
    return url.rstrip("/") + "/"


def _stable_aria(frame, tries: int = 6, pause_ms: int = 250) -> str:
    """Take aria snapshots until two in a row match, so JS-rendered content has settled."""
    previous = None
    for _ in range(tries):
        current = frame.locator("body").aria_snapshot()
        if current == previous:
            return current
        previous = current
        frame.page.wait_for_timeout(pause_ms)
    return previous


def _frame_key(frame) -> str:
    """Name a frame by its iframe's id (stable across releases), else title, else file name."""
    element = frame.frame_element()
    return (element.get_attribute("id") or element.get_attribute("title")
            or frame.url.rsplit("/", 1)[-1])


def _snapshot_all_frames(page) -> dict[str, str]:
    """Aria snapshot of the main page body AND every iframe (the body snapshot only shows '- iframe')."""
    page.wait_for_load_state("networkidle")
    frames = {"main": _stable_aria(page.main_frame)}
    for frame in page.main_frame.child_frames:
        frame.wait_for_load_state("load")
        frames[_frame_key(frame)] = _stable_aria(frame)
    return frames


def _summarize_frame(aria: str) -> dict:
    headings, buttons = [], []
    for line in aria.splitlines():
        match = ARIA_LINE.match(line)
        if not match:
            continue
        name = match["name"] if match["name"] is not None else "(no name)"
        if match["role"] == "heading":
            headings.append(name)
        elif match["role"] == "button":
            buttons.append(name)
    return {"nodes": len(aria.splitlines()), "headings": headings, "buttons": buttons}


def _resolve_snapshot(label_or_path: str, snapshot_dir: Path) -> Path:
    path = Path(label_or_path)
    if path.suffix == ".json" and path.exists():
        return path
    return Path(snapshot_dir) / f"{label_or_path}.json"


def _describe(line: str) -> str:
    """'    - button' -> 'button (no accessible name)'; otherwise just strip the YAML dash."""
    text = line.strip().removeprefix("- ")
    match = ARIA_LINE.match(line)
    if match and match["role"] in NEEDS_NAME and not match["name"]:
        text += " (no accessible name)"
    return text


def _check_test_code(code: str) -> list[str]:
    """Static checks on model-written test code. Returns the test function names."""
    if len(code.encode("utf-8")) > MAX_TEST_BYTES:
        raise ValueError(f"test code is over {MAX_TEST_BYTES} bytes")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"syntax error on line {e.lineno}: {e.msg}") from None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if module not in ALLOWED_IMPORTS:
                raise ValueError(f"import '{module}' not allowed; allowed: {sorted(ALLOWED_IMPORTS)}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            raise ValueError(f"call to '{node.func.id}' not allowed in tests")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(f"dunder attribute '{node.attr}' not allowed in tests")

    tests = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    if not tests:
        raise ValueError("file must define at least one top-level test_* function")
    return tests


def _short_failure(element) -> str:
    """Turn a long pytest/Playwright failure into one line the model can act on:
    'line 14: AssertionError: ... | waiting for get_by_role("button", name="Log in")'
    """
    text = element.text or element.get("message", "")
    lines, waiting_for = [], None
    in_call_log = False
    for line in text.splitlines():
        if not line.startswith("E "):
            continue
        detail = line[1:].strip().replace("playwright._impl._errors.", "")
        if detail.startswith(("Call log", "=====")):
            in_call_log = True
        elif in_call_log:
            if waiting_for is None and detail.lstrip("- ").startswith("waiting for "):
                waiting_for = detail.lstrip("- ")
        elif detail:
            lines.append(detail)
    if waiting_for and not any(waiting_for.removeprefix("waiting for ") in line for line in lines):
        lines.append(waiting_for)

    location = re.search(r"(test_[a-z0-9_]+\.py):(\d+):", text)  # first frame = the test's own line
    prefix = f"line {location[2]}: " if location else ""
    return (prefix + (" | ".join(lines) or element.get("message", "failed")))[:MAX_ERROR_CHARS]


# ---------------------------------------------------------------- tools

def snapshot_page(url: str, label: str, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> dict:
    """Sign in to a portal release and save aria snapshots of every page and frame.

    Pages captured: 'sign-in' (before signing in) and 'dashboard' (after, incl. the lab iframe).
    Full snapshots go to <snapshot_dir>/<label>.json; only a summary is returned.
    """
    check_url(url)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label):
        raise ValueError("label must be 1-40 letters, digits, '-' or '_'")

    base = release_base(url)
    user = load_test_users()[0]
    js_errors: list[str] = []
    pages: dict[str, dict[str, str]] = {}
    error = None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        try:
            response = page.goto(base + "index.html")
            if response is None or not response.ok:
                raise PlaywrightError(f"HTTP {response.status if response else 'no response'}")
            pages["sign-in"] = _snapshot_all_frames(page)

            # Navigate by stable ids and press Enter (not by role/name), so an a11y bug such as
            # a nameless "Sign in" button can't stop us from capturing the pages behind it.
            page.fill("#email", user["email"])
            page.fill("#password", user["password"])
            page.press("#password", "Enter")
            page.wait_for_url("**/dashboard.html")
            pages["dashboard"] = _snapshot_all_frames(page)
        except PlaywrightError as e:  # timeouts, connection refused, etc.
            error = f"Failed on {page.url}: {str(e).splitlines()[0]}"
        finally:
            browser.close()

    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{label}.json"
    path.write_text(json.dumps({
        "label": label,
        "url": base,
        "signed_in_as": user["email"],
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": error,
        "js_errors": js_errors,
        "pages": pages,
    }, indent=2), encoding="utf-8")

    return {
        "saved": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
        "label": label,
        "error": error,
        "js_errors": js_errors,
        "pages": {page_name: {frame: _summarize_frame(aria) for frame, aria in frames.items()}
                  for page_name, frames in pages.items()},
    }


def compare_snapshots(baseline: str, new: str, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> dict:
    """Diff two saved snapshots (labels or .json paths), page by page and frame by frame.

    Returns readable changes such as 'REMOVED: heading "Lab results" [level=1]'.
    """
    old_data = json.loads(_resolve_snapshot(baseline, snapshot_dir).read_text(encoding="utf-8"))
    new_data = json.loads(_resolve_snapshot(new, snapshot_dir).read_text(encoding="utf-8"))

    changes: dict[str, list[str]] = {}
    unchanged: list[str] = []
    # Journey order (sign-in, then dashboard), then any pages only the new release has.
    page_names = list(old_data["pages"]) + [p for p in new_data["pages"] if p not in old_data["pages"]]
    for page_name in page_names:
        old_frames = old_data["pages"].get(page_name)
        new_frames = new_data["pages"].get(page_name)
        if old_frames is None or new_frames is None:
            changes[page_name] = ["PAGE MISSING in " + ("baseline" if old_frames is None else "new release")]
            continue

        for frame in sorted(set(old_frames) | set(new_frames), key=lambda f: (f != "main", f)):
            where = f"{page_name} / {frame}"
            if frame not in new_frames:
                changes[where] = ["FRAME MISSING in new release"]
                continue
            if frame not in old_frames:
                changes[where] = ["NEW FRAME (not in baseline)"]
                continue

            old_lines = old_frames[frame].splitlines()
            new_lines = new_frames[frame].splitlines()
            found = []
            matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
            for op, a1, a2, b1, b2 in matcher.get_opcodes():
                if op == "delete":
                    found += [f"REMOVED: {_describe(line)}" for line in old_lines[a1:a2]]
                elif op == "insert":
                    found += [f"ADDED: {_describe(line)}" for line in new_lines[b1:b2]]
                elif op == "replace":
                    found += [f"CHANGED: {_describe(o)}  ->  {_describe(n)}"
                              for o, n in zip(old_lines[a1:a2], new_lines[b1:b2])]
                    found += [f"REMOVED: {_describe(line)}" for line in old_lines[a1 + (b2 - b1):a2]]
                    found += [f"ADDED: {_describe(line)}" for line in new_lines[b1 + (a2 - a1):b2]]

            if found:
                extra = len(found) - MAX_CHANGES_PER_FRAME
                changes[where] = found[:MAX_CHANGES_PER_FRAME] + ([f"... {extra} more"] if extra > 0 else [])
            else:
                unchanged.append(where)

    new_js_errors = [e for e in new_data["js_errors"] if e not in old_data["js_errors"]]
    return {
        "baseline": old_data["label"],
        "new": new_data["label"],
        "total_changes": sum(len(c) for c in changes.values()),
        "changes": changes,
        "unchanged": unchanged,
        "new_js_errors": new_js_errors,
        "new_release_error": new_data["error"],
    }


def write_test(filename: str, code: str) -> dict:
    """Write a Playwright test file into tests/generated/ (test_*.py only, checked before writing)."""
    if not TEST_FILENAME.fullmatch(filename):
        raise ValueError("filename must look like test_<lowercase_words>.py (no folders)")
    tests = _check_test_code(code)

    path = GENERATED_TESTS_DIR / filename
    existed = path.exists()
    path.write_text(code, encoding="utf-8", newline="\n")
    return {
        "written": str(path.relative_to(REPO_ROOT)),
        "overwrote": existed,
        "tests": tests,
    }


def run_tests(base_url: str, filename: str | None = None, results_dir: Path = DEFAULT_RESULTS_DIR,
              test_name: str | None = None) -> dict:
    """Run generated tests against one release with pytest; return pass/fail per test.

    base_url is set by the harness (the release under test), not by the model.
    test_name (harness only, needs filename) runs a single test function, for triage reruns.
    Pass/fail comes from Playwright assertions via pytest's JUnit XML, never from the LLM.
    """
    check_url(base_url)
    base_url = release_base(base_url)
    if filename is not None:
        if not TEST_FILENAME.fullmatch(filename):
            raise ValueError("filename must look like test_<lowercase_words>.py")
        if not (GENERATED_TESTS_DIR / filename).exists():
            raise ValueError(f"no such test file: {filename}")
    if test_name is not None and (filename is None or not re.fullmatch(r"test_\w{1,80}", test_name)):
        raise ValueError("test_name needs a filename and must look like test_<words>")
    target = str(GENERATED_TESTS_DIR / filename) if filename else str(GENERATED_TESTS_DIR)
    if test_name:
        target += f"::{test_name}"

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S-%f")
    junit_path = results_dir / f"junit-{stamp}.xml"
    log_path = results_dir / f"pytest-{stamp}.log"

    command = [sys.executable, "-m", "pytest", target, "--base-url", base_url,
               "-q", "-p", "no:cacheprovider", f"--junitxml={junit_path}"]
    try:
        proc = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TEST_RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"error": f"test run timed out after {TEST_RUN_TIMEOUT_S}s", "base_url": base_url}
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")

    if not junit_path.exists():
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        return {"error": "pytest did not run: " + " | ".join(tail), "base_url": base_url}

    results = []
    for case in ET.parse(junit_path).getroot().iter("testcase"):
        file = case.get("classname", "").rsplit(".", 1)[-1] + ".py"
        result = {"test": f"{file}::{case.get('name')}", "outcome": "passed"}
        for tag in ("failure", "error", "skipped"):
            element = case.find(tag)
            if element is not None:
                result["outcome"] = "failed" if tag == "failure" else tag
                result["message"] = _short_failure(element)
                break
        results.append(result)

    def count(outcome):
        return sum(r["outcome"] == outcome for r in results)

    return {
        "base_url": base_url,
        "passed": count("passed"),
        "failed": count("failed"),
        "errors": count("error"),
        "results": results,
        "log": str(log_path.relative_to(REPO_ROOT) if log_path.is_relative_to(REPO_ROOT) else log_path),
    }
