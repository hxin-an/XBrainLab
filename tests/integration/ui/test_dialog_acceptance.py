from __future__ import annotations

from unittest.mock import MagicMock, patch

import torch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QGroupBox, QLabel

from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.ui.dialogs.dataset.event_filter_dialog import EventFilterDialog
from XBrainLab.ui.dialogs.dataset.label_mapping_dialog import LabelMappingDialog
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog
from XBrainLab.ui.dialogs.training.training_setting_dialog import TrainingSettingDialog


def _show_dialog(qtbot, dialog: QDialog) -> None:
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)


def _click_ok(qtbot, dialog: QDialog) -> None:
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    qtbot.mouseClick(ok_button, Qt.MouseButton.LeftButton)
    qtbot.wait(50)


def test_label_mapping_dialog_accepts_auto_sorted_mapping(qtbot):
    dialog = LabelMappingDialog(
        None,
        ["/tmp/sub01.set", "/tmp/sub02.set"],
        ["/tmp/sub02_labels.txt", "/tmp/sub01_labels.txt"],
    )

    _show_dialog(qtbot, dialog)
    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_mapping() == {
        "/tmp/sub01.set": "/tmp/sub01_labels.txt",
        "/tmp/sub02.set": "/tmp/sub02_labels.txt",
    }


def test_event_filter_dialog_accepts_checked_selection_via_ok_button(qtbot):
    fake_settings = MagicMock()
    fake_settings.value.return_value = []

    with patch(
        "XBrainLab.ui.dialogs.dataset.event_filter_dialog.QSettings",
        return_value=fake_settings,
    ):
        dialog = EventFilterDialog(None, ["left_hand", "right_hand", "feet"])

    _show_dialog(qtbot, dialog)

    dialog.set_all_checked(False)
    assert dialog.list_widget is not None
    item = dialog.list_widget.item(1)
    assert item is not None
    item.setCheckState(Qt.CheckState.Checked)

    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_selected_ids() == ["right_hand"]
    fake_settings.setValue.assert_called_once_with(
        "last_selected_events",
        ["right_hand"],
    )


def test_epoching_dialog_accepts_selected_event_and_baseline_toggle(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"left": 1, "right": 2})
    dialog = EpochingDialog(None, [data])

    _show_dialog(qtbot, dialog)

    assert dialog.event_list is not None
    for row in range(dialog.event_list.rowCount()):
        check_item = dialog.event_list.item(row, 0)
        event_item = dialog.event_list.item(row, 1)
        assert check_item is not None
        assert event_item is not None
        check_item.setCheckState(
            Qt.CheckState.Checked
            if event_item.text() == "left"
            else Qt.CheckState.Unchecked
        )
    assert dialog.baseline_check is not None
    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    dialog.baseline_check.setChecked(False)
    dialog.tmin_spin.setValue(-0.1)
    dialog.tmax_spin.setValue(0.8)

    _click_ok(qtbot, dialog)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_result() == (None, ["left"], -0.1, 0.8)


def test_epoching_dialog_uses_import_interval_defaults(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (
        None,
        {"Left hand": 1, "Right hand": 2, "Artifact": 99},
    )
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 288, "min": 0.5, "max": 1.25},
        "class_map": {"left": "Left hand", "right": "Right hand"},
    }
    dialog = EpochingDialog(None, [data])

    _show_dialog(qtbot, dialog)

    visible_text = "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.text().strip() and label.isVisibleTo(dialog)
    )
    assert "Suggested from import" in visible_text
    assert "BIDS events.tsv" in visible_text
    assert "Label interval" in visible_text
    assert dialog.tmin_spin is not None
    assert dialog.tmax_spin is not None
    assert dialog.baseline_check is not None
    assert dialog.event_list is not None
    assert dialog.tmin_spin.value() == 0.0
    assert dialog.tmax_spin.value() == 1.25
    assert dialog.baseline_check.isChecked() is False
    checked = [
        event_item.text()
        for row in range(dialog.event_list.rowCount())
        if (check_item := dialog.event_list.item(row, 0)) is not None
        and (event_item := dialog.event_list.item(row, 1)) is not None
        and check_item.checkState() == Qt.CheckState.Checked
    ]
    assert checked == ["Left hand", "Right hand"]


