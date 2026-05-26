from __future__ import annotations

from typing import Annotated

import typer
import uvicorn

app = typer.Typer(add_completion=False)


@app.command()
def main(
    host: Annotated[str, typer.Option("--host", help="Host to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to bind.")] = 8000,
    log_level: Annotated[str, typer.Option("--log-level", help="Uvicorn log level.")] = "info",
) -> None:
    uvicorn.run("presscheck.api:app", host=host, port=port, log_level=log_level)
