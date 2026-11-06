"""Real diagnostic tool-to-dialog import completion and cancellation."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog

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
from XBrainLab.ui.application_capabilities import application_ui_runtime
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


@pytest.mark.optional_public_fixture
@pytest.mark.usefixtures("allow_real_modals")
def test_assistant_bids_handoff_completes_after_real_wizard_apply(
    test_app, qtbot, monkeypatch
) -> None:
    """The Assistant terminal follows the confirmed import, not dialog opening."""
    from tests.integration.ui.test_data_import_wizard_real_fixture_acceptance import (
        PUBLIC_BIDS_ROOT,
        _require_manifest_group,
        _start_wizard_driver,
        _wait_for_applied_interpretation,
    )

    _require_manifest_group("mne-bids-tiny-eeg")
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_args, **_kwargs: str(PUBLIC_BIDS_ROOT)),
    )
    service = get_application_service(test_app.study)
    panel = test_app.dataset_panel
    runtime = application_ui_runtime(panel)
    assert runtime is not None
    controller = LLMController(test_app.study)
    host = WorkflowUiHandoffHost(test_app)
    correlation = AssistantTurnCorrelation(generation=1, turn_id=1)
    terminals = []
    resolutions = []
    controller.turn_finished.connect(terminals.append)

    def _deliver_resolution(resolution):
        resolutions.append(resolution)
        if resolution.status is WorkflowUiHandoffResolutionStatus.COMPLETED:
            assert service.get_view_publication().state.interpretation.has_applied_interpretation
        controller.on_workflow_ui_handoff_resolved(resolution)

    def _open_request(request):
        assert request.tool_name == "import_eeg_data"
        resolution = host.open(request, on_terminal=_deliver_resolution)
        _deliver_resolution(resolution)

    controller.workflow_ui_handoff_requested.connect(_open_request)
    driver = _start_wizard_driver(
        resolve_bids_values=True, source_picker="folder", runtime=runtime
    )
    try:
        acknowledgement = controller.execute_debug_tool(
            AssistantDebugToolRequest.from_params(
                correlation=correlation, tool_name="import_eeg_data", params={}
            )
        )
        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        _wait_for_applied_interpretation(qtbot, driver, runtime, panel)
        qtbot.waitUntil(lambda: bool(terminals), timeout=10_000)
        assert driver.trace[0] == "select BIDS subjects: 01"
        assert driver.trace[-1] == "confirm and import"
        assert driver.fresh_pre_confirm_state == (0, False)
        assert driver.fresh_review_decisions == ["safe"]
        assert [item.status for item in resolutions if item.status.is_terminal] == [
            WorkflowUiHandoffResolutionStatus.COMPLETED
        ]
        assert terminals == [
            AssistantTurnTerminal(correlation=correlation, outcome="completed")
        ]
        assert host.active_request is None
        assert controller.pending_interactions.workflow_handoff is None
        assert controller.is_processing is False
        assert service.get_view_publication().state.interpretation.class_map == {
            "show_stimulus": "show stimulus"
        }
    finally:
        driver.timer.stop()
        close_controller_and_wait(controller, qtbot)
