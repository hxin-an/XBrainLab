"""Direct tests for registry-backed prompt action policy."""

import pytest

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.prompt_policy import (
    DIRECT_ACTION_TOOL_NAMES,
    backend_command_from_prompt_authorization,
    classify_prompt_action,
    prompt_action_authorization,
    request_scoped_tool_names,
)


def test_direct_action_tool_names_do_not_drift_from_registry():
    expected = {
        "browse_files": frozenset({"list_files"}),
        "query_state": frozenset({"query_state", "get_dataset_info"}),
        "navigate": frozenset({"switch_panel"}),
        "scan_source": frozenset({"scan_source"}),
        "preview_interpretation": frozenset({"preview_interpretation"}),
        "validate_interpretation": frozenset({"validate_interpretation"}),
        "apply_interpretation": frozenset({"apply_interpretation"}),
        "save_interpretation_recipe": frozenset({"save_interpretation_recipe"}),
        "reload_interpretation_recipe": frozenset({"reload_interpretation_recipe"}),
        "attach_labels": frozenset({"attach_labels"}),
        "preprocess": frozenset(
            {
                "apply_standard_preprocess",
                "apply_bandpass_filter",
                "apply_notch_filter",
                "normalize_data",
                "resample_data",
                "select_channels",
                "set_reference",
            }
        ),
        "reset_preprocess": frozenset({"reset_preprocess"}),
        "apply_montage": frozenset({"set_montage"}),
        "create_epoch": frozenset({"epoch_data"}),
        "generate_dataset": frozenset({"generate_dataset"}),
        "configure_training": frozenset({"set_model", "configure_training"}),
        "train": frozenset({"start_training"}),
        "stop_training": frozenset({"stop_training"}),
        "reset_session": frozenset({"clear_dataset"}),
        "evaluate": frozenset({"evaluate"}),
        "visualize": frozenset({"visualize"}),
        "saliency": frozenset({"saliency"}),
    }

    assert expected == DIRECT_ACTION_TOOL_NAMES
    assert AGENT_ACTION_CONTRACTS.direct_action_tool_names() == DIRECT_ACTION_TOOL_NAMES


def test_request_scoping_preserves_command_first_and_ui_only_behavior():
    published = frozenset(
        {
            "query_state",
            "get_dataset_info",
            "list_files",
            "switch_panel",
            "apply_standard_preprocess",
            "apply_bandpass_filter",
        }
    )

    assert request_scoped_tool_names(published, intent="query_state") == frozenset(
        {"query_state"}
    )
    assert request_scoped_tool_names(published, intent="browse_files") == frozenset(
        {"list_files"}
    )
    assert request_scoped_tool_names(published, intent="navigate") == frozenset(
        {"switch_panel"}
    )
    assert request_scoped_tool_names(published, intent="preprocess") == frozenset(
        {"apply_standard_preprocess", "apply_bandpass_filter"}
    )


def test_host_selected_training_action_exposes_one_canonical_schema() -> None:
    published = frozenset({"set_model", "configure_training"})
    authorization = prompt_action_authorization(
        command_name="configure_training",
        tool_name="set_model",
    )

    assert request_scoped_tool_names(
        published,
        intent="configure_training",
        authorized_command=authorization,
    ) == frozenset({"set_model"})


def test_host_selected_preprocess_action_exposes_one_canonical_schema() -> None:
    published = frozenset(
        {
            "apply_standard_preprocess",
            "apply_bandpass_filter",
            "apply_notch_filter",
            "resample_data",
        }
    )
    authorization = prompt_action_authorization(
        command_name="preprocess",
        tool_name="resample_data",
    )

    assert request_scoped_tool_names(
        published,
        intent="preprocess",
        authorized_command=authorization,
    ) == frozenset({"resample_data"})


def test_prompt_action_authorization_rejects_tool_command_drift() -> None:
    try:
        prompt_action_authorization(
            command_name="configure_training",
            tool_name="resample_data",
        )
    except ValueError as exc:
        assert "does not implement" in str(exc)
    else:
        raise AssertionError("Mismatched prompt action authorization was accepted")


@pytest.mark.parametrize(
    "text",
    [
        "Use Deep4Net for this training setup.",
        "EEGConformer",
        "braindecode.atcnet",
    ],
)
def test_catalog_model_name_only_request_selects_model_schema(text: str) -> None:
    selection = classify_prompt_action(text, "configure_training")

    assert selection.tool_name == "set_model"
    assert selection.requires_clarification is False


def test_catalog_model_with_training_options_selects_full_configuration() -> None:
    selection = classify_prompt_action(
        "Use Deep4Net for 20 epochs with batch size 16.",
        "configure_training",
    )

    assert selection.tool_name == "configure_training"


@pytest.mark.parametrize(
    ("text", "expected_tool"),
    [
        ("Apply a 4 to 40 Hz band-pass filter.", "apply_bandpass_filter"),
        ("Resample the recordings to 250 Hz.", "resample_data"),
        (
            "Run standard preprocessing with band-pass and notch filtering.",
            "apply_standard_preprocess",
        ),
    ],
)
def test_preprocess_request_selects_only_semantically_exact_schema(
    text: str,
    expected_tool: str,
) -> None:
    selection = classify_prompt_action(text, "preprocess")

    assert selection.tool_name == expected_tool
    assert selection.requires_clarification is False


@pytest.mark.parametrize(
    "text",
    [
        "Preprocess the recordings.",
        "Apply band-pass filtering and then resample the recordings.",
    ],
)
def test_ambiguous_preprocess_request_requires_clarification(text: str) -> None:
    selection = classify_prompt_action(text, "preprocess")

    assert selection.tool_name is None
    assert "standard preprocessing pipeline" in selection.clarification_message


def test_explicit_navigation_exposes_only_switch_panel() -> None:
    published = frozenset(
        {
            "clear_dataset",
            "configure_training",
            "list_files",
            "query_state",
            "reload_interpretation_recipe",
            "scan_source",
            "set_model",
            "switch_panel",
        }
    )
    selection = classify_prompt_action(
        "Go to the next workflow workspace panel.",
        "",
    )
    assert selection.tool_name == "switch_panel"
    assert selection.action_name == "navigate"
    authorization = prompt_action_authorization(
        command_name=selection.action_name,
        tool_name=selection.tool_name,
    )

    assert request_scoped_tool_names(
        published,
        intent="unknown",
        authorized_command=authorization,
    ) == frozenset({"switch_panel"})
    assert backend_command_from_prompt_authorization(authorization) == "navigate"
