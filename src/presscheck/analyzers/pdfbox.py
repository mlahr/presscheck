from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pypdf import PdfReader

from presscheck.models import Finding, Severity, TargetConfig

NON_EMBEDDED_FONTS_CHECK = "fonts.non_embedded"
MINIMUM_TEXT_SIZE_CHECK = "fonts.minimum_text_size"
LOW_EFFECTIVE_RESOLUTION_CHECK = "images.low_effective_resolution"
JPEG_COMPRESSION_POLICY_CHECK = "images.jpeg_compression_policy"
IMAGE_FILTER_POLICY_CHECK = "images.image_filter_policy"
IMAGE_SOFT_MASK_CHECK = "images.has_soft_mask"
IMAGE_COLOR_SPACE_POLICY_CHECK = "color.image_color_space_policy"
OUTPUT_INTENT_REQUIRED_CHECK = "color.output_intent_required"
LIVE_TRANSPARENCY_POLICY_CHECK = "transparency.live_transparency_policy"
OBJECT_BOUNDS_WITHIN_BOX_CHECK = "geometry.object_bounds_within_box"
SAFE_AREA_MARGIN_CHECK = "geometry.safe_area_margin"
REGISTRATION_COLOR_MISUSE_CHECK = "color.registration_color_misuse"
SPOT_COLOR_POLICY_CHECK = "color.spot_color_policy"
OVERPRINT_POLICY_CHECK = "graphics.overprint_policy"
ANNOTATION_POLICY_CHECK = "interactive.annotation_policy"
LINK_URI_POLICY_CHECK = "interactive.link_uri_policy"
ANNOTATION_BOUNDS_CHECK = "interactive.annotation_bounds_within_box"
JAVASCRIPT_POLICY_CHECK = "interactive.javascript_policy"
EMBEDDED_FILES_POLICY_CHECK = "interactive.embedded_files_policy"
FORM_POLICY_CHECK = "interactive.form_policy"
BLANK_PAGE_POLICY_CHECK = "pages.blank_policy"
PDF_VERSION_POLICY_CHECK = "document_metadata.pdf_version_policy"
PDFA_POLICY_CHECK = "document_metadata.pdfa_policy"
PDFX_POLICY_CHECK = "document_metadata.pdfx_policy"
PRODUCER_POLICY_CHECK = "document_metadata.producer_policy"
EFFECTIVE_RESOLUTION_EVIDENCE = "images.effective_resolution"
TEXT_SIZE_EVIDENCE = "fonts.text_size"
OUTPUT_INTENTS_EVIDENCE = "color.output_intents"
TRANSPARENCY_FEATURES_EVIDENCE = "transparency.features"
OBJECT_BOUNDS_EVIDENCE = "geometry.object_bounds"
TEXT_BOUNDS_EVIDENCE = "geometry.text_bounds"
SPECIAL_COLOR_USAGE_EVIDENCE = "color.special_color_usage"
OVERPRINT_USAGE_EVIDENCE = "graphics.overprint_usage"
ANNOTATIONS_EVIDENCE = "interactive.annotations"
DOCUMENT_ACTIONS_EVIDENCE = "interactive.document_actions"
EMBEDDED_FILES_EVIDENCE = "interactive.embedded_files"
FORMS_EVIDENCE = "interactive.forms"
PAGE_CONTENT_EVIDENCE = "pages.page_content"
PDF_VERSION_EVIDENCE = "document_metadata.pdf_version"
DOCUMENT_INFO_EVIDENCE = "document_metadata.info"
XMP_STANDARDS_EVIDENCE = "document_metadata.xmp_standards"
FAILURE_CHECK = "document_integrity.pdfbox_analyzer_failed"
DEFAULT_TIMEOUT_SECONDS = 60
BOX_KEYS = {
    "MediaBox": "/MediaBox",
    "TrimBox": "/TrimBox",
    "BleedBox": "/BleedBox",
    "CropBox": "/CropBox",
}
logger = logging.getLogger(__name__)


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    enabled_checks = [
        check
        for check in (
            target.check(NON_EMBEDDED_FONTS_CHECK),
            target.check(MINIMUM_TEXT_SIZE_CHECK),
            target.check(LOW_EFFECTIVE_RESOLUTION_CHECK),
            target.check(JPEG_COMPRESSION_POLICY_CHECK),
            target.check(IMAGE_FILTER_POLICY_CHECK),
            target.check(IMAGE_SOFT_MASK_CHECK),
            target.check(IMAGE_COLOR_SPACE_POLICY_CHECK),
            target.check(OUTPUT_INTENT_REQUIRED_CHECK),
            target.check(LIVE_TRANSPARENCY_POLICY_CHECK),
            target.check(OBJECT_BOUNDS_WITHIN_BOX_CHECK),
            target.check(SAFE_AREA_MARGIN_CHECK),
            target.check(REGISTRATION_COLOR_MISUSE_CHECK),
            target.check(SPOT_COLOR_POLICY_CHECK),
            target.check(OVERPRINT_POLICY_CHECK),
            target.check(ANNOTATION_POLICY_CHECK),
            target.check(LINK_URI_POLICY_CHECK),
            target.check(ANNOTATION_BOUNDS_CHECK),
            target.check(JAVASCRIPT_POLICY_CHECK),
            target.check(EMBEDDED_FILES_POLICY_CHECK),
            target.check(FORM_POLICY_CHECK),
            target.check(BLANK_PAGE_POLICY_CHECK),
            target.check(PDF_VERSION_POLICY_CHECK),
            target.check(PDFA_POLICY_CHECK),
            target.check(PDFX_POLICY_CHECK),
            target.check(PRODUCER_POLICY_CHECK),
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

    text_size_check = target.check(MINIMUM_TEXT_SIZE_CHECK)
    text_size_evidence = [item for item in evidence if _is_text_size_evidence(item)]
    if text_size_check is not None:
        findings.extend(
            _minimum_text_size_findings(text_size_evidence, text_size_check.severity, text_size_check.params)
        )

    image_check = target.check(LOW_EFFECTIVE_RESOLUTION_CHECK)
    image_evidence = [item for item in evidence if _is_effective_resolution_evidence(item)]
    if image_check is not None:
        findings.extend(_low_resolution_image_findings(image_evidence, image_check.severity, image_check.params))

    jpeg_check = target.check(JPEG_COMPRESSION_POLICY_CHECK)
    if jpeg_check is not None:
        findings.extend(_jpeg_compression_policy_findings(image_evidence, jpeg_check.severity))

    image_filter_check = target.check(IMAGE_FILTER_POLICY_CHECK)
    if image_filter_check is not None:
        findings.extend(_image_filter_policy_findings(image_evidence, image_filter_check.params))

    image_soft_mask_check = target.check(IMAGE_SOFT_MASK_CHECK)
    if image_soft_mask_check is not None:
        findings.extend(_image_soft_mask_findings(image_evidence, image_soft_mask_check.severity))

    color_check = target.check(IMAGE_COLOR_SPACE_POLICY_CHECK)
    if color_check is not None:
        findings.extend(_image_color_space_policy_findings(image_evidence, color_check.params))

    output_intent_check = target.check(OUTPUT_INTENT_REQUIRED_CHECK)
    output_intent_evidence = [item for item in evidence if _is_output_intents_evidence(item)]
    if output_intent_check is not None:
        findings.extend(_output_intent_required_findings(output_intent_evidence, output_intent_check.severity))

    transparency_check = target.check(LIVE_TRANSPARENCY_POLICY_CHECK)
    transparency_evidence = [item for item in evidence if _is_transparency_features_evidence(item)]
    if transparency_check is not None:
        findings.extend(_live_transparency_policy_findings(transparency_evidence, transparency_check.params))

    object_bounds_check = target.check(OBJECT_BOUNDS_WITHIN_BOX_CHECK)
    object_bounds_evidence = [item for item in evidence if _is_object_bounds_evidence(item)]
    if object_bounds_check is not None:
        findings.extend(
            _object_bounds_within_box_findings(
                pdf_path,
                object_bounds_evidence,
                object_bounds_check.severity,
                object_bounds_check.params,
            )
        )

    text_bounds_evidence = [item for item in evidence if _is_text_bounds_evidence(item)]
    safe_area_check = target.check(SAFE_AREA_MARGIN_CHECK)
    if safe_area_check is not None:
        findings.extend(
            _safe_area_margin_findings(
                pdf_path,
                [*text_bounds_evidence, *object_bounds_evidence],
                safe_area_check.severity,
                safe_area_check.params,
            )
        )

    special_color_evidence = [item for item in evidence if _is_special_color_usage_evidence(item)]
    registration_color_check = target.check(REGISTRATION_COLOR_MISUSE_CHECK)
    if registration_color_check is not None:
        findings.extend(
            _registration_color_misuse_findings(special_color_evidence, registration_color_check.severity)
        )

    spot_color_check = target.check(SPOT_COLOR_POLICY_CHECK)
    if spot_color_check is not None:
        findings.extend(
            _spot_color_policy_findings(special_color_evidence, spot_color_check.severity, spot_color_check.params)
        )

    overprint_check = target.check(OVERPRINT_POLICY_CHECK)
    overprint_evidence = [item for item in evidence if _is_overprint_usage_evidence(item)]
    if overprint_check is not None:
        findings.extend(_overprint_policy_findings(overprint_evidence, overprint_check.severity))

    annotations_evidence = [item for item in evidence if _is_annotations_evidence(item)]
    annotation_check = target.check(ANNOTATION_POLICY_CHECK)
    if annotation_check is not None:
        findings.extend(_annotation_policy_findings(annotations_evidence, annotation_check.params))

    link_uri_check = target.check(LINK_URI_POLICY_CHECK)
    if link_uri_check is not None:
        findings.extend(_link_uri_policy_findings(annotations_evidence, link_uri_check.severity, link_uri_check.params))

    annotation_bounds_check = target.check(ANNOTATION_BOUNDS_CHECK)
    if annotation_bounds_check is not None:
        findings.extend(
            _annotation_bounds_findings(
                pdf_path,
                annotations_evidence,
                annotation_bounds_check.severity,
                annotation_bounds_check.params,
            )
        )

    document_actions_evidence = [item for item in evidence if _is_document_actions_evidence(item)]
    javascript_check = target.check(JAVASCRIPT_POLICY_CHECK)
    if javascript_check is not None:
        findings.extend(
            _javascript_policy_findings(annotations_evidence, document_actions_evidence, javascript_check.severity)
        )

    embedded_files_check = target.check(EMBEDDED_FILES_POLICY_CHECK)
    embedded_files_evidence = [item for item in evidence if _is_embedded_files_evidence(item)]
    if embedded_files_check is not None:
        findings.extend(_embedded_files_policy_findings(embedded_files_evidence, embedded_files_check.severity))

    form_check = target.check(FORM_POLICY_CHECK)
    forms_evidence = [item for item in evidence if _is_forms_evidence(item)]
    if form_check is not None:
        findings.extend(_form_policy_findings(forms_evidence, form_check.severity))

    page_content_evidence = [item for item in evidence if _is_page_content_evidence(item)]
    blank_page_check = target.check(BLANK_PAGE_POLICY_CHECK)
    if blank_page_check is not None:
        findings.extend(
            _blank_page_policy_findings(page_content_evidence, blank_page_check.severity, blank_page_check.params)
        )

    pdf_version_evidence = [item for item in evidence if _is_pdf_version_evidence(item)]
    pdf_version_check = target.check(PDF_VERSION_POLICY_CHECK)
    if pdf_version_check is not None:
        findings.extend(
            _pdf_version_policy_findings(pdf_version_evidence, pdf_version_check.severity, pdf_version_check.params)
        )

    xmp_standards_evidence = [item for item in evidence if _is_xmp_standards_evidence(item)]
    pdfa_check = target.check(PDFA_POLICY_CHECK)
    if pdfa_check is not None:
        findings.extend(_pdfa_policy_findings(xmp_standards_evidence, pdfa_check.severity, pdfa_check.params))

    pdfx_check = target.check(PDFX_POLICY_CHECK)
    if pdfx_check is not None:
        findings.extend(_pdfx_policy_findings(xmp_standards_evidence, pdfx_check.severity, pdfx_check.params))

    document_info_evidence = [item for item in evidence if _is_document_info_evidence(item)]
    producer_check = target.check(PRODUCER_POLICY_CHECK)
    if producer_check is not None:
        findings.extend(
            _producer_policy_findings(document_info_evidence, producer_check.severity, producer_check.params)
        )

    logger.info(
        "PDFBox analyzer completed: evidence=%s font_evidence=%s image_evidence=%s "
        "text_size_evidence=%s output_intent_evidence=%s transparency_evidence=%s "
        "object_bounds_evidence=%s text_bounds_evidence=%s special_color_evidence=%s overprint_evidence=%s "
        "annotations_evidence=%s document_actions_evidence=%s embedded_files_evidence=%s "
        "forms_evidence=%s page_content_evidence=%s pdf_version_evidence=%s "
        "xmp_standards_evidence=%s document_info_evidence=%s findings=%s",
        len(evidence),
        len(font_evidence),
        len(image_evidence),
        len(text_size_evidence),
        len(output_intent_evidence),
        len(transparency_evidence),
        len(object_bounds_evidence),
        len(text_bounds_evidence),
        len(special_color_evidence),
        len(overprint_evidence),
        len(annotations_evidence),
        len(document_actions_evidence),
        len(embedded_files_evidence),
        len(forms_evidence),
        len(page_content_evidence),
        len(pdf_version_evidence),
        len(xmp_standards_evidence),
        len(document_info_evidence),
        len(findings),
    )
    return findings


def _jar_path() -> Path:
    override = os.environ.get("PRESSCHECK_PDFBOX_ANALYZER_JAR")
    if override:
        return Path(override)
    return Path.cwd() / "analyzers" / "pdfbox" / "build" / "libs" / "pdfbox-analyzer.jar"


def _is_non_embedded_font_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == NON_EMBEDDED_FONTS_CHECK and item.get("embedded") is False


def _is_effective_resolution_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == EFFECTIVE_RESOLUTION_EVIDENCE


def _is_text_size_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == TEXT_SIZE_EVIDENCE


def _is_output_intents_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == OUTPUT_INTENTS_EVIDENCE


def _is_transparency_features_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == TRANSPARENCY_FEATURES_EVIDENCE


def _is_object_bounds_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == OBJECT_BOUNDS_EVIDENCE


def _is_text_bounds_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == TEXT_BOUNDS_EVIDENCE


def _is_special_color_usage_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == SPECIAL_COLOR_USAGE_EVIDENCE


def _is_overprint_usage_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == OVERPRINT_USAGE_EVIDENCE


def _is_annotations_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == ANNOTATIONS_EVIDENCE


def _is_document_actions_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == DOCUMENT_ACTIONS_EVIDENCE


def _is_embedded_files_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == EMBEDDED_FILES_EVIDENCE


def _is_forms_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == FORMS_EVIDENCE


def _is_page_content_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == PAGE_CONTENT_EVIDENCE


def _is_pdf_version_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == PDF_VERSION_EVIDENCE


def _is_document_info_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == DOCUMENT_INFO_EVIDENCE


def _is_xmp_standards_evidence(item: Any) -> bool:
    return isinstance(item, dict) and item.get("check_id") == XMP_STANDARDS_EVIDENCE


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


def _minimum_text_size_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    min_pt = _required_number(params, "min_pt", MINIMUM_TEXT_SIZE_CHECK)
    groups: dict[tuple[str, str, float, float], dict[str, Any]] = {}
    for item in evidence:
        effective_size = _number_or_none(item.get("effective_size_pt"))
        if effective_size is None or effective_size >= min_pt:
            continue
        horizontal_size = _number_or_none(item.get("horizontal_size_pt"))
        if horizontal_size is None:
            horizontal_size = effective_size
        font_name = str(item.get("font_name", "unknown"))
        subtype = str(item.get("subtype", "unknown"))
        group = groups.setdefault(
            (font_name, subtype, effective_size, horizontal_size),
            {
                "font_name": font_name,
                "subtype": subtype,
                "effective_size_pt": effective_size,
                "horizontal_size_pt": horizontal_size,
                "occurrences": 0,
                "pages": set(),
                "resource_paths": set(),
            },
        )
        occurrences = item.get("occurrences")
        group["occurrences"] += occurrences if isinstance(occurrences, int) else 1
        page = item.get("page")
        if isinstance(page, int):
            group["pages"].add(page)
        resource_path = item.get("resource_path")
        if isinstance(resource_path, str) and resource_path:
            group["resource_paths"].add(resource_path)

    findings = []
    for group in groups.values():
        observed = {
            "font_name": group["font_name"],
            "subtype": group["subtype"],
            "effective_size_pt": group["effective_size_pt"],
            "horizontal_size_pt": group["horizontal_size_pt"],
            "occurrences": group["occurrences"],
            "pages": sorted(group["pages"]),
        }
        if group["resource_paths"]:
            observed["resource_paths"] = sorted(group["resource_paths"])
        findings.append(
            Finding(
                check_id=MINIMUM_TEXT_SIZE_CHECK,
                category="fonts",
                severity=severity,
                message=f"Text effective size is below {min_pt:g} pt.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                observed=observed,
                threshold={"min_pt": min_pt},
            )
        )

    findings.sort(
        key=lambda finding: (
            finding.observed["effective_size_pt"],
            finding.observed["font_name"],
            finding.observed["subtype"],
        )
    )
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
        resource_ref = _resource_ref(item)
        findings.append(
            Finding(
                check_id=LOW_EFFECTIVE_RESOLUTION_CHECK,
                category="images",
                severity=severity,
                message=f"Image effective resolution is below {min_dpi_threshold:g} DPI.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=resource_ref,
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


def _jpeg_compression_policy_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        filters = _string_list(item.get("filters"))
        if "DCTDecode" not in filters:
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=JPEG_COMPRESSION_POLICY_CHECK,
                category="images",
                severity=severity,
                message="Image uses JPEG/DCT compression.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=_resource_ref(item),
                observed=_image_metadata_observed(item) | {"filters": filters},
                threshold={"filter": "DCTDecode"},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.object_ref or ""))
    return findings


def _image_filter_policy_findings(evidence: list[dict[str, Any]], params: dict[str, Any]) -> list[Finding]:
    severity_by_filter = params.get("severity_by_filter")
    if not isinstance(severity_by_filter, dict):
        raise ValueError(f"check '{IMAGE_FILTER_POLICY_CHECK}' requires mapping parameter 'severity_by_filter'")

    findings = []
    for item in evidence:
        filters = _string_list(item.get("filters"))
        for filter_name in filters:
            severity_raw = severity_by_filter.get(filter_name, severity_by_filter.get("Other"))
            if severity_raw is None:
                continue
            if not isinstance(severity_raw, str):
                raise ValueError(
                    f"check '{IMAGE_FILTER_POLICY_CHECK}' severity for filter '{filter_name}' must be null or a string"
                )
            severity = Severity.parse(severity_raw)
            page = item.get("page")
            findings.append(
                Finding(
                    check_id=IMAGE_FILTER_POLICY_CHECK,
                    category="images",
                    severity=severity,
                    message=f"Image uses filter {filter_name}.",
                    analyzer="pdfbox",
                    source_tool="pdfbox",
                    page=page if isinstance(page, int) else None,
                    object_ref=_resource_ref(item),
                    observed=_image_metadata_observed(item) | {"filters": filters, "matched_filter": filter_name},
                    threshold={"severity_by_filter": {filter_name: severity.name}},
                )
            )

    findings.sort(key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["matched_filter"]))
    return findings


def _image_soft_mask_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        if item.get("has_soft_mask") is not True:
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=IMAGE_SOFT_MASK_CHECK,
                category="images",
                severity=severity,
                message="Image uses a soft mask.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=_resource_ref(item),
                observed=_image_metadata_observed(item) | {"has_soft_mask": True},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.object_ref or ""))
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
        resource_ref = _resource_ref(item)
        findings.append(
            Finding(
                check_id=IMAGE_COLOR_SPACE_POLICY_CHECK,
                category="color",
                severity=severity,
                message=f"Image uses color space family {family}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=resource_ref,
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


def _live_transparency_policy_findings(evidence: list[dict[str, Any]], params: dict[str, Any]) -> list[Finding]:
    severity_by_feature = params.get("severity_by_feature")
    if not isinstance(severity_by_feature, dict):
        raise ValueError(
            f"check '{LIVE_TRANSPARENCY_POLICY_CHECK}' requires mapping parameter 'severity_by_feature'"
        )

    findings = []
    for item in evidence:
        features = item.get("features")
        if not isinstance(features, list):
            continue

        configured_features: list[str] = []
        configured_severities: dict[str, Severity] = {}
        for feature in features:
            if not isinstance(feature, str):
                continue
            severity_raw = severity_by_feature.get(feature)
            if severity_raw is None:
                continue
            if not isinstance(severity_raw, str):
                raise ValueError(
                    f"check '{LIVE_TRANSPARENCY_POLICY_CHECK}' severity for feature '{feature}' "
                    "must be null or a string"
                )
            configured_features.append(feature)
            configured_severities[feature] = Severity.parse(severity_raw)

        if not configured_features:
            continue

        severity = max(configured_severities.values())
        page = item.get("page")
        resource_name = item.get("resource_name")
        resource_ref = _resource_ref(item)
        observed = {
            "features": configured_features,
            "resource_name": resource_name,
        }
        for feature in configured_features:
            if feature in item:
                observed[feature] = item.get(feature)

        findings.append(
            Finding(
                check_id=LIVE_TRANSPARENCY_POLICY_CHECK,
                category="transparency",
                severity=severity,
                message=f"PDF uses live transparency features: {', '.join(configured_features)}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=resource_ref,
                observed=observed,
                threshold={
                    "severity_by_feature": {
                        feature: configured_severities[feature].name for feature in configured_features
                    }
                },
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["features"]))
    return findings


def _object_bounds_within_box_findings(
    pdf_path: Path,
    evidence: list[dict[str, Any]],
    severity: Severity,
    params: dict[str, Any],
) -> list[Finding]:
    box_name = str(params.get("box", "BleedBox"))
    pdf_box_key = BOX_KEYS.get(box_name)
    if pdf_box_key is None:
        raise ValueError(f"check '{OBJECT_BOUNDS_WITHIN_BOX_CHECK}' has unsupported box '{box_name}'")
    tolerance = float(params.get("tolerance_pt", 0))

    page_boxes = _read_page_boxes(pdf_path, pdf_box_key)
    findings = []
    for item in evidence:
        page = item.get("page")
        if not isinstance(page, int):
            continue
        box_bounds = page_boxes.get(page)
        if box_bounds is None:
            continue
        object_bounds = _bounds_or_none(item.get("bounds_pt"))
        if object_bounds is None:
            continue

        outside = _outside_amounts(object_bounds, box_bounds, tolerance)
        if not outside:
            continue

        findings.append(
            Finding(
                check_id=OBJECT_BOUNDS_WITHIN_BOX_CHECK,
                category="geometry",
                severity=severity,
                message=f"Placed object extends outside {box_name}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page,
                object_ref=_resource_ref(item),
                observed={
                    "object_type": item.get("object_type"),
                    "bounds_pt": object_bounds,
                    "box": box_name,
                    "box_bounds_pt": box_bounds,
                    "outside": outside,
                },
                threshold={"box": box_name, "tolerance_pt": tolerance},
            )
        )

    findings.sort(
        key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["object_type"] or "")
    )
    return findings


def _safe_area_margin_findings(
    pdf_path: Path,
    evidence: list[dict[str, Any]],
    severity: Severity,
    params: dict[str, Any],
) -> list[Finding]:
    box_name = str(params.get("box", "TrimBox"))
    pdf_box_key = BOX_KEYS.get(box_name)
    if pdf_box_key is None:
        raise ValueError(f"check '{SAFE_AREA_MARGIN_CHECK}' has unsupported box '{box_name}'")

    tolerance = float(params.get("tolerance_pt", 0))
    margins = _safe_area_margins(params)
    include_object_types = set(_string_list(params.get("include_object_types")) or ["text", "image", "form"])
    ignore_crossing_trim = params.get("ignore_objects_crossing_trim", True) is not False
    page_boxes = _read_page_boxes(pdf_path, pdf_box_key)

    findings = []
    for item in evidence:
        object_type = item.get("object_type")
        if not isinstance(object_type, str) or object_type not in include_object_types:
            continue
        page = item.get("page")
        if not isinstance(page, int):
            continue
        box_bounds = page_boxes.get(page)
        if box_bounds is None:
            continue
        bounds = _bounds_or_none(item.get("bounds_pt"))
        if bounds is None:
            continue
        if object_type != "text" and ignore_crossing_trim and _outside_amounts(bounds, box_bounds, tolerance):
            continue

        violations = _safe_area_violations(bounds, box_bounds, margins, tolerance)
        if not violations:
            continue

        observed = {
            "object_type": object_type,
            "bounds_pt": bounds,
            "box": box_name,
            "box_bounds_pt": box_bounds,
            "violations": violations,
        }
        if object_type == "text":
            observed.update(
                {
                    "font_name": item.get("font_name"),
                    "subtype": item.get("subtype"),
                    "effective_size_pt": item.get("effective_size_pt"),
                }
            )

        findings.append(
            Finding(
                check_id=SAFE_AREA_MARGIN_CHECK,
                category="geometry",
                severity=severity,
                message=f"Content is inside the configured safe-area margin from {box_name}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page,
                object_ref=_resource_ref(item),
                observed=observed,
                threshold={
                    "box": box_name,
                    "margins_pt": margins,
                    "include_object_types": sorted(include_object_types),
                    "ignore_objects_crossing_trim": ignore_crossing_trim,
                    "tolerance_pt": tolerance,
                },
            )
        )

    findings.sort(
        key=lambda finding: (
            finding.page or 0,
            finding.object_ref or "",
            finding.observed["object_type"],
            sorted(finding.observed["violations"]),
        )
    )
    return findings


def _registration_color_misuse_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        colorants = _string_list(item.get("colorants"))
        if "All" not in colorants:
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=REGISTRATION_COLOR_MISUSE_CHECK,
                category="color",
                severity=severity,
                message="Registration color is used in painted content.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=_resource_ref(item),
                observed={
                    "paint_operation": item.get("paint_operation"),
                    "paint_role": item.get("paint_role"),
                    "color_space_name": item.get("color_space_name"),
                    "color_space_family": item.get("color_space_family"),
                    "colorants": colorants,
                    "occurrences": _occurrences(item),
                },
            )
        )

    findings.sort(
        key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["paint_operation"] or "")
    )
    return findings


