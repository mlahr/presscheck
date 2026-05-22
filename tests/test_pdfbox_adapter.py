from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter
from pypdf.generic import NameObject, RectangleObject

from pdfdancer_preflight.analyzers import pdfbox
from pdfdancer_preflight.models import CheckConfig, Severity, TargetConfig


def _target() -> TargetConfig:
    return TargetConfig(
        fail_at=Severity.error,
        checks={
            "fonts.non_embedded": CheckConfig(
                check_id="fonts.non_embedded",
                enabled=True,
                severity=Severity.warning,
                params={},
            ),
            "fonts.minimum_text_size": CheckConfig(
                check_id="fonts.minimum_text_size",
                enabled=True,
                severity=Severity.warning,
                params={"min_pt": 6},
            ),
            "images.low_effective_resolution": CheckConfig(
                check_id="images.low_effective_resolution",
                enabled=True,
                severity=Severity.error,
                params={"min_dpi": 300},
            ),
            "images.jpeg_compression_policy": CheckConfig(
                check_id="images.jpeg_compression_policy",
                enabled=True,
                severity=Severity.warning,
                params={},
            ),
            "images.image_filter_policy": CheckConfig(
                check_id="images.image_filter_policy",
                enabled=True,
                severity=Severity.warning,
                params={
                    "severity_by_filter": {
                        "DCTDecode": None,
                        "FlateDecode": None,
                        "JPXDecode": "warning",
                        "JBIG2Decode": "error",
                        "Other": "warning",
                    }
                },
            ),
            "images.has_soft_mask": CheckConfig(
                check_id="images.has_soft_mask",
                enabled=True,
                severity=Severity.warning,
                params={},
            ),
            "color.image_color_space_policy": CheckConfig(
                check_id="color.image_color_space_policy",
                enabled=True,
                severity=Severity.warning,
                params={"severity_by_family": {"DeviceRGB": "error", "DeviceCMYK": None}},
            ),
            "color.output_intent_required": CheckConfig(
                check_id="color.output_intent_required",
                enabled=True,
                severity=Severity.error,
                params={},
            ),
            "color.registration_color_misuse": CheckConfig(
                check_id="color.registration_color_misuse",
                enabled=True,
                severity=Severity.error,
                params={},
            ),
            "color.spot_color_policy": CheckConfig(
                check_id="color.spot_color_policy",
                enabled=True,
                severity=Severity.warning,
                params={"allowed_colorants": [], "ignored_colorants": ["All", "None"]},
            ),
            "graphics.overprint_policy": CheckConfig(
                check_id="graphics.overprint_policy",
                enabled=True,
                severity=Severity.warning,
                params={},
            ),
            "transparency.live_transparency_policy": CheckConfig(
                check_id="transparency.live_transparency_policy",
                enabled=True,
                severity=Severity.warning,
                params={
                    "severity_by_feature": {
                        "stroking_alpha": "warning",
                        "non_stroking_alpha": "warning",
                        "soft_mask": "error",
                        "blend_mode": "warning",
                        "transparency_group": "warning",
                    }
                },
            ),
            "geometry.object_bounds_within_box": CheckConfig(
                check_id="geometry.object_bounds_within_box",
                enabled=True,
                severity=Severity.warning,
                params={"box": "BleedBox", "tolerance_pt": 0.5},
            ),
        },
    )


def _write_pdf_with_bleed_box(path: Path, bleed_box=(0, 0, 100, 100)) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    page[NameObject("/BleedBox")] = RectangleObject(bleed_box)
    with path.open("wb") as file:
        writer.write(file)


