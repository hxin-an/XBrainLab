from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QAbstractItemView, QMainWindow, QMessageBox

from XBrainLab.backend.application import CommandCapability, CommandName
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderData,
    PreprocessRenderPublication,
    PreprocessRenderRequest,
    PreprocessSignalState,
    SignalSeries,
)
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


def _render_publication(
    state: PreprocessSignalState,
    *,
    history: tuple[str, ...] = (),
) -> PreprocessRenderPublication:
    request = PreprocessRenderRequest(publication_generation=3)
    data = (
        PreprocessRenderData(state=state)
        if state is PreprocessSignalState.NO_DATA
        else PreprocessRenderData(
            state=state,
            channels=("C3", "C4"),
            sampling_frequency=100.0,
            cursor_max_seconds=1.0,
            selected_channel_index=0 if state is PreprocessSignalState.RAW else None,
            selected_channel_name="C3" if state is PreprocessSignalState.RAW else None,
            history=history,
            current=(
                SignalSeries(
                    time_seconds=np.array([0.0, 0.01]),
                    values_volts=np.array([0.0, 1e-6]),
                    sampling_frequency=100.0,
                )
                if state is PreprocessSignalState.RAW
                else None
            ),
        )
    )
    return PreprocessRenderPublication(request=request, generation=3, data=data)


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
    cast(Any, real_window).study = mock_main_window.study

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)
    assert panel.controller is not None
    assert panel.controller == mock_controller

    panel.close()
    real_window.close()


def test_update_panel_uses_detached_publication_before_stale_controller(qtbot):
    from XBrainLab.backend.study import Study

    study = Study()
    controller = MagicMock()
    controller.study = study
    controller.get_preprocessed_data_list.side_effect = AssertionError(
        "stale preprocessed list should not be read",
    )
    dataset_controller = MagicMock()

    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
    )
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(0)
    panel.plotter.plot_sample_data = MagicMock()
    publication = _render_publication(
        PreprocessSignalState.RAW,
        history=("bandpass",),
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=publication,
    ):
        panel.update_panel()

    controller.get_preprocessed_data_list.assert_not_called()
    panel.plotter.plot_sample_data.assert_called_once_with(publication)
    assert panel.preview_widget.chan_combo.count() == 2


def test_update_panel_refuses_real_study_query_none_controller_fallback(qtbot):
    from XBrainLab.backend.study import Study

    controller = MagicMock()
    controller.study = Study()
    controller.get_preprocessed_data_list.side_effect = AssertionError(
        "stale preprocessed list should not be read",
    )
    dataset_controller = MagicMock()

    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
    )
    qtbot.addWidget(panel)
    panel.preview_widget.reset_view = MagicMock()

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=None,
    ):
        panel.update_panel()

    controller.get_preprocessed_data_list.assert_not_called()
    panel.preview_widget.reset_view.assert_called_once()


def test_update_panel_epoched_data_cancels_pending_plot_timer(qtbot):
    controller = MagicMock()
    dataset_controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
    )
    qtbot.addWidget(panel)
    panel.sidebar.update_sidebar = MagicMock()
    panel.plotter.plot_sample_data = MagicMock()

    publication = _render_publication(
        PreprocessSignalState.LOCKED,
        history=("epoch",),
    )

    panel.preview_widget.plot_timer.start(1000)
    assert panel.preview_widget.plot_timer.isActive()

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=publication,
    ):
        panel.update_panel()

    assert not panel.preview_widget.plot_timer.isActive()
    panel.plotter.plot_sample_data.assert_not_called()


def test_preprocess_panel_quiesces_native_plots_before_close(qtbot):
    panel = PreprocessPanel(
        controller=MagicMock(),
        dataset_controller=MagicMock(),
    )
    qtbot.addWidget(panel)
    panel.show()
    panel.preview_widget.plot_timer.start(1000)

    panel.close()
    qtbot.wait(0)

    preview = panel.preview_widget
    assert preview._native_plot_shutdown is True
    assert not preview.plot_timer.isActive()
    assert preview.proxy_time.slot is None
    assert preview.proxy_freq.slot is None
    assert not preview.plot_time.updatesEnabled()
    assert not preview.plot_freq.updatesEnabled()
    assert preview.time_current_curve.scene() is None
    assert preview.v_line_time.scene() is None
    assert preview.v_line_freq.scene() is None
    assert preview.v_line_time.getViewBox() is None
    assert preview.v_line_freq.getViewBox() is None
    # The PlotWidget remains parent-owned so a cancelled application close can
    # restore its detached graphics items without rebuilding native canvases.
    assert preview.plot_time.closed is False
    assert preview.plot_freq.closed is False
    assert preview.plot_time.getPlotItem() is not None
    assert preview.plot_freq.getPlotItem() is not None


