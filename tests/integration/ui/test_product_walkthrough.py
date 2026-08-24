"""Product-level UI walkthroughs for XBrainLab desktop workflows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import mne
import numpy as np
import pytest
import torch
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QMessageBox,
    QWidget,
)

import XBrainLab.backend.application.service as application_service_module
from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    CommandName,
    DatasetSplitContextRequest,
    DatasetSplitPreviewReceipt,
    DatasetSplitPreviewRequest,
    DatasetSplitSpecification,
    LoadDataCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)
from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.record import EvalRecord, RecordKey, TrainRecordKey
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle
from XBrainLab.llm.agent.response_presentation import AssistantResponsePresentation
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationRequest,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest
from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeCommandAdmissionStatus,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantWorkflowSurface,
    build_assistant_status_projection,
)
from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
    _dataset_dialog_start_directory,
)

EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY = {
    "count": 1,
    "train_count": 7,
    "val_count": 2,
    "test_count": 3,
    "audit": {
        "ok": True,
        "dataset_count": 1,
        "issues": [],
        "truncated_issue_count": 0,
    },
}


class _ReadyAssistantIntegrationRuntime(QObject):
    """Admit real controller turns without loading an external model."""

    controller_created = pyqtSignal(object)
    runtime_snapshot_changed = pyqtSignal(object)
    turn_finished = pyqtSignal(object)

    def __init__(self, controller: LLMController) -> None:
        super().__init__()
        self.controller = controller
        self.initialized = True
        self.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="integration-test-model",
        )
        self.submissions: list[str] = []
        self.delivery_phases: list[AssistantTurnDeliveryPhase] = []
        self._started = False
        self._next_turn_id = 1
        controller.turn_finished.connect(self.turn_finished.emit)

    def replay_runtime_snapshot(self) -> None:
        self.runtime_snapshot_changed.emit(self.current)

    def start(self) -> bool:
        if not self._started:
            self._started = True
            self.controller_created.emit(self.controller)
        self.runtime_snapshot_changed.emit(self.current)
        return True

    def submit(
        self,
        text: str,
        *,
        generation: int | None = None,
    ) -> RuntimeCommandAdmissionResult:
        correlation = AssistantTurnCorrelation(
            generation=1 if generation is None else generation,
            turn_id=self._next_turn_id,
        )
        self._next_turn_id += 1
        self.submissions.append(text)
        delivery = self.controller.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=correlation,
                text=text,
            )
        )
        self.delivery_phases.append(delivery.phase)
        accepted = delivery.phase is AssistantTurnDeliveryPhase.ACCEPTED
        return RuntimeCommandAdmissionResult(
            command_name="submit",
            status=(
                RuntimeCommandAdmissionStatus.ACCEPTED
                if accepted
                else RuntimeCommandAdmissionStatus.REJECTED
            ),
            message=delivery.message,
            turn_id=correlation.turn_id if accepted else None,
            generation=correlation.generation if accepted else None,
        )

    def resolve_ui_handoff(self, resolution) -> RuntimeCommandAdmissionResult:
        self.controller.on_workflow_ui_handoff_resolved(resolution)
        return RuntimeCommandAdmissionResult(
            command_name="resolve_ui_handoff",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
        )

    def activate_persisted(self) -> RuntimeActivationResult:
        return RuntimeActivationResult(RuntimeActivationStatus.ALREADY_READY)

    def active_local_runtime_blocks_model_deletion(self) -> bool:
        return False

    def close(self) -> bool:
        return bool(self.controller.close())


class _ImportEegToolWorker(AgentWorker):
    """Return one strict target action at the external model boundary."""

    def generate_from_messages(self, request: AssistantGenerationRequest) -> None:
        generation_id = request.generation_id
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=generation_id,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=generation_id,
                phase=AssistantGenerationDispatchPhase.STARTED,
            )
        )
        self.generation_chunk_received.emit(
            generation_id,
            '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}',
        )
        self.generation_finished.emit(generation_id, [])


class _EmptyRagRetriever:
    """Return no examples while retaining the real RAG lifecycle boundary."""

    def initialize(self) -> None:
        return

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del query, allowed_tool_names
        return ""

    def close(self) -> None:
        return


def _click(qtbot, button) -> None:
    qtbot.waitUntil(button.isEnabled, timeout=10000)
    qtbot.mouseClick(
        button,
        Qt.MouseButton.LeftButton,
        pos=button.rect().center(),
    )
    qtbot.wait(50)


def _wait_for_panel_idle(qtbot, panel, *, timeout: int = 10000) -> None:
    """Wait for an async UI command to release its observable busy state."""
    qtbot.waitUntil(panel.isEnabled, timeout=timeout)


def _application_state(study):
    return _query_diagnostics(study, "state")["state"]


def _wait_for_raw_count(qtbot, study, expected: int) -> None:
    qtbot.waitUntil(
        lambda: _application_state(study)["raw"]["count"] == expected,
        timeout=10000,
    )


def _wait_for_dataset_count(qtbot, study, expected: int) -> None:
    qtbot.waitUntil(
        lambda: _application_state(study)["dataset"]["count"] == expected,
        timeout=10000,
    )


def _wait_for_workflow_panel(qtbot, window, index: int, attr_name: str):
    """Wait for user-click navigation to finish lazy panel materialization."""

    qtbot.waitUntil(
        lambda: index in window._loaded_panel_indices
        and window.stack.currentIndex() == index
        and window.stack.currentWidget() is getattr(window, attr_name),
        timeout=10000,
    )
    return getattr(window, attr_name)


def _query_diagnostics(study, query: str):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query),
    )
    assert result.ok, result.message
    return result.diagnostics


def _write_synthetic_raw_fif(tmp_path):
    sfreq = 128
    ch_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    event_samples = sfreq + np.arange(12) * int(1.5 * sfreq)
    data = np.random.default_rng(7).normal(
        size=(len(ch_names), int(event_samples[-1] + 2 * sfreq)),
    )
    raw = mne.io.RawArray(data, info)
    events = np.column_stack(
        (
            event_samples,
            np.zeros(len(event_samples), dtype=int),
            np.tile([1, 2], len(event_samples) // 2),
        ),
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )
    path = tmp_path / "product_walkthrough_raw.fif"
    raw.save(path, overwrite=True)
    return path


def _assert_assistant_status_matches_publication(
    manager,
    *,
    command_name: str,
    surface: AssistantWorkflowSurface,
    decision_fields: tuple[str, ...],
) -> None:
    service = get_application_service(manager.study)
    publication = service.get_view_publication()
    backend_projection = build_workflow_projection(
        publication.state,
        publication.effective_capabilities,
    )

    manager.refresh_backend_status()
    ui_projection = manager.assistant_status_projection

    assert ui_projection is not None
    assert ui_projection.publication_generation == publication.generation
    assert ui_projection.recommended_command == command_name
    assert ui_projection.recommended_command == backend_projection.recommended_command
    assert ui_projection.blocked_command == backend_projection.blocked_command
    assert ui_projection.blocked_reasons == backend_projection.blocked_reasons
    assert ui_projection.decision_fields == decision_fields
    assert ui_projection.decision_fields == backend_projection.decision_fields
    assert ui_projection.existing_ui_surface is surface
    assert manager.chat_panel.empty_state_title.text() == "Get started with XBrainLab"
    assert [
        button.property("assistantPrompt")
        for button in manager.chat_panel.suggestion_prompt_buttons
    ] == [
        "What should I do next?",
        "Explain my current workflow",
        "What can you help me with?",
    ]
    tooltip = manager.chat_panel.empty_state_widget.toolTip()
    assert surface.value in tooltip
    for reason in backend_projection.blocked_reasons:
        assert reason in tooltip
    if not backend_projection.blocked_reasons:
        assert "Action required:" not in tooltip


def test_assistant_product_click_through_layout(test_app, qtbot):
    """Open assistant, verify product language, bubbles, composer, and nav."""
    test_app.init_agent()
    manager = test_app.agent_manager
    with (
        patch.object(
            manager.assistant_runtime,
            "load_config",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            manager.assistant_runtime,
            "needs_first_run",
            return_value=False,
        ),
        patch.object(
            manager.assistant_runtime,
            "activate",
            return_value=RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Model cache not found.",
            ),
        ),
    ):
        _click(qtbot, test_app.ai_btn)

    panel = manager.chat_panel
    assert panel is not None
    assert manager.chat_dock.isVisible()
    dock_title_text = " ".join(
        label.text()
        for label in manager.chat_dock.titleBarWidget().findChildren(QLabel)
        if label.text()
    )
    assert "XBrainLab Assistant" in dock_title_text
    assert panel.empty_state_title.text() == "Get started with XBrainLab"
    assert [button.text() for button in panel.suggestion_prompt_buttons] == [
        "What should I do next?",
        "Explain my current workflow",
        "What can you help me with?",
    ]
    assert panel.runtime_state_widget.isVisible()
    assert panel.runtime_state_title.text() == "Assistant setup required"
    assert "Model cache not found" not in panel.runtime_state_detail.text()
    assert "Backend" not in panel.runtime_state_detail.text()
    assert panel.input_field.placeholderText() == "Set up assistant"
    assert panel.input_field.isEnabled() is False
    assert panel.send_btn.isEnabled() is False

    visible_first_layer = " ".join(
        child.text()
        for child in panel.findChildren(QWidget)
        if isinstance(child, (QLabel, QAbstractButton))
        and child.isVisible()
        and child.text()
    )
    for forbidden in [
        "General Assistant",
        "AI Assistant",
        "Conversation",
        "Assistant mode",
        "Step behavior",
        "Single step",
        "Step by step",
        "Continue safely",
        "Local model ready",
        "Backend:",
        "Commands:",
        "load_data",
        "pipeline_stage",
    ]:
        assert forbidden not in visible_first_layer

    assert dock_title_text.count("XBrainLab") == 1

    assert manager.new_conv_title_btn.text() == "+"
    assert manager.new_conv_title_btn.icon().isNull()
    assert not hasattr(manager, "float_btn")
    assert manager.settings_btn.text() == ""
    assert not manager.settings_btn.icon().isNull()
    assert manager.settings_btn.accessibleName() == "Assistant settings"
    assert not hasattr(manager, "retry_title_btn")
    assert not hasattr(manager, "settings_menu")
    assert not hasattr(manager, "clear_title_btn")
    assert manager.new_conv_title_btn.geometry().right() <= (
        manager.settings_btn.geometry().left()
    )
    assert (
        manager.settings_btn.geometry().right() <= manager.close_btn.geometry().left()
    )

    visible_title_text = " ".join(
        child.text()
        for child in manager.chat_dock.titleBarWidget().findChildren(QAbstractButton)
        if child.isVisible() and child.text()
    )
    assert "Retry" not in visible_title_text
    assert "Clear" not in visible_title_text

    visible_transcript = "\n".join(
        message["content"] for message in manager.chat_controller.messages
    )
    for forbidden in [
        "Tool Output:",
        "Tool Call:",
        "Request:",
        "```json",
        "ApplicationService",
        "BackendFacade",
        "Model cache not found",
    ]:
        assert forbidden not in visible_transcript

    with (
        patch.object(
            manager.assistant_runtime,
            "activate_persisted",
            return_value=RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Model cache not found.",
            ),
        ),
    ):
        manager.handle_user_input("hello")
    assert not hasattr(manager, "retry_title_btn")
    assert not hasattr(manager, "settings_menu")

    assert panel.send_btn.toolButtonStyle() is (Qt.ToolButtonStyle.ToolButtonTextOnly)
    assert panel.send_btn.icon().isNull() is True
    assert panel.send_btn.accessibleName() == "Send request"

    panel.append_message("user", "hello from a product user")
    user_bubble = panel._latest_layout_message_bubble()
    assert user_bubble is not None
    assert user_bubble.get_text().endswith("user")
    assert user_bubble.text_edit.toPlainText().endswith("user")
    assert (
        user_bubble.text_edit.document().textWidth() < user_bubble.bubble_frame.width()
    )

    submission = manager._assistant_turn_state.begin_submission()
    correlation = AssistantTurnCorrelation(
        generation=submission.generation,
        turn_id=1,
    )
    assert manager._assistant_turn_state.accept_admission(
        submission,
        correlation,
    )
    manager._handle_response_presentation(
        AssistantResponsePresentation(
            correlation=correlation,
            text=(
                "The requested action needs a dataset location before it can continue."
            ),
        )
    )
    transcript_after_guidance = "\n".join(
        message["content"] for message in manager.chat_controller.messages
    )
    assert "needs a dataset location" in transcript_after_guidance

    manager._handle_response_presentation(
        AssistantResponsePresentation(
            correlation=correlation,
            text="Workflow state ready. Import EEG files to begin.",
        )
    )
    transcript_after_safe_tool = "\n".join(
        message["content"] for message in manager.chat_controller.messages
    )
    assert "Workflow state ready" in transcript_after_safe_tool
    assert "Tool Output:" not in transcript_after_safe_tool

    for index, attr in [
        (0, "dataset_panel"),
        (1, "preprocess_panel"),
        (2, "training_panel"),
        (3, "evaluation_panel"),
        (4, "visualization_panel"),
    ]:
        _click(qtbot, test_app.nav_btns[index])
        assert test_app.stack.currentIndex() == index
        assert getattr(test_app, attr).isVisible()


def test_assistant_dock_restores_product_width_across_states_and_reopens(
    test_app,
    qtbot,
) -> None:
    """The standard desktop Assistant stays 420 px through its UI lifecycle."""
    qtbot.wait(300)
    test_app.resize(1280, 800)
    qtbot.wait(50)
    test_app.init_agent()
    manager = test_app.agent_manager
    dock = manager.chat_dock
    panel = manager.chat_panel

    assert dock.isHidden()
    with (
        patch.object(
            manager.assistant_runtime,
            "load_config",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            manager.assistant_runtime,
            "needs_first_run",
            return_value=False,
        ),
        patch.object(
            manager.assistant_runtime,
            "activate",
            return_value=RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Model cache not found.",
            ),
        ),
    ):
        _click(qtbot, test_app.ai_btn)
        assert dock.isVisible()
        assert dock.width() == 420
        assert panel.width() == 420

        for phase, message in (
            ("idle", "Choose a local model."),
            ("loading", "Loading assistant."),
            ("ready", ""),
            ("failed", "The selected local model could not start."),
        ):
            panel.set_runtime_state(phase, message)
            qtbot.wait(10)
            assert dock.width() == 420, phase
            assert panel.width() == 420, phase

        panel.set_runtime_state("ready")
        panel.set_processing_state(True)
        qtbot.wait(10)
        assert dock.width() == 420
        assert panel.width() == 420
        panel.set_processing_state(False)

        test_app.resizeDocks([dock], [320], Qt.Orientation.Horizontal)
        qtbot.waitUntil(lambda: dock.width() == 420, timeout=2_000)
        assert panel.width() == 420
        assert panel.minimumWidth() == 320

        for _cycle in range(2):
            _click(qtbot, test_app.ai_btn)
            assert dock.isHidden()
            _click(qtbot, test_app.ai_btn)
            assert dock.isVisible()
            assert dock.width() == 420
            assert panel.width() == 420


def test_assistant_dock_width_stays_within_responsive_product_bounds(
    test_app,
    qtbot,
) -> None:
    """Narrow windows preserve workflow space without losing the 320 px floor."""
    qtbot.wait(300)
    test_app.resize(1280, 800)
    test_app.init_agent()
    manager = test_app.agent_manager
    dock = manager.chat_dock
    panel = manager.chat_panel
    dock.show()
    qtbot.waitUntil(dock.isVisible, timeout=2_000)

    observed_widths = []
    for window_width in (760, 820, 860, 1280):
        test_app.resize(window_width, 800)
        qtbot.wait(50)
        observed_widths.append(dock.width())
        assert 320 <= dock.width() <= 420
        assert panel.width() == dock.width()
        assert test_app.centralWidget().width() >= 436

    assert observed_widths[0] == 320
    assert observed_widths[-1] == 420
    assert observed_widths == sorted(observed_widths)


def test_assistant_dock_preserves_workflow_width_with_wide_platform_title(
    test_app,
    qtbot,
) -> None:
    """Platform title metrics cannot consume the workflow's usable width."""
    test_app.resize(760, 800)
    test_app.init_agent()
    manager = test_app.agent_manager
    dock = manager.chat_dock
    title = dock.findChild(QLabel, "AssistantDockTitle")
    assert title is not None

    title.setMinimumWidth(title.minimumWidth() + 48)
    dock.show()
    test_app.resize(760, 800)
    qtbot.waitUntil(dock.isVisible, timeout=2_000)
    qtbot.wait(50)

    assert manager.assistant_header.minimumSizeHint().width() <= 320
    assert 320 <= dock.width() <= 420
    assert manager.chat_panel.width() == dock.width()
    assert test_app.centralWidget().width() >= 436
    assert title.fontMetrics().horizontalAdvance(title.text()) <= (
        title.contentsRect().width() + 1
    )


