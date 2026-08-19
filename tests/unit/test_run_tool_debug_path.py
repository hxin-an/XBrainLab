"""Launcher path ownership for deferred Assistant walkthrough setup."""

from __future__ import annotations

from pathlib import Path

import run as app_entrypoint
from XBrainLab.debug.tool_debug_mode import ToolDebugMode


def test_repo_relative_walkthrough_path_survives_later_working_directory_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    launch_directory = tmp_path / "launcher"
    later_directory = tmp_path / "later"
    launch_directory.mkdir()
    later_directory.mkdir()
    monkeypatch.chdir(launch_directory)

    resolved = app_entrypoint._resolve_tool_debug_script(
        "scripts/dev/agent_tool_walkthrough/response-presentation.json"
    )

    assert Path(resolved).is_absolute()
    assert Path(resolved).is_file()
    monkeypatch.chdir(later_directory)
    assert ToolDebugMode(resolved).profile_id == "response-presentation"
