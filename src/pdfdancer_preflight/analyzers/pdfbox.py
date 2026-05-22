from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from pdfdancer_preflight.models import Finding, Severity, TargetConfig


NON_EMBEDDED_FONTS_CHECK = "fonts.non_embedded"
FAILURE_CHECK = "document_integrity.pdfbox_analyzer_failed"
DEFAULT_TIMEOUT_SECONDS = 60


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    check = target.check(NON_EMBEDDED_FONTS_CHECK)
    if check is None:
        return []

    jar_path = _jar_path()
    if not jar_path.exists():
        return [_failure("PDFBox analyzer jar was not found.", target, {"jar_path": str(jar_path)})]

    timeout = float(check.params.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    try:
        completed = subprocess.run(
            ["java", "-jar", str(jar_path), str(pdf_path)],
            check=False,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    except FileNotFoundError:
        return [_failure("Java executable was not found.", target, {"executable": "java"})]
    except subprocess.TimeoutExpired:
        return [_failure("PDFBox analyzer timed out.", target, {"timeout_seconds": timeout})]

    if completed.returncode != 0:
        return [_failure("PDFBox analyzer failed.", target, {"exit_code": completed.returncode})]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [_failure("PDFBox analyzer emitted invalid JSON.", target, {})]

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return [_failure("PDFBox analyzer returned an unsuccessful result.", target, {})]

    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        return [_failure("PDFBox analyzer evidence was not a list.", target, {})]

    return [_font_finding(item, check.severity) for item in evidence if _is_non_embedded_font_evidence(item)]


def _jar_path() -> Path:
    override = os.environ.get("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR")
    if override:
        return Path(override)
    return Path.cwd() / "analyzers" / "pdfbox" / "build" / "libs" / "pdfbox-analyzer.jar"


def _is_non_embedded_font_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == NON_EMBEDDED_FONTS_CHECK and item.get("embedded") is False


def _font_finding(item: dict[str, Any], severity: Severity) -> Finding:
    font_name = str(item.get("font_name", "unknown"))
    page = item.get("page")
    return Finding(
        check_id=NON_EMBEDDED_FONTS_CHECK,
        category="fonts",
        severity=severity,
        message=f"Font is not embedded: {font_name}.",
        analyzer="pdfbox",
        source_tool="pdfbox",
        page=page if isinstance(page, int) else None,
        object_ref=str(item["resource_name"]) if "resource_name" in item else None,
        observed={
            "font_name": font_name,
            "resource_name": item.get("resource_name"),
            "subtype": item.get("subtype"),
            "embedded": False,
        },
    )


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

