"""Focused tests for assistant-visible tool feedback and model payloads."""

from __future__ import annotations

import json

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.llm.agent.tool_feedback import (
    compact_state_summary,
    format_tool_output,
    summarize_tool_result,
)
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind


def test_tool_output_preserves_publication_refresh_diagnostics():
    result = ToolCommandResult(
        ok=True,
        tool_name="query_state",
        command_name="query_state",
        message="Application state snapshot ready.",
        state={
            "pipeline_stage": "empty",
            "raw": {
                "loaded": False,
                "count": 0,
                "metadata": [{"large": "payload"}],
                "diagnostics": {"verbose": "details"},
            },
            "training": {
                "has_model": False,
                "missing_requirements": ["Data Splitting"],
            },
        },
        diagnostics={
            "payload_type": "state_snapshot",
            "state": {"too": "big"},
            "publication_generation": 8,
            "view_verified": True,
            "view_stale": True,
            "view_refresh_error": "A command is still publishing state.",
        },
        raw_result={"status": "ok", "state": {"too": "big"}},
    )

    payload = json.loads(format_tool_output("query_state", True, result))

    assert payload["message"] == "Application state snapshot ready."
    assert payload["state_summary"]["pipeline_stage"] == "empty"
    assert payload["state_summary"]["raw"] == {"loaded": False, "count": 0}
    assert payload["state_summary"]["training"]["missing_requirements"] == [
        "Data Splitting"
    ]
    assert payload["diagnostics"] == {
        "payload_type": "state_snapshot",
        "publication_generation": 8,
        "view_verified": True,
        "view_stale": True,
        "view_refresh_error": "A command is still publishing state.",
    }
    assert "raw_result" not in payload
    assert "state" not in payload


def test_import_summary_uses_neutral_product_language():
    result = ToolCommandResult.failure(
        "import_eeg_data",
        "Load raw data first.",
        command_name=CommandName.SCAN_SOURCE.value,
        error_type="precondition",
    )

    summary = summarize_tool_result("import_eeg_data", False, result)

    assert "EEG data import can't run yet" in summary
    assert "**Required first:** Load raw data first." in summary
    assert "Load EEG data" not in summary
    assert "import_eeg_data" not in summary


def test_format_tool_output_keeps_workflow_truth_without_raw_payloads() -> None:
    result = ToolCommandResult(
        ok=True,
        tool_name="query_state",
        command_name="query_state",
        message="Application state snapshot ready.",
        raw_result={"state": {"large": "payload"}},
        state={
            "pipeline_stage": "dataset_ready",
            "raw": {
                "loaded": True,
                "count": 3,
                "metadata": [{"large": "payload"}],
            },
            "dataset": {"available": True, "count": 1, "private": "drop"},
        },
        diagnostics={
            "payload_type": "state_snapshot",
            "state": {"large": "payload"},
            "publication_generation": 9,
        },
    )

    payload = json.loads(format_tool_output("query_state", True, result))

    assert payload["state_summary"] == {
        "pipeline_stage": "dataset_ready",
        "raw": {"loaded": True, "count": 3},
        "dataset": {"available": True, "count": 1},
    }
    assert payload["diagnostics"] == {
        "payload_type": "state_snapshot",
        "publication_generation": 9,
    }
    assert "raw_result" not in payload
    assert "state" not in payload


def test_failure_feedback_redacts_paths_and_tokens_from_all_public_fields() -> None:
    private_path = r"C:\Users\Alice\private\subject-17\events.tsv"
    private_token = "Authorization: Bearer hf_super_secret"  # noqa: S105
    private_message = f"Could not read {private_path}; {private_token}"
    result = ToolCommandResult.failure(
        "import_eeg_data",
        private_message,
        command_name="scan_source",
        state={"last_error": {"message": private_message, "recoverable": True}},
        capability={"reasons": [private_message]},
        raw_result={"status": "failed", "message": private_message},
        error_type="input",
        diagnostics={"detail": private_message},
    )

    model_feedback = format_tool_output("import_eeg_data", False, result)
    user_summary = summarize_tool_result("import_eeg_data", False, result)
    public_values = "\n".join(
        (
            model_feedback,
            user_summary,
            repr(result.to_payload()),
        )
    )

    for private_value in (private_path, private_token, "hf_super_secret"):
        assert private_value not in public_values
    assert "[REDACTED_PATH]" in public_values
    assert "[REDACTED_SECRET]" in public_values


