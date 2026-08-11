from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import scripts.dev.run_public_cross_source_training_smoke as smoke_script
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_EPOCH_ONLY_FIXTURES,
    PUBLIC_TRAINING_FIXTURES,
    REQUIRED_PUBLIC_SMOKE_CASE_IDS,
    SmokeResult,
    build_snapshot,
    render_markdown,
)


def test_build_snapshot_summarizes_runner_results(monkeypatch):
    fixture_names = {fixture["name"] for fixture in PUBLIC_TRAINING_FIXTURES}

    def fake_run_fixture_smoke(fixture):
        name = fixture["name"]
        assert name in fixture_names
        if name == "bbci-gdf":
            return SmokeResult(
                name=name,
                filename=fixture["filename"],
                source_family=fixture["source_family"],
                status="passed",
                dataset_count=1,
                message="ok",
                artifacts_reloaded=True,
            )
        return SmokeResult(
            name=name,
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="failed",
            dataset_count=0,
            message="boom",
        )

    def fake_run_fixture_boundary_smoke(fixture):
        status = "missing" if fixture["name"] == "sccn-eeglab" else "passed"
        return SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status=status,
            dataset_count=0,
            message="epoch only ok",
            protocol="import-preprocess-only",
        )

    monkeypatch.setattr(
        "scripts.dev.run_public_cross_source_training_smoke.run_fixture_smoke",
        fake_run_fixture_smoke,
    )
    monkeypatch.setattr(
        "scripts.dev.run_public_cross_source_training_smoke.run_fixture_boundary_smoke",
        fake_run_fixture_boundary_smoke,
    )

    repo_root = Path("/tmp/xbrainlab")
    snapshot = build_snapshot(repo_root)

    assert snapshot["public_data_dir"] == str(
        repo_root / "tests" / "fixtures" / "data" / "public"
    )
    assert snapshot["summary"]["passed"] == 2
    assert snapshot["summary"]["missing"] == 1
    assert snapshot["summary"]["failed"] == 1


def test_render_markdown_includes_summary():
    snapshot = {
        "results": [
            {
                "name": "bbci-gdf",
                "filename": "bbci-competition-iii-O3VR.gdf",
                "source_family": "BBCI",
                "status": "passed",
                "dataset_count": 1,
                "message": "ok",
                "protocol": "training",
            }
        ],
        "summary": {
            "passed": 1,
            "missing": 0,
            "failed": 0,
            "required_case_count": 4,
            "passed_required_case_count": 1,
            "all_required_passed": False,
            "message": "Event-rich public local-only fixtures provide repeatable training smoke where class-balanced splits are viable.",
        },
    }

    rendered = render_markdown(snapshot)

    assert "# Public Cross-Source Training Smoke" in rendered
    assert "bbci-competition-iii-O3VR.gdf" in rendered
    assert "passed" in rendered
    assert "training smoke" in rendered


def test_cnt_fixture_is_epoch_only_for_tiny_event_count():
    training_fixture_names = {fixture["name"] for fixture in PUBLIC_TRAINING_FIXTURES}
    epoch_fixture_by_name = {
        fixture["name"]: fixture for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
    }

    assert "mne-cnt" not in training_fixture_names
    assert epoch_fixture_by_name["mne-cnt"]["filename"] == "scan41_short.cnt"
    assert epoch_fixture_by_name["mne-cnt"]["label_event_ids"] == ["7"]
    assert epoch_fixture_by_name["mne-cnt"]["epoch_event_ids"] == ["7"]
    assert epoch_fixture_by_name["mne-cnt"]["not_label_event_ids"] == ["0", "109"]
    assert epoch_fixture_by_name["mne-cnt"]["tmax"] == 1.5


def test_sccn_fixture_uses_recording_boundary_safe_epoch_window():
    training_names = {fixture["name"] for fixture in PUBLIC_TRAINING_FIXTURES}
    fixture_by_name = {
        fixture["name"]: fixture for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
    }

    assert "sccn-eeglab" not in training_names
    assert fixture_by_name["sccn-eeglab"]["label_event_ids"] == []
    assert fixture_by_name["sccn-eeglab"]["epoch_event_ids"] == ["rt", "square"]
    assert fixture_by_name["sccn-eeglab"]["not_label_event_ids"] == [
        "rt",
        "square",
    ]
    assert fixture_by_name["sccn-eeglab"]["tmax"] == 1.5
    assert "lacks protocol ground truth" in str(
        fixture_by_name["sccn-eeglab"]["boundary_reason"]
    )


def test_public_smoke_case_configuration_has_unique_canonical_ids():
    configured_case_ids = [
        str(fixture["name"])
        for fixture in (*PUBLIC_TRAINING_FIXTURES, *PUBLIC_EPOCH_ONLY_FIXTURES)
    ]

    assert len(configured_case_ids) == len(set(configured_case_ids))
    assert set(configured_case_ids) == REQUIRED_PUBLIC_SMOKE_CASE_IDS


