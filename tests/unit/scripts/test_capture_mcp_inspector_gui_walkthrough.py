from __future__ import annotations

from pathlib import Path

from scripts.dev.capture_mcp_inspector_gui_walkthrough import (
    EXPECTED_VISIBLE_TOOL_LABELS,
    EXPECTED_VISIBLE_TOOLS,
    build_checks,
    extract_inspector_url,
    render_markdown,
    sanitize_text,
    validate_mcp_inspector_payload,
    wsl_path_to_windows,
)


def _payload(tmp_path: Path) -> dict[str, object]:
    screenshot = tmp_path / "inspector-gui-connected.png"
    screenshot.write_bytes(b"\x89PNG\r\n" + (b"0" * 6000))
    return {
        "status": "passed",
        "claim_boundary": (
            "Automated MCP Inspector GUI click-through; not full MCP client "
            "certification."
        ),
        "inspector_url": ("http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<redacted>"),
        "server_name": "xbrainlab-windows-wsl",
        "node_result": {
            "click": "clicked Connect",
            "connected": True,
            "serverNameVisible": True,
            "commandValue": "wsl.exe",
            "argumentsValue": (
                "bash /mnt/d/workspace_v2/projects/lab/XBrainLab/"
                "scripts/dev/run_mcp_server_for_client.sh"
            ),
            "toolsVisible": dict.fromkeys(EXPECTED_VISIBLE_TOOLS, True),
            "toolLabelsVisible": dict.fromkeys(EXPECTED_VISIBLE_TOOLS, True),
            "after": {
                "text": (
                    "Connected\nxbrainlab\nTools\nList Tools\n"
                    "Scan Source\nPreview Interpretation\n"
                    "Validate Interpretation\nApply Interpretation"
                ),
                "buttons": ["Restart", "Disconnect", "Tools", "List Tools"],
            },
        },
        "screenshot": str(screenshot),
    }


def test_extracts_and_sanitizes_inspector_url() -> None:
    line = "http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=abc123deadbeef"

    assert extract_inspector_url(line) == line
    assert "abc123" not in sanitize_text(line)
    assert "MCP_PROXY_AUTH_TOKEN=<redacted>" in sanitize_text(line)


def test_wsl_path_to_windows_converts_mounted_drive() -> None:
    path = Path("/mnt/d/workspace_v2/projects/lab/XBrainLab/artifacts/mcp/x.png")

    assert wsl_path_to_windows(path) == (
        r"D:\workspace_v2\projects\lab\XBrainLab\artifacts\mcp\x.png"
    )


def test_validate_payload_accepts_gui_connected_tools(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    ok, reason = validate_mcp_inspector_payload(payload)

    assert ok is True
    assert reason == ""
    assert all(build_checks(payload).values())


def test_validate_payload_rejects_missing_visible_tool(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    node_result = payload["node_result"]
    assert isinstance(node_result, dict)
    tools_visible = node_result["toolsVisible"]
    assert isinstance(tools_visible, dict)
    tools_visible["apply_interpretation"] = False
    after = node_result["after"]
    assert isinstance(after, dict)
    after["text"] = str(after["text"]).replace(
        EXPECTED_VISIBLE_TOOL_LABELS["apply_interpretation"],
        "",
    )

    ok, reason = validate_mcp_inspector_payload(payload)

    assert ok is False
    assert "apply_interpretation" in reason


def test_render_markdown_records_gui_claim_boundary(tmp_path: Path) -> None:
    markdown = render_markdown(_payload(tmp_path))

    assert "# MCP Inspector GUI Walkthrough" in markdown
    assert "not full MCP client certification" in markdown
    assert "`connected_visible`: `True`" in markdown
    assert "scan_source" in markdown