def test_summary_translates_backend_precondition_to_product_language() -> None:
    result = ToolCommandResult.failure(
        "import_eeg_data",
        "ApplicationService requires paths list cannot be empty.",
        command_name="scan_source",
        error_type="precondition",
    )

    summary = summarize_tool_result("import_eeg_data", False, result)

    assert summary == (
        "EEG data import can't run yet.\n\n"
        "**Required first:** The workflow requires a file or folder path."
    )
    assert "ApplicationService" not in summary
    assert "paths list" not in summary


def test_training_precondition_shows_more_setup_and_the_first_requirement() -> None:
    result = ToolCommandResult.failure(
        "start_training",
        (
            "Load raw data before training.; Save a valid data splitting "
            "specification before training."
        ),
        command_name="train",
        capability={
            "reasons": [
                "Load raw data before training.",
                "Save a valid data splitting specification before training.",
            ]
        },
        error_type="precondition",
    )

    summary = summarize_tool_result("start_training", False, result)

    assert summary == (
        "Training can't start yet.\n\n**Required first:** Import EEG data."
    )
    assert "data splitting specification" not in summary


def test_training_precondition_keeps_only_the_next_backend_requirement() -> None:
    result = ToolCommandResult.failure(
        "start_training",
        (
            "Select a model before training.; Configure training options before "
            "training."
        ),
        command_name="train",
        capability={
            "reasons": [
                "Select a model before training.",
                "Configure training options before training.",
            ]
        },
        error_type="precondition",
    )

    summary = summarize_tool_result("start_training", False, result)

    assert summary == (
        "Training can't start yet.\n\n**Required first:** Select a model."
    )
    assert "Configure training options" not in summary


def test_direct_preprocess_precondition_uses_a_two_part_product_message() -> None:
    result = ToolCommandResult.failure(
        "apply_bandpass_filter",
        "Load raw data before preprocessing.",
        command_name="preprocess",
        error_type="precondition",
    )

    assert summarize_tool_result("apply_bandpass_filter", False, result) == (
        "Band-pass filtering can't run yet.\n\n"
        "**Required first:** Load raw data before preprocessing."
    )


def test_notch_nyquist_precondition_preserves_actionable_backend_values() -> None:
    result = ToolCommandResult.failure(
        "apply_notch_filter",
        (
            "Notch filtering at 60 Hz cannot run because the lowest sampling rate "
            "is 100 Hz (Nyquist limit 50 Hz). Use a notch frequency below 50 Hz. "
            "If this data was resampled, reset preprocessing, apply notch filtering "
            "before resampling, then resample again."
        ),
        command_name="preprocess",
        error_type="precondition",
        diagnostics={
            "code": "notch_frequency_at_or_above_nyquist",
            "requested_frequency": 60.0,
            "sampling_rate": 100.0,
            "nyquist": 50.0,
            "state_preserved": True,
        },
    )

    summary = summarize_tool_result("apply_notch_filter", False, result)

    assert "60 Hz" in summary
    assert "100 Hz" in summary
    assert "Nyquist limit 50 Hz" in summary
    assert "reset preprocessing" in summary.lower()
    assert "status bar" not in summary.lower()
    assert "try again" not in summary.lower()


def test_bandpass_nyquist_precondition_preserves_actionable_backend_values() -> None:
    result = ToolCommandResult.failure(
        "apply_bandpass_filter",
        (
            "Band-pass filtering up to 100 Hz cannot run because the lowest "
            "sampling rate is 160 Hz (Nyquist limit 80 Hz). Use a high cutoff "
            "below 80 Hz. If this data was resampled, reset preprocessing, apply "
            "band-pass filtering before resampling, then resample again."
        ),
        command_name="preprocess",
        error_type="precondition",
        diagnostics={
            "code": "bandpass_high_frequency_at_or_above_nyquist",
            "requested_frequency": 100.0,
            "sampling_rate": 160.0,
            "nyquist": 80.0,
            "state_preserved": True,
        },
    )

    summary = summarize_tool_result("apply_bandpass_filter", False, result)

    assert "100 Hz" in summary
    assert "160 Hz" in summary
    assert "Nyquist limit 80 Hz" in summary
    assert "reset preprocessing" in summary.lower()
    assert "status bar" not in summary.lower()
    assert "try again" not in summary.lower()


