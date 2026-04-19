from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import scripts.dev.update_quality_dashboard as dashboard
from scripts.dev.update_quality_dashboard import (
    EXPECTED_UI_ARTIFACTS,
    compute_overall_status,
    latest_is_fresh,
    render_markdown,
    validate_ui_artifacts,
)


def _check(status: str) -> dict[str, object]:
    return {
        "label": "Sample",
        "status": status,
        "duration_seconds": 1.23,
        "summary": "ok",
        "command": "pytest sample",
        "output_excerpt": "sample output",
    }


def test_compute_overall_status_prefers_fail():
    checks = [
        type("Check", (), {"status": "pass"})(),
        type("Check", (), {"status": "fail"})(),
        type("Check", (), {"status": "warn"})(),
    ]

    assert compute_overall_status(checks) == "fail"


def test_render_markdown_lists_checks_and_artifacts():
    report = {
        "generated_at": "2026-04-19T03:00:00+00:00",
        "workspace": "/tmp/xbrainlab",
        "overall_status": "warn",
        "checks": [_check("pass"), _check("warn")],
    }

    rendered = render_markdown(report)

    assert "# XBrainLab Quality Dashboard" in rendered
    assert "Overall status: `WARN`" in rendered
    assert "UI Artifacts" in rendered
    assert "artifacts/ui/main-window-initial.png" in rendered


def test_validate_ui_artifacts_detects_missing_files(tmp_path: Path):
    status, summary = validate_ui_artifacts(tmp_path)

    assert status == "fail"
    assert "Missing UI artifacts" in summary


def test_validate_ui_artifacts_accepts_visible_files(tmp_path: Path):
    for filename in EXPECTED_UI_ARTIFACTS:
        Image.new("RGB", (20, 20), (255, 255, 255)).save(tmp_path / filename)

    status, summary = validate_ui_artifacts(tmp_path)

    assert status == "pass"
    assert "UI artifacts look usable" in summary


def test_latest_is_fresh_uses_timestamp(monkeypatch, tmp_path: Path):
    latest_json = tmp_path / "latest.json"
    latest_json.write_text(
        json.dumps({"generated_at": "2999-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(dashboard, "LATEST_JSON", latest_json)

    assert latest_is_fresh(60) is True
