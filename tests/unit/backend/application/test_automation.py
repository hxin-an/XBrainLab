from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    AutomationPayloadError,
    CommandName,
    PreprocessCommand,
    PreprocessOperation,
    ScanSourceCommand,
    build_command_from_payload,
    command_specs,
    execute_automation_payload,
    mcp_tool_specs,
    resource_guard,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
)
from XBrainLab.backend.study import Study


def test_command_specs_cover_primary_application_commands_with_autonomy_policy():
    service = ApplicationService(Study())

    specs = {spec.name: spec for spec in command_specs(service)}

    assert set(specs) == {
        name.value
        for name in CommandName
        if name
        not in {
            CommandName.LOAD_DATA,
            CommandName.ATTACH_LABELS,
            CommandName.IMPORT_LABELS,
        }
    }
    scan = specs[CommandName.SCAN_SOURCE.value]
    assert scan.taxonomy == "data_interpretation"
    assert scan.input_schema["required"] == ["source_path"]
    assert scan.capability is not None
    assert scan.capability["decision_boundary"] == "read_only_discovery"
    assert scan.capability["can_auto_execute"] is True

    apply_spec = specs[CommandName.APPLY_INTERPRETATION.value]
    assert apply_spec.taxonomy == "data_interpretation"
    assert apply_spec.input_schema["properties"]["confirmed"]["type"] == "boolean"
    assert (
        apply_spec.input_schema["properties"]["resource_preflight_confirmed"]["type"]
        == "boolean"
    )
    assert apply_spec.input_schema["properties"]["resource_preflight_token"] == {
        "type": "string",
        "nullable": True,
    }

    dataset_spec = specs[CommandName.GENERATE_DATASET.value]
    split_config = dataset_spec.input_schema["properties"]["split_config"]
    assert split_config["additionalProperties"] is False
    assert split_config["required"] == [
        "train_type",
        "is_cross_validation",
        "val_splitters",
        "test_splitters",
    ]
    assert split_config["properties"]["train_type"]["enum"] == [
        "Full Data",
        "Individual",
    ]
    splitter = split_config["properties"]["test_splitters"]["items"]
    assert "By Trial" in splitter["properties"]["split_type"]["enum"]
    assert "Ratio" in splitter["properties"]["split_unit"]["enum"]


def test_command_specs_fail_closed_when_published_state_is_stale() -> None:
    service = ApplicationService(Study())
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state refresh failed"),
    )
    with pytest.raises(RuntimeError, match="state refresh failed"):
        service.get_state()

    specs = {spec.name: spec for spec in command_specs(service)}

    scan = specs[CommandName.SCAN_SOURCE.value]
    assert scan.capability is not None
    assert scan.capability["enabled"] is False
    assert scan.capability["reasons"] == [PUBLIC_VIEW_UNAVAILABLE_MESSAGE]
    publication = service.get_view_publication()
    assert publication.diagnostic_error == "state refresh failed"
    assert specs[CommandName.QUERY_STATE.value].capability["enabled"] is True
    assert specs[CommandName.STOP_TRAINING.value].capability["enabled"] is True
    reset = specs[CommandName.RESET_SESSION.value].capability
    assert reset["enabled"] is True
    assert reset["requires_confirmation"] is True


def test_preview_command_spec_exposes_recipe_remap_choices():
    service = ApplicationService(Study())

    specs = {spec.name: spec for spec in command_specs(service)}
    choices = specs[CommandName.PREVIEW_INTERPRETATION.value].input_schema[
        "properties"
    ]["choices"]

    assert choices["additionalProperties"] is False
    assert choices["properties"]["eeg_file_remap"]["additionalProperties"] == {
        "type": "string"
    }
    assert choices["properties"]["label_carrier_remap"]["additionalProperties"] == {
        "type": "string"
    }
    carrier_choice = choices["properties"]["label_carrier_choices"][
        "additionalProperties"
    ]
    assert "target_file" in carrier_choice["properties"]
    assert "placement_method" in carrier_choice["properties"]
    assert "event_code" in carrier_choice["properties"]["placement_method"]["enum"]
    assert "duration_field" in carrier_choice["properties"]
    assert "run_event_mappings" in choices["properties"]