def test_training_precondition_preserves_already_running_truth() -> None:
    result = ToolCommandResult.failure(
        "start_training",
        "Training is already running.",
        command_name="train",
        capability={"reasons": ["Training is already running."]},
        error_type="precondition",
    )

    assert (
        summarize_tool_result("start_training", False, result)
        == "Training is already running."
    )


def test_summary_uses_product_language_for_interpretation_decisions() -> None:
    expected_by_decision = {
        "safe": "Data interpretation is ready to apply.",
        "needs_confirmation": (
            "Review and confirm the data interpretation before applying it."
        ),
        "blocked": "Data interpretation needs changes before it can be applied.",
    }

    for decision, expected in expected_by_decision.items():
        result = ToolCommandResult(
            ok=True,
            tool_name="validate_interpretation",
            command_name="validate_interpretation",
            message="Interpretation validation finished.",
            diagnostics={
                "payload_type": "validation_decision",
                "validation_decision": {"decision": decision},
            },
        )

        summary = summarize_tool_result("validate_interpretation", True, result)

        assert summary == expected
        assert decision not in summary


def test_summary_hides_unknown_structured_interpretation_decision_token() -> None:
    result = ToolCommandResult(
        ok=True,
        tool_name="validate_interpretation",
        command_name="validate_interpretation",
        message="Interpretation validation finished.",
        diagnostics={
            "payload_type": "validation_decision",
            "validation_decision": {"decision": "future_backend_status"},
        },
    )

    summary = summarize_tool_result("validate_interpretation", True, result)

    assert summary == "Data interpretation review is ready."
    assert "future_backend_status" not in summary


def test_summary_names_concrete_import_decisions_and_target_surface() -> None:
    result = ToolCommandResult(
        ok=True,
        tool_name="validate_interpretation",
        command_name="validate_interpretation",
        message="Interpretation validation finished.",
        diagnostics={
            "payload_type": "validation_decision",
            "validation_decision": {
                "decision": "needs_confirmation",
                "action_items": [
                    {
                        "issue": "Task metadata is missing for 3 files.",
                        "severity": "needs_confirmation",
                        "target_step": "Review Metadata",
                    },
                    {
                        "issue": "Event roles need review.",
                        "severity": "needs_confirmation",
                        "target_step": "Match Labels",
                    },
                    {
                        "issue": "No external labels are attached.",
                        "severity": "warning",
                        "target_step": "Load Labels",
                    },
                ],
            },
        },
    )

    summary = summarize_tool_result("validate_interpretation", True, result)

    assert summary == (
        "Import review needs your input:\n"
        "- Task metadata is missing for 3 files.\n"
        "- Event roles need review.\n"
        "Use the open Import EEG Data window to review these choices."
    )
    assert "No external labels" not in summary


def test_summary_keeps_typed_import_decisions_when_state_payload_is_large() -> None:
    decision = {
        "decision": "needs_confirmation",
        "action_items": [
            {
                "issue": "Confirm which events are class labels.",
                "severity": "needs_confirmation",
            },
        ],
    }
    result = ToolCommandResult(
        ok=True,
        tool_name="validate_interpretation",
        command_name="validate_interpretation",
        message="Interpretation validation: needs_confirmation.",
        raw_result={
            "state": {
                "metadata": [
                    {"subject": index, "session": index} for index in range(1_000)
                ],
            },
        },
        state={
            "raw": {
                "metadata": [
                    {"subject": index, "session": index} for index in range(1_000)
                ],
            },
        },
        diagnostics={
            "payload_type": "validation_decision",
            "validation_decision": decision,
        },
    )

    summary = summarize_tool_result("validate_interpretation", True, result)

    assert summary == (
        "Import review needs your input:\n"
        "- Confirm which events are class labels.\n"
        "Use the open Import EEG Data window to review these choices."
    )
    assert "needs_confirmation" not in summary


def test_ui_request_feedback_is_typed_for_model_and_user() -> None:
    request = UiRequest(
        kind=UiRequestKind.SWITCH_PANEL,
        params={"panel": "visualization"},
    )

    assert (
        summarize_tool_result("switch_panel", True, request)
        == "I opened the requested workspace panel."
    )
    assert json.loads(format_tool_output("switch_panel", True, request)) == {
        "ok": True,
        "tool_name": "switch_panel",
        "ui_request": "switch_panel",
        "params": {"panel": "visualization"},
    }


def test_compact_state_summary_rejects_non_mapping_state() -> None:
    assert compact_state_summary(None) == {}