def _spot_color_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    allowed = set(_string_list(params.get("allowed_colorants")))
    ignored = set(_string_list(params.get("ignored_colorants")))
    findings = []
    for item in evidence:
        colorants = _string_list(item.get("colorants"))
        disallowed = sorted(colorant for colorant in colorants if colorant not in allowed and colorant not in ignored)
        if not disallowed:
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=SPOT_COLOR_POLICY_CHECK,
                category="color",
                severity=severity,
                message="Special colorants are not allowed by the target.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=_resource_ref(item),
                observed={
                    "paint_operation": item.get("paint_operation"),
                    "paint_role": item.get("paint_role"),
                    "color_space_name": item.get("color_space_name"),
                    "color_space_family": item.get("color_space_family"),
                    "colorants": colorants,
                    "disallowed_colorants": disallowed,
                    "occurrences": _occurrences(item),
                },
                threshold={
                    "allowed_colorants": sorted(allowed),
                    "ignored_colorants": sorted(ignored),
                },
            )
        )

    findings.sort(
        key=lambda finding: (
            finding.page or 0,
            finding.object_ref or "",
            finding.observed["paint_operation"] or "",
            finding.observed["disallowed_colorants"],
        )
    )
    return findings


def _overprint_policy_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        page = item.get("page")
        findings.append(
            Finding(
                check_id=OVERPRINT_POLICY_CHECK,
                category="graphics",
                severity=severity,
                message="Painted content uses overprint.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                object_ref=_resource_ref(item),
                observed={
                    "paint_operation": item.get("paint_operation"),
                    "paint_role": item.get("paint_role"),
                    "overprint_mode": item.get("overprint_mode"),
                    "occurrences": _occurrences(item),
                },
            )
        )

    findings.sort(
        key=lambda finding: (finding.page or 0, finding.object_ref or "", finding.observed["paint_operation"] or "")
    )
    return findings


