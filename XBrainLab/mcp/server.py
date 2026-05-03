"""Minimal MCP stdio server backed by ApplicationService commands.

This module deliberately implements only the MCP lifecycle and tool calls needed
to expose XBrainLab's command surface. It does not create another workflow layer:
all tool calls are converted to automation payloads and executed by
ApplicationService.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from XBrainLab import __version__
from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    execute_automation_payload,
    mcp_tool_specs,
)
from XBrainLab.backend.study import Study

PROTOCOL_VERSION = "2025-06-18"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass(frozen=True)
class JsonRpcError(Exception):
    """Structured JSON-RPC error used inside the stdio server."""

    code: int
    message: str
    data: Any = None


class MCPServer:
    """Stateful MCP tool server for one XBrainLab ApplicationService session."""

    def __init__(self, service: ApplicationService | None = None) -> None:
        self._service = service or ApplicationService(Study())
        self._initialized = False

    def handle_line(self, line: str) -> dict[str, Any] | None:
        """Parse and handle one newline-delimited JSON-RPC message."""
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            return _error_response(None, PARSE_ERROR, "Invalid JSON.", str(exc))
        return self.handle_message(message)

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        """Handle one JSON-RPC request or notification."""
        if not isinstance(message, dict):
            return _error_response(None, INVALID_REQUEST, "Message must be an object.")

        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return _error_response(request_id, INVALID_REQUEST, "Missing method.")

        is_notification = "id" not in message
        try:
            result = self._dispatch(method, message.get("params", {}))
        except JsonRpcError as exc:
            if is_notification:
                return None
            return _error_response(request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # pragma: no cover - defensive server boundary.
            logging.exception("Unhandled MCP server error")
            if is_notification:
                return None
            return _error_response(
                request_id,
                INTERNAL_ERROR,
                "XBrainLab MCP server failed unexpectedly.",
                str(exc),
            )

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Any) -> dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method == "notifications/initialized":
            self._initialized = True
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            self._require_initialized()
            return {"tools": mcp_tool_specs(self._service)}
        if method == "tools/call":
            self._require_initialized()
            return self._call_tool(params)
        raise JsonRpcError(METHOD_NOT_FOUND, f"Unsupported MCP method: {method}")

    def _initialize(self, params: Any) -> dict[str, Any]:
        requested_version = (
            params.get("protocolVersion") if isinstance(params, dict) else None
        )
        self._initialized = True
        return {
            "protocolVersion": requested_version
            if requested_version == PROTOCOL_VERSION
            else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "xbrainlab",
                "title": "XBrainLab ApplicationService MCP Server",
                "version": __version__,
            },
            "instructions": (
                "Use tools to operate XBrainLab through ApplicationService only. "
                "Data interpretation apply, training, reset, and destructive "
                "commands may require human confirmation in the returned autonomy "
                "policy."
            ),
        }

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise JsonRpcError(
                INVALID_REQUEST,
                "Initialize the MCP session before calling tools.",
            )

    def _call_tool(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise JsonRpcError(INVALID_PARAMS, "tools/call params must be an object.")
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise JsonRpcError(INVALID_PARAMS, "tools/call requires a tool name.")
        if name not in {command.value for command in CommandName}:
            raise JsonRpcError(INVALID_PARAMS, f"Unknown tool: {name}")

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "Tool arguments must be an object.")

        execution = execute_automation_payload(
            self._service,
            {"command": name, "arguments": arguments},
        ).to_dict()
        result = execution.get("result")
        is_error = not execution["accepted"] or (
            isinstance(result, dict) and result.get("status") == "failed"
        )
        return {
            "content": [{"type": "text", "text": _tool_result_text(execution)}],
            "structuredContent": execution,
            "isError": is_error,
        }


def run_stdio(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    server: MCPServer | None = None,
) -> int:
    """Run the MCP stdio loop until stdin closes."""
    input_file = input_stream or sys.stdin
    output_file = output_stream or sys.stdout
    active_server = server or MCPServer()

    for raw_line in input_file:
        line = raw_line.strip()
        if not line:
            continue
        response = active_server.handle_line(line)
        if response is None:
            continue
        output_file.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_file.flush()
    return 0


def _tool_result_text(execution: dict[str, Any]) -> str:
    result = execution.get("result")
    if isinstance(result, dict):
        message = result.get("message") or result.get("error_message")
        if isinstance(message, str) and message:
            return message

    verification = execution.get("verification")
    if isinstance(verification, dict):
        error = verification.get("error")
        if isinstance(error, str) and error:
            return error
        reasons = verification.get("reasons")
        if isinstance(reasons, list) and reasons:
            return " ".join(str(reason) for reason in reasons)

    command_name = execution.get("command_name") or "command"
    return f"{command_name} completed."


def _error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