def test_mcp_tool_specs_use_same_command_schema():
    service = ApplicationService(Study())

    tools = {tool["name"]: tool for tool in mcp_tool_specs(service)}

    assert CommandName.SCAN_SOURCE.value in tools
    assert tools[CommandName.SCAN_SOURCE.value]["inputSchema"]["required"] == [
        "source_path"
    ]
    assert (
        tools[CommandName.SCAN_SOURCE.value]["x_xbrainlab"]["taxonomy"]
        == "data_interpretation"
    )
    preview_choices = tools[CommandName.PREVIEW_INTERPRETATION.value]["inputSchema"][
        "properties"
    ]["choices"]
    assert "eeg_file_remap" in preview_choices["properties"]
    assert "label_carrier_remap" in preview_choices["properties"]
    evaluate_schema = tools[CommandName.EVALUATE.value]["inputSchema"]
    assert "include_metrics" not in evaluate_schema["properties"]
    assert "include_pooled_results" not in evaluate_schema["properties"]
    assert "include_model_summaries" not in evaluate_schema["properties"]
    assert "model_summary_plan_index" not in evaluate_schema["properties"]
    assert "model_summary_run_index" not in evaluate_schema["properties"]
    assert "summary_identity" not in evaluate_schema["properties"]
    visualize_schema = tools[CommandName.VISUALIZE.value]["inputSchema"]
    assert set(visualize_schema["properties"]) == {"view"}
    query_state_schema = tools[CommandName.QUERY_STATE.value]["inputSchema"]
    assert set(query_state_schema["properties"]) == {"query", "params"}
    generate_schema = tools[CommandName.GENERATE_DATASET.value]["inputSchema"]
    assert "generator" not in generate_schema["properties"]


def test_mcp_tool_specs_expose_execution_boundary_metadata():
    service = ApplicationService(Study())

    tools = {tool["name"]: tool for tool in mcp_tool_specs(service)}

    train_execution = tools[CommandName.TRAIN.value]["x_xbrainlab"]["execution"]
    assert train_execution["long_running"] is True
    assert train_execution["requires_http_job"] is True
    assert train_execution["supported_job_transports"] == ["http"]
    assert train_execution["requires_confirmation"] is True
    assert train_execution["decision_boundary"] == "long_running"

    evaluate_execution = tools[CommandName.EVALUATE.value]["x_xbrainlab"]["execution"]
    assert evaluate_execution["long_running"] is False
    assert evaluate_execution["requires_http_job"] is False
    assert evaluate_execution["decision_boundary"] is None

    reset_execution = tools[CommandName.RESET_SESSION.value]["x_xbrainlab"]["execution"]
    assert reset_execution["destructive"] is True
    assert reset_execution["requires_confirmation"] is False
    assert reset_execution["confirmation_required"] is False


@pytest.mark.parametrize(
    ("command_name", "field_name"),
    [
        (CommandName.EVALUATE, "include_metrics"),
        (CommandName.EVALUATE, "include_pooled_results"),
        (CommandName.EVALUATE, "include_model_summaries"),
        (CommandName.EVALUATE, "model_summary_plan_index"),
        (CommandName.EVALUATE, "model_summary_run_index"),
        (CommandName.EVALUATE, "summary_identity"),
        (CommandName.GENERATE_DATASET, "generator"),
    ],
)
def test_automation_rejects_ui_only_payload_flags(command_name, field_name):
    with pytest.raises(AutomationPayloadError, match=field_name):
        build_command_from_payload(
            {
                "command": command_name.value,
                "arguments": {field_name: True},
            },
        )


