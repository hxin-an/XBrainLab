from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import scripts.dev.update_quality_dashboard as dashboard
from scripts.dev.update_quality_dashboard import (
    EXPECTED_UI_ARTIFACTS,
    GitState,
    compare_ui_images,
    compute_overall_status,
    configure_headless_env,
    latest_is_fresh,
    render_markdown,
    resource_calibration_evidence_check,
    validate_pytest_like,
    validate_ui_artifacts,
    workspace_traceability_check,
)


def test_ui_checks_force_offscreen_even_when_parent_runtime_selected_xcb(
    monkeypatch,
):
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")

    env = configure_headless_env(ui=True)

    assert env["QT_QPA_PLATFORM"] == "offscreen"


def test_native_xvfb_checks_explicitly_restore_xcb_platform(monkeypatch):
    commands: dict[str, str] = {}

    def record_check(**kwargs):
        commands[str(kwargs["key"])] = str(kwargs["command"])
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)

    dashboard.build_checks()

    assert "xvfb-run -a env QT_QPA_PLATFORM=xcb" in commands["startup_smoke"]
    assert "xvfb-run -a env QT_QPA_PLATFORM=xcb" in commands["ui_baseline_capture"]


def test_dashboard_registers_public_bids_visible_ui_wizard_format_matrix(
    monkeypatch,
):
    checks: dict[str, dict[str, object]] = {}

    def record_check(**kwargs):
        checks[str(kwargs["key"])] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)

    dashboard.build_checks()

    matrix = checks["public_bids_visible_ui_wizard_format_matrix"]
    assert matrix["command"] == (
        f"{dashboard.POETRY} run pytest --capture=sys "
        "tests/integration/ui/test_data_import_wizard_format_matrix.py -q"
    )
    assert matrix["ui"] is True
    assert matrix["validator"] is dashboard.validate_required_pytest_matrix


def test_handoff_dashboard_registers_manifest_before_strict_public_gates(
    monkeypatch,
):
    checks: list[dict[str, object]] = []

    def record_check(**kwargs):
        checks.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)

    dashboard.build_checks_for_mode(
        include_slow_checks=True,
        include_handoff_checks=True,
    )

    keys = [str(check["key"]) for check in checks]
    manifest_index = keys.index("required_public_fixture_manifest")
    integration_index = keys.index("required_public_dataset_integration")
    smoke_index = keys.index("required_public_cross_source_smoke")
    assert manifest_index < integration_index < smoke_index

    manifest = checks[manifest_index]
    assert "--profile required-ci --verify-only" in str(manifest["command"])

    integration = checks[integration_index]
    assert integration["validator"] is dashboard.validate_required_pytest_matrix
    assert "test_public_bids_fixture.py" in str(integration["command"])
    assert "test_public_cross_source_training_smoke.py" in str(integration["command"])


def test_dashboard_handoff_profile_is_explicit() -> None:
    args = dashboard.parse_args(["--handoff"])

    assert args.handoff is True
    assert args.include_slow_checks is False


def test_dashboard_gives_the_isolated_ui_suite_a_gate_level_timeout(monkeypatch):
    checks: dict[str, dict[str, object]] = {}

    def record_check(**kwargs):
        checks[str(kwargs["key"])] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)

    dashboard.build_checks()

    assert checks["ui_unit_suite"]["timeout_seconds"] == (
        dashboard.UI_UNIT_SUITE_TIMEOUT_SECONDS
    )
    assert (
        dashboard.UI_UNIT_SUITE_TIMEOUT_SECONDS
        > dashboard.DEFAULT_CHECK_TIMEOUT_SECONDS
    )


def test_required_pytest_matrix_passes_only_when_every_case_ran():
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "======================= 10 passed in 1.25s =======================",
    )

    assert status == "pass"
    assert "10 passed" in summary


def test_required_pytest_matrix_fails_instead_of_passing_with_skips():
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "================== 9 passed, 1 skipped in 1.25s ==================",
    )

    assert status == "fail"
    assert "skipped" in summary.lower()


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
            "worktree_fingerprint": "abc123",
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
                    "worktree_fingerprint": "clean-fingerprint",
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
                worktree_fingerprint="clean-fingerprint",
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
        worktree_fingerprint="dirty-fingerprint",
        protected_local_changes=("settings.json",),
    )

    assert state.as_report_dict() == {
        "branch": "feature/test",
        "commit": "abcdef1",
        "dirty": True,
        "status_summary": ["M file.py", "?? extra.py"],
        "dirty_count": 2,
        "status_truncated": False,
        "worktree_fingerprint": "dirty-fingerprint",
        "protected_local_changes": ["settings.json"],
        "unprotected_dirty_count": 1,
    }


def test_git_output_preserves_porcelain_status_prefix(monkeypatch):
    monkeypatch.setattr(dashboard.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        dashboard.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=" M settings.json\n",
        ),
    )

    assert dashboard._git_output(["status", "--short"]) == " M settings.json"


