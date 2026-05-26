from __future__ import annotations

from pathlib import Path
from typing import Any

from presscheck.models import Severity

CHANGE_GROUPS = ("added", "resolved", "worsened", "improved", "changed_pages")


def compare_results(
    before: dict[str, Any],
    after: dict[str, Any],
    before_output: Path | None = None,
    after_output: Path | None = None,
) -> dict[str, Any]:
    fail_at = Severity.parse(str(after["fail_at"]))
    changes = _compare_checks(before["summary"]["by_check"], after["summary"]["by_check"])
    regressed = _has_regression(changes, fail_at)
    result = {
        "ok": not regressed,
        "failed": regressed,
        "regressed": regressed,
        "fail_at": fail_at.name,
        "before": {
            "input": before["input"],
            "ok": before["ok"],
            "failed": before["failed"],
            "summary": before["summary"],
        },
        "after": {
            "input": after["input"],
            "ok": after["ok"],
            "failed": after["failed"],
            "summary": after["summary"],
        },
        "summary_delta": _summary_delta(before["summary"], after["summary"]),
        "changes": changes,
    }
    if before_output is not None:
        result["before"]["output"] = str(before_output)
    if after_output is not None:
        result["after"]["output"] = str(after_output)
    return result


def format_comparison(result: dict[str, Any]) -> str:
    before_summary = result["before"]["summary"]
    after_summary = result["after"]["summary"]
    summary_delta = result["summary_delta"]
    lines = [
        "Preflight comparison",
        f"before: {result['before']['input']}",
        f"after:  {result['after']['input']}",
        f"total findings: {before_summary['total_findings']} -> {after_summary['total_findings']} "
        f"({summary_delta['total_findings']:+d})",
        "severity: "
        f"info {before_summary['by_severity']['info']} -> {after_summary['by_severity']['info']} "
        f"({summary_delta['by_severity']['info']:+d}), "
        f"warning {before_summary['by_severity']['warning']} -> {after_summary['by_severity']['warning']} "
        f"({summary_delta['by_severity']['warning']:+d}), "
        f"error {before_summary['by_severity']['error']} -> {after_summary['by_severity']['error']} "
        f"({summary_delta['by_severity']['error']:+d})",
    ]

    for group in CHANGE_GROUPS:
        entries = result["changes"][group]
        lines.append(f"{group}: {len(entries)}")
        for entry in entries:
            lines.append(
                f"  {entry['severity']} {entry['check_id']}: "
                f"{entry['before_count']} -> {entry['after_count']} ({entry['delta']:+d})"
            )

    lines.append(f"regressed: {str(result['regressed']).lower()}")
    return "\n".join(lines) + "\n"


def comparison_output_paths(output: Path) -> tuple[Path, Path]:
    suffix = output.suffix or ".json"
    stem = output.with_suffix("")
    return stem.with_name(f"{stem.name}.before{suffix}"), stem.with_name(f"{stem.name}.after{suffix}")


def _compare_checks(
    before_checks: list[dict[str, Any]], after_checks: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    before_by_key = {_check_key(check): check for check in before_checks}
    after_by_key = {_check_key(check): check for check in after_checks}
    changes: dict[str, list[dict[str, Any]]] = {group: [] for group in CHANGE_GROUPS}

    for key in sorted(before_by_key.keys() | after_by_key.keys()):
        before = before_by_key.get(key)
        after = after_by_key.get(key)
        before_count = int(before["count"]) if before is not None else 0
        after_count = int(after["count"]) if after is not None else 0
        before_pages = set(before["pages"]) if before is not None else set()
        after_pages = set(after["pages"]) if after is not None else set()
        if before_count == after_count and before_pages == after_pages:
            continue

        entry = {
            "category": key[0],
            "check_id": key[1],
            "severity": key[2],
            "before_count": before_count,
            "after_count": after_count,
            "delta": after_count - before_count,
            "before_pages": sorted(before_pages),
            "after_pages": sorted(after_pages),
            "added_pages": sorted(after_pages - before_pages),
            "removed_pages": sorted(before_pages - after_pages),
        }
        if before_count == 0:
            changes["added"].append(entry)
        elif after_count == 0:
            changes["resolved"].append(entry)
        elif after_count > before_count:
            changes["worsened"].append(entry)
        elif after_count < before_count:
            changes["improved"].append(entry)
        else:
            changes["changed_pages"].append(entry)

    return changes


def _summary_delta(before_summary: dict[str, Any], after_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_findings": int(after_summary["total_findings"]) - int(before_summary["total_findings"]),
        "by_severity": {
            severity: int(after_summary["by_severity"][severity]) - int(before_summary["by_severity"][severity])
            for severity in ("info", "warning", "error")
        },
    }


def _has_regression(changes: dict[str, list[dict[str, Any]]], fail_at: Severity) -> bool:
    regression_groups = changes["added"] + changes["worsened"]
    return any(Severity.parse(change["severity"]) >= fail_at for change in regression_groups)


def _check_key(check: dict[str, Any]) -> tuple[str, str, str]:
    return (str(check["category"]), str(check["check_id"]), str(check["severity"]))