def test_assistant_first_open_uses_inline_setup_without_activation(test_app, qtbot):
    test_app.init_agent()
    manager = test_app.agent_manager
    config = SimpleNamespace(model_name=PRIMARY_LOCAL_MODEL_ID)
    with (
        patch.object(
            manager.assistant_runtime,
            "load_config",
            return_value=config,
        ),
        patch.object(
            manager.assistant_runtime,
            "needs_first_run",
            return_value=True,
        ),
        patch.object(
            manager.assistant_runtime,
            "preview_launch",
            return_value=SimpleNamespace(failure=None),
        ),
        patch.object(manager.assistant_runtime, "activate") as activate,
    ):
        _click(qtbot, test_app.ai_btn)

    assert manager.chat_dock.isVisible() is True
    assert manager.chat_panel.runtime_state_title.text() == (
        "Start XBrainLab Assistant"
    )
    assert manager.chat_panel.runtime_state_detail.text() == (
        "Granite 4.0 Micro 3B (Recommended)\nEstimated 8 GB VRAM"
    )
    assert manager.chat_panel.retry_runtime_btn.text() == "Enable Assistant"
    assert manager.chat_panel.setup_btn.text() == "Assistant Settings"
    activate.assert_not_called()


def test_assistant_status_uses_real_interpretation_confirmation_publication(
    test_app,
    qtbot,
    tmp_path,
):
    test_app.init_agent()
    manager = test_app.agent_manager
    fif_path = _write_synthetic_raw_fif(tmp_path)
    service = get_application_service(test_app.study)

    assert service.execute(ScanSourceCommand(source_path=str(fif_path))).ok
    assert service.execute(PreviewInterpretationCommand()).ok
    validation = service.execute(ValidateInterpretationCommand())

    assert validation.ok
    assert validation.state.interpretation.pending_confirmation is True
    _assert_assistant_status_matches_publication(
        manager,
        command_name="apply_interpretation",
        surface=AssistantWorkflowSurface.DATA_IMPORT,
        decision_fields=("metadata_review", "label_matching"),
    )


