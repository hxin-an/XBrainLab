from __future__ import annotations

from unittest.mock import MagicMock, patch

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


def test_preprocess_panel_refreshes_on_dataset_events(qtbot):
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
        dataset_controller.notify("import_finished")
        qtbot.wait(50)

    assert mock_update.call_count == 2
    mock_update.assert_any_call(panel)


def test_training_panel_refreshes_on_dataset_events(qtbot):
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
        dataset_controller.notify("import_finished")
        qtbot.wait(50)

    assert mock_update.call_count == 2
    mock_update.assert_any_call(panel)


def test_evaluation_panel_refreshes_on_training_stopped(qtbot):
    training_controller = Observable()

    with (
        patch.object(EvaluationPanel, "init_ui"),
        patch.object(EvaluationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = EvaluationPanel(
            controller=MagicMock(),
            training_controller=training_controller,
        )
        qtbot.addWidget(panel)

        training_controller.notify("training_stopped")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_visualization_panel_refreshes_on_training_stopped(qtbot):
    training_controller = Observable()

    with (
        patch.object(VisualizationPanel, "init_ui"),
        patch.object(VisualizationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = VisualizationPanel(
            controller=MagicMock(),
            training_controller=training_controller,
        )
        qtbot.addWidget(panel)

        training_controller.notify("training_stopped")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)
