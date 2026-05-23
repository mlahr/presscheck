from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from pdfdancer_preflight.compare import compare_results, comparison_output_paths, format_comparison
from pdfdancer_preflight.logging_config import configure_logging
from pdfdancer_preflight.runner import run_preflight
from pdfdancer_preflight.target_config import load_target_config

app = typer.Typer(add_completion=False)
logger = logging.getLogger(__name__)


@app.command()
def main(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="Input PDF.")],
    target: Annotated[
        Path, typer.Option("--target", "-t", exists=True, dir_okay=False, readable=True, help="Target YAML.")
    ],
    output: Annotated[
        Path, typer.Option("--output", "-o", dir_okay=False, writable=True, help="Output JSON or comparison file.")
    ],
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Log level: critical, error, warning, info, debug."),
    ] = "info",
    after_pdf: Annotated[
        Path | None,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Optional after PDF for comparison mode."),
    ] = None,
) -> None:
    try:
        configure_logging(log_level)
        target_config = load_target_config(target)
        if after_pdf is not None:
            _run_comparison(pdf, after_pdf, target_config, output)
            return

        logger.info("starting preflight: pdf=%s target=%s output=%s", pdf, target, output)
        result = run_preflight(pdf, target_config)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("preflight failed before normal result generation")
        _write_json(output, {"ok": False, "failed": True, "error": str(exc)})
        raise typer.Exit(code=2) from exc

    _write_json(output, result)
    logger.info("wrote result: output=%s ok=%s findings=%s", output, result["ok"], len(result["findings"]))
    if result["failed"]:
        logger.warning("preflight failed severity threshold: fail_at=%s", result["fail_at"])
        raise typer.Exit(code=1)
    logger.info("preflight completed successfully")


def _run_comparison(before_pdf: Path, after_pdf: Path, target_config, output: Path) -> None:
    before_output, after_output = comparison_output_paths(output)
    logger.info(
        "starting preflight comparison: before=%s after=%s output=%s before_output=%s after_output=%s",
        before_pdf,
        after_pdf,
        output,
        before_output,
        after_output,
    )
    before_result = run_preflight(before_pdf, target_config)
    after_result = run_preflight(after_pdf, target_config)
    comparison = compare_results(before_result, after_result, before_output, after_output)

    _write_json(before_output, before_result)
    _write_json(after_output, after_result)
    _write_json(output, comparison)
    typer.echo(format_comparison(comparison), nl=False)
    logger.info("wrote comparison result: output=%s regressed=%s", output, comparison["regressed"])
    if comparison["regressed"]:
        logger.warning("preflight comparison regressed at severity threshold: fail_at=%s", comparison["fail_at"])
        raise typer.Exit(code=1)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
