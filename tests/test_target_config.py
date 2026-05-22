from pathlib import Path

import pytest

from pdfdancer_preflight.models import Severity
from pdfdancer_preflight.target_config import load_target_config


def test_load_target_config(tmp_path: Path) -> None:
    path = tmp_path / "target.yml"
    path.write_text(
        """
fail_at: warning
checks:
  geometry.page_boxes_present:
    enabled: true
    severity: error
    required_boxes: [MediaBox, TrimBox]
""",
        encoding="utf-8",
    )

    target = load_target_config(path)

    assert target.fail_at == Severity.warning
    check = target.check("geometry.page_boxes_present")
    assert check is not None
    assert check.severity == Severity.error
    assert check.params["required_boxes"] == ["MediaBox", "TrimBox"]


def test_requires_checks(tmp_path: Path) -> None:
    path = tmp_path / "target.yml"
    path.write_text("fail_at: error\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checks"):
        load_target_config(path)

