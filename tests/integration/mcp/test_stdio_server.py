from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from XBrainLab.mcp.server import PROTOCOL_VERSION


def _send(proc: subprocess.Popen[str], payload: dict[str, Any]) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line, proc.stderr.read() if proc.stderr is not None else ""
    return json.loads(line)


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
        assert initialized["result"]["capabilities"]["tools"]["listChanged"] is False

        listed = _send(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert any(tool["name"] == "scan_source" for tool in listed["result"]["tools"])

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
        previewed = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "preview_interpretation", "arguments": {}},
            },
        )

        assert scanned["result"]["isError"] is False
        assert previewed["result"]["isError"] is False
        assert (
            previewed["result"]["structuredContent"]["state"]["interpretation"][
                "has_candidate"
            ]
            is True
        )
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=30)
