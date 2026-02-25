"""Event loader module for importing and aligning event/label data with raw EEG."""

from __future__ import annotations

from collections import Counter

import mne
import numpy as np

from XBrainLab.backend.utils.logger import logger

from ..utils import validate_type
from .raw import Raw


class EventLoader:
    """Loader for creating and applying event data to a raw EEG recording.

    Supports two modes:

    - **Sequence Mode**: Labels are a flat array of event codes aligned with
      EEG triggers by order.
    - **Timestamp Mode**: Labels are dicts with ``onset``, ``label``, and
      ``duration`` keys, converted to MNE ``Annotations``.

    Attributes:
        raw: The raw data object to attach events to.
        label_list: Loaded labels — either an array of event codes
            (Sequence Mode) or a list of timestamp dicts (Timestamp Mode).
        events: Event array in MNE format ``(n_events, 3)`` after creation.
        event_id: Event ID mapping ``{name: int}`` after creation.
        annotations: MNE Annotations object for Timestamp Mode.
    """

    def __init__(self, raw: Raw):
        """Initialize the EventLoader.

        Args:
            raw: Raw data object to load events into.
        """
        validate_type(raw, Raw, "raw")
        self.raw = raw
        self.label_list = None
        self.events = None
        self.event_id = None
        self.annotations = None

    def smart_filter(self, target_count: int) -> list[int]:
        """Suggest event IDs whose count best matches a target trial count.

        Uses a simple closest-count heuristic over the raw data's event IDs.

        Args:
            target_count: Desired number of trials.

        Returns:
            List containing the single best-matching event ID, or empty
            if no events exist.
        """
        if not self.raw.has_event():
            return []

        events, _ = self.raw.get_event_list()
        # Count occurrences of each event ID
        counts = Counter(events[:, -1])

        # Simple heuristic: Find single ID with closest count
        best_id = None
        min_diff = float("inf")

        for eid, count in counts.items():
            diff = abs(count - target_count)
            if diff < min_diff:
                min_diff = diff
                best_id = eid

        # TODO: Implement more complex subset sum if needed (e.g. Left + Right = Total)
        # For now, return the single best match
        if best_id is not None:
            return [best_id]
        return []

    def align_sequence(
        self, seq_eeg: list[int], seq_label: list[int]
    ) -> tuple[list[int], list[int]]:
        """Align EEG trigger sequence with label sequence.

        Currently uses simple truncation to the shorter sequence length.
        Full LCS/DTW alignment may be implemented in the future.

        Args:
            seq_eeg: List of EEG trigger indices or codes.
            seq_label: List of label indices or codes.

        Returns:
            Tuple of (eeg_indices, label_indices) representing matched
            positions in both sequences.
        """
        n = len(seq_eeg)
        m = len(seq_label)

        # If perfect match in count, assume 1-to-1 (optimization)
        if n == m:
            return list(range(n)), list(range(m))

        # DP Table for LCS
        # We are matching "items". But what defines a match?
        # In this context, we assume any EEG trigger *could* be any Label.
        # But we want to maximize the number of assignments while preserving order.
        # This is equivalent to finding the longest common subsequence if we
        # treat all items as "matchable".
        # But if all items match, LCS length is min(N, M).
        # And we just pick the first min(N, M)?
        # NO. If we have [A, B, C] and [A, X, B, C], we want to match A-A, B-B,
        # C-C.
        # But here we don't know "A" or "B". We only have "Trigger" and "Label".
        # Unless we use time intervals? But Sequence Mode has no time info for
        # labels.

        # If we have NO content info, we can only assume 1-to-1 mapping.
        # The only question is: do we skip elements from EEG (noise) or Labels
        # (missing)?
        # Usually EEG has extra triggers (noise).
        # So we assume N >= M.
        # We want to find M indices in EEG that "best fit".
        # Without time, "best fit" is undefined unless we assume uniform
        # distribution?
        # Or we just take the first M?

        # However, if we have *some* content info (e.g. trigger codes), we can
        # use it.
        # But `seq_eeg` passed here are just indices or codes?
        # The signature says List[int].
        # If they are codes, we can match codes!
        # But usually Labels are 1, 2, 3 and Triggers are 255, 255, 255 (start
        # trial).
        # So codes don't match.

        # If codes don't match, we can't use LCS based on content.
        # We can only use LCS if we have a "translation" or if we assume generic
        # matching.
        # If generic matching, we just match 1-to-1.

        # The spec says "LCS/DTW heuristic".
        # If we assume the user provided `selected_event_ids`, we filtered EEG to
        # only relevant triggers.
        # So `seq_eeg` contains only "Trial Start" triggers.
        # So they are all identical in meaning.
        # So we can't distinguish them by content.

        # Heuristic Alignment Strategy:
        # If N (triggers) != M (labels), we assume the first N items correspond to the
        # labels, or align based on count if best-id heuristic used.
        # This implementation defaults to simple list alignment/truncation as a robust
        # fallback.
        # as implementing full DTW on timestamps requires more changes.

        # Given the constraints and current state, simple truncation (or "first
        # N") is the most robust default when no content matching is possible.
        # LCS is only useful if we have a sequence of *different* labels and
        # *different* triggers that should correspond.
        # e.g. EEG: [1, 2, 1, 3], Label: [A, B, A, C]. Map 1->A, 2->B, 3->C.
        # Then we can align [1, 2, 1, 3] with [A, B, A, C].
        # But here we usually map "Trigger 255" -> "Label X".
        # So EEG is [255, 255, 255, 255]. Label is [A, B, A, C].
        # We can't align.

        # So, I will stick to the current logic (Truncation) but clean up the code
        # and ensure `align_sequence` is actually used.

        limit = min(n, m)
        return list(range(limit)), list(range(limit))

    def create_event(
        self,
        event_name_map: dict[int, str],
        selected_event_ids: list[int] | None = None,
    ) -> tuple[np.ndarray | None, dict[str, int] | None]:
        """Create event array and event ID mapping from loaded labels.

        Dispatches to Timestamp Mode or Sequence Mode based on the format
        of ``label_list``.

        Args:
            event_name_map: Mapping from numeric event codes to event names.
            selected_event_ids: List of EEG event IDs to filter triggers
                by before alignment (Sequence Mode only).

        Returns:
            Tuple of ``(events, event_id)`` where events is an
            ``(n_events, 3)`` array and event_id is ``{name: int}``,
            or ``(None, None)`` on failure.

        Raises:
            ValueError: If no labels have been loaded, if the raw data has
                no events for sequence alignment, or if an event name is empty.
        """
        if self.label_list is None:
            raise ValueError("No label has been loaded.")

        # --- Timestamp Mode ---
        if (
            isinstance(self.label_list, list)
            and len(self.label_list) > 0
            and isinstance(self.label_list[0], dict)
        ):
            # List of dicts: {'onset': ..., 'label': ..., 'duration': ...}
            onsets = []
            durations = []
            descriptions = []

            for item in self.label_list:
                onsets.append(item["onset"])
                durations.append(item["duration"])
                descriptions.append(str(item["label"]))

            # Create Annotations
            self.annotations = mne.Annotations(
                onset=onsets, duration=durations, description=descriptions
            )
            self.raw.get_mne().set_annotations(self.annotations)

            try:
                events, event_id = mne.events_from_annotations(
                    self.raw.get_mne(), event_id=None
                )
                self.events = events
                self.event_id = event_id
            except Exception as e:
                logger.warning(f"Could not convert annotations to events: {e}")
                return None, None
            return events, event_id

        # --- Sequence Mode ---
        else:
            # label_list is ndarray or list of ints
            labels = np.array(self.label_list)
            if labels.ndim > 1 and labels.shape[1] == 3:
                # Already in MNE format (e.g. from GDF)
                events = labels
                event_id = {
                    event_name_map.get(i, str(i)): i for i in np.unique(events[:, -1])
                }
                self.events = events
                self.event_id = event_id
                return events, event_id

            # Pure Sequence of Labels
            labels = labels.flatten()

            # Get EEG Triggers
            if not self.raw.has_event():
                raise ValueError("Raw data has no events for sequence alignment.")

            eeg_events, _ = self.raw.get_event_list()

            # Filter EEG Triggers
            if selected_event_ids is not None:
                mask = np.isin(eeg_events[:, -1], selected_event_ids)
                filtered_eeg_events = eeg_events[mask]
            else:
                filtered_eeg_events = eeg_events

            # Align
            # We pass indices to align_sequence (dummy for now as we don't use content)
            eeg_indices, label_indices = self.align_sequence(
                list(range(len(filtered_eeg_events))), list(range(len(labels)))
            )

            if len(eeg_indices) != len(labels):
                logger.warning(
                    f"Alignment truncated: EEG={len(filtered_eeg_events)}, "
                    f"Label={len(labels)} -> {len(eeg_indices)} matches."
                )

            # Create new events
            count = len(eeg_indices)
            new_events = np.zeros((count, 3), dtype=int)

            # Use aligned indices
            # filtered_eeg_events[eeg_indices] gives the matched EEG events
            # labels[label_indices] gives the matched labels

            # Note: eeg_indices and label_indices are lists of indices into the
            # respective arrays
            new_events[:, 0] = filtered_eeg_events[eeg_indices, 0]  # Timestamps
            new_events[:, 1] = filtered_eeg_events[eeg_indices, 1]  # Previous val
            new_events[:, -1] = labels[label_indices]  # New Labels

            # Create Event ID map
            unique_labels = np.unique(new_events[:, -1])
            new_event_id = {}
            for lbl in unique_labels:
                name = event_name_map.get(lbl, str(lbl))
                if not name.strip():
                    raise ValueError("Event name cannot be empty.")
                new_event_id[name] = int(lbl)

            self.events = new_events
            self.event_id = new_event_id
            return new_events, new_event_id

    def apply(self) -> None:
        """Apply the loaded event data to the raw data.

        Raises:
            ValueError: If no label has been loaded.
        """
        if self.annotations:
            self.raw.get_mne().set_annotations(self.annotations)
            # Also set events if generated
            if self.events is not None:
                self.raw.set_event(self.events, self.event_id)
        elif self.events is not None and self.event_id is not None:
            self.raw.set_event(self.events, self.event_id)
        else:
            raise ValueError("No label/events generated to apply.")
