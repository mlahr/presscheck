from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
        "summary": summarize_findings(findings),
        "findings": [finding.to_json() for finding in findings],
    }


def summarize_findings(findings: list[Finding]) -> dict[str, Any]:
    by_check: dict[tuple[str, str], dict[str, Any]] = {}
    by_severity = {"info": 0, "warning": 0, "error": 0}

    for finding in findings:
        severity = finding.severity.name
        by_severity[severity] += 1

        entry = by_check.setdefault(
            (finding.check_id, severity),
            {
                "check_id": finding.check_id,
                "category": finding.category,
                "severity": severity,
                "count": 0,
                "pages": set(),
            },
        )
        entry["count"] += 1
        if finding.page is not None:
            entry["pages"].add(finding.page)
        observed_pages = finding.observed.get("pages")
        if isinstance(observed_pages, list):
            for page in observed_pages:
                if isinstance(page, int):
                    entry["pages"].add(page)

    checks = []
    for entry in by_check.values():
        checks.append(
            {
                "check_id": entry["check_id"],
                "category": entry["category"],
                "severity": entry["severity"],
                "count": entry["count"],
                "pages": sorted(entry["pages"]),
            }
        )

    checks.sort(key=lambda item: (item["category"], item["check_id"], item["severity"]))
    return {
        "total_findings": len(findings),
        "by_severity": by_severity,
        "by_check": checks,
    }
