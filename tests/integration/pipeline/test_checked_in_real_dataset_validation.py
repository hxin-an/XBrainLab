"""Validation slices for checked-in real GDF fixtures plus attached labels."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    AttachLabelsCommand,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.training.record import RecordKey
from XBrainLab.backend.training.training_plan import TrainingPlanHolder

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data"
CHECKED_IN_GDF_STEMS = ("A01T", "A02T", "A03T")
EXPECTED_LABEL_EVENT_ID = {"1": 1, "2": 2, "3": 3, "4": 4}
EXPECTED_EPOCH_EVENT_IDS = {"1": 0, "2": 1, "3": 2, "4": 3}
EXPECTED_EPOCH_COUNTS = {
    "A01T": 273,
    "A02T": 270,
    "A03T": 270,
}
EXPECTED_SPLIT_SUMMARIES = {
    "A01T": {
        "count": 1,
        "train_count": 176,
        "val_count": 43,
        "test_count": 54,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
    "A02T": {
        "count": 1,
        "train_count": 173,
        "val_count": 43,
        "test_count": 54,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
    "A03T": {
        "count": 1,
        "train_count": 173,
        "val_count": 43,
        "test_count": 54,
        "audit": {"ok": True, "dataset_count": 1, "issues": []},
    },
}


def _checked_in_fixture_pair(stem: str) -> tuple[str, str]:
    return (
        str(TEST_DATA_DIR / f"{stem}.gdf"),
        str(TEST_DATA_DIR / "label" / f"{stem}.mat"),
    )


def test_real_gdf_internal_event_evidence_identifies_class_candidates():
    selected_files = [
        str(TEST_DATA_DIR / f"{stem}.gdf") for stem in CHECKED_IN_GDF_STEMS
    ]
    if not all(Path(path).exists() for path in selected_files):
        pytest.skip("Checked-in GDF fixtures are unavailable")

    service = ApplicationService()
    scan = service.execute(
        ScanSourceCommand(source_path=str(TEST_DATA_DIR), source_hint="folder")
    )
    assert scan.ok is True
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": selected_files,
                "label_carrier": "embedded_events",
            }
        )
    )
    assert preview.ok is True

    evidence = preview.diagnostics["preview"]["internal_event_preview"]
    candidate_codes = [row["event_code"] for row in evidence["candidate_label_events"]]
    excluded_by_code = {row["event_code"]: row for row in evidence["not_used_events"]}

    assert candidate_codes == ["769", "770", "771", "772"]
    assert all(
        row["coverage"] == "3/3 files" for row in evidence["candidate_label_events"]
    )
    assert {"768", "1023", "32766"} <= set(excluded_by_code)
    assert excluded_by_code["1023"]["use_as"] == "Exclude bad trials"
    assert excluded_by_code["32766"]["use_as"] == "Ignore"


def test_real_gdf_internal_labels_apply_the_same_artifact_policy():
    gdf_path = str(TEST_DATA_DIR / "A01T.gdf")
    service = ApplicationService()
    assert service.execute(
        ScanSourceCommand(source_path=gdf_path, source_hint="file")
    ).ok
    assert service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [gdf_path],
                "label_carrier": "embedded_events",
                "class_map": {
                    "769": "left hand",
                    "770": "right hand",
                    "771": "feet",
                    "772": "tongue",
                },
            }
        )
    ).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    assert service.execute(ApplyInterpretationCommand(confirmed=True)).ok
    assert service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        )
    ).ok
    epoch_result = service.execute(
        CreateEpochCommand(
            -0.2,
            1.0,
            event_ids=["769", "770", "771", "772"],
        )
    )

    assert epoch_result.ok
    assert epoch_result.state.epoch.epoch_count == 273


def _build_label_attached_service(stem: str) -> ApplicationService:
    gdf_path, label_path = _checked_in_fixture_pair(stem)
    if not os.path.exists(gdf_path):
        pytest.skip(f"Test data not found at {gdf_path}")
    if not os.path.exists(label_path):
        pytest.skip(f"Label data not found at {label_path}")

    service = ApplicationService()
    load_result = service.execute(LoadDataCommand(paths=[gdf_path]))
    assert load_result.ok is True
    assert load_result.diagnostics["success_count"] == 1
    attach_result = service.execute(
        AttachLabelsCommand(mapping={f"{stem}.gdf": label_path}),
    )
    assert attach_result.ok is True
    assert attach_result.diagnostics["success_count"] == 1
    return service


def _query_first_preprocessed(service: ApplicationService):
    result = service.execute(
        QueryStateCommand(query="data_lists", include_objects=True)
    )
    assert result.ok is True
    preprocessed = result.runtime["preprocessed_data_list"]
    assert preprocessed
    return preprocessed[0]


def _generate_trial_split(service: ApplicationService, stem: str):
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=4,
                high_freq=38,
            ),
        ).ok
        is True
    )
    assert (
        service.execute(
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE,
                method="z score",
            ),
        ).ok
        is True
    )
    epoch_result = service.execute(
        CreateEpochCommand(0, 4, event_ids=["1", "2", "3", "4"]),
    )
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.epoch_count == EXPECTED_EPOCH_COUNTS[stem]
    assert epoch_result.state.epoch.n_channels == 25
    assert epoch_result.state.epoch.n_times == 1001
    assert epoch_result.state.epoch.event_ids == EXPECTED_EPOCH_EVENT_IDS
    dataset_result = service.execute(
        GenerateDatasetCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        ),
    )
    assert dataset_result.ok is True
    assert dataset_result.diagnostics["split_audit"]["ok"] is True
    assert dataset_result.state.dataset.count == EXPECTED_SPLIT_SUMMARIES[stem]["count"]
    assert dataset_result.state.dataset.split_summary == EXPECTED_SPLIT_SUMMARIES[stem]
    return dataset_result


def _configure_training(service: ApplicationService, output_dir: Path) -> None:
    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok is True
    assert (
        service.execute(
            ConfigureTrainingCommand(
                output_dir=str(output_dir),
                device="cpu",
                epoch=1,
                batch_size=16,
                learning_rate=0.001,
                save_checkpoints_every=1,
                evaluation_option="test_acc",
            ),
        ).ok
        is True
    )
    assert service.get_capabilities().get(CommandName.TRAIN).available is True


def _configure_and_train(service: ApplicationService, output_dir: Path):
    _configure_training(service, output_dir)
    with (
        patch("matplotlib.pyplot.savefig"),
        patch("torch.save"),
        patch("numpy.savetxt"),
        patch("os.makedirs"),
    ):
        train_result = service.execute(
            TrainCommand(confirmed=True, interactive=False),
        )
    assert train_result.ok is True
    assert train_result.state.training.plan_count == 1
    assert train_result.state.training.run_count == 1
    assert train_result.state.training.finished_run_count == 1
    history = service.execute(
        QueryStateCommand(query="training_history", include_objects=True),
    )
    assert history.ok is True
    assert history.diagnostics["row_count"] == 1
    return history.runtime["rows"][0]["record"]


def _wait_for_training_stop(service: ApplicationService, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while service.get_state().active_training.is_running:
        if time.monotonic() >= deadline:
            raise AssertionError("Training job did not stop within the test timeout")
        time.sleep(0.02)


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_dataset_generation(stem):
    """Each checked-in GDF+MAT pair should support dataset generation."""
    service = _build_label_attached_service(stem)

    preprocessed = _query_first_preprocessed(service)
    events, event_id = preprocessed.get_event_list()
    assert event_id == EXPECTED_LABEL_EVENT_ID
    assert events.shape == (288, 3)
    assert preprocessed.is_labels_imported() is True

    dataset_result = _generate_trial_split(service, stem)

    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.count == EXPECTED_SPLIT_SUMMARIES[stem]["count"]
    assert dataset_result.state.dataset.split_summary == EXPECTED_SPLIT_SUMMARIES[stem]


@pytest.mark.parametrize("stem", CHECKED_IN_GDF_STEMS)
def test_checked_in_label_attached_training_smoke(stem, tmp_path):
    """Each checked-in GDF+MAT pair should support a one-epoch training smoke."""
    service = _build_label_attached_service(stem)
    _generate_trial_split(service, stem)

    record = _configure_and_train(service, tmp_path / "test-real-output")

    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train


def test_real_gdf_mat_data_interpretation_product_workflow(tmp_path):
    """A real external-label workflow must use the current interpretation spine."""
    gdf_path, label_path = _checked_in_fixture_pair("A01T")
    service = ApplicationService()
    choices = {
        "selected_eeg_files": [gdf_path],
        "label_carrier_choices": {
            label_path: {
                "label_field": "classlabel",
                "target_event_codes": ["769", "770", "771", "772"],
                "placement_method": "eeg_event",
                "time_model": "trial_order",
                "granularity": "trial",
            }
        },
        "class_map": {
            "1": "left hand",
            "2": "right hand",
            "3": "feet",
            "4": "tongue",
        },
    }

    assert service.execute(
        ScanSourceCommand(
            source_path=gdf_path,
            source_hint="file",
            label_sources=[label_path],
        )
    ).ok
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    assert preview.ok
    placement = preview.diagnostics["preview"]["label_carrier_preview"][0][
        "placement_review"
    ]
    assert placement["status"] == "ready"
    assert placement["matched"] == 288
    assert service.execute(ValidateInterpretationCommand()).ok
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert apply_result.ok
    assert apply_result.diagnostics["label_apply"]["mode"] == "sequence"

    assert service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        )
    ).ok
    epoch_result = service.execute(
        CreateEpochCommand(
            -0.2,
            1.0,
            event_ids=["left hand", "right hand", "feet", "tongue"],
        )
    )
    assert epoch_result.ok
    assert epoch_result.state.epoch.epoch_count == 273
    assert service.execute(
        GenerateDatasetCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        )
    ).ok
    _configure_and_train(service, tmp_path / "product-workflow-output")

    evaluation = service.execute(EvaluateCommand())
    assert evaluation.ok
    assert evaluation.diagnostics["available"] is True
    assert evaluation.diagnostics["plan_count"] == 1
    assert evaluation.diagnostics["finished_run_count"] == 1


def test_cuda_oom_job_failure_is_visible_and_training_can_restart(
    tmp_path, monkeypatch
):
    service = _build_label_attached_service("A01T")
    _generate_trial_split(service, "A01T")
    _configure_training(service, tmp_path / "oom-recovery-output")

    def raise_oom(_holder, _record) -> None:
        raise RuntimeError("CUDA out of memory. Tried to allocate 1.00 GiB")

    monkeypatch.setattr(TrainingPlanHolder, "train_one_repeat", raise_oom)
    start = service.execute(TrainCommand(confirmed=True, interactive=True))
    assert start.ok
    _wait_for_training_stop(service)

    history = service.execute(
        QueryStateCommand(query="training_history", include_objects=True)
    )
    assert history.ok
    failed_plan = history.runtime["rows"][0]["plan"]
    assert failed_plan.status == "Failed: CUDA out of memory"
    assert "CUDA out of memory during training" in failed_plan.error

    monkeypatch.undo()
    with (
        patch("matplotlib.pyplot.savefig"),
        patch("torch.save"),
        patch("numpy.savetxt"),
        patch("os.makedirs"),
    ):
        retry = service.execute(
            TrainCommand(confirmed=True, interactive=False, append=False)
        )
    assert retry.ok
    assert retry.state.training.finished_run_count == 1
