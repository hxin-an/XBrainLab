from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import scripts.dev.update_quality_dashboard as dashboard
from scripts.dev.update_quality_dashboard import (
    EXPECTED_UI_ARTIFACTS,
    GitState,
    compare_ui_images,
    compute_overall_status,
    latest_is_fresh,
    render_markdown,
    validate_pytest_like,
    validate_ui_artifacts,
    workspace_traceability_check,
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
        "git": {
            "branch": "integrate/test",
            "commit": "abc1234",
            "dirty": True,
            "dirty_count": 2,
            "status_truncated": False,
            "status_summary": ["M app.py", "?? new.py"],
        },
        "overall_status": "warn",
        "checks": [_check("pass"), _check("warn")],
    }

    rendered = render_markdown(report)

    assert "# XBrainLab Quality Dashboard" in rendered
    assert "Overall status: `WARN`" in rendered
    assert "UI Baseline Capture" in rendered
    assert "Git branch: `integrate/test`" in rendered
    assert "Dirty worktree: `yes`" in rendered
    assert "Dirty summary: `2` path(s)" in rendered
    assert "`M app.py`" in rendered
    assert "Generated capture paths (transient, git-ignored)" in rendered
    assert "artifacts/ui/main-window-initial.png" in rendered
    assert "tests/baselines/ui/main-window-initial.png" in rendered


def test_validate_ui_artifacts_detects_missing_files(tmp_path: Path):
    status, summary = validate_ui_artifacts(tmp_path, reference_dir=tmp_path / "refs")

    assert status == "fail"
    assert "Missing UI artifacts" in summary


def test_validate_ui_artifacts_accepts_visible_files(tmp_path: Path):
    reference_dir = tmp_path / "refs"
    reference_dir.mkdir()
    for filename in EXPECTED_UI_ARTIFACTS:
        Image.new("RGB", (20, 20), (255, 255, 255)).save(tmp_path / filename)
        Image.new("RGB", (20, 20), (255, 255, 255)).save(reference_dir / filename)

    status, summary = validate_ui_artifacts(tmp_path, reference_dir=reference_dir)

    assert status == "pass"
    assert "match approved references" in summary


def test_validate_ui_artifacts_fails_when_reference_images_drift(tmp_path: Path):
    reference_dir = tmp_path / "refs"
    reference_dir.mkdir()
    for filename in EXPECTED_UI_ARTIFACTS:
        Image.new("RGB", (20, 20), (255, 255, 255)).save(reference_dir / filename)
        Image.new("RGB", (20, 20), (255, 255, 255)).save(tmp_path / filename)

    Image.new("RGB", (20, 20), (0, 0, 0)).save(tmp_path / EXPECTED_UI_ARTIFACTS[0])

    status, summary = validate_ui_artifacts(tmp_path, reference_dir=reference_dir)

    assert status == "fail"
    assert "Nearly black UI artifacts" in summary


def test_compare_ui_images_detects_visual_drift(tmp_path: Path):
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (20, 20), (255, 255, 255)).save(reference)
    Image.new("RGB", (20, 20), (255, 255, 255)).save(candidate)

    status, metrics = compare_ui_images(reference, candidate)

    assert status == "pass"
    assert metrics["mean_diff"] == 0
    assert metrics["changed_ratio"] == 0

    Image.new("RGB", (20, 20), (0, 0, 0)).save(candidate)
    status, metrics = compare_ui_images(reference, candidate)

    assert status == "fail"
    assert isinstance(metrics["mean_diff"], float)
    assert metrics["mean_diff"] > 0