def test_pdfbox_adapter_groups_non_embedded_font_evidence(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.output_intents",
      "category": "color",
      "scope": "document",
      "count": 1,
      "output_intents": [
        {
          "subtype": "OutputIntent",
          "output_condition": "sRGB",
          "output_condition_identifier": "sRGB",
          "registry_name": "http://www.color.org",
          "info": "sRGB",
          "has_dest_output_profile": true
        }
      ]
    },
    {
      "check_id": "fonts.non_embedded",
      "category": "fonts",
      "page": 2,
      "resource_name": "F2",
      "font_name": "Helvetica",
      "subtype": "Type1",
      "embedded": false
    },
    {
      "check_id": "fonts.non_embedded",
      "category": "fonts",
      "page": 1,
      "resource_name": "F1",
      "font_name": "Helvetica",
      "subtype": "Type1",
      "embedded": false
    },
    {
      "check_id": "fonts.non_embedded",
      "category": "fonts",
      "page": 2,
      "resource_name": "F1",
      "font_name": "Helvetica",
      "subtype": "Type1",
      "embedded": false
    },
    {
      "check_id": "fonts.non_embedded",
      "category": "fonts",
      "page": 3,
      "resource_name": "F3",
      "font_name": "Helvetica",
      "subtype": "TrueType",
      "embedded": false
    }
  ]
}
""",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    findings = pdfbox.analyze(tmp_path / "input.pdf", _target())

    assert len(findings) == 2

    type1 = next(finding for finding in findings if finding.observed["subtype"] == "Type1")
    assert type1.check_id == "fonts.non_embedded"
    assert type1.severity == Severity.warning
    assert type1.page is None
    assert type1.object_ref is None
    assert type1.observed == {
        "font_name": "Helvetica",
        "subtype": "Type1",
        "embedded": False,
        "occurrences": 3,
        "resource_names": ["F1", "F2"],
        "pages": [1, 2],
    }

    true_type = next(finding for finding in findings if finding.observed["subtype"] == "TrueType")
    assert true_type.observed == {
        "font_name": "Helvetica",
        "subtype": "TrueType",
        "embedded": False,
        "occurrences": 1,
        "resource_names": ["F3"],
        "pages": [3],
    }


def test_pdfbox_adapter_fails_closed_when_jar_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(tmp_path / "missing.jar"))

    findings = pdfbox.analyze(tmp_path / "input.pdf", _target())

    assert len(findings) == 1
    assert findings[0].check_id == "document_integrity.pdfbox_analyzer_failed"
    assert findings[0].severity == Severity.error


def test_pdfbox_adapter_fails_closed_on_invalid_json(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="not json"))

    findings = pdfbox.analyze(tmp_path / "input.pdf", _target())

    assert findings[0].check_id == "document_integrity.pdfbox_analyzer_failed"


def test_pdfbox_adapter_maps_minimum_text_size_evidence(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 2},
  "evidence": [
    {
      "check_id": "fonts.text_size",
      "category": "fonts",
      "page": 1,
      "font_name": "Helvetica",
      "subtype": "Type1",
      "effective_size_pt": 4.5,
      "horizontal_size_pt": 4.5,
      "occurrences": 3
    },
    {
      "check_id": "fonts.text_size",
      "category": "fonts",
      "page": 2,
      "resource_path": "Form1",
      "font_name": "Helvetica",
      "subtype": "Type1",
      "effective_size_pt": 4.5,
      "horizontal_size_pt": 4.5,
      "occurrences": 5
    },
    {
      "check_id": "fonts.text_size",
      "category": "fonts",
      "page": 2,
      "font_name": "Helvetica",
      "subtype": "Type1",
      "effective_size_pt": 8.0,
      "horizontal_size_pt": 8.0,
      "occurrences": 2
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "fonts.minimum_text_size": CheckConfig(
                check_id="fonts.minimum_text_size",
                enabled=True,
                severity=Severity.warning,
                params={"min_pt": 6},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "fonts.minimum_text_size"
    assert findings[0].category == "fonts"
    assert findings[0].severity == Severity.warning
    assert findings[0].observed == {
        "font_name": "Helvetica",
        "subtype": "Type1",
        "effective_size_pt": 4.5,
        "horizontal_size_pt": 4.5,
        "occurrences": 8,
        "pages": [1, 2],
        "resource_paths": ["Form1"],
    }
    assert findings[0].threshold == {"min_pt": 6.0}


def test_pdfbox_adapter_allows_text_at_minimum_size(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "fonts.text_size",
      "category": "fonts",
      "page": 1,
      "font_name": "Helvetica",
      "subtype": "Type1",
      "effective_size_pt": 6.0,
      "horizontal_size_pt": 6.0,
      "occurrences": 3
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "fonts.minimum_text_size": CheckConfig(
                check_id="fonts.minimum_text_size",
                enabled=True,
                severity=Severity.warning,
                params={"min_pt": 6},
            )
        },
    )

    assert pdfbox.analyze(tmp_path / "input.pdf", target) == []


def test_pdfbox_adapter_rejects_missing_minimum_text_size_threshold(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "analyzer": "pdfbox", "metadata": {"page_count": 1}, "evidence": []}',
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "fonts.minimum_text_size": CheckConfig(
                check_id="fonts.minimum_text_size",
                enabled=True,
                severity=Severity.warning,
                params={},
            )
        },
    )

    try:
        pdfbox.analyze(tmp_path / "input.pdf", target)
    except ValueError as exc:
        assert "requires numeric parameter 'min_pt'" in str(exc)
    else:
        raise AssertionError("expected missing min_pt to raise ValueError")


def test_pdfbox_adapter_maps_low_resolution_image_evidence(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.output_intents",
      "category": "color",
      "scope": "document",
      "count": 1,
      "output_intents": []
    },
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im1",
      "resource_path": "Form1/Im1",
      "pixel_width": 300,
      "pixel_height": 300,
      "drawn_width_pt": 216.0,
      "drawn_height_pt": 216.0,
      "x_dpi": 100.0,
      "y_dpi": 100.0,
      "min_dpi": 100.0,
      "color_space_name": "DeviceRGB",
      "color_space_family": "DeviceRGB",
      "filters": ["DCTDecode"],
      "bits_per_component": 8,
      "interpolate": false,
      "image_mask": false,
      "has_soft_mask": true,
      "has_explicit_mask": false
    },
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im2",
      "pixel_width": 300,
      "pixel_height": 300,
      "drawn_width_pt": 72.0,
      "drawn_height_pt": 72.0,
      "x_dpi": 300.0,
      "y_dpi": 300.0,
      "min_dpi": 300.0,
      "color_space_name": "DeviceCMYK",
      "color_space_family": "DeviceCMYK",
      "filters": ["FlateDecode"],
      "bits_per_component": 8,
      "interpolate": false,
      "image_mask": false,
      "has_soft_mask": false,
      "has_explicit_mask": false
    }
  ]
}
""",
        ),
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", _target())

    image_findings = [finding for finding in findings if finding.check_id == "images.low_effective_resolution"]
    assert len(image_findings) == 1
    assert image_findings[0].severity == Severity.error
    assert image_findings[0].page == 1
    assert image_findings[0].object_ref == "Form1/Im1"
    assert image_findings[0].observed == {
        "pixel_width": 300,
        "pixel_height": 300,
        "drawn_width_pt": 216.0,
        "drawn_height_pt": 216.0,
        "x_dpi": 100.0,
        "y_dpi": 100.0,
        "min_dpi": 100.0,
    }
    assert image_findings[0].threshold == {"min_dpi": 300.0}

    jpeg_findings = [finding for finding in findings if finding.check_id == "images.jpeg_compression_policy"]
    assert len(jpeg_findings) == 1
    assert jpeg_findings[0].severity == Severity.warning
    assert jpeg_findings[0].page == 1
    assert jpeg_findings[0].object_ref == "Form1/Im1"
    assert jpeg_findings[0].observed == {
        "resource_name": "Im1",
        "pixel_width": 300,
        "pixel_height": 300,
        "bits_per_component": 8,
        "color_space_name": "DeviceRGB",
        "color_space_family": "DeviceRGB",
        "filters": ["DCTDecode"],
    }
    assert jpeg_findings[0].threshold == {"filter": "DCTDecode"}

    soft_mask_findings = [finding for finding in findings if finding.check_id == "images.has_soft_mask"]
    assert len(soft_mask_findings) == 1
    assert soft_mask_findings[0].severity == Severity.warning
    assert soft_mask_findings[0].page == 1
    assert soft_mask_findings[0].object_ref == "Form1/Im1"
    assert soft_mask_findings[0].observed == {
        "resource_name": "Im1",
        "pixel_width": 300,
        "pixel_height": 300,
        "bits_per_component": 8,
        "color_space_name": "DeviceRGB",
        "color_space_family": "DeviceRGB",
        "has_soft_mask": True,
    }

    color_findings = [finding for finding in findings if finding.check_id == "color.image_color_space_policy"]
    assert len(color_findings) == 1
    assert color_findings[0].severity == Severity.error
    assert color_findings[0].page == 1
    assert color_findings[0].object_ref == "Form1/Im1"
    assert color_findings[0].observed == {
        "color_space_name": "DeviceRGB",
        "color_space_family": "DeviceRGB",
        "resource_name": "Im1",
    }
    assert color_findings[0].threshold == {"severity_by_family": {"DeviceRGB": "error"}}