def _annotation_policy_findings(evidence: list[dict[str, Any]], params: dict[str, Any]) -> list[Finding]:
    severity_by_subtype = params.get("severity_by_subtype")
    if not isinstance(severity_by_subtype, dict):
        raise ValueError(f"check '{ANNOTATION_POLICY_CHECK}' requires mapping parameter 'severity_by_subtype'")

    findings = []
    for item in evidence:
        subtype = item.get("subtype")
        if not isinstance(subtype, str):
            continue
        severity_raw = severity_by_subtype.get(subtype, severity_by_subtype.get("Other"))
        if severity_raw is None:
            continue
        if not isinstance(severity_raw, str):
            raise ValueError(
                f"check '{ANNOTATION_POLICY_CHECK}' severity for subtype '{subtype}' must be null or a string"
            )
        severity = Severity.parse(severity_raw)
        page = item.get("page")
        findings.append(
            Finding(
                check_id=ANNOTATION_POLICY_CHECK,
                category="interactive",
                severity=severity,
                message=f"PDF contains annotation subtype {subtype}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                observed=_annotation_observed(item),
                threshold={"severity_by_subtype": {subtype: severity.name}},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.observed["subtype"]))
    return findings


def _link_uri_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    allowed_schemes = {scheme.lower() for scheme in _string_list(params.get("allowed_schemes"))}
    disallow_all = params.get("disallow_all") is True
    findings = []
    for item in evidence:
        if item.get("subtype") != "Link":
            continue
        uri = item.get("uri")
        if not isinstance(uri, str):
            continue
        scheme = urlsplit(uri).scheme.lower()
        if not disallow_all and scheme in allowed_schemes:
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=LINK_URI_POLICY_CHECK,
                category="interactive",
                severity=severity,
                message="Link annotation URI is not allowed by the target.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                observed=_annotation_observed(item) | {"uri": uri, "uri_scheme": scheme},
                threshold={"allowed_schemes": sorted(allowed_schemes), "disallow_all": disallow_all},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.observed["uri_scheme"], finding.observed["uri"]))
    return findings


