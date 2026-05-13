from __future__ import annotations

import json
import socket
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.mcp.http_server import _training_progress_message, build_http_server
from XBrainLab.mcp.server import PROTOCOL_VERSION


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _post_json(
    port: int,
    path: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        conn.request("POST", path, json.dumps(payload), headers)
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)
    finally:
        conn.close()


def _post_raw(
    port: int,
    path: str,
    body: str,
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        conn.request("POST", path, body, headers)
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        return response.status, json.loads(text)
    finally:
        conn.close()


def _get_json(
    port: int,
    path: str,
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)
    finally:
        conn.close()


def _start_server(
    *, token: str | None = None, service: ApplicationService | None = None
):
    port = _free_port()
    httpd = build_http_server(
        host="127.0.0.1",
        port=port,
        auth_token=token,
        service=service,
    )
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port, thread


def _training_ready_service() -> tuple[ApplicationService, dict[str, Any]]:
    service = ApplicationService(Study())
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    service.study.loaded_data_list = [raw]
    cast(Any, service.study).datasets = [object()]
    cast(Any, service.study).model_holder = object()
    cast(Any, service.study).training_option = object()
    calls: dict[str, Any] = {"started": 0, "stopped": 0, "running": False}

    def start_training(*, append: bool = True, interactive: bool = True) -> None:
        calls["started"] += 1
        calls["append"] = append
        calls["interactive"] = interactive
        calls["running"] = True

    def stop_training() -> None:
        calls["stopped"] += 1
        calls["running"] = False

    def is_training() -> bool:
        return bool(calls["running"])

    service.training.start_training = start_training
    service.training.stop_training = stop_training
    service.training.is_training = is_training
    return service, calls


def test_http_mcp_rejects_oversized_requests_before_parsing():
    port = _free_port()
    httpd = build_http_server(host="127.0.0.1", port=port, max_body_bytes=16)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, response = _post_raw(port, "/mcp", '{"jsonrpc":"2.0","id":1}')

        assert status == 413
        assert response == {
            "error": "payload_too_large",
            "message": "MCP HTTP request body is too large.",
            "max_body_bytes": 16,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_http_mcp_server_lists_and_calls_application_tools(tmp_path: Path):
    source = tmp_path / "sub-01_task-mi_run-1.gdf"
    source.write_bytes(b"placeholder")
    httpd, port, thread = _start_server()
    try:
        status, health = _get_json(port, "/health")
        assert status == 200
        assert health["status"] == "ok"
        assert health["transport"] == "http"
        assert health["session_id"].startswith("mcp-http-")

        status, initialized = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )
        assert status == 200
        assert initialized["result"]["capabilities"]["tools"]["listChanged"] is False

        status, listed = _post_json(
            port,
            "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert status == 200
        assert any(tool["name"] == "scan_source" for tool in listed["result"]["tools"])

        status, scanned = _post_json(
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
        status, previewed = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "preview_interpretation", "arguments": {}},
            },
        )

        assert status == 200
        assert scanned["result"]["isError"] is False
        assert previewed["result"]["isError"] is False
        adapter = scanned["result"]["structuredContent"]["adapter"]
        preview_adapter = previewed["result"]["structuredContent"]["adapter"]
        assert adapter["mode"] == "headless_mcp_http"
        assert adapter["transport"] == "http"
        assert adapter["session_id"] == health["session_id"]
        assert adapter["session_id"] == preview_adapter["session_id"]
        assert adapter["ui_refresh"]["supported"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_http_mcp_server_requires_bearer_token_when_configured():
    token = "unit-test-token"  # noqa: S105 - non-secret local test token
    httpd, port, thread = _start_server(token=token)
    try:
        status, unauthorized = _get_json(port, "/health")
        assert status == 401
        assert unauthorized["error"] == "unauthorized"

        status, health = _get_json(port, "/health", token=token)
        assert status == 200
        assert health["transport"] == "http"

        status, initialized = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
            token=token,
        )
        assert status == 200
        assert initialized["result"]["serverInfo"]["name"] == "xbrainlab"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_http_mcp_train_uses_job_api_with_status_and_cancel():
    service, calls = _training_ready_service()
    httpd, port, thread = _start_server(service=service)
    try:
        status, initial_jobs = _get_json(port, "/jobs")
        assert status == 200
        assert initial_jobs == {"jobs": []}

        _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )

        status, response = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "train", "arguments": {"confirmed": True}},
            },
        )

        assert status == 200
        result = response["result"]
        assert result["isError"] is False
        assert "Training job started" in result["content"][0]["text"]
        structured = result["structuredContent"]
        assert structured["accepted"] is True
        assert structured["result"]["status"] == "running"
        job = structured["result"]["job"]
        assert job["job_id"].startswith("mcp-http-job-")
        assert job["command_name"] == "train"
        assert job["status"] == "running"
        assert job["supports_cancel"] is True
        assert calls["started"] == 1
        assert structured["adapter"]["mode"] == "headless_mcp_http"
        assert structured["adapter"]["transport"] == "http"

        status, listed_jobs = _get_json(port, "/jobs")
        assert status == 200
        assert [item["job_id"] for item in listed_jobs["jobs"]] == [job["job_id"]]
        assert listed_jobs["jobs"][0]["status"] == "running"

        status, job_status = _get_json(port, f"/jobs/{job['job_id']}")
        assert status == 200
        assert job_status["job"]["status"] == "running"
        assert job_status["job"]["progress"]["message"] == "Training is running."

        status, cancelled = _post_json(port, f"/jobs/{job['job_id']}/cancel", {})
        assert status == 200
        assert cancelled["job"]["job_id"] == job["job_id"]
        assert cancelled["job"]["status"] == "cancelled"
        assert cancelled["cancel_result"]["command_name"] == "stop_training"
        assert calls["stopped"] == 1

        status, after_cancel = _get_json(port, f"/jobs/{job['job_id']}")
        assert status == 200
        assert after_cancel["job"]["status"] == "cancelled"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_training_progress_message_uses_application_state_not_study_trainer():
    class ForbiddenStudy:
        @property
        def trainer(self):
            raise AssertionError("MCP progress must not read service.study.trainer")

    state = SimpleNamespace(
        training=SimpleNamespace(progress_message="Epoch 2/10"),
        active_training=SimpleNamespace(is_running=True),
    )
    service = SimpleNamespace(study=ForbiddenStudy(), get_state=lambda: state)

    assert _training_progress_message(cast(Any, service)) == "Epoch 2/10"


