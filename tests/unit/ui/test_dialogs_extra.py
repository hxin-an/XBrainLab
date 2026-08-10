"""Coverage tests for dialogs: event_filter, import_label, manual_split, smart_parser,
optimizer_setting, channel_selection, epoching, training_setting, data_splitting_dialog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
)

from XBrainLab.backend.application.epoch_context import build_epoching_context

# ============ EventFilterDialog ============


class TestEventFilterDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.event_filter_dialog import EventFilterDialog

        events = ["left_hand", "right_hand", "feet", "tongue"]
        d = EventFilterDialog(None, events)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_set_all_checked(self, dlg):
        dlg.set_all_checked(True)
        dlg.set_all_checked(False)

    def test_set_selection(self, dlg):
        dlg.set_selection(["left_hand", "feet"])

    def test_get_selected_ids_empty(self, dlg):
        dlg.set_all_checked(False)
        dlg.accept()
        result = dlg.get_selected_ids()
        assert result == []

    def test_get_selected_ids_all(self, dlg):
        dlg.set_all_checked(True)
        dlg.accept()
        result = dlg.get_selected_ids()
        assert len(result) == 4

    def test_accept_with_selection(self, dlg):
        dlg.set_all_checked(True)
        dlg.accept()
        result = dlg.get_result()
        assert len(result) == 4

    def test_toggle_selected(self, dlg):
        dlg.set_all_checked(True)
        dlg.toggle_selected()

    def test_toggle_selected_with_items(self, dlg):
        # Select first two items, then toggle
        dlg.set_all_checked(True)
        for i in range(2):
            item = dlg.list_widget.item(i)
            item.setSelected(True)
        dlg.toggle_selected()

    def test_show_context_menu_check(self, dlg):
        from PyQt6.QtCore import QPoint

        dlg.list_widget.item(0).setSelected(True)
        with patch("XBrainLab.ui.dialogs.dataset.event_filter_dialog.QMenu") as M:
            a_check = MagicMock()
            a_uncheck = MagicMock()
            a_toggle = MagicMock()
            M.return_value.addAction.side_effect = [a_check, a_uncheck, a_toggle]
            M.return_value.exec.return_value = a_check
            dlg.show_context_menu(QPoint(0, 0))

    def test_show_context_menu_uncheck(self, dlg):
        from PyQt6.QtCore import QPoint

        dlg.set_all_checked(True)
        dlg.list_widget.item(0).setSelected(True)
        with patch("XBrainLab.ui.dialogs.dataset.event_filter_dialog.QMenu") as M:
            a_check = MagicMock()
            a_uncheck = MagicMock()
            a_toggle = MagicMock()
            M.return_value.addAction.side_effect = [a_check, a_uncheck, a_toggle]
            M.return_value.exec.return_value = a_uncheck
            dlg.show_context_menu(QPoint(0, 0))

    def test_show_context_menu_toggle(self, dlg):
        from PyQt6.QtCore import QPoint

        dlg.set_all_checked(True)
        dlg.list_widget.item(0).setSelected(True)
        with patch("XBrainLab.ui.dialogs.dataset.event_filter_dialog.QMenu") as M:
            a_check = MagicMock()
            a_uncheck = MagicMock()
            a_toggle = MagicMock()
            M.return_value.addAction.side_effect = [a_check, a_uncheck, a_toggle]
            M.return_value.exec.return_value = a_toggle
            dlg.show_context_menu(QPoint(0, 0))

    def test_key_press_space_toggles(self, dlg):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent

        dlg.set_all_checked(True)
        dlg.list_widget.item(0).setSelected(True)
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier(0)
        )
        dlg.keyPressEvent(event)

    def test_accept_persists_selection(self, dlg):
        dlg.set_all_checked(True)
        dlg.accept()
        assert len(dlg.get_selected_ids()) == 4


# ============ ManualSplitDialog ============


class TestManualSplitDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.manual_split_dialog import ManualSplitDialog

        choices = ["S01", "S02", "S03", "S04"]
        d = ManualSplitDialog(None, choices)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_accept(self, dlg):
        # Select first 2 items
        for i in range(2):
            item = dlg.list_widget.item(i)
            item.setSelected(True)
        dlg.accept()
        result = dlg.get_result()
        assert result is not None

    def test_creates_with_tuples(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.manual_split_dialog import ManualSplitDialog

        choices = [(0, "SubjectA"), (1, "SubjectB")]
        d = ManualSplitDialog(None, choices)
        qtbot.addWidget(d)
        assert isinstance(d, ManualSplitDialog)


# ============ ChannelSelectionDialog ============


class TestChannelSelectionDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (
            ChannelSelectionDialog,
        )

        channels = [
            "C3",
            "C4",
            "Cz",
            "Fz",
            "Pz",
            "O1",
            "O2",
        ]
        d = ChannelSelectionDialog(None, channels)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_set_all_checked(self, dlg):
        dlg.set_all_checked(True)
        dlg.set_all_checked(False)

    def test_filter_channels(self, dlg):
        dlg.filter_channels("C")

    def test_accept_all_selected(self, dlg):
        dlg.set_all_checked(True)
        dlg.accept()
        result = dlg.get_result()
        assert len(result) == 7

    def test_accept_none_selected(self, dlg):
        dlg.set_all_checked(False)
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            dlg.accept()


# ============ OptimizerSettingDialog ============


class TestOptimizerSettingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.training.optimizer_setting_dialog import (
            OptimizerSettingDialog,
        )

        d = OptimizerSettingDialog(None)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_has_algo_combo(self, dlg):
        assert isinstance(dlg.algo_combo, QComboBox)

    def test_on_algo_select(self, dlg):
        dlg.on_algo_select("Adam")

    def test_on_algo_select_sgd(self, dlg):
        dlg.on_algo_select("SGD")

    def test_accept(self, dlg):
        dlg.on_algo_select("Adam")
        dlg.accept()
        result = dlg.get_result()
        assert result is not None


# ============ EpochingDialog ============


class TestEpochingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data_list = [MagicMock()]
        data_list[0].get_events_from_annotations.return_value = (
            {"left": 1, "right": 2},
            [],
        )
        data_list[0].get_event_list.return_value = (
            None,
            {"left": 1, "right": 2},
        )
        data_list[0].get_runtime_detail.return_value = {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {"left": "left", "right": "right"},
        }
        d = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                data_list,
                epoch_handoff={
                    "ready": True,
                    "supervised_ready": True,
                    "label_source": "internal_events",
                    "placement_modes": ["internal_events"],
                    "default_epoch_events": ["left", "right"],
                    "selected_event_names": ["left", "right"],
                },
            ),
        )
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_toggle_baseline(self, dlg):
        dlg.toggle_baseline(True)
        dlg.toggle_baseline(False)

    def test_update_duration_info(self, dlg):
        dlg.update_duration_info()

    def test_label_backgrounds_are_transparent(self, dlg):
        assert "QLabel {" in dlg.styleSheet()
        assert "background-color: transparent" in dlg.styleSheet()

        labels_with_local_style = [
            label for label in dlg.findChildren(QLabel) if label.styleSheet().strip()
        ]
        assert labels_with_local_style
        assert all(
            "background-color: transparent" in label.styleSheet()
            for label in labels_with_local_style
        )

    def test_content_scrolls_above_fixed_footer(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        dialog = EpochingDialog(
            None,
            epoch_context={
                "available_events": [
                    {"name": f"event_{index:02d}", "count": 20} for index in range(16)
                ],
                "has_import_hint": True,
                "source": "loaded label files",
                "placement_label": "Label interval",
                "label_field": "trial_type",
                "time_field": "onset",
                "duration_field": "duration",
                "window_evidence": (
                    "Suggested from imported event timing. Review this if the "
                    "dataset uses a different reference point."
                ),
            },
        )
        qtbot.addWidget(dialog)
        dialog.resize(620, 420)
        dialog.show()
        qtbot.wait(0)

        scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
        assert scroll is not None
        assert scroll.widgetResizable()
        assert (
            scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert scroll.isVisibleTo(dialog)

        footer = dialog.findChild(QDialogButtonBox)
        assert footer is not None
        assert footer.isVisibleTo(dialog)

    def test_import_handoff_preselects_epoch_targets(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

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
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 3,
            "unknown_duration_count": 3,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        assert dialog.handoff_label is None
        checked = [
            dialog.event_list.item(row, 1).text()
            for row in range(dialog.event_list.rowCount())
            if dialog.event_list.item(row, 0).checkState() == Qt.CheckState.Checked
        ]

        assert checked == ["Left hand", "Right hand"]
        assert not dialog.event_list.selectedItems()
        assert any(
            "BIDS events from import" in label.text()
            for label in dialog.findChildren(QLabel)
        )

    def test_assistant_handoff_prefills_explicit_event_and_window(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"768": 1, "769": 2, "770": 3},
        )
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data]),
            assistant_suggestions={
                "target_event": "769",
                "t_min": "-0.2",
                "t_max": "0.8",
            },
        )
        qtbot.addWidget(dialog)

        checked = [
            dialog.event_list.item(row, 1).text()
            for row in range(dialog.event_list.rowCount())
            if dialog.event_list.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        assert checked == ["769"]
        assert dialog.tmin_spin.value() == pytest.approx(-0.2)
        assert dialog.tmax_spin.value() == pytest.approx(0.8)

    def test_bids_epoch_dialog_surfaces_duration_policy(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"left": 1, "right": 2},
        )
        data.get_runtime_detail.return_value = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 3, "min": 0.25, "max": 12.0},
            "placement_event_count": 3,
            "unknown_duration_count": 0,
            "class_map": {"left": "left", "right": "right"},
        }

        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                [data],
                epoch_handoff={
                    "ready": True,
                    "supervised_ready": True,
                    "label_source": "bids_events",
                    "placement_modes": ["interval"],
                    "default_epoch_events": ["left", "right"],
                    "selected_event_names": ["left", "right"],
                },
            ),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)

        labels_text = "\n".join(
            label.text()
            for label in dialog.findChildren(QLabel)
            if label.text().strip()
        )

        assert "BIDS events from import" in labels_text
        assert "BIDS events confirmed in Match Labels" not in labels_text
        assert "Use one fixed window" in labels_text
        assert "review the EEG epoch window" in labels_text
        assert dialog.tmin_spin.value() == 0.0
        assert dialog.tmax_spin.value() == 12.0
        assert not dialog.baseline_check.isChecked()

    def test_import_handoff_uses_checked_events_not_stale_selection(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"Left hand": 1, "Right hand": 2},
        )
        data.get_runtime_detail.return_value = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 2,
            "unknown_duration_count": 2,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": True,
            "supervised_ready": True,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        for row in range(dialog.event_list.rowCount()):
            dialog.event_list.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

        with patch(
            "XBrainLab.ui.dialogs.preprocess.epoching_dialog.QMessageBox.warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.get_params() is None

    def test_rejects_baseline_outside_epoch_window(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

        data = MagicMock()
        data.get_event_list.return_value = (
            None,
            {"Left hand": 1},
        )
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data]),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        dialog.event_list.item(0, 0).setCheckState(Qt.CheckState.Checked)
        dialog.tmin_spin.setValue(0.0)
        dialog.tmax_spin.setValue(1.0)
        dialog.baseline_check.setChecked(True)
        dialog.b_min_spin.setValue(-0.2)
        dialog.b_max_spin.setValue(0.0)

        with patch(
            "XBrainLab.ui.dialogs.preprocess.epoching_dialog.QMessageBox.warning"
        ) as warning:
            dialog.accept()

        warning.assert_called_once()
        assert dialog.get_params() is None

    def test_import_handoff_blockers_override_epoch_defaults(self, qtbot):
        from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

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
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 3,
            "unknown_duration_count": 3,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        }
        handoff = {
            "ready": False,
            "supervised_ready": False,
            "default_epoch_events": ["Left hand", "Right hand"],
            "selected_event_names": ["Left hand", "Right hand"],
            "supervised_blockers": ["No class labels were reviewed."],
            "label_source": "bids_events",
            "placement_modes": ["interval"],
        }
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context([data], epoch_handoff=handoff),
        )
        qtbot.addWidget(dialog)

        assert dialog.event_list is not None
        assert dialog.handoff_label is not None
        selected = [item.text() for item in dialog.event_list.selectedItems()]

        assert selected == []
        assert "needs review" in dialog.handoff_label.text()
        assert "No class labels" in dialog.handoff_label.text()
