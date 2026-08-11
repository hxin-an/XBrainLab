"""Cross-source training and import/preprocess smoke for public fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict

import pytest

from scripts.dev.report_data_interpretation_format_matrix import (
    capture_public_fixture_facts,
)
from scripts.dev.run_public_cross_source_training_smoke import (
    PUBLIC_EPOCH_ONLY_FIXTURES,
    PUBLIC_TRAINING_FIXTURES,
    _apply_reviewed_internal_event_import,
)
from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    SaveDatasetSplitCommand,
    TrainCommand,
)
from XBrainLab.backend.training.record import EvalRecord, RecordKey
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict

pytestmark = pytest.mark.optional_public_fixture

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA_DIR = ROOT / "fixtures" / "data" / "public"


class PublicTrainingFixture(TypedDict):
    name: str
    filename: str
    source_family: str
    label_event_ids: list[str]
    epoch_event_ids: list[str]
    not_label_event_ids: list[str]
    class_map: dict[str, str]
    run_event_mappings: dict[str, dict[str, str]]
    tmin: float
    tmax: float
    expected_epoch_block: NotRequired[str]
    split_ratio: NotRequired[float]


def _assert_real_training_artifacts(output_root: Path) -> None:
    """Prove that one public-source run persisted reloadable safe artifacts."""
    record_manifests = list(output_root.rglob("record"))
    assert len(record_manifests) == 1
    artifact_dir = record_manifests[0].parent
    persisted_names = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    assert {"record", "record.npz", "eval", "eval.npz"} <= persisted_names
    checkpoint_paths = [
        path
        for path in artifact_dir.iterdir()
        if path.is_file() and path.name.startswith("Epoch-1-model")
    ]
    assert len(checkpoint_paths) == 1
    reloaded_state_dict = load_model_state_dict(checkpoint_paths[0])
    assert reloaded_state_dict

    reloaded_evaluation = EvalRecord.load(str(artifact_dir))
    assert reloaded_evaluation is not None
    assert len(reloaded_evaluation.label) > 0
    assert len(reloaded_evaluation.output) == len(reloaded_evaluation.label)


def _build_public_training_service(
    fixture: PublicTrainingFixture,
) -> ApplicationService:
    filepath = PUBLIC_DATA_DIR / str(fixture["filename"])
    if not filepath.exists():
        pytest.skip(f"Public fixture not downloaded at {filepath}")

    fact_case_id = {
        "physionet-edf": "public_physionet_motor_edf",
        "bbci-gdf": "public_bbci_gdf",
        "sccn-eeglab": "public_sccn_eeglab",
        "mne-cnt": "public_mne_cnt",
    }[fixture["name"]]
    facts = capture_public_fixture_facts(fact_case_id, ROOT.parent)
    assert facts["status"] == "passed"
    assert facts["mismatches"] == []

    service = ApplicationService()
    _apply_reviewed_internal_event_import(service, filepath, fixture)
    return service


@pytest.mark.parametrize("fixture", PUBLIC_TRAINING_FIXTURES, ids=lambda f: f["name"])
def test_public_cross_source_training_smoke(
    fixture: PublicTrainingFixture,
    tmp_path: Path,
) -> None:
    """Event-rich public fixtures should support a one-epoch training smoke."""
    service = _build_public_training_service(fixture)

    filter_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        ),
    )
    normalize_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=float(fixture["tmin"]),
            t_max=float(fixture["tmax"]),
            event_ids=list(fixture["epoch_event_ids"]),
        ),
    )
    split_ratio = float(fixture["split_ratio"])
    dataset_result = service.execute(
        SaveDatasetSplitCommand(
            test_ratio=split_ratio,
            val_ratio=split_ratio,
            split_strategy="trial",
            training_mode="individual",
        ),
    )

    assert filter_result.ok is True
    assert normalize_result.ok is True
    assert normalize_result.diagnostics["normalization_scope"] == (
        "per_epoch_per_channel"
    )
    assert normalize_result.diagnostics["raw_requests_deferred"] == 1
    assert normalize_result.diagnostics["recording_statistics_used"] is False
    assert epoch_result.ok is True
    assert epoch_result.diagnostics["deferred_normalization_applied_count"] == 1
    assert epoch_result.diagnostics["recording_statistics_used"] is False
    expected_event_names = [
        fixture["class_map"][event_name] for event_name in fixture["epoch_event_ids"]
    ]
    assert epoch_result.state.epoch.event_names == expected_event_names
    assert epoch_result.state.epoch.event_ids == {
        event_name: index for index, event_name in enumerate(expected_event_names)
    }
    assert epoch_result.state.epoch.epoch_count is not None
    assert epoch_result.state.epoch.epoch_count > 0
    assert dataset_result.ok is True
    assert dataset_result.state.dataset.split_spec_saved is True
    assert dataset_result.state.dataset.available is False

    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    output_root = tmp_path / "test-public-output"
    assert (
        service.execute(
            ConfigureTrainingCommand(
                output_dir=str(output_root),
                device="cpu",
                epoch=1,
                batch_size=8,
                learning_rate=0.001,
                save_checkpoints_every=1,
                evaluation_option="val_acc",
            ),
        ).ok
        is True
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is True

    train_result = service.execute(
        TrainCommand(confirmed=True, interactive=False),
    )

    assert train_result.ok is True
    assert train_result.diagnostics["split_preparation"]["split_audit"] == {
        "ok": True,
        "dataset_count": 1,
        "issues": [],
        "truncated_issue_count": 0,
    }
    assert train_result.state.dataset.available is True
    assert train_result.state.dataset.count == 1
    split_summary = train_result.state.dataset.active_split_summary
    assert split_summary["train_count"] > 0
    assert split_summary["val_count"] > 0
    assert split_summary["test_count"] > 0
    assert (
        split_summary["train_count"]
        + split_summary["val_count"]
        + split_summary["test_count"]
        == epoch_result.state.epoch.epoch_count
    )
    assert train_result.state.training.plan_count == 1
    assert train_result.state.training.run_count == 1
    assert train_result.state.training.finished_run_count == 1
    history = service.execute(
        QueryStateCommand(query="training_history"),
    )
    assert history.ok is True
    assert history.diagnostics["row_count"] == 1
    train_metrics = history.diagnostics["rows"][0]["metrics"]["train"]
    assert RecordKey.LOSS in train_metrics
    assert RecordKey.ACC in train_metrics
    _assert_real_training_artifacts(output_root)


@pytest.mark.parametrize("fixture", PUBLIC_EPOCH_ONLY_FIXTURES, ids=lambda f: f["name"])
def test_public_cross_source_import_preprocess_boundary(
    fixture: PublicTrainingFixture,
) -> None:
    """Boundary fixtures must not be relabeled to manufacture training evidence."""
    service = _build_public_training_service(fixture)

    filter_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        ),
    )
    normalize_result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z score",
        ),
    )
    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=float(fixture["tmin"]),
            t_max=float(fixture["tmax"]),
            event_ids=list(fixture["epoch_event_ids"]),
        ),
    )

    assert filter_result.ok is True
    assert normalize_result.ok is True
    assert normalize_result.diagnostics["normalization_scope"] == (
        "per_epoch_per_channel"
    )
    assert normalize_result.diagnostics["raw_requests_deferred"] == 1
    assert epoch_result.failed is True
    assert fixture["expected_epoch_block"] in epoch_result.message
    assert epoch_result.state.epoch.available is False
    assert epoch_result.state.interpretation.class_map == fixture["class_map"]
