"""Shared geometry projection and render capability policy."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

MontageCoordinateDimension = Literal[2, 3]


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
    "project_montage_geometry",
]
