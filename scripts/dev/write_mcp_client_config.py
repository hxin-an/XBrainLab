#!/usr/bin/env python3
"""Write MCP client configuration for the prepared XBrainLab runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "xbrainlab-mcp.json"
MARKDOWN_FILENAME = "xbrainlab-mcp.md"
LOCAL_SERVER_NAME = "default-server"
WINDOWS_WSL_SERVER_NAME = "xbrainlab-windows-wsl"
WRAPPER_RELATIVE_PATH = Path("scripts/dev/run_mcp_server_for_client.sh")
WRAPPER_CLIENT_ARG = "scripts/dev/run_mcp_server_for_client.sh"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="artifacts/mcp",
        help="Directory for MCP client config artifacts.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Prepared XBrainLab repo root used by the MCP server wrapper.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    repo_root = Path(args.repo_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = build_mcp_client_config(repo_root)
    ok, reason = validate_mcp_client_config(config, repo_root=repo_root)
    if not ok:
        raise SystemExit(reason)

    config_path = output_dir / CONFIG_FILENAME
    markdown_path = output_dir / MARKDOWN_FILENAME
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(config, repo_root), encoding="utf-8")
    print(f"Wrote {config_path}")
    print(f"Wrote {markdown_path}")
    return 0


def build_mcp_client_config(repo_root: Path) -> dict[str, Any]:
    """Build an Inspector-compatible MCP servers file."""
    return {
        "mcpServers": {
            LOCAL_SERVER_NAME: {
                "type": "stdio",
                "command": "bash",
                "args": [WRAPPER_CLIENT_ARG],
                "env": {"PYTHONUNBUFFERED": "1"},
            },
            WINDOWS_WSL_SERVER_NAME: {
                "type": "stdio",
                "command": "wsl.exe",
                "args": ["bash", WRAPPER_CLIENT_ARG],
                "env": {"PYTHONUNBUFFERED": "1"},
            },
        }
    }


def validate_mcp_client_config(
    config: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[bool, str]:
    """Validate the committed config keeps the client dependency boundary."""
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        return False, "MCP config must contain an mcpServers object."

    required = {LOCAL_SERVER_NAME, WINDOWS_WSL_SERVER_NAME}
    missing = sorted(required.difference(servers))
    if missing:
        return False, f"MCP config missing server entries: {', '.join(missing)}."

    wrapper = repo_root / WRAPPER_RELATIVE_PATH
    if not wrapper.exists():
        return False, f"MCP server wrapper does not exist: {wrapper}."

    local = servers[LOCAL_SERVER_NAME]
    ok, reason = _validate_server_entry(
        local,
        command="bash",
        args=[WRAPPER_CLIENT_ARG],
        boundary="local prepared runtime",
    )
    if not ok:
        return False, reason

    windows = servers[WINDOWS_WSL_SERVER_NAME]
    ok, reason = _validate_server_entry(
        windows,
        command="wsl.exe",
        args=["bash", WRAPPER_CLIENT_ARG],
        boundary="Windows WSL prepared runtime",
    )
    if not ok:
        return False, reason

    for name, entry in servers.items():
        if not isinstance(entry, dict):
            return False, f"MCP server entry {name} must be an object."
        if entry.get("command") in {"python", "python3"}:
            return False, (
                f"MCP server entry {name} violates the client boundary: "
                "client config must launch the prepared runtime wrapper."
            )
        if str(entry.get("command", "")).endswith("python"):
            return False, (
                f"MCP server entry {name} violates the client boundary: "
                "client config must not point directly at a client Python."
            )

    return True, ""


def build_server_command(
    config: dict[str, Any],
    server_name: str = LOCAL_SERVER_NAME,
) -> list[str]:
    """Extract a process command list from a standard MCP servers file."""
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError("MCP config must contain mcpServers.")
    entry = servers.get(server_name)
    if not isinstance(entry, dict):
        raise ValueError(f"MCP config does not contain server {server_name}.")
    command = entry.get("command")
    args = entry.get("args", [])
    if not isinstance(command, str) or not command:
        raise ValueError(f"MCP server {server_name} is missing command.")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError(f"MCP server {server_name} args must be strings.")
    return [command, *args]


def render_markdown(config: dict[str, Any], repo_root: Path) -> str:
    local_command = " ".join(build_server_command(config, LOCAL_SERVER_NAME))
    windows_command = " ".join(build_server_command(config, WINDOWS_WSL_SERVER_NAME))
    lines = [
        "# XBrainLab MCP Client Config",
        "",
        f"- config: `{CONFIG_FILENAME}`",
        f"- repo root: `{repo_root}`",
        "- transport: `stdio`",
        "- client dependency boundary: the MCP client launches a prepared "
        "XBrainLab runtime wrapper; EEG, PyQt, PyTorch, and local LLM "
        "dependencies stay in the server process.",
        "",
        "## Servers",
        "",
        f"- `{LOCAL_SERVER_NAME}`: `{local_command}`",
        f"- `{WINDOWS_WSL_SERVER_NAME}`: `{windows_command}`",
        "",
        "## Inspector",
        "",
        "```bash",
        f"npx @modelcontextprotocol/inspector --config {CONFIG_FILENAME} "
        f"--server {LOCAL_SERVER_NAME}",
        "```",
        "",
        "The Windows entry is for MCP clients launched from Windows that need to "
        "start the prepared WSL runtime.",
        "",
    ]
    return "\n".join(lines)


def _validate_server_entry(
    entry: Any,
    *,
    command: str,
    args: list[str],
    boundary: str,
) -> tuple[bool, str]:
    if not isinstance(entry, dict):
        return False, f"MCP server entry for {boundary} must be an object."
    if entry.get("type") != "stdio":
        return False, f"MCP server entry for {boundary} must use stdio."
    if entry.get("command") != command:
        return False, (
            f"MCP server entry for {boundary} violates the client boundary: "
            f"expected command {command}."
        )
    if entry.get("args") != args:
        return False, (
            f"MCP server entry for {boundary} violates the client boundary: "
            "expected prepared runtime wrapper args."
        )
    env = entry.get("env", {})
    if not isinstance(env, dict) or env.get("PYTHONUNBUFFERED") != "1":
        return False, f"MCP server entry for {boundary} must set PYTHONUNBUFFERED."
    return True, ""


if __name__ == "__main__":
    raise SystemExit(main())
