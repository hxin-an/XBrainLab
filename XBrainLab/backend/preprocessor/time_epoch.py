import mne
import numpy as np

from ..load_data import Raw
from .base import PreprocessBase


class TimeEpoch(PreprocessBase):
    """Class for epoching data by event markers

    Input:
        baseline: Baseline removal time interval
        selected_event_names: List of event names to be kept
        tmin: Start time before event marker
        tmax: End time after event marker
    """

    def check_data(self):
        super().check_data()
        for preprocessed_data in self.preprocessed_data_list:
            if not preprocessed_data.is_raw():
                raise ValueError("Only raw data can be epoched, got epochs")
            _, event_id = preprocessed_data.get_event_list()
            if not event_id:
                raise ValueError(
                    f"No event markers found for {preprocessed_data.get_filename()}"
                )

    def get_preprocess_desc(
        self, baseline: list, selected_event_names: list, tmin: float, tmax: float
    ):
        return f"Epoching {tmin} ~ {tmax} by event ({baseline} baseline)"

    def _data_preprocess(
        self,
        preprocessed_data: Raw,
        baseline: list,
        selected_event_names: list,
        tmin: float,
        tmax: float,
    ):
        raw_events, raw_event_id = preprocessed_data.get_event_list()

        selected_event_id = {}
        if selected_event_names is None:
            # If None, select all available events
            selected_event_id = raw_event_id.copy()
        else:
            for event_name in selected_event_names:
                if event_name in raw_event_id:
                    selected_event_id[event_name] = raw_event_id[event_name]

        selection_mask = np.zeros(raw_events.shape[0], dtype=bool)
        for event_id in selected_event_id.values():
            selection_mask = np.logical_or(
                selection_mask, raw_events[:, -1] == event_id
            )
        selected_events = raw_events[selection_mask]

        if len(selected_events) == 0:
            available = list(raw_event_id.keys())
            raise ValueError(
                f"No event markers found. Selected: {selected_event_names}. "
                f"Available: {available}"
            )

        if not preprocessed_data.is_raw():
            raise ValueError(
                "Data is already epoched. Cannot perform TimeEpoch on epoched data."
            )

        data = mne.Epochs(
            preprocessed_data.get_mne(),
            selected_events,
            event_id=selected_event_id,
            tmin=tmin,
            tmax=tmax,
            baseline=baseline,
            preload=True,
            event_repeated="drop",
        )

        # FIX: Clear raw events to prevent set_mne from overwriting the correct
        # epoch events with the original (larger) raw events list.
        preprocessed_data.raw_events = None
        preprocessed_data.raw_event_id = None

        preprocessed_data.set_mne(data)
