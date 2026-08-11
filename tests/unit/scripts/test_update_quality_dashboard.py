from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import scripts.dev.update_quality_dashboard as dashboard
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    build_attestation,
    write_attestation,
)
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


def _pytest_attestation(
    tmp_path: Path,
    *,
    counts: dict[str, int] | None = None,
    args: tuple[str, ...] = (),
    exit_code: int = 0,
) -> Path:
    path = tmp_path / "pytest-result.json"
    default_counts = {
        "collected": 10,
        "executed": 10,
        "passed": 10,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }
    write_attestation(
        path,
        build_attestation(
            runner=REQUIRED_PYTEST_RUNNER_ID,
            command_args=args,
            exit_code=exit_code,
            counts=counts or default_counts,
        ),
    )
    return path


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
        f"{dashboard.POETRY} run -- python -m "
        "scripts.dev.run_required_pytest_gate -- --capture=sys "
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
    assert (
        "test_io_integration.py::TestIOIntegration::test_load_public_real_formats"
        in str(integration["command"])
    )
    assert "test_io_integration.py " not in str(integration["command"])
    assert "test_openneuro_bids_channels_apply_to_real_mne_raw" not in str(
        integration["command"]
    )
    assert "test_sleep_edf_infers_prefixed_types_without_renaming_channels" not in str(
        integration["command"]
    )
    assert "test_chbmit_duplicate_channel_names_keep_mne_unique_identity" not in str(
        integration["command"]
    )


def test_dashboard_handoff_profile_is_explicit() -> None:
    calibration_path = Path(
        "build/handoff-evidence/deadbeef/resource-guard/calibration.json"
    )
    args = dashboard.parse_args(
        [
            "--handoff",
            "--output-dir",
            "build/handoff-evidence/deadbeef/dashboard",
            "--resource-calibration-path",
            str(calibration_path),
        ]
    )

    assert args.handoff is True
    assert args.include_slow_checks is False
    assert args.expected_branch is None
    assert args.output_dir == Path("build/handoff-evidence/deadbeef/dashboard")
    assert args.resource_calibration_path == calibration_path


def test_dashboard_can_write_reports_to_a_sha_scoped_external_directory(tmp_path: Path):
    output_dir = tmp_path / ("a" * 40) / "dashboard"
    report = {
        "generated_at": "2026-08-01T00:00:00+00:00",
        "profile": "handoff",
        "workspace": "/tmp/xbrainlab",
        "overall_status": "pass",
        "checks": [],
    }

    dashboard.write_report(report, output_dir=output_dir)

    assert (
        json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))["profile"]
        == "handoff"
    )
    assert (output_dir / "latest.md").is_file()
    assert (output_dir / "history.jsonl").is_file()


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


def test_handoff_check_builder_requests_exact_calibration(monkeypatch, tmp_path: Path):
    commit = "a" * 40
    calibration_path = tmp_path / commit / "resource-guard" / "calibration.json"
    calibration_calls: list[dict[str, object]] = []

    def record_calibration(**kwargs):
        calibration_calls.append(kwargs)
        return SimpleNamespace(key="resource_calibration_evidence")

    monkeypatch.setattr(
        dashboard,
        "resource_calibration_evidence_check",
        record_calibration,
    )
    monkeypatch.setattr(
        dashboard,
        "run_check",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    dashboard.build_checks_for_mode(
        include_slow_checks=False,
        include_handoff_checks=True,
        resource_calibration_path=calibration_path,
        calibration_commit=commit,
    )

    assert calibration_calls == [
        {
            "artifact_path": calibration_path,
            "require_exact_source": True,
            "commit": commit,
        }
    ]


@pytest.mark.parametrize(
    ("check_key", "expected_validator"),
    (
        ("ui_dialog_acceptance", dashboard.validate_required_pytest_matrix),
        ("ui_product_walkthrough", dashboard.validate_required_pytest_matrix),
        (
            "public_bids_visible_ui_wizard_format_matrix",
            dashboard.validate_required_pytest_matrix,
        ),
        ("ui_unit_suite", dashboard.validate_required_pytest_matrix),
        ("io_integration", dashboard.validate_pytest_like),
        (
            "required_public_dataset_integration",
            dashboard.validate_required_pytest_matrix,
        ),
    ),
)
def test_registered_pytest_checks_declare_outcome_policy(
    monkeypatch,
    check_key: str,
    expected_validator,
):
    checks: dict[str, dict[str, object]] = {}

    def record_check(**kwargs):
        checks[str(kwargs["key"])] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)
    monkeypatch.setattr(
        dashboard,
        "resource_calibration_evidence_check",
        lambda **_kwargs: SimpleNamespace(key="resource_calibration_evidence"),
    )

    dashboard.build_checks_for_mode(
        include_slow_checks=False,
        include_handoff_checks=True,
    )

    assert checks[check_key]["validator"] is expected_validator


