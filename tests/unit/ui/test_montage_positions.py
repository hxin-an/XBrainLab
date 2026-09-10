"""Coordinate ordering and validation at the UI-to-montage-command boundary."""

import pytest

from XBrainLab.ui.montage_positions import normalize_montage_positions


def test_mapping_positions_follow_selected_channel_order_without_mutation():
    channels = ["C4", "C3"]
    positions = {"C3": ("1", "2", "3"), "C4": ("4", "5", "6")}

    result = normalize_montage_positions(channels, positions)

    assert result == [(4.0, 5.0, 6.0), (1.0, 2.0, 3.0)]
    assert all(isinstance(value, float) for point in result for value in point)
    assert channels == ["C4", "C3"]
    assert positions == {"C3": ("1", "2", "3"), "C4": ("4", "5", "6")}


def test_iterable_positions_preserve_pairing_and_consume_coordinate_iterables():
    coordinates = [("4", "5", "6"), ("1", "2", "3")]

    result = normalize_montage_positions(
        ["C4", "C3"], (iter(point) for point in coordinates)
    )

    assert result == [(4.0, 5.0, 6.0), (1.0, 2.0, 3.0)]
    assert coordinates == [("4", "5", "6"), ("1", "2", "3")]


def test_empty_positions_remain_empty():
    assert normalize_montage_positions([], []) == []


@pytest.mark.parametrize("positions", [[], [(1, 2, 3), (4, 5, 6)]])
def test_position_count_must_match_selected_channels(positions):
    with pytest.raises(ValueError, match="equal length"):
        normalize_montage_positions(["C3"], positions)


@pytest.mark.parametrize("point", [(1, 2), (1, 2, 3, 4)])
def test_coordinates_must_be_three_dimensional(point):
    with pytest.raises(ValueError, match="x, y, z"):
        normalize_montage_positions(["C3"], [point])


def test_missing_selected_channel_does_not_substitute_another_position():
    with pytest.raises(KeyError, match="C4"):
        normalize_montage_positions(["C4"], {"C3": (1, 2, 3)})


def test_invalid_coordinate_is_rejected_instead_of_coerced_to_zero():
    with pytest.raises(ValueError):
        normalize_montage_positions(["C3"], [(1, "not-a-number", 3)])
