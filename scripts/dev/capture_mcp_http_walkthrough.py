#!/usr/bin/env python3
"""Capture a local HTTP MCP walkthrough artifact."""

from __future__ import annotations

import argparse
import json
import socket
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any, cast

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.mcp.http_server import build_http_server
from XBrainLab.mcp.server import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "mcp"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for http-walkthrough.json and .md artifacts.",
    )
    args = parser.parse_args()
    payload = capture_http_walkthrough(args.output_dir)
    validate_http_walkthrough_payload(payload)
    return 0


def capture_http_walkthrough(output_dir: Path) -> dict[str, Any]:
    """Run a local HTTP MCP walkthrough and write JSON / Markdown artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = Path(tempfile.gettempdir()) / "xbrainlab_mcp_http_walkthrough"
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")

    port = _free_port()
    service = _training_ready_service(source)
    httpd = build_http_server(host="127.0.0.1", port=port, service=service)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        health = _request("GET", port, "/health")
        initial_jobs = _request("GET", port, "/jobs")
        initialized = _request(
            "POST",
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )
        listed = _request(
            "POST",
            port,
            "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        scanned = _request(
            "POST",
            port,
            "/mcp",
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
        previewed = _request(
            "POST",
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "preview_interpretation", "arguments": {}},
            },
        )
        train_job = _request(
            "POST",
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "train", "arguments": {"confirmed": True}},
            },
        )
        job_id = _summary_job_id(train_job)
        listed_jobs = _request("GET", port, "/jobs")
        job_status = _request("GET", port, f"/jobs/{job_id}")
        cancelled_job = _request("POST", port, f"/jobs/{job_id}/cancel", {})
        job_after_cancel = _request("GET", port, f"/jobs/{job_id}")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)

    responses = {
        "health": health,
        "initial_jobs": initial_jobs,
        "initialize": initialized,
        "tools_list": listed,
        "scan_source": scanned,
        "preview_interpretation": previewed,
        "train_job": train_job,
        "jobs": listed_jobs,
        "job_status": job_status,
        "cancel_job": cancelled_job,
        "job_after_cancel": job_after_cancel,
    }
    summary = _summary(responses)
    payload = {
        "workflow": "mcp_http_walkthrough",
        "transport": "http",
        "endpoint": "127.0.0.1:<ephemeral>/mcp",
        "client_dependency_boundary": (
            "The HTTP client uses Python standard-library HTTP and JSON only. "
            "XBrainLab EEG, PyQt, PyTorch, and local LLM dependencies remain in "
            "the server process."
        ),
        "session_boundary": (
            "This is a headless ApplicationService MCP session. It does not "
            "control or refresh the desktop UI."
        ),
        "long_running_boundary": (
            "HTTP train job status and cancel are available for the headless "
            "session. Evaluation/visualization jobs, persistence, and recovery "
            "are not enabled in this slice."
        ),
        "summary": summary,
        "responses": _sanitized(responses, source_dir),
    }

    json_path = output_dir / "http-walkthrough.json"
    markdown_path = output_dir / "http-walkthrough.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def validate_http_walkthrough_payload(payload: dict[str, Any]) -> None:
    """Raise when the HTTP walkthrough does not prove the intended baseline."""
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("HTTP MCP walkthrough missing summary.")
    required = {
        "health_ok": True,
        "tools_listed": True,
        "scan_ok": True,
        "preview_ok": True,
        "headless_http_adapter": True,
        "train_job_created": True,
        "job_listed": True,
        "job_status_running": True,
        "cancel_ok": True,
    }
    failures = [
        key for key, expected in required.items() if summary.get(key) != expected
    ]
    if failures:
        raise RuntimeError(f"HTTP MCP walkthrough failed checks: {failures}")


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a concise Markdown walkthrough report."""
    summary = payload["summary"]
    return "\n".join(
        [
            "# MCP HTTP Walkthrough",
            "",
            f"- transport: `{payload['transport']}`",
            f"- endpoint: `{payload['endpoint']}`",
            f"- session id: `{summary['session_id']}`",
            f"- tools listed: `{summary['tool_count']}`",
            f"- scan ok: `{summary['scan_ok']}`",
            f"- preview ok: `{summary['preview_ok']}`",
            f"- train job: `{summary['train_job_id']}`",
            f"- job listed: `{summary['job_listed']}`",
            f"- job status before cancel: `{summary['train_job_status']}`",
            f"- job status after cancel: `{summary['cancelled_job_status']}`",
            "",
            "## Boundaries",
            "",
            f"- {payload['client_dependency_boundary']}",
            f"- {payload['session_boundary']}",
            f"- {payload['long_running_boundary']}",
            "",
        ]
    )


