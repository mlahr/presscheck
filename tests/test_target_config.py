from pathlib import Path

import pytest

from presscheck.models import Severity
from presscheck.target_config import load_target_config


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


def test_online_fontswap_target_policy() -> None:
    target = load_target_config(Path("examples/targets/online-fontswap.yml"))

    assert target.fail_at == Severity.error

    font_check = target.check("fonts.non_embedded")
    assert font_check is not None
    assert font_check.severity == Severity.error

    assert target.check("geometry.trim_size_matches") is None
    assert target.check("geometry.bleed_margin_at_least") is None
    assert target.check("color.output_intent_required") is None

    link_check = target.check("interactive.link_uri_policy")
    assert link_check is not None
    assert link_check.params["allowed_schemes"] == ["http", "https", "mailto"]
    assert link_check.params["disallow_all"] is False
