from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from pdfdancer_preflight.models import should_fail
from pdfdancer_preflight.runner import run_preflight
from pdfdancer_preflight.target_config import load_target_config


app = typer.Typer(add_completion=False)


@app.command()
def main(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Input PDF."),
    target: Path = typer.Option(..., "--target", "-t", exists=True, dir_okay=False, readable=True, help="Target YAML."),
) -> None:
    try:
        target_config = load_target_config(target)
        result = run_preflight(pdf, target_config)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stdout)
        raise typer.Exit(code=2) from exc

    print(json.dumps(result, indent=2, sort_keys=True), file=sys.stdout)
    findings = result["findings"]
    if should_fail(_finding_stubs(findings), target_config.fail_at):
        raise typer.Exit(code=1)


def _finding_stubs(findings: list[dict]):
    from pdfdancer_preflight.models import Finding, Severity

    return [
        Finding(
            check_id=finding["check_id"],
            category=finding["category"],
            severity=Severity.parse(finding["severity"]),
            message=finding["message"],
            analyzer=finding["analyzer"],
        )
        for finding in findings
    ]

