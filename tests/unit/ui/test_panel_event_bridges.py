from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


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


def test_evaluation_panel_refreshes_on_history_cleared(qtbot):
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

        training_controller.notify("history_cleared")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_evaluation_panel_refreshes_on_config_changed(qtbot):
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

        training_controller.notify("config_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_evaluation_panel_refreshes_on_preprocess_events(qtbot):
    preprocess_controller = Observable()

    with (
        patch.object(EvaluationPanel, "init_ui"),
        patch.object(EvaluationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = EvaluationPanel(
            controller=MagicMock(),
            training_controller=Observable(),
            preprocess_controller=preprocess_controller,
        )
        qtbot.addWidget(panel)

        preprocess_controller.notify("preprocess_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_evaluation_panel_does_not_fetch_training_controller_from_real_study(qtbot):
    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("real Study training fallback is not allowed"),
    )
    controller = MagicMock()
    controller.study = study

    with patch.object(EvaluationPanel, "init_ui"):
        panel = EvaluationPanel(
            controller=controller,
            preprocess_controller=Observable(),
        )
        qtbot.addWidget(panel)

    study.get_controller.assert_not_called()


def test_evaluation_panel_requires_injected_training_controller_for_bridge(qtbot):
    legacy_study = MagicMock()
    legacy_study.get_controller.side_effect = AssertionError(
        "training bridge fallback is not allowed",
    )
    controller = MagicMock()
    controller.study = legacy_study

    with patch.object(EvaluationPanel, "init_ui"):
        panel = EvaluationPanel(
            controller=controller,
            preprocess_controller=Observable(),
        )
        qtbot.addWidget(panel)

    legacy_study.get_controller.assert_not_called()


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


def test_visualization_panel_refreshes_on_history_cleared(qtbot):
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

        training_controller.notify("history_cleared")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_visualization_panel_refreshes_on_config_changed(qtbot):
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

        training_controller.notify("config_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_visualization_panel_refreshes_on_preprocess_events(qtbot):
    preprocess_controller = Observable()

    with (
        patch.object(VisualizationPanel, "init_ui"),
        patch.object(VisualizationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = VisualizationPanel(
            controller=MagicMock(),
            training_controller=Observable(),
            preprocess_controller=preprocess_controller,
        )
        qtbot.addWidget(panel)

        preprocess_controller.notify("preprocess_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_visualization_panel_does_not_fetch_training_controller_from_real_study(qtbot):
    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("real Study training fallback is not allowed"),
    )
    controller = Observable()
    cast(Any, controller).study = study

    with patch.object(VisualizationPanel, "init_ui"):
        panel = VisualizationPanel(
            controller=controller,
            preprocess_controller=Observable(),
        )
        qtbot.addWidget(panel)

    study.get_controller.assert_not_called()


def test_visualization_panel_requires_injected_training_controller_for_bridge(qtbot):
    legacy_study = MagicMock()
    legacy_study.get_controller.side_effect = AssertionError(
        "training bridge fallback is not allowed",
    )
    controller = Observable()
    cast(Any, controller).study = legacy_study

    with patch.object(VisualizationPanel, "init_ui"):
        panel = VisualizationPanel(
            controller=controller,
            preprocess_controller=Observable(),
        )
        qtbot.addWidget(panel)

    legacy_study.get_controller.assert_not_called()


def test_visualization_panel_refreshes_on_montage_changed(qtbot):
    visualization_controller = Observable()

    with (
        patch.object(VisualizationPanel, "init_ui"),
        patch.object(VisualizationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = VisualizationPanel(
            controller=visualization_controller,
            training_controller=Observable(),
        )
        qtbot.addWidget(panel)

        visualization_controller.notify("montage_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)


def test_visualization_panel_refreshes_on_saliency_changed(qtbot):
    visualization_controller = Observable()

    with (
        patch.object(VisualizationPanel, "init_ui"),
        patch.object(VisualizationPanel, "update_panel", autospec=True) as mock_update,
    ):
        panel = VisualizationPanel(
            controller=visualization_controller,
            training_controller=Observable(),
        )
        qtbot.addWidget(panel)

        visualization_controller.notify("saliency_changed")
        qtbot.wait(50)

    mock_update.assert_called_once_with(panel)
