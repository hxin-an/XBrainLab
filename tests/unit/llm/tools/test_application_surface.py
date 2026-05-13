"""Tests for the ApplicationService-backed agent tool surface."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import CommandName, get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.application_surface import (
    CapabilityPolicyUnavailable,
    ToolCommandResult,
    blocked_tool_reasons,
    build_agent_tool_policy,
    execute_application_tool_command,
    legacy_tool_result_succeeded,
    normalize_tool_result,
)


def _assert_tool_command_result(
    result: object,
    *,
    tool_name: str,
    command_name: CommandName,
    ok: bool | None = None,
    error_type: str | None = None,
    raw_status: str | None = None,
) -> ToolCommandResult:
    assert isinstance(result, ToolCommandResult), result
    assert result.tool_name == tool_name
    assert result.command_name == command_name.value
    assert isinstance(result.state, dict)
    assert isinstance(result.capability, dict)
    assert result.capability["tool_name"] == tool_name
    assert result.capability["command_name"] == command_name.value
    if ok is not None:
        assert result.ok is ok
    if error_type is not None:
        assert result.error_type == error_type
    if raw_status is not None:
        assert isinstance(result.raw_result, dict)
        assert result.raw_result["status"] == raw_status
        assert result.raw_result["command_name"] == command_name.value
    return result


def _state(result: ToolCommandResult) -> dict[str, Any]:
    assert isinstance(result.state, dict)
    return result.state


def test_agent_tool_policy_reuses_application_train_reasons():
    study = Study()
    service = get_application_service(study)

    application_train = service.get_capabilities().get(CommandName.TRAIN)
    tool_policy = build_agent_tool_policy(study)

    start_training = tool_policy["start_training"]
    assert start_training.enabled is False
    assert start_training.command_name == CommandName.TRAIN.value
    assert start_training.reasons == tuple(application_train.reasons)
    assert "Generate datasets before training." in start_training.reasons


def test_start_training_surface_preserves_backend_confirmation_boundary():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    study.loaded_data_list = [raw]
    cast(Any, study).datasets = [object()]
    cast(Any, study).model_holder = object()
    cast(Any, study).training_option = object()
    training = study.get_controller("training")
    training.start_training = MagicMock()

    unconfirmed = execute_application_tool_command(study, "start_training", {})
    confirmed = execute_application_tool_command(
        study,
        "start_training",
        {"confirmed": True},
    )

    unconfirmed = _assert_tool_command_result(
        unconfirmed,
        tool_name="start_training",
        command_name=CommandName.TRAIN,
        ok=False,
        error_type="confirmation_required",
        raw_status="failed",
    )
    assert unconfirmed.blocked_reason == "train requires confirmation."
    assert unconfirmed.raw_result["changed_state"]["error_changed"] is True
    confirmed = _assert_tool_command_result(
        confirmed,
        tool_name="start_training",
        command_name=CommandName.TRAIN,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert confirmed.message == "Training started."
    assert confirmed.raw_result["diagnostics"] == {
        "append": True,
        "interactive": True,
    }
    training.start_training.assert_called_once()


def test_blocked_tool_reasons_are_grouped_by_application_command():
    blocked = blocked_tool_reasons(Study())

    assert "train" in blocked
    assert "preprocess" in blocked
    assert "start_training" not in blocked
    assert "apply_bandpass_filter" not in blocked


def test_mapped_tool_missing_params_returns_input_failure():
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    study.data_manager.loaded_data_list = [raw]

    result = execute_application_tool_command(study, "apply_bandpass_filter", {})

    result = _assert_tool_command_result(
        result,
        tool_name="apply_bandpass_filter",
        command_name=CommandName.PREPROCESS,
        ok=False,
        error_type="input",
    )
    assert "Required inputs" in result.message


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

    scan_result = execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    )
    scan_result = _assert_tool_command_result(
        scan_result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert scan_result.raw_result["diagnostics"]["payload_type"] == "scan_result"

    preview_result = execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    )
    preview_result = _assert_tool_command_result(
        preview_result,
        tool_name="preview_interpretation",
        command_name=CommandName.PREVIEW_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )

    validate_result = execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    )
    validate_result = _assert_tool_command_result(
        validate_result,
        tool_name="validate_interpretation",
        command_name=CommandName.VALIDATE_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(validate_result)["interpretation"]["has_validation_decision"] is True

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

    result = _assert_tool_command_result(
        result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert result.raw_result["diagnostics"]["payload_type"] == "scan_result"


def test_application_tool_command_routes_scan_label_sources(tmp_path):
    source_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    source_dir.mkdir()
    label_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    label_path = label_dir / "sub-01_task-mi_events.tsv"
    eeg_path.write_bytes(b"placeholder")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")

    result = execute_application_tool_command(
        Study(),
        "scan_source",
        {"source_path": str(source_dir), "label_sources": [str(label_dir)]},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    scan = result.raw_result["diagnostics"]["scan_result"]
    assert scan["label_sources"] == [str(label_dir.resolve())]
    assert scan["label_carriers"] == [str(label_path.resolve())]


def test_application_tool_command_apply_surfaces_confirmation_required(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    scan_result = execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source)},
    )
    scan_result = _assert_tool_command_result(
        scan_result,
        tool_name="scan_source",
        command_name=CommandName.SCAN_SOURCE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert scan_result.raw_result["diagnostics"]["payload_type"] == "scan_result"

    preview_result = execute_application_tool_command(
        study,
        "preview_interpretation",
        {},
    )
    preview_result = _assert_tool_command_result(
        preview_result,
        tool_name="preview_interpretation",
        command_name=CommandName.PREVIEW_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )

    validate_result = execute_application_tool_command(
        study,
        "validate_interpretation",
        {},
    )
    validate_result = _assert_tool_command_result(
        validate_result,
        tool_name="validate_interpretation",
        command_name=CommandName.VALIDATE_INTERPRETATION,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(validate_result)["interpretation"]["has_validation_decision"] is True

    result = execute_application_tool_command(study, "apply_interpretation", {})

    result = _assert_tool_command_result(
        result,
        tool_name="apply_interpretation",
        command_name=CommandName.APPLY_INTERPRETATION,
        ok=False,
        error_type="confirmation_required",
        raw_status="failed",
    )
    assert result.blocked_reason == "apply_interpretation requires confirmation."


def test_application_tool_command_routes_standard_preprocess(tmp_path):
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = str(tmp_path / "sample.fif")
    study.loaded_data_list = [raw]
    study.preprocessed_data_list = [raw]

    result = execute_application_tool_command(
        study,
        "apply_standard_preprocess",
        {
            "l_freq": 4,
            "h_freq": 40,
            "notch_freq": 50,
            "normalize_method": "z-score",
        },
    )

    result = _assert_tool_command_result(
        result,
        tool_name="apply_standard_preprocess",
        command_name=CommandName.PREPROCESS,
        ok=False,
        error_type="validation",
        raw_status="failed",
    )
    assert result.raw_result["diagnostics"]["exception_type"] == "TypeError"


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

    result = _assert_tool_command_result(
        result,
        tool_name="set_model",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    assert _state(result)["training"]["model_name"] == "EEGNet"
    assert result.raw_result["changed_state"]["training_changed"] is True


def test_application_tool_command_preserves_training_output_dir(tmp_path):
    output_dir = tmp_path / "chatpanel-training-output"

    result = execute_application_tool_command(
        Study(),
        "configure_training",
        {
            "epoch": 1,
            "batch_size": 2,
            "learning_rate": 0.001,
            "device": "cpu",
            "output_dir": str(output_dir),
        },
    )

    result = _assert_tool_command_result(
        result,
        tool_name="configure_training",
        command_name=CommandName.CONFIGURE_TRAINING,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    training_state = result.raw_result["state"]["training"]["training_option"]
    assert training_state["output_dir"] == str(output_dir)


def test_application_tool_command_routes_load_data_to_command_surface(tmp_path):
    sample = tmp_path / "sample.unsupported"
    sample.write_text("not eeg", encoding="utf-8")

    result = execute_application_tool_command(
        Study(),
        "load_data",
        {"paths": [str(sample)]},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="load_data",
        command_name=CommandName.LOAD_DATA,
        ok=False,
        raw_status="failed",
    )
    assert result.error_type in {"unsupported_format", "runtime"}


def test_query_state_tool_uses_application_command_surface():
    study = Study()

    policy = build_agent_tool_policy(study)
    assert policy["query_state"].enabled is True
    assert policy["query_state"].command_name == CommandName.QUERY_STATE.value

    result = execute_application_tool_command(
        study,
        "query_state",
        {"query": "state"},
    )

    result = _assert_tool_command_result(
        result,
        tool_name="query_state",
        command_name=CommandName.QUERY_STATE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    diagnostics = result.raw_result["diagnostics"]
    assert diagnostics["state"]["pipeline_stage"] == "empty"
    assert diagnostics["capabilities"]["query_state"]["enabled"] is True


def test_query_state_tool_surfaces_interpretation_review_truth(tmp_path):
    study = Study()
    service = get_application_service(study)
    source_dir = tmp_path / "agent_reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"placeholder")
    events_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service.dataset.import_files = MagicMock(return_value=(1, []))

    execute_application_tool_command(
        study,
        "scan_source",
        {"source_path": str(source_dir)},
    )
    execute_application_tool_command(
        study,
        "preview_interpretation",
        {
            "choices": {
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand"},
            },
        },
    )
    execute_application_tool_command(study, "validate_interpretation", {})
    execute_application_tool_command(study, "apply_interpretation", {"confirmed": True})
    result = execute_application_tool_command(study, "query_state", {"query": "state"})

    result = _assert_tool_command_result(
        result,
        tool_name="query_state",
        command_name=CommandName.QUERY_STATE,
        ok=True,
        error_type="none",
        raw_status="ok",
    )
    interpretation = result.raw_result["diagnostics"]["state"]["interpretation"]
    assert interpretation["label_carrier_plan"][0]["path"] == str(events_path)
    assert interpretation["label_carrier_plan"][0]["selected_label_field"] == (
        "trial_type"
    )
    capabilities = {
        item["name"]: item for item in interpretation["format_capabilities"]
    }
    assert capabilities["events.tsv"]["format"] == "BIDS events"
    assert interpretation["class_map"] == {"left": "left hand"}


def test_analysis_tools_are_application_service_backed():
    study = Study()

    policy = build_agent_tool_policy(study)
    assert policy["evaluate"].command_name == CommandName.EVALUATE.value
    assert policy["visualize"].command_name == CommandName.VISUALIZE.value
    assert policy["saliency"].command_name == CommandName.SALIENCY.value

    evaluate = execute_application_tool_command(study, "evaluate", {})
    visualize = execute_application_tool_command(
        study, "visualize", {"view": "summary"}
    )
    saliency = execute_application_tool_command(
        study,
        "saliency",
        {"method": "Gradient", "params": {"absolute": True}},
    )

    evaluate = _assert_tool_command_result(
        evaluate,
        tool_name="evaluate",
        command_name=CommandName.EVALUATE,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert (
        evaluate.blocked_reason == "Create a training plan before evaluating results."
    )

    visualize = _assert_tool_command_result(
        visualize,
        tool_name="visualize",
        command_name=CommandName.VISUALIZE,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert visualize.blocked_reason == (
        "Create epochs, complete training, or configure saliency before opening "
        "visualization views."
    )

    saliency = _assert_tool_command_result(
        saliency,
        tool_name="saliency",
        command_name=CommandName.SALIENCY,
        ok=False,
        error_type="precondition",
        raw_status="failed",
    )
    assert saliency.blocked_reason == (
        "Create epochs, generate datasets, or select a model and training settings "
        "before querying saliency readiness."
    )


def test_application_tool_command_leaves_ui_request_tools_on_legacy_path():
    assert (
        execute_application_tool_command(
            Study(),
            "set_montage",
            {"montage_name": "standard_1020"},
        )
        is None
    )
