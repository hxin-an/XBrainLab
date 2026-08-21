#!/usr/bin/env python3
"""Exercise one bounded native desktop lifecycle and write exact evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

REQUIRED_ISOLATED_ENV = (
    "TEMP",
    "TMP",
    "XBRAINLAB_CONFIG_DIR",
    "XBRAINLAB_DATA_DIR",
    "XBRAINLAB_CACHE_DIR",
    "XBRAINLAB_LOG_DIR",
    "XBRAINLAB_MODEL_CACHE_DIR",
    "HF_HOME",
    "MPLCONFIGDIR",
)
PANEL_NAMES = ("dataset", "preprocess", "training", "evaluation", "visualization")
PANEL_TIMEOUT_MS = 20_000
SHUTDOWN_TIMEOUT_MS = 20_000


def _resolved_child(path: str | Path, root: Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"Path escapes the isolated native root: {candidate}"
        ) from error
    return candidate


def validate_isolated_environment(expected_root: str | Path) -> dict[str, str]:
    """Require every mutable smoke path below one owned Unicode root."""
    root = Path(expected_root).expanduser().resolve()
    if " " not in root.name or not any(ord(char) > 127 for char in root.name):
        raise ValueError(
            "The isolated native root must contain a space and non-ASCII text."
        )
    resolved: dict[str, str] = {}
    for variable in REQUIRED_ISOLATED_ENV:
        value = str(os.environ.get(variable, "")).strip()
        if not value:
            raise ValueError(
                f"Required isolated environment variable is missing: {variable}"
            )
        path = _resolved_child(value, root)
        path.mkdir(parents=True, exist_ok=True)
        resolved[variable] = str(path)
    return resolved


def _shutdown_snapshot_is_clean(snapshot: object) -> bool:
    if not isinstance(snapshot, dict):
        return False
    return (
        snapshot.get("application_closed") is True
        and snapshot.get("pre_close_application_idle") is True
        and snapshot.get("pre_close_remaining_workers") == 0
        and snapshot.get("pre_close_remaining_subprocesses") == 0
        and isinstance(snapshot.get("close_attempt_id"), str)
        and bool(str(snapshot["close_attempt_id"]).strip())
    )


def run_native_product_smoke(
    *,
    expected_platform: str,
    expected_isolated_root: str | Path,
) -> dict[str, Any]:
    """Run the real MainWindow, command spine, panel routing, and close path."""
    isolated_environment = validate_isolated_environment(expected_isolated_root)
    isolated_root = Path(expected_isolated_root).expanduser().resolve()

    from PyQt6.QtCore import QEventLoop, QSettings, QTimer
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    qsettings_root = isolated_root / "qt settings"
    qsettings_root.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(qsettings_root),
    )

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    qt_platform = QGuiApplication.platformName()
    if qt_platform != expected_platform:
        raise RuntimeError(
            f"Expected native Qt platform {expected_platform!r}, got {qt_platform!r}."
        )

    from scripts.dev.ui_navigation import open_workflow_panel
    from XBrainLab.backend.application import (
        CommandName,
        NewSessionCommand,
        QueryStateCommand,
    )
    from XBrainLab.backend.application.runtime import (
        get_application_service,
    )
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    study = Study()
    service = get_application_service(study)
    initial_publication = service.get_view_publication()
    initial_query = service.execute(QueryStateCommand(query="state"))
    new_session_capability = service.get_capabilities().get(CommandName.NEW_SESSION)
    if not initial_query.ok:
        raise RuntimeError(f"Initial state query failed: {initial_query.message}")
    if new_session_capability.confirmation_required:
        raise RuntimeError(
            "An empty native session unexpectedly requires confirmation."
        )

    window = MainWindow(study)
    shutdown_snapshots: list[dict[str, Any]] = []
    window.shutdown_completed.connect(shutdown_snapshots.append)
    window.show()
    app.processEvents()

    materialized_panels: list[dict[str, str]] = []
    for index, name in enumerate(PANEL_NAMES):
        panel = open_workflow_panel(window, index, timeout_ms=PANEL_TIMEOUT_MS)
        materialized_panels.append(
            {"index": str(index), "name": name, "class": type(panel).__name__}
        )

    new_session_result = service.execute(NewSessionCommand())
    final_publication = service.get_view_publication()
    if not new_session_result.ok:
        raise RuntimeError(f"New Session failed: {new_session_result.message}")
    if final_publication.generation <= initial_publication.generation:
        raise RuntimeError(
            "New Session did not advance application publication generation."
        )

    shutdown_loop = QEventLoop()

    def _finish_shutdown(snapshot: dict[str, Any]) -> None:
        if shutdown_loop.isRunning():
            shutdown_loop.quit()

    window.shutdown_completed.connect(_finish_shutdown)
    shutdown_timer = QTimer()
    shutdown_timer.setSingleShot(True)
    shutdown_timer.timeout.connect(shutdown_loop.quit)
    shutdown_timer.start(SHUTDOWN_TIMEOUT_MS)
    QTimer.singleShot(0, window.close)
    shutdown_loop.exec()
    shutdown_timer.stop()
    app.processEvents()

    shutdown_snapshot = shutdown_snapshots[-1] if shutdown_snapshots else None
    if not _shutdown_snapshot_is_clean(shutdown_snapshot):
        raise RuntimeError(
            "MainWindow did not publish a clean terminal shutdown snapshot."
        )

    return {
        "schema_version": 1,
        "artifact_type": "xbrainlab.native_platform_product_smoke",
        "passed": True,
        "system": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "qt_platform": qt_platform,
        "expected_qt_platform": expected_platform,
        "isolated_root": str(isolated_root),
        "isolated_environment": isolated_environment,
        "qsettings_root": str(qsettings_root),
        "panels": materialized_panels,
        "initial_query_ok": initial_query.ok,
        "empty_session_confirmation_required": (
            new_session_capability.confirmation_required
        ),
        "initial_generation": initial_publication.generation,
        "final_generation": final_publication.generation,
        "new_session_ok": new_session_result.ok,
        "shutdown": shutdown_snapshot,
    }


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-platform", required=True)
    parser.add_argument("--expected-isolated-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = run_native_product_smoke(
            expected_platform=args.expected_platform,
            expected_isolated_root=args.expected_isolated_root,
        )
    except BaseException as error:
        result = {
            "schema_version": 1,
            "artifact_type": "xbrainlab.native_platform_product_smoke",
            "passed": False,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    _write_artifact(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
