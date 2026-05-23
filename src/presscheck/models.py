from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Severity(IntEnum):
    info = 1
    warning = 2
    error = 3

    @classmethod
    def parse(cls, value: str) -> Severity:
        try:
            return cls[value]
        except KeyError as exc:
            allowed = ", ".join(item.name for item in cls)
            raise ValueError(f"invalid severity '{value}', expected one of: {allowed}") from exc


@dataclass(frozen=True)
class Finding:
    check_id: str
    category: str
    severity: Severity
    message: str
    analyzer: str
    source_tool: str | None = None
    page: int | None = None
    object_ref: str | None = None
    evidence_type: str = "factual"
    observed: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "check_id": self.check_id,
            "category": self.category,
            "severity": self.severity.name,
            "message": self.message,
            "analyzer": self.analyzer,
            "evidence_type": self.evidence_type,
        }
        if self.source_tool is not None:
            payload["source_tool"] = self.source_tool
        if self.page is not None:
            payload["page"] = self.page
        if self.object_ref is not None:
            payload["object_ref"] = self.object_ref
        if self.observed:
            payload["observed"] = self.observed
        if self.threshold:
            payload["threshold"] = self.threshold
        return payload


@dataclass(frozen=True)
class CheckConfig:
    check_id: str
    enabled: bool
    severity: Severity
    params: dict[str, Any]


@dataclass(frozen=True)
class TargetConfig:
    fail_at: Severity
    checks: dict[str, CheckConfig]

    def check(self, check_id: str) -> CheckConfig | None:
        check = self.checks.get(check_id)
        if check is None or not check.enabled:
            return None
        return check


def should_fail(findings: list[Finding], fail_at: Severity) -> bool:
    return any(finding.severity >= fail_at for finding in findings)
