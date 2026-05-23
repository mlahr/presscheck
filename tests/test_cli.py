import json
from pathlib import Path

from typer.testing import CliRunner

from presscheck.cli import app


def test_cli_returns_json_for_invalid_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "invalid.pdf"
    output = tmp_path / "result.json"
    pdf.write_text("not a pdf", encoding="utf-8")
    target = tmp_path / "target.yml"
    target.write_text(
        """
fail_at: error
checks:
  geometry.page_boxes_present:
    enabled: true
    severity: error
    required_boxes: [MediaBox]
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--target", str(target), "--output", str(output), str(pdf)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "starting preflight" in result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["failed"] is True
    assert payload["summary"]["total_findings"] == 1
    assert payload["summary"]["by_check"][0]["check_id"] == "document_integrity.pdf_parseable"
    assert payload["findings"][0]["check_id"] == "document_integrity.pdf_parseable"


def test_cli_writes_config_errors_to_output_file(tmp_path: Path) -> None:
    pdf = tmp_path / "input.pdf"
    output = tmp_path / "nested" / "result.json"
    target = tmp_path / "target.yml"
    pdf.write_text("%PDF-1.4\n", encoding="utf-8")
    target.write_text("fail_at: error\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["--target", str(target), "--output", str(output), str(pdf)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "preflight failed before normal result generation" in result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["failed"] is True
    assert "checks" in payload["error"]


def test_cli_can_quiet_info_logging(tmp_path: Path) -> None:
    pdf = tmp_path / "input.pdf"
    output = tmp_path / "result.json"
    target = tmp_path / "target.yml"
    pdf.write_text("%PDF-1.4\n", encoding="utf-8")
    target.write_text("fail_at: error\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["--target", str(target), "--output", str(output), "--log-level", "error", str(pdf)],
    )

    assert result.exit_code == 2
    assert "starting preflight" not in result.stderr


def test_cli_compare_mode_writes_comparison_and_individual_reports(tmp_path: Path, monkeypatch) -> None:
    before_pdf = tmp_path / "before.pdf"
    after_pdf = tmp_path / "after.pdf"
    output = tmp_path / "compare.json"
    target = _target(tmp_path)
    before_pdf.write_text("%PDF-1.4\n", encoding="utf-8")
    after_pdf.write_text("%PDF-1.4\n", encoding="utf-8")

    def fake_run_preflight(pdf: Path, _target_config) -> dict:
        if pdf == before_pdf:
            return _result(str(pdf), [_check("fonts", "fonts.non_embedded", "error", 1, [1])])
        return _result(str(pdf), [])

    monkeypatch.setattr("presscheck.cli.run_preflight", fake_run_preflight)

    result = CliRunner().invoke(
        app,
        ["--target", str(target), "--output", str(output), str(before_pdf), str(after_pdf)],
    )

    assert result.exit_code == 0
    assert "Preflight comparison" in result.stdout
    assert "resolved: 1" in result.stdout
    comparison = json.loads(output.read_text(encoding="utf-8"))
    before_report = json.loads((tmp_path / "compare.before.json").read_text(encoding="utf-8"))
    after_report = json.loads((tmp_path / "compare.after.json").read_text(encoding="utf-8"))
    assert comparison["regressed"] is False
    assert comparison["before"]["output"] == str(tmp_path / "compare.before.json")
    assert comparison["after"]["output"] == str(tmp_path / "compare.after.json")
    assert before_report["summary"]["total_findings"] == 1
    assert after_report["summary"]["total_findings"] == 0


def test_cli_compare_mode_exits_one_for_fail_threshold_regression(tmp_path: Path, monkeypatch) -> None:
    before_pdf = tmp_path / "before.pdf"
    after_pdf = tmp_path / "after.pdf"
    output = tmp_path / "compare.json"
    target = _target(tmp_path)
    before_pdf.write_text("%PDF-1.4\n", encoding="utf-8")
    after_pdf.write_text("%PDF-1.4\n", encoding="utf-8")

    def fake_run_preflight(pdf: Path, _target_config) -> dict:
        if pdf == before_pdf:
            return _result(str(pdf), [])
        return _result(str(pdf), [_check("fonts", "fonts.non_embedded", "error", 1, [1])])

    monkeypatch.setattr("presscheck.cli.run_preflight", fake_run_preflight)

    result = CliRunner().invoke(
        app,
        ["--target", str(target), "--output", str(output), str(before_pdf), str(after_pdf)],
    )

    assert result.exit_code == 1
    assert "added: 1" in result.stdout
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["regressed"] is True


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "target.yml"
    target.write_text(
        """
fail_at: error
checks:
  fonts.non_embedded:
    enabled: true
    severity: error
""",
        encoding="utf-8",
    )
    return target


def _result(input_path: str, checks: list[dict]) -> dict:
    by_severity = {"info": 0, "warning": 0, "error": 0}
    for check in checks:
        by_severity[check["severity"]] += check["count"]
    failed = by_severity["error"] > 0
    return {
        "ok": not failed,
        "failed": failed,
        "input": input_path,
        "fail_at": "error",
        "summary": {
            "total_findings": sum(by_severity.values()),
            "by_severity": by_severity,
            "by_check": checks,
            "color": {"image_color_space_findings_by_family": {}},
        },
        "findings": [],
    }


def _check(category: str, check_id: str, severity: str, count: int, pages: list[int]) -> dict:
    return {
        "category": category,
        "check_id": check_id,
        "severity": severity,
        "count": count,
        "pages": pages,
    }