def _annotation_bounds_findings(
    pdf_path: Path,
    evidence: list[dict[str, Any]],
    severity: Severity,
    params: dict[str, Any],
) -> list[Finding]:
    box_name = str(params.get("box", "CropBox"))
    pdf_box_key = BOX_KEYS.get(box_name)
    if pdf_box_key is None:
        raise ValueError(f"check '{ANNOTATION_BOUNDS_CHECK}' has unsupported box '{box_name}'")
    tolerance = float(params.get("tolerance_pt", 0))

    page_boxes = _read_page_boxes(pdf_path, pdf_box_key)
    findings = []
    for item in evidence:
        page = item.get("page")
        if not isinstance(page, int):
            continue
        box_bounds = page_boxes.get(page)
        if box_bounds is None:
            continue
        annotation_bounds = _bounds_or_none(item.get("rectangle"))
        if annotation_bounds is None:
            continue
        outside = _outside_amounts(annotation_bounds, box_bounds, tolerance)
        if not outside:
            continue

        findings.append(
            Finding(
                check_id=ANNOTATION_BOUNDS_CHECK,
                category="interactive",
                severity=severity,
                message=f"Annotation extends outside {box_name}.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page,
                observed=_annotation_observed(item)
                | {
                    "box": box_name,
                    "box_bounds_pt": box_bounds,
                    "outside": outside,
                },
                threshold={"box": box_name, "tolerance_pt": tolerance},
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, finding.observed["subtype"]))
    return findings


