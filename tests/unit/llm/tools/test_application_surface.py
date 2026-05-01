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
    assert result.error_type == "runtime"
    assert "Generate datasets" in result.message


def test_legacy_result_success_inference_handles_error_prefixes():
    assert legacy_tool_result_succeeded("Successfully loaded 1 files.") is True
    assert legacy_tool_result_succeeded("Error: paths list cannot be empty.") is False
    assert legacy_tool_result_succeeded("Dataset generation failed: no epoch") is False