def test_every_required_dashboard_pytest_check_uses_attesting_runner(monkeypatch):
    checks: dict[str, dict[str, object]] = {}

    def record_check(**kwargs):
        checks[str(kwargs["key"])] = kwargs
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(dashboard, "run_check", record_check)
    monkeypatch.setattr(
        dashboard,
        "resource_calibration_evidence_check",
        lambda **_kwargs: SimpleNamespace(key="resource_calibration_evidence"),
    )

    dashboard.build_checks_for_mode(
        include_slow_checks=False,
        include_handoff_checks=True,
    )

    required = tuple(
        check
        for check in checks.values()
        if check.get("validator") is dashboard.validate_required_pytest_matrix
    )
    assert required
    for check in required:
        command = str(check["command"])
        assert (
            dashboard._dashboard_pytest_attestation_contract(
                shlex.split(command, posix=os.name != "nt")
            )
            is not None
        ), check["key"]


def test_optional_pytest_like_policy_remains_return_code_based():
    status, summary = validate_pytest_like(
        0,
        "Optional developer probe completed without a pytest summary.",
    )

    assert status == "pass"
    assert summary == "No pytest summary line found."


def test_required_pytest_matrix_passes_only_when_every_case_ran(tmp_path):
    attestation_path = _pytest_attestation(tmp_path)
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "======================= 10 passed in 1.25s =======================",
        attestation_path=attestation_path,
    )

    assert status == "pass"
    assert "10 passed" in summary


@pytest.mark.parametrize(
    "outcome",
    ("failed", "error", "errors", "skipped", "xfailed", "xpassed", "deselected"),
)
def test_required_pytest_matrix_fails_on_disallowed_outcomes(
    outcome: str,
    tmp_path,
):
    outcome_name = "errors" if outcome == "error" else outcome
    counts = {
        "collected": 10,
        "executed": 9 if outcome_name == "deselected" else 10,
        "passed": 9,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }
    counts[outcome_name] = 1
    attestation_path = _pytest_attestation(tmp_path, counts=counts)
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        f"================== 9 passed, 1 {outcome} in 1.25s ==================",
        attestation_path=attestation_path,
    )

    assert status == "fail"
    assert "incomplete" in summary.lower()


def test_required_pytest_matrix_fails_when_attestation_is_missing():
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "Required wrapper exited cleanly without reporting test outcomes.",
    )

    assert status == "fail"
    assert "attestation" in summary.lower()


def test_required_pytest_matrix_rejects_summary_words_inside_regular_output():
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "Migration note: 12 passed records were imported successfully.",
    )

    assert status == "fail"
    assert "attestation" in summary.lower()


def test_required_pytest_matrix_uses_attested_counts_not_terminal_prose(tmp_path):
    counts = {
        "collected": 22,
        "executed": 22,
        "passed": 21,
        "failed": 0,
        "errors": 0,
        "skipped": 1,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }
    attestation_path = _pytest_attestation(tmp_path, counts=counts)
    status, summary = dashboard.validate_required_pytest_matrix(
        0,
        "\n".join(
            (
                "================== 9 passed, 1 skipped in 1.25s ==================",
                "======================= 12 passed in 0.75s =======================",
            )
        ),
        attestation_path=attestation_path,
    )

    assert status == "fail"
    assert "skipped=1" in summary


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
    assert "Overall dashboard status: `WARN`" in rendered
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
                    "upstream": "origin/main",
                    "upstream_commit": "abcdef1",
                    "ahead_count": 0,
                    "behind_count": 0,
                    "dirty": False,
                    "dirty_count": 0,
                    "status_summary": [],
                    "status_truncated": False,
                    "worktree_fingerprint": "clean-fingerprint",
                    "source_tree_fingerprint": "source-tree",
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
                source_tree_fingerprint="source-tree",
                upstream="origin/main",
                upstream_commit="abcdef1",
                ahead_count=0,
                behind_count=0,
            ),
        )
        is True
    )


