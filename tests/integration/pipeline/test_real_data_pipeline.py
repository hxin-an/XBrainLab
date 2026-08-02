import os
from unittest.mock import patch

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    TrainCommand,
)
from XBrainLab.backend.training.record import RecordKey

# Path to real test data stored under tests/fixtures/data in the repo
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "data"),
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
EXPECTED_A01T_CLASS_EVENT_NAMES = ["769", "770", "771", "772"]
EXPECTED_A01T_CLASS_EVENT_IDS = {
    "769": 0,
    "770": 1,
    "771": 2,
    "772": 3,
}
EXPECTED_A01T_SPLIT_SUMMARY = {
    "count": 1,
    "train_count": 185,
    "val_count": 46,
    "test_count": 57,
    "audit": {"ok": True, "dataset_count": 1, "issues": []},
}


@pytest.mark.skipif(not os.path.exists(GDF_FILE), reason="Real test data not found")
def test_real_data_pipeline(tmp_path):
    """
    Test the full pipeline with REAL data (A01T.gdf).
    This verifies that:
    1. Real GDF files can be loaded.
    2. Preprocessing works on real data.
    3. Dataset generation works with real epochs.
    4. Training loop runs successfully with real data shapes.
    """
    service = ApplicationService()

    load_result = service.execute(LoadDataCommand(paths=[GDF_FILE]))
    assert load_result.ok is True
    assert load_result.state.raw.count == 1

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

    assert filter_result.ok is True
    assert normalize_result.ok is True
    assert normalize_result.state.preprocessed.available is True

    epoch_context = service.get_epoch_dialog_context().require_usable()
    assert epoch_context.epoch_setup is not None
    event_names = {row["name"] for row in epoch_context.epoch_setup["available_events"]}
    assert set(EXPECTED_A01T_CLASS_EVENT_NAMES) <= event_names
    assert {"768", "1023", "32766"} <= event_names

    epoch_result = service.execute(
        CreateEpochCommand(
            t_min=0,
            t_max=4,
            baseline=None,
            event_ids=EXPECTED_A01T_CLASS_EVENT_NAMES,
        ),
    )
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.exists is True
    assert epoch_result.state.epoch.epoch_count == 288
    assert epoch_result.state.epoch.n_channels == 25
    assert epoch_result.state.epoch.n_times == 1001
    assert epoch_result.state.epoch.event_names == EXPECTED_A01T_CLASS_EVENT_NAMES
    assert epoch_result.state.epoch.event_ids == EXPECTED_A01T_CLASS_EVENT_IDS

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
    assert dataset_result.state.dataset.available is True
    assert dataset_result.state.dataset.count == EXPECTED_A01T_SPLIT_SUMMARY["count"]
    assert dataset_result.state.dataset.split_summary == EXPECTED_A01T_SPLIT_SUMMARY

    model_result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    training_result = service.execute(
        ConfigureTrainingCommand(
            output_dir=str(tmp_path / "training-output"),
            device="cpu",
            epoch=1,
            batch_size=16,
            learning_rate=0.001,
            save_checkpoints_every=1,
            evaluation_option="val_acc",
        ),
    )
    assert model_result.ok is True
    assert training_result.ok is True
    assert training_result.state.training.has_model is True
    assert training_result.state.training.has_training_option is True
    assert service.get_capabilities().get(CommandName.TRAIN).available is True

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
    assert train_result.state.training.has_trainer is True
    assert train_result.state.training.plan_count == 1
    assert train_result.state.training.run_count == 1
    assert train_result.state.training.finished_run_count == 1
    history_result = service.execute(
        QueryStateCommand(query="training_history"),
    )
    assert history_result.ok is True
    assert history_result.diagnostics["row_count"] == 1
    train_metrics = history_result.diagnostics["rows"][0]["metrics"]["train"]

    assert RecordKey.LOSS in train_metrics
    assert RecordKey.ACC in train_metrics

    evaluate_result = service.execute(EvaluateCommand())
    assert evaluate_result.ok is True
    assert evaluate_result.diagnostics["payload_type"] == "evaluation_summary"
    assert evaluate_result.diagnostics["available"] is True
    assert evaluate_result.diagnostics["plan_count"] == 1
    assert evaluate_result.diagnostics["finished_run_count"] == 1
    evaluation_plan = evaluate_result.diagnostics["plans"][0]
    assert evaluation_plan["finished_run_count"] == 1
    assert evaluation_plan["evaluation_splits"]
    assert evaluation_plan["runs"][0]["finished"] is True