def test_epoching_dialog_displays_and_returns_backend_duration_requirement(
    qtbot,
):
    data = MagicMock()
    data.get_event_list.return_value = (
        None,
        {"left": 1, "right": 2},
    )
    data.get_sfreq.return_value = 100.0
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 2, "min": 0.25, "max": 12.0},
        "class_map": {"left": "left", "right": "right"},
    }
    dialog = EpochingDialog(None, [data])
    _show_dialog(qtbot, dialog)

    requirement = dialog.confirmation_requirement
    assert requirement is not None
    assert dialog.warning_label is not None
    assert requirement["message"] in dialog.warning_label.text()
    assert dialog.confirmation_check is not None
    assert dialog.confirmation_check.text() == requirement["confirmation_label"]

    with patch(
        "XBrainLab.ui.dialogs.preprocess.epoching_dialog.QMessageBox.warning"
    ) as warning:
        dialog.accept()
    warning.assert_called_once_with(
        dialog,
        requirement["title"],
        requirement["message"],
    )
    assert dialog.get_params() is None
    assert dialog.get_confirmation_receipt() is None

    dialog.confirmation_check.setChecked(True)
    initial_receipt = requirement["receipt"]
    assert dialog.tmax_spin is not None
    dialog.tmax_spin.setValue(10.0)
    assert dialog.confirmation_check.isChecked() is False
    assert dialog.confirmation_requirement is not None
    assert dialog.confirmation_requirement["receipt"] != initial_receipt

    window_receipt = dialog.confirmation_requirement["receipt"]
    dialog.confirmation_check.setChecked(True)
    assert dialog.event_list is not None
    for row in range(dialog.event_list.rowCount()):
        event_item = dialog.event_list.item(row, 1)
        check_item = dialog.event_list.item(row, 0)
        if (
            event_item is not None
            and check_item is not None
            and event_item.text() == "right"
        ):
            check_item.setCheckState(Qt.CheckState.Unchecked)
            break
    assert dialog.confirmation_check.isChecked() is False
    assert dialog.confirmation_requirement is not None
    assert dialog.confirmation_requirement["receipt"] != window_receipt

    dialog.confirmation_check.setChecked(True)
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert (
        dialog.get_confirmation_receipt()
        == (dialog.confirmation_requirement["receipt"])
    )


def test_epoching_dialog_preserves_sample_aligned_bids_tmax_precision(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"late_event": 1})
    data.get_sfreq.return_value = 250.0
    data.get_runtime_detail.return_value = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "label_field": "trial_type",
        "time_field": "onset",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
        "class_map": {"late_event": "late_event"},
    }
    context = build_epoching_context([data])

    dialog = EpochingDialog(None, [data], epoch_context=context)
    _show_dialog(qtbot, dialog)

    assert dialog.tmax_spin is not None
    assert dialog.duration_label is not None
    assert context["suggested_t_max"] == 0.496
    assert dialog.tmax_spin.value() == 0.496
    assert "0.50 s window" in dialog.duration_label.text()


def test_epoching_dialog_uses_card_sections_not_groupbox_legends(qtbot):
    data = MagicMock()
    data.get_event_list.return_value = (None, {"Left hand": 1, "Right hand": 2})
    data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "class_map": {"769": "Left hand", "770": "Right hand"},
    }
    dialog = EpochingDialog(None, [data])

    _show_dialog(qtbot, dialog)

    assert dialog.findChildren(QGroupBox) == []


def test_training_setting_dialog_accepts_user_edits_via_ok_button(qtbot):
    controller = MagicMock()
    controller.get_training_option.return_value = None

    with patch(
        "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
        return_value={"Adam": torch.optim.Adam},
    ):
        dialog = TrainingSettingDialog(None, controller)

    _show_dialog(qtbot, dialog)

    assert dialog.epoch_entry is not None
    assert dialog.bs_entry is not None
    assert dialog.lr_entry is not None
    assert dialog.checkpoint_entry is not None
    assert dialog.repeat_entry is not None
    assert dialog.output_dir_label is not None
    assert dialog.evaluation_combo is not None
    dialog.epoch_entry.setText("12")
    dialog.bs_entry.setText("16")
    dialog.lr_entry.setText("0.0005")
    dialog.checkpoint_entry.setText("2")
    dialog.repeat_entry.setText("3")
    dialog.output_dir = "/tmp/train-output"
    dialog.output_dir_label.setText("/tmp/train-output")
    dialog.evaluation_combo.setCurrentText("Last Epoch")

    _click_ok(qtbot, dialog)

    option = dialog.get_result()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert option is not None
    assert option.epoch == 12
    assert option.bs == 16
    assert option.lr == 0.0005
    assert option.output_dir == "/tmp/train-output"
    assert option.repeat_num == 3
