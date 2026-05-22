from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from pdfdancer_preflight.models import Finding, Severity, TargetConfig

NON_EMBEDDED_FONTS_CHECK = "fonts.non_embedded"
FAILURE_CHECK = "document_integrity.pdfbox_analyzer_failed"
DEFAULT_TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    check = target.check(NON_EMBEDDED_FONTS_CHECK)
    if check is None:
        logger.debug("check disabled: %s", NON_EMBEDDED_FONTS_CHECK)
        return []

    jar_path = _jar_path()
    if not jar_path.exists():
        logger.error("PDFBox analyzer jar not found: %s", jar_path)
        return [_failure("PDFBox analyzer jar was not found.", target, {"jar_path": str(jar_path)})]

    timeout = float(check.params.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    logger.info("running PDFBox analyzer: jar=%s timeout_seconds=%s", jar_path, timeout)
    try:
        completed = subprocess.run(
            ["java", "-jar", str(jar_path), str(pdf_path)],
            check=False,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    except FileNotFoundError:
        logger.error("Java executable not found")
        return [_failure("Java executable was not found.", target, {"executable": "java"})]
    except subprocess.TimeoutExpired:
        logger.error("PDFBox analyzer timed out: timeout_seconds=%s", timeout)
        return [_failure("PDFBox analyzer timed out.", target, {"timeout_seconds": timeout})]

    if completed.returncode != 0:
        logger.error("PDFBox analyzer failed: exit_code=%s", completed.returncode)
        return [_failure("PDFBox analyzer failed.", target, {"exit_code": completed.returncode})]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        logger.error("PDFBox analyzer emitted invalid JSON")
        return [_failure("PDFBox analyzer emitted invalid JSON.", target, {})]

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        logger.error("PDFBox analyzer returned unsuccessful payload")
        return [_failure("PDFBox analyzer returned an unsuccessful result.", target, {})]

    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        logger.error("PDFBox analyzer evidence was not a list")
        return [_failure("PDFBox analyzer evidence was not a list.", target, {})]

    font_evidence = [item for item in evidence if _is_non_embedded_font_evidence(item)]
    findings = _group_non_embedded_font_findings(font_evidence, check.severity)
    logger.info(
        "PDFBox analyzer completed: evidence=%s font_evidence=%s findings=%s",
        len(evidence),
        len(font_evidence),
        len(findings),
    )
    return findings


def _jar_path() -> Path:
    override = os.environ.get("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR")
    if override:
        return Path(override)
    return Path.cwd() / "analyzers" / "pdfbox" / "build" / "libs" / "pdfbox-analyzer.jar"


def _is_non_embedded_font_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == NON_EMBEDDED_FONTS_CHECK and item.get("embedded") is False


def _group_non_embedded_font_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in evidence:
        font_name = str(item.get("font_name", "unknown"))
        subtype = str(item.get("subtype", "unknown"))
        group = groups.setdefault(
            (font_name, subtype),
            {
                "font_name": font_name,
                "subtype": subtype,
                "occurrences": 0,
                "pages": set(),
                "resource_names": set(),
            },
        )
        group["occurrences"] += 1
        page = item.get("page")
        if isinstance(page, int):
            group["pages"].add(page)
        resource_name = item.get("resource_name")
        if resource_name is not None:
            group["resource_names"].add(str(resource_name))

    findings = []
    for group in groups.values():
        findings.append(
            Finding(
                check_id=NON_EMBEDDED_FONTS_CHECK,
                category="fonts",
                severity=severity,
                message=f"Font is not embedded: {group['font_name']}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                observed={
                    "font_name": group["font_name"],
                    "subtype": group["subtype"],
                    "embedded": False,
                    "occurrences": group["occurrences"],
                    "resource_names": sorted(group["resource_names"]),
                    "pages": sorted(group["pages"]),
                },
            )
        )

    findings.sort(key=lambda finding: (finding.observed["font_name"], finding.observed["subtype"]))
    return findings


def _failure(message: str, target: TargetConfig, observed: dict[str, Any]) -> Finding:
    return Finding(
        check_id=FAILURE_CHECK,
        category="document_integrity",
        severity=target.fail_at,
        message=message,
        analyzer="pdfbox",
        source_tool="pdfbox",
        observed=observed,
    )
