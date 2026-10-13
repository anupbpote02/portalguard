"""Journey coverage: does a test actually exercise its journey? Static checks, no LLM.

A journey file passes when at least one of its test functions does everything the journey needs.
"The Download PDF button is visible" is not a download test; it must click, wait for the download
and check the file. The harness uses this twice:
  - write_test: a journey file that exercises nothing is rejected, with what's missing;
  - final answer: the run isn't done until every required journey has an accepted file.
"""

import ast
import re

# journey key -> [(what the test must do, regex on the test function's source)]
JOURNEY_RULES = {
    "sign_in": [
        ("fill in the email and password", r"\.fill\("),
        ("submit the form (click or press Enter)", r"\.(click|press)\("),
        ("assert the result with expect()", r"\bexpect\("),
    ],
    "wrong_password": [
        ("fill in the form", r"\.fill\("),
        ("submit the form (click or press Enter)", r"\.(click|press)\("),
        ('check the error message in get_by_role("alert")', r"""["']alert["']"""),
    ],
    "appointments": [
        ("check the appointments themselves (to_have_count / to_have_text / to_contain_text), "
         "not only that something is visible", r"\.(to_have_count|to_have_text|to_contain_text)\("),
    ],
    "lab_results": [
        ('look inside frame_locator("#lab-results-frame")', r"frame_locator\("),
        ("check the results themselves (to_have_count / to_have_text / to_contain_text), "
         "not only that something is visible", r"\.(to_have_count|to_have_text|to_contain_text)\("),
    ],
    "download_pdf": [
        ("wait for the file with page.expect_download()", r"expect_download\("),
        ("click the Download PDF button", r"\.click\("),
        ("check download.suggested_filename", r"suggested_filename"),
    ],
}
REQUIRED_JOURNEYS = list(JOURNEY_RULES)  # diff_check is optional


def _test_functions(code: str) -> dict[str, str]:
    tree = ast.parse(code)
    return {n.name: ast.get_source_segment(code, n) or "" for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def missing_steps(code: str, journey: str) -> list[str]:
    """What the best test in this file still needs to do for the journey ([] = covered)."""
    rules = JOURNEY_RULES.get(journey)
    if not rules:
        return []
    best = None
    for source in _test_functions(code).values():
        missing = [what for what, pattern in rules if not re.search(pattern, source)]
        if best is None or len(missing) < len(best):
            best = missing
    return best if best is not None else [what for what, _ in rules]


def check_journey(code: str, journey: str) -> str | None:
    """Refusal message for write_test, or None if the file exercises its journey."""
    try:
        ast.parse(code)
    except SyntaxError:
        return None  # write_test reports syntax errors itself, with the line number
    missing = missing_steps(code, journey)
    if not missing:
        return None
    return (f"rejected: no test in this file exercises the {journey} journey. "
            f"At least one test must: {'; '.join(missing)}.")


def missing_journeys(file_journeys: dict[str, str]) -> list[str]:
    """Required journeys with no accepted file yet (write_test only accepts files that exercise them)."""
    covered = set(file_journeys.values())
    return [journey for journey in REQUIRED_JOURNEYS if journey not in covered]
