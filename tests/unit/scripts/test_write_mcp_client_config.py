from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.dev.write_mcp_client_config import (
    CONFIG_FILENAME,
    LOCAL_SERVER_NAME,
    WINDOWS_WSL_SERVER_NAME,
    build_mcp_client_config,
    build_server_command,
    validate_mcp_client_config,
)


def test_build_mcp_config_uses_standard_stdio_servers_file(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    wrapper = repo_root / "scripts" / "dev" / "run_mcp_server_for_client.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    config = build_mcp_client_config(repo_root)

    servers = config["mcpServers"]
    assert set(servers) == {LOCAL_SERVER_NAME, WINDOWS_WSL_SERVER_NAME}
    assert servers[LOCAL_SERVER_NAME]["type"] == "stdio"
    assert servers[LOCAL_SERVER_NAME]["command"] == "bash"
    assert servers[LOCAL_SERVER_NAME]["args"] == [str(wrapper)]
    assert servers[WINDOWS_WSL_SERVER_NAME]["type"] == "stdio"
    assert servers[WINDOWS_WSL_SERVER_NAME]["command"] == "wsl.exe"
    assert servers[WINDOWS_WSL_SERVER_NAME]["args"] == ["bash", str(wrapper)]


def test_validate_mcp_config_enforces_external_client_boundary(tmp_path: Path):
    repo_root = tmp_path / "repo"
    wrapper = repo_root / "scripts" / "dev" / "run_mcp_server_for_client.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    config = build_mcp_client_config(repo_root)

    ok, reason = validate_mcp_client_config(config, repo_root=repo_root)

    assert ok is True
    assert reason == ""

    config["mcpServers"][LOCAL_SERVER_NAME]["command"] = sys.executable
    ok, reason = validate_mcp_client_config(config, repo_root=repo_root)

    assert ok is False
    assert "client boundary" in reason


def test_build_server_command_extracts_config_command(tmp_path: Path):
    repo_root = tmp_path / "repo"
    wrapper = repo_root / "scripts" / "dev" / "run_mcp_server_for_client.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    config = build_mcp_client_config(repo_root)

    command = build_server_command(config, LOCAL_SERVER_NAME)

    assert command == ["bash", str(wrapper)]


def test_committed_mcp_config_matches_generator_contract():
    root = Path(__file__).parents[3]
    config_path = root / "artifacts" / "mcp" / CONFIG_FILENAME

    config = json.loads(config_path.read_text(encoding="utf-8"))
    ok, reason = validate_mcp_client_config(config, repo_root=root)

    assert ok is True, reason
    assert build_server_command(config, LOCAL_SERVER_NAME) == [
        "bash",
        str(root / "scripts" / "dev" / "run_mcp_server_for_client.sh"),
    ]


def test_mcp_config_writer_cli_writes_valid_config(tmp_path: Path):
    root = Path(__file__).parents[3]

    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/write_mcp_client_config.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    config = json.loads((tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8"))
    ok, reason = validate_mcp_client_config(config, repo_root=root)

    assert ok is True, reason
    assert "XBrainLab MCP Client Config" in (tmp_path / "xbrainlab-mcp.md").read_text(
        encoding="utf-8"
    )