def test_legacy_compatibility_commands_require_explicit_schema_opt_in():
    service = ApplicationService(Study())

    specs = {spec.name: spec for spec in command_specs(service)}
    tools = {tool["name"]: tool for tool in mcp_tool_specs(service)}

    assert {
        CommandName.LOAD_DATA.value,
        CommandName.ATTACH_LABELS.value,
        CommandName.IMPORT_LABELS.value,
    }.isdisjoint(specs)
    assert {
        CommandName.LOAD_DATA.value,
        CommandName.ATTACH_LABELS.value,
        CommandName.IMPORT_LABELS.value,
    }.isdisjoint(tools)

    specs = {
        spec.name: spec
        for spec in command_specs(
            service,
            include_legacy_compatibility=True,
        )
    }
    tools = {
        tool["name"]: tool
        for tool in mcp_tool_specs(
            service,
            include_legacy_compatibility=True,
        )
    }

    for command_name in (
        CommandName.LOAD_DATA.value,
        CommandName.ATTACH_LABELS.value,
        CommandName.IMPORT_LABELS.value,
    ):
        spec = specs[command_name]
        assert spec.taxonomy == "legacy_data_compatibility"
        assert spec.legacy_compatibility is True
        assert spec.primary_workflow is False
        assert "Legacy compatibility" in spec.description
        assert "review_interpretation" in spec.preferred_commands
        assert "apply_interpretation" in spec.preferred_commands

        metadata = tools[command_name]["x_xbrainlab"]
        assert metadata["legacy_compatibility"] is True
        assert metadata["primary_workflow"] is False
        assert "review_interpretation" in metadata["preferred_commands"]


@pytest.mark.parametrize(
    "command_name",
    [
        CommandName.LOAD_DATA.value,
        CommandName.ATTACH_LABELS.value,
        CommandName.IMPORT_LABELS.value,
    ],
)
def test_legacy_compatibility_payload_requires_explicit_execution_opt_in(
    command_name: str,
) -> None:
    with pytest.raises(
        AutomationPayloadError,
        match="requires explicit compatibility opt-in",
    ):
        build_command_from_payload(
            {"command": command_name, "arguments": {}},
        )


def test_build_command_from_payload_validates_required_and_unknown_arguments():
    command = build_command_from_payload(
        {
            "command": "scan_source",
            "arguments": {"source_path": "/data", "source_hint": "bids"},
        }
    )

    assert isinstance(command, ScanSourceCommand)
    assert command.source_path == "/data"
    assert command.source_hint == "bids"

    with pytest.raises(AutomationPayloadError, match="missing required"):
        build_command_from_payload({"command": "scan_source", "arguments": {}})

    with pytest.raises(AutomationPayloadError, match="unsupported arguments"):
        build_command_from_payload(
            {
                "command": "scan_source",
                "arguments": {"source_path": "/data", "legacy_path": "/other"},
            }
        )


@pytest.mark.parametrize(
    ("command_name", "field_name", "expected_type", "invalid_value"),
    [
        (CommandName.CONFIGURE_TRAINING, "model_name", "string", 123),
        (CommandName.CONFIGURE_TRAINING, "output_dir", "string", 123),
        (CommandName.TRAIN, "append", "boolean", "false"),
        (CommandName.TRAIN, "interactive", "boolean", "false"),
    ],
)
def test_build_training_command_rejects_values_outside_published_schema(
    command_name: CommandName,
    field_name: str,
    expected_type: str,
    invalid_value: object,
) -> None:
    spec = next(spec for spec in command_specs() if spec.name == command_name.value)
    assert spec.input_schema["properties"][field_name]["type"] == expected_type

    with pytest.raises(AutomationPayloadError, match=field_name):
        build_command_from_payload(
            {
                "command": command_name.value,
                "arguments": {field_name: invalid_value},
            },
        )


