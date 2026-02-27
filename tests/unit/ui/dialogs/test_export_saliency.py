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


class TestExportSaliencyCascade:
    """Full cascade flows: plan -> repeat -> method -> export."""

    def test_on_plan_change_clears_repeat(self, dialog):
        dialog.on_plan_change("Plan_0")
        count_before = dialog.repeat_combo.count()
        dialog.on_plan_change("---")
        assert dialog.repeat_combo.count() < count_before

    def test_on_repeat_change_no_combo(self, dialog):
        """When method_combo is None (shouldn't happen but guard exists)."""
        dialog.method_combo = None
        dialog.on_repeat_change("anything")  # no crash

    def test_on_repeat_change_placeholder(self, dialog):
        dialog.on_repeat_change("---")
        # method_combo should only have "---"
        assert dialog.method_combo.count() == 1

    def test_on_plan_change_no_repeat_combo(self, dialog):
        dialog.repeat_combo = None
        dialog.on_plan_change("Plan_0")  # no crash

    def test_export_no_eval_record(self, dialog):
        """Export when plan has no eval record."""
        # Use combo selection so currentText() returns correct values
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        plan_mock = dialog.real_plan_opt["Plan_0_repeat_0"]
        plan_mock.get_eval_record.return_value = None
        with patch(
            "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
        ) as mock_mb:
            dialog.on_export_clicked()
            mock_mb.warning.assert_called_once()

    def test_export_eval_record_exception(self, dialog):
        """Export when get_eval_record raises."""
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        plan_mock = dialog.real_plan_opt["Plan_0_repeat_0"]
        plan_mock.get_eval_record.side_effect = RuntimeError("boom")
        dialog.method_combo.setCurrentIndex(1)
        with patch(
            "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
        ) as mock_mb:
            dialog.on_export_clicked()
            mock_mb.warning.assert_called_once()

    def test_export_cancelled_file_dialog(self, dialog):
        """User cancels the directory picker."""
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        with patch(
            "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QFileDialog.getExistingDirectory",
            return_value="",
        ):
            dialog.on_export_clicked()  # should return early, no crash

    def test_export_write_failure(self, dialog):
        """Export when pickle.dump raises."""
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QFileDialog.getExistingDirectory",
                return_value="/tmp/export",
            ),
            patch("builtins.open", MagicMock()),
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.pickle.dump",
                side_effect=OSError("disk full"),
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
        ):
            dialog.on_export_clicked()
            mock_mb.critical.assert_called_once()

    def test_export_success_full(self, dialog):
        """Full success path with proper selections."""
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QFileDialog.getExistingDirectory",
                return_value="/tmp/out",
            ),
            patch("builtins.open", MagicMock()),
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.pickle.dump",
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
            patch.object(dialog, "accept"),
        ):
            dialog.on_export_clicked()
            mock_mb.information.assert_called_once()

    def test_on_export_no_plan_combo(self, dialog):
        """Guard: plan_combo is None."""
        dialog.plan_combo = None
        dialog.on_export_clicked()  # early return, no crash
