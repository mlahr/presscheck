from __future__ import annotations

import logging


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    logging.basicConfig(level=_parse_level(level), format=LOG_FORMAT, force=True)


def _parse_level(level: str) -> int:
    normalized = level.upper()
    if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        raise ValueError("log level must be one of: critical, error, warning, info, debug")
    return getattr(logging, normalized)

