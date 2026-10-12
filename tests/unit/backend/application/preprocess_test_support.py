"""Real EEG fixtures shared by command-boundary and session tests."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.load_data.raw import Raw


def _minimal_raw(
    filepath: Path,
    *,
    sfreq: float = 100.0,
    duration_seconds: float = 5.0,
) -> Raw:
    sample_count = max(1, round(sfreq * duration_seconds))
    return Raw(
        str(filepath),
        mne.io.RawArray(
            np.zeros((1, sample_count)),
            mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg"),
            verbose="ERROR",
        ),
    )


def _write_reviewed_epoch_fixture(
    path: Path,
    channel_names: tuple[str, ...] = ("Cz",),
    event_rows: np.ndarray | None = None,
    event_desc: dict[int, str] | None = None,
) -> None:
    """Write one real FIF recording accepted by the interpretation workflow."""
    sfreq = 100.0
    raw = mne.io.RawArray(
        np.zeros((len(channel_names), 600)),
        mne.create_info(list(channel_names), sfreq=sfreq, ch_types="eeg"),
        verbose="ERROR",
    )
    events = (
        np.asarray(event_rows, dtype=int)
        if event_rows is not None
        else np.asarray(
            [
                [100, 0, 1],
                [250, 0, 2],
                [400, 0, 1],
            ],
            dtype=int,
        )
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc=event_desc or {1: "left", 2: "right"},
        )
    )
    raw.save(path, overwrite=True, verbose="ERROR")


def _apply_reviewed_epoch_fixture(
    service: ApplicationService,
    path: Path,
    additional_paths: tuple[Path, ...] = (),
    *,
    internal_event_codes: tuple[str, ...] = ("left", "right"),
    class_map: dict[str, str] | None = None,
) -> None:
    """Run the public interpretation commands needed for epoch admission."""
    selected_paths = (path, *additional_paths)
    selection_class_map = class_map or {"left": "left", "right": "right"}
    reviewed_class_map = class_map or {"1": "left", "2": "right"}
    assert service.execute(
        ScanSourceCommand(
            source_path=str(path.parent) if additional_paths else str(path)
        )
    ).ok
    assert service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(item) for item in selected_paths],
                "internal_event_selection": {
                    "label_event_codes": list(internal_event_codes),
                    "class_map": selection_class_map,
                },
                "label_carrier": "embedded_events",
                "event_roles": {"internal_events": "class cue"},
                "class_map": reviewed_class_map,
            },
        )
    ).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    assert service.execute(ApplyInterpretationCommand(confirmed=True)).ok