def _javascript_policy_findings(
    annotations: list[dict[str, Any]],
    document_actions: list[dict[str, Any]],
    severity: Severity,
) -> list[Finding]:
    findings = []
    for item in [*annotations, *document_actions]:
        if item.get("has_javascript") is not True and item.get("action_subtype") != "JavaScript":
            continue
        page = item.get("page")
        findings.append(
            Finding(
                check_id=JAVASCRIPT_POLICY_CHECK,
                category="interactive",
                severity=severity,
                message="PDF contains JavaScript action.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                page=page if isinstance(page, int) else None,
                observed={
                    "scope": item.get("scope", "page"),
                    "location": item.get("location"),
                    "subtype": item.get("subtype"),
                    "action_subtype": item.get("action_subtype"),
                    "has_javascript": True,
                },
            )
        )

    findings.sort(key=lambda finding: (finding.page or 0, str(finding.observed["location"])))
    return findings


def _embedded_files_policy_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        count = item.get("count")
        if not isinstance(count, int) or count <= 0:
            continue
        findings.append(
            Finding(
                check_id=EMBEDDED_FILES_POLICY_CHECK,
                category="interactive",
                severity=severity,
                message="PDF contains embedded files.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                observed={"count": count, "names": _string_list(item.get("names"))},
            )
        )

    return findings