def test_handoff_profile_never_reuses_cached_report(
    monkeypatch,
    tmp_path: Path,
):
    latest_json = tmp_path / "latest.json"
    latest_json.write_text(
        json.dumps(
            {
                "generated_at": "2999-01-01T00:00:00+00:00",
                "workspace": str(dashboard.ROOT),
                "profile": "handoff",
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
            profile="handoff",
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
        is False
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
        upstream="origin/feature/test",
        upstream_commit="1" * 40,
        ahead_count=2,
        behind_count=3,
        protected_local_changes=("settings.json",),
        staged_protected_local_changes=("settings.json",),
    )

    assert state.as_report_dict() == {
        "branch": "feature/test",
        "commit": "abcdef1",
        "dirty": True,
        "status_summary": ["M file.py", "?? extra.py"],
        "dirty_count": 2,
        "status_truncated": False,
        "status_available": True,
        "status_fingerprint": dashboard.EMPTY_STATUS_FINGERPRINT,
        "worktree_fingerprint": "dirty-fingerprint",
        "dirty_fingerprint": "dirty-fingerprint",
        "source_tree_fingerprint": "unavailable",
        "upstream": "origin/feature/test",
        "upstream_commit": "1111111111111111111111111111111111111111",
        "ahead_count": 2,
        "behind_count": 3,
        "protected_local_changes": ["settings.json"],
        "staged_protected_local_changes": ["settings.json"],
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


def test_git_output_preserves_available_empty_status(monkeypatch):
    monkeypatch.setattr(dashboard.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        dashboard.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
        ),
    )

    assert dashboard._git_output(["status", "--short"], allow_empty=True) == ""


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


def test_run_check_requires_wrapper_completion_attestation(monkeypatch):
    command = (
        f"{dashboard.POETRY} run -- python -m "
        "scripts.dev.run_required_pytest_gate -- tests/example.py -q"
    )

    def fake_run(args, *, env, timeout_seconds):
        del timeout_seconds
        expected = dashboard._dashboard_pytest_attestation_contract(args)
        assert expected is not None
        runner, pytest_args = expected
        write_attestation(
            Path(env["XBL_PYTEST_RESULT_JSON"]),
            build_attestation(
                runner=runner,
                command_args=pytest_args,
                exit_code=0,
                counts={
                    "collected": 1,
                    "executed": 1,
                    "passed": 1,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "xfailed": 0,
                    "xpassed": 0,
                    "deselected": 0,
                },
            ),
        )
        return subprocess.CompletedProcess(args, 0, "1 passed", ""), False

    monkeypatch.setattr(dashboard, "_run_bounded_command", fake_run)

    result = dashboard.run_check(
        key="required",
        label="Required",
        category="quality",
        command=command,
        validator=dashboard.validate_required_pytest_matrix,
    )

    assert result.status == "pass"
    assert result.summary == "1 passed (attested)."


def test_run_check_rejects_forged_terminal_success_without_attestation(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "_run_bounded_command",
        lambda args, **_kwargs: (
            subprocess.CompletedProcess(
                args,
                0,
                "================ 1 passed in 0.01s ================",
                "",
            ),
            False,
        ),
    )

    result = dashboard.run_check(
        key="forged",
        label="Forged",
        category="quality",
        command=(
            f"{dashboard.POETRY} run -- python -m "
            "scripts.dev.run_required_pytest_gate -- tests/example.py -q"
        ),
        validator=dashboard.validate_required_pytest_matrix,
    )

    assert result.status == "fail"
    assert "attestation was not produced" in result.summary.lower()


def test_bounded_command_terminates_timed_out_process():
    completed, timed_out = dashboard._run_bounded_command(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        env=os.environ.copy(),
        timeout_seconds=0,
    )

    assert timed_out is True
    assert completed.returncode == 124


@pytest.mark.platform_contract
@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group contract")
def test_bounded_command_cleans_child_when_parent_exits_normally(tmp_path):
    child_pid_path = tmp_path / "dashboard-child.pid"
    source = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
    )

    completed, timed_out = dashboard._run_bounded_command(
        [sys.executable, "-c", source, str(child_pid_path)],
        env=os.environ.copy(),
        # Process startup can be delayed on shared/coverage-heavy CI runners;
        # this test protects descendant cleanup, not Python startup latency.
        timeout_seconds=15,
    )

    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert completed.returncode == 0
    assert timed_out is False
    assert not Path(f"/proc/{child_pid}").exists()


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


def test_handoff_traceability_fails_for_unprotected_dirty_paths():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=[" M settings.json", " M XBrainLab/app.py"],
            dirty_count=2,
            status_truncated=False,
            worktree_fingerprint="dirty-source-fingerprint",
            protected_local_changes=("settings.json",),
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "fail"
    assert result.returncode == 1
    assert "1 unprotected changed path" in result.summary


def test_traceability_fails_when_protected_settings_are_staged():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=["M  settings.json"],
            dirty_count=1,
            status_truncated=False,
            worktree_fingerprint="source-clean-fingerprint",
            staged_protected_local_changes=("settings.json",),
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "fail"
    assert result.returncode == 1
    assert "must never be staged" in result.summary


def test_collect_git_state_uses_full_sha_and_classifies_protected_settings(
    monkeypatch,
):
    commit = "0123456789abcdef0123456789abcdef01234567"
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_git_output(args: list[str], *, allow_empty: bool = False) -> str:
        calls.append((tuple(args), allow_empty))
        if args == ["branch", "--show-current"]:
            return "feature/test"
        if args == ["rev-parse", "HEAD"]:
            return commit
        if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]:
            return "origin/feature/test"
        if args == ["rev-parse", "@{upstream}"]:
            return commit
        if args == ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]:
            return "0\t0"
        if args == ["status", "--short", "--untracked-files=all"]:
            return "\n".join(
                (
                    "M  settings.json",
                    "?? .vscode/settings.json",
                    " M XBrainLab/app.py",
                )
            )
        return "unknown"

    monkeypatch.setattr(dashboard, "_git_output", fake_git_output)
    monkeypatch.setattr(
        dashboard,
        "_worktree_fingerprint",
        lambda _root: "source-clean-fingerprint",
    )

    state = dashboard.collect_git_state()

    assert state.commit == commit
    assert (("rev-parse", "HEAD"), False) in calls
    assert (("rev-parse", "--short=12", "HEAD"), False) not in calls
    assert (("status", "--short", "--untracked-files=all"), True) in calls
    assert state.protected_local_changes == ("settings.json",)
    assert state.staged_protected_local_changes == ("settings.json",)
    assert state.upstream == "origin/feature/test"
    assert state.upstream_commit == commit
    assert state.ahead_count == 0
    assert state.behind_count == 0


