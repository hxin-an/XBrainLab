"""Loaded-label placement step helpers for the Data Import wizard."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from XBrainLab.ui.dialogs.dataset.wizard_host_protocol import (
        DataImportWizardStepHostProtocol,
    )
else:

    class DataImportWizardStepHostProtocol:
        pass


class LabelPlacementStepMixin(DataImportWizardStepHostProtocol):
    """Render and state helpers for external label placement rules."""

    placement_method_buttons: dict[str, QRadioButton]
    placement_method_option_frames: dict[str, QFrame]
    target_event_buttons: dict[str, QCheckBox]
    target_event_option_frames: dict[str, QFrame]

    def _sync_label_placement_after_label_sources_changed(self) -> None:
        """Refresh Match Labels state after Load Labels mutates label sources."""
        if hasattr(self, "label_carrier_tree"):
            self._label_carrier_items.clear()
            self._label_target_widgets.clear()
            self._label_choice_widgets.clear()
            self._label_carrier_remap_widgets.clear()
            self.label_carrier_tree.clear()
            self._populate_label_carrier_tree()
            self._fit_label_carrier_tree_height()
        if self.event_value_editor is not None:
            self.event_value_editor.set_carrier_plans(self._event_value_carrier_plans())
        if hasattr(self, "label_pairing_rows_layout"):
            self._populate_pairing_rows()
        if hasattr(self, "label_source_mode_combo") and not self._label_carrier_items:
            self._set_combo_current_data(
                self.label_source_mode_combo,
                "internal_events",
            )
        self._refresh_event_detail_view()
        if hasattr(self, "pairing_status_label"):
            self._refresh_pairing_status()
        self._refresh_label_source_mode()

    def _build_label_values_card(self, layout: QVBoxLayout) -> None:
        self._updating_label_rule = True
        self.rule_label_field_combo = self._rule_combo(
            self._label_field_rule_choices(),
            self._common_carrier_value("selected_label_field"),
            "Choose the column, variable, or sequence that becomes the label value.",
        )
        self.rule_use_as_combo = self._rule_combo(
            self._label_use_choices(),
            self._common_carrier_value("role") or "external labels",
            "Choose how these labels will be used downstream.",
        )
        self._updating_label_rule = False

        values_grid = QGridLayout()
        values_grid.setContentsMargins(0, 0, 0, 0)
        values_grid.setHorizontalSpacing(10)
        values_grid.setVerticalSpacing(8)
        label_field_control = self._rule_control(
            "Read labels from",
            self.rule_label_field_combo,
        )
        carrier_use_control = self._rule_control(
            "Use as",
            self.rule_use_as_combo,
        )
        has_value_decisions = any(
            isinstance(plan.get("value_decisions"), dict)
            and bool(plan.get("value_decisions"))
            for plan in self._event_value_carrier_plans()
        )
        values_grid.addWidget(
            label_field_control,
            0,
            0,
            1,
            2 if has_value_decisions else 1,
        )
        if not has_value_decisions:
            values_grid.addWidget(carrier_use_control, 0, 1)
        else:
            carrier_use_control.deleteLater()
        self.label_values_status_label = QLabel(self._label_values_status_text())
        self.label_values_status_label.setObjectName("DataImportRuleStatus")
        self.label_values_status_label.setWordWrap(True)
        values_grid.addWidget(self.label_values_status_label, 1, 0, 1, 2)
        layout.addLayout(values_grid)

        for selector in (
            self.rule_label_field_combo,
            self.rule_use_as_combo,
        ):
            selector.currentIndexChanged.connect(self._apply_label_rule_to_preview)

        has_label_rows = bool(self._label_carrier_items)
        for selector in (
            self.rule_label_field_combo,
            self.rule_use_as_combo,
        ):
            selector.setEnabled(has_label_rows)

    def _build_placement_card(self, layout: QVBoxLayout) -> None:
        self._updating_label_rule = True
        placement_method = self._default_placement_method()
        self.rule_placement_method_combo = self._rule_combo(
            self._placement_method_choices(),
            placement_method,
            "Choose how label rows are positioned on the EEG timeline.",
        )
        self.rule_alignment_combo = self._rule_combo(
            self._alignment_rule_choices(placement_method),
            self._default_alignment_value(placement_method),
            "Choose the EEG event, trial order, or time field used to place labels.",
        )
        self.rule_label_unit_combo = self._rule_combo(
            self._label_unit_choices(),
            self._common_carrier_value("granularity") or "trial",
            "Choose what one label row describes.",
        )
        self.rule_duration_field_combo = self._rule_combo(
            self._duration_field_choices(),
            self._common_carrier_value("selected_duration_field"),
            "Choose a duration or end-time field for EEG epoch setup.",
        )
        self.rule_time_model_combo = self._rule_combo(
            self._time_model_choices(),
            self._default_time_model_value(placement_method),
            "Choose how to interpret actual time or sample numbers.",
        )
        for hidden_selector in (
            self.rule_placement_method_combo,
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
        ):
            hidden_selector.setVisible(False)
        self._updating_label_rule = False

        self.placement_card = QWidget()
        self.placement_card.setObjectName("DataImportPlacementControls")
        placement_layout = QVBoxLayout(self.placement_card)
        placement_layout.setContentsMargins(0, 0, 0, 0)
        placement_layout.setSpacing(10)

        placement_layout.addWidget(self._placement_method_selector())
        self.placement_detail_stack = QStackedWidget()
        self.placement_detail_stack.setObjectName("DataImportPlacementDetailStack")
        self.placement_detail_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._build_placement_detail_pages()
        placement_layout.addWidget(self.placement_detail_stack)

        self.placement_status_label = QLabel(self._placement_status_text())
        self.placement_status_label.setObjectName("DataImportRuleStatus")
        self.placement_status_label.setWordWrap(True)
        self.placement_status_label.setVisible(bool(self.placement_status_label.text()))
        placement_layout.addWidget(self.placement_status_label)
        layout.addWidget(self.placement_card)

        self.rule_placement_method_combo.currentIndexChanged.connect(
            self._handle_placement_method_change
        )
        for selector in (
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
        ):
            selector.currentIndexChanged.connect(self._apply_label_rule_to_preview)
        self.rule_time_model_combo.currentIndexChanged.connect(
            self._handle_time_model_change
        )

        has_label_rows = bool(self._label_carrier_items)
        for selector in (
            self.rule_placement_method_combo,
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
            self.rule_time_model_combo,
        ):
            selector.setEnabled(has_label_rows)
        self._sync_placement_method_buttons()
        self._sync_placement_detail_stack()

    def _build_match_check_card(self, layout: QVBoxLayout) -> None:
        self.rule_status_label = QLabel(self._label_rule_status_text())
        self.rule_status_label.setObjectName("DataImportRuleStatus")
        self.rule_status_label.setWordWrap(True)
        layout.addWidget(self.rule_status_label)

    def _label_table_fallback_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("DataImportConversionActionCard")
        card.setVisible(False)
        layout = QGridLayout(card)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(9)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        title = QLabel("XBrainLab cannot match this label file yet")
        title.setObjectName("DataImportActionIssue")
        self.label_table_fallback_reason_label = QLabel("")
        self.label_table_fallback_reason_label.setObjectName("DataImportActionText")
        self.label_table_fallback_reason_label.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(self.label_table_fallback_reason_label)
        layout.addLayout(text_layout, 0, 0, 1, 2)

        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        self.go_to_load_labels_btn = QPushButton("Go to Load Labels")
        self.go_to_load_labels_btn.setObjectName("DataImportToolButton")
        self.go_to_load_labels_btn.clicked.connect(
            lambda: self._go_to_step(self._step_titles.index("Load Labels"))
        )
        action_layout.addWidget(self.go_to_load_labels_btn)

        self.view_label_table_format_btn = QPushButton("View required format")
        self.view_label_table_format_btn.setObjectName("DataImportTertiaryButton")
        self.view_label_table_format_btn.clicked.connect(
            self._show_converted_label_table_format
        )
        action_layout.addWidget(self.view_label_table_format_btn)
        layout.addLayout(
            action_layout,
            0,
            2,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        return card

    def _refresh_label_table_fallback(self) -> None:
        if not hasattr(self, "label_table_fallback_card"):
            return
        visible = self._should_show_label_table_fallback()
        self.label_table_fallback_card.setVisible(visible)
        if visible:
            self.label_table_fallback_reason_label.setText(
                self._label_table_fallback_reason()
            )
        self._refresh_pairing_badges()

    def _should_show_label_table_fallback(self) -> bool:
        if not hasattr(self, "label_source_mode_combo"):
            return False
        if self._label_source_mode() != "loaded_label_files":
            return False
        if not self._label_carrier_items:
            return False
        return bool(self._label_table_fallback_reason())

    def _label_table_fallback_reason(self) -> str:
        if not self._label_carrier_items:
            return ""
        label_field = ""
        if hasattr(self, "rule_label_field_combo"):
            label_field = self._combo_current_data(self.rule_label_field_combo)
        if not label_field:
            return (
                "The file was loaded, but XBrainLab cannot tell which column or "
                "variable contains the labels."
            )
        alignment = ""
        if hasattr(self, "rule_alignment_combo"):
            alignment = self._combo_current_data(self.rule_alignment_combo)
        if not alignment:
            return (
                "The file was loaded, but XBrainLab cannot tell where each label "
                "belongs in the EEG."
            )
        # A blocked placement review is an editable matching decision, not an
        # unreadable file format. Keep the placement controls visible so the
        # user can select target events, timing, intervals, or event codes.
        return ""

    def _build_label_rule_card(self, layout: QVBoxLayout) -> None:
        """Compatibility wrapper for older tests and callers."""
        self._build_label_values_card(layout)
        self._build_placement_card(layout)
        self._build_match_check_card(layout)

    def _placement_method_choices(self) -> list[tuple[str, str]]:
        return [
            ("EEG event order", "eeg_event"),
            ("Label time", "time_field"),
            ("Label interval", "interval"),
            ("Label event code", "event_code"),
        ]

    def _placement_method_selector(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataImportPlacementSelector")
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        title = QLabel("Place labels by")
        title.setObjectName("DataImportRuleLabel")
        layout.addWidget(title, 0, 0, 1, 4)
        self.placement_method_buttons = {}
        self.placement_method_option_frames = {}
        group = QButtonGroup(frame)
        group.setExclusive(True)
        copy = {
            "eeg_event": "Use label rows in order across selected EEG events.",
            "time_field": "Use a time column from the label file.",
            "interval": "Use onset plus duration or end time.",
            "event_code": "Match label rows by event code values.",
        }
        current = self._combo_current_data(self.rule_placement_method_combo)
        for column, (option_title, value) in enumerate(
            self._placement_method_choices()
        ):
            option = QFrame()
            option.setObjectName("DataImportPlacementOption")
            option.setProperty("selected", value == current)
            option_layout = QVBoxLayout(option)
            option_layout.setContentsMargins(10, 8, 10, 9)
            option_layout.setSpacing(4)
            radio = QRadioButton(option_title)
            radio.setObjectName("DataImportPlacementRadio")
            radio.setChecked(value == current)
            radio.toggled.connect(
                lambda checked, method=value: (
                    self._select_placement_method(method) if checked else None
                )
            )
            group.addButton(radio)
            option_layout.addWidget(radio)
            detail = QLabel(copy[value])
            detail.setObjectName("DataImportPlacementOptionDetail")
            detail.setWordWrap(True)
            option_layout.addWidget(detail)
            layout.addWidget(option, 1, column)
            self.placement_method_buttons[value] = radio
            self.placement_method_option_frames[value] = option
        return frame

    def _build_placement_detail_pages(self) -> None:
        pages = [
            ("eeg_event", self._placement_eeg_event_order_page()),
            ("time_field", self._placement_time_field_page()),
            ("interval", self._placement_interval_page()),
            ("event_code", self._placement_event_code_page()),
        ]
        self._placement_detail_page_indexes = {}
        for index, (method, page) in enumerate(pages):
            self.placement_detail_stack.addWidget(page)
            self._placement_detail_page_indexes[method] = index

    def _placement_eeg_event_order_page(self) -> QFrame:
        page = self._placement_detail_frame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._placement_section_title(
                "Target EEG events",
                "Label rows are assigned in file order across the selected EEG events.",
            )
        )
        self.target_event_buttons = {}
        self.target_event_option_frames = {}
        self._target_event_code_selection = self._default_event_order_target_codes()
        choices = self._target_eeg_event_choices()
        if choices:
            layout.addWidget(self._target_event_header_row())
            for display, value in choices:
                layout.addWidget(self._target_event_option_row(display, value))
        else:
            layout.addWidget(
                self._empty_state(
                    "No EEG event candidates are available yet. Review labels after "
                    "the recording exposes event markers.",
                )
            )
        self.target_event_status_label = QLabel(self._target_event_status_text())
        self.target_event_status_label.setObjectName("DataImportRuleStatus")
        self.target_event_status_label.setWordWrap(True)
        layout.addWidget(self.target_event_status_label)
        return page

    def _placement_time_field_page(self) -> QFrame:
        page = self._placement_detail_frame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._placement_section_title(
                "Label time",
                "Use this when each label row has a time or sample position. "
                "If rows simply follow EEG events, use EEG event order.",
            )
        )
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        self.time_field_combo = self._rule_combo(
            self._alignment_rule_choices("time_field"),
            self._default_alignment_value("time_field"),
            "Choose the label-file time field.",
        )
        self.time_field_combo.setObjectName("DataImportTimeFieldSelector")
        self.time_field_combo.currentIndexChanged.connect(
            lambda _index, selector=self.time_field_combo: (
                self._handle_time_field_selector_change(selector)
            )
        )
        controls.addWidget(
            self._rule_control("Time column", self.time_field_combo),
            0,
            0,
        )
        controls.addWidget(
            self._rule_control("Time numbers mean", self.rule_time_model_combo),
            0,
            1,
        )
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        layout.addLayout(controls)
        layout.addWidget(self._time_field_preview_table())
        layout.addWidget(self._time_field_check_panel())
        layout.addStretch(1)
        return page

    def _time_field_preview_table(self) -> QFrame:
        table = QFrame()
        table.setObjectName("DataImportTimePreviewTable")
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(table)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Preview rows")
        title.setObjectName("DataImportSourceTitle")
        layout.addWidget(title)

        header = QFrame()
        header.setObjectName("DataImportTimePreviewHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        time_header = QLabel("Time in EEG")
        time_header.setObjectName("DataImportPairingHeaderLabel")
        time_header.setFixedWidth(150)
        label_header = QLabel("Label value")
        label_header.setObjectName("DataImportPairingHeaderLabel")
        header_layout.addWidget(time_header)
        header_layout.addWidget(label_header, stretch=1)
        layout.addWidget(header)

        self.time_field_preview_row_labels = []
        self.time_field_preview_row_widgets = []
        for _row_index in range(3):
            row = QFrame()
            row.setObjectName("DataImportTimePreviewRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 5, 9, 5)
            row_layout.setSpacing(10)
            time_label = QLabel("")
            time_label.setObjectName("DataImportTimePreviewTime")
            time_label.setFixedWidth(150)
            label_value = QLabel("")
            label_value.setObjectName("DataImportTimePreviewValue")
            label_value.setWordWrap(True)
            row_layout.addWidget(time_label)
            row_layout.addWidget(label_value, stretch=1)
            layout.addWidget(row)
            self.time_field_preview_row_widgets.append(row)
            self.time_field_preview_row_labels.append((time_label, label_value))

        self.time_field_preview_caption_label = QLabel(
            self._time_field_preview_caption_text()
        )
        self.time_field_preview_caption_label.setObjectName("DataImportSourceDetail")
        self.time_field_preview_caption_label.setWordWrap(True)
        layout.addWidget(self.time_field_preview_caption_label)

        self.time_field_preview_empty_label = QLabel(
            "Preview rows will appear after the selected time and label fields can "
            "be read."
        )
        self.time_field_preview_empty_label.setObjectName("DataImportSourceDetail")
        self.time_field_preview_empty_label.setWordWrap(True)
        layout.addWidget(self.time_field_preview_empty_label)

        self._refresh_time_field_preview_rows()
        return table

    def _time_field_check_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("DataImportTimeCheckPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(5)
        title = QLabel("Check")
        title.setObjectName("DataImportSourceTitle")
        self.time_field_check_label = QLabel(self._time_field_check_text())
        self.time_field_check_label.setObjectName("DataImportRuleStatus")
        self.time_field_check_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.time_field_check_label)
        return panel

    def _placement_interval_page(self) -> QFrame:
        page = self._placement_detail_frame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._placement_section_title(
                "Label interval",
                "Use a start field plus duration or end time from the label file.",
            )
        )
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        start_combo = self._rule_combo(
            self._alignment_rule_choices("interval"),
            self._default_alignment_value("interval"),
            "Choose the interval start field.",
        )
        duration_combo = self._rule_combo(
            self._duration_field_choices(),
            self._combo_current_data(self.rule_duration_field_combo),
            "Choose a duration or end-time field.",
        )
        start_combo.currentIndexChanged.connect(
            lambda _index, selector=start_combo: (
                self._sync_alignment_from_visible_combo(selector)
            )
        )
        duration_combo.currentIndexChanged.connect(
            lambda _index, selector=duration_combo: (
                self._sync_duration_from_visible_combo(selector)
            )
        )
        controls.addWidget(self._rule_control("Start field", start_combo), 0, 0)
        controls.addWidget(
            self._rule_control("Duration / end field", duration_combo),
            0,
            1,
        )
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        layout.addLayout(controls)
        layout.addWidget(self._interval_review_panel())
        layout.addStretch(1)
        return page

    def _placement_event_code_page(self) -> QFrame:
        page = self._placement_detail_frame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(8)
        layout.addWidget(
            self._placement_section_title(
                "Label event code",
                "Use a code field in the label file to match EEG event codes.",
            )
        )
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        code_combo = self._rule_combo(
            self._alignment_rule_choices("event_code"),
            self._default_alignment_value("event_code"),
            "Choose the label-file event code field.",
        )
        code_combo.currentIndexChanged.connect(
            lambda _index, selector=code_combo: (
                self._sync_alignment_from_visible_combo(selector)
            )
        )
        controls.addWidget(
            self._rule_control("Label event code field", code_combo),
            0,
            0,
        )
        controls.setColumnStretch(0, 1)
        layout.addLayout(controls)
        layout.addWidget(self._event_code_review_panel())
        layout.addStretch(1)
        return page

    def _interval_review_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("DataImportTimeCheckPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(6)
        title = QLabel("Interval check")
        title.setObjectName("DataImportSourceTitle")
        self.interval_check_label = QLabel(self._interval_check_text())
        self.interval_check_label.setObjectName("DataImportRuleStatus")
        self.interval_check_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(
            self._event_rules_table(
                ["Field", "Rows", "Review"],
                self._interval_review_rows(),
            )
        )
        layout.addWidget(self.interval_check_label)
        return panel

    def _event_code_review_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("DataImportTimeCheckPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(6)
        title = QLabel("Code mapping review")
        title.setObjectName("DataImportSourceTitle")
        self.event_code_check_label = QLabel(self._event_code_check_text())
        self.event_code_check_label.setObjectName("DataImportRuleStatus")
        self.event_code_check_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(
            self._event_rules_table(
                ["Label code", "Label value", "EEG events", "Review"],
                self._event_code_mapping_rows(),
            )
        )
        unlabeled_rows = self._unlabeled_eeg_event_rows()
        if unlabeled_rows:
            unlabeled_title = QLabel("EEG events not labeled")
            unlabeled_title.setObjectName("DataImportSourceTitle")
            layout.addWidget(unlabeled_title)
            layout.addWidget(
                self._event_rules_table(
                    ["Event", "Use as", "Occurrences"],
                    unlabeled_rows,
                )
            )
        layout.addWidget(self.event_code_check_label)
        return panel

    @staticmethod
    def _placement_detail_frame() -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataImportPlacementDetail")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return frame

    def _placement_section_title(self, title: str, detail: str) -> QWidget:
        block = QFrame()
        block.setObjectName("DataImportPlacementSectionTitle")
        block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportSourceDetail")
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)
        return block

    def _placement_note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportSourceDetail")
        label.setWordWrap(True)
        return label

    def _target_event_header_row(self) -> QFrame:
        header = QFrame()
        header.setObjectName("DataImportPairingHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        layout.addWidget(self._pairing_header_label("Target", 64))
        layout.addWidget(self._pairing_header_label("Event", 58))
        layout.addWidget(self._pairing_header_label("Use as"), stretch=2)
        evidence_header = self._pairing_header_label("Source evidence")
        layout.addWidget(evidence_header, stretch=3)
        self._register_match_advanced_widget(evidence_header)
        layout.addWidget(self._pairing_header_label("Occurrences", 92))
        return header

    def _target_event_option_row(self, display: str, value: str) -> QFrame:
        event = self._target_event_row(value)
        row = QFrame()
        row.setObjectName("DataImportTargetEventRow")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        selected = value in self._event_order_target_codes()
        row.setProperty("selected", selected)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)
        checkbox = QCheckBox("Use")
        checkbox.setObjectName("DataImportTargetEventCheckbox")
        checkbox.setProperty("event_code", value)
        checkbox.setChecked(selected)
        checkbox.setFixedWidth(64)
        checkbox.toggled.connect(self._handle_target_event_selection_change)
        layout.addWidget(checkbox)
        code = QLabel(value)
        code.setObjectName("DataImportTargetEventCode")
        code.setFixedWidth(58)
        layout.addWidget(code)
        meaning = QLabel(str(event.get("use_as") or event.get("reason") or display))
        meaning.setObjectName("DataImportSourceTitle")
        meaning.setWordWrap(True)
        layout.addWidget(meaning, stretch=2)
        evidence = QLabel(str(event.get("evidence") or event.get("reason") or ""))
        evidence.setObjectName("DataImportSourceDetail")
        evidence.setWordWrap(True)
        layout.addWidget(evidence, stretch=3)
        self._register_match_advanced_widget(evidence)
        count = QLabel(self._event_count_text(event) or "")
        count.setObjectName("DataImportPairingBadge")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setFixedWidth(92)
        layout.addWidget(count)
        self.target_event_buttons[value] = checkbox
        self.target_event_option_frames[value] = row
        return row

    def _default_placement_method(self) -> str:
        values = {
            str(original.get("placement_method") or "").strip()
            for _item, original in self._label_carrier_items
            if str(original.get("placement_method") or "").strip()
        }
        if len(values) == 1:
            return next(iter(values))
        time_model = self._common_carrier_value("time_model")
        granularity = self._common_carrier_value("granularity")
        if time_model in {"seconds", "relative_time", "sample_index"}:
            return "interval" if granularity == "segment" else "time_field"
        return "eeg_event"

    def _duration_field_choices(self) -> list[tuple[str, str]]:
        choices = [("No duration field", "")]
        choices.extend(
            self._carrier_choice_values(
                "selected_duration_field",
                "duration_candidates",
            )
        )
        return choices

    @staticmethod
    def _time_model_choices() -> list[tuple[str, str]]:
        return [
            ("Seconds from EEG start", "seconds"),
            ("Sample index", "sample_index"),
            ("Other relative time value", "relative_time"),
        ]

    def _default_time_model_value(self, placement_method: str) -> str:
        common = self._common_carrier_value("time_model")
        if common:
            return common
        anchor = self._default_alignment_value(placement_method)
        return self._inferred_time_model_for_anchor(anchor)

    def _label_values_status_text(self) -> str:
        if not self._label_carrier_items:
            return "No loaded label files are available."
        field_value = str(self.rule_label_field_combo.currentData() or "").strip()
        field = self.rule_label_field_combo.currentText()
        use_as = self.rule_use_as_combo.currentText()
        if not field_value:
            return "Choose the field that contains the label values."
        value_summary = self._label_value_count_summary()
        if self._is_bids_source():
            details: list[str] = []
            recommendation = self._common_label_field_recommendation(field_value)
            recommendation_text = self._bids_label_field_recommendation_text(
                recommendation
            )
            if recommendation_text:
                details.append(recommendation_text)
            if self._bids_class_names_need_review():
                details.append("Class names need review.")
            detail_text = " " + " ".join(details) if details else ""
            if value_summary:
                return (
                    f"{field}: {value_summary}. BIDS timing is saved for import "
                    f"and EEG epoch setup.{detail_text}"
                )
            return f"{field} values will be imported from BIDS events.tsv.{detail_text}"
        if value_summary:
            return (
                f"{field}: {value_summary}. Use the preview below to verify placement."
            )
        return f"{field} values will be imported as {use_as.lower()}."

    def _common_label_field_recommendation(
        self,
        selected_field: str,
    ) -> dict[str, Any]:
        recommendations: list[dict[str, Any]] = []
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            raw = original.get("label_field_recommendation")
            if not isinstance(raw, dict):
                continue
            if str(raw.get("field") or "").strip() != selected_field:
                continue
            recommendations.append(raw)
        if not recommendations:
            return {}
        first = recommendations[0]
        identity = (
            str(first.get("field") or ""),
            str(first.get("source") or ""),
            str(first.get("reason_code") or ""),
        )
        if all(
            (
                str(item.get("field") or ""),
                str(item.get("source") or ""),
                str(item.get("reason_code") or ""),
            )
            == identity
            for item in recommendations
        ):
            return first
        return {}

    @staticmethod
    def _bids_label_field_recommendation_text(
        recommendation: dict[str, Any],
    ) -> str:
        source = str(recommendation.get("source") or "").strip()
        if source == "explicit_selection":
            return "Kept from your selection or saved recipe."
        if source != "bids_multi_run_evidence":
            return ""

        reason_code = str(recommendation.get("reason_code") or "").strip()
        copy = {
            "trial_type_over_numeric_value": (
                "Recommended because Trial type contains the class names."
            ),
            "trial_type_has_task_labels": (
                "Recommended because Trial type contains the task labels."
            ),
            "trial_type_is_consistent": (
                "Recommended because Trial type is consistent across the selected runs."
            ),
            "value_is_only_supported_field": (
                "Recommended because Value is the available label field."
            ),
        }
        if reason_code == "value_has_described_classes":
            facts = recommendation.get("facts")
            selected_run_count = 0
            if isinstance(facts, dict):
                try:
                    selected_run_count = max(
                        int(facts.get("selected_run_count") or 0),
                        0,
                    )
                except (TypeError, ValueError):
                    selected_run_count = 0
            if selected_run_count:
                run_word = "run" if selected_run_count == 1 else "runs"
                return (
                    "Recommended from class descriptions across "
                    f"{selected_run_count} selected {run_word}."
                )
            return "Recommended from the BIDS class descriptions."
        return copy.get(reason_code, "Recommended from the selected BIDS data.")

    def _bids_class_names_need_review(self) -> bool:
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            if "selected_label_field_levels_available" in original:
                semantics_available = (
                    original.get("selected_label_field_levels_available") is True
                )
            else:
                semantics_available = (
                    original.get("events_json_sidecar_present") is not False
                )
            if semantics_available:
                continue
            decisions = original.get("value_decisions")
            if not isinstance(decisions, dict):
                continue
            for raw_value, raw_decision in decisions.items():
                if not isinstance(raw_decision, dict):
                    continue
                if str(raw_decision.get("decision") or "") == "resolved":
                    continue
                suggested_name = str(raw_decision.get("suggested_name") or "").strip()
                class_name = str(raw_decision.get("class_name") or "").strip()
                if not class_name and suggested_name in {"", str(raw_value).strip()}:
                    return True
        return False

    def _target_event_status_text(self) -> str:
        if not self._label_carrier_items:
            return "No loaded label files are available."
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        if placement_method != "eeg_event":
            return ""
        targets = self._event_order_target_codes()
        if targets:
            count = self._selected_target_event_count()
            count_text = f"{count} events" if count is not None else "unknown count"
            target_text = ", ".join(targets)
            return f"Target EEG events: {target_text} · {count_text}."
        return (
            "Target EEG events: choose the event set that this label sequence "
            "should follow in order."
        )

    def _placement_status_text(self) -> str:
        if not self._label_carrier_items:
            return "No loaded label files are available."
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        method = self.rule_placement_method_combo.currentText()
        target = self.rule_alignment_combo.currentText()
        if placement_method == "eeg_event":
            return "Check: " + self._eeg_event_order_check_text(
                self._matched_eeg_pair_count(),
                len(self._selected_eeg_file_names()),
                self.rule_label_field_combo.currentText(),
            )
        if placement_method == "time_field":
            return ""
        review_text = self._backend_placement_review_text(placement_method)
        if review_text:
            return review_text
        duration = str(self.rule_duration_field_combo.currentData() or "").strip()
        label_rows = self._active_label_row_count()
        label_rows_text = (
            f" · {label_rows} label rows" if label_rows is not None else ""
        )
        if placement_method == "interval":
            duration_text = (
                f"duration/end field {self.rule_duration_field_combo.currentText()}"
                if duration
                else "duration/end field needs review"
            )
            return (
                f"Check: {method} · start {target} · {duration_text}{label_rows_text}."
            )
        if placement_method == "event_code":
            return f"Check: {method} · code field {target}{label_rows_text}."
        return f"Check: {method} · time field {target}{label_rows_text}."

    def _backend_placement_review_text(self, placement_method: str) -> str:
        reviews = self._active_backend_placement_reviews(placement_method)
        if not reviews:
            return ""
        if len(reviews) == 1:
            return self._single_backend_placement_review_text(reviews[0])
        ready = sum(1 for review in reviews if review.get("status") == "ready")
        needs_review = sum(
            1 for review in reviews if review.get("status") == "needs_review"
        )
        blocked = sum(1 for review in reviews if review.get("status") == "blocked")
        parts = [f"Check: {ready}/{len(reviews)} label file(s) ready"]
        if needs_review:
            parts.append(f"{needs_review} need review")
        if blocked:
            parts.append(f"{blocked} blocked")
        return " · ".join(parts) + "."

    def _active_backend_placement_reviews(
        self,
        placement_method: str,
    ) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            raw_reviews = original.get("placement_reviews")
            review = None
            if isinstance(raw_reviews, dict):
                review = raw_reviews.get(placement_method)
            if not isinstance(review, dict):
                raw_review = original.get("placement_review")
                if (
                    isinstance(raw_review, dict)
                    and raw_review.get("method") == placement_method
                ):
                    review = raw_review
            if isinstance(review, dict):
                reviews.append(review)
        return reviews

    def _single_backend_placement_review_text(self, review: dict[str, Any]) -> str:
        method = str(review.get("method") or "").strip()
        summary = str(review.get("summary") or "").strip().rstrip(".")
        status = str(review.get("status") or "needs_review").replace("_", " ")
        if method == "time_field":
            prefix = "Check: Label time"
        elif method == "interval":
            start = str(review.get("time_field") or "").strip()
            duration = str(review.get("duration_field") or "").strip()
            fields = " + ".join(part for part in (start, duration) if part)
            prefix = (
                f"Check: Label interval · {fields}"
                if fields
                else "Check: Label interval"
            )
        elif method == "event_code":
            field = str(review.get("event_code_field") or "").strip()
            prefix = (
                f"Check: Label event code · {field}"
                if field
                else "Check: Label event code"
            )
        else:
            prefix = "Check"
        if summary:
            return f"{prefix} · {summary} · {status}."
        return f"{prefix} · {status}."

    def _time_field_review(self) -> dict[str, Any]:
        reviews = self._active_backend_placement_reviews("time_field")
        if not reviews:
            return {}
        current = self._combo_current_data(self.rule_alignment_combo)
        for review in reviews:
            if str(review.get("time_field") or "").strip() == current:
                return review
        return (
            reviews[0]
            if len(reviews) == 1
            else self._combined_time_field_review(reviews)
        )

    def _combined_time_field_review(
        self,
        reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        combined: dict[str, Any] = {"method": "time_field"}
        label_rows = [
            value
            for value in (
                self._int_value(review.get("label_rows")) for review in reviews
            )
            if value is not None
        ]
        numeric_rows = [
            value
            for value in (
                self._int_value(review.get("numeric_rows")) for review in reviews
            )
            if value is not None
        ]
        if label_rows:
            combined["label_rows"] = sum(label_rows)
        if numeric_rows:
            combined["numeric_rows"] = sum(numeric_rows)
        mins: list[float] = []
        maxes: list[float] = []
        for review in reviews:
            minimum = self._float_value(review.get("time_min"))
            maximum = self._float_value(review.get("time_max"))
            if minimum is not None:
                mins.append(minimum)
            if maximum is not None:
                maxes.append(maximum)
        if mins:
            combined["time_min"] = min(mins)
        if maxes:
            combined["time_max"] = max(maxes)
        models = {
            str(review.get("time_model") or "").strip()
            for review in reviews
            if str(review.get("time_model") or "").strip()
        }
        if len(models) == 1:
            combined["time_model"] = next(iter(models))
        return combined

    def _single_or_combined_placement_review(self, method: str) -> dict[str, Any]:
        reviews = self._active_backend_placement_reviews(method)
        if not reviews:
            return {}
        if len(reviews) == 1:
            return reviews[0]
        combined: dict[str, Any] = {"method": method}
        for key in (
            "label_rows",
            "numeric_rows",
            "duration_numeric_rows",
            "label_code_count",
            "matched_code_count",
            "missing_code_count",
            "code_mapping_count",
            "unlabeled_eeg_event_count",
        ):
            values = [
                value
                for value in (self._int_value(review.get(key)) for review in reviews)
                if value is not None
            ]
            if values:
                combined[key] = sum(values)
        missing_codes: list[str] = []
        matched_codes: list[str] = []
        seen_codes = {
            "missing_codes": set(),
            "matched_codes": set(),
        }
        for review in reviews:
            for key, target in (
                ("missing_codes", missing_codes),
                ("matched_codes", matched_codes),
            ):
                raw_values = review.get(key)
                if not isinstance(raw_values, list):
                    continue
                for value in raw_values:
                    text = str(value).strip()
                    if not text or text in seen_codes[key]:
                        continue
                    seen_codes[key].add(text)
                    target.append(text)
        if missing_codes:
            combined["missing_codes"] = missing_codes
        if matched_codes:
            combined["matched_codes"] = matched_codes
        return combined

    def _interval_review(self) -> dict[str, Any]:
        return self._single_or_combined_placement_review("interval")

    def _event_code_review(self) -> dict[str, Any]:
        return self._single_or_combined_placement_review("event_code")

    def _interval_review_rows(self) -> list[tuple[str, str, str]]:
        review = self._interval_review()
        label_rows = self._int_value(review.get("label_rows"))
        start_rows = self._int_value(review.get("numeric_rows"))
        duration_rows = self._int_value(review.get("duration_numeric_rows"))
        start_field = str(review.get("time_field") or "").strip() or (
            self._combo_current_data(self.rule_alignment_combo)
        )
        duration_field = str(review.get("duration_field") or "").strip() or (
            self._combo_current_data(self.rule_duration_field_combo)
        )
        return [
            (
                "Label rows",
                self._count_or_review(label_rows),
                "Rows that will receive class or event labels.",
            ),
            (
                "Start field",
                self._count_pair_text(start_rows, label_rows),
                start_field or "Choose an onset, start, sample, or time field.",
            ),
            (
                "Duration / end",
                self._count_pair_text(duration_rows, label_rows),
                duration_field or "Choose duration, end, offset, or stop.",
            ),
        ]

    def _interval_check_text(self) -> str:
        review = self._interval_review()
        summary = str(review.get("summary") or "").strip()
        status = str(review.get("status") or "needs_review").replace("_", " ")
        if summary:
            return (
                f"{summary.rstrip('.')} · {status}. "
                "EEG epoch setup will use this timing information."
            )
        return "Review interval start and duration/end fields before import."

    def _event_code_review_rows(self) -> list[tuple[str, str, str]]:
        review = self._event_code_review()
        field = str(review.get("event_code_field") or "").strip() or (
            self._combo_current_data(self.rule_alignment_combo)
        )
        code_count = self._int_value(review.get("label_code_count"))
        matched_count = self._int_value(review.get("matched_code_count"))
        missing_count = self._int_value(review.get("missing_code_count"))
        matched_codes = [
            str(item).strip()
            for item in review.get("matched_codes", []) or []
            if str(item).strip()
        ]
        missing_codes = [
            str(item).strip()
            for item in review.get("missing_codes", []) or []
            if str(item).strip()
        ]
        missing_count_text = (
            str(missing_count)
            if missing_count is not None
            else str(len(missing_codes))
            if missing_codes
            else "None"
        )
        return [
            (
                "Code field",
                field or "Choose field",
                "Label-file values are matched against EEG event codes.",
            ),
            (
                "Matched codes",
                self._matched_code_count_text(matched_count, code_count),
                self._list_preview(matched_codes, limit=6) or "No matched codes yet.",
            ),
            (
                "Missing codes",
                missing_count_text,
                self._list_preview(missing_codes, limit=6)
                or "Every label code is present in EEG events.",
            ),
        ]

    def _event_code_mapping_rows(self) -> Sequence[tuple[str, ...]]:
        review = self._event_code_review()
        rows = review.get("code_mappings")
        if not isinstance(rows, list) or not rows:
            return self._event_code_review_rows()
        result: list[tuple[str, ...]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("event_code") or "").strip()
            if not code:
                continue
            labels = [
                str(value).strip()
                for value in row.get("label_values", []) or []
                if str(value).strip()
            ]
            label_text = self._list_preview(labels, limit=3) or "Needs review"
            event_count = self._int_value(row.get("eeg_event_count"))
            events_text = (
                f"{event_count} events" if event_count is not None else "Not found"
            )
            result.append(
                (
                    code,
                    label_text,
                    events_text,
                    str(row.get("review") or self._mapping_status_text(row)),
                )
            )
        return result or self._event_code_review_rows()

    def _unlabeled_eeg_event_rows(self) -> list[tuple[str, ...]]:
        review = self._event_code_review()
        raw_rows = review.get("unlabeled_eeg_events")
        if isinstance(raw_rows, list) and raw_rows:
            rows: list[tuple[str, ...]] = []
            for row in raw_rows[:6]:
                if not isinstance(row, dict):
                    continue
                code = str(row.get("event_code") or "").strip()
                if not code:
                    continue
                count = self._int_value(row.get("event_count"))
                rows.append(
                    (
                        code,
                        str(row.get("use_as") or "Available EEG event"),
                        f"{count} events" if count is not None else "Needs review",
                    )
                )
            return rows

        used = {
            str(value).strip()
            for key in ("matched_codes", "missing_codes")
            for value in review.get(key, []) or []
            if str(value).strip()
        }
        result: list[tuple[str, ...]] = []
        for event in self._target_eeg_event_rows():
            code = self._internal_event_code_from_row(event)
            if not code or code in used:
                continue
            result.append(
                (
                    code,
                    str(event.get("use_as") or event.get("reason") or ""),
                    self._event_count_text(event) or "Needs review",
                )
            )
            if len(result) >= 6:
                break
        return result

    @staticmethod
    def _mapping_status_text(row: dict[str, Any]) -> str:
        status = str(row.get("status") or "needs_review")
        if status == "ready":
            return "Ready."
        if status == "blocked":
            return "Blocked."
        return "Needs review."

    def _event_code_check_text(self) -> str:
        review = self._event_code_review()
        summary = str(review.get("summary") or "").strip()
        status = str(review.get("status") or "needs_review").replace("_", " ")
        if summary:
            return f"{summary.rstrip('.')} · {status}."
        return "Review label-file code coverage against EEG event codes."

    @staticmethod
    def _count_or_review(value: int | None) -> str:
        return f"{value} rows" if value is not None else "Needs review"

    def _count_pair_text(self, value: int | None, total: int | None) -> str:
        if value is None:
            return "Needs review"
        if total is not None:
            return f"{value}/{total} rows"
        return f"{value} rows"

    @staticmethod
    def _matched_code_count_text(
        matched: int | None,
        total: int | None,
    ) -> str:
        if matched is None and total is None:
            return "Needs review"
        if total is None:
            return f"{matched or 0} matched"
        return f"{matched or 0}/{total} codes"

    def _refresh_time_field_review(self) -> None:
        if hasattr(self, "time_field_check_label"):
            self.time_field_check_label.setText(self._time_field_check_text())
        if hasattr(self, "time_field_preview_caption_label"):
            self.time_field_preview_caption_label.setText(
                self._time_field_preview_caption_text()
            )
        self._refresh_time_field_preview_rows()
        if hasattr(self, "interval_check_label"):
            self.interval_check_label.setText(self._interval_check_text())
        if hasattr(self, "event_code_check_label"):
            self.event_code_check_label.setText(self._event_code_check_text())

    def _refresh_time_field_preview_rows(self) -> None:
        if not hasattr(self, "time_field_preview_row_labels"):
            return
        rows = self._time_label_preview_rows()
        for index, (time_label, label_value) in enumerate(
            self.time_field_preview_row_labels
        ):
            visible = index < len(rows)
            row_widgets = getattr(self, "time_field_preview_row_widgets", [])
            if index < len(row_widgets):
                row_widgets[index].setVisible(visible)
            if visible:
                time_label.setText(str(rows[index].get("time") or ""))
                label_value.setText(str(rows[index].get("label") or ""))
            else:
                time_label.clear()
                label_value.clear()
            time_label.setVisible(visible)
            label_value.setVisible(visible)
        if hasattr(self, "time_field_preview_empty_label"):
            self.time_field_preview_empty_label.setVisible(not rows)
        if hasattr(self, "time_field_preview_caption_label"):
            self.time_field_preview_caption_label.setVisible(bool(rows))

    def _time_field_preview_caption_text(self) -> str:
        label_field = self._combo_current_data(self.rule_label_field_combo)
        time_field = self._combo_current_data(self.rule_alignment_combo)
        if label_field and time_field:
            return f"Showing first 3 rows from {label_field} using {time_field}."
        return "Showing first 3 matched label rows."

    def _time_field_check_text(self) -> str:
        review = self._time_field_review()
        numeric_rows = self._int_value(review.get("numeric_rows"))
        label_rows = self._int_value(review.get("label_rows"))
        parts: list[str] = []
        if numeric_rows is None:
            parts.append("Time values need review.")
        elif label_rows is not None:
            parts.append(f"{numeric_rows}/{label_rows} rows have usable time values.")
        else:
            parts.append(f"{numeric_rows} rows have usable time values.")

        start = self._float_value(review.get("time_min"))
        end = self._float_value(review.get("time_max"))
        if start is not None and end is not None:
            parts.append(
                "Range: "
                f"{self._number_text(start)} to {self._number_text(end)} "
                f"{self._time_field_unit_text()}."
            )
        else:
            parts.append("Range needs review.")
        parts.append("The EEG epoch window will be set later.")
        return " ".join(parts)

    def _time_field_unit_text(self) -> str:
        raw = ""
        if hasattr(self, "rule_time_model_combo"):
            raw = self._combo_current_data(self.rule_time_model_combo)
        if not raw:
            raw = str(self._time_field_review().get("time_model") or "").strip()
        labels = {
            "seconds": "seconds",
            "sample_index": "samples",
            "relative_time": "relative time units",
        }
        return labels.get(raw, "time units")

    def _time_label_preview_rows(self) -> list[dict[str, str]]:
        current_time_field = self._combo_current_data(self.rule_alignment_combo)
        current_label_field = self._combo_current_data(self.rule_label_field_combo)
        rows: list[dict[str, str]] = []
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            original_time_field = str(original.get("selected_anchor") or "").strip()
            original_label_field = str(
                original.get("selected_label_field") or ""
            ).strip()
            if current_time_field and original_time_field != current_time_field:
                continue
            if current_label_field and original_label_field != current_label_field:
                continue
            preview_rows = original.get("time_label_preview")
            if not isinstance(preview_rows, list):
                continue
            for row in preview_rows:
                if not isinstance(row, dict):
                    continue
                time_value = str(row.get("time") or "").strip()
                label_value = str(row.get("label") or "").strip()
                if not time_value or not label_value:
                    continue
                rows.append({"time": time_value, "label": label_value})
                if len(rows) >= 3:
                    return rows
        return rows

    @staticmethod
    def _int_value(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        text = str(value or "").strip()
        return int(text) if text.isdigit() else None

    @staticmethod
    def _float_value(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _number_text(value: float) -> str:
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"

    def _label_value_count_summary(self) -> str:
        row_count = self._active_label_row_count()
        value_counts: dict[str, int] = {}
        for _item, original in self._label_carrier_items:
            raw_counts = original.get("label_value_counts")
            if not isinstance(raw_counts, dict):
                continue
            for value, count in raw_counts.items():
                text = str(value).strip()
                if not text:
                    continue
                if isinstance(count, int):
                    value_counts[text] = value_counts.get(text, 0) + count
                    continue
                count_text = str(count or "").strip()
                if count_text.isdigit():
                    value_counts[text] = value_counts.get(text, 0) + int(count_text)
        parts: list[str] = []
        if row_count is not None:
            parts.append(f"{row_count} values")
        if value_counts:
            parts.append(f"{len(value_counts)} unique labels")
        return " across ".join(parts)

    def _refresh_label_rule_status(self) -> None:
        if hasattr(self, "label_values_status_label"):
            self.label_values_status_label.setText(self._label_values_status_text())
        if hasattr(self, "target_event_status_label"):
            self.target_event_status_label.setText(self._target_event_status_text())
        self._refresh_time_field_review()
        if hasattr(self, "placement_status_label"):
            status_text = self._placement_status_text()
            self.placement_status_label.setText(status_text)
            self.placement_status_label.setVisible(bool(status_text))
        if hasattr(self, "rule_status_label"):
            self.rule_status_label.setText(self._label_rule_status_text())
        if hasattr(self, "placement_detail_stack"):
            self._sync_placement_detail_stack()
        self._refresh_label_table_fallback()

    def _rule_control(self, label: str, selector: QComboBox) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataImportRuleControl")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 5, 8, 6)
        layout.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("DataImportRuleLabel")
        layout.addWidget(title)
        layout.addWidget(selector)
        return frame

    def _rule_combo(
        self,
        choices: list[tuple[str, str]],
        current_value: str,
        tooltip: str,
    ) -> QComboBox:
        selector = QComboBox(cast(QWidget, self))
        self._prepare_table_combo(selector)
        selector.setToolTip(tooltip)
        seen_values: set[str] = set()
        for display, value in choices:
            if value in seen_values:
                continue
            selector.addItem(display, value)
            seen_values.add(value)
        if current_value and current_value not in seen_values:
            selector.addItem(self._label_choice_display(current_value), current_value)
        current_index = selector.findData(current_value)
        if current_index >= 0:
            selector.setCurrentIndex(current_index)
        elif selector.count() > 0:
            selector.setCurrentIndex(0)
        return selector

    def _match_mode_choices(self) -> list[tuple[str, str]]:
        if not self._label_carrier_items:
            return [("Use events inside EEG files", "internal_events")]
        return [
            ("Same base name", "filename_stem"),
            ("Choose per file below", "manual"),
        ]

    def _default_match_mode(self) -> str:
        if not self._label_carrier_items:
            return "internal_events"
        has_review = any(
            self._label_carrier_item_text(item, 1) in {"", "Needs review"}
            for item, _original in self._label_carrier_items
        )
        return "manual" if has_review else "filename_stem"

    def _label_field_rule_choices(self) -> list[tuple[str, str]]:
        choices = self._carrier_choice_values(
            "selected_label_field",
            "label_candidates",
        )
        selected_fields = {
            str(original.get("selected_label_field") or "").strip()
            for item, original in self._label_carrier_items
            if not self._is_label_carrier_excluded(
                self._label_carrier_key(item, original)
            )
            and str(original.get("selected_label_field") or "").strip()
        }
        if len(selected_fields) > 1:
            return [("Mixed selections - review", ""), *choices]
        return choices or [("Needs review", "")]

    def _default_alignment_value(self, placement_method: str) -> str:
        current = self._common_carrier_value("selected_anchor")
        if placement_method == "eeg_event" and current in {"", "trial order"}:
            event_choices = self._target_eeg_event_choices()
            if event_choices:
                return event_choices[0][1]
        choices = self._alignment_rule_choices(placement_method)
        values = {value for _display, value in choices}
        if current and current in values:
            return current
        if choices:
            return choices[0][1]
        return current

    def _alignment_rule_choices(
        self,
        placement_method: str | None = None,
    ) -> list[tuple[str, str]]:
        method = placement_method or self._combo_current_data(
            self.rule_placement_method_combo
        )
        if method == "eeg_event":
            event_choices = self._target_eeg_event_choices()
            if event_choices:
                return event_choices
        candidate_key = {
            "time_field": "time_field_candidates",
            "interval": "interval_start_candidates",
            "event_code": "event_code_candidates",
        }.get(method, "anchor_candidates")
        choices = self._carrier_choice_values("selected_anchor", candidate_key)
        if "trial order" not in {value for _display, value in choices}:
            choices.append(("Trial order", "trial order"))
        if method in {"time_field", "interval", "event_code"}:
            choices = [
                (display, value) for display, value in choices if value != "trial order"
            ]
        return choices or [("Needs review", "")]

    def _handle_placement_method_change(self) -> None:
        if self._updating_label_rule:
            return
        self._refresh_alignment_choices_for_placement()
        if not self._time_model_rule_touched:
            self._sync_time_model_from_current_alignment()
        self._sync_placement_method_buttons()
        self._sync_placement_detail_stack()
        self._apply_label_rule_to_preview()

    def _select_placement_method(self, method: str) -> None:
        index = self.rule_placement_method_combo.findData(method)
        if index >= 0 and index != self.rule_placement_method_combo.currentIndex():
            self.rule_placement_method_combo.setCurrentIndex(index)
            return
        self._sync_placement_method_buttons()
        self._sync_placement_detail_stack()
        self._apply_label_rule_to_preview()

    def _sync_placement_method_buttons(self) -> None:
        method = self._combo_current_data(self.rule_placement_method_combo)
        for value, button in getattr(self, "placement_method_buttons", {}).items():
            was_blocked = button.blockSignals(True)
            button.setChecked(value == method)
            button.blockSignals(was_blocked)
        for value, frame in getattr(
            self,
            "placement_method_option_frames",
            {},
        ).items():
            frame.setProperty("selected", value == method)
            style = frame.style()
            if style is not None:
                style.unpolish(frame)
                style.polish(frame)

    def _sync_placement_detail_stack(self) -> None:
        if not hasattr(self, "placement_detail_stack"):
            return
        method = self._combo_current_data(self.rule_placement_method_combo)
        index = getattr(self, "_placement_detail_page_indexes", {}).get(method)
        if index is not None:
            self.placement_detail_stack.setCurrentIndex(index)
            page = self.placement_detail_stack.widget(index)
            if page is not None:
                self.placement_detail_stack.setFixedHeight(page.sizeHint().height())
        self._sync_target_event_buttons()

    def _select_target_event(self, target: str) -> None:
        self._target_event_selection_touched = True
        self._target_event_code_selection = [str(target).strip()] if target else []
        if self._target_event_code_selection:
            self._set_combo_current_data(
                self.rule_alignment_combo,
                self._target_event_code_selection[0],
            )
        self._sync_target_event_buttons()
        self._apply_label_rule_to_preview()

    def _handle_target_event_selection_change(self) -> None:
        self._target_event_selection_touched = True
        self._target_event_code_selection = [
            value
            for value, checkbox in getattr(self, "target_event_buttons", {}).items()
            if checkbox.isChecked()
        ]
        if self._target_event_code_selection:
            self._set_combo_current_data(
                self.rule_alignment_combo,
                self._target_event_code_selection[0],
            )
        self._sync_target_event_buttons()
        self._apply_label_rule_to_preview()

    def _sync_target_event_buttons(self) -> None:
        selected = set(self._event_order_target_codes())
        for value, button in getattr(self, "target_event_buttons", {}).items():
            was_blocked = button.blockSignals(True)
            button.setChecked(value in selected)
            button.blockSignals(was_blocked)
        for value, frame in getattr(self, "target_event_option_frames", {}).items():
            frame.setProperty("selected", value in selected)
            style = frame.style()
            if style is not None:
                style.unpolish(frame)
                style.polish(frame)

    def _sync_alignment_from_visible_combo(self, selector: QComboBox) -> None:
        value = str(selector.currentData() or "")
        self._set_combo_current_data(self.rule_alignment_combo, value)
        self._apply_label_rule_to_preview()

    def _handle_time_field_selector_change(self, selector: QComboBox) -> None:
        value = str(selector.currentData() or "")
        self._set_combo_current_data(self.rule_alignment_combo, value)
        if not self._time_model_rule_touched:
            self._sync_time_model_from_current_alignment()
        self._apply_label_rule_to_preview()

    def _handle_time_model_change(self) -> None:
        if self._updating_label_rule:
            return
        self._time_model_rule_touched = True
        self._apply_label_rule_to_preview()

    def _sync_time_model_from_current_alignment(self) -> None:
        if not hasattr(self, "rule_time_model_combo"):
            return
        value = self._inferred_time_model_for_anchor(
            self._combo_current_data(self.rule_alignment_combo)
        )
        was_blocked = self.rule_time_model_combo.blockSignals(True)
        self._set_combo_current_data(self.rule_time_model_combo, value)
        self.rule_time_model_combo.blockSignals(was_blocked)

    def _inferred_time_model_for_anchor(self, anchor: str) -> str:
        anchor = str(anchor or "").strip().lower()
        if "sample" in anchor:
            return "sample_index"
        if any(token in anchor for token in ("timestamp", "lsl")):
            return "relative_time"
        if any(token in anchor for token in ("onset", "time", "latency")):
            first_carrier = self._first_active_label_carrier_original()
            if first_carrier and not self._carrier_uses_seconds(first_carrier):
                return "relative_time"
            return "seconds"
        common = self._common_carrier_value("time_model")
        allowed = {value for _display, value in self._time_model_choices()}
        return common if common in allowed else "seconds"

    def _first_active_label_carrier_original(self) -> dict[str, Any]:
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            return original
        return {}

    def _sync_duration_from_visible_combo(self, selector: QComboBox) -> None:
        value = str(selector.currentData() or "")
        self._set_combo_current_data(self.rule_duration_field_combo, value)
        self._apply_label_rule_to_preview()

    def _refresh_alignment_choices_for_placement(self) -> None:
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        previous = self._combo_current_data(self.rule_alignment_combo)
        choices = self._alignment_rule_choices(placement_method)
        values = {value for _display, value in choices}
        current = (
            previous
            if previous in values
            else self._default_alignment_value(placement_method)
        )
        was_blocked = self.rule_alignment_combo.blockSignals(True)
        self.rule_alignment_combo.clear()
        for display, value in choices:
            self.rule_alignment_combo.addItem(display, value)
        if current and current not in values:
            self.rule_alignment_combo.addItem(
                self._label_choice_display(current),
                current,
            )
        index = self.rule_alignment_combo.findData(current)
        if index >= 0:
            self.rule_alignment_combo.setCurrentIndex(index)
        elif self.rule_alignment_combo.count() > 0:
            self.rule_alignment_combo.setCurrentIndex(0)
        self.rule_alignment_combo.blockSignals(was_blocked)

    def _carrier_choice_values(
        self,
        selected_key: str,
        candidate_key: str,
    ) -> list[tuple[str, str]]:
        values: list[str] = []
        for _item, carrier in self._label_carrier_items:
            selected = str(carrier.get(selected_key) or "").strip()
            if selected and selected not in values:
                values.append(selected)
            candidates = carrier.get(candidate_key) or []
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                text = str(candidate).strip()
                if text and text not in values:
                    values.append(text)
        return [(self._label_choice_display(value), value) for value in values]

    @staticmethod
    def _label_unit_choices() -> list[tuple[str, str]]:
        return [
            ("Trial", "trial"),
            ("Event", "event"),
            ("EEG epoch", "epoch"),
            ("Segment", "segment"),
            ("Session", "session"),
            ("Subject", "subject"),
            ("Sample", "sample"),
        ]

    @staticmethod
    def _label_use_choices() -> list[tuple[str, str]]:
        return [
            ("Class labels", "class cue labels"),
            ("External labels", "external labels"),
            ("Event markers", "trial anchors"),
            ("Responses", "response labels"),
            ("Artifacts", "artifact markers"),
            ("Ignore", "ignored markers"),
        ]

    def _common_carrier_value(self, key: str) -> str:
        values = {
            str(original.get(key) or "").strip()
            for _item, original in self._label_carrier_items
            if str(original.get(key) or "").strip()
        }
        return next(iter(values)) if len(values) == 1 else ""

    def _label_field_requires_backend_refresh(self) -> bool:
        """Return whether the selected field needs a new value preview."""
        if not self._label_rule_controls_changed or not self._label_carrier_items:
            return False
        selected = self._combo_current_data(self.rule_label_field_combo)
        if not selected:
            return False
        return any(
            selected != str(original.get("selected_label_field") or "").strip()
            for item, original in self._label_carrier_items
            if not self._is_label_carrier_excluded(
                self._label_carrier_key(item, original)
            )
        )

    def _apply_label_rule_to_preview(self) -> None:
        if self._updating_label_rule:
            return
        self._label_rule_controls_changed = True
        if not self._label_carrier_items:
            self._refresh_label_rule_status()
            self._sync_next_button_state()
            return
        for item, _original in self._label_carrier_items:
            self._apply_rule_combo_to_item(self.rule_label_field_combo, item, 2)
            self._apply_rule_combo_to_item(self.rule_alignment_combo, item, 3)
            self._apply_rule_combo_to_item(self.rule_label_unit_combo, item, 4)
            self._apply_rule_combo_to_item(self.rule_use_as_combo, item, 5)
        self._refresh_label_rule_status()
        self._sync_next_button_state()
        self._fit_label_carrier_tree_height()
        self._fit_all_tree_columns_to_viewport()

    def _apply_rule_combo_to_item(
        self,
        rule_selector: QComboBox,
        item: QTreeWidgetItem,
        column: int,
    ) -> None:
        value = rule_selector.currentData()
        if value is None:
            return
        text = str(value)
        selector = self._label_choice_widgets.get((id(item), column))
        if selector is not None:
            self._set_combo_current_data(selector, text)
            return
        item.setText(column, self._label_choice_display(text))

    def _set_combo_current_data(self, selector: QComboBox, value: str) -> None:
        index = selector.findData(value)
        if index < 0:
            selector.addItem(
                self._label_choice_display(value),
                value,
            )
            index = selector.findData(value)
        if index >= 0:
            selector.setCurrentIndex(index)

    def _label_rule_status_text(self) -> str:
        if hasattr(self, "label_source_mode_combo") and (
            self._label_source_mode() == "internal_events"
        ):
            if self._class_map_items:
                return (
                    f"Using labels inside EEG files · {len(self._class_map_items)} "
                    "class value(s) available for review."
                )
            if self._event_role_items:
                return (
                    f"Using labels inside EEG files · {len(self._event_role_items)} "
                    "EEG event choice(s) available for review."
                )
            return (
                "Using labels inside EEG files · no event candidates in this preview."
            )
        if not self._label_carrier_items:
            return (
                "No external label files are selected. Import will rely on usable "
                "events inside each EEG file, if available."
            )
        total = len(self._selected_eeg_file_names())
        matched = self._matched_eeg_pair_count()
        needs_review = max(total - matched, 0)
        field = self.rule_label_field_combo.currentText()
        alignment = self.rule_alignment_combo.currentText()
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        if placement_method == "eeg_event":
            return self._eeg_event_order_check_text(matched, total, field)
        placement = self.rule_placement_method_combo.currentText()
        use_as = self.rule_use_as_combo.currentText()
        duration = str(self.rule_duration_field_combo.currentData() or "").strip()
        duration_text = "duration saved" if duration else "duration set later"
        suffix = f"{needs_review} need review" if needs_review else "all covered"
        parts = [f"{matched}/{total} paired", field]
        if placement_method == "interval":
            placement_text = f"{placement} · start {alignment}"
            parts.extend([placement_text, use_as, duration_text])
        elif placement_method == "event_code":
            placement_text = f"{placement} · code field {alignment}"
            parts.extend([placement_text, use_as])
        else:
            placement_text = f"{placement} · time field {alignment}"
            parts.extend([placement_text, use_as])
        parts.append(suffix)
        return " · ".join(parts)

    def _eeg_event_order_check_text(
        self,
        matched_file_count: int,
        total_file_count: int,
        field: str,
    ) -> str:
        label_rows = self._active_label_row_count()
        target_count = self._selected_target_event_count()
        excluded = self._excluded_eeg_event_count()
        parts = [
            f"{matched_file_count}/{total_file_count} paired",
            f"{field}",
            "EEG event order",
        ]
        if target_count is None:
            alignment = self.rule_alignment_combo.currentText().strip()
            if alignment and alignment != "Needs review":
                parts.append(f"at {alignment}")
        if label_rows is not None:
            parts.append(f"{label_rows} label rows")
        if target_count is not None:
            parts.append(f"{target_count} selected EEG events")
        if label_rows is not None and target_count is not None:
            matched = min(label_rows, target_count)
            parts.append(f"{matched} matched")
            if target_count > label_rows:
                difference = target_count - label_rows
                event_word = "event" if difference == 1 else "events"
                verb = "has" if difference == 1 else "have"
                parts.append(f"{difference} selected EEG {event_word} {verb} no label")
            if label_rows > target_count:
                difference = label_rows - target_count
                row_word = "row" if difference == 1 else "rows"
                verb = "has" if difference == 1 else "have"
                parts.append(
                    f"{difference} label {row_word} {verb} no selected EEG event"
                )
        if excluded:
            parts.append(f"{excluded} EEG events excluded")
        if label_rows is not None and target_count is not None:
            if target_count > label_rows:
                parts.append(
                    "Uncheck extra target events or choose another label field"
                )
            elif label_rows > target_count:
                parts.append("Select more target events or check the label file")
        return " · ".join(parts)

    def _active_label_row_count(self) -> int | None:
        total = 0
        has_count = False
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if carrier_key and self._is_label_carrier_excluded(carrier_key):
                continue
            value = original.get("label_row_count")
            if isinstance(value, int) and value >= 0:
                total += value
                has_count = True
                continue
            value_text = str(value or "").strip()
            if value_text.isdigit():
                total += int(value_text)
                has_count = True
        return total if has_count else None

    def _selected_target_event_count(self) -> int | None:
        rows = [
            self._target_event_row(code) for code in self._event_order_target_codes()
        ]
        rows = [row for row in rows if row]
        if not rows:
            return None
        total = 0
        for row in rows:
            row_count = self._event_count_value(row)
            if row_count is None:
                return None
            total += row_count
        return total

    def _event_order_target_codes(self) -> list[str]:
        if self._target_event_code_selection or self._target_event_selection_touched:
            return list(self._target_event_code_selection)
        return self._default_event_order_target_codes()

    def _default_event_order_target_codes(self) -> list[str]:
        values: list[str] = []
        for _item, original in self._label_carrier_items:
            raw_values = original.get("selected_target_event_codes")
            if isinstance(raw_values, (list, tuple, set)):
                for value in raw_values:
                    text = str(value).strip()
                    if text and text not in values:
                        values.append(text)
        if values:
            return values
        original_anchor = self._common_carrier_value("selected_anchor")
        if original_anchor and original_anchor != "trial order":
            return [original_anchor]
        suggested = self._suggested_event_order_target_codes()
        if suggested:
            return suggested
        current = self._combo_current_data(self.rule_alignment_combo)
        if current and current != "trial order":
            return [current]
        return []

    def _suggested_event_order_target_codes(self) -> list[str]:
        label_rows = self._active_label_row_count()
        if label_rows is None:
            return []
        candidate_rows = [
            row
            for row in self._target_eeg_event_rows()
            if "class label" in str(row.get("use_as") or "").lower()
        ]
        candidate_codes = [
            self._internal_event_code_from_row(row)
            for row in sorted(candidate_rows, key=self._target_event_sort_key)
            if self._internal_event_code_from_row(row)
        ]
        candidate_total = sum(
            self._event_count_value(row) or 0 for row in candidate_rows
        )
        if candidate_codes and candidate_total == label_rows:
            return candidate_codes
        for row in sorted(
            self._target_eeg_event_rows(), key=self._target_event_sort_key
        ):
            if self._event_row_is_excluded(row):
                continue
            code = self._internal_event_code_from_row(row)
            if code and self._event_count_value(row) == label_rows:
                return [code]
        return []

    @staticmethod
    def _event_count_value(row: dict[str, Any]) -> int | None:
        for key in ("event_count", "total_events", "count", "total_count"):
            value = row.get(key)
            if isinstance(value, int) and value >= 0:
                return value
            value_text = str(value or "").strip()
            if value_text.isdigit():
                return int(value_text)
        return None

    @staticmethod
    def _event_row_is_excluded(row: dict[str, Any]) -> bool:
        use_as = str(row.get("use_as") or row.get("reason") or "").lower()
        return any(
            token in use_as for token in ("artifact", "boundary", "ignore", "system")
        )

    def _excluded_eeg_event_count(self) -> int:
        total = 0
        for row in self._target_eeg_event_rows():
            if not self._event_row_is_excluded(row):
                continue
            total += self._event_count_value(row) or 0
        return total
