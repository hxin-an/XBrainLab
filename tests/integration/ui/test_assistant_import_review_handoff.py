"""Low-mock product gate for assistant-owned Data Import review cancellation."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog

from tests.integration.ui.modal_helpers import visible_modal_dialog
from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import (
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)

EEG_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "multiformat"
    / "A01T-mini-real_raw.fif"
)
_REAL_DIALOG_EXEC = QDialog.exec


def test_assistant_exact_import_review_cancel_leaves_product_unchanged(
    test_app,
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DataInterpretationPreviewDialog,
        "exec",
        lambda dialog: _REAL_DIALOG_EXEC(dialog),
    )
    service = get_application_service(test_app.study)
    scan = service.execute(ScanSourceCommand(source_path=str(EEG_FIXTURE)))
    assert scan.ok, scan.message
    preview = service.execute(
        PreviewInterpretationCommand(choices={"skip_labels": True})
    )
    assert preview.ok, preview.message
    validation = service.execute(ValidateInterpretationCommand())
    assert validation.ok, validation.message

    publication_before = service.get_view_publication()
    interpretation = publication_before.state.interpretation
    assert interpretation.latest_scan_id is not None
    assert interpretation.latest_candidate_id is not None
    identity = InterpretationReviewIdentity(
        publication_generation=publication_before.generation,
        scan_id=interpretation.latest_scan_id,
        candidate_id=interpretation.latest_candidate_id,
    )
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_interpretation",
        decision_fields=("metadata_review",),
        interpretation_identity=identity,
    )

    controller = LLMController(test_app.study)
    correlation = AssistantTurnCorrelation(generation=1, turn_id=1)
    controller.pending_interactions.begin_workflow_handoff(request)
    controller.is_processing = True
    controller._turn_orchestrator.host_turn_generation = correlation.generation
    controller._turn_orchestrator.host_turn_id = correlation.turn_id
    terminals = []
    completions = []
    controller.turn_finished.connect(terminals.append)
    controller.application_command_completed.connect(completions.append)
    host = WorkflowUiHandoffHost(test_app)
    observed: dict[str, object] = {}
    cancel_clicks: list[None] = []

    def _cancel_exact_dialog(attempt: int = 0) -> None:
        dialog = visible_modal_dialog()
        if not isinstance(dialog, DataInterpretationPreviewDialog):
            if attempt < 20:
                QTimer.singleShot(10, lambda: _cancel_exact_dialog(attempt + 1))
            return
        observed["dialog"] = dialog
        observed["step"] = dialog._step_titles[dialog.step_stack.currentIndex()]
        dialog.cancel_button.clicked.connect(lambda: cancel_clicks.append(None))
        qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    QTimer.singleShot(0, _cancel_exact_dialog)
    try:
        resolution = host.open(request)
        assert resolution.status is WorkflowUiHandoffResolutionStatus.CANCELLED, (
            resolution.message
        )
        controller.on_workflow_ui_handoff_resolved(resolution)

        publication_after = service.get_view_publication()
        assert isinstance(observed.get("dialog"), DataInterpretationPreviewDialog)
        assert observed.get("step") == "Review Metadata"
        assert len(cancel_clicks) == 1
        assert host.active_request is None
        assert controller.pending_interactions.workflow_handoff is None
        assert controller.is_processing is False
        assert terminals == [
            AssistantTurnTerminal(
                correlation=correlation,
                outcome="completed",
            )
        ]
        assert completions == []
        assert publication_after.generation == publication_before.generation
        assert publication_after.state == publication_before.state
        assert (
            publication_after.state.interpretation.has_applied_interpretation is False
        )
    finally:
        close_controller_and_wait(controller, qtbot)
