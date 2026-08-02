from __future__ import annotations

from unittest.mock import MagicMock, patch

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel


def test_preprocess_panel_refreshes_once_for_successful_dataset_import(qtbot):
    preprocess_controller = Observable()
    dataset_controller = Observable()

    with (
        patch("XBrainLab.ui.panels.preprocess.panel.PreviewWidget") as mock_preview,
        patch("XBrainLab.ui.panels.preprocess.panel.HistoryWidget"),
        patch("XBrainLab.ui.panels.preprocess.panel.PreprocessSidebar"),
        patch("XBrainLab.ui.panels.preprocess.panel.PreprocessPlotter"),
        patch.object(PreprocessPanel, "init_ui"),
        patch.object(PreprocessPanel, "update_panel", autospec=True) as mock_update,
    ):
        mock_preview.return_value.request_plot_update.connect = MagicMock()

        panel = PreprocessPanel(
            controller=preprocess_controller,
            dataset_controller=dataset_controller,
        )
        qtbot.addWidget(panel)

        dataset_controller.notify("data_changed")
        qtbot.wait(50)
        dataset_controller.notify("import_finished", 1, [])
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_preprocess_panel_observer_events_use_refresh_coordinator(qtbot):
    preprocess_controller = Observable()
    dataset_controller = Observable()

    with (
        patch("XBrainLab.ui.panels.preprocess.panel.PreviewWidget") as mock_preview,
        patch("XBrainLab.ui.panels.preprocess.panel.HistoryWidget"),
        patch("XBrainLab.ui.panels.preprocess.panel.PreprocessSidebar"),
        patch("XBrainLab.ui.panels.preprocess.panel.PreprocessPlotter"),
        patch.object(PreprocessPanel, "init_ui"),
        patch.object(
            PreprocessPanel,
            "refresh_from_observer",
            autospec=True,
        ) as mock_refresh,
    ):
        mock_preview.return_value.request_plot_update.connect = MagicMock()

        panel = PreprocessPanel(
            controller=preprocess_controller,
            dataset_controller=dataset_controller,
        )
        qtbot.addWidget(panel)

        dataset_controller.notify("data_changed")
        qtbot.wait(50)

    mock_refresh.assert_called_once_with(panel, event_name="data_changed")


def test_training_panel_refreshes_once_for_successful_dataset_import(qtbot):
    training_controller = Observable()
    dataset_controller = Observable()

    with (
        patch.object(TrainingPanel, "init_ui"),
        patch.object(TrainingPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = TrainingPanel(
            controller=training_controller,
            dataset_controller=dataset_controller,
        )
        qtbot.addWidget(panel)

        dataset_controller.notify("data_changed")
        qtbot.wait(50)
        dataset_controller.notify("import_finished", 1, [])
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_training_panel_refreshes_on_preprocess_events(qtbot):
    training_controller = Observable()
    preprocess_controller = Observable()

    with (
        patch.object(TrainingPanel, "init_ui"),
        patch.object(TrainingPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = TrainingPanel(
            controller=training_controller,
            dataset_controller=Observable(),
            preprocess_controller=preprocess_controller,
        )
        qtbot.addWidget(panel)

        preprocess_controller.notify("preprocess_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)
