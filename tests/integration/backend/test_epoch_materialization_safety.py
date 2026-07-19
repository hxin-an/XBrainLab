"""Application-command regressions for atomic epoch materialization."""

from __future__ import annotations

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    CreateEpochCommand,
    ErrorType,
    resource_guard,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


def test_all_dropped_epochs_fail_without_committing_or_locking(monkeypatch) -> None:
    mne_raw = mne.io.RawArray(
        np.zeros((2, 1_000), dtype=np.float64),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    mne_raw.set_annotations(
        mne.Annotations(
            onset=[0.0],
            duration=[float(mne_raw.times[-1])],
            description=["BAD_motion"],
        )
    )
    raw = Raw("all-dropped-command.fif", mne_raw)
    raw.set_event(np.array([[200, 0, 1]], dtype=int), {"left": 1})
    study = Study()
    study.set_loaded_data_list([raw], force_update=True)
    original_preprocessed = study.preprocessed_data_list
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 2 * 10**12,
                "used_bytes": 10**12,
            }
        ),
    )

    result = ApplicationService(study).execute(
        CreateEpochCommand(
            t_min=-0.1,
            t_max=0.5,
            event_ids=["left"],
        )
    )

    assert result.failed is True
    assert result.error_type is ErrorType.VALIDATION
    assert "No usable epochs remain" in result.message
    assert study.preprocessed_data_list is original_preprocessed
    assert study.preprocessed_data_list[0] is raw
    assert raw.get_mne() is mne_raw
    assert study.epoch_data is None
    assert study.is_locked() is False