def test_model_import_action_opens_typed_product_surface_directly(
    test_app,
    qtbot,
    monkeypatch,
) -> None:
    """Route one strict model action through the typed product handoff."""
    with patch("XBrainLab.llm.agent.controller.AgentWorker", _ImportEegToolWorker):
        controller = LLMController(
            test_app.study,
            rag_lifecycle=RAGRetrieverLifecycle(_EmptyRagRetriever()),
        )
    runtime = _ReadyAssistantIntegrationRuntime(controller)
    manager = AgentManager(
        test_app,
        test_app.study,
        runtime_lifecycle=runtime,
    )
    test_app.agent_manager = manager
    handoff_requests: list[WorkflowUiHandoffRequest] = []
    chooser_calls: list[tuple[object, str]] = []

    class _CancelledSourceChooser:
        def __init__(self, parent, *, start_directory=""):
            chooser_calls.append((parent, start_directory))

        def exec(self):
            return False

        def get_result(self):
            return None

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.actions.EegSourceChooserDialog",
        _CancelledSourceChooser,
    )

    try:
        manager.init_ui()
        assert manager.start_system() is None
        controller.workflow_ui_handoff_requested.connect(handoff_requests.append)
        manager.chat_dock.show()
        qtbot.waitUntil(manager.chat_dock.isVisible, timeout=2_000)

        panel = manager.chat_panel
        panel.input_field.setText("幫我處理資料")
        qtbot.waitUntil(panel.send_btn.isEnabled, timeout=2_000)
        _click(qtbot, panel.send_btn)
        qtbot.waitUntil(lambda: bool(chooser_calls), timeout=2_000)
        assert runtime.submissions == ["幫我處理資料"]
        assert runtime.delivery_phases == [AssistantTurnDeliveryPhase.ACCEPTED]
        assert len(handoff_requests) == 1
        assert handoff_requests[0].command is CommandName.SCAN_SOURCE
        assert not hasattr(panel, "response_actions_widget")
        assert chooser_calls
        chooser_parent, chooser_directory = chooser_calls[0]
        assert chooser_parent is test_app.dataset_panel
        assert chooser_directory == _dataset_dialog_start_directory()
        assert test_app.stack.currentWidget() is test_app.dataset_panel
        assert controller.pending_interactions.workflow_handoff is None
        assert all(
            message["content"] != "Help me import EEG data"
            for message in manager.chat_controller.messages
        )
    finally:
        close_controller_and_wait(controller, qtbot)


