from __future__ import annotations

import inspect

from XBrainLab.backend.application import montage_capability
from XBrainLab.backend.application.montage_capability import (
    montage_geometry_capabilities,
    project_montage_geometry,
)


def test_generic_montage_policy_does_not_depend_on_bids_parser() -> None:
    source = inspect.getsource(montage_capability)

    assert "bids_montage_preparation" not in source


def test_rank_policy_distinguishes_topographic_and_three_dimensional_geometry() -> None:
    planar = ((-1.0, 1.0, 0.0), (1.0, 1.0, 0.0), (0.0, -1.0, 0.0))
    spatial = (*planar, (0.0, 0.0, 1.0))

    assert montage_geometry_capabilities(
        planar,
        coordinate_dimension=2,
    ) == (True, False)
    assert montage_geometry_capabilities(
        spatial,
        coordinate_dimension=3,
    ) == (True, True)

    projection = project_montage_geometry(
        spatial,
        coordinate_dimension=3,
    )
    assert projection.positions == spatial
    assert projection.supports_view("topographic_map") is True
    assert projection.supports_view("three_dimensional") is True
