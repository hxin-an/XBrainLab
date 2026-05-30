"""ApplicationService command runner for modal Data Import review refreshes."""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.application_capabilities import execute_application_command


def execute_interpretation_command_responsive(
    panel: QWidget,
    command: Any,
    *,
    error_title: str,
) -> Any:
    """Run a modal review refresh through the command API without fallback paths."""
    _ = error_title
    return execute_application_command(panel, command)