def test_only_root_settings_is_protected():
    assert frozenset({"settings.json"}) == dashboard.PROTECTED_LOCAL_CONFIG_PATHS


def test_handoff_main_returns_nonzero_for_unprotected_dirty_tree(monkeypatch):
    reports: list[dict[str, object]] = []

    def unexpected_check_build(**_kwargs):
        raise AssertionError("dirty handoff must fail before running dashboard checks")

    monkeypatch.setattr(
        dashboard,
        "collect_git_state",
        lambda: GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=[" M XBrainLab/app.py"],
            dirty_count=1,
            status_truncated=False,
            worktree_fingerprint="dirty-source-fingerprint",
        ),
    )
    monkeypatch.setattr(
        dashboard,
        "build_checks_for_mode",
        unexpected_check_build,
    )
    monkeypatch.setattr(
        dashboard,
        "write_report",
        lambda report, **_kwargs: reports.append(report),
    )

    exit_code = dashboard.main(["--handoff"])

    assert exit_code == 1
    assert reports[0]["overall_status"] == "fail"


def _assert_invalid_handoff_cannot_reuse_fresh_report(
    monkeypatch,
    git_state: GitState,
) -> None:
    reports: list[dict[str, object]] = []
    freshness_calls = 0

    def cached_report_is_fresh(*_args, **_kwargs):
        nonlocal freshness_calls
        freshness_calls += 1
        return True

    def unexpected_check_build(**_kwargs):
        raise AssertionError("invalid handoff must fail before running checks")

    monkeypatch.setattr(dashboard, "collect_git_state", lambda: git_state)
    monkeypatch.setattr(dashboard, "latest_is_fresh", cached_report_is_fresh)
    monkeypatch.setattr(
        dashboard,
        "build_checks_for_mode",
        unexpected_check_build,
    )
    monkeypatch.setattr(dashboard, "write_report", reports.append)

    exit_code = dashboard.main(["--handoff", "--skip-if-fresh-minutes", "60"])

    assert exit_code == 1
    assert freshness_calls == 0
    assert len(reports) == 1
    assert reports[0]["overall_status"] == "fail"
    checks = reports[0]["checks"]
    assert isinstance(checks, list)
    assert [check["key"] for check in checks] == ["workspace_traceability"]


