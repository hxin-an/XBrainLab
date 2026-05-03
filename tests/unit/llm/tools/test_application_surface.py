"""Tests for the ApplicationService-backed agent tool surface."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.application_surface import (
    CapabilityPolicyUnavailable,
    blocked_tool_reasons,
    build_agent_tool_policy,
    execute_application_tool_command,
    legacy_tool_result_succeeded,
    normalize_tool_result,
)


def test_agent_tool_policy_reuses_application_train_reasons():
    study = Study()
    facade = BackendFacade(study)

    application_train = facade.get_capabilities().get(CommandName.TRAIN)
    tool_policy = build_agent_tool_policy(study)

    start_training = tool_policy["start_training"]
    assert start_training.enabled is False
    assert start_training.command_name == CommandName.TRAIN.value
    assert start_training.reasons == tuple(application_train.reasons)
    assert "Generate datasets before training." in start_training.reasons


def test_blocked_tool_reasons_are_grouped_by_application_command():
    blocked = blocked_tool_reasons(Study())

    assert "train" in blocked
    assert "preprocess" in blocked
    assert "start_training" not in blocked
    assert "apply_bandpass_filter" not in blocked


def test_clear_dataset_surface_preserves_reset_confirmation_boundary():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.is_raw.return_value = True
    study.data_manager.loaded_data_list = [raw]

    clear_dataset = build_agent_tool_policy(study)["clear_dataset"]

    assert clear_dataset.enabled is True
    assert clear_dataset.command_name == CommandName.RESET_SESSION.value
    assert clear_dataset.destructive is True
    assert clear_dataset.confirmation_required is True


def test_data_interpretation_surface_preserves_autonomy_policy(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    policy = build_agent_tool_policy(study)
    scan_source = policy["scan_source"]

    assert scan_source.enabled is True
    assert scan_source.command_name == CommandName.SCAN_SOURCE.value
    assert scan_source.can_auto_execute is True
    assert scan_source.decision_boundary == "read_only_discovery"

    assert execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    ).ok
    assert execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    ).ok
    assert execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    ).ok

    apply_interpretation = build_agent_tool_policy(study)["apply_interpretation"]

    assert apply_interpretation.enabled is True
    assert apply_interpretation.command_name == CommandName.APPLY_INTERPRETATION.value
    assert apply_interpretation.confirmation_required is True
    assert apply_interpretation.requires_confirmation is True
    assert apply_interpretation.can_auto_execute is False
    assert apply_interpretation.stop_after_success is True
    assert apply_interpretation.blocks_downstream_until_confirmed is True
    assert apply_interpretation.to_dict()["decision_boundary"] == "semantic_apply"


def test_application_tool_command_routes_data_interpretation_scan(tmp_path):
    source = tmp_path / "sample.fif"
    source.write_bytes(b"placeholder")

    result = execute_application_tool_command(
        Study(),
        "scan_source",
        {"source_path": str(source), "source_hint": "file"},
    )

    assert result is not None
    assert result.ok is True
    assert result.command_name == CommandName.SCAN_SOURCE.value
    assert result.raw_result["diagnostics"]["payload_type"] == "scan_result"


def test_application_tool_command_apply_surfaces_confirmation_required(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    assert execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    ).ok
    assert execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    ).ok
    assert execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    ).ok

    result = execute_application_tool_command(study, "apply_interpretation", {})

    assert result is not None
    assert result.ok is False
    assert result.command_name == CommandName.APPLY_INTERPRETATION.value
    assert result.error_type == "confirmation_required"


def test_application_surface_requires_real_study():
    with pytest.raises(CapabilityPolicyUnavailable):
        build_agent_tool_policy(MagicMock())


def test_legacy_error_string_becomes_failed_structured_result():
    result = normalize_tool_result(
        Study(),
        "start_training",
        "Failed to start training: Generate datasets before training.",
    )

    assert result.ok is False
    assert result.command_name == CommandName.TRAIN.value
    assert result.error_type == "precondition"
    assert "Generate datasets" in result.message


def test_legacy_result_success_inference_handles_error_prefixes():
    assert legacy_tool_result_succeeded("Successfully loaded 1 files.") is True
    assert legacy_tool_result_succeeded("Error: paths list cannot be empty.") is False
    assert legacy_tool_result_succeeded("Dataset generation failed: no epoch") is False


def test_application_tool_command_returns_structured_result_for_model_config():
    study = Study()

    result = execute_application_tool_command(
        study,
        "set_model",
        {"model_name": "EEGNet"},
    )

    assert result is not None
    assert result.ok is True
    assert result.command_name == CommandName.CONFIGURE_TRAINING.value
    assert result.raw_result["status"] == "ok"
    assert study.model_holder.target_model.__name__ == "EEGNet"


def test_application_tool_command_routes_load_data_to_command_surface(tmp_path):
    sample = tmp_path / "sample.unsupported"
    sample.write_text("not eeg", encoding="utf-8")

    result = execute_application_tool_command(
        Study(),
        "load_data",
        {"paths": [str(sample)]},
    )

    assert result is not None
    assert result.ok is False
    assert result.command_name == CommandName.LOAD_DATA.value
    assert result.raw_result["status"] == "failed"


def test_application_tool_command_leaves_ui_request_tools_on_legacy_path():
    assert (
        execute_application_tool_command(
            Study(),
            "set_montage",
            {"montage_name": "standard_1020"},
        )
        is None
    )
