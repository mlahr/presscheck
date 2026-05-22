from pdfdancer_preflight.models import Finding, Severity, should_fail


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

