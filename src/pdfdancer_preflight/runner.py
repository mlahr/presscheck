from __future__ import annotations

from pathlib import Path

from pdfdancer_preflight.analyzers import geometry, ghostscript, pdfbox
from pdfdancer_preflight.models import Finding, TargetConfig, should_fail


def run_preflight(pdf_path: Path, target: TargetConfig) -> dict:
    findings: list[Finding] = []

    findings.extend(ghostscript.analyze(pdf_path, target))
    findings.extend(pdfbox.analyze(pdf_path, target))
    findings.extend(geometry.analyze(pdf_path, target))

    failed = should_fail(findings, target.fail_at)
    return {
        "ok": not failed,
        "failed": failed,
        "input": str(pdf_path),
        "fail_at": target.fail_at.name,
        "findings": [finding.to_json() for finding in findings],
    }