def test_handoff_fresh_cache_cannot_bypass_unprotected_dirty_failure(monkeypatch):
    _assert_invalid_handoff_cannot_reuse_fresh_report(
        monkeypatch,
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=[" M XBrainLab/app.py"],
            dirty_count=1,
            worktree_fingerprint="dirty-source-fingerprint",
        ),
    )


def test_handoff_fresh_cache_cannot_bypass_staged_protected_failure(monkeypatch):
    _assert_invalid_handoff_cannot_reuse_fresh_report(
        monkeypatch,
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=["M  settings.json"],
            dirty_count=1,
            worktree_fingerprint="source-clean-fingerprint",
            protected_local_changes=("settings.json",),
            staged_protected_local_changes=("settings.json",),
        ),
    )


def test_handoff_traceability_rejects_truncated_commit_sha():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="abcdef123456",
            dirty=False,
            status_summary=[],
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "fail"
    assert result.returncode == 1
    assert "full 40-character commit SHA" in result.summary


def test_handoff_traceability_accepts_only_unstaged_protected_settings():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=[" M settings.json"],
            dirty_count=1,
            status_truncated=False,
            worktree_fingerprint="source-clean-fingerprint",
            protected_local_changes=("settings.json",),
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "pass"
    assert result.returncode == 0


def test_handoff_traceability_rejects_vscode_settings_as_unprotected():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=True,
            status_summary=[" M settings.json", " M .vscode/settings.json"],
            dirty_count=2,
            worktree_fingerprint="dirty-source-fingerprint",
            protected_local_changes=("settings.json",),
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "fail"
    assert "1 unprotected changed path" in result.summary


def _clean_synced_handoff_state(**overrides: object) -> GitState:
    values: dict[str, object] = {
        "branch": dashboard.DEFAULT_HANDOFF_BRANCH,
        "commit": "a" * 40,
        "dirty": False,
        "status_summary": [],
        "upstream": f"origin/{dashboard.DEFAULT_HANDOFF_BRANCH}",
        "upstream_commit": "a" * 40,
        "ahead_count": 0,
        "behind_count": 0,
    }
    values.update(overrides)
    return GitState(**values)  # type: ignore[arg-type]


def test_handoff_branch_hygiene_accepts_expected_synced_upstream():
    result = workspace_traceability_check(
        _clean_synced_handoff_state(),
        fail_on_unprotected_dirty=True,
        expected_branch=dashboard.DEFAULT_HANDOFF_BRANCH,
        require_upstream_sync=True,
    )

    assert result.status == "pass"
    assert "0 ahead / 0 behind" in result.summary


@pytest.mark.parametrize(
    ("overrides", "expected_summary"),
    [
        ({"branch": "feature/wrong"}, "expected branch"),
        ({"upstream": "unknown", "upstream_commit": "unknown"}, "configured upstream"),
        ({"upstream_commit": "b" * 40}, "does not equal upstream"),
        ({"ahead_count": 1}, "1 ahead / 0 behind"),
        ({"behind_count": 1}, "0 ahead / 1 behind"),
    ],
)
def test_handoff_branch_hygiene_fails_closed(
    overrides: dict[str, object],
    expected_summary: str,
):
    result = workspace_traceability_check(
        _clean_synced_handoff_state(**overrides),
        fail_on_unprotected_dirty=True,
        expected_branch=dashboard.DEFAULT_HANDOFF_BRANCH,
        require_upstream_sync=True,
    )

    assert result.status == "fail"
    assert expected_summary in result.summary


