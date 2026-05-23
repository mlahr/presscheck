from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import NameObject, RectangleObject

from presscheck.analyzers.geometry import analyze
from presscheck.models import CheckConfig, Severity, TargetConfig


def _target() -> TargetConfig:
    return TargetConfig(
        fail_at=Severity.error,
        checks={
            "geometry.page_boxes_present": CheckConfig(
                check_id="geometry.page_boxes_present",
                enabled=True,
                severity=Severity.error,
                params={"required_boxes": ["MediaBox", "TrimBox", "BleedBox"]},
            ),
            "geometry.trim_size_matches": CheckConfig(
                check_id="geometry.trim_size_matches",
                enabled=True,
                severity=Severity.error,
                params={"expected_width_pt": 612, "expected_height_pt": 792, "tolerance_pt": 0.5},
            ),
            "geometry.bleed_margin_at_least": CheckConfig(
                check_id="geometry.bleed_margin_at_least",
                enabled=True,
                severity=Severity.error,
                params={"margin_pt": 9, "tolerance_pt": 0.5},
            ),
            "pages.count_policy": CheckConfig(
                check_id="pages.count_policy",
                enabled=True,
                severity=Severity.error,
                params={"min_count": 1},
            ),
        },
    )


def _write_pdf(path: Path, *, trim_box=(9, 9, 621, 801), bleed_box=(0, 0, 630, 810)) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/TrimBox")] = RectangleObject(trim_box)
    page[NameObject("/BleedBox")] = RectangleObject(bleed_box)
    with path.open("wb") as file:
        writer.write(file)


def test_geometry_accepts_expected_boxes_and_trim(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _write_pdf(pdf)

    findings = analyze(pdf, _target())

    assert findings == []


def test_geometry_reports_missing_boxes(tmp_path: Path) -> None:
    pdf = tmp_path / "missing.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf.open("wb") as file:
        writer.write(file)

    findings = analyze(pdf, _target())

    assert {finding.observed["missing_box"] for finding in findings} == {"TrimBox", "BleedBox"}


def test_geometry_reports_trim_size_mismatch(tmp_path: Path) -> None:
    pdf = tmp_path / "wrong-size.pdf"
    _write_pdf(pdf, trim_box=(9, 9, 609, 801))

    findings = analyze(pdf, _target())

    assert any(finding.check_id == "geometry.trim_size_matches" for finding in findings)
    assert findings[0].page == 1


def test_geometry_reports_insufficient_bleed_margin(tmp_path: Path) -> None:
    pdf = tmp_path / "insufficient-bleed.pdf"
    _write_pdf(pdf, bleed_box=(3, 0, 630, 805))

    findings = analyze(pdf, _target())

    finding = next(finding for finding in findings if finding.check_id == "geometry.bleed_margin_at_least")
    assert finding.page == 1
    assert finding.observed == {
        "margins": {"left_pt": 6.0, "bottom_pt": 9.0, "right_pt": 9.0, "top_pt": 4.0},
        "too_small": {"left_pt": 6.0, "top_pt": 4.0},
    }
    assert finding.threshold == {"margin_pt": 9.0, "tolerance_pt": 0.5}


def test_geometry_skips_bleed_margin_when_required_boxes_are_missing(tmp_path: Path) -> None:
    pdf = tmp_path / "missing-bleed-box.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/TrimBox")] = RectangleObject((0, 0, 612, 792))
    with pdf.open("wb") as file:
        writer.write(file)

    findings = analyze(pdf, _target())

    assert any(finding.observed.get("missing_box") == "BleedBox" for finding in findings)
    assert not any(finding.check_id == "geometry.bleed_margin_at_least" for finding in findings)


def test_geometry_reports_invalid_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "invalid.pdf"
    pdf.write_text("not a pdf", encoding="utf-8")

    findings = analyze(pdf, _target())

    assert findings[0].check_id == "document_integrity.pdf_parseable"


def test_geometry_reports_page_count_policy_violation(tmp_path: Path) -> None:
    pdf = tmp_path / "count.pdf"
    _write_pdf(pdf)
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "pages.count_policy": CheckConfig(
                check_id="pages.count_policy",
                enabled=True,
                severity=Severity.error,
                params={"expected_count": 2, "min_count": 2, "max_count": 2},
            )
        },
    )

    findings = analyze(pdf, target)

    assert len(findings) == 1
    assert findings[0].check_id == "pages.count_policy"
    assert findings[0].observed == {
        "page_count": 1,
        "violations": {"expected_count": 2, "min_count": 2},
    }


def test_geometry_reports_page_parity_violation(tmp_path: Path) -> None:
    pdf = tmp_path / "parity.pdf"
    _write_pdf(pdf)
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "pages.parity_policy": CheckConfig(
                check_id="pages.parity_policy",
                enabled=True,
                severity=Severity.warning,
                params={"required_parity": "even"},
            )
        },
    )

    findings = analyze(pdf, target)

    assert len(findings) == 1
    assert findings[0].check_id == "pages.parity_policy"
    assert findings[0].observed == {"page_count": 1, "parity": "odd"}


def test_geometry_reports_mixed_page_sizes(tmp_path: Path) -> None:
    pdf = tmp_path / "mixed-size.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=120, height=100)
    with pdf.open("wb") as file:
        writer.write(file)
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "pages.size_consistency": CheckConfig(
                check_id="pages.size_consistency",
                enabled=True,
                severity=Severity.warning,
                params={"box": "MediaBox", "tolerance_pt": 0.5},
            )
        },
    )

    findings = analyze(pdf, target)

    assert len(findings) == 1
    assert findings[0].check_id == "pages.size_consistency"
    assert findings[0].observed == {
        "box": "MediaBox",
        "size_groups": [
            {"width_pt": 100.0, "height_pt": 100.0, "pages": [1]},
            {"width_pt": 120.0, "height_pt": 100.0, "pages": [2]},
        ],
    }