def test_latest_is_fresh_uses_timestamp(monkeypatch, tmp_path: Path):
    latest_json = tmp_path / "latest.json"
    latest_json.write_text(
        json.dumps(
            {
                "generated_at": "2999-01-01T00:00:00+00:00",
                "workspace": str(dashboard.ROOT),
                "profile": "fast",
                "git": {
                    "branch": "main",
                    "commit": "abcdef1",
                    "dirty": False,
                    "dirty_count": 0,
                    "status_summary": [],
                    "status_truncated": False,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(dashboard, "LATEST_JSON", latest_json)

    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="main",
                commit="abcdef1",
                dirty=False,
                status_summary=[],
                dirty_count=0,
                status_truncated=False,
            ),
        )
        is True
    )


def test_latest_is_fresh_rejects_commit_or_dirty_mismatch(
    monkeypatch,
    tmp_path: Path,
):
    latest_json = tmp_path / "latest.json"
    latest_json.write_text(
        json.dumps(
            {
                "generated_at": "2999-01-01T00:00:00+00:00",
                "workspace": str(dashboard.ROOT),
                "profile": "fast",
                "git": {
                    "branch": "main",
                    "commit": "abcdef1",
                    "dirty": False,
                    "dirty_count": 0,
                    "status_summary": [],
                    "status_truncated": False,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "LATEST_JSON", latest_json)

    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="main",
                commit="abcdef2",
                dirty=False,
                status_summary=[],
                dirty_count=0,
                status_truncated=False,
            ),
        )
        is False
    )
    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="main",
                commit="abcdef1",
                dirty=True,
                status_summary=["M app.py"],
                dirty_count=1,
                status_truncated=False,
            ),
        )
        is False
    )


def test_latest_is_fresh_rejects_branch_or_dirty_status_mismatch(
    monkeypatch,
    tmp_path: Path,
):
    latest_json = tmp_path / "latest.json"
    latest_json.write_text(
        json.dumps(
            {
                "generated_at": "2999-01-01T00:00:00+00:00",
                "workspace": str(dashboard.ROOT),
                "profile": "fast",
                "git": {
                    "branch": "main",
                    "commit": "abcdef1",
                    "dirty": True,
                    "dirty_count": 1,
                    "status_summary": ["M app.py"],
                    "status_truncated": False,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "LATEST_JSON", latest_json)

    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="feature",
                commit="abcdef1",
                dirty=True,
                status_summary=["M app.py"],
                dirty_count=1,
                status_truncated=False,
            ),
        )
        is False
    )
    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="main",
                commit="abcdef1",
                dirty=True,
                status_summary=["M other.py"],
                dirty_count=1,
                status_truncated=False,
            ),
        )
        is False
    )
    assert (
        latest_is_fresh(
            60,
            git_state=GitState(
                branch="main",
                commit="abcdef1",
                dirty=True,
                status_summary=["M app.py"],
                dirty_count=1,
                status_truncated=True,
            ),
        )
        is False
    )


def test_validate_pytest_like_fails_on_traceback_even_with_zero_returncode():
    output = "\n".join(
        [
            "============================ 1233 passed in 32.67s =============================",
            "Traceback (most recent call last):",
            '  File "matplotlib/backends/backend_qt.py", line 523, in _draw_idle',
            "RuntimeError: wrapped C/C++ object of type FigureCanvasQTAgg has been deleted",
        ]
    )

    status, summary = validate_pytest_like(0, output)

    assert status == "fail"
    assert "Unhandled exception output" in summary
    assert "FigureCanvasQTAgg has been deleted" in summary


def test_git_state_serializes_dirty_status_summary():
    state = GitState(
        branch="feature/test",
        commit="abcdef1",
        dirty=True,
        status_summary=["M file.py", "?? extra.py"],
        dirty_count=2,
        status_truncated=False,
    )

    assert state.as_report_dict() == {
        "branch": "feature/test",
        "commit": "abcdef1",
        "dirty": True,
        "status_summary": ["M file.py", "?? extra.py"],
        "dirty_count": 2,
        "status_truncated": False,
    }


def test_workspace_traceability_warns_for_dirty_tree():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="abcdef1",
            dirty=True,
            status_summary=["M file.py"],
            dirty_count=1,
            status_truncated=False,
        )
    )

    assert result.status == "warn"
    assert "Dirty worktree has 1 changed path" in result.summary
