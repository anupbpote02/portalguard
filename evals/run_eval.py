"""Score PortalGuard against the planted bugs. Deterministic matching, no LLM judge.

    python -m evals.run_eval              # mock LLM (default): $0, no key
    python -m evals.run_eval --real       # gpt-4.1-mini, key from .env
    python -m evals.run_eval --real --repeat 3

Each repeat runs the agent twice with memory OFF (so every run starts cold and is comparable):
  1. on the buggy release  -> recall, precision, type accuracy against evals/expected_bugs.json
  2. on the good release   -> false alarms (anything reported there is wrong)
Results: evals/results.json and evals/results.md. Starts the portal itself if it isn't running.
Exit code 1 if recall < --min-recall or false alarms > --max-false-alarms (usable as a CI gate).
"""

import argparse
import functools
import http.server
import json
import statistics
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import URLError

from dotenv import load_dotenv

from agent.harness import Harness
from agent.llm import MockLLM, OpenAILLM, qe_scenario
from agent.memory import Memory
from agent.tools import REPO_ROOT

EVALS_DIR = REPO_ROOT / "evals"
EXPECTED_FILE = EVALS_DIR / "expected_bugs.json"
PORT = 8000
GOOD = f"http://localhost:{PORT}/good/"
BUGGY = f"http://localhost:{PORT}/buggy/"


# ---------------------------------------------------------------- matching

def rule_matches(rule: dict, bug: dict) -> bool:
    """One rule, plain substring checks against the bug's structured evidence."""
    if "diff" in rule:
        return any(rule["where"] in line and rule["diff"] in line for line in bug["diff_evidence"])
    return bug["journey"] == rule["journey"] and any(rule["error"] in (e or "") for e in bug["errors"])


def match_bugs(reported: list[dict], expected: list[dict]) -> dict:
    """Assign each reported bug to the first expected bug it matches (in answer-key order).

    true positive  = reported bug that matches an expected bug not matched before
    duplicate      = reported bug that matches an expected bug already matched (not counted as wrong)
    false positive = reported bug that matches nothing
    """
    found, duplicates, false_positives, type_correct = {}, [], [], 0
    for bug in reported:
        hit = next((e for e in expected if any(rule_matches(r, bug) for r in e["match"])), None)
        if hit is None:
            false_positives.append(bug["title"])
        elif hit["id"] in found:
            duplicates.append(f"{hit['id']}: {bug['title']}")
        else:
            found[hit["id"]] = bug["title"]
            type_correct += bug["category"] == hit["type"]
    missed = [e["id"] for e in expected if e["id"] not in found]
    true_positives = len(found)
    return {
        "found": found,
        "missed": missed,
        "duplicates": duplicates,
        "false_positives": false_positives,
        "recall": true_positives / len(expected) if expected else 1.0,
        "precision": (true_positives + len(duplicates)) / len(reported) if reported else 1.0,
        "type_accuracy": type_correct / true_positives if true_positives else None,
    }


# ---------------------------------------------------------------- running the agent

