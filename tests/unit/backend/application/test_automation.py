from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
)
from XBrainLab.backend.study import Study


def test_command_specs_cover_application_commands_with_autonomy_policy():
    service = ApplicationService(Study())

    specs = {spec.name: spec for spec in command_specs(service)}

    assert set(specs) == {name.value for name in CommandName}
    scan = specs[CommandName.SCAN_SOURCE.value]
    assert scan.taxonomy == "data_interpretation"
    assert scan.input_schema["required"] == ["source_path"]
    assert scan.capability is not None
    assert scan.capability["decision_boundary"] == "read_only_discovery"
    assert scan.capability["can_auto_execute"] is True

    apply_spec = specs[CommandName.APPLY_INTERPRETATION.value]
    assert apply_spec.taxonomy == "data_interpretation"
    assert apply_spec.input_schema["properties"]["confirmed"]["type"] == "boolean"


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


def test_headless_cli_lists_mcp_tool_specs():
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/dev/run_application_command.py", "--mcp-tools"],
        check=True,
        capture_output=True,
        text=True,
    )

    tools = json.loads(completed.stdout)
    assert any(tool["name"] == "scan_source" for tool in tools)
