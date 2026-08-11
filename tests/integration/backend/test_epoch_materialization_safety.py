"""Application-command regressions for atomic epoch materialization."""

from __future__ import annotations

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    ErrorType,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    resource_guard,
)


def test_all_dropped_epochs_fail_without_committing_or_locking(
    monkeypatch,
    tmp_path,
) -> None:
    mne_raw = mne.io.RawArray(
        np.zeros((2, 1_000), dtype=np.float64),
        mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
        verbose=False,
    )
    mne_raw.set_annotations(
        mne.Annotations(
            onset=[0.0, 2.0, 4.0],
            duration=[float(mne_raw.times[-1]), 0.0, 0.0],
            description=["BAD_motion", "left", "right"],
        )
    )
    fif_path = tmp_path / "all-dropped-command_raw.fif"
    mne_raw.save(fif_path, overwrite=True, verbose=False)

    service = ApplicationService()
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

    try:
        scanned = service.execute(
            ScanSourceCommand(source_path=str(fif_path), source_hint="file")
        )
        previewed = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(fif_path)],
                    "label_carrier": "embedded_events",
                    "class_map": {"left": "left", "right": "right"},
                    "internal_event_selection": {
                        "label_event_codes": ["left", "right"],
                        "class_map": {"left": "left", "right": "right"},
                    },
                }
            )
        )
        validated = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert scanned.ok, scanned.message
        assert previewed.ok, previewed.message
        assert validated.ok, validated.message
        assert applied.ok, applied.message
        assert applied.state.interpretation.epoch_handoff["ready"] is True
        assert set(
            applied.state.interpretation.epoch_handoff["default_epoch_events"]
        ) == {"left", "right"}

        original_preprocessed = service.study.preprocessed_data_list
        raw = original_preprocessed[0]
        loaded_mne_raw = raw.get_mne()
        result = service.execute(
            CreateEpochCommand(
                t_min=-0.1,
                t_max=0.5,
                event_ids=["left", "right"],
            )
        )

        assert result.failed is True
        assert result.error_type is ErrorType.VALIDATION
        assert "No usable epochs remain" in result.message
        assert service.study.preprocessed_data_list is original_preprocessed
        assert service.study.preprocessed_data_list[0] is raw
        assert raw.get_mne() is loaded_mne_raw
        assert service.study.epoch_data is None
        assert service.study.is_locked() is False
    finally:
        service.close()
