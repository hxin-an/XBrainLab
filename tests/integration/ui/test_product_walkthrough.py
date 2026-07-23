"""Product-level UI walkthroughs for XBrainLab desktop workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mne
import numpy as np
import pytest
import torch
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractButton, QLabel, QMessageBox, QWidget

import XBrainLab.backend.application.service as application_service_module
from scripts.dev.capture_human_like_product_walkthrough import REQUIRED_PHASES
from XBrainLab.backend.application import (
    CommandName,
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
from XBrainLab.backend.training.record import RecordKey, TrainRecordKey
from XBrainLab.llm.agent.response_presentation import AssistantResponsePresentation
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeSetupAction,
    RuntimeSetupOutcome,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantWorkflowSurface,
)
from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
    LocalRuntimeFirstRunDialog,
)

EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY = {
    "count": 1,
    "train_count": 7,
    "val_count": 2,
    "test_count": 3,
    "audit": {"ok": True, "dataset_count": 1, "issues": []},
}


def test_human_like_capture_script_is_a_real_exit_code_gate(tmp_path) -> None:
    """Execute the product capture itself so helper-only tests cannot mask failure."""
    root = Path(__file__).resolve().parents[3]
    output_dir = tmp_path / "human-like-walkthrough-runs" / "current"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(  # noqa: S603 - fixed repository script path
        [
            sys.executable,
            "scripts/dev/capture_human_like_product_walkthrough.py",
            "--output-dir",
            str(output_dir),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    reports = sorted(output_dir.parent.glob("*/human-like-walkthrough.md"))
    report_text = reports[-1].read_text(encoding="utf-8") if reports else ""

    assert completed.returncode == 0, (
        "Human-like walkthrough process failed.\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}\n"
        f"report:\n{report_text}"
    )
    payload = json.loads(
        (output_dir / "human-like-walkthrough.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "passed"
    expected_phase_count = len(REQUIRED_PHASES)
    assert payload["pass_fail_summary"]["observed_phase_count"] == expected_phase_count
    assert payload["pass_fail_summary"]["required_phase_count"] == expected_phase_count
    assert payload["artifact_run"]["source_fingerprint"]
    assert isinstance(payload["artifact_run"]["working_tree_dirty"], bool)


def _click(qtbot, button) -> None:
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
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


def _query_diagnostics(study, query: str, *, include_objects: bool = False):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query, include_objects=include_objects),
    )
    assert result.ok, result.message
    return result.local_payload


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
    assert (
        manager.chat_panel.empty_state_action_button.text() == "Suggest the next step"
    )
    assert (
        manager.chat_panel.empty_state_action_button.property("assistantPrompt")
        == ui_projection.recommended_label
    )
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
    assert panel.empty_state_title.text() == "How can I help with your EEG workflow?"
    assert panel.empty_state_action_button.text() == "Suggest the next step"
    assert panel.empty_state_action_button.property("assistantPrompt") == (
        "Scan data source"
    )
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

    assert manager.retry_title_btn.text() == ""
    assert not manager.retry_title_btn.icon().isNull()
    assert manager.settings_btn.text() == "⋮"
    assert manager.settings_btn.icon().isNull()
    assert manager.settings_btn.accessibleName() == "Assistant options"
    assert not hasattr(manager, "float_btn")
    assert manager.retry_title_btn.isEnabled() is False
    assert not hasattr(manager, "clear_title_btn")
    assert manager.retry_title_btn.geometry().right() <= (
        manager.new_conv_title_btn.geometry().left()
    )
    menu_text = [
        action.text() for action in manager.settings_menu.actions() if action.text()
    ]
    assert menu_text == ["Assistant settings", "Float assistant", "New chat"]
    assert manager.clear_conversation_title_action.isEnabled() is False

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
    assert manager.retry_title_btn.isEnabled() is False
    assert manager.clear_conversation_title_action.isEnabled() is False

    assert panel.send_btn.toolButtonStyle() is (Qt.ToolButtonStyle.ToolButtonIconOnly)
    assert panel.send_btn.icon().isNull() is False
    assert panel.send_btn.accessibleName() == "Send"

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


@pytest.mark.parametrize(
    ("choice", "outcome_message", "visible_message"),
    [
        (
            LocalRuntimeFirstRunDialog.LATER,
            "Assistant setup was deferred.",
            "Assistant setup was deferred. Open assistant settings when you are "
            "ready to continue.",
        ),
        (
            LocalRuntimeFirstRunDialog.DISABLE,
            "Assistant is disabled.",
            "Assistant is disabled. Open assistant settings to enable it.",
        ),
    ],
)
def test_assistant_first_open_preserves_local_runtime_confirmation(
    test_app,
    qtbot,
    choice,
    outcome_message,
    visible_message,
):
    """Opening the dock still reaches the local runtime first-run confirmation."""
    test_app.init_agent()
    manager = test_app.agent_manager
    status_messages: list[str] = []
    manager.status_message_received.connect(status_messages.append)
    with (
        patch.object(
            manager.assistant_runtime,
            "load_config",
            return_value=SimpleNamespace(),
        ),
        patch.object(
            manager.assistant_runtime,
            "needs_first_run",
            return_value=True,
        ),
        patch.object(
            manager,
            "_show_local_runtime_first_run_dialog",
            return_value=choice,
        ) as show_first_run,
        patch.object(
            manager.assistant_runtime,
            "apply_first_run_choice",
            return_value=RuntimeSetupOutcome(
                RuntimeSetupAction.STOP,
                outcome_message,
            ),
        ),
        patch.object(manager.assistant_runtime, "activate") as activate,
    ):
        _click(qtbot, test_app.ai_btn)

    assert manager.chat_dock.isVisible() is True
    assert test_app.ai_btn.isChecked() is True
    show_first_run.assert_called_once()
    activate.assert_not_called()
    assert status_messages[-1] == visible_message
    assert manager.chat_panel.runtime_state_title.text() == "Assistant setup required"
    assert manager.chat_panel.runtime_state_detail.text() == visible_message
    assert manager.chat_panel.setup_btn.isVisible()


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


def test_import_command_success_refreshes_dataset_table_without_stale_controller(
    test_app,
    qtbot,
    tmp_path,
):
    """A backend import command success must refresh UI from command/query truth."""
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
            "XBrainLab.ui.panels.dataset.actions.QFileDialog.getOpenFileNames",
            return_value=([str(fif_path)], ""),
        ),
        patch(
            "XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog",
        ) as PreviewDialog,
    ):
        PreviewDialog.return_value.exec.return_value = True
        PreviewDialog.return_value.get_result.return_value = {
            "confirmed": True,
            "choices": {"label_carrier": "embedded_events"},
        }
        _click(qtbot, test_app.dataset_panel.sidebar.import_btn)
        _wait_for_raw_count(qtbot, test_app.study, 1)

    qtbot.waitUntil(lambda: test_app.dataset_panel.table.rowCount() == 1, timeout=5000)
    loaded_objects = _query_diagnostics(
        test_app.study,
        "data_lists",
        include_objects=True,
    )["loaded_data_list"]
    assert test_app.dataset_panel.table.rowCount() == 1
    assert (
        test_app.dataset_panel.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        is loaded_objects[0]
    )
    stale_render.assert_not_called()
    stale_sidebar.assert_not_called()


def test_pipeline_product_walkthrough_uses_user_facing_actions(
    test_app, qtbot, tmp_path, monkeypatch
):
    """Drive import -> preprocess -> epoch -> split -> configure -> dry-run train UI."""
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    fif_path = _write_synthetic_raw_fif(tmp_path)
    training_option_holder = {}
    fake_train_calls = []

    def fake_handle_train(
        _training_commands,
        command,
        *,
        defer_synchronous_completion=False,
    ):
        """Populate finished-run state through the command route without real training."""
        assert isinstance(command, TrainCommand)
        assert command.confirmed is True
        assert defer_synchronous_completion is False
        fake_train_calls.append(command)
        eval_record = SimpleNamespace(
            label=np.array([0, 1, 0, 1]),
            output=np.array([0, 1, 0, 1]),
            gradient={},
            gradient_input={},
            smoothgrad={},
            smoothgrad_sq={},
            vargrad={},
            get_per_class_metrics=lambda: {
                0: {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 2},
                1: {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 2},
                "macro_avg": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1-score": 1.0,
                    "support": 4,
                },
            },
            get_acc=lambda: 1.0,
            get_auc=lambda: None,
            get_kappa=lambda: 1.0,
        )
        record = SimpleNamespace(
            epoch=1,
            repeat=0,
            train={
                TrainRecordKey.LOSS: [0.25],
                TrainRecordKey.ACC: [100.0],
                TrainRecordKey.AUC: [None],
                TrainRecordKey.LR: [0.001],
                TrainRecordKey.TIME: [0.1],
            },
            val={
                RecordKey.LOSS: [0.2],
                RecordKey.ACC: [100.0],
                RecordKey.AUC: [None],
            },
            eval_record=eval_record,
            is_finished=lambda: True,
            get_epoch=lambda: 1,
            get_eval_record=lambda: eval_record,
            get_confusion_figure=lambda show_percentage=False: Figure(figsize=(3, 2)),
        )
        model_holder = ModelHolder(EEGNet, {}, None)
        option = training_option_holder["option"]

        class _CompletedWalkthroughPlan(TrainingPlanHolder):
            def __init__(self):
                self.model_holder = model_holder
                self.option = option
                self.train_record_list = [record]
                self._state_tracker = None
                self._interrupt = False
                self.error = None
                self.status = "Finished"

            def bind_state_tracker(self, tracker) -> None:
                self._state_tracker = tracker

            def get_name(self) -> str:
                return "Product walkthrough dry-run"

            def get_plans(self):
                return list(self.train_record_list)

            def get_training_repeat(self) -> int:
                return 0

        test_app.study.trainer = Trainer([_CompletedWalkthroughPlan()])
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
        "handle_train",
        fake_handle_train,
    )
    test_app.study._application_service = None
    service = get_application_service(test_app.study)
    test_app.init_agent()
    manager = test_app.agent_manager
    assert service._command_handlers[CommandName.TRAIN] == (
        service._handle_train_with_automation
    )

    test_app.switch_page(0)

    with (
        patch(
            "XBrainLab.ui.panels.dataset.actions.QFileDialog.getOpenFileNames",
            return_value=([str(fif_path)], ""),
        ),
        patch(
            "XBrainLab.ui.panels.dataset.actions.DataInterpretationPreviewDialog",
        ) as PreviewDialog,
    ):
        PreviewDialog.return_value.exec.return_value = True
        PreviewDialog.return_value.get_result.return_value = {
            "confirmed": True,
            "choices": {"label_carrier": "embedded_events"},
        }
        assert test_app.dataset_panel.sidebar.import_btn.text() == "Import file"
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
        def __init__(self, _parent, _data_list, **_dialog_context):
            pass

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
        lambda: bool(_application_state(test_app.study)["epoch"]["exists"]),
        timeout=5000,
    )
    epoch_state = _application_state(test_app.study)["epoch"]
    assert epoch_state["exists"] is True
    assert epoch_state["epoch_count"] == 12
    assert epoch_state["n_channels"] == 4
    assert epoch_state["n_times"] == 167
    assert epoch_state["event_ids"] == {"left": 0, "right": 1}
    _assert_assistant_status_matches_publication(
        manager,
        command_name="generate_dataset",
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
    split_context = _query_diagnostics(
        test_app.study,
        "dataset_generation_context",
        include_objects=True,
    )
    assert split_context["epoch_available"] is True
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

    class FakeSplitDialog:
        def __init__(self, _parent, _controller, **_dialog_context):
            pass

        def exec(self):
            return True

        def get_result(self):
            return split_payload

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
    _wait_for_dataset_count(qtbot, test_app.study, 1)
    dataset_state = _application_state(test_app.study)["dataset"]
    assert dataset_state["count"] == EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY["count"]
    assert dataset_state["split_summary"] == EXPECTED_PRODUCT_WALKTHROUGH_SPLIT_SUMMARY
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
    assert training_state["model_name"] == "EEGNet"

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