@pytest.mark.parametrize(
    ("command_name", "field_name", "invalid_value"),
    [
        (CommandName.CONFIGURE_TRAINING, "model_name", 123),
        (CommandName.CONFIGURE_TRAINING, "output_dir", 123),
        (CommandName.TRAIN, "append", "false"),
        (CommandName.TRAIN, "interactive", "false"),
    ],
)
def test_execute_training_payload_rejects_schema_error_before_service_execution(
    command_name: CommandName,
    field_name: str,
    invalid_value: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    execute_spy = MagicMock(
        side_effect=AssertionError("invalid payload must not reach service.execute"),
    )
    monkeypatch.setattr(service, "execute", execute_spy)

    execution = execute_automation_payload(
        service,
        {
            "command": command_name.value,
            "arguments": {field_name: invalid_value},
        },
    )

    assert execution.accepted is False
    assert execution.command_name == command_name.value
    assert execution.verification["schema_valid"] is False
    assert field_name in execution.verification["error"]
    assert execution.result is None
    execute_spy.assert_not_called()


def test_build_command_preserves_typed_enum_values():
    command = build_command_from_payload(
        {
            "command": "preprocess",
            "arguments": {
                "operation": PreprocessOperation.BANDPASS.value,
                "low_freq": 4.0,
                "high_freq": 40.0,
            },
        }
    )

    assert isinstance(command, PreprocessCommand)
    assert command.operation == PreprocessOperation.BANDPASS.value


def test_execute_automation_payload_routes_through_service_and_policy(tmp_path: Path):
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")
    service = ApplicationService(Study())

    scan = execute_automation_payload(
        service,
        {"command": "scan_source", "arguments": {"source_path": str(source)}},
    )
    preview = execute_automation_payload(
        service,
        {"command": "preview_interpretation", "arguments": {}},
    )
    validation = execute_automation_payload(
        service,
        {"command": "validate_interpretation", "arguments": {}},
    )
    apply_without_confirmation = execute_automation_payload(
        service,
        {"command": "apply_interpretation", "arguments": {}},
    )

    assert scan.accepted is True
    assert scan.result is not None
    assert scan.result["status"] == "ok"
    assert preview.result is not None
    assert preview.result["status"] == "ok"
    assert validation.result is not None
    assert validation.result["status"] == "ok"
    assert apply_without_confirmation.accepted is True
    assert apply_without_confirmation.autonomy["requires_confirmation"] is True
    assert apply_without_confirmation.verification["confirmation_required"] is True
    assert apply_without_confirmation.result is not None
    assert apply_without_confirmation.result["status"] == "failed"
    assert apply_without_confirmation.result["error_type"] == "confirmation_required"


def test_automation_public_serializer_redacts_internal_result_and_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Clinical Records" / "Mary Example" / "recording.gdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"placeholder")
    service = ApplicationService(Study())

    execution = execute_automation_payload(
        service,
        {"command": "scan_source", "arguments": {"source_path": str(source)}},
    )

    internal = execution.to_internal_dict()
    public = execution.to_public_dict()

    assert str(source) in json.dumps(internal)
    assert str(source) not in json.dumps(public)
    assert "Clinical Records" not in json.dumps(public)
    assert "Mary Example" not in json.dumps(public)
    assert "[REDACTED_PATH]" in json.dumps(public)
    assert execution.to_dict() == public


def test_execute_automation_payload_state_contains_interpretation_review_truth(
    tmp_path: Path,
):
    source_dir = tmp_path / "automation_reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"placeholder")
    events_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    execute_automation_payload(
        service,
        {"command": "scan_source", "arguments": {"source_path": str(source_dir)}},
    )
    execute_automation_payload(
        service,
        {
            "command": "preview_interpretation",
            "arguments": {
                "choices": {
                    "label_carrier_choices": {
                        str(events_path): {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                            "value_decisions": {
                                "left": {
                                    "role": "stimulus",
                                    "keep_event": True,
                                    "use_as_class": True,
                                    "class_name": "left hand",
                                    "decision_source": "user_choice",
                                    "provenance": "automation_test",
                                }
                            },
                        },
                    },
                },
            },
        },
    )
    execute_automation_payload(
        service,
        {"command": "validate_interpretation", "arguments": {}},
    )
    apply_execution = execute_automation_payload(
        service,
        {"command": "apply_interpretation", "arguments": {"confirmed": True}},
    )

    interpretation = apply_execution.state["interpretation"]
    assert interpretation["label_carrier_plan"][0]["path"] == str(events_path)
    assert interpretation["label_carrier_plan"][0]["selected_anchor"] == "onset"
    assert interpretation["class_map"] == {"left": "left hand"}
    capabilities = {
        item["name"]: item for item in interpretation["format_capabilities"]
    }
    assert capabilities["events.tsv"]["format"] == "BIDS events"


