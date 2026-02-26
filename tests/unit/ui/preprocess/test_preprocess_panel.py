from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


@pytest.fixture
def mock_main_window(qapp):
    window = MagicMock(spec=QMainWindow)
    window.study = MagicMock()
    # Add custom methods not in QMainWindow spec
    window.refresh_panels = MagicMock()
    return window


@pytest.fixture
def mock_controller(mock_main_window):
    preprocess_ctrl = MagicMock()
    preprocess_ctrl.is_epoched.return_value = False
    preprocess_ctrl.has_data.return_value = True
    preprocess_ctrl.get_preprocessed_data_list.return_value = []

    dataset_ctrl = MagicMock()
    dataset_ctrl.get_loaded_data_list.return_value = []

    def get_ctrl_side_effect(name):
        if name == "preprocess":
            return preprocess_ctrl
        if name == "dataset":
            return dataset_ctrl
        return MagicMock()

    mock_main_window.study.get_controller.side_effect = get_ctrl_side_effect
    return preprocess_ctrl


def test_preprocess_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Use real objects for inheritance check
    real_window = QMainWindow()
    real_window.study = mock_main_window.study

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)
    assert panel.controller is not None
    assert panel.controller == mock_controller

    panel.close()
    real_window.close()


def test_preprocess_panel_filtering(mock_main_window, mock_controller, qtbot):
    """Test filtering delegates to controller."""
    mock_controller.has_data.return_value = True

    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel.plotter, "plot_sample_data"),  # Mock plotting
        patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = (
            1.0,
            40.0,
            50.0,
        )  # l_freq, h_freq, notch

        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
        ) as mock_info:
            panel.sidebar.open_filtering()

            mock_controller.apply_filter.assert_called_with(1.0, 40.0, 50.0)
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_resample(mock_main_window, mock_controller, qtbot):
    """Test resampling delegates to controller."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel.plotter, "plot_sample_data"),
        patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = 256.0

        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
        ) as mock_info:
            panel.sidebar.open_resample()

            mock_controller.apply_resample.assert_called_with(256.0)
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_epoching(mock_main_window, mock_controller, qtbot):
    """Test epoching delegates to controller."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    real_window.study = mock_main_window.study
    real_window.refresh_panels = MagicMock()

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel.plotter, "plot_sample_data"),
        patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = ((0.0, 0.1), ["Event1"], -0.2, 0.5)

        mock_controller.apply_epoching.return_value = True

        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
        ) as mock_info:
            panel.sidebar.open_epoching()

            mock_controller.apply_epoching.assert_called_with(
                (0.0, 0.1), ["Event1"], -0.2, 0.5
            )
            # Should show success message
            mock_info.assert_called_once()

    real_window.close()


def test_preprocess_panel_reset(mock_main_window, mock_controller, qtbot):
    """Test reset delegates to controller."""
    mock_controller.has_data.return_value = True
    real_window = QMainWindow()
    real_window.study = mock_main_window.study

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel.plotter, "plot_sample_data"),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
        ) as mock_info,
        patch.object(panel.sidebar, "info_panel") as mock_info_panel,
    ):
        panel.sidebar.reset_preprocess()
        mock_controller.reset_preprocess.assert_called_once()
        mock_info.assert_called_once()
        # mock_info_panel.update_info.assert_called_once()  # Handled by Service now

    real_window.close()


class TestPreprocessSidebarOps:
    """Tests for preprocess sidebar operations — rereference, normalize, errors."""

    @pytest.fixture
    def setup(self, mock_main_window, mock_controller, qtbot):
        mock_controller.has_data.return_value = True
        real_window = QMainWindow()
        real_window.study = mock_main_window.study
        real_window.refresh_panels = MagicMock()
        panel = PreprocessPanel(parent=real_window)
        qtbot.addWidget(panel)
        yield panel, mock_controller, real_window
        real_window.close()

    def test_rereference_success(self, setup):
        panel, mock_ctrl, _ = setup
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            panel.sidebar.open_rereference()
            mock_ctrl.apply_rereference.assert_called_with(["Cz"])
            mock_info.assert_called_once()

    def test_rereference_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_rereference.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.RereferenceDialog"
            ) as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            panel.sidebar.open_rereference()
            mock_crit.assert_called_once()

    def test_normalize_success(self, setup):
        panel, mock_ctrl, _ = setup
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "zscore"
            panel.sidebar.open_normalize()
            mock_ctrl.apply_normalization.assert_called_with("zscore")
            mock_info.assert_called_once()

    def test_normalize_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_normalization.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "zscore"
            panel.sidebar.open_normalize()
            mock_crit.assert_called_once()

    def test_filtering_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_filter.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, 50.0)
            panel.sidebar.open_filtering()
            mock_crit.assert_called_once()

    def test_resample_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_resample.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = 256.0
            panel.sidebar.open_resample()
            mock_crit.assert_called_once()

    def test_epoching_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_epoching.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (0.0, 0.1),
                ["Ev1"],
                -0.2,
                0.5,
            )
            panel.sidebar.open_epoching()
            mock_crit.assert_called_once()

    def test_reset_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.reset_preprocess.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
        ):
            panel.sidebar.reset_preprocess()
            mock_crit.assert_called_once()

    def test_update_button_states_epoched(self, setup):
        panel, _, _ = setup
        panel.sidebar._update_button_states(is_epoched=True)
        assert "locked" in panel.sidebar.btn_filter.toolTip().lower()
        assert "locked" in panel.sidebar.btn_epoch.toolTip().lower()
        assert "Epoched" in panel.sidebar.btn_epoch.text()

    def test_check_lock_when_epoched(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.is_epoched.return_value = True
        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
        ) as mock_warn:
            result = panel.sidebar.check_lock()
        assert result is True
        mock_warn.assert_called_once()

    def test_check_data_loaded_false(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.has_data.return_value = False
        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
        ) as mock_warn:
            result = panel.sidebar.check_data_loaded()
        assert result is False
        mock_warn.assert_called_once()