def test_backend_observer_refresh_keeps_fixed_assistant_homepage(
    test_app,
    qtbot,
    tmp_path,
) -> None:
    """Backend publication refreshes status without rebuilding onboarding."""
    test_app.init_agent()
    manager = test_app.agent_manager
    panel = manager.chat_panel
    service = get_application_service(test_app.study)
    fif_path = _write_synthetic_raw_fif(tmp_path)

    initial_projection = manager.assistant_status_projection
    assert initial_projection is not None
    initial_generation = initial_projection.publication_generation
    assert initial_projection.stage == "No data loaded"
    homepage_copy = (
        panel.empty_state_title.text(),
        panel.empty_state_intro.text(),
        tuple(
            (button.text(), button.subtitle(), button.property("assistantPrompt"))
            for button in panel.suggestion_prompt_buttons
        ),
    )
    assert homepage_copy[0] == "Get started with XBrainLab"
    terminal_publications = []
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        terminal_publications.append,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        load_future = executor.submit(
            service.execute,
            LoadDataCommand(paths=[str(fif_path)]),
        )
        qtbot.waitUntil(load_future.done, timeout=10_000)
        load_result = load_future.result()

    assert load_result.ok, load_result.message
    assert service.bids_montage_preparation.wait_for_idle(timeout=10.0)
    publication = service.get_view_publication()
    assert publication.generation > initial_generation
    assert terminal_publications
    assert terminal_publications[-1] == publication, [
        (
            item.generation,
            item.revision,
            item.usable,
            item.state.pipeline_stage,
            item.refresh_error,
        )
        for item in terminal_publications
    ]
    publication_generations = [item.generation for item in terminal_publications]
    assert publication_generations == sorted(set(publication_generations))
    expected_projection = build_assistant_status_projection(publication)
    assert expected_projection.stage == (
        "EEG data loaded · Ready for preprocessing or epoching"
    )
    qtbot.waitUntil(
        lambda: (
            manager.assistant_status_projection is not None
            and manager.assistant_status_projection.publication_generation
            == publication.generation
        ),
        timeout=5_000,
    )

    refreshed_projection = manager.assistant_status_projection
    assert refreshed_projection is not None
    assert refreshed_projection.publication_generation == publication.generation
    assert refreshed_projection == expected_projection
    assert refreshed_projection.recommended_command is None
    assert (
        panel.empty_state_title.text(),
        panel.empty_state_intro.text(),
        tuple(
            (button.text(), button.subtitle(), button.property("assistantPrompt"))
            for button in panel.suggestion_prompt_buttons
        ),
    ) == homepage_copy


