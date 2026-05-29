"""Tests for ModelSummaryWindow — 39 uncovered lines."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog


class TestModelSummaryWindow:
    @pytest.fixture
    def window(self, qtbot):
        with patch("XBrainLab.ui.panels.visualization.model_summary.QMessageBox"):
            from XBrainLab.ui.panels.visualization.model_summary import (
                ModelSummaryWindow,
            )

            trainer = MagicMock()
            trainer.get_name.return_value = "Plan-0"
            w = ModelSummaryWindow(None, [trainer])
            qtbot.addWidget(w)
            yield w

    def test_creates(self, window):
        assert isinstance(window, QDialog)

    def test_has_plan_combo(self, window):
        assert window.plan_combo.count() >= 2  # "Select a plan" + "Plan-0"

    def test_on_plan_select_invalid(self, window):
        window.on_plan_select("nonexistent")
        assert window.summary_text.toPlainText() == ""

    def test_on_plan_select_success(self, window):
        trainer = window.trainer_map["Plan-0"]
        trainer.model_holder.get_model.return_value.to.return_value = MagicMock()
        import numpy as np

        trainer.dataset.get_training_data.return_value = (
            np.zeros((10, 1, 22, 256)),
            np.zeros(10),
        )
        trainer.dataset.get_epoch_data.return_value.get_model_args.return_value = {}
        trainer.option.bs = 32
        trainer.option.get_device.return_value = "cpu"
        mock_summary = MagicMock(return_value="Model Summary Text")
        mock_torchinfo = ModuleType("torchinfo")
        cast(Any, mock_torchinfo).summary = mock_summary
        with patch.dict("sys.modules", {"torchinfo": mock_torchinfo}):
            window.on_plan_select("Plan-0")
        assert "Model Summary Text" in window.summary_text.toPlainText()

    def test_on_plan_select_without_torchinfo_uses_fallback(self, window, monkeypatch):
        from torch import nn

        trainer = window.trainer_map["Plan-0"]
        trainer.model_holder.get_model.return_value = nn.Sequential(
            nn.Flatten(),
            nn.Linear(100, 2),
        )
        import numpy as np

        trainer.dataset.get_training_data.return_value = (
            np.zeros((10, 1, 100)),
            np.zeros(10),
        )
        trainer.dataset.get_epoch_data.return_value.get_model_args.return_value = {}
        trainer.option.bs = 32
        trainer.option.get_device.return_value = "cpu"
        monkeypatch.setitem(sys.modules, "torchinfo", None)

        window.on_plan_select("Plan-0")

        text = window.summary_text.toPlainText()
        assert "Model: Sequential" in text
        assert "Total parameters:" in text
        assert "Detailed layer shapes require optional dependency 'torchinfo'." in text

    def test_on_plan_select_error(self, window):
        trainer = window.trainer_map["Plan-0"]
        trainer.model_holder.get_model.side_effect = RuntimeError("model error")
        window.on_plan_select("Plan-0")
        assert "Error" in window.summary_text.toPlainText()

    def test_empty_trainers(self, qtbot):
        with patch(
            "XBrainLab.ui.panels.visualization.model_summary.QMessageBox"
        ) as mock_mb:
            from XBrainLab.ui.panels.visualization.model_summary import (
                ModelSummaryWindow,
            )

            w = ModelSummaryWindow(None, [])
            qtbot.addWidget(w)
            mock_mb.warning.assert_called_once()
