from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from pdfdancer_preflight.models import Finding, Severity, TargetConfig

NON_EMBEDDED_FONTS_CHECK = "fonts.non_embedded"
LOW_EFFECTIVE_RESOLUTION_CHECK = "images.low_effective_resolution"
IMAGE_COLOR_SPACE_POLICY_CHECK = "color.image_color_space_policy"
OUTPUT_INTENT_REQUIRED_CHECK = "color.output_intent_required"
EFFECTIVE_RESOLUTION_EVIDENCE = "images.effective_resolution"
OUTPUT_INTENTS_EVIDENCE = "color.output_intents"
FAILURE_CHECK = "document_integrity.pdfbox_analyzer_failed"
DEFAULT_TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    enabled_checks = [
        check
        for check in (
            target.check(NON_EMBEDDED_FONTS_CHECK),
            target.check(LOW_EFFECTIVE_RESOLUTION_CHECK),
            target.check(IMAGE_COLOR_SPACE_POLICY_CHECK),
            target.check(OUTPUT_INTENT_REQUIRED_CHECK),
        )
        if check is not None
    ]
    if not enabled_checks:
        logger.debug("all PDFBox-backed checks disabled")
        return []

    jar_path = _jar_path()
    if not jar_path.exists():
        logger.error("PDFBox analyzer jar not found: %s", jar_path)
        return [_failure("PDFBox analyzer jar was not found.", target, {"jar_path": str(jar_path)})]

    timeout = max(float(check.params.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)) for check in enabled_checks)
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

    findings: list[Finding] = []

    font_check = target.check(NON_EMBEDDED_FONTS_CHECK)
    font_evidence = [item for item in evidence if _is_non_embedded_font_evidence(item)]
    if font_check is not None:
        findings.extend(_group_non_embedded_font_findings(font_evidence, font_check.severity))

    image_check = target.check(LOW_EFFECTIVE_RESOLUTION_CHECK)
    image_evidence = [item for item in evidence if _is_effective_resolution_evidence(item)]
    if image_check is not None:
        findings.extend(_low_resolution_image_findings(image_evidence, image_check.severity, image_check.params))

    color_check = target.check(IMAGE_COLOR_SPACE_POLICY_CHECK)
    if color_check is not None:
        findings.extend(_image_color_space_policy_findings(image_evidence, color_check.params))

    output_intent_check = target.check(OUTPUT_INTENT_REQUIRED_CHECK)
    output_intent_evidence = [item for item in evidence if _is_output_intents_evidence(item)]
    if output_intent_check is not None:
        findings.extend(_output_intent_required_findings(output_intent_evidence, output_intent_check.severity))

    logger.info(
        "PDFBox analyzer completed: evidence=%s font_evidence=%s image_evidence=%s "
        "output_intent_evidence=%s findings=%s",
        len(evidence),
        len(font_evidence),
        len(image_evidence),
        len(output_intent_evidence),
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


def _is_effective_resolution_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == EFFECTIVE_RESOLUTION_EVIDENCE


def _is_output_intents_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == OUTPUT_INTENTS_EVIDENCE


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


def _low_resolution_image_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    min_dpi_threshold = _required_number(params, "min_dpi", LOW_EFFECTIVE_RESOLUTION_CHECK)
    findings = []
    for item in evidence:
        min_dpi = _number_or_none(item.get("min_dpi"))
        if min_dpi is None or min_dpi >= min_dpi_threshold:
            continue

        page = item.get("page")
        resource_name = item.get("resource_name")
        findings.append(
            Finding(
                check_id=LOW_EFFECTIVE_RESOLUTION_CHECK,
                category="images",
                severity=severity,
                message=f"Image effective resolution is below {min_dpi_threshold:g} DPI.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=str(resource_name) if resource_name is not None else None,
                observed={
                    "pixel_width": item.get("pixel_width"),
                    "pixel_height": item.get("pixel_height"),
                    "drawn_width_pt": item.get("drawn_width_pt"),
                    "drawn_height_pt": item.get("drawn_height_pt"),
                    "x_dpi": item.get("x_dpi"),
                    "y_dpi": item.get("y_dpi"),
                    "min_dpi": min_dpi,
                },
                threshold={"min_dpi": min_dpi_threshold},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["min_dpi"]))
    return findings


def _image_color_space_policy_findings(evidence: list[dict[str, Any]], params: dict[str, Any]) -> list[Finding]:
    severity_by_family = params.get("severity_by_family")
    if not isinstance(severity_by_family, dict):
        raise ValueError(f"check '{IMAGE_COLOR_SPACE_POLICY_CHECK}' requires mapping parameter 'severity_by_family'")

    findings = []
    for item in evidence:
        family = item.get("color_space_family")
        if not isinstance(family, str):
            continue
        severity_raw = severity_by_family.get(family)
        if severity_raw is None:
            continue
        if not isinstance(severity_raw, str):
            raise ValueError(
                f"check '{IMAGE_COLOR_SPACE_POLICY_CHECK}' severity for family '{family}' must be null or a string"
            )
        severity = Severity.parse(severity_raw)
        page = item.get("page")
        resource_name = item.get("resource_name")
        findings.append(
            Finding(
                check_id=IMAGE_COLOR_SPACE_POLICY_CHECK,
                category="color",
                severity=severity,
                message=f"Image uses color space family {family}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=str(resource_name) if resource_name is not None else None,
                observed={
                    "color_space_name": item.get("color_space_name"),
                    "color_space_family": family,
                    "resource_name": resource_name,
                },
                threshold={"severity_by_family": {family: severity.name}},
            )
        )

    findings.sort(
        key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["color_space_family"])
    )
    return findings


def _output_intent_required_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    count = 0 if not evidence else evidence[0].get("count")
    if count != 0:
        return []

    return [
        Finding(
            check_id=OUTPUT_INTENT_REQUIRED_CHECK,
            category="color",
            severity=severity,
            message="PDF has no OutputIntent.",
            analyzer="pdfbox",
            source_tool="pdfbox",
            observed={"count": 0},
        )
    ]


def _required_number(params: dict[str, Any], name: str, check_id: str) -> float:
    value = params.get(name)
    if not isinstance(value, int | float):
        raise ValueError(f"check '{check_id}' requires numeric parameter '{name}'")
    return float(value)


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


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
