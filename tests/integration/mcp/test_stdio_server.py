from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from XBrainLab.mcp.server import PROTOCOL_VERSION


def _send(proc: subprocess.Popen[str], payload: dict[str, Any]) -> dict[str, Any]:
    stdin = proc.stdin
    stdout = proc.stdout
    if stdin is None or stdout is None:
        raise AssertionError("stdio server process was not created with pipes")
    stdin.write(json.dumps(payload) + "\n")
    stdin.flush()
    line = stdout.readline()
    if line == "":
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise AssertionError(stderr)
    return json.loads(line)


def _jsonrpc_result(message: dict[str, Any], request_id: int) -> dict[str, Any]:
    assert message["jsonrpc"] == "2.0"
    assert message["id"] == request_id
    assert "error" not in message
    result = message.get("result")
    assert isinstance(result, dict), message
    return result


def test_stdio_mcp_server_lists_and_calls_application_tools(tmp_path: Path):
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "scripts/dev/run_mcp_server.py"],
        cwd=Path(__file__).parents[3],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        initialized = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )
        initialized_result = _jsonrpc_result(initialized, 1)
        assert initialized_result["capabilities"]["tools"]["listChanged"] is False

        listed = _send(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        listed_result = _jsonrpc_result(listed, 2)
        tools = {tool["name"]: tool for tool in listed_result["tools"]}
        assert tools["scan_source"]["inputSchema"]["required"] == ["source_path"]

        scanned = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "scan_source",
                    "arguments": {"source_path": str(source)},
                },
            },
        )
        scanned_result = _jsonrpc_result(scanned, 3)
        previewed = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "preview_interpretation", "arguments": {}},
            },
        )
        previewed_result = _jsonrpc_result(previewed, 4)

        assert scanned_result["isError"] is False
        assert scanned_result["structuredContent"]["command_name"] == "scan_source"
        assert scanned_result["structuredContent"]["accepted"] is True
        assert previewed_result["isError"] is False
        assert previewed_result["structuredContent"]["command_name"] == (
            "preview_interpretation"
        )
        assert previewed_result["structuredContent"]["accepted"] is True
        assert (
            previewed_result["structuredContent"]["state"]["interpretation"][
                "has_candidate"
            ]
            is True
        )
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=30)
