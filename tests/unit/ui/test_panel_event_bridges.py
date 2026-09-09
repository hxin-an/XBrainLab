from __future__ import annotations

from unittest.mock import patch

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.training.panel import TrainingPanel


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
