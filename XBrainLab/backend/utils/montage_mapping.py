"""Montage channel-name matching helpers.

This module owns the fuzzy channel cleanup that used to live inside the legacy
``BackendFacade.set_montage`` path. Keeping it here makes the behavior directly
testable and reusable by command/UI confirmation paths before the facade is
physically removed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import SupportsFloat

PositionValue = SupportsFloat | str
PositionInput = Sequence[PositionValue]
Position3D = tuple[float, float, float]


@dataclass(frozen=True)
class MontageChannelMapping:
    """Result of mapping dataset channels to standard montage positions."""

    channels: list[str]
    positions: list[Position3D]
    matched_count: int
    total_count: int

    @property
    def full_match(self) -> bool:
        """Whether every requested channel was mapped."""
        return self.matched_count == self.total_count

    @property
    def has_matches(self) -> bool:
        """Whether at least one requested channel was mapped."""
        return self.matched_count > 0


def normalize_channel_name_for_montage(channel_name: str) -> str:
    """Normalize noisy EEG channel labels for standard montage lookup."""
    return (
        channel_name.lower()
        .replace("eeg", "")
        .replace("ref", "")
        .replace("-", "")
        .strip()
    )


def resolve_montage_channel_name(
    channel_name: str,
    montage_channel_names: Sequence[str],
) -> str | None:
    """Resolve a dataset channel name to a standard montage channel name."""
    montage_lookup = {name.lower(): name for name in montage_channel_names}
    channel_key = channel_name.lower()
    if channel_key in montage_lookup:
        return montage_lookup[channel_key]

    clean_channel_key = normalize_channel_name_for_montage(channel_name)
    return montage_lookup.get(clean_channel_key)


def _coerce_position_3d(position: PositionInput) -> Position3D:
    values = tuple(float(value) for value in position)
    if len(values) != 3:
        raise ValueError("Montage positions must contain exactly three values.")
    return (values[0], values[1], values[2])


def map_channels_to_montage_positions(
    current_channels: Sequence[str],
    montage_positions: Mapping[str, PositionInput],
) -> MontageChannelMapping:
    """Map current dataset channel names to montage positions.

    The returned channel names preserve the original dataset names because those
    are the channels that downstream ``ApplyMontageCommand`` applies to.
    """
    mapped_channels: list[str] = []
    mapped_positions: list[Position3D] = []
    montage_channel_names = tuple(montage_positions.keys())

    for channel_name in current_channels:
        montage_channel_name = resolve_montage_channel_name(
            channel_name,
            montage_channel_names,
        )
        if montage_channel_name is None:
            continue

        mapped_channels.append(channel_name)
        mapped_positions.append(
            _coerce_position_3d(montage_positions[montage_channel_name]),
        )

    return MontageChannelMapping(
        channels=mapped_channels,
        positions=mapped_positions,
        matched_count=len(mapped_channels),
        total_count=len(current_channels),
    )
