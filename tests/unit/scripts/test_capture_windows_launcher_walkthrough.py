from __future__ import annotations

from scripts.dev.capture_windows_launcher_walkthrough import (
    extract_log_path,
    render_markdown,
    startup_geometry_checks,
    windows_log_path_to_wsl,
)


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
