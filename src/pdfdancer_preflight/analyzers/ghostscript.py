from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from pdfdancer_preflight.models import Finding, TargetConfig

CHECK_ID = "document_integrity.ghostscript_processable"
logger = logging.getLogger(__name__)


def analyze(pdf_path: Path, target: TargetConfig) -> list[Finding]:
    check = target.check(CHECK_ID)
    if check is None:
        logger.debug("check disabled: %s", CHECK_ID)
        return []

    timeout = float(check.params.get("timeout_seconds", 60))
    command = [
        "gs",
        "-q",
        "-dBATCH",
        "-dNOPAUSE",
        "-dSAFER",
        "-sDEVICE=nullpage",
        str(pdf_path),
    ]

    logger.info("running Ghostscript processability check: timeout_seconds=%s", timeout)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    except FileNotFoundError:
        logger.error("Ghostscript executable not found")
        return [
            Finding(
                check_id=CHECK_ID,
                category="document_integrity",
                severity=check.severity,
                message="Ghostscript executable was not found.",
                analyzer="ghostscript",
                source_tool="ghostscript",
                observed={"executable": "gs"},
            )
        ]
    except subprocess.TimeoutExpired:
        logger.error("Ghostscript timed out: timeout_seconds=%s", timeout)
        return [
            Finding(
                check_id=CHECK_ID,
                category="document_integrity",
                severity=check.severity,
                message="Ghostscript timed out while processing the PDF.",
                analyzer="ghostscript",
                source_tool="ghostscript",
                observed={"timeout_seconds": timeout},
            )
        ]

    if completed.returncode == 0:
        logger.info("Ghostscript processed PDF successfully")
        return []

    logger.error("Ghostscript failed: exit_code=%s", completed.returncode)
    return [
        Finding(
            check_id=CHECK_ID,
            category="document_integrity",
            severity=check.severity,
            message="Ghostscript could not process the PDF.",
            analyzer="ghostscript",
            source_tool="ghostscript",
            observed={"exit_code": completed.returncode},
        )
    ]
