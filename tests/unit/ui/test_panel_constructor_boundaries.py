from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.study import Study
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


@contextmanager
def _constructor_patches(panel_cls: type) -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(patch.object(panel_cls, "init_ui"))
        if panel_cls is PreprocessPanel:
            stack.enter_context(
                patch("XBrainLab.ui.panels.preprocess.panel.PreviewWidget"),
            )
            stack.enter_context(
                patch("XBrainLab.ui.panels.preprocess.panel.HistoryWidget"),
            )
            stack.enter_context(
                patch("XBrainLab.ui.panels.preprocess.panel.PreprocessSidebar"),
            )
            stack.enter_context(
                patch("XBrainLab.ui.panels.preprocess.panel.PreprocessPlotter"),
            )
        yield


@pytest.mark.parametrize(
    "panel_cls",
    [DatasetPanel, PreprocessPanel, TrainingPanel, EvaluationPanel, VisualizationPanel],
)
def test_real_study_panel_constructor_requires_injected_controller(qtbot, panel_cls):
    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("real Study controller fallback is not allowed"),
    )
    main_window = QMainWindow()
    cast(Any, main_window).study = study
    qtbot.addWidget(main_window)

    with _constructor_patches(panel_cls):
        panel = panel_cls(parent=main_window)
        qtbot.addWidget(panel)

    study.get_controller.assert_not_called()
