from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pdfdancer_preflight.models import CheckConfig, Severity, TargetConfig


def load_target_config(path: Path) -> TargetConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"target config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid target YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("target config must be a mapping")

    fail_at_raw = raw.get("fail_at")
    if not isinstance(fail_at_raw, str):
        raise ValueError("target config requires string field 'fail_at'")
    fail_at = Severity.parse(fail_at_raw)

    checks_raw = raw.get("checks")
    if not isinstance(checks_raw, dict) or not checks_raw:
        raise ValueError("target config requires non-empty mapping field 'checks'")

    checks: dict[str, CheckConfig] = {}
    for check_id, check_raw in checks_raw.items():
        if not isinstance(check_id, str):
            raise ValueError("check ids must be strings")
        if not isinstance(check_raw, dict):
            raise ValueError(f"check '{check_id}' must be a mapping")
        enabled = bool(check_raw.get("enabled", True))
        severity_raw = check_raw.get("severity")
        if not isinstance(severity_raw, str):
            raise ValueError(f"check '{check_id}' requires string field 'severity'")
        severity = Severity.parse(severity_raw)
        params: dict[str, Any] = {key: value for key, value in check_raw.items() if key not in {"enabled", "severity"}}
        checks[check_id] = CheckConfig(check_id=check_id, enabled=enabled, severity=severity, params=params)

    return TargetConfig(fail_at=fail_at, checks=checks)