def test_import_command_success_refreshes_dataset_table_without_stale_controller(
    test_app,
    qtbot,
    tmp_path,
):
    """A backend import command success must refresh UI from command/query truth."""
    from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
        EegSourceSelection,
    )

    fif_path = _write_synthetic_raw_fif(tmp_path)
    test_app.switch_page(0)

    with (
        patch.object(
            test_app.dataset_panel,
            "_compatibility_loaded_data_list_for_render",
            side_effect=AssertionError("stale loaded-data render fallback was read"),
        ) as stale_render,
        patch.object(
            test_app.dataset_panel.sidebar,
            "_compatibility_sidebar_state",
            side_effect=AssertionError("stale sidebar controller state was read"),
        ) as stale_sidebar,
        patch(
            "XBrainLab.ui.panels.dataset.actions.EegSourceChooserDialog",
        ) as SourceChooser,
        patch(
            "XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog",
        ) as PreviewDialog,
    ):
        SourceChooser.return_value.exec.return_value = True
        SourceChooser.return_value.get_result.return_value = EegSourceSelection(
            kind="files",
            paths=(str(fif_path),),
        )
        PreviewDialog.return_value.exec.return_value = True
        PreviewDialog.return_value.get_result.return_value = {
            "confirmed": True,
            "choices": {"label_carrier": "embedded_events"},
        }
        _click(qtbot, test_app.dataset_panel.sidebar.import_btn)
        _wait_for_raw_count(qtbot, test_app.study, 1)

    qtbot.waitUntil(lambda: test_app.dataset_panel.table.rowCount() == 1, timeout=5000)
    loaded_rows = _query_diagnostics(test_app.study, "data_lists")["raw_rows"]
    assert test_app.dataset_panel.table.rowCount() == 1
    name_item = test_app.dataset_panel.table.item(0, 0)
    assert name_item.data(Qt.ItemDataRole.UserRole) is None
    row_identity = name_item.data(test_app.dataset_panel._ROW_IDENTITY_ROLE)
    assert row_identity.canonical_filepath.endswith(loaded_rows[0]["filename"])
    stale_render.assert_not_called()
    stale_sidebar.assert_not_called()


