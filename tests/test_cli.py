from pathlib import Path

from typer.testing import CliRunner

from pdfdancer_preflight.cli import app


def test_cli_returns_json_for_invalid_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "invalid.pdf"
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

    result = CliRunner().invoke(app, ["--target", str(target), str(pdf)])

    assert result.exit_code == 1
    assert '"ok": false' in result.stdout
    assert "document_integrity.pdf_parseable" in result.stdout

