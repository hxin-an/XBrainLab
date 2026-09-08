"""Shared geometry projection and render capability policy."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

MontageCoordinateDimension = Literal[2, 3]


def montage_layout_issues(
    selected_channels: Iterable[str],
    mapped_channels: Iterable[str],
    electrode_names: Iterable[str],
    positions: Iterable[Any],
    *,
    valid_electrodes: Iterable[str] | None = None,
) -> tuple[tuple[str | None, str], ...]:
    """Return row/global issues for one complete topographic channel layout.

    ``Select Channels`` owns which channels are retained.  A montage therefore
    has to cover that exact selection; it must not silently turn a partial map
    into a different dataset geometry.
    """
    selected = tuple(str(channel) for channel in selected_channels)
    mapped = tuple(str(channel) for channel in mapped_channels)
    electrodes = tuple(str(electrode) for electrode in electrode_names)
    coordinate_rows = tuple(positions)
    issues: dict[str | None, str] = {}

    if (
        not selected
        or len(set(selected)) != len(selected)
        or any(not channel for channel in selected)
    ):
        return ((None, "Selected channels must be non-empty and unique."),)
    if len(mapped) != len(electrodes) or len(mapped) != len(coordinate_rows):
        return ((None, "Each selected channel needs one electrode position."),)

    selected_set = set(selected)
    mapped_indices: dict[str, int] = {}
    for index, channel in enumerate(mapped):
        if channel not in selected_set:
            issues[None] = "Mapped channels must match the selected channels."
            continue
        if channel in mapped_indices:
            issues[channel] = "Each selected channel can be mapped once."
            continue
        mapped_indices[channel] = index
    for channel in selected:
        if channel not in mapped_indices:
            issues[channel] = "Choose an electrode."

    allowed = None if valid_electrodes is None else set(valid_electrodes)
    electrode_rows: dict[str, list[str]] = {}
    for channel, index in mapped_indices.items():
        electrode = electrodes[index]
        if not electrode:
            issues[channel] = "Choose an electrode."
        elif allowed is not None and electrode not in allowed:
            issues[channel] = "Choose an electrode from this layout."
        else:
            electrode_rows.setdefault(electrode, []).append(channel)
    for channels in electrode_rows.values():
        if len(channels) > 1:
            for channel in channels:
                issues[channel] = "Each electrode can be used once."

    if issues:
        return tuple(issues.items())
    for channel, index in mapped_indices.items():
        if not project_montage_geometry(
            (coordinate_rows[index],),
            coordinate_dimension=3,
        ).positions:
            issues[channel] = "This electrode position is not usable."
    if issues:
        return tuple(issues.items())
    projected = project_montage_geometry(
        coordinate_rows,
        coordinate_dimension=3,
    )
    if not projected.supports_topographic:
        return ((None, "Mapped positions do not support a topographic map."),)
    return ()


def montage_geometry_capabilities(
    positions: tuple[tuple[float, float, float], ...],
    *,
    coordinate_dimension: MontageCoordinateDimension | None,
) -> tuple[bool, bool]:
    """Return view support without treating sparse or 2-D geometry as 3-D."""
    if coordinate_dimension not in {2, 3} or not positions:
        return False, False
    values = np.asarray(positions, dtype=float)
    centered_xy = values[:, :2] - values[:, :2].mean(axis=0, keepdims=True)
    topographic = len(values) >= 3 and np.linalg.matrix_rank(centered_xy) >= 2
    centered_xyz = values - values.mean(axis=0, keepdims=True)
    three_dimensional = (
        coordinate_dimension == 3
        and len(values) >= 4
        and np.linalg.matrix_rank(centered_xyz) >= 3
    )
    return bool(topographic), bool(three_dimensional)


@dataclass(frozen=True, slots=True)
class MontageGeometryProjection:
    """Normalized finite geometry and the views admitted by its spatial rank."""

    positions: tuple[tuple[float, float, float], ...]
    supports_topographic: bool
    supports_three_dimensional: bool

    def supports_view(self, view: str) -> bool:
        """Return whether this geometry supports a position-dependent view."""
        if view == "topographic_map":
            return self.supports_topographic
        if view == "three_dimensional":
            return self.supports_three_dimensional
        return False


def project_montage_geometry(
    positions: Iterable[Any],
    *,
    coordinate_dimension: MontageCoordinateDimension | None,
) -> MontageGeometryProjection:
    """Normalize geometry before applying the canonical montage rank policy."""
    normalized: list[tuple[float, float, float]] = []
    try:
        rows = tuple(positions)
    except TypeError:
        rows = ()
    for row in rows:
        if isinstance(row, (str, bytes)) or not isinstance(row, Iterable):
            return MontageGeometryProjection((), False, False)
        try:
            coordinates = tuple(float(value) for value in row)
        except (TypeError, ValueError):
            return MontageGeometryProjection((), False, False)
        if len(coordinates) != 3 or not all(map(math.isfinite, coordinates)):
            return MontageGeometryProjection((), False, False)
        normalized.append(coordinates)

    projected = tuple(normalized)
    supports_topographic, supports_three_dimensional = montage_geometry_capabilities(
        projected,
        coordinate_dimension=coordinate_dimension,
    )
    return MontageGeometryProjection(
        positions=projected,
        supports_topographic=supports_topographic,
        supports_three_dimensional=supports_three_dimensional,
    )


__all__ = [
    "MontageCoordinateDimension",
    "MontageGeometryProjection",
    "montage_geometry_capabilities",
    "montage_layout_issues",
    "project_montage_geometry",
]