def _form_policy_findings(evidence: list[dict[str, Any]], severity: Severity) -> list[Finding]:
    findings = []
    for item in evidence:
        findings.append(
            Finding(
                check_id=FORM_POLICY_CHECK,
                category="interactive",
                severity=severity,
                message="PDF contains interactive form structures.",
                analyzer="pdfbox",
                source_tool="pdfbox",
                observed={
                    "field_count": item.get("field_count"),
                    "has_xfa": item.get("has_xfa"),
                    "signatures_exist": item.get("signatures_exist"),
                    "append_only": item.get("append_only"),
                },
            )
        )

    return findings


def _blank_page_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    blank_pages = sorted(
        item["page"]
        for item in evidence
        if item.get("is_structurally_blank") is True and isinstance(item.get("page"), int)
    )
    if not blank_pages:
        return []

    allowed_pages = set(_int_list(params.get("allowed_pages")))
    effective_blank_pages = [page for page in blank_pages if page not in allowed_pages]

    if params.get("allow_trailing_blank") is True and effective_blank_pages:
        last_page = max(item["page"] for item in evidence if isinstance(item.get("page"), int))
        if effective_blank_pages[-1] == last_page:
            effective_blank_pages = effective_blank_pages[:-1]

    max_blank_pages = params.get("max_blank_pages")
    if isinstance(max_blank_pages, int) and len(effective_blank_pages) <= max_blank_pages:
        return []
    if not effective_blank_pages:
        return []

    observed = {
        "blank_pages": effective_blank_pages,
        "blank_page_count": len(effective_blank_pages),
        "all_blank_pages": blank_pages,
    }
    return [
        Finding(
            check_id=BLANK_PAGE_POLICY_CHECK,
            category="pages",
            severity=severity,
            message="PDF contains blank pages not allowed by the target policy.",
            analyzer="pdfbox",
            source_tool="pdfbox",
            observed=observed,
            threshold={
                "allowed_pages": sorted(allowed_pages),
                "allow_trailing_blank": params.get("allow_trailing_blank") is True,
                "max_blank_pages": max_blank_pages,
            },
        )
    ]


