"""Event loader module for importing and aligning event/label data with raw EEG."""

from __future__ import annotations

import contextlib
import math
import warnings
from collections import Counter
from dataclasses import dataclass
from typing import Any

import mne
import numpy as np

from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.utils import validate_type
from XBrainLab.backend.utils.logger import logger

_MNE_EXCLUDED_CLASS_PREFIXES = ("bad", "edge")
_MNE_ANNOTATION_TIME_TOLERANCE_SECONDS = 1e-6


def _require_equal_annotation_counts(
    applied: mne.Annotations,
    expected: mne.Annotations,
) -> None:
    if len(applied) != len(expected):
        raise ValueError(
            "MNE timestamp annotation commit produced a row-count mismatch.",
        )


@dataclass(frozen=True)
class _TimestampRow:
    """One normalized external timestamp row before MNE attachment."""

    source_index: int
    onset: float
    duration: float
    raw_label: str
    description: str
    ch_names: tuple[str, ...]
    use_as_class: bool

    def annotation_key(self) -> tuple[float, float, str, tuple[str, ...]]:
        return _annotation_key(
            onset=self.onset,
            duration=self.duration,
            description=self.description,
            ch_names=self.ch_names,
        )

    def exact_key(self) -> tuple[float, float, str, tuple[str, ...], str, bool]:
        return (*self.annotation_key(), self.raw_label, self.use_as_class)