def test_handoff_output_contract_accepts_gitignored_sha_scoped_directory():
    commit = "a" * 40
    result = dashboard.handoff_output_contract_check(
        dashboard.ROOT / "build" / "handoff-evidence" / commit / "dashboard",
        commit=commit,
    )

    assert result.status == "pass"


@pytest.mark.parametrize(
    "output_dir",
    [
        dashboard.ROOT / "build" / "handoff-evidence" / "wrong" / "dashboard",
        dashboard.ROOT / "docs" / ("a" * 40) / "dashboard",
        None,
    ],
)
def test_handoff_output_contract_rejects_unscoped_or_tracked_output(
    output_dir: Path | None,
):
    result = dashboard.handoff_output_contract_check(
        output_dir,
        commit="a" * 40,
    )

    assert result.status == "fail"


def test_handoff_invalid_tracked_output_never_receives_failure_report(monkeypatch):
    reports: list[tuple[dict[str, object], dict[str, object]]] = []
    state = _clean_synced_handoff_state()
    invalid_output = dashboard.ROOT / "docs" / state.commit / "dashboard"
    monkeypatch.setattr(dashboard, "collect_git_state", lambda: state)
    monkeypatch.setattr(
        dashboard,
        "build_checks_for_mode",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid output must fail before dashboard checks")
        ),
    )
    monkeypatch.setattr(
        dashboard,
        "write_report",
        lambda report, **kwargs: reports.append((report, kwargs)),
    )

    exit_code = dashboard.main(["--handoff", "--output-dir", str(invalid_output)])

    assert exit_code == 1
    assert reports[0][1] == {}
    assert reports[0][0]["evidence_output_dir"] == str(dashboard.QUALITY_DIR)


def test_handoff_traceability_fails_when_git_status_is_unavailable():
    result = workspace_traceability_check(
        GitState(
            branch="feature/test",
            commit="a" * 40,
            dirty=False,
            status_summary=[],
            status_available=False,
        ),
        fail_on_unprotected_dirty=True,
    )

    assert result.status == "fail"
    assert result.returncode == 1
    assert "git status" in result.summary


def test_handoff_report_requires_external_manifest_sections_3_to_6(monkeypatch):
    reports: list[dict[str, object]] = []
    build_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        dashboard,
        "collect_git_state",
        lambda: _clean_synced_handoff_state(
            worktree_fingerprint="clean-fingerprint",
            source_tree_fingerprint="source-tree",
        ),
    )
    monkeypatch.setattr(
        dashboard,
        "build_checks_for_mode",
        lambda **kwargs: build_calls.append(kwargs) or [],
    )
    monkeypatch.setattr(
        dashboard,
        "write_report",
        lambda report, **_kwargs: reports.append(report),
    )

    output_dir = (
        dashboard.ROOT / "build" / "handoff-evidence" / ("a" * 40) / "dashboard"
    )
    calibration_path = (
        dashboard.ROOT
        / "build"
        / "handoff-evidence"
        / ("a" * 40)
        / "resource-guard"
        / "calibration.json"
    )
    exit_code = dashboard.main(
        [
            "--handoff",
            "--output-dir",
            str(output_dir),
            "--resource-calibration-path",
            str(calibration_path),
        ]
    )

    assert exit_code == 0
    assert build_calls == [
        {
            "include_slow_checks": True,
            "include_handoff_checks": True,
            "resource_calibration_path": calibration_path,
            "calibration_commit": "a" * 40,
        }
    ]
    handoff_manifest = reports[0]["handoff_manifest"]
    assert handoff_manifest == {
        "schema_version": 1,
        "role": "dashboard_summary",
        "certifies_full_manifest": False,
        "externally_required_sections": [3, 4, 5, 6],
        "ordered_sections": [1, 2, 3, 4, 5, 6, 7, 8],
        "dashboard_clean_last": True,
        "expected_branch": dashboard.DEFAULT_HANDOFF_BRANCH,
        "requires_upstream_sync": True,
    }
    rendered = render_markdown(reports[0])
    assert "Dashboard summary only" in rendered
    assert "does not run or certify manifest sections `3`-`6`" in rendered
    assert "Certifies full handoff manifest: `no`" in rendered
    assert "External manifest evidence required: `3`, `4`, `5`, `6`" in rendered


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


