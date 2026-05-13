import os
from unittest.mock import patch

import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
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


@pytest.mark.skipif(not os.path.exists(GDF_FILE), reason="Real test data not found")
def test_real_data_pipeline():
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

    data_lists_result = service.execute(
        QueryStateCommand(query="data_lists", include_objects=True),
    )
    assert data_lists_result.ok is True
    assert data_lists_result.diagnostics["preprocessed_count"] == 1
    processed_raw = data_lists_result.diagnostics["preprocessed_data_list"][0]

    # Get available events
    events, event_id = processed_raw.get_event_list()

    # Deduplicate events based on time sample (column 0)
    # Keep the first occurrence
    _, unique_indices = np.unique(events[:, 0], return_index=True)
    # Sort indices to preserve order
    unique_indices = np.sort(unique_indices)
    events = events[unique_indices]

    # Verify no duplicates
    assert len(np.unique(events[:, 0])) == len(events), "Duplicates still exist!"

    # Filter event_names to only include those present in the deduplicated events
    present_event_ids = np.unique(events[:, -1])
    filtered_event_names = [
        name for name, eid in event_id.items() if eid in present_event_ids
    ]

    with patch.object(
        processed_raw, "get_raw_event_list", return_value=(events, event_id)
    ):
        epoch_result = service.execute(
            CreateEpochCommand(
                t_min=0,
                t_max=4,
                baseline=None,
                event_ids=filtered_event_names,
            ),
        )
    assert epoch_result.ok is True
    assert epoch_result.state.epoch.exists is True
    assert epoch_result.state.epoch.n_channels > 0
    assert epoch_result.state.epoch.n_times > 0
    assert len(epoch_result.state.epoch.event_ids) > 0

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
    assert dataset_result.state.dataset.count > 0
    assert dataset_result.state.dataset.split_summary["train_count"] > 0
    assert dataset_result.state.dataset.split_summary["val_count"] > 0
    assert dataset_result.state.dataset.split_summary["test_count"] > 0

    model_result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))
    training_result = service.execute(
        ConfigureTrainingCommand(
            output_dir="test_real_output",
            device="cpu",
            epoch=1,
            batch_size=16,
            learning_rate=0.001,
            save_checkpoints_every=1,
            evaluation_option="test_acc",
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
    history_result = service.execute(
        QueryStateCommand(query="training_history", include_objects=True),
    )
    assert history_result.ok is True
    assert history_result.diagnostics["row_count"] > 0
    record = history_result.diagnostics["rows"][0]["record"]

    assert RecordKey.LOSS in record.train
    assert RecordKey.ACC in record.train
