"""Direct tests for registry-backed prompt action policy."""

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.prompt_policy import (
    DIRECT_ACTION_TOOL_NAMES,
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