def test_resource_calibration_dashboard_default_is_checkpoint_only(
    monkeypatch,
    tmp_path: Path,
):
    artifact = tmp_path / "calibration.json"
    artifact.write_text('{"schema_version": 2}\n', encoding="utf-8")
    validation_kwargs: list[dict[str, object]] = []

    def validate(_payload, **kwargs):
        validation_kwargs.append(kwargs)
        return []

    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", artifact)
    monkeypatch.setattr(
        dashboard,
        "strict_calibration_failure_reasons",
        validate,
    )

    result = resource_calibration_evidence_check()

    assert result.status == "warn"
    assert "checkpoint-only" in result.summary.lower()
    assert validation_kwargs[0]["validate_source"] is False


def test_handoff_resource_calibration_uses_explicit_sha_scoped_ignored_path(
    monkeypatch,
    tmp_path: Path,
):
    commit = "a" * 40
    tracked_default = tmp_path / "tracked-calibration.json"
    tracked_default.write_text('{"identity": "tracked"}\n', encoding="utf-8")
    explicit = tmp_path / commit / "resource-guard" / "calibration.json"
    explicit.parent.mkdir(parents=True)
    explicit.write_text('{"identity": "explicit"}\n', encoding="utf-8")
    validated: list[tuple[dict[str, object], dict[str, object]]] = []

    def validate(payload, **kwargs):
        validated.append((payload, kwargs))
        return []

    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", tracked_default)
    monkeypatch.setattr(dashboard, "_git_ignores_path", lambda path: path == explicit)
    monkeypatch.setattr(dashboard, "strict_calibration_failure_reasons", validate)

    result = resource_calibration_evidence_check(
        artifact_path=explicit,
        require_exact_source=True,
        commit=commit,
    )

    assert result.status == "pass"
    assert validated[0][0]["identity"] == "explicit"
    assert validated[0][1]["validate_source"] is True
    assert str(explicit) in result.command


def test_tracked_default_resource_calibration_cannot_certify_handoff(
    monkeypatch,
    tmp_path: Path,
):
    commit = "a" * 40
    tracked_default = tmp_path / "calibration.json"
    tracked_default.write_text('{"schema_version": 2}\n', encoding="utf-8")
    validation_called = False

    def validate(_payload, **_kwargs):
        nonlocal validation_called
        validation_called = True
        return []

    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", tracked_default)
    monkeypatch.setattr(dashboard, "strict_calibration_failure_reasons", validate)

    result = resource_calibration_evidence_check(
        artifact_path=tracked_default,
        require_exact_source=True,
        commit=commit,
    )

    assert result.status == "fail"
    assert "tracked default" in result.summary.lower()
    assert validation_called is False


def test_handoff_resource_calibration_requires_explicit_path(
    monkeypatch,
    tmp_path: Path,
):
    tracked_default = tmp_path / "calibration.json"
    tracked_default.write_text('{"schema_version": 2}\n', encoding="utf-8")
    monkeypatch.setattr(dashboard, "RESOURCE_CALIBRATION_PATH", tracked_default)

    result = resource_calibration_evidence_check(
        require_exact_source=True,
        commit="a" * 40,
    )

    assert result.status == "fail"
    assert "explicit --resource-calibration-path" in result.summary


@pytest.mark.parametrize(
    ("include_commit", "ignored", "expected_summary"),
    (
        (False, True, "exact sha"),
        (True, False, "git-ignored"),
    ),
)
def test_handoff_resource_calibration_rejects_unscoped_or_unignored_path(
    monkeypatch,
    tmp_path: Path,
    include_commit: bool,
    ignored: bool,
    expected_summary: str,
):
    commit = "a" * 40
    scope = commit if include_commit else "checkpoint"
    artifact = tmp_path / scope / "resource-guard" / "calibration.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"schema_version": 2}\n', encoding="utf-8")
    monkeypatch.setattr(dashboard, "_git_ignores_path", lambda _path: ignored)

    result = resource_calibration_evidence_check(
        artifact_path=artifact,
        require_exact_source=True,
        commit=commit,
    )

    assert result.status == "fail"
    assert expected_summary in result.summary.lower()


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