def _summary(responses: dict[str, Any]) -> dict[str, Any]:
    health = responses["health"]["body"]
    tools = responses["tools_list"]["body"]["result"]["tools"]
    scan = responses["scan_source"]["body"]["result"]["structuredContent"]
    preview = responses["preview_interpretation"]["body"]["result"]["structuredContent"]
    train = responses["train_job"]["body"]["result"]["structuredContent"]
    jobs = responses["jobs"]["body"]["jobs"]
    job_status = responses["job_status"]["body"]["job"]
    cancelled = responses["cancel_job"]["body"]["job"]
    adapter = scan["adapter"]
    return {
        "health_ok": responses["health"]["status"] == 200
        and health.get("status") == "ok",
        "session_id": health.get("session_id"),
        "tool_count": len(tools),
        "tools_listed": any(tool.get("name") == "scan_source" for tool in tools),
        "scan_ok": scan.get("result", {}).get("status") == "ok",
        "preview_ok": preview.get("result", {}).get("status") == "ok",
        "headless_http_adapter": adapter.get("mode") == "headless_mcp_http"
        and adapter.get("transport") == "http"
        and adapter.get("ui_refresh", {}).get("supported") is False,
        "train_job_id": train.get("result", {}).get("job", {}).get("job_id"),
        "train_job_created": train.get("result", {}).get("status") == "running",
        "job_listed": any(
            job.get("job_id") == train.get("result", {}).get("job", {}).get("job_id")
            for job in jobs
        ),
        "train_job_status": job_status.get("status"),
        "job_status_running": job_status.get("status") == "running",
        "cancelled_job_status": cancelled.get("status"),
        "cancel_ok": cancelled.get("status") == "cancelled",
    }


def _summary_job_id(response: dict[str, Any]) -> str:
    try:
        job_id = response["body"]["result"]["structuredContent"]["result"]["job"][
            "job_id"
        ]
    except KeyError as exc:
        raise RuntimeError("HTTP MCP train did not return a job id.") from exc
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError("HTTP MCP train returned an invalid job id.")
    return job_id


def _request(
    method: str,
    port: int,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        body = json.dumps(payload) if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        return {
            "status": response.status,
            "body": json.loads(text) if text else {},
        }
    finally:
        conn.close()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sanitized(value: Any, source_dir: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitized(item, source_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitized(item, source_dir) for item in value]
    if isinstance(value, str):
        return value.replace(str(source_dir), "<mcp_http_source>")
    return value


def _training_ready_service(source: Path) -> ApplicationService:
    """Build a service state where train capability reaches job boundary."""
    service = ApplicationService(Study())
    cast(Any, service.study).loaded_data_list = [_RawStub(source)]
    cast(Any, service.study).datasets = [object()]
    cast(Any, service.study).model_holder = object()
    cast(Any, service.study).training_option = object()
    running = {"value": False}

    def start_training() -> None:
        running["value"] = True

    def stop_training() -> None:
        running["value"] = False

    def is_training() -> bool:
        return running["value"]

    service.training.start_training = start_training
    service.training.stop_training = stop_training
    service.training.is_training = is_training
    return service


class _RawStub:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get_filename(self) -> str:
        return self._path.name

    def get_filepath(self) -> str:
        return str(self._path)

    def get_subject_name(self) -> str:
        return "S01"

    def get_session_name(self) -> str:
        return "session-01"

    def get_nchan(self) -> int:
        return 4

    def get_sfreq(self) -> float:
        return 128.0

    def get_epochs_length(self) -> int:
        return 0

    def get_event_list(self) -> tuple[list[Any], dict[str, int]]:
        return [], {}

    def get_filter_range(self) -> tuple[float, float]:
        return 0.0, 64.0

    def is_raw(self) -> bool:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
