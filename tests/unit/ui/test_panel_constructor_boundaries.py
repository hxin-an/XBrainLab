from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel


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
    [DatasetPanel, PreprocessPanel, TrainingPanel],
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


@pytest.mark.parametrize(
    "panel_cls",
    [DatasetPanel, PreprocessPanel],
)
def test_publication_wired_panel_does_not_resolve_compatibility_controllers(
    qtbot,
    panel_cls,
):
    study = MagicMock()
    study.get_controller.side_effect = AssertionError(
        "typed product wiring must not resolve compatibility controllers",
    )
    main_window = QMainWindow()
    cast(Any, main_window).study = study
    qtbot.addWidget(main_window)

    with _constructor_patches(panel_cls):
        panel = panel_cls(parent=main_window, publication_port=Observable())
        qtbot.addWidget(panel)

    assert panel.controller is None
    if panel_cls is PreprocessPanel:
        assert panel.dataset_controller is None
    study.get_controller.assert_not_called()


def test_training_partial_typed_ports_fail_closed_without_controller_fallback(
    qtbot,
):
    controller = MagicMock()
    controller.get_formatted_history.return_value = [{"status": "stale"}]
    query_port = MagicMock()
    action_port = MagicMock()
    transient_port = Observable()

    with _constructor_patches(TrainingPanel):
        panel = TrainingPanel(
            controller=controller,
            query_port=query_port,
            publication_port=None,
            action_port=action_port,
            transient_port=transient_port,
        )
        qtbot.addWidget(panel)

    assert panel.controller is None
    assert panel.dataset_controller is None
    assert panel.preprocess_controller is None
    assert panel._history_for_render() is None
    query_port.query_training_history.assert_not_called()
    controller.get_formatted_history.assert_not_called()
