from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.dev.write_mcp_client_config import (
    CONFIG_FILENAME,
    LOCAL_SERVER_NAME,
    build_server_command,
    validate_mcp_client_config,
)


def test_committed_mcp_client_config_launches_prepared_runtime(tmp_path: Path):
    root = Path(__file__).parents[3]
    config = json.loads(
        (root / "artifacts" / "mcp" / CONFIG_FILENAME).read_text(encoding="utf-8")
    )
    ok, reason = validate_mcp_client_config(config, repo_root=root)
    assert ok is True, reason

    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/capture_mcp_stdio_walkthrough.py",
            "--output-dir",
            str(tmp_path),
            "--server-command",
            *build_server_command(config, LOCAL_SERVER_NAME),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads((tmp_path / "stdio-walkthrough.json").read_text())
    summary = payload["summary"]

    assert "standard-library" in payload["client_dependency_boundary"]
    assert summary["initialized"] is True
    assert summary["has_scan_source"] is True
    assert summary["tool_results"]["scan_source"]["status"] == "ok"
    assert summary["tool_results"]["preview_interpretation"]["status"] == "ok"