def _normalize_label_value(value: Any) -> Any:
    """Convert NumPy scalars to Python scalars for robust dict/set usage."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def _coerce_event_code(value: Any) -> int | None:
    """Preserve integer-like labels as event IDs when possible."""
    value = _normalize_label_value(value)

    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)

    if isinstance(value, (float, np.floating)):
        float_value = float(value)
        if float_value.is_integer():
            return int(float_value)
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            with contextlib.suppress(ValueError):
                return int(stripped)

    return None


def _annotation_key(
    *,
    onset: float,
    duration: float,
    description: str,
    ch_names: tuple[str, ...],
) -> tuple[float, float, str, tuple[str, ...]]:
    return (
        round(float(onset), 12),
        round(float(duration), 12),
        str(description),
        tuple(ch_names),
    )


def _merge_external_annotations(
    *,
    existing: mne.Annotations,
    external: mne.Annotations,
) -> mne.Annotations:
    """Merge external labels with existing acquisition annotations.

    External labels are authoritative for the generated event array, while all
    existing annotations remain available as recording context. Exact duplicate
    reviewed rows have already been removed before this boundary, so every
    external annotation must remain even when two distinct source rows normalize
    to the same MNE description. Existing acquisition annotations are de-duplicated
    against those external annotation keys. Rows sort by onset with external
    labels first, then duration, description, channel names, and original position.
    """
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[float, float, str, tuple[str, ...]]] = set()

    for index, (onset, duration, description) in enumerate(
        zip(external.onset, external.duration, external.description, strict=True)
    ):
        ch_names = tuple(str(item) for item in external.ch_names[index])
        key = _annotation_key(
            onset=float(onset),
            duration=float(duration),
            description=str(description),
            ch_names=ch_names,
        )
        seen_keys.add(key)
        rows.append(
            {
                "onset": float(onset),
                "duration": float(duration),
                "description": str(description),
                "ch_names": ch_names,
                "source_rank": 0,
                "source_index": index,
            }
        )

    for index, (onset, duration, description) in enumerate(
        zip(existing.onset, existing.duration, existing.description, strict=True)
    ):
        ch_names = tuple(str(item) for item in existing.ch_names[index])
        key = _annotation_key(
            onset=float(onset),
            duration=float(duration),
            description=str(description),
            ch_names=ch_names,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(
            {
                "onset": float(onset),
                "duration": float(duration),
                "description": str(description),
                "ch_names": ch_names,
                "source_rank": 1,
                "source_index": index,
            }
        )

    rows.sort(
        key=lambda row: (
            row["onset"],
            row["source_rank"],
            row["duration"],
            row["description"],
            row["ch_names"],
            row["source_index"],
        )
    )
    orig_time = existing.orig_time or external.orig_time
    return mne.Annotations(
        onset=[row["onset"] for row in rows],
        duration=[row["duration"] for row in rows],
        description=[row["description"] for row in rows],
        orig_time=orig_time,
        ch_names=[row["ch_names"] for row in rows],
    )


def _annotation_snapshot(
    raw_mne: Any,
    *,
    fallback: mne.Annotations | None = None,
) -> mne.Annotations:
    """Copy attached MNE annotations, or a known-safe fallback for adapters."""
    annotations = getattr(raw_mne, "annotations", None)
    if isinstance(annotations, mne.Annotations):
        return annotations.copy()
    if fallback is not None:
        return fallback.copy()
    return mne.Annotations([], [], [])


def _set_attached_annotations(raw_mne: Any, annotations: mne.Annotations) -> None:
    """Attach an annotation snapshot without shifting first-sample onsets twice."""
    payload = annotations
    first_time = float(getattr(raw_mne, "first_time", 0.0) or 0.0)
    if annotations.orig_time is None and first_time:
        payload = mne.Annotations(
            onset=np.asarray(annotations.onset, dtype=float) - first_time,
            duration=annotations.duration,
            description=annotations.description,
            orig_time=None,
            ch_names=annotations.ch_names,
        )
    raw_mne.set_annotations(payload)


def _timestamp_description(
    item: dict[str, Any],
    *,
    mapped_label: Any,
) -> tuple[str, bool]:
    raw_label = str(item.get("label") or "").strip()
    use_as_class_value = item.get("use_as_class", True)
    if not isinstance(use_as_class_value, bool):
        raise ValueError("Timestamp label row has no explicit class-use decision.")
    use_as_class = use_as_class_value
    role = str(item.get("role") or "unknown").strip().casefold()
    if use_as_class:
        description = str(item.get("class_name") or mapped_label).strip()
        if not description:
            raise ValueError("Timestamp class description cannot be empty.")
        if description.casefold().startswith(_MNE_EXCLUDED_CLASS_PREFIXES):
            raise ValueError(
                "MNE excludes class description prefixes Bad* and Edge*: "
                f"{description}.",
            )
        return description, True
    token = str(item.get("description") or raw_label or mapped_label).strip()
    if not token:
        raise ValueError("Timestamp annotation description cannot be empty.")
    if role == "artifact":
        return f"BAD_artifact/{token}", False
    if role == "boundary":
        return f"BAD_boundary/{token}", False
    semantic_role = role if role not in {"", "unknown"} else "annotation"
    return f"{semantic_role}/{token}", False


def _timestamp_channel_names(item: dict[str, Any], raw_mne: Any) -> tuple[str, ...]:
    raw_names = item.get("ch_names", ())
    if raw_names in (None, ""):
        return ()
    names: tuple[str, ...]
    if isinstance(raw_names, str):
        names = (raw_names.strip(),) if raw_names.strip() else ()
    elif isinstance(raw_names, (list, tuple, set)):
        names = tuple(str(name).strip() for name in raw_names if str(name).strip())
    else:
        raise ValueError("Timestamp annotation channel names must be a string or list.")
    available = {str(name) for name in getattr(raw_mne, "ch_names", [])}
    missing = [name for name in names if name not in available]
    if missing:
        raise ValueError(
            "Timestamp annotation references unknown EEG channel(s): "
            + ", ".join(missing)
            + ".",
        )
    return names


def _finite_timestamp_number(value: Any, *, field: str, row: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Timestamp label row {row} has non-numeric {field}.") from exc
    if not math.isfinite(result):
        raise ValueError(f"Timestamp label row {row} has non-finite {field}.")
    return result


def _normalize_timestamp_rows(
    label_list: list[Any],
    *,
    event_name_map: dict[Any, str],
    raw_mne: Any,
) -> list[_TimestampRow]:
    sfreq = float(raw_mne.info["sfreq"])
    n_times = int(getattr(raw_mne, "n_times", 0) or 0)
    if sfreq <= 0 or n_times <= 0:
        raise ValueError(
            "Stored EEG sample bounds are unavailable for timestamp labels."
        )
    recording_duration = n_times / sfreq
    last_sample_time = (n_times - 1) / sfreq
    tolerance = max(1e-12, 1.0 / sfreq * 1e-9)
    rows: list[_TimestampRow] = []
    for source_index, raw_item in enumerate(label_list, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"Timestamp label row {source_index} is not a row record.")
        item = dict(raw_item)
        onset = _finite_timestamp_number(
            item.get("onset"),
            field="onset",
            row=source_index,
        )
        duration = _finite_timestamp_number(
            item.get("duration", 0.0),
            field="duration",
            row=source_index,
        )
        if (
            onset < 0
            or duration < 0
            or onset > last_sample_time + tolerance
            or onset + duration > recording_duration + tolerance
        ):
            raise ValueError(
                f"Timestamp label row {source_index} is outside the stored EEG range.",
            )
        raw_label_value = _normalize_label_value(item.get("label"))
        raw_label = str(raw_label_value).strip()
        if not raw_label:
            raise ValueError(f"Timestamp label row {source_index} has no label value.")
        mapped_label = event_name_map.get(
            raw_label_value,
            event_name_map.get(raw_label, raw_label_value),
        )
        description, use_as_class = _timestamp_description(
            item,
            mapped_label=mapped_label,
        )
        rows.append(
            _TimestampRow(
                source_index=source_index,
                onset=onset,
                duration=duration,
                raw_label=raw_label,
                description=description,
                ch_names=_timestamp_channel_names(item, raw_mne),
                use_as_class=use_as_class,
            )
        )

    unique_rows: list[_TimestampRow] = []
    seen: set[tuple[float, float, str, tuple[str, ...], str, bool]] = set()
    for row in rows:
        key = row.exact_key()
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    class_rows_by_sample: dict[int, list[_TimestampRow]] = {}
    for row in unique_rows:
        if not row.use_as_class:
            continue
        relative_sample = int(raw_mne.time_as_index([row.onset], use_rounding=True)[0])
        absolute_sample = int(raw_mne.first_samp) + relative_sample
        if absolute_sample < int(raw_mne.first_samp) or absolute_sample > int(
            raw_mne.last_samp
        ):
            raise ValueError(
                f"Timestamp label row {row.source_index} is outside the stored EEG "
                "range.",
            )
        class_rows_by_sample.setdefault(absolute_sample, []).append(row)
    for sample, sample_rows in class_rows_by_sample.items():
        if len(sample_rows) > 1:
            sources = ", ".join(str(row.source_index) for row in sample_rows)
            raise ValueError(
                "Ambiguous class placement at EEG sample "
                f"{sample}: timestamp rows {sources} resolve to the same sample.",
            )
    return unique_rows


def _attached_relative_annotation_rows(
    annotations: mne.Annotations,
    *,
    first_time: float,
) -> list[tuple[str, tuple[str, ...], float, float]]:
    return sorted(
        [
            (
                str(description),
                tuple(str(name) for name in annotations.ch_names[index]),
                float(onset) - first_time,
                float(duration),
            )
            for index, (onset, duration, description) in enumerate(
                zip(
                    annotations.onset,
                    annotations.duration,
                    annotations.description,
                    strict=True,
                )
            )
        ]
    )


def _reviewed_annotation_rows(
    rows: list[_TimestampRow],
) -> list[tuple[str, tuple[str, ...], float, float]]:
    return sorted(
        (row.description, row.ch_names, row.onset, row.duration) for row in rows
    )


def _require_matching_reviewed_annotations(
    applied: mne.Annotations,
    rows: list[_TimestampRow],
    *,
    first_time: float,
) -> None:
    """Verify MNE retained every reviewed row and its semantic placement.

    MNE stores annotation timestamps at microsecond precision. BIDS event
    onsets derived from a sampling grid can therefore move by a fraction of a
    microsecond when attached to a Raw object. Counts and semantic fields stay
    exact; only onset and duration use this bounded storage tolerance.
    """
    if len(applied) != len(rows):
        raise ValueError(
            "MNE timestamp annotation output did not match every reviewed row.",
        )
    expected = _reviewed_annotation_rows(rows)
    produced = _attached_relative_annotation_rows(
        applied,
        first_time=first_time,
    )
    for expected_row, produced_row in zip(expected, produced, strict=True):
        expected_description, expected_channels, expected_onset, expected_duration = (
            expected_row
        )
        produced_description, produced_channels, produced_onset, produced_duration = (
            produced_row
        )
        if (
            produced_description != expected_description
            or produced_channels != expected_channels
            or not math.isclose(
                produced_onset,
                expected_onset,
                rel_tol=0.0,
                abs_tol=_MNE_ANNOTATION_TIME_TOLERANCE_SECONDS,
            )
            or not math.isclose(
                produced_duration,
                expected_duration,
                rel_tol=0.0,
                abs_tol=_MNE_ANNOTATION_TIME_TOLERANCE_SECONDS,
            )
        ):
            raise ValueError(
                "MNE timestamp annotation output did not match every reviewed row.",
            )


def _prepare_external_annotations(
    raw_mne: Any,
    rows: list[_TimestampRow],
) -> mne.Annotations:
    existing = _annotation_snapshot(raw_mne)
    external = mne.Annotations(
        onset=[row.onset for row in rows],
        duration=[row.duration for row in rows],
        description=[row.description for row in rows],
        ch_names=[row.ch_names for row in rows],
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            raw_mne.set_annotations(external)
        applied = _annotation_snapshot(raw_mne, fallback=external)
        _require_matching_reviewed_annotations(
            applied,
            first_time=float(getattr(raw_mne, "first_time", 0.0) or 0.0),
            rows=rows,
        )
        return applied
    finally:
        _set_attached_annotations(raw_mne, existing)


def _events_from_timestamp_rows(
    raw_mne: Any,
    rows: list[_TimestampRow],
) -> tuple[np.ndarray, dict[str, int]]:
    class_rows = [row for row in rows if row.use_as_class]
    descriptions = sorted({row.description for row in class_rows})
    event_id = {description: index for index, description in enumerate(descriptions, 1)}
    event_rows = [
        [
            int(raw_mne.first_samp)
            + int(raw_mne.time_as_index([row.onset], use_rounding=True)[0]),
            0,
            event_id[row.description],
        ]
        for row in class_rows
    ]
    event_rows.sort(key=lambda row: (row[0], row[2]))
    events = np.asarray(event_rows, dtype=int).reshape((-1, 3))
    if len(events) != len(class_rows):
        raise ValueError(
            "MNE timestamp class event output did not match every reviewed class row.",
        )
    return events, event_id


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
        self.label_list: Any | None = None
        self.events: np.ndarray | None = None
        self.event_id: dict[str, int] | None = None
        self.annotations: mne.Annotations | None = None
        self._external_annotations: mne.Annotations | None = None

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

        # Returns the single best matching event ID
        if best_id is not None:
            return [best_id]
        return []

    def align_sequence(
        self,
        seq_eeg: list[int],
        seq_label: list[int],
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
        event_name_map: dict[Any, str],
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
            raw_mne = self.raw.get_mne()
            existing_annotations = _annotation_snapshot(raw_mne)
            timestamp_rows = _normalize_timestamp_rows(
                self.label_list,
                event_name_map=event_name_map,
                raw_mne=raw_mne,
            )
            applied_external_annotations = _prepare_external_annotations(
                raw_mne,
                timestamp_rows,
            )
            events, event_id = _events_from_timestamp_rows(raw_mne, timestamp_rows)
            merged_annotations = _merge_external_annotations(
                existing=existing_annotations,
                external=applied_external_annotations,
            )

            self.events = events
            self.event_id = event_id
            self.annotations = merged_annotations
            self._external_annotations = applied_external_annotations
            return events, event_id

        # --- Sequence Mode ---
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
        if len(labels) == 0:
            raise ValueError("Loaded labels are empty.")

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
        if len(filtered_eeg_events) == 0:
            raise ValueError("No EEG events matched the selected event filter.")

        if len(filtered_eeg_events) != len(labels):
            raise ValueError(
                "Label count does not match selected EEG event count: "
                f"{len(labels)} label row(s), "
                f"{len(filtered_eeg_events)} selected EEG event(s).",
            )

        # Align
        # We pass indices to align_sequence (dummy for now as we don't use content)
        eeg_indices, label_indices = self.align_sequence(
            list(range(len(filtered_eeg_events))),
            list(range(len(labels))),
        )

        if len(eeg_indices) < len(filtered_eeg_events) or len(label_indices) < len(
            labels
        ):
            logger.warning(
                "Alignment truncated: EEG=%d, Label=%d -> %d matches.",
                len(filtered_eeg_events),
                len(labels),
                len(eeg_indices),
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
        aligned_labels = [_normalize_label_value(labels[idx]) for idx in label_indices]

        label_to_code: dict[Any, int] = {}
        code_to_name: dict[int, str] = {}
        used_codes: set[int] = set()
        next_code = 1

        for row_index, label in enumerate(aligned_labels):
            if label in label_to_code:
                code = label_to_code[label]
            else:
                preferred_code = _coerce_event_code(label)
                if preferred_code is not None and preferred_code not in used_codes:
                    code = preferred_code
                else:
                    while next_code in used_codes:
                        next_code += 1
                    code = next_code
                    next_code += 1

                label_to_code[label] = code
                used_codes.add(code)

                name = event_name_map.get(label, str(label))
                if not name.strip():
                    raise ValueError("Event name cannot be empty.")
                code_to_name[code] = name

            new_events[row_index, -1] = code

        new_event_id = {
            name: code
            for code, name in sorted(
                code_to_name.items(),
                key=lambda item: item[0],
            )
        }

        self.events = new_events
        self.event_id = new_event_id
        return new_events, new_event_id

    def apply(self) -> None:
        """Apply the loaded event data to the raw data.

        Raises:
            ValueError: If no label has been loaded.

        """
        if self.annotations is not None:
            raw_mne = self.raw.get_mne()
            current_annotations = _annotation_snapshot(raw_mne)
            previous_events = (
                self.raw.raw_events.copy() if self.raw.raw_events is not None else None
            )
            previous_event_id = (
                self.raw.raw_event_id.copy()
                if self.raw.raw_event_id is not None
                else None
            )
            external_annotations = (
                self._external_annotations
                if self._external_annotations is not None
                else self.annotations
            )
            merged_annotations = _merge_external_annotations(
                existing=current_annotations,
                external=external_annotations,
            )
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", RuntimeWarning)
                    _set_attached_annotations(raw_mne, merged_annotations)
                applied_annotations = _annotation_snapshot(
                    raw_mne,
                    fallback=merged_annotations,
                )
                _require_equal_annotation_counts(
                    applied_annotations,
                    merged_annotations,
                )
                self.annotations = applied_annotations
                if self.events is not None and self.event_id is not None:
                    self.raw.set_event(self.events, self.event_id)
            except Exception:
                with contextlib.suppress(Exception):
                    _set_attached_annotations(raw_mne, current_annotations)
                self.raw.raw_events = previous_events
                self.raw.raw_event_id = previous_event_id
                raise
        elif self.events is not None and self.event_id is not None:
            self.raw.set_event(self.events, self.event_id)
        else:
            raise ValueError("No label/events generated to apply.")
