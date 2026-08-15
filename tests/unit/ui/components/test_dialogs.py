from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QRadioButton,
)

from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.backend.load_data import Raw
from XBrainLab.ui.dialogs.dataset import ChannelSelectionDialog, SmartParserDialog
from XBrainLab.ui.dialogs.preprocess import (
    EpochingDialog,
    FilteringDialog,
    NormalizeDialog,
    RereferenceDialog,
    ResampleDialog,
)
from XBrainLab.ui.styles.theme import Theme


def _button_contains_color(button: QPushButton, color: str) -> bool:
    image = button.grab().toImage()
    expected = QColor(color)
    matching = 0
    sampled = 0
    for x in range(4, max(image.width() - 4, 4)):
        for y in range(4, max(image.height() - 4, 4)):
            sampled += 1
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - expected.red()) <= 3
                and abs(pixel.green() - expected.green()) <= 3
                and abs(pixel.blue() - expected.blue()) <= 3
            ):
                matching += 1
    return sampled > 0 and matching / sampled >= 0.2


def test_channel_selection_dialog(qtbot):
    """Test ChannelSelectionDialog initialization and selection."""
    channels = ["C3", "C4", "Cz"]

    # Mock Preprocessor
    with patch("XBrainLab.backend.preprocessor.ChannelSelection"):
        dialog = ChannelSelectionDialog(None, channels)
        qtbot.addWidget(dialog)

        # Check list items
        assert dialog.list_widget.count() == 3
        items = [dialog.list_widget.item(i).text() for i in range(3)]
        assert items == ["C3", "C4", "Cz"]

        # Test Accept
        # Select all first
        for i in range(3):
            dialog.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

        dialog.accept()
        # Should populate selected_channels
        assert dialog.selected_channels == ["C3", "C4", "Cz"]


def test_smart_parser_dialog(qtbot):
    """Test SmartParserDialog regex logic."""
    filepaths = ["/data/sub-01_ses-01_eeg.set", "/data/sub-02_ses-01_eeg.set"]
    dialog = SmartParserDialog(filepaths, None)
    qtbot.addWidget(dialog)

    # Set regex pattern manually to ensure test stability
    dialog.radio_regex.setChecked(True)
    dialog.regex_preset_combo.setCurrentIndex(0)
    # Pattern: sub-(\d+)_ses-(\d+)
    dialog.regex_input.setText(r"sub-(\d+)_ses-(\d+)")
    dialog.regex_sub_idx.setValue(1)
    dialog.regex_sess_idx.setValue(2)

    # Trigger preview (usually connected to textChanged)
    dialog.update_preview()

    assert dialog.table.rowCount() == 2

    # Row 0
    item_sub = dialog.table.item(0, 1)  # Subject
    item_ses = dialog.table.item(0, 2)  # Session
    assert item_sub.text() == "01"
    assert item_ses.text() == "01"


def test_epoching_dialog_init(qtbot):
    """
    Test EpochingDialog initialization and basic flow.
    """
    # Mock Raw object with spec to pass validation
    mock_data = MagicMock(spec=Raw)
    mock_data.get_raw_event_list.return_value = (MagicMock(), {"Event1": 1})
    mock_data.get_event_list.return_value = (MagicMock(), {"Event1": 1})
    mock_data.get_runtime_detail.return_value = {
        "source": "Labels inside EEG files",
        "placement_method": "internal_events",
        "class_map": {"Event1": "Event1", "Event2": "Event2"},
    }
    mock_data.is_raw.return_value = True

    # Patch validate_list_type to bypass strict type checking if spec
    # doesn't work perfectly
    with patch("XBrainLab.backend.preprocessor.base.validate_list_type"):
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                [mock_data],
                epoch_handoff={
                    "ready": True,
                    "supervised_ready": True,
                    "label_source": "internal_events",
                    "placement_modes": ["internal_events"],
                    "default_epoch_events": ["Event1", "Event2"],
                    "selected_event_names": ["Event1", "Event2"],
                },
            ),
        )
        qtbot.addWidget(dialog)

        # Check if event table is populated
        assert dialog.event_list.rowCount() > 0
        assert dialog.event_list.horizontalHeaderItem(0).text() == "Use"
        assert dialog.event_list.item(0, 1).text() == "Event1"

        # Verify new UI elements exist (added for epoch duration validation)
        assert isinstance(dialog.duration_label, QLabel)
        assert isinstance(dialog.warning_label, QLabel)
        assert callable(dialog.update_duration_info)

        # Select event
        dialog.event_list.item(0, 0).setCheckState(Qt.CheckState.Checked)

        # Accept
        dialog.accept()

        # Verify get_params
        params = dialog.get_params()
        # (baseline, selected_events, tmin, tmax)
        # Default baseline check is False ? Let's Assume default config or
        # check UI state
        # But we just verified get_params returns what accepts sets.

        assert params is not None
        assert params[1] == ["Event1"]
        assert isinstance(params[2], float)  # tmin
        assert isinstance(params[3], float)  # tmax


