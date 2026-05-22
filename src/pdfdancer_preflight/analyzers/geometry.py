from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from pdfdancer_preflight.models import Finding, TargetConfig

PAGE_BOXES_CHECK = "geometry.page_boxes_present"
TRIM_SIZE_CHECK = "geometry.trim_size_matches"
BLEED_MARGIN_CHECK = "geometry.bleed_margin_at_least"
logger = logging.getLogger(__name__)

BOX_KEYS = {
    "MediaBox": "/MediaBox",
    "TrimBox": "/TrimBox",
    "BleedBox": "/BleedBox",
    "CropBox": "/CropBox",
}


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    if (
        target.check(PAGE_BOXES_CHECK) is None
        and target.check(TRIM_SIZE_CHECK) is None
        and target.check(BLEED_MARGIN_CHECK) is None
    ):
        logger.debug("all geometry checks disabled")
        return []

    logger.info("parsing PDF for geometry checks")
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            logger.error("PDF is encrypted; geometry checks unsupported")
            return [
                Finding(
                    check_id="document_integrity.encrypted_pdf",
                    category="document_integrity",
                    severity=_fallback_severity(target),
                    message="Encrypted PDFs are unsupported.",
                    analyzer="geometry",
                    observed={"encrypted": True},
                )
            ]
    except Exception as exc:
        logger.error("PDF parse failed for geometry checks: exception_type=%s", type(exc).__name__)
        return [
            Finding(
                check_id="document_integrity.pdf_parseable",
                category="document_integrity",
                severity=_fallback_severity(target),
                message="PDF could not be parsed for geometry checks.",
                analyzer="geometry",
                observed={"exception_type": type(exc).__name__},
            )
        ]

    findings: list[Finding] = []
    logger.info("PDF parsed for geometry checks: pages=%s", len(reader.pages))
    page_boxes_check = target.check(PAGE_BOXES_CHECK)
    if page_boxes_check is not None:
        findings.extend(_check_page_boxes_present(reader, page_boxes_check.severity, page_boxes_check.params))

    trim_size_check = target.check(TRIM_SIZE_CHECK)
    if trim_size_check is not None:
        findings.extend(_check_trim_size(reader, trim_size_check.severity, trim_size_check.params))

    bleed_margin_check = target.check(BLEED_MARGIN_CHECK)
    if bleed_margin_check is not None:
        findings.extend(_check_bleed_margin(reader, bleed_margin_check.severity, bleed_margin_check.params))

    logger.info("geometry checks completed: findings=%s", len(findings))
    return findings


def _check_page_boxes_present(reader: PdfReader, severity, params: dict[str, Any]) -> list[Finding]:
    required = params.get("required_boxes", ["MediaBox", "TrimBox", "BleedBox"])
    findings: list[Finding] = []
    for page_index, page in enumerate(reader.pages, start=1):
        for box_name in required:
            pdf_key = BOX_KEYS.get(str(box_name))
            if pdf_key is None:
                continue
            if page.get(pdf_key) is None:
                findings.append(
                    Finding(
                        check_id=PAGE_BOXES_CHECK,
                        category="geometry",
                        severity=severity,
                        message=f"Page is missing required {box_name}.",
                        analyzer="geometry",
                        page=page_index,
                        observed={"missing_box": box_name},
                        threshold={"required_boxes": required},
                    )
                )
    return findings


def _check_trim_size(reader: PdfReader, severity, params: dict[str, Any]) -> list[Finding]:
    expected_width = _required_number(params, "expected_width_pt", TRIM_SIZE_CHECK)
    expected_height = _required_number(params, "expected_height_pt", TRIM_SIZE_CHECK)
    tolerance = float(params.get("tolerance_pt", 0))

    findings: list[Finding] = []
    for page_index, page in enumerate(reader.pages, start=1):
        trim_box = page.get("/TrimBox")
        if trim_box is None:
            continue
        width = float(trim_box[2]) - float(trim_box[0])
        height = float(trim_box[3]) - float(trim_box[1])
        width_delta = abs(width - expected_width)
        height_delta = abs(height - expected_height)
        if width_delta > tolerance or height_delta > tolerance:
            findings.append(
                Finding(
                    check_id=TRIM_SIZE_CHECK,
                    category="geometry",
                    severity=severity,
                    message="TrimBox size does not match target trim size.",
                    analyzer="geometry",
                    page=page_index,
                    observed={"width_pt": width, "height_pt": height},
                    threshold={
                        "expected_width_pt": expected_width,
                        "expected_height_pt": expected_height,
                        "tolerance_pt": tolerance,
                    },
                )
            )
    return findings


def _check_bleed_margin(reader: PdfReader, severity, params: dict[str, Any]) -> list[Finding]:
    required_margin = _required_number(params, "margin_pt", BLEED_MARGIN_CHECK)
    tolerance = float(params.get("tolerance_pt", 0))

    findings: list[Finding] = []
    for page_index, page in enumerate(reader.pages, start=1):
        trim_box = page.get("/TrimBox")
        bleed_box = page.get("/BleedBox")
        if trim_box is None or bleed_box is None:
            continue

        margins = {
            "left_pt": float(trim_box[0]) - float(bleed_box[0]),
            "bottom_pt": float(trim_box[1]) - float(bleed_box[1]),
            "right_pt": float(bleed_box[2]) - float(trim_box[2]),
            "top_pt": float(bleed_box[3]) - float(trim_box[3]),
        }
        too_small = {side: value for side, value in margins.items() if value + tolerance < required_margin}
        if too_small:
            findings.append(
                Finding(
                    check_id=BLEED_MARGIN_CHECK,
                    category="geometry",
                    severity=severity,
                    message="BleedBox does not extend far enough beyond TrimBox.",
                    analyzer="geometry",
                    page=page_index,
                    observed={"margins": margins, "too_small": too_small},
                    threshold={"margin_pt": required_margin, "tolerance_pt": tolerance},
                )
            )
    return findings


def _required_number(params: dict[str, Any], name: str, check_id: str) -> float:
    value = params.get(name)
    if not isinstance(value, int | float):
        raise ValueError(f"check '{check_id}' requires numeric parameter '{name}'")
    return float(value)


def _fallback_severity(target: TargetConfig):
    for check_id in (PAGE_BOXES_CHECK, TRIM_SIZE_CHECK, BLEED_MARGIN_CHECK):
        check = target.check(check_id)
        if check is not None:
            return check.severity
    return target.fail_at
