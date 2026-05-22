import json
from pathlib import Path

from typer.testing import CliRunner

from pdfdancer_preflight.cli import app


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
