"""Demo of write_test + run_tests (no LLM): one sample test, run against good and buggy.

Usage (portal must be running: python -m http.server 8000 --directory portal):
    python -m agent.demo_tools
"""

import json
import sys
import urllib.request
from datetime import datetime
from urllib.error import URLError

from agent.tools import REPO_ROOT, run_tests, write_test

GOOD = "http://localhost:8000/good/"
BUGGY = "http://localhost:8000/buggy/"

# What a model would write for the "download PDF" journey. It signs in by label + Enter so it only
# fails for one reason (the download), not because of the separate sign-in button bug.
SAMPLE_TEST = '''\
from playwright.sync_api import Page, expect


def test_download_lab_results_pdf(page: Page, base_url: str, patient: dict):
    page.goto(base_url + "index.html")
    page.get_by_label("Email").fill(patient["email"])
    page.get_by_label("Password").fill(patient["password"])
    page.get_by_label("Password").press("Enter")
    expect(page).to_have_url(base_url + "dashboard.html")

    lab = page.frame_locator("#lab-results-frame")
    with page.expect_download() as download_info:
        lab.get_by_role("button", name="Download PDF").click()
    assert download_info.value.suggested_filename == f"lab-results-{patient['mrn']}.pdf"
    expect(lab.get_by_role("status")).to_have_text("Download started")
'''


def show(title, value):
    print(f"\n== {title} ->")
    print(json.dumps(value, indent=2))


def main() -> int:
    try:
        urllib.request.urlopen(GOOD, timeout=3)
    except URLError:
        print(f"Portal not reachable at {GOOD}\nStart it first:  python -m http.server 8000 --directory portal")
        return 2

    results_dir = REPO_ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S") / "test-results"
    show("write_test('test_download_pdf.py', ...)", write_test("test_download_pdf.py", SAMPLE_TEST))
    show(f"run_tests(base_url={GOOD!r})", run_tests(GOOD, "test_download_pdf.py", results_dir))
    show(f"run_tests(base_url={BUGGY!r})", run_tests(BUGGY, "test_download_pdf.py", results_dir))

    print("\n== write_test guardrails (each should be rejected) ->")
    for filename, code in [
        ("../conftest.py", "def test_x(): pass"),
        ("test_shell.py", "import os\ndef test_x(): os.system('whoami')"),
        ("test_sneaky.py", "def test_x(): __import__('os')"),
        ("test_broken.py", "def test_x(:\n    pass"),
        ("test_empty.py", "x = 1"),
    ]:
        try:
            write_test(filename, code)
            print(f"  NOT REJECTED: {filename}")
        except ValueError as e:
            print(f"  rejected {filename}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
