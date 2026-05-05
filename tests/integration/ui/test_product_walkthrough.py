"""Product-level UI walkthroughs for XBrainLab desktop workflows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import mne
import numpy as np
import torch
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractButton, QLabel, QWidget

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.record import RecordKey, TrainRecordKey
from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
    LocalRuntimeFirstRunDialog,
)


def _click(qtbot, button) -> None:
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait(50)


def _write_synthetic_raw_fif(tmp_path):
    sfreq = 128
    ch_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(7).normal(size=(len(ch_names), sfreq * 6))
    raw = mne.io.RawArray(data, info)
    events = np.array(
        [
            [128, 0, 1],
            [256, 0, 2],
            [384, 0, 1],
            [512, 0, 2],
            [640, 0, 1],
            [704, 0, 2],
        ],
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


def test_assistant_product_click_through_layout(test_app, qtbot):
    """Open assistant, verify product language, bubbles, composer, and nav."""
    manager = test_app.agent_manager
    with (
        patch.object(manager, "_load_runtime_config", return_value=SimpleNamespace()),
        patch.object(
            manager,
            "_assistant_runtime_start_status",
            return_value=(False, "Model cache not found."),
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
    assert dock_title_text == "XBrainLab"
    assert panel.title_label.text() == ""
    assert panel.title_label.isHidden()
    assert panel.findChild(type(panel.title_label), "AssistantSubtitle").isHidden()
    assert panel.findChild(QWidget, "AssistantHeader").isHidden()
    assert panel.workflow_guidance.isHidden()
    assert "Commands:" not in panel.available_commands_chip.text()
    assert "load_data" not in panel.available_commands_chip.text()
    assert "attach_labels" not in panel.available_commands_chip.text()
    assert "Load EEG data" not in panel.available_commands_chip.text()
    assert "Attach labels" not in panel.available_commands_chip.text()
    assert "Scan data source" in panel.available_commands_chip.text()
    visible_footer_text = " ".join(
        label.text()
        for label in panel.control_panel.findChildren(type(panel.title_label))
        if label.isVisible()
    )
    assert visible_footer_text == ""
    assert "Local" not in visible_footer_text
    assert "Backend" not in visible_footer_text
    assert panel.options_btn.isHidden()
    assert panel.feature_btn.isHidden()
    assert panel.mode_btn.isHidden()
    assert panel.step_mode_status_label.isHidden()
    assert panel.input_field.placeholderText() == "Ask about EEG workflow"
    assert len(panel.input_field.placeholderText()) <= 24

    visible_first_layer = " ".join(
        child.text()
        for child in panel.findChildren(QWidget)
        if isinstance(child, (QLabel, QAbstractButton))
        and child.isVisible()
        and child.text()
    )
    for forbidden in [
        "General Assistant",
        "XBrainLab Assistant",
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

    heading_text = f"{dock_title_text} {panel.title_label.text()}"
    assert heading_text.count("Assistant") == 0

    assert manager.retry_title_btn.text() == "↻"
    assert manager.retry_title_btn.isEnabled() is False
    assert not hasattr(manager, "clear_title_btn")
    assert manager.retry_title_btn.geometry().right() <= (
        manager.new_conv_title_btn.geometry().left()
    )
    menu_text = [
        action.text() for action in manager.settings_menu.actions() if action.text()
    ]
    assert menu_text == ["Assistant settings", "Clear conversation"]
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
        patch.object(manager, "_load_runtime_config", return_value=SimpleNamespace()),
        patch.object(
            manager,
            "_assistant_runtime_start_status",
            return_value=(False, "Model cache not found."),
        ),
    ):
        manager.handle_user_input("hello")
    assert manager.retry_title_btn.isEnabled()
    assert manager.clear_conversation_title_action.isEnabled()
    assert panel.retry_btn.isHidden()
    assert panel.clear_btn.isHidden()

    send_text_width = panel.send_btn.fontMetrics().horizontalAdvance(
        panel.send_btn.text()
    )
    assert send_text_width < panel.send_btn.width() - 12

    panel.append_message("user", "hello from a product user")
    user_bubble = panel.chat_layout.itemAt(panel.chat_layout.count() - 2).widget()
    assert user_bubble.get_text().endswith("user")
    assert user_bubble.text_edit.toPlainText().endswith("user")
    assert (
        user_bubble.text_edit.document().textWidth() < user_bubble.bubble_frame.width()
    )

    manager._handle_agent_response(
        "Tool",
        "Tool list_files completed. Error: directory is required",
    )
    transcript_after_tool = "\n".join(
        message["content"] for message in manager.chat_controller.messages
    )
    assert "Tool list_files completed" not in transcript_after_tool
    assert "could not complete" in panel.notice_label.text()

    manager._handle_agent_response(
        "Tool",
        "Workflow state ready. Import EEG files to begin.",
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


def test_assistant_first_open_preserves_local_runtime_confirmation(test_app, qtbot):
    """Opening the dock still reaches the local runtime first-run confirmation."""
    manager = test_app.agent_manager
    with (
        patch.object(manager, "_load_runtime_config", return_value=SimpleNamespace()),
        patch.object(manager, "_needs_local_runtime_first_run", return_value=True),
        patch.object(
            manager,
            "_show_local_runtime_first_run_dialog",
            return_value=LocalRuntimeFirstRunDialog.LATER,
        ) as show_first_run,
        patch.object(manager, "_assistant_runtime_start_status") as start_status,
        patch.object(manager, "start_system") as start_system,
    ):
        _click(qtbot, test_app.ai_btn)

    assert manager.chat_dock.isVisible()
    show_first_run.assert_called_once()
    start_status.assert_not_called()
    start_system.assert_not_called()


def test_pipeline_product_walkthrough_uses_user_facing_actions(
    test_app, qtbot, tmp_path
):
    """Drive import -> preprocess -> epoch -> split -> configure -> dry-run train."""
    fif_path = _write_synthetic_raw_fif(tmp_path)

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
        PreviewDialog.return_value.get_result.return_value = {"confirmed": True}
        assert test_app.dataset_panel.sidebar.import_btn.text() == (
            "Interpret Data Source"
        )
        _click(qtbot, test_app.dataset_panel.sidebar.import_btn)

    assert test_app.study.loaded_data_list
    assert test_app.dataset_panel.table.rowCount() == 1

    _click(qtbot, test_app.nav_btns[1])

    class FakeFilteringDialog:
        def __init__(self, _parent):
            pass

        def exec(self):
            return True

        def get_params(self):
            return (1.0, 40.0, None)

    class FakeEpochingDialog:
        def __init__(self, _parent, _data_list):
            pass

        def exec(self):
            return True

        def get_params(self):
            return (None, ["left", "right"], 0.0, 0.25)

    with patch(
        "XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog",
        FakeFilteringDialog,
    ):
        _click(qtbot, test_app.preprocess_panel.sidebar.btn_filter)
    assert test_app.study.preprocessed_data_list

    with patch(
        "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog",
        FakeEpochingDialog,
    ):
        _click(qtbot, test_app.preprocess_panel.sidebar.btn_epoch)
    assert test_app.study.epoch_data is not None

    _click(qtbot, test_app.nav_btns[2])

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
    generator = test_app.study.get_datasets_generator(split_config)

    class FakeSplitDialog:
        def __init__(self, _parent, _controller):
            pass

        def exec(self):
            return True

        def get_result(self):
            return generator

    class FakeModelDialog:
        def __init__(self, _parent, _controller):
            pass

        def exec(self):
            return True

        def get_result(self):
            return ModelHolder(EEGNet, {}, None)

    class FakeTrainingSettingDialog:
        def __init__(self, _parent, _controller):
            pass

        def exec(self):
            return True

        def get_result(self):
            return TrainingOption(
                output_dir=str(tmp_path / "training-output"),
                optim=torch.optim.Adam,
                optim_params={},
                use_cpu=True,
                gpu_idx=None,
                epoch=1,
                bs=2,
                lr=0.001,
                checkpoint_epoch=0,
                evaluation_option=TrainingEvaluation.TEST_ACC,
                repeat_num=1,
            )

    with patch(
        "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog", FakeSplitDialog
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_split)
    assert test_app.study.datasets

    with patch(
        "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog", FakeModelDialog
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_model)
    assert test_app.study.model_holder is not None

    with patch(
        "XBrainLab.ui.panels.training.sidebar.TrainingSettingDialog",
        FakeTrainingSettingDialog,
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_setting)
    assert test_app.study.training_option is not None
    assert test_app.training_panel.sidebar.btn_start.isEnabled()

    training_controller = test_app.study.get_controller("training")

    def fake_start_training():
        eval_record = SimpleNamespace(
            get_per_class_metrics=lambda: {
                0: {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 2},
                1: {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 2},
                "macro_avg": {
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1-score": 1.0,
                    "support": 4,
                },
            }
        )
        record = SimpleNamespace(
            epoch=1,
            repeat=0,
            train={
                TrainRecordKey.LOSS: [0.25],
                TrainRecordKey.ACC: [100.0],
                TrainRecordKey.LR: [0.001],
            },
            val={
                RecordKey.LOSS: [0.2],
                RecordKey.ACC: [100.0],
            },
            eval_record=eval_record,
            is_finished=lambda: True,
            get_epoch=lambda: 1,
            get_eval_record=lambda: eval_record,
            get_confusion_figure=lambda show_percentage=False: Figure(figsize=(3, 2)),
        )
        model_holder = ModelHolder(EEGNet, {}, None)
        option = test_app.study.training_option
        plan = SimpleNamespace(
            model_holder=model_holder,
            option=option,
            get_name=lambda: "Product walkthrough dry-run",
            get_plans=lambda: [record],
            get_training_repeat=lambda: 0,
        )
        test_app.study.trainer = SimpleNamespace(
            get_training_plan_holders=lambda: [plan],
            is_running=lambda: False,
            current_idx=0,
        )
        training_controller.notify("training_started")
        training_controller.notify("training_stopped")

    with patch.object(
        training_controller, "start_training", side_effect=fake_start_training
    ):
        _click(qtbot, test_app.training_panel.sidebar.btn_start)

    _click(qtbot, test_app.nav_btns[3])
    assert test_app.evaluation_panel.model_combo.currentText().startswith("Fold 1")
    assert "Finished" in test_app.evaluation_panel.run_combo.currentText()