def test_run_check_reports_bounded_timeout(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "_run_bounded_command",
        lambda *_args, **_kwargs: (
            subprocess.CompletedProcess(
                args=["slow-check"],
                returncode=124,
                stdout="partial output",
                stderr="",
            ),
            True,
        ),
    )

    result = dashboard.run_check(
        key="slow",
        label="Slow check",
        category="quality",
        command="slow-check",
        timeout_seconds=12,
    )

    assert result.status == "fail"
    assert result.returncode == 124
    assert result.summary == "Timed out after 12 seconds."
    assert "partial output" in result.output_excerpt


def test_bounded_command_terminates_timed_out_process():
    completed, timed_out = dashboard._run_bounded_command(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        env=os.environ.copy(),
        timeout_seconds=0,
    )

    assert timed_out is True
    assert completed.returncode == 124


def test_workspace_traceability_warns_for_dirty_tree():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="abcdef1",
            dirty=True,
            status_summary=["M file.py"],
            dirty_count=1,
            status_truncated=False,
            worktree_fingerprint="dirty-fingerprint",
        )
    )

    assert result.status == "warn"
    assert "Dirty worktree has 1 unprotected changed path" in result.summary


def test_workspace_traceability_passes_for_only_declared_local_settings():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="abcdef1",
            dirty=True,
            status_summary=[" M settings.json"],
            dirty_count=1,
            status_truncated=False,
            worktree_fingerprint="source-clean-fingerprint",
            protected_local_changes=("settings.json",),
        )
    )

    assert result.status == "pass"
    assert "Tracked source is clean" in result.summary
    assert "settings.json" in result.summary


def test_workspace_traceability_warns_when_source_is_dirty_beside_local_settings():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="abcdef1",
            dirty=True,
            status_summary=[" M settings.json", " M XBrainLab/app.py"],
            dirty_count=2,
            status_truncated=False,
            worktree_fingerprint="dirty-source-fingerprint",
            protected_local_changes=("settings.json",),
        )
    )

    assert result.status == "warn"
    assert "1 unprotected changed path" in result.summary


def test_resource_calibration_dashboard_check_fails_when_artifact_is_stale(
    monkeypatch,
    tmp_path: Path,
):
    artifact = tmp_path / "calibration.json"
    artifact.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", artifact)
    monkeypatch.setattr(
        dashboard,
        "strict_calibration_failure_reasons",
        lambda _payload, **_kwargs: ["source digest is stale"],
    )

    result = resource_calibration_evidence_check()

    assert result.status == "fail"
    assert "source digest is stale" in result.summary


def test_resource_calibration_dashboard_check_accepts_fresh_strict_artifact(
    monkeypatch,
    tmp_path: Path,
):
    artifact = tmp_path / "calibration.json"
    artifact.write_text('{"schema_version": 2}\n', encoding="utf-8")
    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", artifact)
    monkeypatch.setattr(
        dashboard,
        "strict_calibration_failure_reasons",
        lambda _payload, **_kwargs: [],
    )

    result = resource_calibration_evidence_check()

    assert result.status == "pass"
    assert "strict calibration evidence is current" in result.summary


def test_worktree_fingerprint_changes_when_dirty_content_changes_with_same_status(
    tmp_path: Path,
):
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [git, "init", "-q"], cwd=tmp_path, check=True
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [git, "add", "tracked.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [
            git,
            "-c",
            "user.name=XBrainLab Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )
    tracked.write_text("first dirty value\n", encoding="utf-8")
    first = dashboard._worktree_fingerprint(tmp_path)
    tracked.write_text("second dirty value\n", encoding="utf-8")
    second = dashboard._worktree_fingerprint(tmp_path)

    assert first not in {"", "unavailable"}
    assert second not in {"", "unavailable"}
    assert first != second


def test_worktree_fingerprint_ignores_declared_local_settings_content(
    tmp_path: Path,
):
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [git, "init", "-q"], cwd=tmp_path, check=True
    )
    settings = tmp_path / "settings.json"
    tracked = tmp_path / "tracked.txt"
    settings.write_text('{"model": "baseline"}\n', encoding="utf-8")
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [git, "add", "settings.json", "tracked.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(  # noqa: S603 - resolved git binary with fixed test arguments.
        [
            git,
            "-c",
            "user.name=XBrainLab Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
    )

    baseline = dashboard._worktree_fingerprint(tmp_path)
    settings.write_text('{"model": "local-phi4"}\n', encoding="utf-8")
    local_override = dashboard._worktree_fingerprint(tmp_path)
    tracked.write_text("source changed\n", encoding="utf-8")
    source_changed = dashboard._worktree_fingerprint(tmp_path)

    assert baseline not in {"", "unavailable"}
    assert local_override == baseline
    assert source_changed != baseline


def test_latest_is_fresh_rejects_changed_worktree_fingerprint(
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
                    "worktree_fingerprint": "old-content",
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
                dirty=True,
                status_summary=["M app.py"],
                dirty_count=1,
                status_truncated=False,
                worktree_fingerprint="new-content",
            ),
        )
        is False
    )
