from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from pdfdancer_preflight.runner import run_preflight
from pdfdancer_preflight.target_config import load_target_config

app = typer.Typer(add_completion=False)


@app.command()
def main(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True, help="Input PDF.")],
    target: Annotated[
        Path, typer.Option("--target", "-t", exists=True, dir_okay=False, readable=True, help="Target YAML.")
    ],
    output: Annotated[Path, typer.Option("--output", "-o", dir_okay=False, writable=True, help="Output JSON file.")],
) -> None:
    try:
        target_config = load_target_config(target)
        result = run_preflight(pdf, target_config)
    except Exception as exc:
        _write_json(output, {"ok": False, "failed": True, "error": str(exc)})
        raise typer.Exit(code=2) from exc

    _write_json(output, result)
    if result["failed"]:
        raise typer.Exit(code=1)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