def test_pdfbox_adapter_maps_image_filter_policy(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im1",
      "filters": ["JPXDecode", "CustomDecode"],
      "pixel_width": 300,
      "pixel_height": 300,
      "bits_per_component": 8,
      "color_space_name": "DeviceRGB",
      "color_space_family": "DeviceRGB"
    },
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im2",
      "filters": ["FlateDecode"],
      "pixel_width": 300,
      "pixel_height": 300,
      "bits_per_component": 8,
      "color_space_name": "DeviceRGB",
      "color_space_family": "DeviceRGB"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "images.image_filter_policy": CheckConfig(
                check_id="images.image_filter_policy",
                enabled=True,
                severity=Severity.warning,
                params={
                    "severity_by_filter": {
                        "FlateDecode": None,
                        "JPXDecode": "warning",
                        "Other": "error",
                    }
                },
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert [finding.observed["matched_filter"] for finding in findings] == ["CustomDecode", "JPXDecode"]
    assert [finding.severity for finding in findings] == [Severity.error, Severity.warning]
    assert findings[0].threshold == {"severity_by_filter": {"CustomDecode": "error"}}
    assert findings[1].threshold == {"severity_by_filter": {"JPXDecode": "warning"}}


def test_pdfbox_adapter_skips_image_compression_checks_when_disabled(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im1",
      "filters": ["DCTDecode", "JPXDecode"],
      "has_soft_mask": true
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "images.jpeg_compression_policy": CheckConfig(
                check_id="images.jpeg_compression_policy",
                enabled=False,
                severity=Severity.warning,
                params={},
            ),
            "images.image_filter_policy": CheckConfig(
                check_id="images.image_filter_policy",
                enabled=False,
                severity=Severity.warning,
                params={"severity_by_filter": {"JPXDecode": "warning"}},
            ),
            "images.has_soft_mask": CheckConfig(
                check_id="images.has_soft_mask",
                enabled=False,
                severity=Severity.warning,
                params={},
            ),
        },
    )

    assert pdfbox.analyze(tmp_path / "input.pdf", target) == []


