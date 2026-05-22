from __future__ import annotations

import logging
from pathlib import Path

from pdfdancer_preflight.analyzers import geometry, ghostscript, pdfbox
from pdfdancer_preflight.models import Finding, TargetConfig, should_fail

logger = logging.getLogger(__name__)


def run_preflight(pdf_path: Path, target: TargetConfig) -> dict:
    findings: list[Finding] = []

    logger.info("running analyzers")
    for analyzer_name, analyzer in (
        ("ghostscript", ghostscript.analyze),
        ("pdfbox", pdfbox.analyze),
        ("geometry", geometry.analyze),
    ):
        before = len(findings)
        logger.info("starting analyzer: %s", analyzer_name)
        analyzer_findings = analyzer(pdf_path, target)
        findings.extend(analyzer_findings)
        logger.info("finished analyzer: %s findings=%s", analyzer_name, len(findings) - before)

    failed = should_fail(findings, target.fail_at)
    logger.info(
        "severity evaluation complete: fail_at=%s failed=%s total_findings=%s",
        target.fail_at.name,
        failed,
        len(findings),
    )
    return {
        "ok": not failed,
        "failed": failed,
        "input": str(pdf_path),
        "fail_at": target.fail_at.name,
        "findings": [finding.to_json() for finding in findings],
    }
