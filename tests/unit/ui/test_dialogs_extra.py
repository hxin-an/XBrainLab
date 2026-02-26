"""Coverage tests for dialogs: event_filter, import_label, manual_split, smart_parser,
optimizer_setting, channel_selection, epoching, training_setting, data_splitting_dialog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QComboBox

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
        assert dlg is not None

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
        assert dlg is not None

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
        assert d is not None


# ============ ChannelSelectionDialog ============


class TestChannelSelectionDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (
            ChannelSelectionDialog,
        )

        data_obj = MagicMock()
        data_obj.get_mne.return_value.ch_names = [
            "C3",
            "C4",
            "Cz",
            "Fz",
            "Pz",
            "O1",
            "O2",
        ]
        data_list = [data_obj]
        d = ChannelSelectionDialog(None, data_list)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg is not None

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
        assert dlg is not None

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
        d = EpochingDialog(None, data_list)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg is not None

    def test_toggle_baseline(self, dlg):
        dlg.toggle_baseline(True)
        dlg.toggle_baseline(False)

    def test_update_duration_info(self, dlg):
        dlg.update_duration_info()


# ============ SmartParserDialog ============


class TestSmartParserDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.smart_parser_dialog import SmartParserDialog

        filenames = [
            "S01_sess1_run1.set",
            "S01_sess2_run1.set",
            "S02_sess1_run1.set",
        ]
        d = SmartParserDialog(filenames, parent=None)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg is not None

    def test_toggle_mode(self, dlg):
        dlg.toggle_mode()

    def test_update_preview(self, dlg):
        dlg.update_preview()


# ============ TrainingSettingDialog ============


class TestTrainingSettingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.training.training_setting_dialog import (
            TrainingSettingDialog,
        )

        ctrl = MagicMock()
        ctrl.get_training_option.return_value = None
        ctrl.has_model.return_value = True
        ctrl.get_model_holder.return_value = MagicMock()
        d = TrainingSettingDialog(None, ctrl)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg is not None

    def test_set_optimizer(self, dlg):
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.OptimizerSettingDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            import torch.optim

            MockDlg.return_value.get_result.return_value = (
                torch.optim.Adam,
                {"lr": 0.001},
            )
            dlg.set_optimizer()

    def test_set_output_dir(self, dlg):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="/tmp/output",
        ):
            dlg.set_output_dir()


# ============ ControlSidebar ============


class TestControlSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from PyQt6.QtWidgets import QMainWindow

        from XBrainLab.ui.panels.visualization.control_sidebar import ControlSidebar

        panel = MagicMock()
        panel.controller = MagicMock()
        panel.main_window = QMainWindow()
        sb = ControlSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert sidebar is not None

    def test_update_info(self, sidebar):
        sidebar.update_info()

    def test_set_montage(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.visualization.control_sidebar.PickMontageDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = (
                ["C3", "C4"],
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            )
            sidebar.set_montage()

    def test_set_saliency(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.visualization.control_sidebar.SaliencySettingDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = {"method": "gradient"}
            sidebar.set_saliency()

    def test_export_saliency(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.visualization.control_sidebar.ExportSaliencyDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            sidebar.export_saliency()