def test_pdfbox_adapter_allows_null_or_omitted_color_space_policy(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.output_intents",
      "category": "color",
      "scope": "document",
      "count": 1,
      "output_intents": []
    },
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im1",
      "pixel_width": 300,
      "pixel_height": 300,
      "drawn_width_pt": 72.0,
      "drawn_height_pt": 72.0,
      "x_dpi": 300.0,
      "y_dpi": 300.0,
      "min_dpi": 300.0,
      "color_space_name": "DeviceRGB",
      "color_space_family": "DeviceRGB"
    },
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im2",
      "pixel_width": 300,
      "pixel_height": 300,
      "drawn_width_pt": 72.0,
      "drawn_height_pt": 72.0,
      "x_dpi": 300.0,
      "y_dpi": 300.0,
      "min_dpi": 300.0,
      "color_space_name": "DeviceGray",
      "color_space_family": "DeviceGray"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.image_color_space_policy": CheckConfig(
                check_id="color.image_color_space_policy",
                enabled=True,
                severity=Severity.info,
                params={"severity_by_family": {"DeviceRGB": None}},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert [finding for finding in findings if finding.check_id == "color.image_color_space_policy"] == []


def test_pdfbox_adapter_rejects_invalid_color_space_policy_severity(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "images.effective_resolution",
      "category": "images",
      "page": 1,
      "resource_name": "Im1",
      "color_space_name": "DeviceRGB",
      "color_space_family": "DeviceRGB"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.image_color_space_policy": CheckConfig(
                check_id="color.image_color_space_policy",
                enabled=True,
                severity=Severity.info,
                params={"severity_by_family": {"DeviceRGB": "fatal"}},
            )
        },
    )

    try:
        pdfbox.analyze(tmp_path / "input.pdf", target)
    except ValueError as exc:
        assert "invalid severity" in str(exc)
    else:
        raise AssertionError("expected invalid severity to raise ValueError")


