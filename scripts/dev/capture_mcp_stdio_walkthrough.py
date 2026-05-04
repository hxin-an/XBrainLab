#!/usr/bin/env python3
"""Capture an MCP stdio client walkthrough artifact.

The client side intentionally uses only the Python standard library. The spawned
server runs inside the prepared XBrainLab runtime and owns the ApplicationService
dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2025-06-18"


@dataclass(frozen=True)
class ClientStep:
    """One client-observable MCP request/response pair."""

    label: str
    request: dict[str, Any]
    response: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="artifacts/mcp",
        help="Directory for walkthrough JSON and Markdown artifacts.",
    )
    parser.add_argument(
        "--server-command",
        nargs="+",
        default=[sys.executable, "scripts/dev/run_mcp_server.py"],
        help="Command used to launch the prepared XBrainLab MCP stdio server.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stdio-walkthrough.json"
    md_path = output_dir / "stdio-walkthrough.md"

    with tempfile.TemporaryDirectory(prefix="xbrainlab-mcp-") as tmp:
        source = Path(tmp) / "sub-01_task-mi_run-1.gdf"
        source.write_bytes(b"placeholder")
        steps = run_walkthrough(args.server_command, source)

    payload = {
        "client_dependency_boundary": (
            "Client script imports only Python standard-library modules; "
            "XBrainLab runtime dependencies stay in the spawned server process."
        ),
        "server_command": args.server_command,
        "steps": [asdict(step) for step in steps],
        "summary": summarize_steps(steps),
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def run_walkthrough(server_command: list[str], source: Path) -> list[ClientStep]:
    proc = subprocess.Popen(  # noqa: S603
        server_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    steps: list[ClientStep] = []
    try:
        steps.append(
            _exchange(
                proc,
                "initialize",
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "xbrainlab-stdio-walkthrough",
                            "version": "1.0",
                        },
                    },
                },
            )
        )
        steps.append(
            _exchange(
                proc,
                "tools/list",
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
        )
        steps.append(
            _exchange(
                proc,
                "scan_source",
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
        )
        steps.append(
            _exchange(
                proc,
                "preview_interpretation",
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "preview_interpretation",
                        "arguments": {},
                    },
                },
            )
        )
        steps.append(
            _exchange(
                proc,
                "validate_interpretation",
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "validate_interpretation",
                        "arguments": {},
                    },
                },
            )
        )
        steps.append(
            _exchange(
                proc,
                "train",
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "train",
                        "arguments": {},
                    },
                },
            )
        )
        return steps
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)


def summarize_steps(steps: list[ClientStep]) -> dict[str, Any]:
    listed_tools = _tools_by_name(_step_result(steps, "tools/list").get("tools", []))
    tool_results = {
        step.label: _tool_result_summary(step.response)
        for step in steps
        if step.request.get("method") == "tools/call"
    }
    adapter_boundary = _adapter_boundary_summary(steps)
    long_running_boundary = _long_running_boundary_summary(steps)
    return {
        "initialized": "result" in steps[0].response,
        "tool_count": len(listed_tools),
        "has_scan_source": "scan_source" in listed_tools,
        "has_preview_interpretation": "preview_interpretation" in listed_tools,
        "scan_source_taxonomy": listed_tools.get("scan_source", {})
        .get("x_xbrainlab", {})
        .get("taxonomy"),
        "adapter_boundary": adapter_boundary,
        "long_running_boundary": long_running_boundary,
        "tool_results": tool_results,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# XBrainLab MCP Stdio Walkthrough",
        "",
        f"- client dependency boundary: {payload['client_dependency_boundary']}",
        f"- server command: `{' '.join(payload['server_command'])}`",
        f"- initialized: `{summary['initialized']}`",
        f"- tool count: `{summary['tool_count']}`",
        f"- has scan_source: `{summary['has_scan_source']}`",
        f"- scan_source taxonomy: `{summary['scan_source_taxonomy']}`",
        f"- adapter mode: `{summary['adapter_boundary']['mode']}`",
        f"- adapter transport: `{summary['adapter_boundary']['transport']}`",
        f"- session id stable: `{summary['adapter_boundary']['session_id_stable']}`",
        f"- UI refresh supported: `{summary['adapter_boundary']['ui_refresh_supported']}`",
        f"- UI refresh boundary: {summary['adapter_boundary']['ui_refresh_reason']}",
        f"- long-running boundary: `{summary['long_running_boundary']['error_type']}`",
        f"- long-running job supported: `{summary['long_running_boundary']['supported']}`",
        "",
        "## Tool Calls",
        "",
    ]
    for name, result in summary["tool_results"].items():
        lines.extend(
            [
                f"### {name}",
                "",
                f"- isError: `{result['is_error']}`",
                f"- status: `{result['status']}`",
                f"- text: {result['text']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _exchange(
    proc: subprocess.Popen[str],
    label: str,
    request: dict[str, Any],
) -> ClientStep:
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("MCP process was not opened with stdio pipes.")
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(f"MCP server closed before {label} response: {stderr}")
    return ClientStep(label=label, request=request, response=json.loads(line))


def _step_result(steps: list[ClientStep], label: str) -> dict[str, Any]:
    for step in steps:
        if step.label == label:
            return step.response.get("result", {})
    return {}


def _adapter_boundary_summary(steps: list[ClientStep]) -> dict[str, Any]:
    adapters: list[dict[str, Any]] = []
    for step in steps:
        result = step.response.get("result")
        if not isinstance(result, dict):
            continue
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            continue
        adapter = structured.get("adapter")
        if isinstance(adapter, dict):
            adapters.append(adapter)
    first = adapters[0] if adapters else {}
    session_ids = {str(adapter.get("session_id") or "") for adapter in adapters}
    ui_refresh = first.get("ui_refresh") if isinstance(first, dict) else {}
    if not isinstance(ui_refresh, dict):
        ui_refresh = {}
    return {
        "mode": str(first.get("mode") or "unknown"),
        "transport": str(first.get("transport") or "unknown"),
        "session_id": str(first.get("session_id") or ""),
        "session_id_stable": len(session_ids - {""}) <= 1,
        "ui_refresh_supported": bool(ui_refresh.get("supported")),
        "ui_refresh_reason": str(ui_refresh.get("reason") or ""),
    }


def _long_running_boundary_summary(steps: list[ClientStep]) -> dict[str, Any]:
    for step in steps:
        if step.label != "train":
            continue
        result = step.response.get("result")
        if not isinstance(result, dict):
            break
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            break
        command_result = structured.get("result")
        if not isinstance(command_result, dict):
            break
        diagnostics = command_result.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        boundary = diagnostics.get("job_boundary")
        if not isinstance(boundary, dict):
            boundary = {}
        return {
            "error_type": str(command_result.get("error_type") or ""),
            "supported": bool(boundary.get("supported")),
            "required_transport": str(boundary.get("required_transport") or ""),
            "supports_progress": bool(boundary.get("supports_progress")),
            "supports_cancel": bool(boundary.get("supports_cancel")),
        }
    return {
        "error_type": "",
        "supported": False,
        "required_transport": "",
        "supports_progress": False,
        "supports_cancel": False,
    }


def _tools_by_name(tools: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(tools, list):
        return {}
    return {
        str(tool["name"]): tool
        for tool in tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }


def _tool_result_summary(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result", {})
    structured = result.get("structuredContent", {}) if isinstance(result, dict) else {}
    command_result = (
        structured.get("result", {}) if isinstance(structured, dict) else {}
    )
    content = result.get("content", []) if isinstance(result, dict) else []
    text = ""
    if content and isinstance(content[0], dict):
        text = str(content[0].get("text", ""))
    return {
        "is_error": result.get("isError") if isinstance(result, dict) else None,
        "status": command_result.get("status")
        if isinstance(command_result, dict)
        else None,
        "text": text,
    }


if __name__ == "__main__":
    raise SystemExit(main())
