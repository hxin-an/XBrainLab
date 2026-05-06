"""Local HTTP adapter for XBrainLab MCP JSON-RPC.

The HTTP server is intentionally thin: it owns a headless ``ApplicationService``
session through ``MCPServer`` and exposes JSON-RPC over ``POST /mcp``. It does
not control or refresh a desktop UI.
"""

from __future__ import annotations

import json
import logging
from hmac import compare_digest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from XBrainLab.backend.application import ApplicationService
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
        auth_token: str | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.mcp_server = mcp_server
        self.auth_token = auth_token
        self.max_body_bytes = max_body_bytes


class MCPHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for local MCP JSON-RPC calls."""

    server: MCPHTTPServer

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path != "/health":
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
            }
        )

    def do_POST(self) -> None:
        if not self._authorized():
            return
        if self.path != "/mcp":
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

    def log_message(self, fmt: str, *args: Any) -> None:
        """Route HTTP request logs to logging instead of stdout."""
        logging.getLogger("XBrainLab.mcp.http").debug(fmt, *args)


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
    return MCPHTTPServer(
        (host, port),
        MCPHTTPRequestHandler,
        mcp_server=server,
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
