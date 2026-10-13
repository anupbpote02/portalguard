"""Triage: decide what each failing test means. Deterministic code, not the model.

The last good release is the oracle. For each test that fails on the release:
  1. run it on the baseline:  fails there too       -> broken_test (the test is wrong: model heals it, max 3 tries)
  2. rerun it on the release: passes now            -> flaky       (recorded, not reported)
  3. passes on baseline, fails on release 2/2 runs  -> real_bug    (if it matches a snapshot diff or a journey)
                                                    -> unconfirmed (no supporting evidence: human review)
"""

import hashlib
import re

from agent.tools import GENERATED_TESTS_DIR

FLAKY_RERUNS = 1          # extra release runs before a failure counts as consistent
MAX_HEAL_ATTEMPTS = 3

LOCATOR_NAME = re.compile(r'name=\\?"([^"\\]+)')
WAITING_FOR = re.compile(r"waiting for (.+)$")
JOURNEYS = {  # test file keyword -> journey from the QE plan
    "sign_in": "Sign in",
    "appointment": "See upcoming appointments",
    "lab_result": "View lab results",
    "download": "Download lab results PDF",
}


def split_test_id(test_id: str) -> tuple[str, str]:
    """'test_x.py::test_y[chromium]' -> ('test_x.py', 'test_y')"""
    filename, name = test_id.split("::", 1)
    return filename, name.split("[", 1)[0]


def _file_hash(filename: str) -> str:
    path = GENERATED_TESTS_DIR / filename
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else ""


