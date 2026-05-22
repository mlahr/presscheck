from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

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
    output: Annotated[Path, typer.Option("--output", "-o", dir_okay=False, writable=True, help="Output JSON file.")],
    log_level: Annotated[str, typer.Option("--log-level", help="Log level: critical, error, warning, info, debug.")] = "info",
) -> None:
    try:
        configure_logging(log_level)
        logger.info("starting preflight: pdf=%s target=%s output=%s", pdf, target, output)
        target_config = load_target_config(target)
        result = run_preflight(pdf, target_config)
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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
