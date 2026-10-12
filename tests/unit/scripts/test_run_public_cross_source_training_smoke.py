from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

import scripts.dev.run_public_cross_source_training_smoke as smoke_script
from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_EPOCH_ONLY_FIXTURES,
    PUBLIC_TRAINING_FIXTURES,
    REQUIRED_PUBLIC_SMOKE_CASE_IDS,
    SmokeResult,
    build_snapshot,
    render_markdown,
)
from scripts.dev.training_evidence_fixture import verify_real_training_artifacts
from tests.integration.pipeline.test_trainer_model_integration import (
    _make_synthetic_dataset,
)
from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.record import EvalRecord, RecordKey, TrainRecord


@pytest.mark.parametrize("failure_stage", ["parent_directory", "output_allocation"])
def test_output_setup_failure_closes_real_imported_service(
    tmp_path, monkeypatch, failure_stage
):
    source = write_training_ready_raw_fif(tmp_path / "training_raw.fif")
    fixture = {
        **PUBLIC_TRAINING_FIXTURES[0],
        "filename": source.name,
        "label_event_ids": ["left", "right"],
        "not_label_event_ids": [],
        "class_map": {"left": "left", "right": "right"},
        "run_event_mappings": {},
    }
    service = ApplicationService()
    monkeypatch.setattr(smoke_script, "get_application_service", lambda _study: service)
    monkeypatch.setattr(smoke_script, "_public_data_dir", lambda: tmp_path)
    monkeypatch.setattr(smoke_script, "ROOT", tmp_path)
    if failure_stage == "parent_directory":
        (tmp_path / "build").write_text("not a directory", encoding="utf-8")
    else:
        original_mkdtemp = smoke_script.tempfile.mkdtemp

        def fail_output_allocation(*args, **kwargs):
            if kwargs.get("dir") == tmp_path / "build/validation/public-cross-source":
                raise OSError("output allocation denied")
            return original_mkdtemp(*args, **kwargs)

        monkeypatch.setattr(smoke_script.tempfile, "mkdtemp", fail_output_allocation)
    try:
        try:
            result = smoke_script.run_fixture_smoke(fixture)
        finally:
            assert service.is_closed, (
                "output setup failure left the imported service open"
            )
        assert result.status == "failed"
        assert result.artifacts_reloaded is False
        assert result.dataset_count == 0
        assert result.message
        if failure_stage == "output_allocation":
            assert "output allocation denied" in result.message
    finally:
        service.close()


@pytest.fixture
def persisted_training_artifacts(tmp_path, request):
    dataset, *_ = _make_synthetic_dataset()
    option = TrainingOption(
        output_dir=str(tmp_path),
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=2,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.VAL_ACC,
        repeat_num=1,
    )
    model = ModelHolder(EEGNet, {}, None).get_model(
        dataset.get_epoch_data().get_model_args()
    )
    record = TrainRecord(0, dataset, model, option, seed=42)
    for _epoch in range(getattr(request, "param", 1)):
        record.update_train({RecordKey.LOSS: 0.5, RecordKey.ACC: 75.0})
        record.update_validation({RecordKey.LOSS: 0.6, RecordKey.ACC: 70.0})
        record.step()
        record.export_checkpoint()
    artifact_dir = Path(record.target_path)
    EvalRecord(
        np.array([0, 1]),
        np.array([[0.8, 0.2], [0.1, 0.9]]),
        {},
        {},
        {},
        {},
        {},
    ).export(str(artifact_dir))
    return artifact_dir


@pytest.mark.parametrize("persisted_training_artifacts", [1, 2], indirect=True)
def test_training_artifact_evidence_loads_real_record(persisted_training_artifacts):
    verify_real_training_artifacts(persisted_training_artifacts)


@pytest.mark.parametrize("persisted_training_artifacts", [1, 2], indirect=True)
def test_training_artifact_evidence_rejects_wrong_checkpoint(
    persisted_training_artifacts,
):
    artifact_dir = persisted_training_artifacts
    manifest = json.loads((artifact_dir / "record").read_text(encoding="utf-8"))
    checkpoint = artifact_dir / f"Epoch-{manifest['payload']['epoch']}-model"
    checkpoint.rename(checkpoint.with_name(checkpoint.name + "-unrelated"))
    with pytest.raises(RuntimeError, match="checkpoint"):
        verify_real_training_artifacts(artifact_dir)


@pytest.mark.parametrize("corruption", ["npz", "schema", "history", "epoch"])
def test_training_artifact_evidence_rejects_corrupt_record(
    persisted_training_artifacts, corruption
):
    artifact_dir = persisted_training_artifacts
    verify_real_training_artifacts(artifact_dir)
    if corruption == "npz":
        (artifact_dir / "record.npz").write_bytes(b"not a numeric archive")
    else:
        manifest_path = artifact_dir / "record"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = manifest["payload"]
        if corruption == "schema":
            payload["record_schema_version"] = -1
        elif corruption == "history":
            payload["train"] = []
        else:
            payload["epoch"] = 99
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError):
        verify_real_training_artifacts(artifact_dir)


def test_public_data_dir_uses_canonical_data_root_when_configured(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("XBRAINLAB_DATA_DIR", str(tmp_path))

    assert smoke_script._public_data_dir() == (
        tmp_path / "datasets" / "public-fixtures"
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
