"""Tests for montage channel-name matching outside the legacy facade."""

import pytest

from XBrainLab.backend.utils.montage_mapping import (
    map_channels_to_montage_positions,
    normalize_channel_name_for_montage,
    resolve_montage_channel_name,
)


def test_exact_matches_preserve_dataset_channel_names_and_coerce_positions() -> None:
    mapping = map_channels_to_montage_positions(
        ["Fp1", "Fp2", "Cz"],
        {
            "Fp1": [0, 1, 2],
            "Fp2": ("0.4", "0.5", "0.6"),
            "Cz": (0.7, 0.8, 0.9),
        },
    )

    assert mapping.channels == ["Fp1", "Fp2", "Cz"]
    assert mapping.positions == [
        (0.0, 1.0, 2.0),
        (0.4, 0.5, 0.6),
        (0.7, 0.8, 0.9),
    ]
    assert mapping.matched_count == 3
    assert mapping.total_count == 3
    assert mapping.full_match
    assert mapping.has_matches


def test_fuzzy_matches_eeg_ref_and_hyphen_noise() -> None:
    mapping = map_channels_to_montage_positions(
        ["EEGFp1", "Fp2-ref", "EEG-Cz-Ref"],
        {
            "Fp1": (0.1, 0.2, 0.3),
            "Fp2": (0.4, 0.5, 0.6),
            "Cz": (0.7, 0.8, 0.9),
        },
    )

    assert mapping.channels == ["EEGFp1", "Fp2-ref", "EEG-Cz-Ref"]
    assert mapping.positions == [
        (0.1, 0.2, 0.3),
        (0.4, 0.5, 0.6),
        (0.7, 0.8, 0.9),
    ]
    assert mapping.full_match


def test_partial_match_reports_counts_without_filling_unknown_channels() -> None:
    mapping = map_channels_to_montage_positions(
        ["Fp1", "Missing", "Cz"],
        {
            "Fp1": (0.1, 0.2, 0.3),
            "Cz": (0.7, 0.8, 0.9),
        },
    )

    assert mapping.channels == ["Fp1", "Cz"]
    assert mapping.matched_count == 2
    assert mapping.total_count == 3
    assert not mapping.full_match


def test_no_match_is_explicit() -> None:
    mapping = map_channels_to_montage_positions(
        ["Fp1", "Fp2"],
        {"O1": (0.1, 0.2, 0.3)},
    )

    assert mapping.channels == []
    assert mapping.positions == []
    assert mapping.matched_count == 0
    assert mapping.total_count == 2
    assert not mapping.full_match
    assert not mapping.has_matches


def test_resolve_channel_name_prefers_exact_case_insensitive_match() -> None:
    assert resolve_montage_channel_name("fp1", ["Fp1", "Fp2"]) == "Fp1"


def test_normalize_channel_name_for_montage_matches_legacy_cleanup() -> None:
    assert normalize_channel_name_for_montage(" EEG-Fp1-Ref ") == "fp1"


def test_malformed_position_vector_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="three values"):
        map_channels_to_montage_positions(
            ["Fp1"],
            {"Fp1": (0.1, 0.2)},
        )
