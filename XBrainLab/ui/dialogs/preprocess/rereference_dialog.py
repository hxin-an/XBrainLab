"""EEG re-reference settings dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box
from XBrainLab.ui.dialogs.preprocess.common import (
    configure_preprocess_dialog_layout,
    create_preprocess_section,
    fit_preprocess_dialog_to_content,
)


class RereferenceDialog(BaseDialog):
    """Choose average reference or one or more explicit reference channels."""

    def __init__(self, parent, channel_names: list[str]):
        if not isinstance(channel_names, list) or any(
            not isinstance(channel, str) for channel in channel_names
        ):
            raise TypeError("channel_names must be a list of strings")
        self.channel_names = list(channel_names)
        self.reref_params: str | list[str] | None = None
        self.reference_method_group: QButtonGroup
        self.average_radio: QRadioButton
        self.selected_channels_radio: QRadioButton
        self.avg_check: QRadioButton
        self.chan_list: QListWidget
        self.validation_label: QLabel
        self.ok_button: QPushButton
        self.section_title: QLabel
        self.channels_title: QLabel
        super().__init__(parent, title="Re-reference", width=460, height=420)
        fit_preprocess_dialog_to_content(self, minimum_width=460)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        configure_preprocess_dialog_layout(layout)

        method_section, self.section_title, method_layout = create_preprocess_section(
            "Reference method",
            parent=self,
        )
        self.reference_method_group = QButtonGroup(self)
        self.reference_method_group.setExclusive(True)
        self.average_radio = QRadioButton("Average reference")
        self.selected_channels_radio = QRadioButton("Selected reference channels")
        self.reference_method_group.addButton(self.average_radio)
        self.reference_method_group.addButton(self.selected_channels_radio)
        method_layout.addWidget(self.average_radio)
        method_layout.addWidget(self.selected_channels_radio)
        layout.addWidget(method_section)

        channel_section, self.channels_title, channel_layout = (
            create_preprocess_section("Reference channels", parent=self)
        )
        self.chan_list = QListWidget()
        self.chan_list.setObjectName("PreprocessReferenceChannels")
        self.chan_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.chan_list.setMinimumHeight(150)
        self.chan_list.addItems(self.channel_names)
        channel_layout.addWidget(self.chan_list)
        layout.addWidget(channel_section)

        self.validation_label = QLabel(
            "Select at least one reference channel.",
        )
        self.validation_label.setObjectName("PreprocessInlineError")
        self.validation_label.hide()
        layout.addWidget(self.validation_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if not isinstance(ok_button, QPushButton):
            raise RuntimeError("Re-reference dialog OK button is unavailable")
        self.ok_button = ok_button
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Compatibility alias retained for callers that only inspect checked state.
        self.avg_check = self.average_radio
        self.average_radio.toggled.connect(self._sync_reference_mode)
        self.selected_channels_radio.toggled.connect(self._sync_reference_mode)
        self.chan_list.itemSelectionChanged.connect(self._sync_reference_mode)
        self.average_radio.setChecked(True)
        self._sync_reference_mode()

    def toggle_avg(self, checked: bool) -> None:
        """Compatibility entry point for older callers."""
        self.average_radio.setChecked(bool(checked))
        self.selected_channels_radio.setChecked(not bool(checked))

    def _sync_reference_mode(self, *_args) -> None:
        selected_mode = self.selected_channels_radio.isChecked()
        self.chan_list.setEnabled(selected_mode)
        self.channels_title.setEnabled(selected_mode)
        valid = not selected_mode or bool(self.chan_list.selectedItems())
        self.validation_label.setVisible(selected_mode and not valid)
        self.ok_button.setEnabled(valid)
        fit_preprocess_dialog_to_content(self, minimum_width=460)

    def accept(self) -> None:
        if self.average_radio.isChecked():
            self.reref_params = "average"
            super().accept()
            return
        selected = [item.text() for item in self.chan_list.selectedItems()]
        if not selected:
            self._sync_reference_mode()
            return
        self.reref_params = selected
        super().accept()

    def get_params(self):
        return self.reref_params

    def get_result(self):
        return self.get_params()