def test_signal_preview_uses_distinct_no_data_loaded_and_locked_states(qtbot):
    controller = MagicMock()
    dataset_controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
    )
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(0)
    panel.plotter.plot_sample_data = MagicMock()

    panel.preview_widget.reset_view()
    assert panel.preview_widget.empty_state.isVisible()
    assert not panel.preview_widget.plot_content.isVisible()
    assert not panel.preview_widget.locked_state.isVisible()
    assert panel.preview_widget.empty_state_title.text() == "No EEG data loaded"

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=_render_publication(PreprocessSignalState.RAW),
    ):
        panel.update_panel()
    assert panel.preview_widget.plot_content.isVisible()
    assert not panel.preview_widget.empty_state.isVisible()
    assert not panel.preview_widget.locked_state.isVisible()

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=_render_publication(
            PreprocessSignalState.LOCKED,
            history=("Band-pass filter",),
        ),
    ):
        panel.update_panel()
    assert panel.preview_widget.locked_state.isVisible()
    assert not panel.preview_widget.plot_content.isVisible()
    assert panel.preview_widget.locked_state_title.text() == "Preprocessing locked"
    assert (
        "EEG epochs have already been created"
        in panel.preview_widget.locked_state_detail.text()
    )

    panel.preview_widget.show_unavailable_message(
        "Published preprocess objects are stale. Refresh the panel."
    )
    assert panel.preview_widget.unavailable_state.isVisible()
    assert not panel.preview_widget.locked_state.isVisible()
    assert panel.preview_widget.unavailable_state_title.text() == (
        "Signal preview unavailable"
    )
    assert "stale" in panel.preview_widget.unavailable_state_detail.text()


def test_preprocessing_history_keeps_one_height_across_states(qtbot):
    controller = MagicMock()
    panel = PreprocessPanel(controller=controller, dataset_controller=MagicMock())
    qtbot.addWidget(panel)
    history = panel.history_widget
    initial_height = history.minimumHeight()
    assert history.MAX_VISIBLE_ROWS == 7

    history.show_no_data()
    no_history_item = history.history_list.item(0)
    assert no_history_item is not None
    assert no_history_item.text() == "No preprocessing history yet."
    assert (
        history.history_list.selectionMode()
        == QAbstractItemView.SelectionMode.NoSelection
    )
    history.update_history([], False)
    empty_history_item = history.history_list.item(0)
    assert empty_history_item is not None
    assert empty_history_item.text() == (
        "No preprocessing operations have been applied yet."
    )
    history.update_history([f"Step {index}" for index in range(12)], True)
    history.show()
    qtbot.wait(0)

    assert initial_height == history.maximumHeight()
    assert history.minimumHeight() == history.maximumHeight()
    assert history.history_list.count() == 13
    epoch_lock_item = history.history_list.item(12)
    assert epoch_lock_item is not None
    assert epoch_lock_item.text() == (
        "EEG epochs created. Preprocessing is now locked."
    )
    first_hidden_item = history.history_list.item(history.MAX_VISIBLE_ROWS)
    assert first_hidden_item is not None
    first_hidden = history.history_list.visualItemRect(first_hidden_item)
    viewport = history.history_list.viewport()
    assert viewport is not None
    assert not viewport.rect().intersects(first_hidden)


def test_update_plot_only_epoched_data_shows_locked_message_without_plotting(qtbot):
    controller = MagicMock()
    dataset_controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
    )
    qtbot.addWidget(panel)
    panel.plotter.plot_sample_data = MagicMock()
    panel.preview_widget.show_locked_message = MagicMock()

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=_render_publication(PreprocessSignalState.LOCKED),
    ):
        panel.update_plot_only()

    panel.preview_widget.show_locked_message.assert_called_once_with(
        "Preprocessing locked",
    )
    panel.plotter.plot_sample_data.assert_not_called()