class Triage:
    def __init__(self, run_tests_fn, baseline_url: str, release_url: str):
        self.run_tests = run_tests_fn          # (base_url, filename, test_name) -> run_tests result
        self.baseline_url = baseline_url
        self.release_url = release_url
        self.tests: dict[str, dict] = {}       # "file::name" -> record (verdict, evidence, history)
        self.heal_attempts: dict[str, int] = {}
        self.snapshots: dict[str, dict] = {}   # label -> snapshot_page summary
        self.diff: dict | None = None          # last compare_snapshots result
        self.harness_runs = 0                  # test runs the harness did on its own (reruns, baseline)
        self.events: list[dict] = []           # for the trace
        # From long-term memory: test id -> code hash of tests that passed on this same baseline before.
        self.known_baseline_passes: dict[str, str] = {}

    # ------------------------------------------------------------ hooks called by the harness

    def record_snapshot(self, result: dict) -> None:
        self.snapshots[result["label"]] = result

    def record_diff(self, result: dict) -> None:
        self.diff = result

    def before_write(self, filename: str) -> str | None:
        """Called before write_test. Returns a refusal message, or None to allow the write."""
        records = [r for r in self.tests.values() if r["file"] == filename]
        if any(r["verdict"] == "real_bug" for r in records):
            return (f"refused: {filename} is evidence of a confirmed bug (passes on baseline, fails on "
                    "release). Changing it would hide the bug.")
        if any(r["verdict"] in ("broken_test", "gave_up") for r in records):
            if self.heal_attempts.get(filename, 0) >= MAX_HEAL_ATTEMPTS:
                return f"refused: heal limit reached for {filename} ({MAX_HEAL_ATTEMPTS} attempts)"
            self.heal_attempts[filename] = self.heal_attempts.get(filename, 0) + 1
            for r in records:
                r["heal_attempts"] = self.heal_attempts[filename]
        return None

    def process(self, release_result: dict) -> dict:
        """Triage one run_tests result (on the release). Returns verdicts to show the model."""
        verdicts = {}
        for result in release_result.get("results", []):
            filename, name = split_test_id(result["test"])
            test_id = f"{filename}::{name}"
            record = self.tests.setdefault(test_id, {
                "test": test_id, "file": filename, "name": name, "verdict": None, "code_hash": None,
                "heal_attempts": 0, "first_error": None, "history": [],
            })
            code_hash = _file_hash(filename)
            was_broken = record["verdict"] in ("broken_test", "gave_up")

            # Same code, already decided: don't spend more runs on it.
            if record["code_hash"] == code_hash and record["verdict"] in ("real_bug", "flaky", "unconfirmed"):
                verdicts[test_id] = self._for_model(record)
                continue
            record["code_hash"] = code_hash

            if result["outcome"] == "passed":
                record["verdict"] = "passed"
                record["healed"] = record.get("healed") or was_broken
                if was_broken:
                    verdicts[test_id] = self._for_model(record)
                continue

            record["first_error"] = record["first_error"] or result.get("message")
            record["release_error"] = result.get("message")
            self._decide(record, filename, name, was_broken)
            verdicts[test_id] = self._for_model(record)
        return verdicts

    # ------------------------------------------------------------ decision

    def _run_one(self, base_url: str, filename: str, name: str) -> dict:
        self.harness_runs += 1
        result = self.run_tests(base_url, filename, name)
        outcomes = result.get("results") or [{"outcome": "error", "message": result.get("error", "no result")}]
        return outcomes[0]

    def _decide(self, record: dict, filename: str, name: str, was_broken: bool) -> None:
        # Baseline first: a test that can't pass on the last good release is wrong, whatever else happens.
        # Memory can answer this without a run: same test code already passed on this same baseline.
        if self.known_baseline_passes.get(record["test"]) == record["code_hash"]:
            baseline = {"outcome": "passed"}
            record["baseline_from_memory"] = True
        else:
            baseline = self._run_one(self.baseline_url, filename, name)
        record["baseline_outcome"] = baseline["outcome"]
        if baseline["outcome"] != "passed":
            record["baseline_error"] = baseline.get("message")
            if self.heal_attempts.get(filename, 0) >= MAX_HEAL_ATTEMPTS:
                self._set(record, "gave_up", f"still fails on the baseline after {MAX_HEAL_ATTEMPTS} heal attempts")
            else:
                self._set(record, "broken_test", "fails on the baseline (last good release) too, so the test is wrong")
            return

        runs = ["failed"]
        for _ in range(FLAKY_RERUNS):
            rerun = self._run_one(self.release_url, filename, name)
            runs.append(rerun["outcome"])
            if rerun["outcome"] == "passed":
                self._set(record, "flaky", f"failed, then passed on rerun ({' -> '.join(runs)}); not reported")
                return

        # A regression: passes on the last good release, fails on this one every time.
        record["healed"] = record.get("healed") or was_broken
        record["release_runs"] = runs
        diff_lines = self._matching_diff_lines(record["release_error"] or "")
        journey = next((j for key, j in JOURNEYS.items() if key in filename), None)
        record["diff_evidence"] = diff_lines
        record["journey"] = journey
        record["category"] = "accessibility" if diff_lines else "functional"
        if diff_lines or journey:
            self._set(record, "real_bug", f"passes on baseline, fails on release {len(runs)}/{len(runs)} runs")
        else:
            self._set(record, "unconfirmed", "regression with no matching snapshot diff or journey; needs review")

    def _matching_diff_lines(self, error: str) -> list[str]:
        """Snapshot diff lines that mention an accessible name the failing locator was looking for."""
        names = set(LOCATOR_NAME.findall(error))
        if not names or not self.diff:
            return []
        return [f"{where}: {line}" for where, lines in self.diff.get("changes", {}).items()
                for line in lines if any(f'"{n}"' in line for n in names)]

    def _set(self, record: dict, verdict: str, why: str) -> None:
        record["verdict"], record["why"] = verdict, why
        record["history"].append(verdict)
        self.events.append({"test": record["test"], "verdict": verdict, "why": why,
                            "heal_attempts": record["heal_attempts"]})

    # ------------------------------------------------------------ what the model sees

    def _for_model(self, record: dict) -> dict:
        out = {"verdict": record["verdict"], "why": record.get("why", "")}
        if record.get("healed") and record["verdict"] == "passed":
            out["why"] = "healed: now passes"
        if record["verdict"] == "broken_test":
            out["baseline_error"] = record.get("baseline_error")
            out["heal_attempts_left"] = MAX_HEAL_ATTEMPTS - self.heal_attempts.get(record["file"], 0)
            out["baseline_has"] = self._baseline_hints()
            out["next"] = "Fix this test with write_test (same filename), then run_tests on that file."
        elif record["verdict"] == "real_bug":
            out["evidence"] = record["diff_evidence"] or [f"journey broken: {record['journey']}"]
            out["next"] = "Do not change this test; it is evidence of a bug."
        return out

    def _baseline_hints(self) -> dict:
        """Frame ids and accessible names in the baseline, so the model can pick real locators."""
        label = (self.diff or {}).get("baseline")
        summary = self.snapshots.get(label) if label else None
        if not summary:
            return {}
        return {f"{page} / {frame}": {k: v for k, v in info.items() if k in ("headings", "buttons")}
                for page, frames in summary["pages"].items() for frame, info in frames.items()}

    # ------------------------------------------------------------ for the report

    def records(self, verdict: str) -> list[dict]:
        return [r for r in self.tests.values() if r["verdict"] == verdict]

    def healed(self) -> list[dict]:
        return [r for r in self.tests.values() if r.get("healed")]
