from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

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
            )
        },
    )


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
