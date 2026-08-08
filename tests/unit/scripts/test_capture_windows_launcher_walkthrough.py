from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from scripts.dev.capture_windows_launcher_walkthrough import (
    ACTIVE_WSL_REPO,
    REPO_ROOT,
    _windows_path,
    extract_log_path,
    launcher_windows_paths,
    render_markdown,
    startup_geometry_checks,
    windows_log_path_to_wsl,
)


def test_launcher_walkthrough_targets_the_active_repository() -> None:
    assert str(REPO_ROOT) == ACTIVE_WSL_REPO
    launcher_relative_path = (
        "scripts",
        "launchers",
        "xbrainlab_wsl_launcher.ps1",
    )
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert REPO_ROOT.joinpath(*launcher_relative_path).is_file()


def test_launcher_windows_paths_are_derived_from_a_wsl_mount() -> None:
    repo_root = PurePosixPath("/mnt/d/workspace_v2/projects/lab/xbrainlab")

    active_windows_repo, powershell_launcher = launcher_windows_paths(repo_root)

    assert PureWindowsPath(active_windows_repo) == PureWindowsPath(
        r"D:\workspace_v2\projects\lab\xbrainlab"
    )
    assert PureWindowsPath(powershell_launcher) == PureWindowsPath(
        active_windows_repo,
    ).joinpath(
        "scripts",
        "launchers",
        "xbrainlab_wsl_launcher.ps1",
    )
    assert "integrated-manual" not in powershell_launcher.lower()


def test_windows_path_rejects_non_wsl_paths_when_resolution_is_requested() -> None:
    with pytest.raises(RuntimeError, match=r"Expected a /mnt/<drive>/ path"):
        _windows_path(
            PurePosixPath(
                "/Users/runner/work/XBrainLab/XBrainLab/scripts/launchers/"
                "xbrainlab_wsl_launcher.ps1"
            )
        )


def test_active_launcher_sources_do_not_reference_retired_worktrees() -> None:
    launcher_dir = REPO_ROOT / "scripts" / "launchers"
    launcher_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(launcher_dir.glob("xbrainlab_wsl_launcher.*"))
    )

    assert "XBrainLab-integrated-manual" not in launcher_text


def test_extracts_and_converts_windows_launcher_log_path() -> None:
    output = (
        "Log: C:\\Users\\Administrator\\AppData\\Local\\XBrainLab\\logs"
        "\\launcher-20260504-112233.log\r\n"
    )

    path = extract_log_path(output)

    assert path.endswith("launcher-20260504-112233.log")
    assert windows_log_path_to_wsl(path).endswith(
        "/Users/Administrator/AppData/Local/XBrainLab/logs/launcher-20260504-112233.log"
    )


def test_render_markdown_keeps_launcher_claim_boundary() -> None:
    payload = {
        "status": "passed",
        "claim_boundary": "Automated walkthrough; not a human click-through.",
        "desktop_cmd": "C:\\Users\\Administrator\\Desktop\\XBrainLab.cmd",
        "powershell_launcher": "D:\\workspace_v2\\projects\\lab\\XBrainLab\\x.ps1",
        "active_wsl_repo": "/mnt/d/workspace_v2/projects/lab/XBrainLab",
        "checks": {"startup_saw_main_window": True},
        "log_paths": {"startup": "/mnt/c/logs/launcher.log"},
        "commands": [
            {
                "name": "powershell_startup_smoke",
                "returncode": 0,
                "stdout": "MainWindow initialized\nGUI kept running until timeout",
            }
        ],
    }

    rendered = render_markdown(payload)

    assert "not a human click-through" in rendered
    assert "`startup_saw_main_window`: `True`" in rendered
    assert "MainWindow initialized" in rendered


def test_startup_geometry_checks_require_screen_and_widget_diagnostics() -> None:
    checks = startup_geometry_checks(
        "\n".join(
            [
                "startup geometry: screen_count=1 primary='screen'",
                "startup geometry: screen[0] name='screen'",
                "startup geometry: splash.after_show geometry=(10,10 420x260)",
                "startup geometry: main_window.after_show geometry=(20,20 1280x820)",
            ]
        )
    )

    assert checks == {
        "startup_geometry_screen_count_logged": True,
        "startup_geometry_screen_detail_logged": True,
        "startup_geometry_splash_logged": True,
        "startup_geometry_main_window_logged": True,
    }