def test_pdfbox_adapter_reports_missing_output_intent(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.output_intents",
      "category": "color",
      "scope": "document",
      "count": 0,
      "output_intents": []
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.output_intent_required": CheckConfig(
                check_id="color.output_intent_required",
                enabled=True,
                severity=Severity.error,
                params={},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "color.output_intent_required"
    assert findings[0].category == "color"
    assert findings[0].severity == Severity.error
    assert findings[0].observed == {"count": 0}


def test_pdfbox_adapter_allows_present_output_intent(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.output_intents",
      "category": "color",
      "scope": "document",
      "count": 1,
      "output_intents": []
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.output_intent_required": CheckConfig(
                check_id="color.output_intent_required",
                enabled=True,
                severity=Severity.error,
                params={},
            )
        },
    )

    assert pdfbox.analyze(tmp_path / "input.pdf", target) == []


def test_pdfbox_adapter_maps_registration_color_misuse(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.special_color_usage",
      "category": "color",
      "page": 1,
      "resource_path": "Form1",
      "paint_operation": "path_fill",
      "paint_role": "non_stroking",
      "color_space_name": "Separation",
      "color_space_family": "Separation",
      "colorants": ["All"],
      "occurrences": 3
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.registration_color_misuse": CheckConfig(
                check_id="color.registration_color_misuse",
                enabled=True,
                severity=Severity.error,
                params={},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "color.registration_color_misuse"
    assert findings[0].category == "color"
    assert findings[0].severity == Severity.error
    assert findings[0].page == 1
    assert findings[0].object_ref == "Form1"
    assert findings[0].observed == {
        "paint_operation": "path_fill",
        "paint_role": "non_stroking",
        "color_space_name": "Separation",
        "color_space_family": "Separation",
        "colorants": ["All"],
        "occurrences": 3,
    }


def test_pdfbox_adapter_maps_spot_color_policy(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.special_color_usage",
      "category": "color",
      "page": 1,
      "paint_operation": "path_fill",
      "paint_role": "non_stroking",
      "color_space_name": "DeviceN",
      "color_space_family": "DeviceN",
      "colorants": ["BrandBlue", "AllowedSpot", "All"],
      "occurrences": 2
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.spot_color_policy": CheckConfig(
                check_id="color.spot_color_policy",
                enabled=True,
                severity=Severity.warning,
                params={"allowed_colorants": ["AllowedSpot"], "ignored_colorants": ["All", "None"]},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "color.spot_color_policy"
    assert findings[0].category == "color"
    assert findings[0].severity == Severity.warning
    assert findings[0].observed == {
        "paint_operation": "path_fill",
        "paint_role": "non_stroking",
        "color_space_name": "DeviceN",
        "color_space_family": "DeviceN",
        "colorants": ["BrandBlue", "AllowedSpot", "All"],
        "disallowed_colorants": ["BrandBlue"],
        "occurrences": 2,
    }
    assert findings[0].threshold == {
        "allowed_colorants": ["AllowedSpot"],
        "ignored_colorants": ["All", "None"],
    }


def test_pdfbox_adapter_maps_overprint_policy(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "graphics.overprint_usage",
      "category": "graphics",
      "page": 1,
      "resource_path": "Form1",
      "paint_operation": "path_stroke",
      "paint_role": "stroking",
      "overprint_mode": 1,
      "occurrences": 4
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "graphics.overprint_policy": CheckConfig(
                check_id="graphics.overprint_policy",
                enabled=True,
                severity=Severity.warning,
                params={},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "graphics.overprint_policy"
    assert findings[0].category == "graphics"
    assert findings[0].severity == Severity.warning
    assert findings[0].page == 1
    assert findings[0].object_ref == "Form1"
    assert findings[0].observed == {
        "paint_operation": "path_stroke",
        "paint_role": "stroking",
        "overprint_mode": 1,
        "occurrences": 4,
    }


def test_pdfbox_adapter_skips_print_color_checks_when_disabled(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "color.special_color_usage",
      "category": "color",
      "page": 1,
      "colorants": ["All"],
      "occurrences": 1
    },
    {
      "check_id": "graphics.overprint_usage",
      "category": "graphics",
      "page": 1,
      "paint_operation": "path_fill",
      "paint_role": "non_stroking",
      "overprint_mode": 1,
      "occurrences": 1
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "color.registration_color_misuse": CheckConfig(
                check_id="color.registration_color_misuse",
                enabled=False,
                severity=Severity.error,
                params={},
            ),
            "color.spot_color_policy": CheckConfig(
                check_id="color.spot_color_policy",
                enabled=False,
                severity=Severity.warning,
                params={"allowed_colorants": [], "ignored_colorants": ["All", "None"]},
            ),
            "graphics.overprint_policy": CheckConfig(
                check_id="graphics.overprint_policy",
                enabled=False,
                severity=Severity.warning,
                params={},
            ),
        },
    )

    assert pdfbox.analyze(tmp_path / "input.pdf", target) == []


def test_pdfbox_adapter_maps_transparency_policy_evidence(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "transparency.features",
      "category": "transparency",
      "page": 1,
      "resource_name": "gs1",
      "resource_path": "Form1/gs1",
      "features": ["non_stroking_alpha", "blend_mode"],
      "non_stroking_alpha": 0.5,
      "blend_mode": "Multiply"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "transparency.live_transparency_policy": CheckConfig(
                check_id="transparency.live_transparency_policy",
                enabled=True,
                severity=Severity.warning,
                params={
                    "severity_by_feature": {
                        "non_stroking_alpha": "warning",
                        "blend_mode": "error",
                    }
                },
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert len(findings) == 1
    assert findings[0].check_id == "transparency.live_transparency_policy"
    assert findings[0].category == "transparency"
    assert findings[0].severity == Severity.error
    assert findings[0].page == 1
    assert findings[0].object_ref == "Form1/gs1"
    assert findings[0].observed == {
        "features": ["non_stroking_alpha", "blend_mode"],
        "resource_name": "gs1",
        "non_stroking_alpha": 0.5,
        "blend_mode": "Multiply",
    }
    assert findings[0].threshold == {
        "severity_by_feature": {
            "non_stroking_alpha": "warning",
            "blend_mode": "error",
        }
    }


def test_pdfbox_adapter_allows_null_or_omitted_transparency_features(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "transparency.features",
      "category": "transparency",
      "page": 1,
      "resource_name": "gs1",
      "features": ["non_stroking_alpha", "blend_mode"],
      "non_stroking_alpha": 0.5,
      "blend_mode": "Multiply"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "transparency.live_transparency_policy": CheckConfig(
                check_id="transparency.live_transparency_policy",
                enabled=True,
                severity=Severity.info,
                params={"severity_by_feature": {"non_stroking_alpha": None}},
            )
        },
    )

    assert pdfbox.analyze(tmp_path / "input.pdf", target) == []


def test_pdfbox_adapter_falls_back_to_resource_name_without_resource_path(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "transparency.features",
      "category": "transparency",
      "page": 1,
      "resource_name": "gs1",
      "features": ["blend_mode"],
      "blend_mode": "Multiply"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "transparency.live_transparency_policy": CheckConfig(
                check_id="transparency.live_transparency_policy",
                enabled=True,
                severity=Severity.info,
                params={"severity_by_feature": {"blend_mode": "warning"}},
            )
        },
    )

    findings = pdfbox.analyze(tmp_path / "input.pdf", target)

    assert findings[0].object_ref == "gs1"


def test_pdfbox_adapter_reports_object_bounds_outside_configured_box(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "input.pdf"
    _write_pdf_with_bleed_box(pdf, bleed_box=(0, 0, 100, 100))
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "geometry.object_bounds",
      "category": "geometry",
      "page": 1,
      "resource_name": "Im1",
      "resource_path": "Form1/Im1",
      "object_type": "image",
      "bounds_pt": {"left": -2.0, "bottom": 10.0, "right": 105.0, "top": 120.0}
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "geometry.object_bounds_within_box": CheckConfig(
                check_id="geometry.object_bounds_within_box",
                enabled=True,
                severity=Severity.warning,
                params={"box": "BleedBox", "tolerance_pt": 0.5},
            )
        },
    )

    findings = pdfbox.analyze(pdf, target)

    assert len(findings) == 1
    assert findings[0].check_id == "geometry.object_bounds_within_box"
    assert findings[0].category == "geometry"
    assert findings[0].severity == Severity.warning
    assert findings[0].page == 1
    assert findings[0].object_ref == "Form1/Im1"
    assert findings[0].observed == {
        "object_type": "image",
        "bounds_pt": {"left": -2.0, "bottom": 10.0, "right": 105.0, "top": 120.0},
        "box": "BleedBox",
        "box_bounds_pt": {"left": 0.0, "bottom": 0.0, "right": 100.0, "top": 100.0},
        "outside": {"left_pt": 2.0, "right_pt": 5.0, "top_pt": 20.0},
    }
    assert findings[0].threshold == {"box": "BleedBox", "tolerance_pt": 0.5}


def test_pdfbox_adapter_allows_object_bounds_inside_configured_box(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "input.pdf"
    _write_pdf_with_bleed_box(pdf, bleed_box=(0, 0, 100, 100))
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "geometry.object_bounds",
      "category": "geometry",
      "page": 1,
      "resource_name": "Im1",
      "object_type": "image",
      "bounds_pt": {"left": 0.25, "bottom": 0.25, "right": 100.25, "top": 100.25}
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "geometry.object_bounds_within_box": CheckConfig(
                check_id="geometry.object_bounds_within_box",
                enabled=True,
                severity=Severity.warning,
                params={"box": "BleedBox", "tolerance_pt": 0.5},
            )
        },
    )

    assert pdfbox.analyze(pdf, target) == []


def test_pdfbox_adapter_skips_object_bounds_when_configured_box_is_missing(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "input.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as file:
        writer.write(file)
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "geometry.object_bounds",
      "category": "geometry",
      "page": 1,
      "resource_name": "Im1",
      "object_type": "image",
      "bounds_pt": {"left": -10.0, "bottom": 0.0, "right": 50.0, "top": 50.0}
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "geometry.object_bounds_within_box": CheckConfig(
                check_id="geometry.object_bounds_within_box",
                enabled=True,
                severity=Severity.warning,
                params={"box": "BleedBox", "tolerance_pt": 0.5},
            )
        },
    )

    assert pdfbox.analyze(pdf, target) == []


def test_pdfbox_adapter_rejects_invalid_transparency_policy_severity(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "pdfbox-analyzer.jar"
    jar.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR", str(jar))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="""
{
  "ok": true,
  "analyzer": "pdfbox",
  "metadata": {"page_count": 1},
  "evidence": [
    {
      "check_id": "transparency.features",
      "category": "transparency",
      "page": 1,
      "resource_name": "gs1",
      "features": ["blend_mode"],
      "blend_mode": "Multiply"
    }
  ]
}
""",
        ),
    )
    target = TargetConfig(
        fail_at=Severity.error,
        checks={
            "transparency.live_transparency_policy": CheckConfig(
                check_id="transparency.live_transparency_policy",
                enabled=True,
                severity=Severity.info,
                params={"severity_by_feature": {"blend_mode": "fatal"}},
            )
        },
    )

    try:
        pdfbox.analyze(tmp_path / "input.pdf", target)
    except ValueError as exc:
        assert "invalid severity" in str(exc)
    else:
        raise AssertionError("expected invalid severity to raise ValueError")
