"""Observable Filter section states and retained user input."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog


@pytest.mark.parametrize(
    "bandpass,notch", [(True, True), (True, False), (False, True), (False, False)]
)
def test_filter_contents_follow_header_toggles(qtbot, bandpass, notch):
    dialog = FilteringDialog(None, sampling_rate_hz=250)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.notch_mode_combo.setCurrentText("Custom")
    dialog.bandpass_check.setChecked(bandpass)
    dialog.notch_check.setChecked(notch)

    labels = {label.text(): label for label in dialog.findChildren(QLabel)}
    for text in ("Frequency range", "-", "Hz"):
        assert labels[text].isEnabled() is bandpass
    assert labels["Power-line frequency"].isEnabled() is notch
    for widget, enabled in (
        (dialog.l_freq_spin, bandpass),
        (dialog.h_freq_spin, bandpass),
        (dialog.notch_mode_combo, notch),
        (dialog.notch_spin, notch),
    ):
        assert widget.isVisible()
        assert widget.isEnabled() is enabled
    for toggle, enabled in (
        (dialog.bandpass_check, bandpass),
        (dialog.notch_check, notch),
    ):
        assert toggle.isVisible() and toggle.isEnabled()
        assert toggle.text() == ("On" if enabled else "Off")
    assert dialog.ok_button.isEnabled() is (bandpass or notch)
    if bandpass or notch:
        dialog.accept()
        assert dialog.get_result() == (
            1.0 if bandpass else None,
            40.0 if bandpass else None,
            50.0 if notch else None,
        )
    else:
        assert dialog.validation_label.text() == "Enable at least one filter."
        dialog.accept()
        assert dialog.isVisible()
        assert dialog.get_result() is None


def test_keyboard_toggles_preserve_entered_filter_values(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=250)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.notch_check.click()
    dialog.notch_mode_combo.setCurrentText("Custom")
    for spin, text in (
        (dialog.l_freq_spin, "2.5"),
        (dialog.h_freq_spin, "35"),
        (dialog.notch_spin, "55"),
    ):
        spin.setFocus()
        spin.selectAll()
        qtbot.keyClicks(spin, text)
        qtbot.keyClick(spin, Qt.Key.Key_Tab)
    for toggle in (dialog.bandpass_check, dialog.notch_check):
        toggle.setFocus()
        qtbot.keyClick(toggle, Qt.Key.Key_Space)
        assert not toggle.isChecked()
        qtbot.keyClick(toggle, Qt.Key.Key_Space)
        assert toggle.isChecked()
    assert dialog.notch_mode_combo.currentText() == "Custom"
    dialog.accept()
    assert dialog.get_result() == (2.5, 35.0, 55.0)
