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
        Finding(
            check_id="color.image_color_space_policy",
            category="color",
            severity=Severity.warning,
            message="rgb",
            analyzer="test",
            page=5,
            observed={"color_space_family": "ICCBasedRGB"},
        ),
        Finding(
            check_id="color.image_color_space_policy",
            category="color",
            severity=Severity.warning,
            message="indexed",
            analyzer="test",
            page=6,
            observed={"color_space_family": "Indexed"},
        ),
        Finding(
            check_id="color.image_color_space_policy",
            category="color",
            severity=Severity.warning,
            message="rgb",
            analyzer="test",
            page=7,
            observed={"color_space_family": "ICCBasedRGB"},
        ),
    ]

    summary = summarize_findings(findings)

    assert summary["total_findings"] == 7
    assert summary["by_severity"] == {"info": 0, "warning": 4, "error": 3}
    assert summary["by_check"] == [
        {
            "check_id": "color.image_color_space_policy",
            "category": "color",
            "severity": "warning",
            "count": 3,
            "pages": [5, 6, 7],
        },
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
    assert summary["color"]["image_color_space_families"] == {"ICCBasedRGB": 2, "Indexed": 1}
