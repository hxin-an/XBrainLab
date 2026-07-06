"""Coverage tests for SaliencySettingDialog - 90 uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox


@pytest.fixture
def dialog(qtbot):
    from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
        SaliencySettingDialog,
    )

    dlg = SaliencySettingDialog(parent=None, saliency_params=None)
    qtbot.addWidget(dlg)
    return dlg


@pytest.fixture
def dialog_with_params(qtbot):
    from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
        SaliencySettingDialog,
    )

    params = {"Gradient": {"n_steps": 50}}
    dlg = SaliencySettingDialog(parent=None, saliency_params=params)
    qtbot.addWidget(dlg)
    return dlg


class TestSaliencySettingInit:
    def test_creates_dialog(self, dialog):
        assert dialog.windowTitle() == "Saliency Setting"

    def test_has_params_tables(self, dialog):
        assert isinstance(dialog.params_tables, dict)

    def test_has_method_checkboxes(self, dialog):
        checks = {
            check.text(): check
            for check in dialog.findChildren(QCheckBox)
            if check.text() in {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}
        }
        assert set(checks) == {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}
        assert all(check.isChecked() for check in checks.values())

    def test_ok_cancel_buttons_have_no_icons(self, dialog):
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        for standard in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Cancel,
        ):
            button = buttons.button(standard)
            assert button is not None
            assert button.icon().isNull()

    def test_creates_with_params(self, dialog_with_params):
        assert isinstance(dialog_with_params, QDialog)


class TestSaliencySettingMethods:
    def test_check_init_data(self, dialog):
        dialog.check_init_data()

    def test_display_data(self, dialog):
        dialog.display_data()

    def test_accept(self, dialog):
        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()
        result = dialog.get_result()
        assert result is not None
        assert result["profile"] == "advanced"
        assert set(result["methods"]) == {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}

    def test_get_result_default(self, dialog):
        result = dialog.get_result()
        # Should return saliency_params (possibly None or dict)
        assert result is None or isinstance(result, dict)
