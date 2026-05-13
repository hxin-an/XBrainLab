"""Local HTTP adapter for XBrainLab MCP JSON-RPC.

The HTTP server is intentionally thin: it owns a headless ``ApplicationService``
session through ``MCPServer`` and exposes JSON-RPC over ``POST /mcp``. It does
not control or refresh a desktop UI.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from hmac import compare_digest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import time
from typing import Any
from urllib.parse import urlparse

from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    execute_automation_payload,
)
from XBrainLab.mcp.server import MCPServer

DEFAULT_MAX_BODY_BYTES = 1_048_576


class MCPHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server carrying one headless MCP session."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        mcp_server: MCPServer,
        job_registry: MCPHTTPJobRegistry,
        auth_token: str | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.mcp_server = mcp_server
        self.job_registry = job_registry
        self.auth_token = auth_token
        self.max_body_bytes = max_body_bytes


class MCPHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for local MCP JSON-RPC calls."""

    server: MCPHTTPServer

    def do_GET(self) -> None:
        if not self._authorized():
            return
        path = urlparse(self.path).path
        if path == "/jobs":
            self._write_json({"jobs": self.server.job_registry.list_jobs()})
            return
        if path.startswith("/jobs/"):
            self._handle_job_get(path)
            return
        if path != "/health":
            self._write_json(
                {"error": "not_found", "message": "Unknown endpoint."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._write_json(
            {
                "status": "ok",
                "transport": self.server.mcp_server.transport,
                "session_id": self.server.mcp_server.session_id,
                "ui_refresh_supported": False,
                "job_api": {
                    "supported": True,
                    "supports_progress": True,
                    "supports_cancel": True,
                    "job_count": self.server.job_registry.job_count(),
                },
            }
        )

    def do_POST(self) -> None:
        if not self._authorized():
            return
        path = urlparse(self.path).path
        if path.startswith("/jobs/") and path.endswith("/cancel"):
            self._handle_job_cancel(path)
            return
        if path != "/mcp":
            self._write_json(
                {"error": "not_found", "message": "Unknown endpoint."},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._write_json(
                {"error": "bad_request", "message": "Invalid Content-Length."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        if content_length > self.server.max_body_bytes:
            self._write_json(
                {
                    "error": "payload_too_large",
                    "message": "MCP HTTP request body is too large.",
                    "max_body_bytes": self.server.max_body_bytes,
                },
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        body = self.rfile.read(content_length).decode("utf-8")
        try:
            message = json.loads(body)
        except json.JSONDecodeError as exc:
            self._write_json(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Invalid JSON.",
                        "data": str(exc),
                    },
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        response = self.server.mcp_server.handle_message(message)
        if response is None:
            self._write_json({}, status=HTTPStatus.ACCEPTED)
            return
        self._write_json(response)

    def _authorized(self) -> bool:
        token = self.server.auth_token
        if not token:
            return True
        expected = f"Bearer {token}"
        provided = self.headers.get("Authorization", "")
        if compare_digest(provided, expected):
            return True
        self._write_json(
            {
                "error": "unauthorized",
                "message": "Missing or invalid bearer token.",
            },
            status=HTTPStatus.UNAUTHORIZED,
        )
        return False

    def _write_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _handle_job_get(self, path: str) -> None:
        job_id = _job_id_from_path(path)
        if job_id is None:
            self._write_json(
                {"error": "not_found", "message": "Unknown job endpoint."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        job = self.server.job_registry.get_job(job_id)
        if job is None:
            self._write_json(
                {"error": "job_not_found", "message": "Unknown MCP HTTP job."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._write_json({"job": job})

    def _handle_job_cancel(self, path: str) -> None:
        job_id = _job_id_from_path(path, suffix="/cancel")
        if job_id is None:
            self._write_json(
                {"error": "not_found", "message": "Unknown job endpoint."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        response = self.server.job_registry.cancel_job(job_id)
        if response is None:
            self._write_json(
                {"error": "job_not_found", "message": "Unknown MCP HTTP job."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        self._write_json(response)

    def log_message(self, fmt: str, *args: Any) -> None:
        """Route HTTP request logs to logging instead of stdout."""
        logging.getLogger("XBrainLab.mcp.http").debug(fmt, *args)


@dataclass
class MCPHTTPJobRecord:
    """In-memory HTTP job state for one long-running command."""

    job_id: str
    command_name: str
    payload: dict[str, Any]
    created_at: float
    command_execution: dict[str, Any]
    cancel_requested: bool = False
    cancel_execution: dict[str, Any] | None = None
    terminal_status: str | None = None
    updated_at: float = field(default_factory=time)


class MCPHTTPJobRegistry:
    """Track local HTTP long-running jobs for one MCP session."""

    def __init__(self, mcp_server: MCPServer) -> None:
        self._mcp_server = mcp_server
        self._lock = threading.Lock()
        self._jobs: dict[str, MCPHTTPJobRecord] = {}
        self._starting_command_name: str | None = None

    def job_count(self) -> int:
        with self._lock:
            return len(self._jobs)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._job_snapshot_locked(record) for record in self._jobs.values()]

    def start_job(
        self,
        command_name: str,
        payload: dict[str, Any],
        capability: Any,
        adapter: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            active_job = self._active_job_locked()
            if self._starting_command_name is not None or active_job is not None:
                return self._job_conflict_execution(
                    command_name,
                    capability,
                    adapter,
                    active_job=active_job,
                )
            self._starting_command_name = command_name

        try:
            command_execution = execute_automation_payload(
                self._mcp_server.service,
                payload,
            ).to_dict()
        except Exception:
            with self._lock:
                self._starting_command_name = None
            raise

        command_execution["adapter"] = adapter
        result = command_execution.get("result")
        if not command_execution.get("accepted", False) or (
            isinstance(result, dict) and result.get("status") == "failed"
        ):
            with self._lock:
                self._starting_command_name = None
            return command_execution

        now = time()
        record = MCPHTTPJobRecord(
            job_id=f"mcp-http-job-{uuid.uuid4().hex[:12]}",
            command_name=command_name,
            payload=payload,
            created_at=now,
            updated_at=now,
            command_execution=command_execution,
        )
        with self._lock:
            self._jobs[record.job_id] = record
            self._starting_command_name = None
            job = self._job_snapshot_locked(record)

        message = f"{_product_command_name(command_name)} job started."
        return {
            "accepted": True,
            "command_name": command_name,
            "verification": {
                "schema_valid": True,
                "capability_enabled": capability.enabled,
                "confirmation_required": True,
                "long_running_job_created": True,
                "reasons": list(capability.reasons),
            },
            "autonomy": _autonomy_metadata(capability),
            "capability": capability.to_dict(),
            "result": {
                "status": job["status"],
                "command_name": command_name,
                "message": message,
                "job": job,
                "diagnostics": {
                    "job_boundary": {
                        "supported": True,
                        "transport": "http",
                        "supports_progress": True,
                        "supports_cancel": True,
                    },
                    "command_result": command_execution.get("result"),
                },
            },
            "state": self._mcp_server.service.get_state().to_dict(),
            "adapter": adapter,
        }

    def _active_job_locked(self) -> dict[str, Any] | None:
        running = bool(self._mcp_server.service.get_state().active_training.is_running)
        for record in self._jobs.values():
            if _job_status(record, running) in {"running", "cancel_requested"}:
                return self._job_snapshot_locked(record)
        return None

    def _job_conflict_execution(
        self,
        command_name: str,
        capability: Any,
        adapter: dict[str, Any],
        *,
        active_job: dict[str, Any] | None,
    ) -> dict[str, Any]:
        fresh_capability = (
            self._mcp_server.service.get_capabilities().get(command_name) or capability
        )
        starting_command_name = self._starting_command_name
        if starting_command_name is not None:
            message = (
                f"{_product_command_name(command_name)} job is already starting. "
                "Wait for it to appear in the job list before starting another run."
            )
        else:
            message = (
                f"{_product_command_name(command_name)} job is already running. "
                "Check the existing job status or cancel it before starting "
                "another run."
            )
        reasons = [message, *list(getattr(fresh_capability, "reasons", []))]
        return {
            "accepted": False,
            "command_name": command_name,
            "verification": {
                "schema_valid": True,
                "capability_enabled": False,
                "confirmation_required": getattr(
                    fresh_capability,
                    "confirmation_required",
                    False,
                ),
                "long_running_job_created": False,
                "resource_locked": True,
                "reasons": reasons,
            },
            "autonomy": _autonomy_metadata(fresh_capability),
            "capability": fresh_capability.to_dict(),
            "result": {
                "status": "failed",
                "command_name": command_name,
                "message": message,
                "error_type": "job_already_running",
                "recoverable": True,
                "diagnostics": {
                    "job_boundary": {
                        "supported": True,
                        "transport": "http",
                        "supports_progress": True,
                        "supports_cancel": True,
                    },
                    "active_job": active_job,
                    "starting_command_name": starting_command_name,
                },
            },
            "state": self._mcp_server.service.get_state().to_dict(),
            "adapter": adapter,
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return self._job_snapshot_locked(record)

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            return None
        cancel_execution = execute_automation_payload(
            self._mcp_server.service,
            {"command": CommandName.STOP_TRAINING.value, "arguments": {}},
        ).to_dict()
        cancel_execution["adapter"] = self._mcp_server.adapter_metadata()
        with self._lock:
            record.cancel_requested = True
            record.cancel_execution = cancel_execution
            record.updated_at = time()
            job = self._job_snapshot_locked(record)
        return {
            "job": job,
            "cancel_result": cancel_execution,
        }

    def _job_snapshot_locked(self, record: MCPHTTPJobRecord) -> dict[str, Any]:
        state = self._mcp_server.service.get_state()
        running = bool(state.active_training.is_running)
        status = _job_status(record, running)
        if record.terminal_status is None and status in {
            "completed",
            "cancelled",
            "failed",
        }:
            record.terminal_status = status
            record.updated_at = time()
        return {
            "job_id": record.job_id,
            "command_name": record.command_name,
            "status": status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "supports_cancel": record.command_name == CommandName.TRAIN.value,
            "cancel_requested": record.cancel_requested,
            "progress": {
                "running": running,
                "message": _training_progress_message(self._mcp_server.service),
                "finished_run_count": state.training.finished_run_count,
                "run_count": state.training.run_count,
            },
            "command_result": record.command_execution.get("result"),
        }


def build_http_server(
    *,
    host: str,
    port: int,
    auth_token: str | None = None,
    service: ApplicationService | None = None,
    mcp_server: MCPServer | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> MCPHTTPServer:
    """Build a local HTTP MCP server without starting the serving loop."""
    server = mcp_server or MCPServer(service, transport="http")
    if server.transport != "http":
        raise ValueError("MCP HTTP server requires an MCPServer transport='http'.")
    job_registry = MCPHTTPJobRegistry(server)
    server.set_long_running_handler(job_registry.start_job)
    return MCPHTTPServer(
        (host, port),
        MCPHTTPRequestHandler,
        mcp_server=server,
        job_registry=job_registry,
        auth_token=auth_token or None,
        max_body_bytes=max_body_bytes,
    )


def run_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    auth_token: str | None = None,
    service: ApplicationService | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> int:
    """Run the local HTTP MCP server until interrupted."""
    httpd = build_http_server(
        host=host,
        port=port,
        auth_token=auth_token,
        service=service,
        max_body_bytes=max_body_bytes,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        httpd.server_close()
    return 0


def _job_id_from_path(path: str, *, suffix: str = "") -> str | None:
    if suffix and path.endswith(suffix):
        path = path[: -len(suffix)]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2 or parts[0] != "jobs" or not parts[1]:
        return None
    return parts[1]


def _job_status(record: MCPHTTPJobRecord, running: bool) -> str:
    if record.terminal_status is not None:
        return record.terminal_status
    result = record.command_execution.get("result")
    if isinstance(result, dict) and result.get("status") == "failed":
        return "failed"
    if record.cancel_requested:
        return "cancel_requested" if running else "cancelled"
    return "running" if running else "completed"


def _training_progress_message(service: ApplicationService) -> str:
    state = service.get_state()
    progress_message = getattr(state.training, "progress_message", None)
    if isinstance(progress_message, str) and progress_message:
        return progress_message
    if state.active_training.is_running:
        return "Training is running."
    return "Training is not running."


def _product_command_name(command_name: str) -> str:
    if command_name == CommandName.TRAIN.value:
        return "Training"
    return command_name.replace("_", " ").title()


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