def test_pipeline_product_walkthrough_uses_user_facing_actions(
    test_app, qtbot, tmp_path, monkeypatch
):
    """Drive import -> preprocess -> epoch -> split -> configure -> dry-run train UI."""
    from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (
        EegSourceSelection,
    )

    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    blocking_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, text, *_args, **_kwargs: blocking_messages.append(
            (str(title), str(text)),
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, text, *_args, **_kwargs: blocking_messages.append(
            (str(title), str(text)),
        ),
    )
    fif_path = _write_synthetic_raw_fif(tmp_path)
    training_option_holder = {}
    fake_train_calls = []

    def fake_start_train_after_preflight(
        _training_commands,
        command,
        *,
        preflight,
        receipt_reused,
        defer_synchronous_completion=False,
    ):
        """Populate finished-run state through the command route without real training."""
        assert isinstance(command, TrainCommand)
        assert command.confirmed is True
        assert preflight.ok is True
        assert receipt_reused is False
        assert defer_synchronous_completion is False
        assert service.get_state().dataset.split_materialized is True
        fake_train_calls.append(command)
        eval_record = EvalRecord(
            label=np.array([0, 1, 0, 1]),
            output=np.array(
                [
                    [4.0, -4.0],
                    [-4.0, 4.0],
                    [4.0, -4.0],
                    [-4.0, 4.0],
                ]
            ),
            evaluation_split="test",
            gradient={},
            gradient_input={},
            smoothgrad={},
            smoothgrad_sq={},
            vargrad={},
        )
        model_holder = ModelHolder(EEGNet, {}, None)
        option = training_option_holder["option"]
        admitted_datasets = (
            _training_commands.training_runtime.resource_context().datasets
        )
        assert len(admitted_datasets) == 1
        completed_plan = TrainingPlanHolder(
            model_holder,
            admitted_datasets[0],
            option,
            None,
        )
        record = completed_plan.train_record_list[0]
        record.update_train(
            {
                TrainRecordKey.LOSS: 0.25,
                TrainRecordKey.ACC: 100.0,
                TrainRecordKey.AUC: None,
            }
        )
        record.update_statistic(
            {
                TrainRecordKey.LR: 0.001,
                TrainRecordKey.TIME: 0.1,
            }
        )
        record.update_validation(
            {
                RecordKey.LOSS: 0.2,
                RecordKey.ACC: 100.0,
                RecordKey.AUC: None,
            }
        )
        record.step()
        record.set_eval_record(eval_record)
        completed_plan.status = "Finished"
        test_app.study.trainer = Trainer([completed_plan])
        return (
            "Training started.",
            {
                "append": command.append,
                "interactive": command.interactive,
                "fake_training": True,
            },
        )

    monkeypatch.setattr(
        application_service_module._LazyTrainingCommandService,
        "start_train_after_preflight",
        fake_start_train_after_preflight,
    )
    test_app.study._application_service = None
    service = get_application_service(test_app.study)
    test_app.init_agent()
    manager = test_app.agent_manager
    assert service._command_handlers[CommandName.TRAIN] == (
        service._handle_train_with_saved_split
    )

    test_app.switch_page(0)

    with (
        patch(
            "XBrainLab.ui.panels.dataset.actions.EegSourceChooserDialog",
        ) as SourceChooser,
        patch(
            "XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog",
        ) as PreviewDialog,
    ):
        SourceChooser.return_value.exec.return_value = True
        SourceChooser.return_value.get_result.return_value = EegSourceSelection(
            kind="files",
            paths=(str(fif_path),),
        )
        PreviewDialog.return_value.exec.return_value = True
        PreviewDialog.return_value.get_result.return_value = {
            "confirmed": True,
            "choices": {"label_carrier": "embedded_events"},
        }
        assert test_app.dataset_panel.sidebar.import_btn.text() == "Import Data"
        _click(qtbot, test_app.dataset_panel.sidebar.import_btn)
        _wait_for_raw_count(qtbot, test_app.study, 1)

    qtbot.waitUntil(lambda: test_app.dataset_panel.table.rowCount() == 1, timeout=5000)
    assert test_app.dataset_panel.table.rowCount() == 1

    _click(qtbot, test_app.nav_btns[1])
    _wait_for_workflow_panel(qtbot, test_app, 1, "preprocess_panel")
    qtbot.waitUntil(
        lambda: test_app.preprocess_panel.preview_widget.chan_combo.count() == 4
        and test_app.preprocess_panel.preview_widget.time_current_curve.xData
        is not None
        and len(test_app.preprocess_panel.preview_widget.time_current_curve.xData) > 0,
        timeout=5000,
    )
    assert (
        test_app.preprocess_panel.preview_widget.preview_stack.currentWidget()
        is test_app.preprocess_panel.preview_widget.plot_content
    )

    class FakeFilteringDialog:
        def __init__(self, _parent, *, sampling_rate_hz=None):
            assert sampling_rate_hz == pytest.approx(128.0)

        def exec(self):
            return True

        def get_params(self):
            return (1.0, 40.0, None)

    class FakeEpochingDialog:
        def __init__(self, _parent, *, epoch_context, **_dialog_context):
            available_events = {
                str(row.get("name"))
                for row in epoch_context.get("available_events", [])
            }
            assert {"left", "right"} <= available_events

        def exec(self):
            return True

        def get_params(self):
            return (None, ["left", "right"], 0.0, 1.3)

        def get_confirmation_receipt(self):
            return None

    with patch(
        "XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog",
        FakeFilteringDialog,
    ):
        _click(qtbot, test_app.preprocess_panel.sidebar.btn_filter)
    _wait_for_panel_idle(qtbot, test_app.preprocess_panel)
    assert _application_state(test_app.study)["preprocessed"]["count"] == 1
    _assert_assistant_status_matches_publication(
        manager,
        command_name="create_epoch",
        surface=AssistantWorkflowSurface.EPOCH_SETTINGS,
        decision_fields=("target_event", "epoch_window"),
    )
    qtbot.waitUntil(
        lambda: test_app.preprocess_panel.sidebar.btn_epoch.isEnabled(),
        timeout=5000,
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog",
        FakeEpochingDialog,
    ):
        _click(qtbot, test_app.preprocess_panel.sidebar.btn_epoch)
    qtbot.waitUntil(
        lambda: bool(_application_state(test_app.study)["epoch"]["exists"])
        or bool(blocking_messages),
        timeout=5000,
    )
    assert not blocking_messages, blocking_messages
    epoch_state = _application_state(test_app.study)["epoch"]
    assert epoch_state["exists"] is True
    assert epoch_state["epoch_count"] == 12
    assert epoch_state["n_channels"] == 4
    assert epoch_state["n_times"] == 167
    assert epoch_state["event_ids"] == {"left": 0, "right": 1}
    _assert_assistant_status_matches_publication(
        manager,
        command_name="configure_dataset_split",
        surface=AssistantWorkflowSurface.DATASET_SPLIT,
        decision_fields=("split_strategy", "training_mode"),
    )

    _click(qtbot, test_app.nav_btns[2])
    _wait_for_workflow_panel(qtbot, test_app, 2, "training_panel")

    split_config = DataSplittingConfig(
        train_type=TrainingType.IND,
        is_cross_validation=False,
        val_splitter_list=[
            DataSplitter(
                split_type=ValSplitByType.TRIAL,
                value_var="0.25",
                split_unit=SplitUnit.RATIO,
            )
        ],
        test_splitter_list=[
            DataSplitter(
                split_type=SplitByType.TRIAL,
                value_var="0.25",
                split_unit=SplitUnit.RATIO,
            )
        ],
    )
    split_service = get_application_service(test_app.study)
    split_context = split_service.get_dataset_split_context(
        DatasetSplitContextRequest(
            publication_generation=split_service.get_view_publication().generation,
        ),
    )
    assert split_context.context.epoch_available is True
    split_payload = {
        "train_type": split_config.train_type.value,
        "is_cross_validation": split_config.is_cross_validation,
        "val_splitters": [
            {
                "split_type": ValSplitByType.TRIAL.value,
                "split_unit": SplitUnit.RATIO.value,
                "value": "0.25",
                "is_option": True,
            },
        ],
        "test_splitters": [
            {
                "split_type": SplitByType.TRIAL.value,
                "split_unit": SplitUnit.RATIO.value,
                "value": "0.25",
                "is_option": True,
            },
        ],
    }
    split_preview_receipts: list[DatasetSplitPreviewReceipt] = []

    class FakeSplitDialog:
        def __init__(
            self,
            _parent,
            *,
            split_context,
            publication_generation,
            preview_provider,
            **_dialog_context,
        ):
            assert split_context.epoch_available is True
            assert split_context.trial_count == 12
            preview = preview_provider(
                DatasetSplitPreviewRequest(
                    request_id="product-walkthrough-split-preview",
                    publication_generation=publication_generation,
                    specification=DatasetSplitSpecification.from_payload(split_payload),
                )
            )
            self.preview_receipt = preview.receipt
            assert isinstance(self.preview_receipt, DatasetSplitPreviewReceipt)
            split_preview_receipts.append(self.preview_receipt)

        def exec(self):
            return True

        def get_result(self):
            return split_payload

        def get_preview_receipt(self):
            return self.preview_receipt

    class FakeModelDialog:
        def __init__(self, _parent, _controller, **_dialog_context):
            pass

        def exec(self):
            return True

        def get_result(self):
            return ModelHolder(EEGNet, {}, None)

    class FakeTrainingSettingDialog:
        def __init__(self, _parent, _controller, **_dialog_context):
            pass

        def exec(self):
            return True

        def get_result(self):
            option = TrainingOption(
                output_dir=str(tmp_path / "training-output"),
                optim=torch.optim.Adam,
                optim_params={},
                use_cpu=True,
                gpu_idx=None,
                epoch=1,
                bs=2,
                lr=0.001,
                checkpoint_epoch=0,
                evaluation_option=TrainingEvaluation.VAL_ACC,
                repeat_num=1,
            )
            training_option_holder["option"] = option
            return option

    with patch(
        "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog", FakeSplitDialog
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_split)
    qtbot.waitUntil(
        lambda: _application_state(test_app.study)["dataset"]["split_spec_saved"]
        or bool(blocking_messages),
        timeout=5000,
    )
    assert not blocking_messages, blocking_messages
    assert len(split_preview_receipts) == 1
    preview_receipt = split_preview_receipts[0]
    dataset_state = _application_state(test_app.study)["dataset"]
    assert dataset_state["count"] == 0
    assert dataset_state["generator_exists"] is False
    assert dataset_state["split_spec_saved"] is True
    assert dataset_state["split_materialized"] is False
    assert dataset_state["split_preview_summary"] == preview_receipt.summary_payload()
    assert dataset_state["active_split_summary"] == {}
    _assert_assistant_status_matches_publication(
        manager,
        command_name="configure_training",
        surface=AssistantWorkflowSurface.TRAINING_SETTINGS,
        decision_fields=("model", "training_options"),
    )

    with patch(
        "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog", FakeModelDialog
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_model)
    training_state = _application_state(test_app.study)["training"]
    assert training_state["has_model"] is True
    assert training_state["model_name"] == "EEGNet (XBrainLab)"

    with patch(
        "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog",
        FakeTrainingSettingDialog,
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_setting)
    training_state = _application_state(test_app.study)["training"]
    assert training_state["has_training_option"] is True
    assert training_state["training_option"]["epoch"] == 1
    assert training_state["training_option"]["batch_size"] == 2
    assert test_app.training_panel.sidebar.btn_start.isEnabled()

    with patch.object(
        QMessageBox,
        "question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_start)
        qtbot.waitUntil(lambda: len(fake_train_calls) == 1, timeout=5000)

    assert len(fake_train_calls) == 1
    _wait_for_dataset_count(qtbot, test_app.study, 1)
    dataset_state = _application_state(test_app.study)["dataset"]
    assert dataset_state["count"] == EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY["count"]
    assert dataset_state["split_materialized"] is True
    assert (
        dataset_state["active_split_summary"]
        == EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY
    )
    qtbot.waitUntil(
        lambda: _application_state(test_app.study)["training"]["finished_run_count"]
        == 1,
        timeout=5000,
    )
    training_state = _application_state(test_app.study)["training"]
    assert training_state["has_trainer"] is True
    assert training_state["plan_count"] == 1
    assert training_state["finished_run_count"] == 1

    _click(qtbot, test_app.nav_btns[3])
    _wait_for_workflow_panel(qtbot, test_app, 3, "evaluation_panel")
    assert test_app.evaluation_panel.model_combo.currentText().startswith("Fold 1")
    assert "Finished" in test_app.evaluation_panel.run_combo.currentText()
    qtbot.waitUntil(
        lambda: test_app.evaluation_panel._evaluation_render is not None,
        timeout=10_000,
    )
    qtbot.waitUntil(
        lambda: test_app.evaluation_panel._evaluation_render_worker is None,
        timeout=10_000,
    )
    producer_identities = test_app.evaluation_panel.metrics_table.property(
        "producerIdentities"
    )
    assert isinstance(producer_identities, list)
    assert len(producer_identities) == 1
    assert producer_identities[0]["dataset_fingerprint"]
    assert producer_identities[0]["split_fingerprint"]
    assert producer_identities[0]["run_fingerprint"]
    assert producer_identities[0]["model_fingerprint"]