def test_dashboard_records_stable_pre_and_post_source_identity(monkeypatch):
    reports: list[dict[str, object]] = []
    stable = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=False,
        status_summary=[],
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
    )
    monkeypatch.setattr(dashboard, "collect_git_state", lambda: stable)
    monkeypatch.setattr(dashboard, "build_checks_for_mode", lambda **_kwargs: [])
    monkeypatch.setattr(dashboard, "write_report", reports.append)

    assert dashboard.main([]) == 0

    report = reports[0]
    assert report["git_before"] == stable.as_report_dict()
    assert report["git_after"] == stable.as_report_dict()
    checks = report["checks"]
    assert isinstance(checks, list)
    stability = next(check for check in checks if check["key"] == "source_stability")
    assert stability["status"] == "pass"


def test_dashboard_fails_closed_when_source_identity_drifts_during_checks(
    monkeypatch,
):
    reports: list[dict[str, object]] = []
    before = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=False,
        status_summary=[],
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
    )
    after = GitState(
        branch="feature/evidence-drifted",
        commit="d" * 40,
        dirty=True,
        status_summary=[" M scripts/dev/update_quality_dashboard.py"],
        dirty_count=1,
        worktree_fingerprint="e" * 64,
        source_tree_fingerprint="f" * 64,
    )
    states = iter((before, after))
    monkeypatch.setattr(dashboard, "collect_git_state", lambda: next(states))
    monkeypatch.setattr(dashboard, "build_checks_for_mode", lambda **_kwargs: [])
    monkeypatch.setattr(dashboard, "write_report", reports.append)

    assert dashboard.main([]) == 1

    report = reports[0]
    assert report["git_before"] == before.as_report_dict()
    assert report["git_after"] == after.as_report_dict()
    assert report["overall_status"] == "fail"
    checks = report["checks"]
    assert isinstance(checks, list)
    stability = next(check for check in checks if check["key"] == "source_stability")
    assert stability["status"] == "fail"
    assert "branch" in stability["summary"]
    assert "commit" in stability["summary"]
    assert "dirty fingerprint" in stability["summary"]
    assert "source-tree fingerprint" in stability["summary"]


def test_source_stability_detects_unstaged_settings_becoming_staged() -> None:
    before = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=True,
        status_summary=[" M settings.json"],
        dirty_count=1,
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
        protected_local_changes=("settings.json",),
        staged_protected_local_changes=(),
    )
    after = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=True,
        status_summary=["M  settings.json"],
        dirty_count=1,
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
        protected_local_changes=("settings.json",),
        staged_protected_local_changes=("settings.json",),
    )

    result = dashboard.source_stability_check(before, after)

    assert result.status == "fail"
    assert "status" in result.summary.lower()


def test_source_stability_fails_when_post_run_status_is_unavailable() -> None:
    before = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=False,
        status_summary=[],
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
    )
    after = GitState(
        branch="feature/evidence",
        commit="a" * 40,
        dirty=False,
        status_summary=[],
        status_available=False,
        worktree_fingerprint="b" * 64,
        source_tree_fingerprint="c" * 64,
    )

    result = dashboard.source_stability_check(before, after)

    assert result.status == "fail"
    assert "unavailable" in result.summary.lower()


def test_source_stability_detects_status_change_beyond_display_summary() -> None:
    shared = {
        "branch": "feature/evidence",
        "commit": "a" * 40,
        "dirty": True,
        "status_summary": [f" M source_{index}.py" for index in range(40)],
        "dirty_count": 41,
        "status_truncated": True,
        "worktree_fingerprint": "b" * 64,
        "source_tree_fingerprint": "c" * 64,
    }
    before = GitState(**shared, status_fingerprint="d" * 64)
    after = GitState(**shared, status_fingerprint="e" * 64)

    result = dashboard.source_stability_check(before, after)

    assert result.status == "fail"
    assert "status fingerprint" in result.summary.lower()