def test_epoching_dialog_baseline_and_primary_button_are_product_styled(qtbot):
    mock_data = MagicMock(spec=Raw)
    mock_data.get_event_list.return_value = (MagicMock(), {"Event1": 1})
    mock_data.is_raw.return_value = True

    dialog = EpochingDialog(
        None,
        epoch_context=build_epoching_context([mock_data]),
    )
    qtbot.addWidget(dialog)

    baseline = dialog.findChild(QPushButton, "PreprocessToggle")
    assert baseline is not None
    assert baseline.isCheckable()
    assert baseline.text() in {"On", "Off"}
    assert "QPushButton#PreprocessToggle" in dialog.styleSheet()

    create_button = dialog.findChild(QPushButton, "EpochPrimaryButton")
    assert create_button is not None
    assert create_button.text() == "Confirm"
    assert not create_button.autoDefault()
    assert not create_button.isDefault()

    title = dialog.findChild(QLabel, "EpochDialogTitle")
    assert title is not None
    assert title.text() == "Create EEG Epochs"
    assert dialog.findChild(QFrame, "EpochFooterRule") is None


def test_resample_dialog_init(qtbot):
    """Test ResampleDialog."""
    dialog = ResampleDialog(None)
    qtbot.addWidget(dialog)

    # Set value
    # Set value
    dialog.sfreq_spin.setValue(250)
    dialog.accept()

    assert dialog.get_params() == 250


def test_resample_dialog_hides_empty_native_stepper_strip(qtbot):
    dialog = ResampleDialog(None)
    qtbot.addWidget(dialog)

    assert dialog.sfreq_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert not dialog.sfreq_spin.isReadOnly()


def test_filtering_dialog_init(qtbot):
    """Test FilteringDialog."""
    dialog = FilteringDialog(None)
    qtbot.addWidget(dialog)

    # Set values
    dialog.l_freq_spin.setValue(1.0)
    dialog.h_freq_spin.setValue(40.0)
    # Check notch
    dialog.notch_check.setChecked(True)
    dialog.notch_mode_combo.setCurrentText("Custom")
    dialog.notch_spin.setValue(60.0)

    dialog.accept()
    # (l_freq, h_freq, notch_freqs)
    params = dialog.get_params()
    assert params == (1.0, 40.0, 60.0)


def test_filtering_dialog_hides_empty_native_stepper_strips(qtbot):
    dialog = FilteringDialog(None)
    qtbot.addWidget(dialog)

    for spinbox in (
        dialog.l_freq_spin,
        dialog.h_freq_spin,
        dialog.notch_spin,
    ):
        assert spinbox.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert not spinbox.isReadOnly()


def test_filtering_dialog_uses_section_toggles_and_inline_validation(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=100.0)
    qtbot.addWidget(dialog)

    assert dialog.bandpass_check.text() == "On"
    assert dialog.notch_check.text() == "Off"
    assert dialog.bandpass_title.text() == "Band-pass filter"
    assert dialog.notch_title.text() == "Notch filter"
    assert dialog.frequency_range_label.text() == "Frequency range"

    dialog.h_freq_spin.setValue(50.0)
    assert not dialog.ok_button.isEnabled()
    assert "below 50" in dialog.validation_label.text()

    dialog.h_freq_spin.setValue(40.0)
    assert dialog.ok_button.isEnabled()
    assert not dialog.validation_label.isVisibleTo(dialog)


def test_filtering_toggles_match_epoch_visual_and_interaction_contract(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=250.0)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.bandpass_check.isVisible())

    bandpass = dialog.bandpass_check
    notch = dialog.notch_check
    assert bandpass.text() == "On"
    assert notch.text() == "Off"
    assert abs(bandpass.width() - notch.width()) <= 1
    assert bandpass.height() == notch.height()
    assert bandpass.height() <= 30
    assert _button_contains_color(bandpass, Theme.BLUE_PRIMARY)
    assert not _button_contains_color(notch, Theme.BLUE_PRIMARY)

    bandpass.click()
    qtbot.waitUntil(lambda: not dialog.ok_button.isEnabled())
    assert bandpass.text() == "Off"
    assert not dialog.l_freq_spin.isEnabled()
    assert not dialog.h_freq_spin.isEnabled()
    assert not _button_contains_color(bandpass, Theme.BLUE_PRIMARY)
    assert dialog.validation_label.text() == "Enable at least one filter."

    notch.click()
    qtbot.waitUntil(lambda: dialog.ok_button.isEnabled())
    assert notch.text() == "On"
    assert dialog.notch_mode_combo.isEnabled()
    assert _button_contains_color(notch, Theme.BLUE_PRIMARY)


