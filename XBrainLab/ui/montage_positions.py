"""Shared helpers for UI montage position command arguments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def normalize_montage_positions(
    channels: Sequence[str],
    positions: Mapping[str, Iterable[Any]] | Iterable[Iterable[Any]],
) -> list[tuple[float, float, float]]:
    """Return montage positions as JSON-safe ``(x, y, z)`` tuples."""
    if isinstance(positions, Mapping):
        position_values = [positions[channel] for channel in channels]
    else:
        position_values = list(positions)

    if len(position_values) != len(channels):
        raise ValueError("channels and positions must have equal length.")

    normalized: list[tuple[float, float, float]] = []
    for position in position_values:
        coords = list(position)
        if len(coords) != 3:
            raise ValueError("Each montage position must contain x, y, z values.")
        normalized.append((float(coords[0]), float(coords[1]), float(coords[2])))
    return normalized
