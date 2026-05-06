from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_capture_mcp_http_walkthrough_writes_client_artifact(tmp_path: Path):
    root = Path(__file__).parents[3]

    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/capture_mcp_http_walkthrough.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=root,
        check=True,
    )

    payload = json.loads((tmp_path / "http-walkthrough.json").read_text())
    markdown = (tmp_path / "http-walkthrough.md").read_text(encoding="utf-8")

    assert payload["workflow"] == "mcp_http_walkthrough"
    assert payload["summary"]["health_ok"] is True
    assert payload["summary"]["tools_listed"] is True
    assert payload["summary"]["scan_ok"] is True
    assert payload["summary"]["preview_ok"] is True
    assert payload["summary"]["headless_http_adapter"] is True
    assert payload["summary"]["train_job_created"] is True
    assert payload["summary"]["job_status_running"] is True
    assert payload["summary"]["cancel_ok"] is True
    assert payload["summary"]["train_job_id"].startswith("mcp-http-job-")
    assert "MCP HTTP Walkthrough" in markdown
    assert "job status after cancel: `cancelled`" in markdown