def test_http_mcp_rejects_duplicate_train_start_while_job_is_starting():
    service, calls = _training_ready_service()
    start_entered = Event()
    release_start = Event()
    first_response: dict[str, Any] = {}

    def slow_start_training(*, append: bool = True, interactive: bool = True) -> None:
        calls["started"] += 1
        calls["append"] = append
        calls["interactive"] = interactive
        if calls["started"] == 1:
            start_entered.set()
            release_start.wait(timeout=5)
        calls["running"] = True

    service.training.start_training = slow_start_training
    httpd, port, thread = _start_server(service=service)
    try:
        _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )

        def call_first_train() -> None:
            first_response["value"] = _post_json(
                port,
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "train", "arguments": {"confirmed": True}},
                },
            )

        first_thread = Thread(target=call_first_train)
        first_thread.start()
        assert start_entered.wait(timeout=5)

        status, second = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "train", "arguments": {"confirmed": True}},
            },
        )

        release_start.set()
        first_thread.join(timeout=10)

        assert not first_thread.is_alive()
        assert first_response["value"][0] == 200
        assert first_response["value"][1]["result"]["isError"] is False
        assert status == 200
        assert second["result"]["isError"] is True
        structured = second["result"]["structuredContent"]
        assert structured["accepted"] is False
        assert structured["result"]["error_type"] == "job_already_running"
        assert "Training job is already starting" in structured["result"]["message"]
        assert calls["started"] == 1
    finally:
        release_start.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_http_mcp_job_terminal_status_survives_later_train_runs():
    service, calls = _training_ready_service()
    httpd, port, thread = _start_server(service=service)
    try:
        _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
        )
        status, first_response = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "train", "arguments": {"confirmed": True}},
            },
        )
        assert status == 200
        first_job = first_response["result"]["structuredContent"]["result"]["job"]

        status, cancelled = _post_json(port, f"/jobs/{first_job['job_id']}/cancel", {})
        assert status == 200
        assert cancelled["job"]["status"] == "cancelled"

        status, second_response = _post_json(
            port,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "train", "arguments": {"confirmed": True}},
            },
        )
        assert status == 200
        second_job = second_response["result"]["structuredContent"]["result"]["job"]
        assert calls["started"] == 2

        status, listed_jobs = _get_json(port, "/jobs")
        assert status == 200
        jobs_by_id = {job["job_id"]: job for job in listed_jobs["jobs"]}
        assert jobs_by_id[first_job["job_id"]]["status"] == "cancelled"
        assert jobs_by_id[second_job["job_id"]]["status"] == "running"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)
