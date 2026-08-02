"""Deterministic EEG fixture shared by local training walkthroughs."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np


def write_training_ready_raw_fif(destination: Path) -> Path:
    """Write balanced events with enough duration for EEGNet and split coverage."""
    path = destination.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    sfreq = 128
    ch_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(43).normal(size=(len(ch_names), sfreq * 25))
    raw = mne.io.RawArray(data, info)
    events = np.asarray(
        [
            [sfreq * second, 0, 1 if index % 2 == 0 else 2]
            for index, second in enumerate(range(1, 24, 2))
        ],
        dtype=int,
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        ),
    )
    raw.save(path, overwrite=True)
    return path
