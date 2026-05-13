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


def _tool_command_result(result: ToolCommandResult | None) -> ToolCommandResult:
    assert isinstance(result, ToolCommandResult), result
    return result


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

    unconfirmed = _tool_command_result(
        execute_application_tool_command(study, "start_training", {})
    )
    confirmed = _tool_command_result(
        execute_application_tool_command(
            study,
            "start_training",
            {"confirmed": True},
        )
    )

    assert unconfirmed.ok is False
    assert unconfirmed.command_name == CommandName.TRAIN.value
    assert unconfirmed.error_type == "confirmation_required"
    assert confirmed.ok is True
    assert confirmed.command_name == CommandName.TRAIN.value
    assert confirmed.raw_result["status"] == "ok"
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

    result = _tool_command_result(
        execute_application_tool_command(study, "apply_bandpass_filter", {})
    )

    assert result.ok is False
    assert result.command_name == CommandName.PREPROCESS.value
    assert result.error_type == "input"
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

    scan_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "scan_source",
            {"source_path": str(source)},
        )
    )
    assert scan_result.ok
    assert scan_result.command_name == CommandName.SCAN_SOURCE.value
    assert scan_result.raw_result["diagnostics"]["payload_type"] == "scan_result"

    preview_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "preview_interpretation",
            {},
        )
    )
    assert preview_result.ok
    assert preview_result.command_name == CommandName.PREVIEW_INTERPRETATION.value

    validate_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "validate_interpretation",
            {},
        )
    )
    assert validate_result.ok
    assert validate_result.command_name == CommandName.VALIDATE_INTERPRETATION.value

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

    result = _tool_command_result(
        execute_application_tool_command(
            Study(),
            "scan_source",
            {"source_path": str(source), "source_hint": "file"},
        )
    )

    assert result.ok is True
    assert result.command_name == CommandName.SCAN_SOURCE.value
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

    result = _tool_command_result(
        execute_application_tool_command(
            Study(),
            "scan_source",
            {"source_path": str(source_dir), "label_sources": [str(label_dir)]},
        )
    )

    assert result.ok is True
    assert result.command_name == CommandName.SCAN_SOURCE.value
    scan = result.raw_result["diagnostics"]["scan_result"]
    assert scan["label_sources"] == [str(label_dir.resolve())]
    assert scan["label_carriers"] == [str(label_path.resolve())]


def test_application_tool_command_apply_surfaces_confirmation_required(tmp_path):
    study = Study()
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    scan_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "scan_source",
            {"source_path": str(source)},
        )
    )
    assert scan_result.ok
    assert scan_result.command_name == CommandName.SCAN_SOURCE.value

    preview_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "preview_interpretation",
            {},
        )
    )
    assert preview_result.ok
    assert preview_result.command_name == CommandName.PREVIEW_INTERPRETATION.value

    validate_result = _tool_command_result(
        execute_application_tool_command(
            study,
            "validate_interpretation",
            {},
        )
    )
    assert validate_result.ok
    assert validate_result.command_name == CommandName.VALIDATE_INTERPRETATION.value

    result = _tool_command_result(
        execute_application_tool_command(study, "apply_interpretation", {})
    )

    assert result.ok is False
    assert result.command_name == CommandName.APPLY_INTERPRETATION.value
    assert result.error_type == "confirmation_required"


def test_application_tool_command_routes_standard_preprocess(tmp_path):
    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = str(tmp_path / "sample.fif")
    study.loaded_data_list = [raw]
    study.preprocessed_data_list = [raw]

    result = _tool_command_result(
        execute_application_tool_command(
            study,
            "apply_standard_preprocess",
            {
                "l_freq": 4,
                "h_freq": 40,
                "notch_freq": 50,
                "normalize_method": "z-score",
            },
        )
    )

    assert result.command_name == CommandName.PREPROCESS.value
    assert result.raw_result["status"] in {"ok", "failed"}


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

    result = _tool_command_result(
        execute_application_tool_command(
            study,
            "set_model",
            {"model_name": "EEGNet"},
        )
    )

    assert result.ok is True
    assert result.command_name == CommandName.CONFIGURE_TRAINING.value
    assert result.raw_result["status"] == "ok"
    assert result.raw_result["state"]["training"]["has_model"] is True
    assert result.raw_result["state"]["training"]["model_name"] == "EEGNet"


def test_application_tool_command_preserves_training_output_dir(tmp_path):
    output_dir = tmp_path / "chatpanel-training-output"

    result = _tool_command_result(
        execute_application_tool_command(
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
    )

    assert result.ok is True
    assert result.command_name == CommandName.CONFIGURE_TRAINING.value
    training_state = result.raw_result["state"]["training"]["training_option"]
    assert training_state["output_dir"] == str(output_dir)


def test_application_tool_command_routes_load_data_to_command_surface(tmp_path):
    sample = tmp_path / "sample.unsupported"
    sample.write_text("not eeg", encoding="utf-8")

    result = _tool_command_result(
        execute_application_tool_command(
            Study(),
            "load_data",
            {"paths": [str(sample)]},
        )
    )

    assert result.ok is False
    assert result.command_name == CommandName.LOAD_DATA.value
    assert result.raw_result["status"] == "failed"


def test_query_state_tool_uses_application_command_surface():
    study = Study()

    policy = build_agent_tool_policy(study)
    assert policy["query_state"].enabled is True
    assert policy["query_state"].command_name == CommandName.QUERY_STATE.value

    result = _tool_command_result(
        execute_application_tool_command(
            study,
            "query_state",
            {"query": "state"},
        )
    )

    assert result.ok is True
    assert result.command_name == CommandName.QUERY_STATE.value
    assert result.raw_result["status"] == "ok"


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
    result = _tool_command_result(
        execute_application_tool_command(study, "query_state", {"query": "state"})
    )

    assert result.ok is True
    assert result.command_name == CommandName.QUERY_STATE.value
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

    evaluate = _tool_command_result(
        execute_application_tool_command(study, "evaluate", {})
    )
    visualize = _tool_command_result(
        execute_application_tool_command(study, "visualize", {"view": "summary"})
    )
    saliency = _tool_command_result(
        execute_application_tool_command(
            study,
            "saliency",
            {"method": "Gradient", "params": {"absolute": True}},
        )
    )

    assert evaluate.command_name == CommandName.EVALUATE.value
    assert evaluate.error_type == "precondition"
    assert isinstance(evaluate.blocked_reason, str)
    assert "training plan" in evaluate.blocked_reason

    assert visualize.command_name == CommandName.VISUALIZE.value
    assert visualize.error_type == "precondition"
    assert isinstance(visualize.blocked_reason, str)
    assert "epochs" in visualize.blocked_reason

    assert saliency.command_name == CommandName.SALIENCY.value
    assert saliency.error_type == "precondition"
    assert isinstance(saliency.blocked_reason, str)
    assert "training settings" in saliency.blocked_reason


def test_application_tool_command_leaves_ui_request_tools_on_legacy_path():
    assert (
        execute_application_tool_command(
            Study(),
            "set_montage",
            {"montage_name": "standard_1020"},
        )
        is None
    )
