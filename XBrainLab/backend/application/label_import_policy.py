"""Bounded product policy for materialized external label mappings."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from .errors import PreconditionError

MAX_LABEL_MAPPING_CARDINALITY = 256
MAX_LABEL_PREVIEW_FILES = 64
MAX_LABEL_PREVIEW_TEXT_LENGTH = 512
MAX_LABEL_PREVIEW_PATH_LENGTH = 4096

_CARDINALITY_SUGGESTIONS = [
    "select the label field that contains class or event codes",
    "convert the source to a bounded class or event column",
]
_FILE_COUNT_SUGGESTIONS = [
    "select label files for a matching EEG subset or smaller batch"
]


@dataclass(frozen=True, slots=True)
class LabelMaterializationReview:
    """Bounded metadata derived without copying a materialized label payload."""

    unique_labels: tuple[Any, ...]
    files: tuple[dict[str, Any], ...]
    mode: str
    target_count: int | None
    total_label_count: int


def materialize_reviewed_label_map(
    paths: Iterable[str],
    *,
    load: Callable[[str], Any],
    error_code: str,
    normalize_value: Callable[[Any], Any],
    validate_value: Callable[[Any, str], None] | None = None,
) -> tuple[dict[str, Any], LabelMaterializationReview]:
    """Load and review one file at a time, stopping before the next parser call."""
    reviewer = _LabelMaterializationReviewer(
        error_code=error_code,
        normalize_value=normalize_value,
        validate_value=validate_value,
    )
    label_map: dict[str, Any] = {}
    for raw_path in paths:
        path = str(raw_path)
        payload = load(path)
        reviewer.add(path=path, payload=payload)
        label_map[path] = payload
    return label_map, reviewer.finish()


class _LabelMaterializationReviewer:
    """Accumulate only bounded review metadata across sequential parser results."""

    def __init__(
        self,
        *,
        error_code: str,
        normalize_value: Callable[[Any], Any],
        validate_value: Callable[[Any, str], None] | None,
    ) -> None:
        self._error_code = error_code
        self._normalize_value = normalize_value
        self._validate_value = validate_value
        self._unique: dict[Any, None] = {}
        self._files: list[dict[str, Any]] = []
        self._modes: set[str] = set()
        self._sequence_lengths: list[int] = []
        self._total_count = 0

    def add(self, *, path: str, payload: Any) -> None:
        """Review one payload before its caller proceeds to the next file."""
        timestamp = _is_timestamp_payload(payload)
        mode = "timestamp" if timestamp else "sequence"
        values: Iterable[Any]
        if timestamp:
            count = len(payload)
            values = (row.get("label") for row in payload)
        else:
            array = np.asarray(payload)
            count = int(array.size)
            values = iter(array.flat)

        for raw_value in values:
            value = self._normalize_value(raw_value)
            if self._validate_value is not None:
                self._validate_value(value, path)
            try:
                is_new = value not in self._unique
            except TypeError as exc:
                raise PreconditionError(
                    "The selected label field contains an unsupported mapping value.",
                    diagnostics={
                        "code": "label_mapping_value_unsupported",
                        "path": path,
                        "value_type": type(value).__name__,
                    },
                ) from exc
            if not is_new:
                continue
            self._unique[value] = None
            if len(self._unique) > MAX_LABEL_MAPPING_CARDINALITY:
                raise_label_cardinality_error(code=self._error_code)

        self._modes.add(mode)
        if not timestamp:
            self._sequence_lengths.append(count)
        self._total_count += count
        self._files.append(
            {
                "path": path,
                "mode": mode,
                "label_count": count,
            }
        )

    def finish(self) -> LabelMaterializationReview:
        mode = next(iter(self._modes)) if len(self._modes) == 1 else "mixed"
        target_count = (
            self._sequence_lengths[0]
            if mode == "sequence"
            and self._sequence_lengths
            and len(set(self._sequence_lengths)) == 1
            else None
        )
        return LabelMaterializationReview(
            unique_labels=tuple(self._unique),
            files=tuple(self._files),
            mode=mode,
            target_count=target_count,
            total_label_count=self._total_count,
        )


def enforce_public_label_mapping_cardinality(mapping: Any) -> None:
    """Reject an oversized caller-supplied mapping without copying its keys."""
    if not isinstance(mapping, Mapping):
        return
    for observed, _key in enumerate(mapping, start=1):
        if observed > MAX_LABEL_MAPPING_CARDINALITY:
            raise_label_cardinality_error(code="label_mapping_cardinality_exceeded")


def enforce_label_file_count(
    observed_count: int,
    *,
    code: str,
) -> None:
    """Keep one external-label request aligned to one reviewable EEG subset."""
    if observed_count <= MAX_LABEL_PREVIEW_FILES:
        return
    raise PreconditionError(
        f"{observed_count} label files were selected, but one mapping review "
        f"supports at most {MAX_LABEL_PREVIEW_FILES}. Select label files for a "
        "matching EEG subset or smaller batch, then retry.",
        diagnostics={
            "code": code,
            "observed_count": observed_count,
            "limit": MAX_LABEL_PREVIEW_FILES,
            "suggestions": list(_FILE_COUNT_SUGGESTIONS),
        },
    )


def raise_label_cardinality_error(*, code: str) -> None:
    """Report the first proven lower bound and stop inspecting the payload."""
    observed_at_least = MAX_LABEL_MAPPING_CARDINALITY + 1
    raise PreconditionError(
        "This external label selection contains at least "
        f"{observed_at_least} distinct values, but one label mapping supports at "
        f"most {MAX_LABEL_MAPPING_CARDINALITY} class or event codes. Select the "
        "correct label field or convert the source before retrying.",
        diagnostics={
            "code": code,
            "observed_count": observed_at_least,
            "observed_count_is_lower_bound": True,
            "limit": MAX_LABEL_MAPPING_CARDINALITY,
            "suggestions": list(_CARDINALITY_SUGGESTIONS),
        },
    )


def _is_timestamp_payload(payload: Any) -> bool:
    return bool(isinstance(payload, list) and payload and isinstance(payload[0], dict))
