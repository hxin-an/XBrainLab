"""Correlated Data Import wizard capture and cancellation helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.validation import (
    EXPECTED_DECISION_FIELDS,
    EXPECTED_WIZARD_STEPS,
    EXPECTED_WIZARD_TARGET,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def capture_and_cancel_workflow_dialog(
    dialog: Any,
    *,
    request: Any,
    controller_request: Any,
    host_request: Any,
    screenshot_path: Path,
    capture: Callable[[Any, Path], int],
) -> dict[str, Any]:
    """Capture and cancel the exact typed Data Import workflow handoff."""
    if (
        not isinstance(dialog, DataInterpretationPreviewDialog)
        or not dialog.isVisible()
    ):
        raise RuntimeError(
            "Workflow handoff dialog must be a visible DataInterpretationPreviewDialog."
        )
    if not all(
        isinstance(value, WorkflowUiHandoffRequest)
        for value in (request, controller_request, host_request)
    ):
        raise RuntimeError("Workflow handoff owners must expose typed requests.")
    if controller_request != request or host_request != request:
        raise RuntimeError("Workflow handoff owners disagree on request identity.")
    if request.command_name != "apply_interpretation":
        raise RuntimeError("Workflow handoff is not for interpretation apply.")
    if request.decision_fields != EXPECTED_DECISION_FIELDS:
        raise RuntimeError("Workflow handoff decision fields are not exact.")

    step_titles = tuple(getattr(dialog, "_step_titles", ()))
    current_index = dialog.step_stack.currentIndex()
    current_title = (
        step_titles[current_index] if 0 <= current_index < len(step_titles) else ""
    )
    if step_titles != EXPECTED_WIZARD_STEPS or current_title != EXPECTED_WIZARD_TARGET:
        raise RuntimeError("Data Import wizard did not open at the exact target step.")
    cancel_button = dialog.cancel_button
    if (
        cancel_button.text() != "Cancel"
        or not cancel_button.isVisible()
        or not cancel_button.isEnabled()
    ):
        raise RuntimeError("Data Import wizard has no usable Cancel action.")

    screenshot_path = Path(screenshot_path)
    if capture(dialog, screenshot_path) != 0:
        raise RuntimeError("Data Import wizard screenshot could not be captured.")
    clicked: list[bool] = []
    cancel_button.clicked.connect(lambda: clicked.append(True))
    evidence = {
        "dialog_opened": True,
        "dialog_visible": True,
        "dialog_class": f"{type(dialog).__module__}.{type(dialog).__qualname__}",
        "object_name": dialog.objectName(),
        "dialog_title": dialog.windowTitle(),
        "request_id": request.request_id,
        "decision_fields": list(request.decision_fields),
        "step_titles": list(step_titles),
        "current_step_index": current_index,
        "current_step_title": current_title,
        "cancel_button_text": cancel_button.text(),
        "cancel_clicked": True,
        "screenshot": str(screenshot_path),
    }
    cancel_button.click()
    evidence["cancel_signal_observed"] = clicked == [True]
    evidence["visible_after_cancel_click"] = dialog.isVisible()
    return evidence
