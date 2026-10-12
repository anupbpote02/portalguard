"""Tools the agent can call.

Each tool saves big data to disk and returns only a short summary (short-term memory):
the model never sees a full aria snapshot, only what changed.
"""

import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_USERS_FILE = REPO_ROOT / "portal" / "test-users.json"
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "runs" / "adhoc" / "snapshots"

ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
PAGE_TIMEOUT_MS = 10_000
MAX_CHANGES_PER_FRAME = 20

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
