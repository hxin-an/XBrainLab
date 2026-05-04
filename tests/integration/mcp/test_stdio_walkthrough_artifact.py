from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_capture_mcp_stdio_walkthrough_writes_client_artifact(tmp_path: Path):
    root = Path(__file__).parents[3]

    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/capture_mcp_stdio_walkthrough.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads((tmp_path / "stdio-walkthrough.json").read_text())
    markdown = (tmp_path / "stdio-walkthrough.md").read_text(encoding="utf-8")

    assert "standard-library" in payload["client_dependency_boundary"]
    assert payload["summary"]["initialized"] is True
    assert payload["summary"]["has_scan_source"] is True
    assert payload["summary"]["scan_source_taxonomy"] == "data_interpretation"
    assert payload["summary"]["adapter_boundary"]["mode"] == "headless_mcp_stdio"
    assert payload["summary"]["adapter_boundary"]["transport"] == "stdio"
    assert payload["summary"]["adapter_boundary"]["ui_refresh_supported"] is False
    assert payload["summary"]["adapter_boundary"]["session_id_stable"] is True
    assert payload["summary"]["tool_results"]["scan_source"]["status"] == "ok"
    assert payload["summary"]["tool_results"]["preview_interpretation"]["status"] == (
        "ok"
    )
    assert payload["summary"]["tool_results"]["train"]["status"] == "failed"
    assert payload["summary"]["long_running_boundary"]["error_type"] == (
        "long_running_job_required"
    )
    assert payload["summary"]["long_running_boundary"]["supported"] is False
    assert "MCP Stdio Walkthrough" in markdown
    assert "headless_mcp_stdio" in markdown
    assert "long_running_job_required" in markdown
