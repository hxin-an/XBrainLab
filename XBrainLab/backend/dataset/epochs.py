"""Epochs module for converting Raw data into epoch arrays for splitting."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import mne
import numpy as np
import pandas as pd

from ..load_data import Raw
from ..utils import validate_list_type
from .option import SplitUnit


@dataclass(frozen=True)
class EpochWindowProvenance:
    """Source-recording sample interval represented by one epoch.

    ``source_recording_id`` is an opaque content or path fingerprint. The
    original source path and digest payload are never retained in this object.

    ``window_end_sample_exclusive`` makes adjacency unambiguous: two windows
    overlap only when ``max(start) < min(end)``.
    """

    source_recording_id: str
    event_sample: int
    window_start_sample: int
    window_end_sample_exclusive: int
    source_sfreq: float
    epoch_sfreq: float
    tmin_seconds: float
    tmax_seconds: float
    source_coordinates_verified: bool


MAX_TRIAL_SELECTION_EVIDENCE = 100
MAX_TRIAL_SELECTION_EVIDENCE_INDICES = 100
SOURCE_PATH_FINGERPRINT_PREFIX = "path-sha256:"
SOURCE_CONTENT_FINGERPRINT_PREFIX = "content-sha256:"
UNVERIFIED_SOURCE_FINGERPRINT_PREFIX = "unverified-wrapper-sha256:"
EPOCH_SOURCE_PROVENANCE_METADATA_COLUMN = "xbrainlab_source_coordinate_provenance_v1"
EPOCH_SOURCE_PROVENANCE_SCHEMA_VERSION = 1
EPOCH_SOURCE_PROVENANCE_ORIGIN = "xbrainlab_raw_event_source"
_XBRAINLAB_EVENT_EPOCH_HISTORY_MARKER = " by event ("
_XBRAINLAB_WINDOW_EPOCH_HISTORY_SUFFIX = " by sliding window"
_SHA256_HEX_LENGTH = 64


def is_opaque_source_recording_id(value: str) -> bool:
    """Return whether a source identity has a supported opaque format."""
    if not isinstance(value, str):
        return False
    for prefix in (
        SOURCE_CONTENT_FINGERPRINT_PREFIX,
        SOURCE_PATH_FINGERPRINT_PREFIX,
        UNVERIFIED_SOURCE_FINGERPRINT_PREFIX,
    ):
        if not value.startswith(prefix):
            continue
        digest = value.removeprefix(prefix)
        return len(digest) == _SHA256_HEX_LENGTH and all(
            character in "0123456789abcdef" for character in digest
        )
    return False


def _is_verified_source_recording_id(value: str) -> bool:
    return any(
        value.startswith(prefix)
        for prefix in (
            SOURCE_CONTENT_FINGERPRINT_PREFIX,
            SOURCE_PATH_FINGERPRINT_PREFIX,
        )
    ) and is_opaque_source_recording_id(value)


def _build_atomic_trial_groups(
    provenance: tuple[EpochWindowProvenance, ...],
) -> np.ndarray:
    """Build connected overlap components in source-recording coordinates."""
    group_ids = np.full(len(provenance), -1, dtype=int)
    by_source: dict[str, list[tuple[int, EpochWindowProvenance]]] = {}
    for index, item in enumerate(provenance):
        if item.source_coordinates_verified and is_opaque_source_recording_id(
            item.source_recording_id,
        ):
            by_source.setdefault(item.source_recording_id, []).append((index, item))

    next_group_id = 0
    for source_id in sorted(by_source):
        windows = sorted(
            by_source[source_id],
            key=lambda pair: (
                pair[1].window_start_sample,
                pair[1].window_end_sample_exclusive,
                pair[0],
            ),
        )
        component_end: int | None = None
        component_id = -1
        for index, item in windows:
            if component_end is None or item.window_start_sample >= component_end:
                component_id = next_group_id
                next_group_id += 1
                component_end = item.window_end_sample_exclusive
            else:
                component_end = max(
                    component_end,
                    item.window_end_sample_exclusive,
                )
            group_ids[index] = component_id

    # Unverified source coordinates cannot safely imply relationships. Keeping
    # each such epoch independent avoids fabricating overlap groups; the
    # trial-wise split audit blocks this provenance state.
    for index in np.flatnonzero(group_ids < 0):
        group_ids[index] = next_group_id
        next_group_id += 1
    return group_ids


def _unverified_source_recording_id(source_wrapper_index: int) -> str:
    digest = sha256(
        f"epoch-source-wrapper:{source_wrapper_index}".encode("ascii"),
    ).hexdigest()
    return f"{UNVERIFIED_SOURCE_FINGERPRINT_PREFIX}{digest}"


def _source_recording_id(
    preprocessed_data: Raw,
    *,
    source_wrapper_index: int,
) -> tuple[str, bool]:
    """Return the reviewed content identity or a canonical-path fallback."""
    fallback = _unverified_source_recording_id(source_wrapper_index)
    try:
        identity = preprocessed_data.get_source_content_identity()
    except (AttributeError, TypeError, ValueError):
        return fallback, False
    if isinstance(identity, dict) and identity.get("algorithm") == "sha256":
        digest = str(identity.get("sha256") or "").strip().lower()
        if len(digest) == _SHA256_HEX_LENGTH and all(
            character in "0123456789abcdef" for character in digest
        ):
            return f"{SOURCE_CONTENT_FINGERPRINT_PREFIX}{digest}", True

    filepath = preprocessed_data.get_filepath()
    if not filepath.strip():
        return fallback, False

    try:
        resolved = Path(filepath).expanduser().resolve(strict=False)
        if resolved.exists() and not resolved.is_file():
            return fallback, False
    except (OSError, RuntimeError, ValueError):
        return fallback, False

    canonical_path = os.path.normcase(os.path.normpath(str(resolved)))
    if not canonical_path:
        return fallback, False
    digest = sha256(canonical_path.encode("utf-8")).hexdigest()
    return f"{SOURCE_PATH_FINGERPRINT_PREFIX}{digest}", True


def _source_sampling_frequency(data: mne.BaseEpochs, epoch_sfreq: float) -> float:
    """Return one unambiguous source-coordinate sampling frequency."""
    raw_source_sfreq = getattr(data, "_raw_sfreq", None)
    if raw_source_sfreq is None:
        return epoch_sfreq
    try:
        values = np.asarray(raw_source_sfreq, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError("MNE source sampling frequency is not numeric") from exc
    if len(values) == 0:
        return epoch_sfreq
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("MNE source sampling frequency must be positive")
    source_sfreq = float(values[0])
    if not np.allclose(values, source_sfreq, rtol=0.0, atol=1e-12):
        raise ValueError(
            "MNE epochs contain multiple source sampling frequencies; "
            "source sample coordinates are ambiguous",
        )
    return source_sfreq


def _computed_epoch_window_provenance(
    preprocessed_data: Raw,
    data: mne.BaseEpochs,
    *,
    source_wrapper_index: int,
    source_coordinates_verified: bool,
) -> tuple[EpochWindowProvenance, ...]:
    """Translate MNE epoch timing into source-recording sample intervals."""
    events = np.asarray(data.events)
    times = np.asarray(data.times, dtype=float)
    if events.ndim != 2 or events.shape[1] != 3 or len(events) != len(data):
        raise ValueError("MNE epoch events do not match the epoch collection")
    if times.ndim != 1 or len(times) == 0:
        raise ValueError("MNE epochs do not expose a usable time axis")

    epoch_sfreq = float(data.info["sfreq"])
    # MNE retains this coordinate frequency across Epochs.resample and FIF IO.
    source_sfreq = _source_sampling_frequency(data, epoch_sfreq)
    if not np.isfinite(epoch_sfreq) or epoch_sfreq <= 0:
        raise ValueError("MNE epoch sampling frequency must be positive")
    if not np.isfinite(source_sfreq) or source_sfreq <= 0:
        raise ValueError("MNE source sampling frequency must be positive")

    tmin_seconds = float(times[0])
    tmax_seconds = float(times[-1])
    start_offset = int(np.rint(tmin_seconds * source_sfreq))
    source_window_samples = int(
        np.rint(len(times) * source_sfreq / epoch_sfreq),
    )
    if source_window_samples <= 0:
        raise ValueError("MNE epoch window must contain at least one source sample")

    source_id, source_identity_verified = _source_recording_id(
        preprocessed_data,
        source_wrapper_index=source_wrapper_index,
    )
    coordinates_verified = (
        source_coordinates_verified
        and source_identity_verified
        and _is_verified_source_recording_id(source_id)
    )
    return tuple(
        EpochWindowProvenance(
            source_recording_id=source_id,
            event_sample=int(event[0]),
            window_start_sample=int(event[0]) + start_offset,
            window_end_sample_exclusive=(
                int(event[0]) + start_offset + source_window_samples
            ),
            source_sfreq=source_sfreq,
            epoch_sfreq=epoch_sfreq,
            tmin_seconds=tmin_seconds,
            tmax_seconds=tmax_seconds,
            source_coordinates_verified=coordinates_verified,
        )
        for event in events
    )


def _serialize_epoch_window_provenance(
    item: EpochWindowProvenance,
) -> str:
    return json.dumps(
        {
            "schema_version": EPOCH_SOURCE_PROVENANCE_SCHEMA_VERSION,
            "origin": EPOCH_SOURCE_PROVENANCE_ORIGIN,
            **asdict(item),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _deserialize_epoch_window_provenance(
    value: object,
) -> EpochWindowProvenance | None:
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != EPOCH_SOURCE_PROVENANCE_SCHEMA_VERSION:
        return None
    if payload.get("origin") != EPOCH_SOURCE_PROVENANCE_ORIGIN:
        return None
    if payload.get("source_coordinates_verified") is not True:
        return None

    source_recording_id = payload.get("source_recording_id")
    integer_fields = (
        "event_sample",
        "window_start_sample",
        "window_end_sample_exclusive",
    )
    float_fields = (
        "source_sfreq",
        "epoch_sfreq",
        "tmin_seconds",
        "tmax_seconds",
    )
    if not isinstance(source_recording_id, str):
        return None
    if not _is_verified_source_recording_id(source_recording_id):
        return None
    if any(
        not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool)
        for field in integer_fields
    ):
        return None
    if any(
        not isinstance(payload.get(field), int | float)
        or isinstance(payload.get(field), bool)
        for field in float_fields
    ):
        return None

    item = EpochWindowProvenance(
        source_recording_id=source_recording_id,
        event_sample=int(payload["event_sample"]),
        window_start_sample=int(payload["window_start_sample"]),
        window_end_sample_exclusive=int(payload["window_end_sample_exclusive"]),
        source_sfreq=float(payload["source_sfreq"]),
        epoch_sfreq=float(payload["epoch_sfreq"]),
        tmin_seconds=float(payload["tmin_seconds"]),
        tmax_seconds=float(payload["tmax_seconds"]),
        source_coordinates_verified=True,
    )
    if item.window_start_sample >= item.window_end_sample_exclusive:
        return None
    if (
        not np.isfinite(item.source_sfreq)
        or item.source_sfreq <= 0
        or not np.isfinite(item.epoch_sfreq)
        or item.epoch_sfreq <= 0
        or not np.isfinite(item.tmin_seconds)
        or not np.isfinite(item.tmax_seconds)
        or item.tmin_seconds > item.tmax_seconds
    ):
        return None
    return item


def _embedded_epoch_window_provenance(
    data: mne.BaseEpochs,
) -> tuple[EpochWindowProvenance, ...] | None:
    metadata = data.metadata
    if (
        metadata is None
        or EPOCH_SOURCE_PROVENANCE_METADATA_COLUMN not in metadata.columns
        or len(metadata) != len(data)
    ):
        return None

    events = np.asarray(data.events)
    times = np.asarray(data.times, dtype=float)
    if events.ndim != 2 or events.shape != (len(data), 3):
        return None
    if times.ndim != 1 or len(times) == 0:
        return None
    records: list[EpochWindowProvenance] = []
    for index, encoded in enumerate(
        metadata[EPOCH_SOURCE_PROVENANCE_METADATA_COLUMN].tolist(),
    ):
        item = _deserialize_epoch_window_provenance(encoded)
        if item is None or item.event_sample != int(events[index, 0]):
            return None
        expected_start = item.event_sample + int(
            np.rint(item.tmin_seconds * item.source_sfreq),
        )
        expected_samples = int(
            np.rint(
                len(times) * item.source_sfreq / item.epoch_sfreq,
            ),
        )
        if (
            expected_samples <= 0
            or item.window_start_sample != expected_start
            or item.window_end_sample_exclusive != expected_start + expected_samples
        ):
            return None
        records.append(item)
    return tuple(records)


def mark_xbrainlab_raw_event_source_epochs(
    preprocessed_data: Raw,
) -> tuple[EpochWindowProvenance, ...]:
    """Persist explicit raw-event source coordinates in MNE epoch metadata.

    This function is the trust boundary for an XBrainLab producer that still
    has the source recording and event-coordinate context. Imported epoched
    files must not call it merely because they expose MNE events.
    """
    data = preprocessed_data.get_mne()
    if not isinstance(data, mne.BaseEpochs):
        raise TypeError("Raw-event provenance can only be attached to MNE epochs")
    provenance = _computed_epoch_window_provenance(
        preprocessed_data,
        data,
        source_wrapper_index=0,
        source_coordinates_verified=True,
    )
    if not provenance or not all(
        item.source_coordinates_verified for item in provenance
    ):
        raise ValueError(
            "Verified raw-event provenance requires an explicit source identity.",
        )

    metadata = (
        data.metadata.copy()
        if data.metadata is not None
        else pd.DataFrame(index=np.arange(len(data)))
    )
    metadata[EPOCH_SOURCE_PROVENANCE_METADATA_COLUMN] = [
        _serialize_epoch_window_provenance(item) for item in provenance
    ]
    data.metadata = metadata
    return provenance


def _has_xbrainlab_epoch_creation_record(preprocessed_data: Raw) -> bool:
    """Return whether XBrainLab recorded an in-session raw epoch operation."""
    try:
        history = preprocessed_data.get_preprocess_history()
    except (AttributeError, TypeError, ValueError):
        return False
    if not isinstance(history, list):
        return False
    return any(
        isinstance(record, str)
        and record.startswith("Epoching ")
        and (
            _XBRAINLAB_EVENT_EPOCH_HISTORY_MARKER in record
            or record.endswith(_XBRAINLAB_WINDOW_EPOCH_HISTORY_SUFFIX)
        )
        for record in history
    )


def _epoch_window_provenance(
    preprocessed_data: Raw,
    data: mne.BaseEpochs,
    *,
    source_wrapper_index: int,
) -> tuple[EpochWindowProvenance, ...]:
    """Read explicit provenance or fail closed to unverified coordinates."""
    embedded = _embedded_epoch_window_provenance(data)
    if embedded is not None:
        return embedded
    return _computed_epoch_window_provenance(
        preprocessed_data,
        data,
        source_wrapper_index=source_wrapper_index,
        source_coordinates_verified=False,
    )


class TrialSelectionSequence(Enum):
    """Enumeration defining the attribute order for balanced trial selection.

    Attributes:
        SESSION: Select by session attribute.
        SUBJECT: Select by subject attribute.
        LABEL: Select by label attribute.

    """

    SESSION = "session"
    SUBJECT = "subject"
    LABEL = "label"


class Epochs:
    """Container for epoch data derived from preprocessed EEG recordings.

    Aggregates multiple ``Raw`` objects into a unified epoch array with
    consistent label, subject, and session mappings. Provides picking and
    splitting utilities used by the dataset generator.

    Args:
        preprocessed_data_list: List of preprocessed ``Raw`` objects. Each must
            be of epoch type (not unsegmented raw).

    .. note::

        The constructor unifies event IDs across all input files by calling
        ``set_event`` on each ``Raw`` object **in place**.  Callers should
        be aware that the original ``preprocessed_data_list`` items are
        mutated.

    Attributes:
        sfreq: Sampling frequency of the data in Hz.
        subject_map: Mapping from subject index to subject name.
        session_map: Mapping from session index to session name.
        label_map: Mapping from label index to label name.
        event_id: Mapping from event name to event ID.
        ch_names: List of EEG channel names.
        channel_position: List of channel (x, y, z) positions, or None.
        subject: Array of subject index for each epoch.
        session: Array of session index for each epoch.
        label: Array of label index for each epoch.
        idx: Array of within-file epoch index for each epoch.
        data: 3D array of shape ``(n_epochs, n_channels, n_samples)``.
        epoch_window_provenance: Source recording and sample-window metadata for
            each epoch. No EEG sample arrays are stored in this metadata.

    Raises:
        ValueError: If any item in preprocessed_data_list is unsegmented raw.

    """

    def __init__(self, preprocessed_data_list: list[Raw]):
        validate_list_type(
            instance_list=preprocessed_data_list,
            type_class=Raw,
            message_name="preprocessed_data_list",
        )
        for preprocessed_data in preprocessed_data_list:
            if preprocessed_data.is_raw():
                raise ValueError(
                    "Items of preprocessed_data_list must be "
                    f"{Raw.__module__}.Raw of type epoch.",
                )

        epoch_sources: list[mne.BaseEpochs] = []
        for preprocessed_data in preprocessed_data_list:
            data = preprocessed_data.get_mne()
            if not isinstance(data, mne.BaseEpochs):
                raise TypeError("Preprocessed epoch data must contain MNE epochs")
            epoch_sources.append(data)
        self._validate_channel_identity(epoch_sources)

        self.sfreq = None
        # maps
        self.subject_map: dict[int, str] = {}  # index: subject name
        self.session_map: dict[int, str] = {}  # index: session name
        self.label_map: dict[int, str] = {}  # {int(event_id): 'description'}
        self.event_id: dict[str, int] = {}  # {'event_name': int(event_id)}
        self.ch_names = epoch_sources[0].info.ch_names.copy() if epoch_sources else []
        self.channel_position: list | None = None
        self.tmin: float = 0.0  # epoch start time relative to event (seconds)

        # 1D np array
        self.subject: np.ndarray = np.array([])
        self.session: np.ndarray = np.array([])
        self.label: np.ndarray = np.array([])
        self.idx: np.ndarray = np.array([])
        self.epoch_window_provenance: tuple[EpochWindowProvenance, ...] = ()
        self.trial_group: np.ndarray = np.array([], dtype=int)
        self.trial_selection_evidence: list[dict[str, Any]] = []
        self.trial_selection_evidence_dropped = 0

        self.data: np.ndarray = np.array([])

        # event_id
        for preprocessed_data in preprocessed_data_list:
            _, event_id = preprocessed_data.get_event_list()
            self.event_id.update(event_id)
        ## fix
        fixed_event_id: dict[str, int] = {}
        for event_name in self.event_id:
            fixed_event_id[event_name] = len(fixed_event_id)
        ## update
        self.event_id = fixed_event_id
        for preprocessed_data in preprocessed_data_list:
            old_events, old_event_id = preprocessed_data.get_event_list()

            old_event_id = old_event_id.copy()

            events = old_events.copy()
            event_id = old_event_id.copy()
            old_labels = old_events[:, 2].copy()

            if len(set(old_event_id.values())) != len(old_event_id):
                raise ValueError(
                    "Epoch event names must map to unique source event codes.",
                )
            unknown_codes = set(np.unique(old_labels)) - set(old_event_id.values())
            if unknown_codes:
                raise ValueError(
                    "Epoch events contain code(s) missing from event_id: "
                    + ", ".join(str(code) for code in sorted(unknown_codes)),
                )
            for old_event_name, old_event_label in old_event_id.items():
                events[:, 2][old_labels == old_event_label] = fixed_event_id[
                    old_event_name
                ]
                event_id[old_event_name] = fixed_event_id[old_event_name]
            preprocessed_data.set_event(events, event_id)

        # label map
        self.label_map = {}
        for event_name, event_label in self.event_id.items():
            self.label_map[event_label] = event_name

        # info
        map_subject: dict[str, int] = {}
        map_session: dict[str, int] = {}

        # Collect arrays in lists first, then concatenate once (O(n) vs O(n²))
        subject_parts: list[np.ndarray] = []
        session_parts: list[np.ndarray] = []
        label_parts: list[np.ndarray] = []
        idx_parts: list[np.ndarray] = []
        data_parts: list[np.ndarray] = []
        provenance_parts: list[EpochWindowProvenance] = []

        for source_wrapper_index, preprocessed_data in enumerate(
            preprocessed_data_list,
        ):
            data = epoch_sources[source_wrapper_index]
            if _embedded_epoch_window_provenance(
                data
            ) is None and _has_xbrainlab_epoch_creation_record(preprocessed_data):
                # A producer record without usable source identity remains
                # unverified and will be blocked by a trial-wise audit.
                with suppress(TypeError, ValueError):
                    mark_xbrainlab_raw_event_source_epochs(preprocessed_data)
            epoch_len = preprocessed_data.get_epochs_length()
            subject_name = preprocessed_data.get_subject_name()
            session_name = preprocessed_data.get_session_name()
            if subject_name not in map_subject:
                map_subject[subject_name] = len(map_subject)
            if session_name not in map_session:
                map_session[session_name] = len(map_session)
            subject_idx = map_subject[subject_name]
            session_idx = map_session[session_name]

            subject_parts.append(np.full(epoch_len, subject_idx))
            session_parts.append(np.full(epoch_len, session_idx))
            label_parts.append(data.events[:, 2])
            idx_parts.append(np.arange(epoch_len))
            data_parts.append(data.get_data())
            provenance_parts.extend(
                _epoch_window_provenance(
                    preprocessed_data,
                    data,
                    source_wrapper_index=source_wrapper_index,
                ),
            )
            self.sfreq = data.info["sfreq"]
            self.tmin = getattr(data, "tmin", 0.0)

        if subject_parts:
            self.subject = np.concatenate(subject_parts)
            self.session = np.concatenate(session_parts)
            self.label = np.concatenate(label_parts)
            self.idx = np.concatenate(idx_parts)
            self.data = np.concatenate(data_parts)
            self.epoch_window_provenance = tuple(provenance_parts)
            self.trial_group = _build_atomic_trial_groups(
                self.epoch_window_provenance,
            )

        self.session_map = {map_session[i]: i for i in map_session}
        self.subject_map = {map_subject[i]: i for i in map_subject}

    @staticmethod
    def _validate_channel_identity(epoch_sources: list[mne.BaseEpochs]) -> None:
        """Reject multi-file epochs whose channel axes have different meaning."""
        if not epoch_sources:
            return
        reference = epoch_sources[0]
        reference_names = list(reference.info["ch_names"])
        reference_types = list(reference.get_channel_types())
        for index, data in enumerate(epoch_sources[1:], start=1):
            channel_names = list(data.info["ch_names"])
            if channel_names != reference_names:
                raise ValueError(
                    "Epoch channel names or order differ between files: "
                    f"source 0 has {reference_names}, source {index} has "
                    f"{channel_names}.",
                )
            channel_types = list(data.get_channel_types())
            if channel_types != reference_types:
                raise ValueError(
                    "Epoch channel types differ between files: "
                    f"source 0 has {reference_types}, source {index} has "
                    f"{channel_types}.",
                )

    def copy(self) -> Epochs:
        """Return a deep copy of this Epochs object.

        Returns:
            A new independent Epochs instance with identical data.

        """
        return deepcopy(self)

    # data splitting
    ## get list
    def get_subject_list(self) -> np.ndarray:
        """Return list of subject index of each epoch."""
        return self.subject

    def get_session_list(self) -> np.ndarray:
        """Return list of session index of each epoch."""
        return self.session

    def get_label_list(self) -> np.ndarray:
        """Return list of label index of each epoch."""
        return self.label

    ## get list by mask
    def get_subject_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        """Return list of subject index of each epoch by mask.

        Args:
            mask: Mask to filter out remaining epochs. 1D np.ndarray of bool.

        """
        return self.subject[mask]

    def get_session_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        """Return list of session index of each epoch by mask.

        Args:
            mask: Mask to filter out remaining epochs. 1D np.ndarray of bool.

        """
        return self.session[mask]

    def get_label_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        """Return list of label index of each epoch by mask.

        Args:
            mask: Mask to filter out remaining epochs. 1D np.ndarray of bool.

        """
        return self.label[mask]

    def get_idx_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        """Return list of epoch index of each epoch by mask.

        Args:
            mask: Mask to filter out remaining epochs. 1D np.ndarray of bool.

        """
        return self.idx[mask]

    def get_epoch_window_provenance(
        self,
    ) -> tuple[EpochWindowProvenance, ...]:
        """Return immutable source-window provenance in epoch index order.

        Older serialized ``Epochs`` instances may not contain this attribute;
        callers receive an empty tuple so they can report an incomplete audit.
        """
        return tuple(getattr(self, "epoch_window_provenance", ()))

    def get_trial_group_list(self) -> np.ndarray:
        """Return the atomic temporal-overlap group for every epoch."""
        groups = np.asarray(
            getattr(self, "trial_group", np.array([], dtype=int)),
            dtype=int,
        )
        if len(groups) != self.get_data_length():
            return np.arange(self.get_data_length(), dtype=int)
        return groups.copy()

    def get_trial_selection_evidence(self) -> list[dict[str, Any]]:
        """Return bounded structured evidence from trial split selections."""
        return deepcopy(getattr(self, "trial_selection_evidence", []))

    def get_trial_selection_evidence_dropped(self) -> int:
        """Return the number of old selection evidence records discarded."""
        return int(getattr(self, "trial_selection_evidence_dropped", 0))

    def reset_trial_selection_evidence(self) -> None:
        """Clear trial selection evidence before a new generation run."""
        self.trial_selection_evidence = []
        self.trial_selection_evidence_dropped = 0

    def _record_trial_selection_evidence(self, evidence: dict[str, Any]) -> None:
        if len(self.trial_selection_evidence) >= MAX_TRIAL_SELECTION_EVIDENCE:
            self.trial_selection_evidence.pop(0)
            self.trial_selection_evidence_dropped += 1
        self.trial_selection_evidence.append(deepcopy(evidence))

    ## get by index
    def get_subject_name(self, idx: int) -> str:
        """Return subject name by subject index.

        Args:
            idx: Subject index.

        """
        return self.subject_map[idx]

    def get_session_name(self, idx: int) -> str:
        """Return session name by session index.

        Args:
            idx: Session index.

        """
        return self.session_map[idx]

    def get_label_name(self, idx: int) -> str:
        """Return label name by label index.

        Args:
            idx: Label index.

        """
        return self.label_map[idx]

    ## get map
    def get_subject_map(self) -> dict:
        """Return mapping from subject index to subject name."""
        return self.subject_map

    def get_session_map(self) -> dict:
        """Return mapping from session index to session name."""
        return self.session_map

    def get_label_map(self) -> dict:
        """Return mapping from label index to label name."""
        return self.label_map

    ## misc getter
    def get_subject_index_list(self) -> list:
        """Return list of subject index."""
        return list(self.subject_map.keys())

    def pick_subject_mask_by_idx(self, idx: int) -> np.ndarray:
        """Return mask of epochs by subject index.

        Args:
            idx: Subject index.

        """
        return self.subject == idx

    ## data info
    def get_data_length(self) -> int:
        """Return number of total epochs."""
        return len(self.data)

    ## picker
    """
        How it works:
            (Enter pick_XXX)
            Get the list of selected attributes.
            (Enter _pick)
            Calculate the number of ids to be selected. (In _get_real_num)
            Generate the mask and selected counter filtered by each attribute.
                (In _generate_mask_target)
            while number of epochs to be selected > 0:
                Get the mask and counter of epochs with least selected counter.
                    (In _get_filtered_mask_pair)
                Choose one epoch
                Select all epochs matched the chosen epoch by the attribute.
                Update the counter of groups that contain the chosen epoch.
                    (In _update_mask_target)
                Decrease the number of ids to be selected.
            Return the selected mask.
        Note: sequence of attributes to be selected can make the result different.
            (The sequence is defined in _get_filtered_mask_pair)
        Note: Trial is different from other attributes.
            (In pick_trial) The index of trial is discarded
                            ecause it is meaningless so far.
    """

    def _generate_mask_target(self, mask: np.ndarray) -> dict:
        """Generate mask-counter pairs grouped by label, subject, and session.

        Creates a nested dictionary structure that tracks which epochs belong
        to each (label, subject, session) combination and how many have been
        selected so far.

        Args:
            mask: Boolean mask of available epochs.

        Returns:
            Nested dict with structure
            ``{label_idx: {subject_idx: {session_idx: [bool_mask, count]}}}``.

        """
        filter_preview_mask: dict[int, dict[int, dict[int, list]]] = {}
        unique_label_idx = np.unique(self.get_label_list())
        unique_subject_idx = np.unique(self.get_subject_list())
        unique_session_idx = np.unique(self.get_session_list())
        for label_idx in unique_label_idx:
            if label_idx not in filter_preview_mask:
                filter_preview_mask[label_idx] = {}
            for subject_idx in unique_subject_idx:
                if subject_idx not in filter_preview_mask[label_idx]:
                    filter_preview_mask[label_idx][subject_idx] = {}
                for session_idx in unique_session_idx:
                    filter_mask = (
                        (self.label == label_idx)
                        & (self.subject == subject_idx)
                        & (self.session == session_idx)
                    )
                    target_filter_mask = filter_mask & mask
                    filter_preview_mask[label_idx][subject_idx][session_idx] = [
                        target_filter_mask,
                        0,
                    ]
        return filter_preview_mask

    def _get_filtered_mask_pair(self, filter_preview_mask: dict) -> list | None:
        """Find the mask-counter pair with the least-selected group.

        Used for balanced epoch selection to ensure even distribution across
        label/subject/session combinations.

        Args:
            filter_preview_mask: Nested mask-counter dict from
                :meth:`_generate_mask_target`.

        Returns:
            ``[bool_mask, count]`` pair with the smallest count, or None if
            no selectable epochs remain.

        """
        min_count = self.get_data_length()
        filtered_mask_pair = None
        sequence = [
            TrialSelectionSequence.SESSION,
            TrialSelectionSequence.SUBJECT,
            TrialSelectionSequence.LABEL,
        ]
        for a in np.unique(getattr(self, f"get_{sequence[0].value}_list")()):
            for b in np.unique(getattr(self, f"get_{sequence[1].value}_list")()):
                for c in np.unique(getattr(self, f"get_{sequence[2].value}_list")()):
                    args = [a, b, c]
                    label_idx = args[sequence.index(TrialSelectionSequence.LABEL)]
                    subject_idx = args[sequence.index(TrialSelectionSequence.SUBJECT)]
                    session_idx = args[sequence.index(TrialSelectionSequence.SESSION)]
                    target = filter_preview_mask[label_idx][subject_idx][session_idx]
                    if target[0].any() and target[1] < min_count:
                        min_count = target[1]
                        filtered_mask_pair = target
        return filtered_mask_pair

    def _update_mask_target(self, filter_preview_mask: dict, pos: np.ndarray) -> dict:
        """Update mask-counter pairs after selecting epochs.

        Removes selected epochs from available masks and increments counters
        for all groups that contained the selected epochs.

        Args:
            filter_preview_mask: Nested mask-counter dict to update.
            pos: Boolean mask of newly selected epochs.

        Returns:
            Updated mask-counter dict.

        """
        for unique_subject_idx in filter_preview_mask.values():
            for unique_session_idx in unique_subject_idx.values():
                for filtered_mask_pair in unique_session_idx.values():
                    filtered_mask_pair[1] += sum(filtered_mask_pair[0] & pos)
                    filtered_mask_pair[0] &= np.logical_not(pos)
        return filter_preview_mask

    def _get_real_num(
        self,
        target_type: np.ndarray,
        value: float | list[int],
        split_unit: SplitUnit,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        group_idx: int,
    ) -> int:
        """Calculate the number of unique IDs to select for splitting.

        Converts a ratio, absolute number, or k-fold specification into an
        actual count of unique target IDs to pick.

        Args:
            target_type: Array of target attribute indices (e.g. subject or
                session index per epoch).
            value: Splitting value (ratio, count, or manual list).
            split_unit: Unit of the splitting value.
            mask: Boolean mask of available epochs (excluding prior CV folds).
            clean_mask: Boolean mask of all selectable epochs, or None.
            group_idx: Current cross-validation group index.

        Returns:
            Number of unique IDs to select.

        Raises:
            ValueError: If value type does not match the expected split unit.
            NotImplementedError: If the split unit is unsupported.

        """
        if clean_mask is None:
            target = len(np.unique(target_type[mask]))
        else:
            target = len(np.unique(target_type[clean_mask]))
        if split_unit == SplitUnit.KFOLD:
            if not isinstance(value, (int, float)):
                raise ValueError("Value must be int or float")
            value = int(value)
            inc = target % value
            num = target // value
            if inc > group_idx:
                num += 1
        elif split_unit == SplitUnit.RATIO:
            if not isinstance(value, (int, float)):
                raise ValueError("Value must be int or float")
            num = int(value * target)
        elif split_unit == SplitUnit.NUMBER:
            if not isinstance(value, (int, float)):
                raise ValueError("Value must be int or float")
            num = int(min(value, target))
        else:
            raise NotImplementedError
        num = int(num)
        return num

    def _pick(
        self,
        target_type: np.ndarray,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        value: float | list[int],
        split_unit: SplitUnit,
        group_idx: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return mask of selected epochs by splitting option and target type.

        Args:
            target_type: List of index of target type.
                         Can be list index of subject or session.
            mask: Mask to filter out remaining epochs,
                  ecxluding already selected cross validation part.
                  1D np.ndarray of bool.
            clean_mask: Mask to filter out remaining epochs,
                        including all available selection.
                        1D np.ndarray of bool.
            value: Value of splitting option.
                   Can be ratio, number, or list of manual selection.
            split_unit: SplitUnit of splitting option.
            group_idx: Group index of cross validation.

        Returns:
            [selected_mask, remaining_mask]

        """
        num = self._get_real_num(
            target_type,
            value,
            split_unit,
            mask,
            clean_mask,
            group_idx,
        )
        ret = mask & False
        filter_preview_mask = self._generate_mask_target(mask)
        while num > 0:
            filtered_mask_pair = self._get_filtered_mask_pair(filter_preview_mask)
            if filtered_mask_pair is None:
                return ret, mask
            target = target_type[filtered_mask_pair[0]]
            if len(target) > 0:
                pos = mask & (target_type == target[-1])
                ret |= pos
                mask &= np.logical_not(pos)
                self._update_mask_target(filter_preview_mask, pos)
                filtered_mask_pair[0] &= np.logical_not(pos)
                filtered_mask_pair[1] += sum(pos)
                num -= 1
        return ret, mask

    def _pick_manual(
        self,
        target_type: np.ndarray,
        mask: np.ndarray,
        value: list[int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return mask of selected epochs by manual selection.

        Args:
            target_type: List of index of target type.
                         Can be list index of subject or session.
            mask: Mask to filter out remaining epochs,
                  ecxluding already selected cross validation part.
                  1D np.ndarray of bool.
            value: List of manual selection.

        Returns:
            [selected_mask, remaining_mask]

        """
        ret = mask & False
        for v in value:
            pos = mask & (target_type == v)
            ret |= pos
            mask &= np.logical_not(pos)
        return ret, mask

    def pick_subject(
        self,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        value: float | list[int],
        split_unit: SplitUnit,
        group_idx: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return mask of epochs selected by subject.

        Args:
            mask: Mask to filter out remaining epochs,
                  ecxluding already selected cross validation part.
                  1D np.ndarray of bool.
            clean_mask: Mask to filter out remaining epochs,
                        including all available selection.
                        1D np.ndarray of bool.
            value: Value of splitting option.
                   Can be ratio, number, or list of manual selection.
            split_unit: SplitUnit of splitting option.
            group_idx: Group index of cross validation.

        Returns:
            [selected_mask, remaining_mask]

        """
        target_type = self.get_subject_list()
        if split_unit == SplitUnit.MANUAL:
            if not isinstance(value, list):
                raise ValueError("Value must be a list for manual selection")
            return self._pick_manual(target_type, mask, value)
        return self._pick(
            target_type,
            mask,
            clean_mask,
            value,
            split_unit,
            group_idx,
        )

    def pick_session(
        self,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        value: float | list[int],
        split_unit: SplitUnit,
        group_idx: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return mask of epochs selected by session.

        Args:
            mask: Mask to filter out remaining epochs,
                  ecxluding already selected cross validation part.
                  1D np.ndarray of bool.
            clean_mask: Mask to filter out remaining epochs,
                        including all available selection.
                        1D np.ndarray of bool.
            value: Value of splitting option.
                   Can be ratio, number,
                   or list of manual selection.
            split_unit: SplitUnit of splitting option.
            group_idx: Group index of cross validation.

        Returns:
            [selected_mask, remaining_mask]

        """
        target_type = self.get_session_list()
        if split_unit == SplitUnit.MANUAL:
            if not isinstance(value, list):
                raise ValueError("Value must be a list for manual selection")
            return self._pick_manual(target_type, mask, value)
        return self._pick(
            target_type,
            mask,
            clean_mask,
            value,
            split_unit,
            group_idx,
        )

    @staticmethod
    def _bounded_trial_indices(values: np.ndarray | list[int]) -> list[int]:
        return [
            int(value)
            for value in np.asarray(values, dtype=int).tolist()[
                :MAX_TRIAL_SELECTION_EVIDENCE_INDICES
            ]
        ]

    def _pick_manual_atomic_trial_groups(
        self,
        mask: np.ndarray,
        value: list[int],
        group_idx: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        requested = sorted({int(index) for index in value})
        invalid = [
            index for index in requested if index < 0 or index >= self.get_data_length()
        ]
        if invalid:
            raise ValueError(f"Manual trial indices are out of range: {invalid}")

        groups = self.get_trial_group_list()
        selected = np.zeros_like(mask, dtype=bool)
        selected_group_ids: list[int] = []
        for index in requested:
            group_id = int(groups[index])
            group_mask = groups == group_id
            unavailable = np.flatnonzero(group_mask & np.logical_not(mask))
            if len(unavailable) > 0:
                raise ValueError(
                    "Manual trial selection would split atomic overlap group "
                    f"{group_id}; unavailable epoch indices: "
                    f"{self._bounded_trial_indices(unavailable)}",
                )
            selected |= group_mask
            selected_group_ids.append(group_id)

        requested_set = set(requested)
        selected_indices = np.flatnonzero(selected)
        expanded_indices = np.asarray(
            [index for index in selected_indices if int(index) not in requested_set],
            dtype=int,
        )
        mask &= np.logical_not(selected)
        self._record_trial_selection_evidence(
            {
                "selection_unit": "manual",
                "group_index": group_idx,
                "requested_count": len(requested),
                "requested_indices": self._bounded_trial_indices(requested),
                "requested_indices_truncated": len(requested)
                > MAX_TRIAL_SELECTION_EVIDENCE_INDICES,
                "expanded_count": len(expanded_indices),
                "expanded_indices": self._bounded_trial_indices(expanded_indices),
                "expanded_indices_truncated": len(expanded_indices)
                > MAX_TRIAL_SELECTION_EVIDENCE_INDICES,
                "selected_group_count": len(set(selected_group_ids)),
                "selected_epoch_count": int(selected.sum()),
            },
        )
        return selected, mask

    def _trial_target_epoch_count(
        self,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        value: float | list[int],
        split_unit: SplitUnit,
        group_idx: int,
    ) -> int:
        available_count = int(mask.sum())
        scope_count = available_count if clean_mask is None else int(clean_mask.sum())
        if split_unit == SplitUnit.KFOLD:
            if not isinstance(value, (int, float)):
                raise ValueError("K-fold trial split value must be numeric")
            fold_count = int(value)
            if fold_count <= 0:
                raise ValueError("K-fold trial split value must be positive")
            scope_mask = mask if clean_mask is None else clean_mask
            atomic_group_count = len(
                np.unique(self.get_trial_group_list()[scope_mask]),
            )
            if atomic_group_count < fold_count:
                raise ValueError(
                    f"K-fold trial split requires at least {fold_count} atomic "
                    f"groups; found {atomic_group_count}.",
                )
            if group_idx < 0 or group_idx >= fold_count:
                raise ValueError("K-fold group index is out of range")
            if group_idx == fold_count - 1:
                return available_count
            base, remainder = divmod(scope_count, fold_count)
            return min(base + int(group_idx < remainder), available_count)
        if split_unit == SplitUnit.RATIO:
            if not isinstance(value, (int, float)):
                raise ValueError("Trial split ratio must be numeric")
            return min(int(float(value) * scope_count), available_count)
        if split_unit == SplitUnit.NUMBER:
            if not isinstance(value, (int, float)):
                raise ValueError("Trial split number must be numeric")
            return min(int(value), available_count)
        raise NotImplementedError

    def _pick_atomic_trial_groups(
        self,
        mask: np.ndarray,
        target_epoch_count: int,
        reserve_group_count: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        selected = np.zeros_like(mask, dtype=bool)
        groups = self.get_trial_group_list()
        filter_preview_mask = self._generate_mask_target(mask)
        while int(selected.sum()) < target_epoch_count:
            available_group_count = len(np.unique(groups[mask]))
            if selected.any() and available_group_count <= reserve_group_count:
                break
            filtered_mask_pair = self._get_filtered_mask_pair(filter_preview_mask)
            if filtered_mask_pair is None:
                break
            candidates = np.flatnonzero(filtered_mask_pair[0])
            if len(candidates) == 0:
                break
            group_id = int(groups[int(candidates[-1])])
            group_mask = groups == group_id
            unavailable = group_mask & np.logical_not(mask)
            if unavailable.any():
                raise ValueError(
                    f"Trial split scope would split atomic overlap group {group_id}.",
                )
            selected_now = mask & group_mask
            selected |= selected_now
            mask &= np.logical_not(selected_now)
            self._update_mask_target(filter_preview_mask, selected_now)
        return selected, mask

    def pick_trial(
        self,
        mask: np.ndarray,
        clean_mask: np.ndarray | None,
        value: float | list[int],
        split_unit: SplitUnit,
        group_idx: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Select whole temporal-overlap groups for a trial-wise split."""
        if split_unit == SplitUnit.MANUAL:
            if not isinstance(value, list):
                raise ValueError("Value must be a list for manual selection")
            return self._pick_manual_atomic_trial_groups(mask, value, group_idx)

        target_epoch_count = self._trial_target_epoch_count(
            mask,
            clean_mask,
            value,
            split_unit,
            group_idx,
        )
        selected, remaining = self._pick_atomic_trial_groups(
            mask,
            target_epoch_count,
            reserve_group_count=(
                int(value) - group_idx - 1
                if split_unit == SplitUnit.KFOLD and isinstance(value, (int, float))
                else 0
            ),
        )
        selected_groups = np.unique(
            self.get_trial_group_list()[selected],
        )
        self._record_trial_selection_evidence(
            {
                "selection_unit": split_unit.value.lower().replace(" ", "_"),
                "group_index": group_idx,
                "target_epoch_count": target_epoch_count,
                "selected_epoch_count": int(selected.sum()),
                "selected_group_count": len(selected_groups),
                "selected_group_ids": self._bounded_trial_indices(selected_groups),
                "selected_group_ids_truncated": len(selected_groups)
                > MAX_TRIAL_SELECTION_EVIDENCE_INDICES,
            },
        )
        return selected, remaining

    # train
    def get_model_args(self):
        """Return arguments needed for model initialization.

        Returns:
            Dict with keys ``n_classes``, ``channels``, ``samples``, ``sfreq``.

        """
        return {
            "n_classes": len(self.label_map),
            "channels": len(self.ch_names),
            "samples": self.data.shape[-1],
            "sfreq": self.sfreq,
        }

    def get_data(self) -> np.ndarray:
        """Return the epoch data array.

        Returns:
            3D array of shape ``(n_epochs, n_channels, n_samples)``.

        """
        return self.data

    # eval
    def get_label_number(self) -> int:
        """Return number of labels."""
        return len(self.label_map)

    def get_channel_names(self) -> list:
        """Return list of channel names."""
        return self.ch_names

    def get_epoch_duration(self) -> float:
        """Return duration of each epoch in seconds."""
        if self.sfreq is None:
            return 0.0
        return np.round(self.data.shape[-1] / self.sfreq, 2)

    def set_channels(self, ch_names: list[str], channel_position: list) -> None:
        """Atomically apply a montage-aligned channel subset and ordering.

        Args:
            ch_names: Existing dataset channel names in the requested output order.
            channel_position: List of channel positions as ``(x, y, z)`` tuples.

        Raises:
            ValueError: If channel identity or position data is ambiguous.
            RuntimeError: If the epoch channel axis is inconsistent with its names.

        """
        requested_names = [str(name).strip() for name in ch_names]
        if not requested_names or any(not name for name in requested_names):
            raise ValueError("Montage must contain at least one named channel.")
        if len(set(requested_names)) != len(requested_names):
            raise ValueError("Montage channel names must be unique.")
        if len(set(self.ch_names)) != len(self.ch_names):
            raise ValueError(
                "Dataset channel names must be unique before montage apply."
            )
        if len(requested_names) != len(channel_position):
            raise ValueError("channels and positions must have equal length.")

        positions = np.asarray(channel_position, dtype=float)
        if positions.shape != (len(requested_names), 3):
            raise ValueError("Each montage position must contain x, y, z values.")
        if not np.isfinite(positions).all():
            raise ValueError("Montage positions must contain finite values.")

        unknown = [name for name in requested_names if name not in self.ch_names]
        if unknown:
            raise ValueError(
                f"Montage contains unknown channel(s): {', '.join(unknown)}."
            )
        if self.data.ndim != 3 or self.data.shape[1] != len(self.ch_names):
            raise RuntimeError(
                "Epoch data channel axis does not match the current channel names."
            )

        channel_indices = [self.ch_names.index(name) for name in requested_names]
        reordered_data = self.data[:, channel_indices, :]
        normalized_positions = [tuple(position) for position in positions.tolist()]

        self.data = reordered_data
        self.ch_names = requested_names
        self.channel_position = normalized_positions

    def get_montage_position(self) -> list | None:
        """Return the channel positions for montage visualization.

        Returns:
            List of channel positions as (x, y, z) tuples, or None if not set.

        """
        return self.channel_position

    def get_mne(self):
        """Reconstruct an MNE ``EpochsArray`` from stored data.

        Returns:
            ``mne.EpochsArray`` with the stored epoch data, channel info,
            and event mapping.

        """
        info = mne.create_info(ch_names=self.ch_names, sfreq=self.sfreq, ch_types="eeg")

        n_epochs = len(self.data)
        # Construct dummy events
        events = np.zeros((n_epochs, 3), dtype=int)
        events[:, 0] = np.arange(n_epochs) * 1000  # distinct onset
        events[:, 2] = self.label.astype(int)

        # event_id might need to be inverted or checked if values match label indices
        # self.event_id is {name: int}. self.label is int.

        epochs = mne.EpochsArray(
            data=self.data,
            info=info,
            events=events,
            event_id=self.event_id,
            tmin=self.tmin,
            verbose=False,
        )

        return epochs
