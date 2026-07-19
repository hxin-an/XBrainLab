"""Shared minimum-class policy for supervised EEG workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

MINIMUM_SUPERVISED_CLASS_COUNT = 2
INSUFFICIENT_USABLE_CLASSES_KIND = "insufficient_usable_classes"


def usable_class_labels(
    labels_and_counts: Iterable[tuple[Any, Any]],
) -> tuple[str, ...]:
    """Return distinct class labels backed by at least one usable trial."""
    labels: set[str] = set()
    for raw_label, raw_count in labels_and_counts:
        label = str(raw_label).strip()
        if not label:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError, OverflowError):
            continue
        if count > 0:
            labels.add(label)
    return tuple(sorted(labels, key=str.casefold))


def has_minimum_usable_classes(labels: Iterable[str]) -> bool:
    """Return whether distinct non-empty labels meet supervised minimums."""
    normalized = {str(label).strip() for label in labels if str(label).strip()}
    return len(normalized) >= MINIMUM_SUPERVISED_CLASS_COUNT


def insufficient_usable_classes_message(labels: Iterable[str]) -> str:
    """Build one concrete blocker shared by handoff, capability, and audit."""
    normalized = sorted(
        {str(label).strip() for label in labels if str(label).strip()},
        key=str.casefold,
    )
    detail = ", ".join(normalized) if normalized else "none"
    return (
        "Supervised workflows require at least "
        f"{MINIMUM_SUPERVISED_CLASS_COUNT} selected class labels with usable "
        f"trials; found {len(normalized)} ({detail})."
    )
