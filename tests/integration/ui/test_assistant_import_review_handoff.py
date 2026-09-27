"""Real diagnostic tool-to-dialog cancellation without backend mutation."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QDialogButtonBox

from tests.integration.ui.modal_helpers import visible_modal_dialog
from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import get_application_service
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryPhase,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffResolutionStatus
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
    EegSourceChooserDialog,
)

_REAL_DIALOG_EXEC = QDialog.exec


def test_assistant_import_dialog_cancel_leaves_product_unchanged(
    test_app,
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        EegSourceChooserDialog,
        "exec",
        lambda dialog: _REAL_DIALOG_EXEC(dialog),
    )
    service = get_application_service(test_app.study)
    publication_before = service.get_view_publication()
    controller = LLMController(test_app.study)
    correlation = AssistantTurnCorrelation(generation=1, turn_id=1)
    terminals = []
    completions = []
    resolutions = []
    controller.turn_finished.connect(terminals.append)
    controller.application_command_completed.connect(completions.append)
    host = WorkflowUiHandoffHost(test_app)
    observed: list[EegSourceChooserDialog] = []
    cancel_clicks: list[None] = []

    def _open_request(request) -> None:
        assert request.tool_name == "import_eeg_data"
        assert request.command_name == "scan_source"
        resolution = host.open(request)
        resolutions.append(resolution)
        controller.on_workflow_ui_handoff_resolved(resolution)

    controller.workflow_ui_handoff_requested.connect(_open_request)

    def _cancel_exact_dialog(attempt: int = 0) -> None:
        dialog = visible_modal_dialog()
        if not isinstance(dialog, EegSourceChooserDialog):
            if attempt < 20:
                QTimer.singleShot(10, lambda: _cancel_exact_dialog(attempt + 1))
            return
        observed.append(dialog)
        cancel_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel_button is not None
        cancel_button.clicked.connect(lambda: cancel_clicks.append(None))
        qtbot.mouseClick(cancel_button, Qt.MouseButton.LeftButton)

    QTimer.singleShot(0, _cancel_exact_dialog)
    try:
        acknowledgement = controller.execute_debug_tool(
            AssistantDebugToolRequest.from_params(
                correlation=correlation,
                tool_name="import_eeg_data",
                params={},
            )
        )
        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        assert len(resolutions) == 1
        assert resolutions[0].status is WorkflowUiHandoffResolutionStatus.CANCELLED
        assert len(observed) == 1
        assert len(cancel_clicks) == 1
        assert host.active_request is None
        assert controller.pending_interactions.workflow_handoff is None
        assert controller.is_processing is False
        assert terminals == [
            AssistantTurnTerminal(correlation=correlation, outcome="cancelled")
        ]
        assert completions == []
        publication_after = service.get_view_publication()
        assert publication_after.generation == publication_before.generation
        assert publication_after.state == publication_before.state
    finally:
        close_controller_and_wait(controller, qtbot)