def test_preprocess_panel_filtering(mock_main_window, mock_controller, qtbot):
    """Filtering blocks instead of mutating the controller compatibility."""
    mock_controller.has_data.return_value = True

    # Use real window
    real_window = QMainWindow()
    cast(Any, real_window).study = mock_main_window.study
    cast(Any, real_window).refresh_panels = MagicMock()

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

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            panel.sidebar.open_filtering()

            mock_controller.apply_filter.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Filtering Blocked"
            mock_info.assert_not_called()

    real_window.close()


def test_preprocess_panel_resample(mock_main_window, mock_controller, qtbot):
    """Resampling blocks instead of mutating the controller compatibility."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    cast(Any, real_window).study = mock_main_window.study
    cast(Any, real_window).refresh_panels = MagicMock()

    panel = PreprocessPanel(parent=real_window)
    qtbot.addWidget(panel)

    with (
        patch.object(panel.plotter, "plot_sample_data"),
        patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDialog,
    ):
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_params.return_value = 256.0

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            panel.sidebar.open_resample()

            mock_controller.apply_resample.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Resampling Blocked"
            mock_info.assert_not_called()

    real_window.close()


def test_preprocess_panel_epoching(mock_main_window, mock_controller, qtbot):
    """Epoching blocks instead of mutating the controller compatibility."""
    mock_controller.has_data.return_value = True
    # Use real window
    real_window = QMainWindow()
    cast(Any, real_window).study = mock_main_window.study
    cast(Any, real_window).refresh_panels = MagicMock()

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

        with (
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            panel.sidebar.open_epoching()

            mock_controller.apply_epoching.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Create EEG Epochs Blocked"
            mock_info.assert_not_called()

    real_window.close()


def test_preprocess_panel_reset(mock_main_window, mock_controller, qtbot):
    """Reset blocks instead of mutating the controller compatibility."""
    mock_controller.has_data.return_value = True
    real_window = QMainWindow()
    cast(Any, real_window).study = mock_main_window.study

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
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
        ) as mock_warning,
        patch.object(panel.sidebar, "info_panel") as mock_info_panel,
    ):
        panel.sidebar.reset_preprocess()
        mock_controller.reset_preprocess.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Reset Blocked"
        mock_info.assert_not_called()
        # mock_info_panel.update_info.assert_called_once()  # Handled by Service now

    real_window.close()


@pytest.mark.parametrize(
    "publication",
    [
        pytest.param(None, id="missing-publication"),
        pytest.param(
            SimpleNamespace(
                effective_capabilities={},
                state=SimpleNamespace(active_dataset=None),
            ),
            id="missing-capabilities",
        ),
        pytest.param(
            SimpleNamespace(
                effective_capabilities={},
                state=SimpleNamespace(
                    active_dataset=SimpleNamespace(has_epoch_data=True),
                ),
            ),
            id="missing-capabilities-epoched-state",
        ),
    ],
)
def test_preprocess_sidebar_buttons_fail_closed_without_product_truth(
    qtbot,
    publication,
):
    from XBrainLab.backend.study import Study

    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = Study()
    controller = MagicMock()
    dataset_controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
        parent=window,
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_application_view_publication",
            return_value=publication,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.run_controller_compatibility_call",
            side_effect=AssertionError(
                "real product state must not consult controller compatibility"
            ),
        ) as compatibility_call,
    ):
        panel.sidebar.update_sidebar()

    compatibility_call.assert_not_called()
    expected = {
        panel.sidebar.btn_filter: (
            "Preprocessing availability is unavailable right now."
        ),
        panel.sidebar.btn_resample: (
            "Preprocessing availability is unavailable right now."
        ),
        panel.sidebar.btn_rereference: (
            "Preprocessing availability is unavailable right now."
        ),
        panel.sidebar.btn_normalize: (
            "Preprocessing availability is unavailable right now."
        ),
        panel.sidebar.btn_epoch: (
            "EEG epoch creation availability is unavailable right now."
        ),
        panel.sidebar.btn_reset: (
            "Reset preprocessing availability is unavailable right now."
        ),
    }
    for button, tooltip in expected.items():
        assert button.isEnabled() is False
        assert button.toolTip() == tooltip


def test_preprocess_sidebar_unavailable_truth_overrides_stale_epoch_lock(qtbot):
    from XBrainLab.backend.study import Study

    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = Study()
    panel = PreprocessPanel(
        controller=MagicMock(),
        dataset_controller=MagicMock(),
        parent=window,
    )
    qtbot.addWidget(panel)
    unavailable = "Workflow state is temporarily unavailable."
    publication = SimpleNamespace(
        usable=False,
        effective_capabilities={
            command_name: CommandCapability(
                command_name=command_name.value,
                enabled=False,
                reasons=[unavailable],
            )
            for command_name in (
                CommandName.PREPROCESS,
                CommandName.CREATE_EPOCH,
                CommandName.RESET_PREPROCESS,
            )
        },
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(has_epoch_data=True),
        ),
    )

    with patch(
        "XBrainLab.ui.panels.preprocess.sidebar.get_application_view_publication",
        return_value=publication,
    ):
        panel.sidebar.update_sidebar()

    assert panel.sidebar.btn_epoch.text() == "Create EEG Epochs"
    assert panel.sidebar.btn_epoch.toolTip() == unavailable
    assert panel.sidebar.btn_reset.toolTip() == unavailable
    assert "locked" not in panel.sidebar.btn_reset.toolTip().lower()


@pytest.mark.parametrize(
    "review_context",
    [
        pytest.param(None, id="missing-review"),
        pytest.param(
            SimpleNamespace(capability=None, publication_generation=51),
            id="missing-capability",
        ),
    ],
)
def test_preprocess_action_fails_closed_without_product_review(
    qtbot,
    review_context,
):
    from XBrainLab.backend.study import Study

    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = Study()
    controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=MagicMock(),
        parent=window,
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_command_review_context",
            return_value=review_context,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.run_controller_compatibility_call",
            side_effect=AssertionError(
                "real product actions must not consult controller compatibility"
            ),
        ) as compatibility_call,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog",
        ) as dialog,
        patch.object(QMessageBox, "warning") as warning,
    ):
        panel.sidebar.open_filtering()

    compatibility_call.assert_not_called()
    dialog.assert_not_called()
    warning.assert_called_once_with(
        panel.sidebar,
        "Filtering Blocked",
        "Preprocessing availability is unavailable right now.",
    )


def test_reset_preprocess_fails_closed_without_product_capability(qtbot):
    from XBrainLab.backend.study import Study

    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = Study()
    controller = MagicMock()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=MagicMock(),
        parent=window,
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_application_view_publication",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.run_controller_compatibility_call",
            side_effect=AssertionError(
                "real product actions must not consult controller compatibility"
            ),
        ) as compatibility_call,
        patch.object(QMessageBox, "warning") as warning,
        patch.object(QMessageBox, "question") as question,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command",
        ) as execute,
    ):
        panel.sidebar.reset_preprocess()

    compatibility_call.assert_not_called()
    question.assert_not_called()
    execute.assert_not_called()
    warning.assert_called_once_with(
        panel.sidebar,
        "Reset Blocked",
        "Reset preprocessing availability is unavailable right now.",
    )


class TestPreprocessSidebarOps:
    """Tests for preprocess sidebar operations — rereference, normalize, errors."""

    @pytest.fixture
    def setup(self, mock_main_window, mock_controller, qtbot):
        mock_controller.has_data.return_value = True
        real_window = QMainWindow()
        cast(Any, real_window).study = mock_main_window.study
        cast(Any, real_window).refresh_panels = MagicMock()
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
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            panel.sidebar.open_rereference()
            mock_ctrl.apply_rereference.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Re-reference Blocked"
            mock_info.assert_not_called()

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
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = ["Cz"]
            panel.sidebar.open_rereference()
            mock_ctrl.apply_rereference.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Re-reference Blocked"
            mock_crit.assert_not_called()

    def test_normalize_success(self, setup):
        panel, mock_ctrl, _ = setup
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information"
            ) as mock_info,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "zscore"
            panel.sidebar.open_normalize()
            mock_ctrl.apply_normalization.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Normalization Blocked"
            mock_info.assert_not_called()

    def test_normalize_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_normalization.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = "zscore"
            panel.sidebar.open_normalize()
            mock_ctrl.apply_normalization.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Normalization Blocked"
            mock_crit.assert_not_called()

    def test_filtering_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_filter.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (1.0, 40.0, 50.0)
            panel.sidebar.open_filtering()
            mock_ctrl.apply_filter.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Filtering Blocked"
            mock_crit.assert_not_called()

    def test_filtering_dialog_receives_loaded_sampling_rate(self, setup):
        panel, _mock_ctrl, _ = setup
        panel._query_preprocess_data_rows = MagicMock(
            return_value=([{"sampling_frequency": 256.0}], [])
        )
        with (
            patch.object(
                panel.sidebar,
                "_begin_preprocess_review",
                return_value=(None, True),
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog"
            ) as dialog_type,
        ):
            dialog_type.return_value.exec.return_value = False
            panel.sidebar.open_filtering()

        dialog_type.assert_called_once_with(
            panel.sidebar,
            sampling_rate_hz=256.0,
        )

    def test_filtering_dialog_uses_lowest_sampling_rate_across_loaded_data(self, setup):
        panel, _mock_ctrl, _ = setup
        panel._query_preprocess_data_rows = MagicMock(
            return_value=(
                [
                    {"sampling_frequency": 256.0},
                    {"sampling_frequency": 128.0},
                ],
                [],
            )
        )
        with (
            patch.object(
                panel.sidebar,
                "_begin_preprocess_review",
                return_value=(None, True),
            ),
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog"
            ) as dialog_type,
        ):
            dialog_type.return_value.exec.return_value = False
            panel.sidebar.open_filtering()

        dialog_type.assert_called_once_with(
            panel.sidebar,
            sampling_rate_hz=128.0,
        )

    def test_resample_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_resample.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.ResampleDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = 256.0
            panel.sidebar.open_resample()
            mock_ctrl.apply_resample.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Resampling Blocked"
            mock_crit.assert_not_called()

    def test_epoching_error(self, setup):
        panel, mock_ctrl, _ = setup
        mock_ctrl.apply_epoching.side_effect = RuntimeError("fail")
        with (
            patch.object(panel.plotter, "plot_sample_data"),
            patch("XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog") as MockDlg,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.critical"
            ) as mock_crit,
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_params.return_value = (
                (0.0, 0.1),
                ["Ev1"],
                -0.2,
                0.5,
            )
            panel.sidebar.open_epoching()
            mock_ctrl.apply_epoching.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Create EEG Epochs Blocked"
            mock_crit.assert_not_called()

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
            patch(
                "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.warning"
            ) as mock_warning,
        ):
            panel.sidebar.reset_preprocess()
            mock_ctrl.reset_preprocess.assert_not_called()
            mock_warning.assert_called_once()
            assert mock_warning.call_args.args[1] == "Reset Blocked"
            mock_crit.assert_not_called()

    def test_update_button_states_epoched(self, setup):
        panel, _, _ = setup
        panel.sidebar._update_button_states(is_epoched=True)
        assert "locked" in panel.sidebar.btn_filter.toolTip().lower()
        assert "locked" in panel.sidebar.btn_epoch.toolTip().lower()
        assert panel.sidebar.btn_epoch.text() == "EEG Epochs Created"
        assert not panel.sidebar.btn_reset.isEnabled()

    def test_update_button_states_disables_reset_without_loaded_data(self, setup):
        panel, _, _ = setup

        def capability(_widget, command_name):
            enabled = command_name not in {
                CommandName.PREPROCESS,
                CommandName.CREATE_EPOCH,
                CommandName.RESET_PREPROCESS,
            }
            return CommandCapability(
                command_name=command_name.value,
                enabled=enabled,
                reasons=[] if enabled else ["Load EEG data first."],
            )

        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_command_capability",
            side_effect=capability,
        ):
            panel.sidebar._update_button_states(is_epoched=False)

        assert not panel.sidebar.btn_reset.isEnabled()

    def test_update_sidebar_uses_publication_epoch_state_for_locked_copy(self, setup):
        panel, _, _ = setup
        disabled = CommandCapability(
            command_name=CommandName.PREPROCESS.value,
            enabled=False,
            reasons=["Preprocessing is locked after EEG epochs are created."],
        )
        publication = SimpleNamespace(
            effective_capabilities={
                CommandName.PREPROCESS: disabled,
                CommandName.CREATE_EPOCH: CommandCapability(
                    command_name=CommandName.CREATE_EPOCH.value,
                    enabled=False,
                    reasons=["Epoch data already exists."],
                ),
            },
            state=SimpleNamespace(
                active_dataset=SimpleNamespace(has_epoch_data=True),
            ),
        )

        with patch(
            "XBrainLab.ui.panels.preprocess.sidebar.get_application_view_publication",
            return_value=publication,
        ):
            panel.sidebar.update_sidebar()

        assert panel.sidebar.btn_epoch.text() == "EEG Epochs Created"
        assert not panel.sidebar.btn_reset.isEnabled()
        assert "locked" in panel.sidebar.btn_reset.toolTip().lower()

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
