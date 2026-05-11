from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from XBrainLab.backend.application import ApplicationService, CommandName
from XBrainLab.backend.study import Study
from XBrainLab.mcp.server import PROTOCOL_VERSION, MCPServer


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

    assert response is not None
    assert response["id"] == 1
    result = response["result"]
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

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
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

    assert scan is not None
    assert scan["result"]["isError"] is False
    assert scan["result"]["structuredContent"]["result"]["status"] == "ok"
    assert "Scanned" in scan["result"]["content"][0]["text"]
    assert preview is not None
    assert preview["result"]["isError"] is False
    assert preview["result"]["structuredContent"]["result"]["status"] == "ok"
    assert (
        preview["result"]["structuredContent"]["state"]["interpretation"][
            "has_candidate"
        ]
        is True
    )
    scan_adapter = scan["result"]["structuredContent"]["adapter"]
    preview_adapter = preview["result"]["structuredContent"]["adapter"]
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

    assert response is not None
    result = response["result"]
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

    assert response is not None
    result = response["result"]
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
    cast(Any, service.study).datasets = [object()]
    cast(Any, service.study).model_holder = object()
    cast(Any, service.study).training_option = object()
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

    assert response is not None
    result = response["result"]
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

    assert response is not None
    assert response["error"]["code"] == -32602
    assert "Unknown tool" in response["error"]["message"]