def ensure_portal() -> str:
    """Use the running portal, or serve portal/ on a background thread (handy in CI)."""
    try:
        urllib.request.urlopen(GOOD, timeout=2)
        return "already running"
    except URLError:
        pass

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(REPO_ROOT / "portal"))
    server = http.server.ThreadingHTTPServer(("localhost", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "started by run_eval"


def make_llm(real: bool, release_url: str):
    return OpenAILLM() if real else MockLLM(qe_scenario(GOOD, release_url))


def run_agent(real: bool, release_url: str, run_dir: Path) -> dict:
    harness = Harness(make_llm(real, release_url), GOOD, release_url, run_dir=run_dir,
                      memory=Memory(enabled=False))
    return harness.run()


def run_metrics(summary: dict) -> dict:
    return {key: summary[key] for key in ("stop_reason", "steps", "tool_calls", "harness_test_runs",
                                           "total_tokens", "total_cost_usd", "duration_s")} | {
        "healed": len(summary["healed"]), "report": summary["report"]}


# ---------------------------------------------------------------- output

def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 4) if values else None


def to_markdown(results: dict) -> str:
    t = results["totals"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:.0f}%"
    lines = [
        f"# PortalGuard eval ({results['mode']}, {results['repeats']} repeat(s), {results['started_at']})",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Recall (planted bugs found) | {pct(t['recall'])} |",
        f"| Precision (reported bugs that are real) | {pct(t['precision'])} |",
        f"| Bug type accuracy | {pct(t['type_accuracy'])} |",
        f"| False alarms on good release | {t['false_alarms_on_good']} |",
        f"| Tests healed (buggy + good) | {t['tests_healed']} |",
        f"| LLM steps (buggy + good) | {t['steps']} |",
        f"| Tokens (buggy + good) | {t['tokens']:,} |",
        f"| Cost (buggy + good) | ${t['cost_usd']:.4f} |",
        f"| Duration (buggy + good) | {t['duration_s']}s |",
        f"| Gate (recall >= {results['gate']['min_recall']}, false alarms <= "
        f"{results['gate']['max_false_alarms']}) | {'PASS' if results['gate']['passed'] else 'FAIL'} |",
        "",
        "## Per planted bug",
        "",
        "| Bug | Type | Found in | Reported as |",
        "|---|---|---|---|",
    ]
    for bug in results["expected"]:
        hits = [r for r in results["runs"] if bug["id"] in r["buggy"]["match"]["found"]]
        reported = hits[0]["buggy"]["match"]["found"][bug["id"]] if hits else "missed"
        lines.append(f"| {bug['id']} {bug['title']} | {bug['type']} | {len(hits)}/{len(results['runs'])} runs | "
                     f"{reported.replace('|', '/')} |")
    lines += ["", "## Per run", "",
              "| Repeat | Release | Stop | Bugs reported | Recall | Precision | Healed | Steps | Tokens | Cost | Duration |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results["runs"]:
        for release in ("buggy", "good"):
            m, run = r[release]["match"], r[release]["run"]
            lines.append(
                f"| {r['repeat']} | {release} | `{run['stop_reason']}` | {r[release]['bugs_reported']} | "
                + (f"{pct(m['recall'])} | {pct(m['precision'])}" if release == "buggy" else "n/a | n/a")
                + f" | {run['healed']} | {run['steps']} | {run['total_tokens']:,} | ${run['total_cost_usd']:.4f} | "
                f"{run['duration_s']}s |")
    problems = [(r["repeat"], label, item) for r in results["runs"]
                for label, items in (("missed", r["buggy"]["match"]["missed"]),
                                     ("false positive (buggy)", r["buggy"]["match"]["false_positives"]),
                                     ("duplicate (buggy)", r["buggy"]["match"]["duplicates"]),
                                     ("false alarm (good)", r["good"]["bug_titles"]))
                for item in items]
    lines += ["", "## Misses and false alarms", ""]
    lines += [f"- repeat {n}, {label}: {item}" for n, label, item in problems] or ["None."]
    lines += ["", "Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", default=True, help="scripted fake LLM (default)")
    mode.add_argument("--real", action="store_true", help="gpt-4.1-mini via OPENAI_API_KEY in .env")
    parser.add_argument("--repeat", type=int, default=1, help="repeats (useful with --real: the model varies)")
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--max-false-alarms", type=int, default=0)
    args = parser.parse_args()

    if args.real:
        load_dotenv()
        try:
            OpenAILLM()
        except RuntimeError as e:
            print(e)
            return 2

    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["bugs"]
    started = datetime.now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    print(f"Portal: {ensure_portal()}. Mode: {'real' if args.real else 'mock'}. Memory: off.")

    runs = []
    for repeat in range(1, args.repeat + 1):
        row = {"repeat": repeat}
        for release, url in (("buggy", BUGGY), ("good", GOOD)):
            print(f"  repeat {repeat}: running agent on {release} ...", flush=True)
            summary = run_agent(args.real, url, REPO_ROOT / "runs" / f"eval-{stamp}-r{repeat}-{release}")
            row[release] = {
                "run": run_metrics(summary),
                "bugs_reported": len(summary["bugs"]),
                "bug_titles": [b["title"] for b in summary["bugs"]],
                "match": match_bugs(summary["bugs"], expected if release == "buggy" else []),
            }
        runs.append(row)

    both = [r[release]["run"] for r in runs for release in ("buggy", "good")]
    totals = {
        "recall": mean([r["buggy"]["match"]["recall"] for r in runs]),
        "precision": mean([r["buggy"]["match"]["precision"] for r in runs]),
        "type_accuracy": mean([r["buggy"]["match"]["type_accuracy"] for r in runs]),
        "false_alarms_on_good": sum(r["good"]["bugs_reported"] for r in runs),
        "tests_healed": sum(run["healed"] for run in both),
        "steps": sum(run["steps"] for run in both),
        "tokens": sum(run["total_tokens"] for run in both),
        "cost_usd": round(sum(run["total_cost_usd"] for run in both), 6),
        "duration_s": round(sum(run["duration_s"] for run in both), 1),
    }
    gate_passed = totals["recall"] >= args.min_recall and totals["false_alarms_on_good"] <= args.max_false_alarms
    results = {
        "mode": "real" if args.real else "mock",
        "repeats": args.repeat,
        "started_at": started.isoformat(timespec="seconds"),
        "memory": "off",
        "expected": [{k: b[k] for k in ("id", "title", "type")} for b in expected],
        "totals": totals,
        "gate": {"min_recall": args.min_recall, "max_false_alarms": args.max_false_alarms, "passed": gate_passed},
        "runs": runs,
    }

    (EVALS_DIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
    markdown = to_markdown(results)
    (EVALS_DIR / "results.md").write_text(markdown, encoding="utf-8", newline="\n")
    print("\n" + markdown)
    print("Saved evals/results.json and evals/results.md")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
