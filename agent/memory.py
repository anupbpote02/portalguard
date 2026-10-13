"""Memory.

Short-term (one run): big data lives on disk (snapshots, pytest logs); the model only sees summaries.
Long-term (across runs): memory/memory.json, written by the harness at the end of each run:
  - baselines:          a saved copy of the last good release's snapshot (+ tests known to pass on it)
  - working_selectors:  locators from tests that passed on the baseline
  - selector_fixes:     bad -> good locators learned from healed tests, applied to new tests
  - reported_bugs:      confirmed bugs by fingerprint, so repeats are "known", not "new"
  - flaky_tests:        tests that failed then passed on rerun
  - run_count / runs:   short run history

Only harness-verified facts are stored (triage verdicts from Playwright runs), never model claims.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from agent.tools import REPO_ROOT, release_base

MEMORY_DIR = REPO_ROOT / "memory"
MEMORY_FILE = MEMORY_DIR / "memory.json"
MAX_RUN_HISTORY = 20
MAX_SELECTORS_IN_BRIEFING = 30

# Locator calls in test code, e.g. frame_locator("#lab-results-frame"), get_by_role("heading", name="Lab results")
SELECTOR_CALL = re.compile(r'\b(?:frame_locator|get_by_role|get_by_label|get_by_text|locator)\([^()]*\)')


def empty_memory() -> dict:
    return {"version": 1, "run_count": 0, "baselines": {}, "working_selectors": {}, "selector_fixes": {},
            "reported_bugs": {}, "flaky_tests": {}, "runs": []}


def selectors_in(code: str) -> set[str]:
    return set(SELECTOR_CALL.findall(code))


def bug_fingerprint(record: dict) -> str:
    """Stable id for a confirmed bug: the snapshot diff line if there is one, else journey + error shape."""
    if record.get("diff_evidence"):
        return "a11y|" + record["diff_evidence"][0]
    error = re.sub(r"^line \d+: ", "", record.get("release_error") or "")
    return f"functional|{record.get('journey')}|{re.sub(r'\d+', 'N', error)}"


def bug_title(record: dict) -> str:
    if record.get("diff_evidence"):
        where, change = record["diff_evidence"][0].split(": ", 1)
        return f"{change} ({where})"
    return f"{record.get('journey')} journey broken"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memory:
    def __init__(self, path: Path = MEMORY_FILE, enabled: bool = True):
        self.path = Path(path)
        self.enabled = enabled
        self.data = empty_memory()
        if enabled and self.path.exists():
            self.data = {**empty_memory(), **json.loads(self.path.read_text(encoding="utf-8"))}

    @property
    def run_count(self) -> int:
        return self.data["run_count"]

    # ------------------------------------------------------------ baseline

    def cached_baseline(self, baseline_url: str) -> dict | None:
        entry = self.data["baselines"].get(release_base(baseline_url))
        if not entry or not (REPO_ROOT / entry["snapshot_path"]).exists():
            return None
        return entry

    def save_baseline(self, baseline_url: str, snapshot_file: Path, summary: dict) -> None:
        """Keep our own copy: runs/ is throwaway, memory/ is what persists between runs (and CI jobs)."""
        url = release_base(baseline_url)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
        target = self.path.parent / "baselines" / f"{slug}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot_file, target)
        self.data["baselines"][url] = {
            "snapshot_path": target.relative_to(REPO_ROOT).as_posix(),
            "summary": summary,
            "saved_at": _now(),
            "passing_tests": {},  # test id -> code hash, valid only for THIS baseline
        }

    def baseline_passes(self, baseline_url: str) -> dict[str, str]:
        entry = self.cached_baseline(baseline_url)
        return dict(entry["passing_tests"]) if entry else {}

    # ------------------------------------------------------------ selectors

    def apply_selector_fixes(self, code: str) -> tuple[str, list[str]]:
        """Swap locators that failed on the baseline before for the ones that fixed them."""
        applied = []
        for bad, fix in self.data["selector_fixes"].items():
            if bad in code:
                code = code.replace(bad, fix["good"])
                applied.append(f"{bad} -> {fix['good']}")
        return code, applied

    # ------------------------------------------------------------ bugs / flaky

    def known_bug(self, record: dict) -> dict | None:
        return self.data["reported_bugs"].get(bug_fingerprint(record))

    # ------------------------------------------------------------ briefing for the model

    def briefing(self, baseline_url: str, baseline_preloaded: bool) -> str | None:
        if not self.enabled or self.run_count == 0:
            return None
        lines = [f"Long-term memory (this is run #{self.run_count + 1}):"]
        if baseline_preloaded:
            saved_at = self.cached_baseline(baseline_url)["saved_at"]
            lines.append(f'- The baseline snapshot is already saved as label "baseline" (from {saved_at}). '
                         "Do not snapshot the baseline again; snapshot only the release.")
        working = list(self.data["working_selectors"])[:MAX_SELECTORS_IN_BRIEFING]
        if working:
            lines.append("- Locators that worked on the baseline before: " + "; ".join(working))
        if self.data["selector_fixes"]:
            lines.append("- Locators that were wrong before (do not use): " + "; ".join(
                f"{bad} (use {fix['good']})" for bad, fix in self.data["selector_fixes"].items()))
        if self.data["reported_bugs"]:
            lines.append("- Bugs already reported: " + "; ".join(b["title"] for b in self.data["reported_bugs"].values()))
        if self.data["flaky_tests"]:
            lines.append("- Known flaky tests: " + ", ".join(self.data["flaky_tests"]))
        return "\n".join(lines)

    # ------------------------------------------------------------ learning at the end of a run

    def learn(self, run_id: str, release_url: str, baseline_url: str, triage, code_versions: dict[str, list[str]],
              summary: dict) -> dict:
        """Store what this run proved. Returns what was learned (for the trace)."""
        if not self.enabled:
            return {}
        run_number = self.run_count + 1
        learned = {"selector_fixes": [], "new_bugs": [], "known_bugs": [], "flaky": []}

        # Tests that passed on the baseline: their locators work, and the baseline run can be skipped next time.
        baseline_entry = self.data["baselines"].get(release_base(baseline_url))
        for record in triage.tests.values():
            if record.get("baseline_outcome") == "passed":
                if baseline_entry is not None:
                    baseline_entry["passing_tests"][record["test"]] = record["code_hash"]
                code = (code_versions.get(record["file"]) or [""])[-1]
                for selector in sorted(selectors_in(code)):
                    self.data["working_selectors"].setdefault(selector, {"first_run": run_number})

        # Healed tests: whatever locator changed between a failing version and the final one was the fix.
        for record in triage.healed():
            versions = code_versions.get(record["file"], [])
            if len(versions) < 2:
                continue
            final = selectors_in(versions[-1])
            for earlier in versions[:-1]:
                removed, added = selectors_in(earlier) - final, final - selectors_in(earlier)
                if len(removed) == 1 and len(added) == 1:
                    bad, good = removed.pop(), added.pop()
                    if bad not in self.data["selector_fixes"]:
                        self.data["selector_fixes"][bad] = {"good": good, "learned_run": run_number,
                                                            "from_test": record["test"]}
                        learned["selector_fixes"].append(f"{bad} -> {good}")

        for record in triage.records("real_bug"):
            fingerprint = bug_fingerprint(record)
            bug = self.data["reported_bugs"].get(fingerprint)
            if bug:
                bug["last_seen_run"], bug["times_seen"] = run_number, bug["times_seen"] + 1
                learned["known_bugs"].append(bug["title"])
            else:
                self.data["reported_bugs"][fingerprint] = {
                    "title": bug_title(record), "category": record["category"], "journey": record["journey"],
                    "test": record["test"], "release_url": release_url,
                    "first_reported_run": run_number, "last_seen_run": run_number, "times_seen": 1,
                }
                learned["new_bugs"].append(bug_title(record))

        for record in triage.records("flaky"):
            entry = self.data["flaky_tests"].setdefault(record["test"], {"times_flaky": 0})
            entry["times_flaky"] += 1
            entry["last_seen_run"] = run_number
            learned["flaky"].append(record["test"])

        self.data["run_count"] = run_number
        self.data["runs"] = (self.data["runs"] + [{
            "run": run_number, "run_id": run_id, "release_url": release_url, "stop_reason": summary["stop_reason"],
            "new_bugs": len(learned["new_bugs"]), "known_bugs": len(learned["known_bugs"]),
            "steps": summary["steps"], "duration_s": summary["duration_s"],
        }])[-MAX_RUN_HISTORY:]
        return learned

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8", newline="\n")
        tmp.replace(self.path)  # atomic: a crash mid-write never leaves half a memory file
