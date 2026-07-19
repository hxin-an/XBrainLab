"""Format-semantic normalization regressions."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import mne
import numpy as np

from XBrainLab.backend.event_semantics import mark_gdf_rejected_trials


def test_gdf_rejected_trial_normalization_preserves_scoped_annotations() -> None:
    annotations = mne.Annotations(
        onset=[1.25, 4.5, 8.0],
        duration=[0.75, 1.5, 0.0],
        description=["Stimulus/S 1023", "769", "note"],
        orig_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ch_names=[("C3",), ("C4", "Cz"), ()],
    )
    mne_data = SimpleNamespace(annotations=annotations)
    mne_data.set_annotations = lambda value: setattr(mne_data, "annotations", value)
    data = SimpleNamespace(
        get_filepath=lambda: "/data/subject.gdf",
        get_mne=lambda: mne_data,
    )

    changed = mark_gdf_rejected_trials(data)

    assert changed is True
    normalized = mne_data.annotations
    np.testing.assert_array_equal(normalized.onset, annotations.onset)
    np.testing.assert_array_equal(normalized.duration, annotations.duration)
    assert normalized.orig_time == annotations.orig_time
    assert normalized.ch_names.tolist() == annotations.ch_names.tolist()
    assert normalized.description.tolist() == ["BAD_rejected_trial", "769", "note"]