def test_cli_help_does_not_require_writable_mne_home(tmp_path):
    readonly_home = tmp_path / "readonly-home"
    readonly_home.mkdir()
    readonly_home.chmod(0o555)
    env = dict(os.environ)
    env.pop("MNE_DONTWRITE_HOME", None)
    env["HOME"] = str(readonly_home)

    completed = subprocess.run(  # noqa: S603 - fixed interpreter and checked-in script
        [sys.executable, str(smoke_script.__file__), "--help"],
        cwd=Path(smoke_script.__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--strict" in completed.stdout


def test_strict_smoke_denominator_is_fixed_when_fixture_configuration_shrinks(
    monkeypatch,
):
    monkeypatch.setattr(
        smoke_script,
        "PUBLIC_EPOCH_ONLY_FIXTURES",
        tuple(
            fixture
            for fixture in PUBLIC_EPOCH_ONLY_FIXTURES
            if fixture["name"] != "sccn-eeglab"
        ),
    )
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=1,
            message="ok",
            artifacts_reloaded=True,
        ),
    )
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_boundary_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=0,
            message="ok",
            protocol="import-preprocess-only",
        ),
    )

    summary = build_snapshot()["summary"]

    assert summary["required_case_count"] == len(REQUIRED_PUBLIC_SMOKE_CASE_IDS) == 4
    assert summary["missing_required_case_ids"] == ["sccn-eeglab"]
    assert summary["all_required_passed"] is False


def test_strict_snapshot_rejects_duplicate_case_after_failure_then_pass(
    monkeypatch,
):
    duplicate_fixture = dict(PUBLIC_TRAINING_FIXTURES[0])
    monkeypatch.setattr(
        smoke_script,
        "PUBLIC_TRAINING_FIXTURES",
        (duplicate_fixture, duplicate_fixture, PUBLIC_TRAINING_FIXTURES[1]),
    )
    duplicate_runs = 0

    def fake_run_fixture_smoke(fixture):
        nonlocal duplicate_runs
        status = "passed"
        if fixture["name"] == duplicate_fixture["name"]:
            duplicate_runs += 1
            status = "failed" if duplicate_runs == 1 else "passed"
        return SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status=status,
            dataset_count=1 if status == "passed" else 0,
            message="ok" if status == "passed" else "first run failed",
            artifacts_reloaded=status == "passed",
        )

    monkeypatch.setattr(
        smoke_script,
        "run_fixture_smoke",
        fake_run_fixture_smoke,
    )
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_boundary_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=0,
            message="ok",
            protocol="import-preprocess-only",
        ),
    )

    summary = build_snapshot()["summary"]

    assert summary["duplicate_configured_case_ids"] == ["physionet-edf"]
    assert summary["duplicate_result_case_ids"] == ["physionet-edf"]
    assert summary["failed_required_case_ids"] == ["physionet-edf"]
    assert "physionet-edf" not in summary["passed_required_case_ids"]
    assert summary["all_required_passed"] is False


def test_strict_snapshot_rejects_duplicate_result_ids(monkeypatch):
    duplicate_result_id = str(PUBLIC_TRAINING_FIXTURES[0]["name"])

    monkeypatch.setattr(
        smoke_script,
        "run_fixture_smoke",
        lambda fixture: SmokeResult(
            name=duplicate_result_id,
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=1,
            message="ok",
            artifacts_reloaded=True,
        ),
    )
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_boundary_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=0,
            message="ok",
            protocol="import-preprocess-only",
        ),
    )

    summary = build_snapshot()["summary"]

    assert summary["duplicate_configured_case_ids"] == []
    assert summary["duplicate_result_case_ids"] == ["physionet-edf"]
    assert summary["all_required_passed"] is False


def test_json_output_keeps_runner_noise_off_stdout(monkeypatch, capsys):
    def fake_build_snapshot():
        print("mne progress that should not corrupt json")
        return {
            "repo_root": "/tmp/xbrainlab",
            "public_data_dir": "/tmp/xbrainlab/tests/fixtures/data/public",
            "results": [],
            "summary": {
                "passed": 0,
                "missing": 0,
                "failed": 0,
                "message": "ok",
            },
        }

    monkeypatch.setattr(smoke_script, "build_snapshot", fake_build_snapshot)
    monkeypatch.setattr(
        "sys.argv",
        ["run_public_cross_source_training_smoke.py", "--format", "json"],
    )

    assert smoke_script.main() == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out)["summary"]["message"] == "ok"
    assert "mne progress" not in captured.out
    assert "mne progress that should not corrupt json" in captured.err


def test_strict_smoke_rejects_training_without_real_artifact_reload(
    monkeypatch,
):
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=1,
            message="training returned success without persistence evidence",
            artifacts_reloaded=False,
        ),
    )
    monkeypatch.setattr(
        smoke_script,
        "run_fixture_boundary_smoke",
        lambda fixture: SmokeResult(
            name=fixture["name"],
            filename=fixture["filename"],
            source_family=fixture["source_family"],
            status="passed",
            dataset_count=0,
            message="epoch only ok",
            protocol="import-preprocess-only",
        ),
    )

    summary = build_snapshot()["summary"]

    assert summary["missing_artifact_reload_case_ids"] == [
        "bbci-gdf",
        "physionet-edf",
    ]
    assert summary["passed_required_case_count"] == 2
    assert summary["all_required_passed"] is False


def test_required_training_smoke_does_not_mock_persistence() -> None:
    source = inspect.getsource(smoke_script.run_fixture_smoke)

    assert "unittest.mock" not in source
    assert "patch(" not in source
    assert "torch.save" not in source
    assert "numpy.savetxt" not in source
    assert "os.makedirs" not in source
