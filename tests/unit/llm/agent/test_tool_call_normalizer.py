"""Stable-v2 tool proposals are never rewritten by Host heuristics."""

from __future__ import annotations

import pytest

from XBrainLab.llm.agent.tool_call_normalizer import normalize_tool_call


@pytest.mark.parametrize(
    ("tool_name", "params"),
    (
        ("create_epochs", {}),
        ("import_eeg_data", {}),
        ("apply_bandpass_filter", {"low_freq": 4.0, "high_freq": 38.0}),
        ("normalize_data", {"method": "z-score"}),
        ("switch_panel", {"panel_name": "visualization", "view_mode": "3d_plot"}),
        ("respond_to_user", {"message": "Choose the first action to run."}),
    ),
)
def test_normalizer_preserves_exact_target_proposal(
    tool_name: str,
    params: dict[str, object],
) -> None:
    original = dict(params)

    assert normalize_tool_call(
        tool_name,
        params,
        latest_user_text="Text must not authorize or fill anything.",
        published_tool_names=frozenset({tool_name}),
    ) == (tool_name, original)
    assert params == original


@pytest.mark.parametrize(
    ("legacy_name", "replacement"),
    (
        ("create_epoch", "create_epochs"),
        ("train", "start_training"),
        ("preprocess", "apply_bandpass_filter"),
        ("get_state", "respond_to_user"),
    ),
)
def test_normalizer_does_not_alias_retired_names(
    legacy_name: str,
    replacement: str,
) -> None:
    normalized_name, normalized_params = normalize_tool_call(
        legacy_name,
        {"confirmed": True},
        latest_user_text="Run it now with 4 to 38 Hz.",
    )

    assert normalized_name == legacy_name
    assert normalized_name != replacement
    assert normalized_params == {"confirmed": True}


def test_normalizer_does_not_infer_or_rename_parameters() -> None:
    params = {
        "low_frequency": 4,
        "high_frequency": 38,
        "resource_preflight_confirmed": True,
        "extra": None,
    }

    assert normalize_tool_call(
        "apply_bandpass_filter",
        params,
        latest_user_text="Use a 1 to 40 Hz bandpass instead.",
    ) == ("apply_bandpass_filter", params)
