"""Tests for UI reads of ApplicationService command capabilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import CommandName
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import get_command_capability


def test_ui_capability_helper_returns_application_policy(qtbot):
    study = Study()
    widget = QWidget()
    widget.main_window = MagicMock()
    widget.main_window.study = study
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)
    backend_capability = (
        BackendFacade(study)
        .get_capabilities()
        .get(
            CommandName.TRAIN,
        )
    )

    assert ui_capability is not None
    assert ui_capability.enabled == backend_capability.enabled
    assert ui_capability.reasons == backend_capability.reasons


def test_ui_capability_helper_ignores_mock_study(qtbot):
    widget = QWidget()
    widget.main_window = MagicMock()
    widget.main_window.study = MagicMock()
    qtbot.addWidget(widget)

    assert get_command_capability(widget, CommandName.TRAIN) is None
