"""Integration coverage for temporal leakage from overlapping EEG windows."""

import mne
import numpy as np

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.application.commands import (
    GenerateDatasetCommand,
    LoadDataCommand,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    TrainingType,
    audit_dataset_splits,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor import WindowEpoch


def test_sliding_window_epochs_cannot_cross_trial_wise_splits_when_they_overlap():
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    source = Raw(
        "recordings/sliding-window-source.fif",
        mne.io.RawArray(np.zeros((1, 600)), info, verbose=False),
    )
    source.set_event(np.asarray([[0, 0, 1]]), {"continuous": 1})
    windowed = WindowEpoch([source]).data_preprocess(duration=2.0, overlap=1.0)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(windowed[0])
    epoch_data = Epochs(windowed)
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name("sliding-window-split")
    dataset.train_mask[0] = True
    dataset.val_mask[1] = True
    dataset.test_mask[3] = True
    dataset.remaining_mask[:] = False

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "epoch_window_overlap"
    )
    assert result.ok is False
    assert issue.indices == [0, 1]
    assert issue.details["overlaps"][0]["left_window"] == [0, 200]
    assert issue.details["overlaps"][0]["right_window"] == [100, 300]
    assert issue.details["overlaps"][0]["overlap_window"] == [100, 200]


def test_imported_multiclass_fif_without_provenance_is_backend_blocked(
    tmp_path,
) -> None:
    info = mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg")
    epoch_count = 12
    events = np.column_stack(
        (
            np.arange(epoch_count, dtype=int) * 150,
            np.zeros(epoch_count, dtype=int),
            (np.arange(epoch_count, dtype=int) % 2) + 1,
        ),
    )
    imported_epochs = mne.EpochsArray(
        np.zeros((epoch_count, 2, 100)),
        info,
        events=events,
        event_id={"left": 1, "right": 2},
        verbose=False,
    )
    fif_path = tmp_path / "imported-multiclass-epo.fif"
    imported_epochs.save(fif_path, overwrite=True, verbose=False)
    service = ApplicationService()

    load_result = service.execute(LoadDataCommand(paths=[str(fif_path)]))
    split_result = service.execute(
        GenerateDatasetCommand(
            split_strategy="trial",
            training_mode="group",
            test_ratio=0.25,
            val_ratio=0.25,
        ),
    )

    issue = next(
        item
        for item in split_result.diagnostics["split_audit"]["issues"]
        if item["details"].get("kind") == "missing_epoch_window_provenance"
    )
    assert load_result.ok is True
    assert load_result.state.epoch.epoch_count == epoch_count
    assert split_result.failed is True
    assert split_result.error_type == ErrorType.DATA_MISMATCH
    assert split_result.diagnostics["rolled_back"] is True
    assert split_result.diagnostics["blocking_issue_kinds"] == [
        "missing_epoch_window_provenance",
    ]
    assert issue["severity"] == "error"
    assert issue["details"]["unverified_count"] == epoch_count
    assert split_result.state.dataset.available is False