def test_filtering_dialog_preserves_values_when_sections_are_disabled(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=250.0)
    qtbot.addWidget(dialog)
    dialog.l_freq_spin.setValue(2.5)
    dialog.h_freq_spin.setValue(45.0)
    dialog.bandpass_check.setChecked(False)

    assert not dialog.l_freq_spin.isEnabled()
    assert not dialog.h_freq_spin.isEnabled()

    dialog.bandpass_check.setChecked(True)
    assert dialog.l_freq_spin.value() == 2.5
    assert dialog.h_freq_spin.value() == 45.0


def test_filtering_dialog_validates_and_preserves_notch_mode(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=100.0)
    qtbot.addWidget(dialog)
    dialog.notch_check.setChecked(True)
    dialog.notch_mode_combo.setCurrentText("Custom")
    dialog.notch_spin.setValue(49.0)

    assert dialog.ok_button.isEnabled()
    dialog.notch_spin.setValue(50.0)
    assert not dialog.ok_button.isEnabled()
    assert "below 50" in dialog.validation_label.text()

    dialog.notch_check.setChecked(False)
    dialog.notch_check.setChecked(True)
    assert dialog.notch_mode_combo.currentText() == "Custom"
    assert dialog.notch_spin.value() == 50.0


def test_rereference_dialog_default(qtbot):
    """Test RereferenceDialog default state (Average)."""
    dialog = RereferenceDialog(None, ["C3", "C4", "Cz"])
    qtbot.addWidget(dialog)

    assert dialog.average_radio.isChecked()
    assert [dialog.chan_list.item(index).text() for index in range(3)] == [
        "C3",
        "C4",
        "Cz",
    ]
    dialog.accept()
    assert dialog.get_params() == "average"


def test_rereference_dialog_explains_mutually_exclusive_reference_modes(qtbot):
    dialog = RereferenceDialog(None, ["C3", "C4"])
    qtbot.addWidget(dialog)

    assert isinstance(dialog.average_radio, QRadioButton)
    assert isinstance(dialog.selected_channels_radio, QRadioButton)
    assert dialog.average_radio.text() == "Average reference"
    assert dialog.selected_channels_radio.text() == "Selected reference channels"
    assert not dialog.chan_list.isEnabled()

    dialog.selected_channels_radio.setChecked(True)
    assert dialog.chan_list.isEnabled()
    assert not dialog.ok_button.isEnabled()
    dialog.chan_list.item(0).setSelected(True)
    assert dialog.ok_button.isEnabled()

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    assert all(not button.autoDefault() for button in buttons.buttons())
    assert all(not button.isDefault() for button in buttons.buttons())


def test_rereference_dialog_custom(qtbot):
    """Test RereferenceDialog custom selection."""
    dialog = RereferenceDialog(None, ["C3", "C4", "Cz"])
    qtbot.addWidget(dialog)

    dialog.selected_channels_radio.setChecked(True)
    item = dialog.chan_list.item(0)
    item.setSelected(True)

    dialog.accept()
    assert dialog.get_params() == ["C3"]


def test_normalize_dialog_init(qtbot):
    """Test NormalizeDialog."""
    dialog = NormalizeDialog(None)
    qtbot.addWidget(dialog)

    # Select Z-Score
    dialog.zscore_radio.setChecked(True)
    dialog.accept()

    assert dialog.get_params() == "z score"
    assert dialog.section_title.text() == "Normalization method"
    assert dialog.zscore_radio.isEnabled()
    assert dialog.minmax_radio.isEnabled()
    assert "QGroupBox" not in type(dialog.section_container).__name__


def test_preprocess_setting_dialogs_fit_their_visible_content(qtbot):
    """Compact setting dialogs must not distribute surplus height between rows."""
    dialogs = (
        NormalizeDialog(None),
        ResampleDialog(None),
        FilteringDialog(None, sampling_rate_hz=250.0),
        RereferenceDialog(None, ["Fz", "C3", "Cz", "C4", "Pz"]),
    )

    for dialog in dialogs:
        qtbot.addWidget(dialog)
        dialog.layout().activate()
        assert dialog.height() <= dialog.sizeHint().height() + 2


def test_filtering_validation_resize_keeps_dialog_center_stable(qtbot):
    dialog = FilteringDialog(None, sampling_rate_hz=250.0)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)
    original_center = dialog.geometry().center()

    dialog.h_freq_spin.setValue(0.0)
    qtbot.wait(0)

    updated_center = dialog.geometry().center()
    assert abs(updated_center.x() - original_center.x()) <= 1
    assert abs(updated_center.y() - original_center.y()) <= 1
