"""Coverage tests for SaliencySettingDialog - 90 uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QWidget,
)


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
            if check.objectName().startswith("SaliencyMethodCheck_")
        }
        assert set(checks) == {"SmoothGrad", "SmoothGrad Squared", "VarGrad"}
        assert all(check.isChecked() for check in checks.values())
        assert set(dialog.method_checks) == {
            "SmoothGrad",
            "SmoothGrad_Squared",
            "VarGrad",
        }

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
        assert buttons.button(QDialogButtonBox.StandardButton.Ok).objectName() == (
            "PrimaryConfirmButton"
        )

    def test_compute_methods_is_lightweight_checkbox_row(self, dialog):
        methods_row = dialog.findChild(QWidget, "SaliencyComputeMethodsRow")
        assert methods_row is not None
        assert dialog.findChild(QFrame, "SaliencyComputeMethodsGroup") is None
        assert "border:" not in methods_row.styleSheet()

    def test_parameter_pages_are_compact_forms_without_vertical_separators(
        self, dialog
    ):
        assert dialog.findChildren(QFrame, "SaliencyMethodParamPage") == []
        separators = [
            frame
            for frame in dialog.findChildren(QFrame)
            if frame.frameShape() == QFrame.Shape.VLine
            or "separator" in frame.objectName().lower()
            or "divider" in frame.objectName().lower()
        ]
        assert separators == []

        for editors in dialog.param_editors.values():
            widths = [editor.minimumWidth() for editor in editors.values()]
            assert 140 <= min(widths) <= 180
            assert len(set(widths)) == 1
            assert all(
                editor.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
                for editor in editors.values()
            )

        for page in dialog.method_param_pages.values():
            assert page.maximumWidth() <= 420
            layout = page.layout()
            assert isinstance(layout, QGridLayout)
            assert layout.columnCount() == 2
            assert layout.columnStretch(0) == 0
            assert layout.columnStretch(1) == 0

    def test_parameter_forms_use_product_labels_and_keep_raw_result_keys(
        self,
        dialog,
    ):
        labels = {
            label.text(): label
            for label in dialog.findChildren(QLabel, "SaliencyParamLabel")
        }
        assert set(labels) == {
            "Noise samples",
            "Samples per batch",
            "Noise standard deviation",
        }
        assert all(label.toolTip() for label in labels.values())
        for editors in dialog.param_editors.values():
            assert editors["nt_samples_batch_size"].specialValueText() == "Automatic"
            assert all(editor.toolTip() for editor in editors.values())

    def test_method_parameters_panel_is_lightweight_not_heavy_gray_block(self, dialog):
        params_panel = dialog.findChild(QWidget, "SaliencyMethodParametersPanel")
        assert params_panel is not None
        assert params_panel.maximumWidth() <= 460
        assert "background-color" not in params_panel.styleSheet()
        assert "border:" not in params_panel.styleSheet()

    def test_creates_with_params(self, dialog_with_params):
        assert isinstance(dialog_with_params, QDialog)


class TestSaliencySettingMethods:
    def test_check_init_data(self, dialog):
        dialog.check_init_data()

    def test_display_data(self, dialog):
        dialog.display_data()

    def test_method_checkboxes_drive_dynamic_parameter_tabs(self, dialog, qtbot):
        tabs = dialog.findChild(QTabWidget, "SaliencyMethodTabs")
        assert tabs is not None
        assert [tabs.tabText(index) for index in range(tabs.count())] == [
            "SmoothGrad",
            "SmoothGrad Squared",
            "VarGrad",
        ]

        dialog.method_checks["SmoothGrad"].setChecked(False)
        qtbot.wait(0)
        assert "SmoothGrad" not in [
            tabs.tabText(index) for index in range(tabs.count())
        ]
        assert dialog.param_editors["SmoothGrad"]["nt_samples"].value() == 5

        dialog.method_checks["SmoothGrad"].setChecked(True)
        qtbot.wait(0)
        assert tabs.currentWidget() is dialog.method_param_pages["SmoothGrad"]
        assert dialog.param_editors["SmoothGrad"]["nt_samples"].value() == 5

        for check in dialog.method_checks.values():
            check.setChecked(False)
        qtbot.wait(0)
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        assert not buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert not dialog.empty_state_label.isHidden()

    def test_method_switching_keeps_dialog_center_stable(self, dialog, qtbot):
        dialog.show()
        qtbot.wait(0)
        original_center = dialog.geometry().center()

        for check in dialog.method_checks.values():
            check.setChecked(False)
        qtbot.wait(0)

        updated_center = dialog.geometry().center()
        assert abs(updated_center.x() - original_center.x()) <= 1
        assert abs(updated_center.y() - original_center.y()) <= 1

    def test_empty_state_text_is_not_clipped_when_all_methods_are_unchecked(
        self,
        dialog,
        qtbot,
    ):
        for check in dialog.method_checks.values():
            check.setChecked(False)
        qtbot.wait(0)

        label = dialog.findChild(QLabel, "SaliencyEmptyState")
        assert label is not None
        assert not label.isHidden()
        assert label.wordWrap()
        assert (
            label.text()
            == "Select at least one saliency method to configure parameters."
        )
        assert label.minimumWidth() >= 360
        assert label.minimumHeight() >= 42
        assert label.sizeHint().height() <= label.minimumHeight()
        tabs = dialog.findChild(QTabWidget, "SaliencyMethodTabs")
        assert tabs is not None
        assert tabs.maximumHeight() == 0
        assert dialog.params_group.maximumHeight() <= label.minimumHeight() + 4

        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        assert ok_button is not None and not ok_button.isEnabled()
        assert cancel_button is not None and cancel_button.isEnabled()

    def test_single_selected_method_uses_direct_form_without_tabs(self, dialog, qtbot):
        for method, check in dialog.method_checks.items():
            check.setChecked(method == "SmoothGrad")
        qtbot.wait(0)

        tabs = dialog.findChild(QTabWidget, "SaliencyMethodTabs")
        assert tabs is not None
        assert tabs.count() == 0
        assert tabs.maximumHeight() == 0
        assert dialog.params_title.text() == "SmoothGrad parameters"
        assert not dialog.single_method_host.isHidden()
        assert dialog.method_param_pages["SmoothGrad"].parent() is (
            dialog.single_method_host
        )
        assert not dialog.method_param_pages["SmoothGrad"].isHidden()

        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None and ok_button.isEnabled()

    def test_multiple_selected_methods_use_dynamic_tabs(self, dialog, qtbot):
        dialog.method_checks["VarGrad"].setChecked(False)
        qtbot.wait(0)

        tabs = dialog.findChild(QTabWidget, "SaliencyMethodTabs")
        assert tabs is not None
        assert [tabs.tabText(index) for index in range(tabs.count())] == [
            "SmoothGrad",
            "SmoothGrad Squared",
        ]
        assert dialog.params_title.text() == "Method parameters"
        assert dialog.single_method_host.isHidden()

    @pytest.mark.parametrize("selected_count", [0, 1, 3])
    def test_dialog_actions_remain_inside_viewport(
        self,
        dialog,
        qtbot,
        selected_count,
    ):
        selected = set(list(dialog.method_checks)[:selected_count])
        for method, check in dialog.method_checks.items():
            check.setChecked(method in selected)
        dialog.show()
        qtbot.wait(0)

        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        button_bottom_right = buttons.mapTo(dialog, buttons.rect().bottomRight())
        assert button_bottom_right.x() <= dialog.contentsRect().right()
        assert button_bottom_right.y() <= dialog.contentsRect().bottom()
        assert buttons.geometry().top() > dialog.params_group.geometry().bottom()

    def test_accept_reads_compact_form_values(self, dialog):
        dialog.param_editors["SmoothGrad"]["nt_samples"].setValue(7)
        dialog.param_editors["SmoothGrad"]["nt_samples_batch_size"].setValue(0)
        stdevs = dialog.param_editors["SmoothGrad"]["stdevs"]
        assert isinstance(stdevs, QDoubleSpinBox)
        stdevs.setValue(0.25)

        batch_size = dialog.param_editors["SmoothGrad"]["nt_samples_batch_size"]
        assert isinstance(batch_size, QSpinBox)

        with patch("PyQt6.QtWidgets.QDialog.accept"):
            dialog.accept()

        result = dialog.get_result()
        assert result["SmoothGrad"]["nt_samples"] == 7
        assert result["SmoothGrad"]["nt_samples_batch_size"] is None
        assert result["SmoothGrad"]["stdevs"] == 0.25

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
