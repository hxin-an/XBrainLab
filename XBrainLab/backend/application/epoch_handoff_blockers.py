"""Typed blocker contract for Data Interpretation epoch handoff."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EpochHandoffBlockerCode(str, Enum):
    """Stable policy identifiers for supervised epoch handoff blockers."""

    IMPORT_NOT_APPLIED = "import_not_applied"
    UNRESOLVED_EXTERNAL_VALUES = "unresolved_external_values"
    MISSING_REVIEWED_TARGET = "missing_reviewed_target"
    LABELS_NOT_APPLIED = "labels_not_applied"
    MISSING_CLASS_LABELS = "missing_class_labels"
    INSUFFICIENT_USABLE_CLASSES = "insufficient_usable_classes"


@dataclass(frozen=True)
class EpochHandoffBlocker:
    """A stable policy code paired with user-facing explanation text."""

    code: EpochHandoffBlockerCode
    message: str


def serialize_epoch_handoff_blockers(
    blockers: list[EpochHandoffBlocker],
) -> tuple[list[str], list[str]]:
    """Return backward-compatible messages plus stable serialized codes."""
    return (
        [blocker.message for blocker in blockers],
        [blocker.code.value for blocker in blockers],
    )


def decode_epoch_handoff_blocker_codes(
    raw_codes: object,
    *,
    expected_count: int,
) -> tuple[EpochHandoffBlockerCode, ...] | None:
    """Decode a complete code list, returning ``None`` for legacy/invalid data."""
    if (
        not isinstance(raw_codes, list)
        or not raw_codes
        or len(raw_codes) != expected_count
    ):
        return None

    decoded: list[EpochHandoffBlockerCode] = []
    for raw_code in raw_codes:
        if not isinstance(raw_code, str):
            return None
        try:
            decoded.append(EpochHandoffBlockerCode(raw_code))
        except ValueError:
            return None
    return tuple(decoded)
