from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import torch

from XBrainLab.backend.application import ApplicationService, CommandName
from XBrainLab.backend.dataset.epochs import EpochWindowProvenance
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.mcp.server import PROTOCOL_VERSION, MCPServer


def _jsonrpc_result(
    response: dict[str, Any] | None,
    request_id: int,
) -> dict[str, Any]:
    assert isinstance(response, dict), response
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == request_id
    assert "error" not in response
    result = response.get("result")
    assert isinstance(result, dict), response
    return result


def _jsonrpc_error(
    response: dict[str, Any] | None,
    request_id: int,
) -> dict[str, Any]:
    assert isinstance(response, dict), response
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == request_id
    assert "result" not in response
    error = response.get("error")
    assert isinstance(error, dict), response
    return error


def test_initialize_declares_tools_capability():
    server = MCPServer()

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "unit-test", "version": "1.0"},
            },
        }
    )

    result = _jsonrpc_result(response, 1)
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "xbrainlab"


def test_tools_list_uses_application_command_schema():
    server = MCPServer()
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )

    result = _jsonrpc_result(response, 2)
    tools = {tool["name"]: tool for tool in result["tools"]}
    scan = tools[CommandName.SCAN_SOURCE.value]
    assert scan["inputSchema"]["required"] == ["source_path"]
    assert scan["inputSchema"]["properties"]["label_sources"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert "adapter" in scan["outputSchema"]["properties"]
    assert scan["x_xbrainlab"]["taxonomy"] == "data_interpretation"
    assert scan["x_xbrainlab"]["capability"]["can_auto_execute"] is True
    assert scan["x_xbrainlab"]["execution"]["requires_http_job"] is False
    train = tools[CommandName.TRAIN.value]
    assert train["x_xbrainlab"]["execution"]["long_running"] is True
    assert train["x_xbrainlab"]["execution"]["requires_http_job"] is True
    assert train["x_xbrainlab"]["execution"]["supported_job_transports"] == ["http"]
    reset = tools[CommandName.RESET_SESSION.value]
    assert reset["x_xbrainlab"]["execution"]["destructive"] is True


def test_tools_call_reuses_one_application_service_session(tmp_path: Path):
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")
    server = MCPServer()
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    scan = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "scan_source",
                "arguments": {"source_path": str(source)},
            },
        }
    )
    preview = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "preview_interpretation", "arguments": {}},
        }
    )

    scan_result = _jsonrpc_result(scan, 2)
    assert scan_result["isError"] is False
    assert scan_result["structuredContent"]["command_name"] == "scan_source"
    assert scan_result["structuredContent"]["accepted"] is True
    assert scan_result["structuredContent"]["verification"]["schema_valid"] is True
    assert scan_result["structuredContent"]["result"]["status"] == "ok"
    assert "Scanned" in scan_result["content"][0]["text"]
    preview_result = _jsonrpc_result(preview, 3)
    assert preview_result["isError"] is False
    assert preview_result["structuredContent"]["command_name"] == (
        "preview_interpretation"
    )
    assert preview_result["structuredContent"]["accepted"] is True
    assert preview_result["structuredContent"]["verification"]["schema_valid"] is True
    assert preview_result["structuredContent"]["result"]["status"] == "ok"
    assert (
        preview_result["structuredContent"]["state"]["interpretation"]["has_candidate"]
        is True
    )
    scan_adapter = scan_result["structuredContent"]["adapter"]
    preview_adapter = preview_result["structuredContent"]["adapter"]
    assert scan_adapter["mode"] == "headless_mcp_stdio"
    assert scan_adapter["transport"] == "stdio"
    assert scan_adapter["session_id"]
    assert scan_adapter["session_id"] == preview_adapter["session_id"]
    assert scan_adapter["ui_refresh"]["supported"] is False
    assert "does not refresh" in scan_adapter["ui_refresh"]["reason"]


