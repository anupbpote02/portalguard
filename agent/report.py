"""Write runs/<id>/report.md from harness state (triage records, budgets), never from the model's text."""

from pathlib import Path

from agent.triage import JOURNEYS, MAX_HEAL_ATTEMPTS, Triage

JOURNEY_ORDER = list(JOURNEYS.values())


def _one_line(text) -> str:
    return str(text or "").replace("\n", " ")


def _cell(text) -> str:
    """Text for a markdown table cell (pipes must be escaped there, and only there)."""
    return _one_line(text).replace("|", "\\|")


def _group_bugs(triage: Triage) -> list[dict]:
    """One finding per piece of evidence: tests that hit the same diff line are the same bug."""
    groups: dict[tuple, dict] = {}
    for record in triage.records("real_bug"):
        key = tuple(record["diff_evidence"]) or (record["test"],)
        group = groups.setdefault(key, {"evidence": record["diff_evidence"], "records": []})
        group["records"].append(record)
    order = {journey: i for i, journey in enumerate(JOURNEY_ORDER)}
    return sorted(groups.values(), key=lambda g: order.get(g["records"][0]["journey"], len(order)))


def _bug_title(group: dict) -> str:
    if group["evidence"]:
        where, change = group["evidence"][0].split(": ", 1)
        return f"{change} ({where})"
    record = group["records"][0]
    return f"{record['journey']} journey broken ({record['test']})"


def write_report(path: Path, summary: dict, triage: Triage, baseline_url: str, release_url: str,
                 model: str) -> Path:
    bugs = _group_bugs(triage)
    healed = triage.healed()
    flaky = triage.records("flaky")
    unconfirmed = triage.records("unconfirmed")
    gave_up = triage.records("gave_up") + triage.records("broken_test")
    run_id = Path(summary["run_dir"]).name

    lines = [
        f"# PortalGuard report: run {run_id}",
        "",
        f"- **Release under test:** {release_url}",
        f"- **Baseline (last good release):** {baseline_url}",
        f"- **Model:** {model}  |  **Stop reason:** `{summary['stop_reason']}`",
        "- Synthetic test data only. Verdicts come from Playwright assertions run by the harness "
        "(release runs, reruns, baseline runs), not from the model.",
        "",
        "## Summary",
        "",
        "| Real bugs | Healed tests | Flaky (not reported) | Unconfirmed | Broken tests left |",
        "|---|---|---|---|---|",
        f"| {len(bugs)} | {len(healed)} | {len(flaky)} | {len(unconfirmed)} | {len(gave_up)} |",
        "",
        "| LLM steps | Tool calls | Harness test runs | Tokens | Cost | Duration |",
        "|---|---|---|---|---|---|",
        f"| {summary['steps']} | {summary['tool_calls']} ({summary['blocked_calls']} blocked) | "
        f"{triage.harness_runs} | {summary['total_tokens']:,} | ${summary['total_cost_usd']:.4f} | "
        f"{summary['duration_s']}s |",
        "",
        "## Bugs found",
        "",
    ]
    if not bugs:
        lines += ["No real bugs found.", ""]
    for number, group in enumerate(bugs, 1):
        first = group["records"][0]
        lines += [
            f"### {number}. {_bug_title(group)}",
            "",
            f"- **Type:** {first['category']}" + (f"  |  **Journey:** {first['journey']}" if first["journey"] else ""),
            "- **Evidence:**",
        ]
        for record in group["records"]:
            lines += [
                f"  - Test `{record['test']}`: passed on baseline, failed on release "
                f"{len(record['release_runs'])}/{len(record['release_runs'])} runs"
                + (" (after healing)" if record.get("healed") else ""),
                f"  - Failure: `{_one_line(record['release_error'])}`",
            ]
        for line in group["evidence"]:
            lines.append(f"  - Snapshot diff: `{line}`")
        if not group["evidence"]:
            lines.append("  - Snapshot diff: no change in the accessibility tree (functional bug)")
        lines += [
            f"- **Reproduce:** `python -m pytest tests/generated/{first['file']} --base-url {release_url}`"
            f" (a copy of the test is kept in `runs/{run_id}/tests/`)",
            "",
        ]

    lines += ["## Healed tests", ""]
    if healed:
        lines += ["| Test | Attempts | Original error | Now |", "|---|---|---|---|"]
        for record in healed:
            now = {"passed": "passes on release", "real_bug": "valid; fails on release (bug above)"}.get(
                record["verdict"], record["verdict"])
            lines.append(f"| `{record['test']}` | {record['heal_attempts']}/{MAX_HEAL_ATTEMPTS} | "
                         f"`{_cell(record['first_error'])}` | {now} |")
    else:
        lines.append("None.")
    lines.append("")

    lines += ["## Flaky tests (not reported as bugs)", ""]
    lines += [f"- `{r['test']}`: {r['why']}" for r in flaky] or ["None."]
    lines.append("")

    if unconfirmed or gave_up:
        lines += ["## Needs human review", ""]
        lines += [f"- `{r['test']}` ({r['verdict']}): {r['why']}. Error: `{_one_line(r.get('release_error'))}`"
                  for r in unconfirmed + gave_up]
        lines.append("")

    lines += ["## Snapshot diff (baseline -> release)", ""]
    changes = (triage.diff or {}).get("changes", {})
    if changes:
        for where, items in changes.items():
            lines += [f"- **{where}**"] + [f"  - `{item}`" for item in items]
    else:
        lines.append("No snapshot diff recorded." if triage.diff is None else "No changes.")
    lines += ["", f"Trace: `runs/{run_id}/trace.jsonl`", ""]

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path
