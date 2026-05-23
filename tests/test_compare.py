from pathlib import Path

from presscheck.compare import compare_results, comparison_output_paths, format_comparison


def test_compare_results_classifies_summary_changes(tmp_path: Path) -> None:
    before = _result(
        "before.pdf",
        [
            _check("fonts", "fonts.non_embedded", "error", 2, [1, 2]),
            _check("geometry", "geometry.page_boxes_present", "error", 1, [3]),
            _check("images", "images.low_effective_resolution", "warning", 2, [5, 6]),
            _check("pages", "pages.blank_policy", "warning", 1, [7]),
            _check("color", "color.output_intent_required", "error", 1, [8]),
        ],
    )
    after = _result(
        "after.pdf",
        [
            _check("fonts", "fonts.non_embedded", "error", 3, [1, 2, 4]),
            _check("images", "images.low_effective_resolution", "warning", 1, [5]),
            _check("pages", "pages.blank_policy", "warning", 1, [9]),
            _check("interactive", "interactive.javascript_policy", "error", 1, [10]),
        ],
    )

    comparison = compare_results(before, after, tmp_path / "before.json", tmp_path / "after.json")

    assert comparison["regressed"] is True
    assert comparison["summary_delta"] == {
        "total_findings": -1,
        "by_severity": {"info": 0, "warning": -1, "error": 0},
    }
    assert [(entry["check_id"], entry["delta"]) for entry in comparison["changes"]["added"]] == [
        ("interactive.javascript_policy", 1)
    ]
    assert [(entry["check_id"], entry["delta"]) for entry in comparison["changes"]["resolved"]] == [
        ("color.output_intent_required", -1),
        ("geometry.page_boxes_present", -1),
    ]
    assert [(entry["check_id"], entry["delta"]) for entry in comparison["changes"]["worsened"]] == [
        ("fonts.non_embedded", 1)
    ]
    assert [(entry["check_id"], entry["delta"]) for entry in comparison["changes"]["improved"]] == [
        ("images.low_effective_resolution", -1)
    ]
    assert comparison["changes"]["changed_pages"][0]["check_id"] == "pages.blank_policy"
    assert comparison["changes"]["changed_pages"][0]["added_pages"] == [9]
    assert comparison["changes"]["changed_pages"][0]["removed_pages"] == [7]


def test_compare_results_ignores_warning_regression_when_fail_at_error(tmp_path: Path) -> None:
    before = _result("before.pdf", [])
    after = _result("after.pdf", [_check("images", "images.low_effective_resolution", "warning", 1, [1])])

    comparison = compare_results(before, after, tmp_path / "before.json", tmp_path / "after.json")

    assert comparison["regressed"] is False
    assert comparison["ok"] is True
    assert comparison["failed"] is False


def test_format_comparison_includes_human_summary(tmp_path: Path) -> None:
    before = _result("before.pdf", [_check("fonts", "fonts.non_embedded", "error", 2, [1, 2])])
    after = _result("after.pdf", [_check("fonts", "fonts.non_embedded", "error", 1, [1])])
    comparison = compare_results(before, after, tmp_path / "before.json", tmp_path / "after.json")

    output = format_comparison(comparison)

    assert "Preflight comparison" in output
    assert "total findings: 2 -> 1 (-1)" in output
    assert "improved: 1" in output
    assert "error fonts.non_embedded: 2 -> 1 (-1)" in output
    assert "regressed: false" in output


def test_comparison_output_paths_derive_before_and_after_files() -> None:
    before, after = comparison_output_paths(Path("nested/compare.json"))

    assert before == Path("nested/compare.before.json")
    assert after == Path("nested/compare.after.json")


def _result(input_path: str, checks: list[dict]) -> dict:
    by_severity = {"info": 0, "warning": 0, "error": 0}
    for check in checks:
        by_severity[check["severity"]] += check["count"]
    failed = by_severity["error"] > 0
    return {
        "ok": not failed,
        "failed": failed,
        "input": input_path,
        "fail_at": "error",
        "summary": {
            "total_findings": sum(by_severity.values()),
            "by_severity": by_severity,
            "by_check": checks,
            "color": {"image_color_space_findings_by_family": {}},
        },
        "findings": [],
    }


def _check(category: str, check_id: str, severity: str, count: int, pages: list[int]) -> dict:
    return {
        "category": category,
        "check_id": check_id,
        "severity": severity,
        "count": count,
        "pages": pages,
    }
