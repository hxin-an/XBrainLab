"""Behavior tests for ExportSaliencyDialog selection and export paths."""

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
    def test_on_plan_change_populates_repeat_options(self, dialog):
        dialog.on_plan_change("Plan_0")
        assert dialog.repeat_combo.count() >= 1

    def test_on_plan_change_placeholder_clears_repeat_options(self, dialog):
        dialog.on_plan_change("Plan_0")
        assert dialog.repeat_combo.count() > 1

        dialog.on_plan_change("---")

        assert dialog.repeat_combo.count() == 1
        assert dialog.repeat_combo.itemText(0) == "---"
        assert dialog.real_plan_opt == {}

    def test_on_repeat_change_populates_method_options(self, dialog):
        dialog.on_plan_change("Plan_0")
        dialog.on_repeat_change("Plan_0_repeat_0")

        methods = [
            dialog.method_combo.itemText(index)
            for index in range(dialog.method_combo.count())
        ]
        assert methods == [
            "---",
            "Gradient",
            "Gradient * Input",
            "SmoothGrad",
            "SmoothGrad_Squared",
            "VarGrad",
        ]

    def test_on_export_clicked_without_complete_selection_warns(self, dialog):
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
            patch.object(dialog, "accept") as mock_accept,
        ):
            dialog.on_export_clicked()
        mock_mb.warning.assert_called_once_with(
            dialog,
            "Warning",
            "Please select all options.",
        )
        mock_accept.assert_not_called()

    def test_on_export_clicked_success(self, dialog):
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QFileDialog.getExistingDirectory",
                return_value="/tmp/export",
            ),
            patch("builtins.open", MagicMock()),
            patch("pickle.dump"),
            patch.object(dialog, "accept") as mock_accept,
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
        ):
            dialog.on_export_clicked()
        mock_mb.information.assert_called_once()
        mock_accept.assert_called_once()


class TestExportSaliencyCascade:
    """Full cascade flows: plan -> repeat -> method -> export."""

    def test_on_plan_change_clears_repeat(self, dialog):
        dialog.on_plan_change("Plan_0")
        count_before = dialog.repeat_combo.count()
        dialog.on_plan_change("---")
        assert dialog.repeat_combo.count() < count_before

    def test_on_repeat_change_missing_method_combo_returns_without_side_effect(
        self, dialog
    ):
        dialog.method_combo = None

        dialog.on_repeat_change("anything")

        assert dialog.method_combo is None

    def test_on_repeat_change_placeholder(self, dialog):
        dialog.on_repeat_change("---")
        # method_combo should only have "---"
        assert dialog.method_combo.count() == 1

    def test_on_plan_change_missing_repeat_combo_preserves_existing_plan_map(
        self,
        dialog,
    ):
        existing_plan = object()
        dialog.real_plan_opt = {"existing": existing_plan}
        dialog.repeat_combo = None

        dialog.on_plan_change("Plan_0")

        assert dialog.real_plan_opt == {"existing": existing_plan}

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

    def test_export_cancelled_file_dialog_does_not_export_or_accept(self, dialog):
        dialog.plan_combo.setCurrentText("Plan_0")
        dialog.repeat_combo.setCurrentText("Plan_0_repeat_0")
        dialog.method_combo.setCurrentIndex(1)
        eval_record = MagicMock()
        dialog.real_plan_opt[
            "Plan_0_repeat_0"
        ].get_eval_record.return_value = eval_record
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QFileDialog.getExistingDirectory",
                return_value="",
            ),
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
            patch.object(dialog, "accept") as mock_accept,
        ):
            dialog.on_export_clicked()

        eval_record.export_saliency.assert_not_called()
        mock_mb.information.assert_not_called()
        mock_mb.critical.assert_not_called()
        mock_accept.assert_not_called()

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

    def test_on_export_missing_plan_combo_returns_before_warning(self, dialog):
        dialog.plan_combo = None
        with (
            patch(
                "XBrainLab.ui.dialogs.visualization.export_saliency_dialog.QMessageBox"
            ) as mock_mb,
            patch.object(dialog, "accept") as mock_accept,
        ):
            dialog.on_export_clicked()

        mock_mb.warning.assert_not_called()
        mock_accept.assert_not_called()
