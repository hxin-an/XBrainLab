"""Coverage tests for sidebar modules: preprocess, training, dataset, viz control."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow


def _make_panel_mock():
    p = MagicMock()
    p.controller = MagicMock()
    p.dataset_controller = MagicMock()
    # main_window must be a real QWidget so AggregateInfoPanel can use it as parent
    p.main_window = QMainWindow()
    p.update_panel = MagicMock()
    p.controller.is_locked.return_value = False
    p.controller.has_data.return_value = True
    p.controller.is_epoched.return_value = False
    return p


# ============ PreprocessSidebar ============


class TestPreprocessSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar

        panel = _make_panel_mock()
        panel.controller.get_preprocessed_data_list.return_value = []
        sb = PreprocessSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert sidebar is not None

    def test_update_sidebar(self, sidebar):
        sidebar.update_sidebar()

    def test_check_lock_unlocked(self, sidebar):
        # check_lock returns False when NOT epoched (action is allowed)
        assert sidebar.check_lock() is False

    def test_check_lock_locked(self, sidebar):
        sidebar.panel.controller.is_epoched.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            # check_lock returns True when epoched (action is blocked)
            assert sidebar.check_lock() is True

    def test_check_data_loaded_true(self, sidebar):
        assert sidebar.check_data_loaded() is True

    def test_check_data_loaded_false(self, sidebar):
        sidebar.panel.controller.has_data.return_value = False
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            assert sidebar.check_data_loaded() is False

    def test_open_filtering_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, [50.0])
            sidebar.open_filtering()
            sidebar.panel.controller.apply_filter.assert_called_once()

    def test_open_resample_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = 256
            sidebar.open_resample()
            sidebar.panel.controller.apply_resample.assert_called_once()

    def test_open_rereference_accepted(self, sidebar):
        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            sidebar.open_rereference()
            sidebar.panel.controller.apply_rereference.assert_called_once()

    def test_open_normalize_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "z-score"
            sidebar.open_normalize()
            sidebar.panel.controller.apply_normalization.assert_called_once()

    def test_open_epoching_accepted(self, sidebar):
        with (
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (None, 0),
                ["left", "right"],
                -0.5,
                1.0,
            )
            sidebar.panel.controller.apply_epoching.return_value = True
            sidebar.open_epoching()
            sidebar.panel.controller.apply_epoching.assert_called_once()

    def test_reset_preprocess(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.reset_preprocess()
            sidebar.panel.controller.reset_preprocess.assert_called()


# ============ TrainingSidebar ============


class TestTrainingSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.training.sidebar import TrainingSidebar

        panel = _make_panel_mock()
        panel.controller.has_datasets.return_value = False
        panel.controller.has_model.return_value = False
        panel.controller.has_training_option.return_value = False
        panel.controller.is_training.return_value = False
        sb = TrainingSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert sidebar is not None

    def test_check_ready_to_train(self, sidebar):
        sidebar.check_ready_to_train()

    def test_update_info(self, sidebar):
        sidebar.update_info()

    def test_split_data_accepted(self, sidebar):
        sidebar.panel.controller.has_data = MagicMock(return_value=True)
        sidebar.panel.dataset_controller.has_data.return_value = True
        sidebar.panel.dataset_controller.get_epoch_data.return_value = MagicMock()
        with patch(
            "XBrainLab.ui.panels.training.sidebar.DataSplittingDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = MagicMock()
            sidebar.split_data()

    def test_select_model_accepted(self, sidebar):
        sidebar.panel.controller.is_training.return_value = False
        mock_holder = MagicMock()
        mock_holder.target_model.__name__ = "EEGNet"
        sidebar.panel.controller.get_model_holder.return_value = mock_holder
        with (
            patch(
                "XBrainLab.ui.panels.training.sidebar.ModelSelectionDialog"
            ) as MockDlg,
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = mock_holder
            sidebar.select_model()
            sidebar.panel.controller.set_model_holder.assert_called_once()

    def test_on_training_started(self, sidebar):
        sidebar.on_training_started()

    def test_on_training_stopped(self, sidebar):
        sidebar.on_training_stopped()

    def test_stop_training(self, sidebar):
        sidebar.panel.controller.is_training.return_value = True
        sidebar.stop_training()
        sidebar.panel.controller.stop_training.assert_called()

    def test_clear_history(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.clear_history()
            sidebar.panel.controller.clear_history.assert_called()


# ============ DatasetSidebar ============


class TestDatasetSidebar:
    @pytest.fixture
    def sidebar(self, qtbot):
        from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar

        panel = _make_panel_mock()
        panel.action_handler = MagicMock()
        panel.controller.get_loaded_data_list.return_value = []
        sb = DatasetSidebar(panel)
        qtbot.addWidget(sb)
        return sb

    def test_creates(self, sidebar):
        assert sidebar is not None

    def test_update_sidebar(self, sidebar):
        sidebar.update_sidebar()

    def test_open_channel_selection_accepted(self, sidebar):
        sidebar.panel.controller.has_data.return_value = True
        sidebar.panel.controller.is_locked.return_value = False
        sidebar.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        with patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = ["Fp1", "Fp2"]
            sidebar.open_channel_selection()

    def test_clear_dataset(self, sidebar):
        from PyQt6.QtWidgets import QMessageBox

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            sidebar.clear_dataset()
            sidebar.panel.controller.clean_dataset.assert_called()


# ============ CardWidget & PlaceholderWidget ============


class TestCardWidget:
    def test_creates_with_title(self, qtbot):
        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Test Card")
        qtbot.addWidget(card)
        assert card is not None

    def test_creates_without_title(self, qtbot):
        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("")
        qtbot.addWidget(card)
        assert card is not None

    def test_add_widget(self, qtbot):
        from PyQt6.QtWidgets import QLabel

        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Card")
        qtbot.addWidget(card)
        label = QLabel("hello")
        card.add_widget(label)

    def test_add_layout(self, qtbot):
        from PyQt6.QtWidgets import QHBoxLayout

        from XBrainLab.ui.components.card import CardWidget

        card = CardWidget("Card")
        qtbot.addWidget(card)
        layout = QHBoxLayout()
        card.add_layout(layout)


class TestPlaceholderWidget:
    def test_creates(self, qtbot):
        from XBrainLab.ui.components.placeholder import PlaceholderWidget

        w = PlaceholderWidget("📊", "No data available")
        qtbot.addWidget(w)
        assert w is not None

    def test_message_displayed(self, qtbot):
        from XBrainLab.ui.components.placeholder import PlaceholderWidget

        w = PlaceholderWidget("⚠", "Please load data first")
        qtbot.addWidget(w)
        assert "load data" in w.msg_label.text().lower()