def _pdf_version_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    if not evidence:
        return []
    item = evidence[0]
    effective_version = item.get("effective_version")
    if not isinstance(effective_version, str):
        return []

    violations = {}
    allowed_versions = _string_list(params.get("allowed_versions"))
    if allowed_versions and effective_version not in allowed_versions:
        violations["allowed_versions"] = allowed_versions

    min_version = params.get("min_version")
    if isinstance(min_version, str) and _version_tuple(effective_version) < _version_tuple(min_version):
        violations["min_version"] = min_version

    max_version = params.get("max_version")
    if isinstance(max_version, str) and _version_tuple(effective_version) > _version_tuple(max_version):
        violations["max_version"] = max_version

    if not violations:
        return []

    return [
        Finding(
            check_id=PDF_VERSION_POLICY_CHECK,
            category="document_metadata",
            severity=severity,
            message="PDF version does not match target policy.",
            analyzer="pdfbox",
            source_tool="pdfbox",
            observed={
                "document_version": item.get("document_version"),
                "catalog_version": item.get("catalog_version"),
                "effective_version": effective_version,
                "violations": violations,
            },
            threshold={
                key: value
                for key, value in {
                    "allowed_versions": allowed_versions,
                    "min_version": min_version,
                    "max_version": max_version,
                }.items()
                if value
            },
        )
    ]


def _pdfa_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    item = evidence[0] if evidence else {}
    pdfa_part = item.get("pdfa_part")
    pdfa_conformance = item.get("pdfa_conformance")
    require_pdfa = params.get("require_pdfa") is True
    allowed_parts = _int_list(params.get("allowed_parts"))
    allowed_conformance = _string_list(params.get("allowed_conformance"))

    violations = {}
    if require_pdfa and pdfa_part is None:
        violations["require_pdfa"] = True
    if allowed_parts and pdfa_part is not None and pdfa_part not in allowed_parts:
        violations["allowed_parts"] = allowed_parts
    if allowed_conformance and isinstance(pdfa_conformance, str) and pdfa_conformance not in allowed_conformance:
        violations["allowed_conformance"] = allowed_conformance

    if not violations:
        return []

    return [
        Finding(
            check_id=PDFA_POLICY_CHECK,
            category="document_metadata",
            severity=severity,
            message="PDF/A identification does not match target policy.",
            analyzer="pdfbox",
            source_tool="pdfbox",
            observed={
                "has_xmp": item.get("has_xmp"),
                "xmp_parseable": item.get("xmp_parseable"),
                "pdfa_part": pdfa_part,
                "pdfa_conformance": pdfa_conformance,
                "violations": violations,
            },
            threshold={
                "require_pdfa": require_pdfa,
                "allowed_parts": allowed_parts,
                "allowed_conformance": allowed_conformance,
            },
        )
    ]


def _pdfx_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    item = evidence[0] if evidence else {}
    pdfx_version = item.get("pdfx_version")
    pdfx_conformance = item.get("pdfx_conformance")
    require_pdfx = params.get("require_pdfx") is True
    allowed_versions = _string_list(params.get("allowed_versions"))

    violations = {}
    if require_pdfx and pdfx_version is None:
        violations["require_pdfx"] = True
    if allowed_versions and isinstance(pdfx_version, str) and pdfx_version not in allowed_versions:
        violations["allowed_versions"] = allowed_versions

    if not violations:
        return []

    return [
        Finding(
            check_id=PDFX_POLICY_CHECK,
            category="document_metadata",
            severity=severity,
            message="PDF/X identification does not match target policy.",
            analyzer="pdfbox",
            source_tool="pdfbox",
            observed={
                "has_xmp": item.get("has_xmp"),
                "xmp_parseable": item.get("xmp_parseable"),
                "pdfx_version": pdfx_version,
                "pdfx_conformance": pdfx_conformance,
                "violations": violations,
            },
            threshold={"require_pdfx": require_pdfx, "allowed_versions": allowed_versions},
        )
    ]


