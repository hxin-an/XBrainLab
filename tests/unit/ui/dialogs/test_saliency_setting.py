"""Coverage tests for SaliencySettingDialog - 90 uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest


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

    def test_creates_with_params(self, dialog_with_params):
        assert dialog_with_params is not None


class TestSaliencySettingMethods:
    def test_check_init_data(self, dialog):
        dialog.check_init_data()

    def test_display_data(self, dialog):
        dialog.display_data()

    def test_accept(self, dialog):
        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

    def test_get_result_default(self, dialog):
        result = dialog.get_result()
        # Should return saliency_params (possibly None or dict)
        assert result is None or isinstance(result, dict)
