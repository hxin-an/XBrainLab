"""Coverage tests for ExportSaliencyDialog - 79 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QComboBox


def _make_trainer(name="Plan_0"):
    trainer = MagicMock()
    trainer.get_name.return_value = name
    plan = MagicMock()
    plan.get_name.return_value = f"{name}_repeat_0"
    plan.get_eval_record.return_value = MagicMock()
    trainer.get_plans.return_value = [plan]
    return trainer


@pytest.fixture
def dialog(qtbot):
    from XBrainLab.ui.dialogs.visualization.export_saliency_dialog import (
        ExportSaliencyDialog,
    )

    trainers = [_make_trainer("Plan_0"), _make_trainer("Plan_1")]
    dlg = ExportSaliencyDialog(parent=None, trainers=trainers)
    qtbot.addWidget(dlg)
    return dlg


class TestExportSaliencyInit:
    def test_creates_dialog(self, dialog):
        assert (
            "Export" in dialog.windowTitle() or "export" in dialog.windowTitle().lower()
        )

    def test_has_plan_combo(self, dialog):
        assert isinstance(dialog.plan_combo, QComboBox)


class TestExportSaliencyMethods:
    def test_on_plan_change(self, dialog):
        dialog.on_plan_change("Plan_0")
        assert dialog.repeat_combo.count() >= 1

    def test_on_plan_change_placeholder(self, dialog):
        dialog.on_plan_change("---")

    def test_on_repeat_change(self, dialog):
        dialog.on_plan_change("Plan_0")
        dialog.on_repeat_change("Plan_0_repeat_0")

    def test_on_export_clicked_no_selection(self, dialog):
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            dialog.on_export_clicked()

    def test_on_export_clicked_success(self, dialog):
        dialog.on_plan_change("Plan_0")
        dialog.on_repeat_change("Plan_0_repeat_0")
        # Select a saliency method
        if hasattr(dialog, "method_combo") and dialog.method_combo is not None:
            dialog.method_combo.setCurrentIndex(1)
        with (
            patch(
                "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
                return_value="/tmp/export",
            ),
            patch("builtins.open", MagicMock()),
            patch("pickle.dump"),
            patch("PyQt6.QtWidgets.QDialog.accept"),
            patch("PyQt6.QtWidgets.QMessageBox.information"),
        ):
            dialog.on_export_clicked()
