from __future__ import annotations

from pathlib import Path

from XBrainLab.backend.application import CommandName
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
    assert "adapter" in scan["outputSchema"]["properties"]
    assert scan["x_xbrainlab"]["taxonomy"] == "data_interpretation"
    assert scan["x_xbrainlab"]["capability"]["can_auto_execute"] is True


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