def test_execute_automation_payload_reports_schema_error_without_service_execution():
    service = ApplicationService(Study())

    execution = execute_automation_payload(
        service,
        {"command": "scan_source", "arguments": {}},
    )

    assert execution.accepted is False
    assert execution.command_name == CommandName.SCAN_SOURCE.value
    assert execution.verification["schema_valid"] is False
    assert "missing required" in execution.verification["error"]
    assert execution.result is None


def test_headless_load_requires_explicit_resource_warning_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 2_000_000)

    blocked = execute_automation_payload(
        service,
        {"command": "load_data", "arguments": {"paths": [str(path)]}},
        allow_legacy_compatibility=True,
    )

    assert blocked.result is not None
    assert blocked.result["status"] == "failed"
    assert blocked.result["error_type"] == "confirmation_required"
    assert blocked.result["diagnostics"]["resource_preflight"]["risk_level"] == (
        "warning"
    )
    challenge = blocked.result["diagnostics"]["resource_preflight"][
        "confirmation_challenge"
    ]
    assert challenge["command_name"] == "load_data"
    service.dataset.import_files.assert_not_called()

    continued = execute_automation_payload(
        service,
        {
            "command": "load_data",
            "arguments": {
                "paths": [str(path)],
                "resource_preflight_confirmed": True,
                "resource_preflight_token": challenge["challenge_id"],
            },
        },
        allow_legacy_compatibility=True,
    )

    assert continued.result is not None
    assert continued.result["status"] == "ok"
    assert continued.result["diagnostics"]["resource_preflight"]["risk_level"] == (
        "warning"
    )
    service.dataset.import_files.assert_called_once_with([str(path)])


def test_automation_preflight_reads_one_committed_publication():
    service = ApplicationService(Study())
    publication = service.get_view_publication()
    service.get_view_publication = MagicMock(return_value=publication)
    service.get_state = MagicMock(
        side_effect=AssertionError("automation must not rebuild state separately"),
    )
    service.get_capabilities = MagicMock(
        side_effect=AssertionError("automation must not rebuild policy separately"),
    )

    execution = execute_automation_payload(
        service,
        {"command": "scan_source", "arguments": {}},
    )

    assert execution.accepted is False
    service.get_view_publication.assert_called_once_with()


def test_headless_cli_lists_mcp_tool_specs():
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/dev/run_application_command.py", "--mcp-tools"],
        check=True,
        capture_output=True,
        text=True,
    )

    tools = json.loads(completed.stdout)
    assert any(tool["name"] == "scan_source" for tool in tools)
    assert not any(tool["name"] == "load_data" for tool in tools)


def test_headless_cli_legacy_compatibility_requires_explicit_opt_in():
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/run_application_command.py",
            "--mcp-tools",
            "--include-legacy-compatibility",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    tools = json.loads(completed.stdout)
    assert any(tool["name"] == "load_data" for tool in tools)


def test_headless_cli_redacts_hostile_command_text() -> None:
    private_command = "/home/alice/Clinical Records/Mary Example"
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/run_application_command.py",
            "--payload",
            json.dumps({"command": private_command, "arguments": {}}),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert private_command not in completed.stdout
    assert "Clinical Records" not in completed.stdout
    assert "Mary Example" not in completed.stdout
    assert "[REDACTED_PATH]" in completed.stdout
    json.loads(completed.stdout)