def _producer_policy_findings(
    evidence: list[dict[str, Any]], severity: Severity, params: dict[str, Any]
) -> list[Finding]:
    if not evidence:
        return []

    item = evidence[0]
    disallowed = _string_list(params.get("disallowed_contains"))
    warn = _string_list(params.get("warn_contains"))
    findings = []
    for field in ("producer", "creator"):
        value = item.get(field)
        if not isinstance(value, str):
            continue
        for match_type, needles in (("disallowed_contains", disallowed), ("warn_contains", warn)):
            for needle in needles:
                if needle.lower() not in value.lower():
                    continue
                findings.append(
                    Finding(
                        check_id=PRODUCER_POLICY_CHECK,
                        category="document_metadata",
                        severity=severity,
                        message=f"Document {field} matches target producer policy.",
                        analyzer="pdfbox",
                        source_tool="pdfbox",
                        observed={
                            "field": field,
                            "value": value,
                            "matched": needle,
                            "match_type": match_type,
                        },
                        threshold={
                            "disallowed_contains": disallowed,
                            "warn_contains": warn,
                        },
                    )
                )

    findings.sort(key=lambda finding: (finding.observed["field"], finding.observed["matched"]))
    return findings


def _read_page_boxes(pdf_path: Path, pdf_box_key: str) -> dict[int, dict[str, float]]:
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            return {}
    except Exception:
        return {}

    page_boxes = {}
    for page_index, page in enumerate(reader.pages, start=1):
        box = page.get(pdf_box_key)
        if box is None:
            continue
        page_boxes[page_index] = {
            "left": float(box[0]),
            "bottom": float(box[1]),
            "right": float(box[2]),
            "top": float(box[3]),
        }
    return page_boxes


def _bounds_or_none(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    bounds = {}
    for key in ("left", "bottom", "right", "top"):
        number = _number_or_none(value.get(key))
        if number is None:
            return None
        bounds[key] = number
    return bounds


def _outside_amounts(
    object_bounds: dict[str, float],
    box_bounds: dict[str, float],
    tolerance: float,
) -> dict[str, float]:
    outside = {}
    left = box_bounds["left"] - object_bounds["left"]
    bottom = box_bounds["bottom"] - object_bounds["bottom"]
    right = object_bounds["right"] - box_bounds["right"]
    top = object_bounds["top"] - box_bounds["top"]
    if left > tolerance:
        outside["left_pt"] = left
    if bottom > tolerance:
        outside["bottom_pt"] = bottom
    if right > tolerance:
        outside["right_pt"] = right
    if top > tolerance:
        outside["top_pt"] = top
    return outside


def _safe_area_margins(params: dict[str, Any]) -> dict[str, float]:
    raw_margins = params.get("margins_pt")
    if isinstance(raw_margins, dict):
        return {
            "left": _number_or_default(raw_margins.get("left"), 18.0),
            "right": _number_or_default(raw_margins.get("right"), 18.0),
            "top": _number_or_default(raw_margins.get("top"), 18.0),
            "bottom": _number_or_default(raw_margins.get("bottom"), 18.0),
        }
    margin = _number_or_default(params.get("margin_pt"), 18.0)
    return {"left": margin, "right": margin, "top": margin, "bottom": margin}


def _safe_area_violations(
    object_bounds: dict[str, float],
    box_bounds: dict[str, float],
    margins: dict[str, float],
    tolerance: float,
) -> dict[str, float]:
    violations = {}
    left_distance = object_bounds["left"] - box_bounds["left"]
    bottom_distance = object_bounds["bottom"] - box_bounds["bottom"]
    right_distance = box_bounds["right"] - object_bounds["right"]
    top_distance = box_bounds["top"] - object_bounds["top"]
    if margins["left"] - left_distance > tolerance:
        violations["left_pt"] = margins["left"] - left_distance
    if margins["bottom"] - bottom_distance > tolerance:
        violations["bottom_pt"] = margins["bottom"] - bottom_distance
    if margins["right"] - right_distance > tolerance:
        violations["right_pt"] = margins["right"] - right_distance
    if margins["top"] - top_distance > tolerance:
        violations["top_pt"] = margins["top"] - top_distance
    return violations


def _required_number(params: dict[str, Any], name: str, check_id: str) -> float:
    value = params.get(name)
    if not isinstance(value, int | float):
        raise ValueError(f"check '{check_id}' requires numeric parameter '{name}'")
    return float(value)


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _number_or_default(value: Any, default: float) -> float:
    number = _number_or_none(value)
    return default if number is None else number


def _image_metadata_observed(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_name": item.get("resource_name"),
        "pixel_width": item.get("pixel_width"),
        "pixel_height": item.get("pixel_height"),
        "bits_per_component": item.get("bits_per_component"),
        "color_space_name": item.get("color_space_name"),
        "color_space_family": item.get("color_space_family"),
    }


def _annotation_observed(item: dict[str, Any]) -> dict[str, Any]:
    observed = {
        "subtype": item.get("subtype"),
        "rectangle": item.get("rectangle"),
        "flags": item.get("flags"),
        "printed": item.get("printed"),
        "hidden": item.get("hidden"),
        "no_view": item.get("no_view"),
    }
    action_subtype = item.get("action_subtype")
    if action_subtype is not None:
        observed["action_subtype"] = action_subtype
    return observed


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _occurrences(item: dict[str, Any]) -> int:
    occurrences = item.get("occurrences")
    return occurrences if isinstance(occurrences, int) else 1


def _resource_ref(item: dict[str, Any]) -> str | None:
    resource_path = item.get("resource_path")
    if isinstance(resource_path, str):
        return resource_path
    resource_name = item.get("resource_name")
    if resource_name is not None:
        return str(resource_name)
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
