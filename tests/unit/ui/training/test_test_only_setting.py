"""Coverage tests for test_only_setting.py (60 miss, 0% covered)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton

from XBrainLab.ui.panels.training.test_only_setting import TestOnlySettingWindow


@pytest.fixture
def dialog(qtbot):
    dlg = TestOnlySettingWindow(parent=None)
    qtbot.addWidget(dlg)
    return dlg


class TestTestOnlySettingInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "Test Only Setting"
        assert dialog.training_option is None

    def test_has_batch_size_entry(self, dialog):
        assert isinstance(dialog.bs_entry, QLineEdit)

    def test_has_device_controls(self, dialog):
        assert isinstance(dialog.dev_btn, QPushButton)
        assert isinstance(dialog.dev_label, QLabel)

    def test_has_output_controls(self, dialog):
        assert isinstance(dialog.out_btn, QPushButton)
        assert isinstance(dialog.output_dir_label, QLabel)


class TestSetDevice:
    def test_set_device_accepted(self, dialog):
        with patch(
            "XBrainLab.ui.panels.training.test_only_setting.DeviceSettingDialog"
        ) as MockDev:
            mock_dialog = MockDev.return_value
            mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.get_result.return_value = (True, 0)
            dialog.set_device()
            assert dialog.use_cpu is True
            assert dialog.gpu_idx == 0

    def test_set_device_cancelled(self, dialog):
        with patch(
            "XBrainLab.ui.panels.training.test_only_setting.DeviceSettingDialog"
        ) as MockDev:
            mock_dialog = MockDev.return_value
            mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
            dialog.set_device()
            assert dialog.use_cpu is None


class TestSetOutputDir:
    def test_set_output_dir(self, dialog):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="/tmp/output",
        ):
            dialog.set_output_dir()
            assert dialog.output_dir == "/tmp/output"
            assert dialog.output_dir_label.text() == "/tmp/output"

    def test_set_output_dir_cancelled(self, dialog):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="",
        ):
            dialog.set_output_dir()
            assert dialog.output_dir is None


class TestConfirm:
    def test_confirm_success(self, dialog):
        dialog.bs_entry.setText("32")
        dialog.output_dir = "/tmp"
        dialog.use_cpu = True
        dialog.gpu_idx = 0
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            dialog.confirm()
            mock_accept.assert_called_once()
        result = dialog.get_result()
        assert result is not None
        assert result.bs == 32

    def test_confirm_invalid_batch(self, dialog):
        dialog.bs_entry.setText("not_a_number")
        dialog.confirm()
        # Should show warning, not crash
        assert dialog.training_option is None

    def test_confirm_default_values(self, dialog):
        dialog.bs_entry.setText("16")
        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.confirm()
        result = dialog.get_result()
        assert result is not None


class TestGetResult:
    def test_returns_none_before_confirm(self, dialog):
        assert dialog.get_result() is None
