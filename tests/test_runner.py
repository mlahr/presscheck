from pdfdancer_preflight.models import Finding, Severity, should_fail
from pdfdancer_preflight.runner import summarize_findings


def test_should_fail_at_configured_threshold() -> None:
    findings = [
        Finding(
            check_id="example",
            category="document_integrity",
            severity=Severity.warning,
            message="warning",
            analyzer="test",
        )
    ]

    assert should_fail(findings, Severity.warning)
    assert not should_fail(findings, Severity.error)


def test_summarize_findings_groups_by_check_and_severity() -> None:
    findings = [
        Finding(
            check_id="fonts.non_embedded",
            category="fonts",
            severity=Severity.error,
            message="font",
            analyzer="test",
            observed={"pages": [2, 4]},
        ),
        Finding(
            check_id="fonts.non_embedded",
            category="fonts",
            severity=Severity.error,
            message="font",
            analyzer="test",
            observed={"pages": [1, 2]},
        ),
        Finding(
            check_id="geometry.page_boxes_present",
            category="geometry",
            severity=Severity.warning,
            message="box",
            analyzer="test",
        ),
        Finding(
            check_id="geometry.page_boxes_present",
            category="geometry",
            severity=Severity.error,
            message="box",
            analyzer="test",
            page=3,
        ),
    ]

    summary = summarize_findings(findings)

    assert summary["total_findings"] == 4
    assert summary["by_severity"] == {"info": 0, "warning": 1, "error": 3}
    assert summary["by_check"] == [
        {
            "check_id": "fonts.non_embedded",
            "category": "fonts",
            "severity": "error",
            "count": 2,
            "pages": [1, 2, 4],
        },
        {
            "check_id": "geometry.page_boxes_present",
            "category": "geometry",
            "severity": "error",
            "count": 1,
            "pages": [3],
        },
        {
            "check_id": "geometry.page_boxes_present",
            "category": "geometry",
            "severity": "warning",
            "count": 1,
            "pages": [],
        },
    ]
