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
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

from XBrainLab import __version__
from XBrainLab.backend.application import (
    ApplicationService,
    AutomationPayloadError,
    CommandName,
    build_command_from_payload,
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

LongRunningHandler = Callable[
    [str, dict[str, Any], Any, dict[str, Any]],
    dict[str, Any],
]


@dataclass(frozen=True)
class JsonRpcError(Exception):
    """Structured JSON-RPC error used inside the stdio server."""

    code: int
    message: str
    data: Any = None


class MCPServer:
    """Stateful MCP tool server for one XBrainLab ApplicationService session."""

    def __init__(
        self,
        service: ApplicationService | None = None,
        *,
        transport: str = "stdio",
        long_running_handler: LongRunningHandler | None = None,
    ) -> None:
        transport = transport.strip().lower()
        if transport not in {"stdio", "http"}:
            raise ValueError(f"Unsupported MCP transport: {transport}")
        self._service = service or ApplicationService(Study())
        self._transport = transport
        self._session_id = f"mcp-{transport}-{uuid.uuid4().hex[:12]}"
        self._long_running_handler = long_running_handler
        self._initialized = False

    @property
    def session_id(self) -> str:
        """Return the stable adapter session id."""
        return self._session_id

    @property
    def transport(self) -> str:
        """Return the adapter transport."""
        return self._transport

    @property
    def service(self) -> ApplicationService:
        """Return the owned ApplicationService session."""
        return self._service

    def set_long_running_handler(
        self,
        handler: LongRunningHandler | None,
    ) -> None:
        """Set an optional transport-owned long-running command handler."""
        self._long_running_handler = handler

    def adapter_metadata(self) -> dict[str, Any]:
        """Return metadata describing this MCP adapter session."""
        return self._adapter_metadata()

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

        payload = {"command": name, "arguments": arguments}
        try:
            build_command_from_payload(payload)
        except AutomationPayloadError:
            execution = execute_automation_payload(self._service, payload).to_dict()
            execution["adapter"] = self._adapter_metadata()
            return {
                "content": [{"type": "text", "text": _tool_result_text(execution)}],
                "structuredContent": execution,
                "isError": True,
            }

        capability = self._service.get_capabilities().get(name)
        if capability.long_running and capability.enabled:
            if self._long_running_handler is not None:
                execution = self._long_running_handler(
                    name,
                    payload,
                    capability,
                    self._adapter_metadata(),
                )
                return {
                    "content": [{"type": "text", "text": _tool_result_text(execution)}],
                    "structuredContent": execution,
                    "isError": not execution.get("accepted", False),
                }
            execution = self._long_running_boundary_execution(name, capability)
            return {
                "content": [{"type": "text", "text": _tool_result_text(execution)}],
                "structuredContent": execution,
                "isError": True,
            }

        execution = execute_automation_payload(
            self._service,
            payload,
        ).to_dict()
        execution["adapter"] = self._adapter_metadata()
        result = execution.get("result")
        is_error = not execution["accepted"] or (
            isinstance(result, dict) and result.get("status") == "failed"
        )
        return {
            "content": [{"type": "text", "text": _tool_result_text(execution)}],
            "structuredContent": execution,
            "isError": is_error,
        }

    def _long_running_boundary_execution(
        self,
        name: str,
        capability: Any,
    ) -> dict[str, Any]:
        if self._transport == "http":
            message = (
                "MCP HTTP job execution is not enabled yet. Use the desktop UI "
                "or a future HTTP job API with progress and cancel support."
            )
        else:
            message = (
                "MCP stdio does not execute long-running commands synchronously. "
                "Use the desktop UI or a future HTTP job API with progress and "
                "cancel support."
            )
        job_boundary = {
            "supported": False,
            "required_transport": "http_job_api",
            "supports_progress": False,
            "supports_cancel": False,
        }
        return {
            "accepted": False,
            "command_name": name,
            "verification": {
                "schema_valid": True,
                "capability_enabled": capability.enabled,
                "confirmation_required": True,
                "long_running_job_required": True,
                "reasons": [message, *capability.reasons],
            },
            "autonomy": _autonomy_metadata(capability),
            "capability": capability.to_dict(),
            "result": {
                "status": "failed",
                "command_name": name,
                "message": message,
                "error_type": "long_running_job_required",
                "recoverable": True,
                "error_message": message,
                "diagnostics": {
                    "job_boundary": job_boundary,
                    "capability_reasons": capability.reasons,
                },
            },
            "state": self._service.get_state().to_dict(),
            "adapter": self._adapter_metadata(),
        }

    def _adapter_metadata(self) -> dict[str, Any]:
        return {
            "mode": f"headless_mcp_{self._transport}",
            "transport": self._transport,
            "session_id": self._session_id,
            "ui_refresh": {
                "supported": False,
                "reason": (
                    "This MCP server owns a headless ApplicationService session "
                    "and does not refresh a desktop UI."
                ),
            },
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


def _autonomy_metadata(capability: Any) -> dict[str, Any]:
    return {
        "can_auto_execute": capability.can_auto_execute,
        "requires_confirmation": capability.requires_confirmation,
        "confirmation_required": capability.confirmation_required,
        "decision_boundary": capability.decision_boundary,
        "continue_allowed_after_success": capability.continue_allowed_after_success,
        "retry_limit": capability.retry_limit,
        "stop_after_success": capability.stop_after_success,
        "blocks_downstream_until_confirmed": (
            capability.blocks_downstream_until_confirmed
        ),
    }


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