def test_tools_call_returns_tool_error_for_schema_repair():
    server = MCPServer()
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "scan_source", "arguments": {}},
        }
    )

    result = _jsonrpc_result(response, 2)
    assert result["isError"] is True
    assert "missing required arguments" in result["content"][0]["text"]
    assert result["structuredContent"]["accepted"] is False
    assert result["structuredContent"]["verification"]["schema_valid"] is False


def test_stdio_mcp_reports_precondition_before_long_running_job_boundary():
    server = MCPServer()
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "train", "arguments": {}},
        }
    )

    result = _jsonrpc_result(response, 2)
    assert result["isError"] is True
    assert "Generate datasets before training" in result["content"][0]["text"]
    structured = result["structuredContent"]
    assert structured["accepted"] is True
    assert structured["verification"]["schema_valid"] is True
    assert structured["verification"]["capability_enabled"] is False
    assert "long_running_job_required" not in structured["verification"]
    assert structured["result"]["error_type"] == "precondition"
    assert structured["adapter"]["mode"] == "headless_mcp_stdio"


def test_stdio_mcp_blocks_enabled_long_running_commands_until_job_api_exists():
    service = ApplicationService(Study())
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    service.study.loaded_data_list = [raw]
    epoch_data = MagicMock()
    epoch_data.get_data.return_value = np.zeros((4, 1, 8), dtype=np.float32)
    labels = np.asarray([0, 1, 0, 1])
    epoch_data.get_label_list.return_value = labels
    epoch_data.get_label_list_by_mask.side_effect = lambda mask: labels[mask]
    epoch_data.get_label_number.return_value = 2
    epoch_data.get_model_args.return_value = {}
    epoch_data.get_epoch_window_provenance.return_value = tuple(
        EpochWindowProvenance(
            source_recording_id=f"path-sha256:{'a' * 64}",
            event_sample=index * 20,
            window_start_sample=index * 20,
            window_end_sample_exclusive=index * 20 + 8,
            source_sfreq=100.0,
            epoch_sfreq=100.0,
            tmin_seconds=0.0,
            tmax_seconds=0.07,
            source_coordinates_verified=True,
        )
        for index in range(4)
    )
    dataset = MagicMock()
    dataset.get_epoch_data.return_value = epoch_data
    dataset.get_name.return_value = "test dataset"
    dataset.train_mask = np.asarray([True, True, False, False])
    dataset.val_mask = np.asarray([False, False, True, False])
    dataset.test_mask = np.asarray([False, False, False, True])
    cast(Any, service.study).datasets = [dataset]
    service.study.model_holder = ModelHolder(torch.nn.Identity, {})
    service.study.training_option = TrainingOption(
        "/tmp/xbrainlab-mcp-test",
        torch.optim.Adam,
        {},
        True,
        None,
        1,
        2,
        0.001,
        0,
        TrainingEvaluation.VAL_ACC,
        1,
    )
    service.get_state()
    server = MCPServer(service)
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "train", "arguments": {"confirmed": True}},
        }
    )

    result = _jsonrpc_result(response, 2)
    assert result["isError"] is True
    assert "long-running" in result["content"][0]["text"]
    structured = result["structuredContent"]
    assert structured["accepted"] is False
    assert structured["verification"]["schema_valid"] is True
    assert structured["verification"]["capability_enabled"] is True
    assert structured["verification"]["long_running_job_required"] is True
    assert structured["result"]["error_type"] == "long_running_job_required"
    assert structured["result"]["diagnostics"]["job_boundary"] == {
        "supported": False,
        "required_transport": "http_job_api",
        "supports_progress": False,
        "supports_cancel": False,
    }
    assert structured["adapter"]["mode"] == "headless_mcp_stdio"


def test_unknown_tool_is_protocol_error():
    server = MCPServer()
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "not_a_command", "arguments": {}},
        }
    )

    error = _jsonrpc_error(response, 2)
    assert error["code"] == -32602
    assert "Unknown tool" in error["message"]
