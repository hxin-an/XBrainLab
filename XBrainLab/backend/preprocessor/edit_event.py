"""Preprocessors for editing EEG event names and IDs."""

from __future__ import annotations

import numpy as np

from ..load_data import Raw
from ..utils.logger import logger
from .base import PreprocessBase


class EditEventName(PreprocessBase):
    """Renames event labels in epoched EEG data.

    Maps existing event names to new names. This is useful for
    standardising event labels across different recording sessions or
    merging semantically equivalent event categories.
    """

    def check_data(self):
        """Validates that data is epoched.

        Raises:
            ValueError: If any data instance is raw (not epoched).
        """
        super().check_data()
        for preprocessed_data in self.preprocessed_data_list:
            if preprocessed_data.is_raw():
                raise ValueError("Event name can only be edited for epoched data")

    def get_preprocess_desc(self, new_event_name: dict[str, str]):
        """Returns a description of the event name editing step.

        Args:
            new_event_name: Mapping from old event names to new event names.

        Returns:
            A string describing how many event names were updated.
        """
        diff = np.sum(
            np.array(list(new_event_name.values()))
            != np.array(list(new_event_name.keys()))
        )
        return f"Update {diff} event names"

    def _data_preprocess(self, preprocessed_data: Raw, new_event_name: dict[str, str]):
        """Renames events in a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            new_event_name: Mapping from old event names to new event names.

        Raises:
            ValueError: If a specified event name is not found, no names were
                changed, or the renaming would create duplicate names.
        """
        # update parent event name to event id dict
        events, event_id = preprocessed_data.get_event_list()
        for k in new_event_name:
            if k not in event_id:
                raise ValueError(f"New event name '{k}' not found in old event name.")
        if list(new_event_name.keys()) == list(new_event_name.values()):
            raise ValueError("No Event name updated.")

        new_event_id = {}
        for e in event_id:
            new_name = new_event_name.get(e, e)
            if new_name in new_event_id:
                raise ValueError(f"Duplicate event name: {new_name}")
            new_event_id[new_name] = event_id[e]

        preprocessed_data.set_event(events, new_event_id)


class EditEventId(PreprocessBase):
    """Modifies event numeric IDs in epoched EEG data.

    Reassigns the integer event codes associated with each event label.
    When multiple event names are mapped to the same ID, their labels are
    automatically merged.
    """

    def check_data(self):
        """Validates that data is epoched.

        Raises:
            ValueError: If any data instance is raw (not epoched).
        """
        super().check_data()
        for preprocessed_data in self.preprocessed_data_list:
            if preprocessed_data.is_raw():
                raise ValueError("Event id can only be edited for epoched data")

    def get_preprocess_desc(self, new_event_ids: dict[str, int]):
        """Returns a description of the event ID editing step.

        Args:
            new_event_ids: Mapping from event names to new integer IDs.

        Returns:
            A string indicating that event IDs were updated.
        """
        return "Update event ids"

    def _data_preprocess(self, preprocessed_data: Raw, new_event_ids: dict[str, int]):
        """Reassigns event IDs in a single data instance.

        Args:
            preprocessed_data: The data instance to preprocess.
            new_event_ids: Mapping from event names to new integer IDs.

        Raises:
            ValueError: If no event IDs were actually changed.
        """
        # update parent event data
        events, event_id = preprocessed_data.get_event_list()

        has_change = False
        for name, new_id in new_event_ids.items():
            if name in event_id and event_id[name] != new_id:
                has_change = True
                break

        if not has_change:
            raise ValueError("No Event Id updated.")

        new_events, new_event_id = events.copy(), {}
        if len(np.unique(list(new_event_ids.keys()))) != len(
            np.unique(list(new_event_ids.values()))
        ):
            logger.warning(
                "Updated with duplicate new event IDs. "
                "Event names of same event ID are automatically merged."
            )
            uq, cnt = np.unique(
                list(new_event_ids.values()), return_counts=True
            )  # [1,2,3], [1,1,2]
            dup = uq[cnt > 1]  # 3
            event_id_dup: dict[int, list] = {v: [] for v in dup}  # 3: [768_2, 768_3]
            for k, v in event_id.items():
                if new_event_ids[k] not in dup:
                    new_event_id[k] = new_event_ids[k]
                else:
                    event_id_dup[new_event_ids[k]].append(k)

                new_events[np.where(events[:, -1] == v), -1] = new_event_ids[k]
            event_id_merged = {
                k: "/".join(v) for k, v in event_id_dup.items()
            }  # 3: 768_2/768_3
            new_event_id.update({v: k for k, v in event_id_merged.items()})
        else:
            for k, v in event_id.items():
                new_id = new_event_ids.get(k, v)
                new_event_id[k] = new_id
                new_events[np.where(events[:, -1] == v), -1] = new_id

        preprocessed_data.set_event(new_events, new_event_id)
