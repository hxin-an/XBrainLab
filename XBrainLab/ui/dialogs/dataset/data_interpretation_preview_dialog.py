"""Preview dialog for Data Interpretation import decisions."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPalette, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.dataset.smart_parser_dialog import SmartParserDialog
from XBrainLab.ui.styles.theme import Theme
from XBrainLab.ui.table_sizing import scaled_column_widths


class _CurrentStepStackedWidget(QStackedWidget):
    """Stacked widget whose scroll size follows only the visible step."""

    def sizeHint(self) -> QSize:  # noqa: N802
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()
        return current.minimumSizeHint()


class _StepScrollArea(QScrollArea):
    """Scroll area that ignores wheel input when the current step fits."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            scrollbar = self.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(0)
            event.accept()
            return
        super().wheelEvent(event)


class _ConvertedLabelTableDialog(BaseDialog):
    """Explain the converted label table format."""

    def __init__(self, parent=None):
        self.close_button: QPushButton
        super().__init__(
            parent=parent,
            title="Load Converted Label Table",
            width=760,
            height=660,
        )

    def init_ui(self) -> None:
        self.setObjectName("DataImportConvertedLabelDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("DataImportPanelHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title = QLabel("XBrainLab label table")
        title.setObjectName("DataImportPanelTitle")
        detail = QLabel(
            "Create this CSV/TSV when XBrainLab can load a label file but cannot "
            "tell which values are labels or where they belong in the EEG."
        )
        detail.setObjectName("DataImportPanelSubtitle")
        detail.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(detail)
        layout.addWidget(header)

        structure_title = QLabel("Required structure")
        structure_title.setObjectName("DataImportSourceTitle")
        layout.addWidget(structure_title)

        structure_layout = QGridLayout()
        structure_layout.setContentsMargins(0, 0, 0, 0)
        structure_layout.setHorizontalSpacing(10)
        structure_layout.setVerticalSpacing(10)
        structure_layout.addWidget(
            self._label_table_requirement_card(
                "1",
                "One row per label",
                "Each row describes one trial, event, sample, or interval.",
            ),
            0,
            0,
        )
        structure_layout.addWidget(
            self._label_table_requirement_card(
                "2",
                "Column named label",
                "This is the class or target value used for training.",
            ),
            0,
            1,
        )
        structure_layout.addWidget(
            self._label_table_requirement_card(
                "3",
                "One placement column",
                "This tells XBrainLab where the label belongs in the EEG.",
            ),
            0,
            2,
        )
        layout.addLayout(structure_layout)

        placement_title = QLabel("Choose the placement that matches your file")
        placement_title.setObjectName("DataImportSourceTitle")
        layout.addWidget(placement_title)

        placement_grid = QGridLayout()
        placement_grid.setContentsMargins(0, 0, 0, 0)
        placement_grid.setHorizontalSpacing(10)
        placement_grid.setVerticalSpacing(10)
        placement_grid.addWidget(
            self._label_table_alignment_tile(
                "EEG event code",
                "event_code,label",
                "Use when label rows refer to event codes in the EEG file.",
            ),
            0,
            0,
        )
        placement_grid.addWidget(
            self._label_table_alignment_tile(
                "Timestamp",
                "onset_seconds,label",
                "Use when labels have event start times in seconds.",
            ),
            0,
            1,
        )
        placement_grid.addWidget(
            self._label_table_alignment_tile(
                "Sample index",
                "sample,label",
                "Use when labels point to EEG sample numbers.",
            ),
            1,
            0,
        )
        placement_grid.addWidget(
            self._label_table_alignment_tile(
                "Interval",
                "onset_seconds,duration_seconds,label",
                "Use when labels cover a time range.",
            ),
            1,
            1,
        )
        layout.addLayout(placement_grid)

        example_layout = QGridLayout()
        example_layout.setContentsMargins(0, 0, 0, 0)
        example_layout.setHorizontalSpacing(10)
        example_layout.setVerticalSpacing(10)
        example_layout.addWidget(
            self._label_table_example_card(
                "Example: labels follow EEG event codes",
                "event_code,label\n769,left_hand\n770,right_hand",
            ),
            0,
            0,
        )
        example_layout.addWidget(
            self._label_table_example_card(
                "Example: labels have timestamps",
                "onset_seconds,label\n12.50,left_hand\n16.00,right_hand",
            ),
            0,
            1,
        )
        layout.addLayout(example_layout)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("DataImportPrimaryButton")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

    def get_result(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def _label_table_requirement_card(
        number: str,
        title: str,
        detail: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("DataImportFormatRequirement")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(9)
        number_label = QLabel(number)
        number_label.setObjectName("DataImportStepNumber")
        number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number_label.setFixedSize(24, 24)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportSourceDetail")
        detail_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(detail_label)
        layout.addWidget(number_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, stretch=1)
        return card

    @staticmethod
    def _label_table_alignment_tile(title: str, columns: str, detail: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName("DataImportFormatTile")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        columns_label = QLabel(columns)
        columns_label.setObjectName("DataImportCodeInline")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportSourceDetail")
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(columns_label)
        layout.addWidget(detail_label)
        return tile

    @staticmethod
    def _label_table_example_card(title: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("DataImportCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        body_label = QLabel(body)
        body_label.setObjectName("DataImportCodeBlock")
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        return card


class DataInterpretationPreviewDialog(BaseDialog):
    """Show scan, metadata, warning, and validation details before apply."""

    def __init__(
        self,
        parent=None,
        scan_result: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
        validation_decision: dict[str, Any] | None = None,
    ):
        self.scan_result = dict(scan_result or {})
        self.preview = dict(preview or {})
        self.validation_decision = dict(validation_decision or {})
        self.workflow_steps_label: QLabel
        self.step_labels: list[QLabel]
        self.summary_label: QLabel
        self.source_summary_label: QLabel
        self.decision_label: QLabel
        self.confirmation_label: QLabel
        self.label_sources_label: QLabel
        self.label_source_rows_widget: QWidget
        self.label_source_rows_layout: QVBoxLayout
        self.add_label_file_btn: QPushButton
        self.add_label_folder_btn: QPushButton
        self.skip_labels_btn: QPushButton
        self.smart_parse_btn: QPushButton
        self.label_source_mode_combo: QComboBox
        self.label_source_status_label: QLabel
        self.label_match_mode_combo: QComboBox
        self.internal_event_card: QFrame
        self.internal_event_status_label: QLabel
        self.pairing_card: QFrame
        self.label_values_card: QFrame
        self.placement_card: QFrame
        self.label_table_fallback_card: QFrame
        self.label_table_fallback_reason_label: QLabel
        self.view_label_table_format_btn: QPushButton
        self.match_check_card: QFrame
        self.pairing_status_label: QLabel
        self.label_pairing_rows_widget: QWidget
        self.label_pairing_rows_layout: QVBoxLayout
        self.rule_label_field_combo: QComboBox
        self.rule_alignment_combo: QComboBox
        self.rule_placement_method_combo: QComboBox
        self.rule_duration_field_combo: QComboBox
        self.rule_label_unit_combo: QComboBox
        self.rule_use_as_combo: QComboBox
        self.label_values_status_label: QLabel
        self.target_event_status_label: QLabel
        self.placement_status_label: QLabel
        self.rule_status_label: QLabel
        self.placement_detail_stack: QStackedWidget
        self.placement_method_buttons: dict[str, QRadioButton]
        self.placement_method_option_frames: dict[str, QFrame]
        self.target_event_buttons: dict[str, QCheckBox]
        self.target_event_option_frames: dict[str, QFrame]
        self.class_map_rows_widget: QWidget | None = None
        self.save_recipe_check: QCheckBox
        self.file_tree: QTreeWidget
        self.label_carrier_tree: QTreeWidget
        self.event_group: QGroupBox
        self.event_tree: QTreeWidget
        self.review_tree: QTreeWidget
        self.review_actions_panel: QWidget
        self.review_actions_layout: QVBoxLayout
        self.event_layout: QVBoxLayout
        self.scroll_area: QScrollArea
        self.step_stack: QStackedWidget
        self.button_box: QDialogButtonBox
        self.back_button: QPushButton
        self.next_button: QPushButton
        self.cancel_button: QPushButton
        self.apply_button: QPushButton
        self._step_titles = [
            "Choose EEG Data",
            "Load Labels",
            "Review Metadata",
            "Match Labels",
            "Review and Import",
        ]
        self._metadata_items: list[tuple[QTreeWidgetItem, dict[str, Any]]] = []
        self._label_carrier_items: list[tuple[QTreeWidgetItem, dict[str, Any]]] = []
        self._label_target_widgets: dict[int, QComboBox] = {}
        self._eeg_label_widgets: dict[str, QComboBox] = {}
        self._eeg_label_status_widgets: dict[str, QLabel] = {}
        self._label_choice_widgets: dict[tuple[int, int], QComboBox] = {}
        self._eeg_file_remap_widgets: dict[str, QComboBox] = {}
        self._label_carrier_remap_widgets: dict[str, QComboBox] = {}
        self._event_role_widgets: dict[int, QComboBox] = {}
        self._event_role_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._class_map_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._class_map_widgets: dict[int, QComboBox] = {}
        self._internal_event_user_roles: dict[str, str] = {}
        self._internal_class_name_edits: dict[str, str] = {}
        self._target_event_code_selection: list[str] = []
        self._target_event_selection_touched = False
        self._event_detail_widgets: list[QWidget] = []
        self._tree_column_specs: dict[int, tuple[int, ...]] = {}
        self._updating_label_rule = False
        self._label_rule_controls_changed = False
        self._initial_label_sources = self._clean_label_sources(
            self.scan_result.get("label_sources")
        )
        self._extra_label_sources = list(self._initial_label_sources)
        self._excluded_label_carriers: list[str] = []
        self._skip_labels = False
        super().__init__(
            parent=parent,
            title="Import EEG Data",
            width=1040,
            height=760,
        )

    @property
    def decision(self) -> str:
        """Return the validation decision string."""
        return str(self.validation_decision.get("decision", "unknown"))

    def init_ui(self) -> None:
        self._apply_product_tree_style()
        self.setObjectName("DataImportWizardDialog")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 16)
        root_layout.setSpacing(14)

        self.workflow_steps_label = QLabel()
        self.workflow_steps_label.setObjectName("InterpretationWorkflowSteps")
        self.workflow_steps_label.setWordWrap(True)
        self.workflow_steps_label.setVisible(False)

        stepper_layout = QHBoxLayout()
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(8)
        self.step_labels = []
        for index, title in enumerate(self._step_titles, start=1):
            step_label = QLabel(f"{index}. {title}")
            step_label.setObjectName("DataImportStepLabel")
            step_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            step_label.setMinimumHeight(34)
            stepper_layout.addWidget(step_label, stretch=1)
            self.step_labels.append(step_label)
        root_layout.addLayout(stepper_layout)

        source_path = str(self.scan_result.get("source_path", ""))
        self.summary_label = QLabel(
            str(self.preview.get("summary") or "Review the interpreted EEG source.")
        )
        self.summary_label.setObjectName("InterpretationSummary")
        self.summary_label.setWordWrap(True)
        root_layout.addWidget(self.summary_label)

        self.step_stack = _CurrentStepStackedWidget(self)
        self.step_stack.setObjectName("DataImportWizardSteps")

        decision_text = self._decision_text()
        self.decision_label = QLabel(decision_text)
        self.decision_label.setObjectName("InterpretationDecision")
        self.decision_label.setWordWrap(True)
        source_panel, source_panel_layout = self._step_panel()
        source_panel_layout.addWidget(
            self._panel_header(
                "Choose EEG Data",
                "Selected data and scan location are tracked separately.",
            )
        )
        source_overview_layout = QGridLayout()
        source_overview_layout.setContentsMargins(0, 0, 0, 0)
        source_overview_layout.setHorizontalSpacing(12)
        source_overview_layout.setVerticalSpacing(12)
        source_overview_layout.addWidget(
            self._metric_card(
                "Selected scope",
                self._source_selection_text(),
                self._source_file_preview_text(),
            ),
            0,
            0,
            1,
            2,
        )
        source_overview_layout.addWidget(
            self._metric_card("Scan location", source_path or "Unknown source"),
            0,
            2,
            1,
            2,
        )
        source_overview_layout.addWidget(
            self._metric_card("EEG files", str(self._file_count())),
            1,
            0,
        )
        source_overview_layout.addWidget(
            self._metric_card("Label carriers", str(self._label_carrier_count())),
            1,
            1,
        )
        source_overview_layout.addWidget(
            self._metric_card("BIDS", self._bids_status()),
            1,
            2,
            1,
            2,
        )
        source_panel_layout.addLayout(source_overview_layout)
        source_panel_layout.addStretch()
        self.step_stack.addWidget(source_panel)

        attach_panel, attach_panel_layout = self._step_panel()
        attach_panel_layout.addWidget(
            self._panel_header(
                "Load Labels",
                "Load the label files that will be matched to this EEG data.",
            )
        )
        label_sources_card, label_sources_layout = self._card("Label files")
        label_sources_layout.addWidget(
            self._wrapped_label(self._label_detection_text())
        )
        self.label_source_rows_widget = QWidget()
        self.label_source_rows_widget.setObjectName("DataImportSourceRows")
        self.label_source_rows_layout = QVBoxLayout(self.label_source_rows_widget)
        self.label_source_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.label_source_rows_layout.setSpacing(8)
        self._refresh_label_source_rows()
        label_sources_layout.addWidget(self.label_source_rows_widget)
        self.label_sources_label = QLabel(self._label_sources_status_text())
        self.label_sources_label.setObjectName("DataImportStatusLabel")
        self.label_sources_label.setWordWrap(True)
        self.label_sources_label.setVisible(
            self._label_sources_changed() or self._skip_labels
        )
        label_sources_layout.addWidget(self.label_sources_label)
        label_button_layout = QHBoxLayout()
        label_button_layout.setContentsMargins(0, 0, 0, 0)
        label_button_layout.setSpacing(8)
        self.add_label_file_btn = QPushButton("Load label file")
        self.add_label_file_btn.setObjectName("DataImportToolButton")
        self.add_label_file_btn.setToolTip("Load a label file from another location.")
        self.add_label_file_btn.clicked.connect(self._add_label_file)
        self.add_label_folder_btn = QPushButton("Load label folder")
        self.add_label_folder_btn.setObjectName("DataImportToolButton")
        self.add_label_folder_btn.setToolTip(
            "Load a folder of label files from another location.",
        )
        self.add_label_folder_btn.clicked.connect(self._add_label_folder)
        self.skip_labels_btn = QPushButton("Continue without labels")
        self.skip_labels_btn.setObjectName("DataImportTertiaryButton")
        self.skip_labels_btn.setToolTip(
            "Continue this import without labels; supervised workflows may be limited.",
        )
        self.skip_labels_btn.clicked.connect(self._skip_labels_for_now)
        label_button_layout.addWidget(self.add_label_file_btn)
        label_button_layout.addWidget(self.add_label_folder_btn)
        label_button_layout.addStretch()
        label_button_layout.addWidget(self.skip_labels_btn)
        label_sources_layout.addLayout(label_button_layout)
        attach_panel_layout.addWidget(label_sources_card)
        attach_panel_layout.addStretch()
        self.step_stack.addWidget(attach_panel)

        metadata_panel, metadata_panel_layout = self._step_panel()
        metadata_panel_layout.addWidget(
            self._panel_header(
                "Review Metadata",
                "Subject, session, task, and run choices are saved into the recipe.",
            )
        )
        self.smart_parse_btn = QPushButton("Smart Parse metadata")
        self.smart_parse_btn.setObjectName("DataImportToolButton")
        self.smart_parse_btn.clicked.connect(self._run_smart_parse)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(
            ["File", "Subject", "Session", "Task", "Run"],
        )
        self.file_tree.setMinimumHeight(160)
        self.file_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_files()
        self._fit_tree_columns(
            self.file_tree,
            (260, 110, 120, 150, 70),
            stretch_column=0,
        )
        self._fit_compact_tree_height(self.file_tree, min_height=86, max_height=160)
        complete_count, missing_fields = self._metadata_completion_counts()
        metadata_table_card = QFrame()
        metadata_table_card.setObjectName("DataImportCard")
        metadata_table_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        metadata_table_layout = QVBoxLayout(metadata_table_card)
        metadata_table_layout.setContentsMargins(14, 12, 14, 12)
        metadata_table_layout.setSpacing(8)
        metadata_title_layout = QHBoxLayout()
        metadata_title_layout.setContentsMargins(0, 0, 0, 0)
        metadata_title_layout.setSpacing(10)
        metadata_title = QLabel("Metadata")
        metadata_title.setObjectName("DataImportCardTitle")
        metadata_title_layout.addWidget(
            metadata_title,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        metadata_title_layout.addStretch()
        metadata_tool_holder = QFrame()
        metadata_tool_holder.setObjectName("DataImportMetadataToolHolder")
        metadata_tool_layout = QVBoxLayout(metadata_tool_holder)
        metadata_tool_layout.setContentsMargins(0, 3, 0, 0)
        metadata_tool_layout.setSpacing(0)
        metadata_tool_layout.addWidget(self.smart_parse_btn)
        metadata_title_layout.addWidget(metadata_tool_holder)
        metadata_table_layout.addLayout(metadata_title_layout)
        metadata_summary = QLabel(
            self._metadata_review_summary(complete_count, missing_fields)
        )
        metadata_summary.setObjectName("DataImportSummaryValue")
        metadata_summary.setWordWrap(False)
        metadata_summary.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        metadata_table_layout.addWidget(metadata_summary)
        metadata_table_layout.addWidget(self.file_tree)
        metadata_panel_layout.addWidget(metadata_table_card)
        metadata_panel_layout.addStretch()
        self.step_stack.addWidget(metadata_panel)

        label_panel, label_panel_layout = self._step_panel()
        label_panel_layout.addWidget(
            self._panel_header(
                "Match Labels",
                "Choose the label source, then map label values onto the EEG.",
            )
        )
        self.label_carrier_tree = QTreeWidget()
        self.label_carrier_tree.setHeaderLabels(
            [
                "Label file",
                "EEG file",
                "Label source",
                "Alignment",
                "Label unit",
                "Use as",
            ],
        )
        self.label_carrier_tree.setMinimumHeight(110)
        self.label_carrier_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_label_carrier_tree()
        self._fit_tree_columns(
            self.label_carrier_tree,
            (190, 145, 150, 175, 135, 150),
            stretch_column=5,
        )
        self._fit_compact_tree_height(
            self.label_carrier_tree,
            min_height=92,
            max_height=150,
        )
        self.label_carrier_tree.setVisible(False)

        label_source_card, label_source_layout = self._card("Label source")
        self._build_label_source_mode_card(label_source_layout)
        label_panel_layout.addWidget(label_source_card)

        self.internal_event_card, internal_event_layout = self._card(
            "Events inside EEG files"
        )
        self._build_internal_event_card(internal_event_layout)
        label_panel_layout.addWidget(self.internal_event_card)

        self.pairing_card, pairing_layout = self._card("File pairing")
        self._build_pairing_card(pairing_layout)
        label_panel_layout.addWidget(self.pairing_card)

        self.label_table_fallback_card = self._label_table_fallback_card()
        label_panel_layout.addWidget(self.label_table_fallback_card)

        self.label_values_card, label_values_layout = self._card(
            "Label values and placement"
        )
        self.placement_card = self.label_values_card
        self._build_label_values_card(label_values_layout)
        self._build_placement_card(label_values_layout)
        label_panel_layout.addWidget(self.label_values_card)

        self.event_group = QGroupBox("Class names and event use")
        self.event_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.event_layout = QVBoxLayout(self.event_group)
        self.event_layout.setContentsMargins(12, 10, 12, 12)
        self.event_layout.setSpacing(6)
        self.event_tree = QTreeWidget()
        self.event_tree.setHeaderLabels(["Label / event", "Use as", "Name / meaning"])
        self.event_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self.event_layout.addWidget(self.event_tree)
        self._refresh_event_detail_view()
        label_panel_layout.addWidget(self.event_group)
        if hasattr(self, "internal_event_status_label"):
            self.internal_event_status_label.setText(self._internal_event_status_text())
        self.match_check_card, match_check_layout = self._card("Check")
        self._build_match_check_card(match_check_layout)
        label_panel_layout.addWidget(self.match_check_card)
        self._refresh_label_source_mode()
        label_panel_layout.addStretch()
        self.step_stack.addWidget(label_panel)

        review_panel, review_panel_layout = self._step_panel()
        review_panel_layout.addWidget(
            self._panel_header(
                "Review and Import",
                "Only items that affect import readiness are shown here.",
            )
        )
        review_status_layout = QHBoxLayout()
        review_status_layout.setContentsMargins(0, 0, 0, 0)
        review_status_layout.setSpacing(12)
        decision_card, decision_layout = self._card("Import readiness")
        decision_layout.addWidget(self.decision_label)
        review_status_layout.addWidget(decision_card, stretch=2)
        recipe_card, recipe_layout = self._card("Recipe")
        recipe_layout.addWidget(
            self._wrapped_label(
                "Source, metadata edits, label choices, and confirmations"
            )
        )
        review_status_layout.addWidget(recipe_card, stretch=2)
        review_panel_layout.addLayout(review_status_layout)
        self.review_actions_panel = QWidget()
        self.review_actions_panel.setObjectName("DataImportActionItemsPanel")
        self.review_actions_layout = QVBoxLayout(self.review_actions_panel)
        self.review_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.review_actions_layout.setSpacing(10)
        self._populate_review_action_cards()
        review_panel_layout.addWidget(self.review_actions_panel)
        self.review_tree = QTreeWidget()
        self.review_tree.setObjectName("InterpretationReviewSummary")
        self.review_tree.setHeaderLabels(
            ["Target step", "Issue", "Impact", "Next action"],
        )
        self.review_tree.setRootIsDecorated(False)
        self.review_tree.setAlternatingRowColors(True)
        self.review_tree.setUniformRowHeights(True)
        self.review_tree.setMinimumHeight(132)
        self.review_tree.setMaximumHeight(220)
        self._fit_tree_columns(
            self.review_tree,
            (135, 220, 315, 245),
            stretch_column=3,
        )
        self._populate_review_tree()
        self._fit_review_tree_height()
        self.review_tree.setVisible(self._has_remap_options())
        if self._has_remap_options():
            remap_card, remap_layout = self._card("Recipe replacements")
            remap_layout.addWidget(self.review_tree)
            review_panel_layout.addWidget(remap_card)
        review_panel_layout.addStretch()
        self.step_stack.addWidget(review_panel)

        self.scroll_area = _StepScrollArea(self)
        self.scroll_area.setObjectName("DataImportStepScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setWidget(self.step_stack)
        root_layout.addWidget(self.scroll_area, stretch=1)

        self.confirmation_label = QLabel(self._confirmation_text())
        self.confirmation_label.setObjectName("InterpretationConfirmation")
        self.confirmation_label.setWordWrap(True)
        root_layout.addWidget(self.confirmation_label)

        self.save_recipe_check = QCheckBox("Save reusable import recipe after applying")
        apply_allowed = self._apply_allowed()
        self.save_recipe_check.setChecked(apply_allowed)
        self.save_recipe_check.setEnabled(apply_allowed)
        self.save_recipe_check.setToolTip(
            "Recipe records source, metadata decisions, label carriers, and "
            "confirmations for review or replay."
        )
        root_layout.addWidget(self.save_recipe_check)

        separator = QFrame()
        separator.setObjectName("DataImportFooterSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        root_layout.addWidget(separator)

        footer_frame = QFrame()
        footer_frame.setObjectName("DataImportFooter")
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("DataImportSecondaryButton")
        self.back_button.setStyleSheet(self._secondary_button_style())
        self.back_button.clicked.connect(self._go_previous_step)
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("DataImportPrimaryButton")
        self.next_button.setStyleSheet(self._primary_button_style())
        self.next_button.clicked.connect(self._go_next_step)

        self.button_box = QDialogButtonBox(self)
        self.apply_button = QPushButton(
            "Apply Remap"
            if self.decision == "blocked" and self._has_remap_options()
            else "Confirm and Apply"
            if self.decision == "needs_confirmation"
            else "Apply Interpretation"
        )
        self.apply_button.setObjectName("DataImportPrimaryButton")
        self.apply_button.setStyleSheet(self._primary_button_style())
        self.apply_button.setEnabled(apply_allowed)
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("DataImportSecondaryButton")
        self.cancel_button.setStyleSheet(self._secondary_button_style())
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addStretch()
        footer_layout.addWidget(self.back_button)
        footer_layout.addWidget(self.next_button)
        footer_layout.addWidget(self.apply_button)
        root_layout.addWidget(footer_frame)
        self._sync_step_state()
        self._fit_all_tree_columns_to_viewport()

    def _panel_header(self, title: str, detail: str) -> QFrame:
        header = QFrame()
        header.setObjectName("DataImportPanelHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportPanelTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportPanelSubtitle")
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)
        return header

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("DataImportCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportCardTitle")
        layout.addWidget(title_label)
        return card, layout

    def _metric_card(self, title: str, value: str, detail: str = "") -> QFrame:
        card = QFrame()
        card.setObjectName("DataImportMetricCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("DataImportMetricValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("DataImportMetricDetail")
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(detail_label)
        return card

    @staticmethod
    def _summary_line(label: str, value: str) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportSummaryLine")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label_widget = QLabel(label)
        label_widget.setObjectName("DataImportSummaryLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("DataImportSummaryValue")
        value_widget.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addStretch()
        layout.addWidget(value_widget)
        return row

    def _build_label_source_mode_card(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.label_source_mode_combo = self._rule_combo(
            self._label_source_mode_choices(),
            self._default_label_source_mode(),
            "Choose whether labels come from the EEG files or from loaded label files.",
        )
        row.addWidget(self._label_source_mode_control())
        self.label_source_status_label = QLabel(self._label_source_status_text())
        self.label_source_status_label.setObjectName("DataImportRuleStatus")
        self.label_source_status_label.setWordWrap(True)
        self.label_source_status_label.setVisible(False)
        row.addStretch(1)
        layout.addLayout(row)
        self.label_source_mode_combo.currentIndexChanged.connect(
            self._refresh_label_source_mode
        )

    def _label_source_mode_choices(self) -> list[tuple[str, str]]:
        choices = [
            ("Labels inside EEG files", "internal_events"),
            ("Loaded label files", "loaded_label_files"),
        ]
        if self._label_carrier_items:
            return [choices[1], choices[0]]
        return choices

    def _default_label_source_mode(self) -> str:
        return "loaded_label_files" if self._label_carrier_items else "internal_events"

    def _label_source_mode(self) -> str:
        value = self.label_source_mode_combo.currentData()
        return str(value or self._default_label_source_mode())

    def _label_source_status_text(self) -> str:
        mode = self._label_source_mode()
        if mode == "loaded_label_files":
            if not self._label_carrier_items:
                return "No label files are loaded. Load a label file or switch source."
            return "Pair each label file, then choose how label values are placed."
        return (
            "Use events inside the EEG files, then confirm which events become classes."
        )

    def _label_source_mode_control(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataImportLabelSourceModeControl")
        frame.setFixedWidth(280)
        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        title = QLabel("Source")
        title.setObjectName("DataImportLabelSourceChoiceLabel")
        title.setFixedWidth(48)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.label_source_mode_combo.setMinimumContentsLength(24)
        self.label_source_mode_combo.setMinimumWidth(225)
        self.label_source_mode_combo.setMaximumWidth(225)
        self.label_source_mode_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(
            self.label_source_mode_combo,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        return frame

    def _refresh_label_source_mode(self) -> None:
        if not hasattr(self, "label_source_mode_combo"):
            return
        self._refresh_event_detail_view()
        mode = self._label_source_mode()
        use_loaded = mode == "loaded_label_files"
        has_event_details = bool(
            self._event_role_items
            or self._class_map_items
            or self._event_detail_widgets
        )
        has_class_map = bool(self._class_map_items)

        if hasattr(self, "label_source_status_label"):
            self.label_source_status_label.setText(self._label_source_status_text())
        if hasattr(self, "pairing_status_label"):
            self.pairing_status_label.setText(self._pairing_summary_text())
        fallback_visible = use_loaded and self._should_show_label_table_fallback()
        if hasattr(self, "pairing_card"):
            self.pairing_card.setVisible(use_loaded)
        for widget in (
            getattr(self, "label_values_card", None),
            getattr(self, "placement_card", None),
        ):
            if widget is not None:
                widget.setVisible(use_loaded and not fallback_visible)
        self._refresh_label_table_fallback()
        if hasattr(self, "match_check_card"):
            self.match_check_card.setVisible(False)
        if hasattr(self, "internal_event_card"):
            internal_details_available = bool(
                self._internal_candidate_label_event_rows()
                or self._internal_not_used_event_rows()
                or self._event_role_items
                or self._class_map_items
            )
            self.internal_event_card.setVisible(
                (not use_loaded) and not internal_details_available
            )
        if hasattr(self, "event_group"):
            self.event_group.setVisible(
                has_event_details
                and (not fallback_visible)
                and (not use_loaded or has_class_map)
            )
        if hasattr(self, "rule_status_label"):
            self.rule_status_label.setText(self._label_rule_status_text())
        self._sync_scroll_policy()

    def _refresh_event_detail_view(self) -> None:
        if not hasattr(self, "event_tree") or not hasattr(self, "event_layout"):
            return
        self._clear_event_detail_widgets()
        self.event_tree.clear()
        self._event_role_items.clear()
        self._event_role_widgets.clear()
        self._class_map_items.clear()
        self._class_map_widgets.clear()
        self._populate_event_tree()
        self._fit_tree_columns(self.event_tree, (220, 150, 420), stretch_column=2)
        self._fit_event_tree_height()
        if self._label_source_mode() == "internal_events":
            self._build_internal_event_rules_view()
        elif self._class_map_items:
            self.event_group.setTitle("Class names")
            self._add_event_section_title("Class names")
            class_map_rows_widget = self._build_class_map_rows_widget()
            self.class_map_rows_widget = class_map_rows_widget
            self.event_layout.addWidget(class_map_rows_widget)
            self._event_detail_widgets.append(class_map_rows_widget)
            class_map_rows_widget.setVisible(True)
            self.event_tree.setVisible(False)
            self.event_group.setMaximumHeight(
                class_map_rows_widget.sizeHint().height() + 68,
            )
        else:
            self.event_tree.setVisible(bool(self._event_role_items))
            self.event_group.setMaximumHeight(16777215)
        has_event_details = bool(self._event_role_items or self._class_map_items)
        has_event_details = has_event_details or bool(self._event_detail_widgets)
        self.event_group.setVisible(has_event_details)
        if hasattr(self, "internal_event_status_label"):
            self.internal_event_status_label.setText(self._internal_event_status_text())

    def _clear_event_detail_widgets(self) -> None:
        self.class_map_rows_widget = None
        for widget in list(self._event_detail_widgets):
            self._delete_event_detail_widget(widget)
        self._event_detail_widgets.clear()

    def _delete_event_detail_widget(self, widget: QWidget) -> None:
        try:
            widget.hide()
            self.event_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        except RuntimeError:
            pass

    def _build_internal_event_rules_view(self) -> None:
        self.event_group.setTitle("")
        group_title = QLabel("Labels inside EEG files")
        group_title.setObjectName("DataImportInternalGroupTitle")
        self.event_layout.insertWidget(0, group_title)
        self._event_detail_widgets.append(group_title)

        candidate_rows = self._internal_candidate_label_event_rows()
        not_used_rows = self._internal_not_used_event_rows()

        summary = QLabel(self._internal_event_summary_text())
        summary.setObjectName("DataImportInternalSummaryLine")
        summary.setWordWrap(True)
        self.event_layout.insertWidget(1, summary)
        self._event_detail_widgets.append(summary)

        if candidate_rows:
            self._add_event_section_spacing(7)
            self._add_event_section_title("Suggested training labels")
            candidate_help = self._event_section_help(
                "Confirm which EEG events become training labels.",
            )
            self._ensure_class_name_items_from_event_rows(candidate_rows)
            candidate_table = self._internal_training_labels_table(candidate_rows)
            self.event_layout.addWidget(candidate_table)
            self._event_detail_widgets.extend([candidate_help, candidate_table])
            self.event_tree.setVisible(False)
        else:
            self.event_tree.setVisible(bool(self._event_role_items))

        not_used_rows = self._internal_not_used_event_rows()
        if not_used_rows:
            self._add_event_section_spacing(9)
            self._add_event_section_title("Other EEG events")
            other_help = self._event_section_help(
                "These events are available in the EEG files but are not currently "
                "used as class labels.",
            )
            not_used_table = self._internal_other_events_table(not_used_rows)
            self.event_layout.addWidget(not_used_table)
            self._event_detail_widgets.extend([other_help, not_used_table])
        if candidate_rows or not_used_rows:
            self._add_event_section_spacing(7)
            selection_preview = QLabel(
                self._internal_event_selection_preview_text(
                    candidate_rows,
                    not_used_rows,
                )
            )
            selection_preview.setObjectName("DataImportInternalCheckLine")
            selection_preview.setWordWrap(True)
            self.event_layout.addWidget(selection_preview)
            self._event_detail_widgets.append(selection_preview)
        self.event_group.setMaximumHeight(16777215)

    def _add_event_section_spacing(self, height: int) -> QWidget:
        spacer = QWidget()
        spacer.setObjectName("DataImportEventSectionSpacer")
        spacer.setFixedHeight(max(height, 0))
        self.event_layout.addWidget(spacer)
        self._event_detail_widgets.append(spacer)
        return spacer

    def _add_event_section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportSourceTitle")
        label.setWordWrap(False)
        self.event_layout.addWidget(label)
        self._event_detail_widgets.append(label)
        return label

    def _event_section_help(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportSourceDetail")
        label.setWordWrap(True)
        self.event_layout.addWidget(label)
        return label

    def _internal_training_labels_table(
        self,
        rows: list[dict[str, str]],
    ) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportInternalLabelsTable")
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setMinimumHeight(42 + max(len(rows), 1) * 38)
        grid = QGridLayout(table)
        grid.setContentsMargins(13, 12, 13, 13)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(11)
        headers = [
            "Event",
            "Use as",
            "Evidence",
            "Count / coverage",
            "Class name",
            "",
        ]
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)

        item_by_code = {code: item for item, code, _original in self._class_map_items}
        for row_index, row in enumerate(rows, start=1):
            code = str(row.get("code") or "").strip()
            self._grid_text(grid, row_index, 0, code, primary=True)
            self._grid_text(grid, row_index, 1, str(row.get("use_as") or "Class label"))
            self._grid_text(
                grid,
                row_index,
                2,
                str(row.get("evidence") or "Suggested by event pattern"),
            )
            self._grid_text(grid, row_index, 3, str(row.get("coverage") or ""))
            item = item_by_code.get(code)
            if item is not None:
                selector = self._clone_class_map_selector(item, table)
                selector.setMinimumHeight(28)
                grid.addWidget(selector, row_index, 4)
            else:
                self._grid_text(grid, row_index, 4, "")
            button = self._internal_event_action_button(
                "Not a label",
                code,
                "not a label",
                table,
            )
            grid.addWidget(button, row_index, 5)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 4)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 3)
        grid.setColumnStretch(5, 0)
        return table

    def _internal_other_events_table(self, rows: list[dict[str, str]]) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportInternalOtherEventsTable")
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setMinimumHeight(42 + max(len(rows), 1) * 36)
        grid = QGridLayout(table)
        grid.setContentsMargins(13, 12, 13, 13)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        headers = [
            "Event",
            "Suggested use",
            "Evidence / reason",
            "Count / coverage",
            "",
        ]
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)

        for row_index, row in enumerate(rows, start=1):
            code = str(row.get("code") or "").strip()
            self._grid_text(grid, row_index, 0, code, primary=True)
            self._grid_text(grid, row_index, 1, str(row.get("use_as") or "Ignore"))
            self._grid_text(grid, row_index, 2, str(row.get("reason") or ""))
            self._grid_text(grid, row_index, 3, str(row.get("coverage") or ""))
            button = self._internal_event_action_button(
                "Use as label",
                code,
                "class label",
                table,
            )
            grid.addWidget(button, row_index, 4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 4)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 0)
        return table

    def _grid_text(
        self,
        grid: QGridLayout,
        row: int,
        column: int,
        text: str,
        *,
        primary: bool = False,
    ) -> QLabel:
        label = QLabel(text)
        label.setObjectName(
            "DataImportPairingFile" if primary else "DataImportSourceDetail"
        )
        label.setWordWrap(column in {1, 2})
        label.setMinimumHeight(24)
        grid.addWidget(label, row, column)
        return label

    def _internal_event_action_button(
        self,
        text: str,
        code: str,
        role: str,
        parent: QWidget,
    ) -> QPushButton:
        button = QPushButton(text, parent)
        button.setObjectName("DataImportInlineAction")
        button.setProperty("event_code", code)
        button.setFlat(True)
        button.setMinimumHeight(24)
        button.setMaximumWidth(82)
        button.setToolTip(
            "Move this EEG event into training labels."
            if role == "class label"
            else "Keep this EEG event, but do not use it as a training label."
        )
        button.clicked.connect(
            lambda _checked=False, event_code=code, event_role=role: (
                self._set_internal_event_role(event_code, event_role)
            )
        )
        return button

    def _set_internal_event_role(self, code: str, role: str) -> None:
        code = str(code).strip()
        if not code:
            return
        self._remember_internal_class_name_edits()
        self._internal_event_user_roles[code] = role
        self._refresh_event_detail_view()
        if hasattr(self, "event_group"):
            self.event_group.setVisible(True)
        if hasattr(self, "rule_status_label"):
            self.rule_status_label.setText(self._label_rule_status_text())
        self._sync_scroll_policy()

    def _remember_internal_class_name_edits(self) -> None:
        for tree_item, code, _original in self._class_map_items:
            value = self._class_map_item_text(tree_item).strip()
            if value:
                self._internal_class_name_edits[code] = value

    def _internal_event_check_text(
        self,
        candidate_rows: list[dict[str, str]],
        not_used_rows: list[dict[str, str]],
    ) -> str:
        label_count = len(candidate_rows)
        other_count = len(not_used_rows)
        if label_count:
            label_text = f"{label_count} EEG event(s) will be used as training labels."
        else:
            label_text = "No EEG events are currently selected as training labels."
        other_text = (
            f"{other_count} other EEG event(s) are kept out of training labels."
            if other_count
            else "No other EEG events are listed for this preview."
        )
        return f"{label_text} {other_text}"

    def _internal_event_selection_preview_text(
        self,
        candidate_rows: list[dict[str, str]],
        not_used_rows: list[dict[str, str]],
    ) -> str:
        training = self._event_code_list_text(row["code"] for row in candidate_rows)
        excluded = self._event_code_list_text(row["code"] for row in not_used_rows)
        if training and excluded:
            return f"Selection preview: train on {training}; not used: {excluded}."
        if training:
            return f"Selection preview: train on {training}."
        if excluded:
            return (
                f"Selection preview: no training labels selected; not used: {excluded}."
            )
        return "Selection preview: no EEG events are selected yet."

    @staticmethod
    def _event_code_list_text(codes: Iterable[str], *, limit: int = 6) -> str:
        values = [str(code).strip() for code in codes if str(code).strip()]
        if not values:
            return ""
        if len(values) <= limit:
            return ", ".join(values)
        visible = ", ".join(values[:limit])
        return f"{visible} +{len(values) - limit} more"

    def _event_rules_table(
        self,
        headers: list[str],
        rows: list[tuple[str, str, str]],
    ) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportEventRulesTable")
        table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        table.setMinimumHeight(32 + max(len(rows), 1) * 24)
        grid = QGridLayout(table)
        grid.setContentsMargins(10, 7, 10, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)
        for row_index, row in enumerate(rows, start=1):
            for column, value in enumerate(row):
                label = QLabel(value)
                label.setObjectName(
                    "DataImportPairingFile" if column == 0 else "DataImportSourceDetail"
                )
                label.setWordWrap(column == 2)
                label.setMinimumHeight(18)
                grid.addWidget(label, row_index, column)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 3)
        return table

    def _build_internal_event_card(self, layout: QVBoxLayout) -> None:
        self.internal_event_status_label = self._wrapped_label(
            self._internal_event_status_text()
        )
        layout.addWidget(self.internal_event_status_label)

    def _internal_event_status_text(self) -> str:
        if self._event_role_items or self._class_map_items:
            return (
                "Detected event or class information inside the EEG import preview. "
                "Use the confirmation rows below to keep the role and names explicit."
            )
        return (
            "No internal event candidates are available in this preview yet. If the "
            "recording contains usable events, they can still be reviewed after load "
            "before epoching."
        )

    def _internal_event_summary_text(self) -> str:
        payload = self._internal_event_preview_payload()
        file_count = len(self._selected_eeg_file_names())
        parts = [
            f"{file_count} EEG file(s) selected"
            if file_count
            else "No selected EEG files",
        ]
        pattern_status = str(payload.get("pattern_status") or "").strip()
        if pattern_status:
            parts.append(pattern_status)
        elif self._internal_candidate_label_event_rows():
            parts.append("Event pattern ready for review")
        elif self._event_role_items or self._class_map_items:
            parts.append("Internal event information available")
        else:
            parts.append("No internal label events detected yet")
        if payload.get("names_reliable") is False:
            parts.append("Event names need review")
        return " · ".join(parts)

    def _internal_candidate_label_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = payload.get("candidate_label_events") or payload.get(
            "candidate_events"
        )
        rows: list[dict[str, str]] = []
        if isinstance(raw_rows, list):
            for raw in raw_rows:
                if not isinstance(raw, dict):
                    continue
                code = self._internal_event_code_from_row(raw)
                if not code:
                    continue
                if self._internal_event_user_roles.get(code) == "not a label":
                    continue
                rows.append(
                    {
                        "code": code,
                        "use_as": str(raw.get("use_as") or "Class label"),
                        "coverage": self._event_coverage_text(raw),
                        "class_name": self._internal_event_class_name(raw, payload),
                        "evidence": self._event_evidence_text(
                            raw,
                            "Suggested by event pattern",
                        ),
                    }
                )
        for row in self._base_not_used_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) != "class label":
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": "Class label",
                    "coverage": str(row.get("coverage") or ""),
                    "class_name": self._internal_class_name_edits.get(code, ""),
                    "evidence": "Changed by user",
                }
            )
        if rows:
            return sorted(rows, key=self._event_code_sort_key)
        class_map = self._class_map_for_current_label_source()
        if class_map:
            return [
                {
                    "code": str(code),
                    "use_as": "Class label",
                    "coverage": self._default_event_coverage_text(),
                    "class_name": self._internal_class_name_edits.get(
                        str(code),
                        str(label),
                    ),
                    "evidence": "Existing class map",
                }
                for code, label in sorted(
                    class_map.items(),
                    key=self._class_map_sort_key,
                )
            ]
        return []

    def _internal_not_used_event_rows(self) -> list[dict[str, str]]:
        rows = []
        for row in self._base_not_used_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) == "class label":
                continue
            rows.append(row)
        for row in self._base_candidate_label_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) != "not a label":
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": "Not used",
                    "reason": "Changed by user",
                    "coverage": str(row.get("coverage") or ""),
                }
            )
        return sorted(rows, key=self._event_code_sort_key)

    @staticmethod
    def _event_code_sort_key(item: dict[str, str]) -> tuple[int, int | str]:
        code = str(item.get("code") or "").strip()
        return (0, int(code)) if code.isdigit() else (1, code.casefold())

    def _base_candidate_label_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = payload.get("candidate_label_events") or payload.get(
            "candidate_events"
        )
        rows: list[dict[str, str]] = []
        if not isinstance(raw_rows, list):
            return rows
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            code = self._internal_event_code_from_row(raw)
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "coverage": self._event_coverage_text(raw),
                }
            )
        return rows

    def _base_not_used_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = (
            payload.get("not_used_events")
            or payload.get("non_label_events")
            or payload.get("excluded_events")
            or []
        )
        rows: list[dict[str, str]] = []
        if not isinstance(raw_rows, list):
            return rows
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            code = self._internal_event_code_from_row(raw)
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": str(raw.get("use_as") or raw.get("role") or "Ignore"),
                    "reason": str(raw.get("reason") or raw.get("meaning") or ""),
                    "coverage": self._event_coverage_text(raw),
                }
            )
        return rows

    def _internal_event_preview_payload(self) -> dict[str, Any]:
        payload = self.preview.get("internal_event_preview") or self.preview.get(
            "inside_eeg_events"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _internal_event_code_from_row(row: dict[str, Any]) -> str:
        for key in (
            "event_code",
            "original_event_code",
            "original_code",
            "original_label",
            "value",
            "raw_value",
            "code",
            "label",
            "event_label",
        ):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    def _event_coverage_text(self, row: dict[str, Any]) -> str:
        coverage = str(row.get("coverage") or "").strip()
        event_count = self._event_count_text(row)
        if coverage and event_count:
            return f"{event_count} · {coverage}"
        if coverage:
            return coverage
        file_count = len(self._selected_eeg_file_names())
        present = row.get("present_files")
        total = row.get("total_files")
        if isinstance(present, int) and isinstance(total, int) and total > 0:
            file_coverage = f"{present}/{total} files"
            return f"{event_count} · {file_coverage}" if event_count else file_coverage
        missing = row.get("missing_files")
        if isinstance(missing, list) and file_count:
            file_coverage = f"{max(file_count - len(missing), 0)}/{file_count} files"
            return f"{event_count} · {file_coverage}" if event_count else file_coverage
        default_coverage = self._default_event_coverage_text()
        if event_count and default_coverage:
            return f"{event_count} · {default_coverage}"
        return event_count or default_coverage

    @staticmethod
    def _event_count_text(row: dict[str, Any]) -> str:
        for key in (
            "event_count",
            "total_events",
            "occurrence_count",
            "occurrences",
            "count",
            "total_count",
        ):
            value = row.get(key)
            if isinstance(value, int) and value >= 0:
                return f"{value} events"
            value_text = str(value or "").strip()
            if value_text.isdigit():
                return f"{value_text} events"
        file_counts = row.get("file_counts") or row.get("per_file_counts")
        if isinstance(file_counts, dict):
            total = sum(
                value for value in file_counts.values() if isinstance(value, int)
            )
            return f"{total} events" if total >= 0 else ""
        if isinstance(file_counts, list):
            total = sum(value for value in file_counts if isinstance(value, int))
            return f"{total} events" if total >= 0 else ""
        return ""

    def _target_eeg_event_choices(self) -> list[tuple[str, str]]:
        rows = self._target_eeg_event_rows()
        choices: list[tuple[str, str]] = []
        for row in sorted(rows, key=self._target_event_sort_key):
            code = self._internal_event_code_from_row(row)
            if not code:
                continue
            count = self._event_count_text(row)
            use_as = str(row.get("use_as") or row.get("reason") or "").strip()
            detail = " · ".join(part for part in [use_as, count] if part)
            display = f"{code} · {detail}" if detail else code
            choices.append((display, code))
        return choices

    def _target_eeg_event_rows(self) -> list[dict[str, Any]]:
        payload = self._internal_event_preview_payload()
        rows: list[dict[str, Any]] = []
        for key in ("not_used_events", "candidate_label_events", "candidate_events"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
        return rows

    def _target_event_row(self, code: str) -> dict[str, Any]:
        target = str(code or "").strip()
        if not target:
            return {}
        for row in self._target_eeg_event_rows():
            if self._internal_event_code_from_row(row) == target:
                return row
        return {}

    def _target_event_sort_key(self, row: dict[str, Any]) -> tuple[int, str]:
        use_as = str(row.get("use_as") or row.get("reason") or "").lower()
        evidence = str(row.get("evidence") or "").lower()
        if "trial timing" in use_as or "candidate total" in evidence:
            rank = 0
        elif "class label" in use_as:
            rank = 1
        elif any(
            token in use_as for token in ("artifact", "boundary", "ignore", "system")
        ):
            rank = 3
        else:
            rank = 2
        return (rank, self._internal_event_code_from_row(row).casefold())

    def _default_event_coverage_text(self) -> str:
        file_count = len(self._selected_eeg_file_names())
        return f"{file_count}/{file_count} files" if file_count else ""

    def _internal_event_class_name(
        self,
        row: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        code = self._internal_event_code_from_row(row)
        if code in self._internal_class_name_edits:
            return self._internal_class_name_edits[code]
        if payload.get("names_reliable") is False:
            return ""
        return str(row.get("class_name") or row.get("name") or "").strip()

    @staticmethod
    def _event_evidence_text(row: dict[str, Any], fallback: str) -> str:
        return str(row.get("evidence") or row.get("reason") or fallback).strip()

    def _ensure_class_name_items_from_event_rows(
        self,
        rows: list[dict[str, str]],
    ) -> None:
        if self._class_map_items:
            return
        self.event_tree.clear()
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            class_name = str(row.get("class_name") or "").strip()
            tree_item = QTreeWidgetItem([code, "class name", class_name])
            self._class_map_items.append((tree_item, code, class_name))
            self.event_tree.addTopLevelItem(tree_item)
            self._install_class_map_selector(tree_item, class_name)

    def _build_pairing_card(self, layout: QVBoxLayout) -> None:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        self.pairing_status_label = QLabel(self._pairing_summary_text())
        self.pairing_status_label.setObjectName("DataImportPairingSummary")
        self.pairing_status_label.setWordWrap(True)
        header.addWidget(self.pairing_status_label, stretch=1)
        self.label_match_mode_combo = self._rule_combo(
            self._match_mode_choices(),
            self._default_match_mode(),
            "Choose how label files are matched to EEG files.",
        )
        header.addWidget(
            self._inline_rule_control("Pair by", self.label_match_mode_combo)
        )
        layout.addLayout(header)

        self.label_pairing_rows_widget = QWidget()
        self.label_pairing_rows_widget.setObjectName("DataImportPairingRows")
        self.label_pairing_rows_layout = QVBoxLayout(self.label_pairing_rows_widget)
        self.label_pairing_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.label_pairing_rows_layout.setSpacing(5)
        self._populate_pairing_rows()
        layout.addWidget(self.label_pairing_rows_widget)

    def _populate_pairing_rows(self) -> None:
        self._clear_layout(self.label_pairing_rows_layout)
        self._eeg_label_widgets.clear()
        self._eeg_label_status_widgets.clear()
        self._ensure_label_target_widgets()
        if not self._label_carrier_items:
            self.label_pairing_rows_layout.addWidget(
                self._empty_state(
                    "No loaded label files. This import will use internal EEG "
                    "events only if they can be interpreted.",
                )
            )
            return
        eeg_files = self._selected_eeg_file_names()
        if not eeg_files:
            self.label_pairing_rows_layout.addWidget(
                self._empty_state(
                    "No selected EEG files are available for label matching.",
                )
            )
            return
        self.label_pairing_rows_layout.addWidget(self._pairing_header_row())
        for eeg_file in eeg_files:
            self.label_pairing_rows_layout.addWidget(self._pairing_row(eeg_file))
        unassigned_labels = self._unassigned_label_file_names()
        if unassigned_labels:
            unassigned = QLabel(
                "Unused label file(s): "
                + ", ".join(unassigned_labels[:4])
                + (
                    f" +{len(unassigned_labels) - 4} more"
                    if len(unassigned_labels) > 4
                    else ""
                )
            )
            unassigned.setObjectName("DataImportPairingNotice")
            unassigned.setWordWrap(True)
            self.label_pairing_rows_layout.addWidget(unassigned)

    def _ensure_label_target_widgets(self) -> None:
        for item, _original in self._label_carrier_items:
            if id(item) in self._label_target_widgets:
                continue
            selector = self._label_target_selector(
                self._label_carrier_item_text(item, 1),
            )
            self._label_target_widgets[id(item)] = selector
            selector.currentIndexChanged.connect(self._refresh_pairing_status)

    def _pairing_header_row(self) -> QFrame:
        header = QFrame()
        header.setObjectName("DataImportPairingHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        layout.addWidget(self._pairing_header_label("EEG file"), stretch=3)
        layout.addWidget(self._pairing_header_label("Label file"), stretch=3)
        layout.addWidget(self._pairing_header_label("Status", 92))
        return header

    def _pairing_header_label(self, text: str, width: int | None = None) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportPairingHeaderLabel")
        if width is not None:
            label.setFixedWidth(width)
        return label

    def _pairing_row(self, eeg_file: str) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportPairingRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        eeg_label = QLabel(eeg_file)
        eeg_label.setObjectName("DataImportPairingFile")
        eeg_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(eeg_label, stretch=3)

        selector = self._label_file_selector(eeg_file)
        self._eeg_label_widgets[eeg_file] = selector
        selector.currentIndexChanged.connect(
            lambda _index, eeg=eeg_file, widget=selector: self._assign_label_to_eeg(
                eeg,
                widget,
            )
        )
        layout.addWidget(selector, stretch=3)

        matched = bool(selector.currentData())
        badge = QLabel("Matched" if matched else "Needs label")
        badge.setObjectName("DataImportPairingBadge")
        badge.setProperty("pairingState", "matched" if matched else "review")
        badge.setFixedWidth(92)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._eeg_label_status_widgets[eeg_file] = badge
        layout.addWidget(badge)
        return row

    def _label_file_selector(self, eeg_file: str) -> QComboBox:
        selector = QComboBox(self.label_pairing_rows_widget)
        self._prepare_table_combo(selector)
        selector.setToolTip("Choose the label file that applies to this EEG file.")
        selector.addItem("Choose label file", "")
        for item, original in self._label_carrier_items:
            key = self._label_carrier_key(item, original)
            if not key:
                continue
            selector.addItem(self._label_file_display(item, original), key)
        current_key = self._label_key_for_eeg(eeg_file)
        if current_key:
            index = selector.findData(current_key)
            if index >= 0:
                selector.setCurrentIndex(index)
        return selector

    def _assign_label_to_eeg(self, eeg_file: str, selector: QComboBox) -> None:
        selected_key = str(selector.currentData() or "")
        for item, original in self._label_carrier_items:
            key = self._label_carrier_key(item, original)
            target_selector = self._label_target_widgets.get(id(item))
            if target_selector is None:
                continue
            current_target = self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
            if key == selected_key:
                self._set_combo_current_data(target_selector, eeg_file)
            elif current_target == eeg_file:
                self._set_combo_current_data(target_selector, "")
        self._refresh_pairing_status()

    def _label_key_for_eeg(self, eeg_file: str) -> str:
        for item, original in self._label_carrier_items:
            current_target = self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
            if current_target == eeg_file:
                return self._label_carrier_key(item, original)
        return ""

    @staticmethod
    def _label_carrier_key(
        item: QTreeWidgetItem,
        original: dict[str, Any],
    ) -> str:
        return str(original.get("path") or original.get("name") or item.text(0)).strip()

    @staticmethod
    def _label_file_display(item: QTreeWidgetItem, original: dict[str, Any]) -> str:
        return str(
            original.get("name")
            or Path(str(original.get("path") or "")).name
            or item.text(0)
        )

    def _inline_rule_control(self, label: str, selector: QComboBox) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataImportInlineRuleControl")
        frame.setMinimumWidth(370)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(7)
        title = QLabel(label)
        title.setObjectName("DataImportRuleLabel")
        layout.addWidget(title)
        selector.setFixedWidth(250)
        selector.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(selector)
        return frame

    def _refresh_pairing_status(self) -> None:
        for eeg_file, selector in getattr(self, "_eeg_label_widgets", {}).items():
            expected_key = self._label_key_for_eeg(eeg_file)
            if str(selector.currentData() or "") != expected_key:
                previous = selector.blockSignals(True)
                self._set_combo_current_data(selector, expected_key)
                selector.blockSignals(previous)
            badge = self._eeg_label_status_widgets.get(eeg_file)
            if badge is None:
                continue
            matched = bool(selector.currentData())
            badge.setText("Matched" if matched else "Needs label")
            badge.setProperty("pairingState", "matched" if matched else "review")
            style = badge.style()
            if style is not None:
                style.unpolish(badge)
                style.polish(badge)
        if hasattr(self, "pairing_status_label"):
            self.pairing_status_label.setText(self._pairing_summary_text())
        self._refresh_label_rule_status()

    def _pairing_summary_text(self) -> str:
        if not self._label_carrier_items:
            return "No label files loaded."
        total = len(self._selected_eeg_file_names())
        matched = self._matched_eeg_pair_count()
        needs_review = max(total - matched, 0)
        unassigned = len(self._unassigned_label_file_names())
        parts = [f"{matched}/{total} EEG files paired"]
        if needs_review:
            parts.append(f"{needs_review} need label")
        if unassigned:
            parts.append(f"{unassigned} unused label file(s)")
        fallback_reason = (
            self._label_table_fallback_reason()
            if hasattr(self, "rule_label_field_combo")
            else ""
        )
        if fallback_reason:
            parts.append("label format needs conversion")
        elif len(parts) == 1:
            parts.append("ready to place on EEG")
        return " · ".join(parts)

    def _matched_eeg_pair_count(self) -> int:
        return sum(
            1
            for name in self._selected_eeg_file_names()
            if self._label_key_for_eeg(name)
        )

    def _matched_label_pair_count(self) -> int:
        return sum(
            1
            for item, _original in self._label_carrier_items
            if self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
        )

    def _unmatched_eeg_file_names(self) -> list[str]:
        eeg_files = self._selected_eeg_file_names()
        matched = {
            Path(
                self._label_carrier_choice_text(
                    "target_file",
                    self._label_carrier_item_text(item, 1),
                )
            ).name
            for item, _original in self._label_carrier_items
            if self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
        }
        return [name for name in eeg_files if name not in matched]

    def _unassigned_label_file_names(self) -> list[str]:
        result: list[str] = []
        for item, original in self._label_carrier_items:
            target = self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
            if target:
                continue
            result.append(self._label_file_display(item, original))
        return result

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
        values_grid.addWidget(
            self._rule_control("Read labels from", self.rule_label_field_combo),
            0,
            0,
        )
        values_grid.addWidget(
            self._rule_control("Use as", self.rule_use_as_combo),
            0,
            1,
        )
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
            "Choose a duration or end-time field to pass to epoch setup.",
        )
        for hidden_selector in (
            self.rule_placement_method_combo,
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
        ):
            hidden_selector.setVisible(False)
        self._updating_label_rule = False

        layout.addWidget(self._placement_method_selector())
        self.placement_detail_stack = QStackedWidget()
        self.placement_detail_stack.setObjectName("DataImportPlacementDetailStack")
        self.placement_detail_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._build_placement_detail_pages()
        layout.addWidget(self.placement_detail_stack)

        self.placement_status_label = QLabel(self._placement_status_text())
        self.placement_status_label.setObjectName("DataImportRuleStatus")
        self.placement_status_label.setWordWrap(True)
        layout.addWidget(self.placement_status_label)

        self.rule_placement_method_combo.currentIndexChanged.connect(
            self._handle_placement_method_change
        )
        for selector in (
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
        ):
            selector.currentIndexChanged.connect(self._apply_label_rule_to_preview)

        has_label_rows = bool(self._label_carrier_items)
        for selector in (
            self.rule_placement_method_combo,
            self.rule_alignment_combo,
            self.rule_label_unit_combo,
            self.rule_duration_field_combo,
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

        self.view_label_table_format_btn = QPushButton("View examples")
        self.view_label_table_format_btn.setObjectName("DataImportToolButton")
        self.view_label_table_format_btn.clicked.connect(
            self._show_converted_label_table_format
        )
        layout.addWidget(
            self.view_label_table_format_btn,
            0,
            2,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        checklist = QFrame()
        checklist.setObjectName("DataImportFormatChecklist")
        checklist_layout = QVBoxLayout(checklist)
        checklist_layout.setContentsMargins(10, 8, 10, 8)
        checklist_layout.setSpacing(5)
        checklist_title = QLabel("Required format")
        checklist_title.setObjectName("DataImportSourceTitle")
        checklist_layout.addWidget(checklist_title)
        checklist_layout.addWidget(
            self._conversion_check_line("One row per label, trial, event, or interval")
        )
        checklist_layout.addWidget(
            self._conversion_check_line("Required column: label")
        )
        checklist_layout.addWidget(
            self._conversion_check_line(
                "One placement column: event_code, onset_seconds, sample, or interval"
            )
        )
        layout.addWidget(checklist, 1, 0, 1, 2)

        example_layout = QVBoxLayout()
        example_layout.setContentsMargins(0, 0, 0, 0)
        example_layout.setSpacing(5)
        example_title = QLabel("Example table")
        example_title.setObjectName("DataImportSourceTitle")
        example = QLabel("event_code,label\n769,left_hand\n770,right_hand")
        example.setObjectName("DataImportCodeBlock")
        example.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        example_layout.addWidget(example_title)
        example_layout.addWidget(example)
        layout.addLayout(example_layout, 1, 2)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        return card

    @staticmethod
    def _conversion_check_line(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportChecklistLine")
        label.setWordWrap(True)
        return label

    def _refresh_label_table_fallback(self) -> None:
        if not hasattr(self, "label_table_fallback_card"):
            return
        visible = self._should_show_label_table_fallback()
        self.label_table_fallback_card.setVisible(visible)
        if visible:
            self.label_table_fallback_reason_label.setText(
                self._label_table_fallback_reason()
            )

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
        placement_method = ""
        alignment = ""
        if hasattr(self, "rule_placement_method_combo"):
            placement_method = self._combo_current_data(
                self.rule_placement_method_combo
            )
        if hasattr(self, "rule_alignment_combo"):
            alignment = self._combo_current_data(self.rule_alignment_combo)
        if not alignment:
            return (
                "The file was loaded, but XBrainLab cannot tell where each label "
                "belongs in the EEG."
            )
        blocked_reviews = [
            review
            for review in self._active_backend_placement_reviews(placement_method)
            if str(review.get("status") or "").strip().lower() == "blocked"
        ]
        if blocked_reviews:
            summary = str(blocked_reviews[0].get("summary") or "").strip().rstrip(".")
            if summary:
                return (
                    "The file was loaded, but this placement rule is blocked: "
                    f"{summary}."
                )
            return "The file was loaded, but XBrainLab cannot match it to EEG events."
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
        for column, (title, value) in enumerate(self._placement_method_choices()):
            option = QFrame()
            option.setObjectName("DataImportPlacementOption")
            option.setProperty("selected", value == current)
            option_layout = QVBoxLayout(option)
            option_layout.setContentsMargins(10, 8, 10, 9)
            option_layout.setSpacing(4)
            radio = QRadioButton(title)
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
                "Use one time field from each label row to place labels on the "
                "EEG timeline.",
            )
        )
        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        time_field_combo = self._rule_combo(
            self._alignment_rule_choices("time_field"),
            self._default_alignment_value("time_field"),
            "Choose the label-file time field.",
        )
        time_field_combo.currentIndexChanged.connect(
            lambda _index, selector=time_field_combo: (
                self._sync_alignment_from_visible_combo(selector)
            )
        )
        controls.addWidget(
            self._rule_control("Label time field", time_field_combo),
            0,
            0,
        )
        controls.setColumnStretch(0, 1)
        layout.addLayout(controls)
        layout.addWidget(
            self._placement_note("Epoch window will be set later in epoch setup.")
        )
        layout.addStretch(1)
        return page

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
        layout.addWidget(self._placement_note("Matches against EEG event codes."))
        layout.addStretch(1)
        return page

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
        layout.addWidget(self._pairing_header_label("Evidence"), stretch=3)
        layout.addWidget(self._pairing_header_label("Count", 92))
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

    def _label_values_status_text(self) -> str:
        if not self._label_carrier_items:
            return "No loaded label files are available."
        field_value = str(self.rule_label_field_combo.currentData() or "").strip()
        field = self.rule_label_field_combo.currentText()
        use_as = self.rule_use_as_combo.currentText()
        if not field_value:
            return "Choose the field that contains the label values."
        value_summary = self._label_value_count_summary()
        if value_summary:
            return (
                f"{field}: {value_summary}. "
                "Class names can be confirmed below when values are known."
            )
        return (
            f"{field} values will be imported as {use_as.lower()}. "
            "Class names can be confirmed below when values are known."
        )

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
            field = str(review.get("time_field") or "").strip()
            prefix = f"Check: Label time · {field}" if field else "Check: Label time"
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
        if hasattr(self, "placement_status_label"):
            self.placement_status_label.setText(self._placement_status_text())
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
        selector = QComboBox(self)
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
            ("Epoch", "epoch"),
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

    def _apply_label_rule_to_preview(self) -> None:
        if self._updating_label_rule:
            return
        self._label_rule_controls_changed = True
        if not self._label_carrier_items:
            self._refresh_label_rule_status()
            return
        for item, _original in self._label_carrier_items:
            self._apply_rule_combo_to_item(self.rule_label_field_combo, item, 2)
            self._apply_rule_combo_to_item(self.rule_alignment_combo, item, 3)
            self._apply_rule_combo_to_item(self.rule_label_unit_combo, item, 4)
            self._apply_rule_combo_to_item(self.rule_use_as_combo, item, 5)
        self._refresh_label_rule_status()
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

    @staticmethod
    def _set_combo_current_data(selector: QComboBox, value: str) -> None:
        index = selector.findData(value)
        if index < 0:
            selector.addItem(
                DataInterpretationPreviewDialog._label_choice_display(value),
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
                    "event role(s) available for review."
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
                parts.append(f"{target_count - label_rows} unlabeled EEG events")
            if label_rows > target_count:
                parts.append(f"{label_rows - target_count} unmatched label rows")
        if excluded:
            parts.append(f"{excluded} EEG events excluded")
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

    def _add_label_source_rows(self, layout: QVBoxLayout) -> None:
        carriers = self._label_carrier_preview_rows()
        if not carriers:
            layout.addWidget(
                self._empty_state("No nearby label/event source detected.")
            )
        for carrier in carriers[:5]:
            name = str(
                carrier.get("name")
                or Path(str(carrier.get("path", ""))).name
                or "Label source"
            )
            carrier_path = str(carrier.get("path") or "").strip()
            layout.addWidget(
                self._source_row(
                    name,
                    self._label_source_detail(carrier, carrier_path),
                    remove_callback=(
                        lambda _checked=False, item=carrier_path: (
                            self._remove_label_carrier(item)
                        )
                    )
                    if carrier_path
                    else None,
                )
            )
        if len(carriers) > 5:
            layout.addWidget(self._empty_state(f"{len(carriers) - 5} more source(s)."))

        for source in self._extra_label_sources:
            layout.addWidget(
                self._source_row(
                    *self._user_label_source_row(source),
                    remove_callback=lambda _checked=False, item=source: (
                        self._remove_label_source(item)
                    ),
                )
            )

    def _refresh_label_source_rows(self) -> None:
        self._clear_layout(self.label_source_rows_layout)
        self._add_label_source_rows(self.label_source_rows_layout)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _label_carrier_preview_rows(self) -> list[dict[str, Any]]:
        carriers = self.preview.get("label_carrier_preview") or []
        if not isinstance(carriers, list) or not carriers:
            carriers = [
                {
                    "name": Path(str(carrier)).name,
                    "path": str(carrier),
                    "source_kind": "auto",
                }
                for carrier in self.scan_result.get("label_carriers", []) or []
            ]
        result: list[dict[str, Any]] = []
        if not isinstance(carriers, list):
            return result
        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            carrier_path = str(carrier.get("path") or "").strip()
            if carrier_path and self._is_label_carrier_excluded(carrier_path):
                continue
            result.append(carrier)
        return result

    def _source_row(
        self,
        title: str,
        detail: str,
        *,
        remove_callback: Any | None = None,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportSourceRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportSourceDetail")
        detail_label.setWordWrap(False)
        detail_label.setToolTip(detail)
        detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_layout.addWidget(title_label)
        if detail:
            text_layout.addWidget(detail_label)
        layout.addLayout(text_layout)
        layout.addStretch()
        if remove_callback is not None:
            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("DataImportTertiaryButton")
            remove_btn.setToolTip("Remove this loaded label source from the import.")
            remove_btn.clicked.connect(remove_callback)
            layout.addWidget(remove_btn)
        return row

    def _remove_label_source(self, source: str) -> None:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return
        before = list(self._extra_label_sources)
        self._extra_label_sources = [
            item
            for item in self._extra_label_sources
            if self._normalized_label_source_key(item) != source_key
        ]
        if self._extra_label_sources == before:
            return
        self._exclude_carriers_from_source(source)
        self._skip_labels = False
        self._refresh_label_source_rows()
        self._refresh_label_matching_after_source_change()
        self.label_sources_label.setText("Removed label source.")
        self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _remove_label_carrier(self, carrier_path: str) -> None:
        carrier = str(carrier_path).strip()
        if not carrier:
            return
        if self._is_label_carrier_excluded(carrier):
            return
        self._excluded_label_carriers.append(carrier)
        self._skip_labels = False
        self._refresh_label_source_rows()
        self._refresh_label_matching_after_source_change()
        self.label_sources_label.setText("Removed label file.")
        self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _exclude_carriers_from_source(self, source: str) -> None:
        for carrier in self._label_carrier_preview_rows():
            carrier_path = str(carrier.get("path") or "").strip()
            if carrier_path and self._carrier_belongs_to_source(carrier, source):
                self._remove_label_carrier_without_refresh(carrier_path)

    def _remove_label_carrier_without_refresh(self, carrier_path: str) -> None:
        carrier = str(carrier_path).strip()
        if carrier and not self._is_label_carrier_excluded(carrier):
            self._excluded_label_carriers.append(carrier)

    def _refresh_label_matching_after_source_change(self) -> None:
        if hasattr(self, "label_carrier_tree"):
            self.label_carrier_tree.clear()
            self._label_carrier_items.clear()
            self._label_target_widgets.clear()
            self._label_choice_widgets.clear()
            self._label_carrier_remap_widgets.clear()
            self._populate_label_carrier_tree()
            self._fit_label_carrier_tree_height()
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

    @staticmethod
    def _empty_state(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportEmptyState")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _inline_notice(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportInlineNotice")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _label_source_detail(carrier: dict[str, Any], carrier_path: str) -> str:
        source_kind = str(carrier.get("source_kind") or "").strip().lower()
        source_location = str(carrier.get("source_location") or "").strip()
        if source_location:
            location_type = (
                "file"
                if DataInterpretationPreviewDialog._looks_like_file(source_location)
                else "folder"
            )
            action = "Added from" if source_kind == "user_added" else "Found in"
            return f"{action} {location_type}: {source_location}"
        if carrier_path:
            parent = Path(carrier_path).parent.as_posix()
            return f"Found in folder: {parent}"
        return ""

    @staticmethod
    def _looks_like_file(path: str) -> bool:
        return bool(Path(path).suffix)

    def _populate_review_action_cards(self) -> None:
        rows = self._review_rows()
        if not rows:
            rows = [
                (
                    "Review and Import",
                    "Import settings",
                    "No warnings or confirmations.",
                    "Import can continue.",
                )
            ]
        grouped: dict[str, list[tuple[str, str, str]]] = {}
        for target_step, issue, impact, next_action in rows:
            grouped.setdefault(target_step, []).append((issue, impact, next_action))
        for target_step in self._step_titles:
            items = grouped.get(target_step)
            if not items:
                continue
            group_card, group_layout = self._card(target_step)
            for issue, impact, next_action in items:
                group_layout.addWidget(
                    self._action_item_card(issue, impact, next_action)
                )
            self.review_actions_layout.addWidget(group_card)

    @staticmethod
    def _action_item_card(issue: str, impact: str, next_action: str) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportActionCard")
        layout = QGridLayout(row)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(4)
        issue_label = QLabel(issue)
        issue_label.setObjectName("DataImportActionIssue")
        issue_label.setWordWrap(True)
        impact_label = QLabel("Impact")
        impact_label.setObjectName("DataImportActionKicker")
        impact_value = QLabel(impact)
        impact_value.setObjectName("DataImportActionText")
        impact_value.setWordWrap(True)
        action_label = QLabel("Next")
        action_label.setObjectName("DataImportActionKicker")
        action_value = QLabel(next_action)
        action_value.setObjectName("DataImportActionText")
        action_value.setWordWrap(True)
        layout.addWidget(issue_label, 0, 0, 1, 4)
        layout.addWidget(impact_label, 1, 0)
        layout.addWidget(impact_value, 1, 1)
        layout.addWidget(action_label, 1, 2)
        layout.addWidget(action_value, 1, 3)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(3, 2)
        return row

    @staticmethod
    def _step_panel() -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        panel.setObjectName("DataImportStepPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(14)
        return panel, layout

    @staticmethod
    def _primary_button_style() -> str:
        return f"""
            QPushButton {{
                background-color: {Theme.BLUE_PRIMARY};
                color: #e8e8e8;
                border: 1px solid {Theme.BLUE_HOVER};
                border-radius: 4px;
                padding: 6px 14px;
                min-height: 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {Theme.BLUE_HOVER}; }}
            QPushButton:pressed {{ background-color: {Theme.BLUE_PRESSED}; }}
            QPushButton:disabled {{
                background-color: {Theme.BTN_DISABLED_BG};
                color: {Theme.BTN_DISABLED_TEXT};
                border: 1px solid {Theme.BTN_DISABLED_BORDER};
            }}
        """

    @staticmethod
    def _secondary_button_style() -> str:
        return f"""
            QPushButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.ACCENT_PRIMARY};
                background-color: {Theme.BACKGROUND_LIGHT};
            }}
            QPushButton:disabled {{
                color: {Theme.BTN_DISABLED_TEXT};
                background-color: {Theme.BTN_DISABLED_BG};
                border: 1px solid {Theme.BTN_DISABLED_BORDER};
            }}
        """

    def _go_next_step(self) -> None:
        self._go_to_step(self.step_stack.currentIndex() + 1)

    def _go_previous_step(self) -> None:
        self._go_to_step(self.step_stack.currentIndex() - 1)

    def _go_to_step(self, index: int) -> None:
        bounded_index = max(0, min(index, self.step_stack.count() - 1))
        if bounded_index == self.step_stack.currentIndex():
            self._sync_step_state()
            self.step_stack.updateGeometry()
            self._sync_scroll_policy()
            return
        self.step_stack.setCurrentIndex(bounded_index)
        self.step_stack.updateGeometry()
        self._sync_step_state()

    def _sync_step_state(self) -> None:
        if not hasattr(self, "step_stack"):
            return
        current = self.step_stack.currentIndex()
        total = len(self._step_titles)
        title = self._step_titles[current] if current < total else "Review"
        self.workflow_steps_label.setText(
            f"Step {current + 1} of {total}: {title}\n" + " | ".join(self._step_titles)
        )
        self._sync_step_labels(current)
        self.back_button.setEnabled(current > 0)
        final_step = current == total - 1
        self.next_button.setVisible(not final_step)
        if not final_step and current + 1 < total:
            self.next_button.setText(f"Next: {self._step_titles[current + 1]}")
        self.apply_button.setVisible(final_step)
        self.confirmation_label.setVisible(final_step)
        self.save_recipe_check.setVisible(final_step)
        self._fit_metadata_tree_height()
        self._fit_label_carrier_tree_height()
        self._fit_all_tree_columns_to_viewport()
        self._fit_event_tree_height()
        self._fit_review_tree_height()
        self._sync_scroll_policy()

    def _sync_step_labels(self, current: int) -> None:
        if not hasattr(self, "step_labels"):
            return
        for index, label in enumerate(self.step_labels):
            if index < current:
                state = "done"
            elif index == current:
                state = "active"
            else:
                state = "upcoming"
            label.setProperty("stepState", state)
            style = label.style()
            if style is not None:
                style.unpolish(label)
                style.polish(label)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "review_tree"):
            self._fit_metadata_tree_height()
            self._fit_label_carrier_tree_height()
            self._fit_all_tree_columns_to_viewport()
            self._fit_event_tree_height()
            self._fit_review_tree_height()
            self._sync_scroll_policy()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_metadata_tree_height)
        QTimer.singleShot(0, self._fit_label_carrier_tree_height)
        QTimer.singleShot(0, self._fit_all_tree_columns_to_viewport)
        QTimer.singleShot(0, self._fit_event_tree_height)
        QTimer.singleShot(0, self._fit_review_tree_height)
        QTimer.singleShot(0, self._sync_scroll_policy)

    def _sync_scroll_policy(self) -> None:
        if not hasattr(self, "scroll_area") or not hasattr(self, "step_stack"):
            return
        current = self.step_stack.currentWidget()
        if current is None:
            return
        viewport = self.scroll_area.viewport()
        if viewport is None:
            return
        viewport_height = viewport.height()
        if viewport_height <= 0:
            return
        content_height = current.sizeHint().height()
        needs_scroll = content_height > viewport_height + 4
        target_height = content_height if needs_scroll else viewport_height
        if self.step_stack.minimumHeight() != target_height:
            self.step_stack.setFixedHeight(target_height)
        policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if needs_scroll
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.scroll_area.verticalScrollBarPolicy() != policy:
            self.scroll_area.setVerticalScrollBarPolicy(policy)
        if policy == Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            scrollbar = self.scroll_area.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(0)

    def get_result(self) -> dict[str, Any]:
        choices = self._edited_choices()
        if self._skip_labels:
            choices["skip_labels"] = True
        result: dict[str, Any] = {
            "confirmed": self.decision == "needs_confirmation"
            or (self.decision == "blocked" and self._has_complete_remap_choices()),
            "save_recipe": self.save_recipe_check.isChecked(),
            "choices": choices,
        }
        if self._extra_label_sources != self._initial_label_sources:
            result["label_sources"] = list(self._extra_label_sources)
            result["label_sources_changed"] = True
        return result

    @staticmethod
    def _wrapped_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    @staticmethod
    def _clean_label_sources(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result

    def _label_sources_changed(self) -> bool:
        return self._extra_label_sources != self._initial_label_sources

    def _label_detection_text(self) -> str:
        carriers = self.preview.get("label_carrier_preview") or []
        if not isinstance(carriers, list) or not carriers:
            carriers = self.scan_result.get("label_carriers") or []
        count = len(carriers) if isinstance(carriers, list) else 0
        if count:
            return f"{count} label/event file(s) will be reviewed for this import."
        return "No label/event file was detected near the selected EEG data."

    def _label_sources_status_text(self) -> str:
        if self._skip_labels:
            return (
                "Skipped labels for now. Supervised dataset generation and "
                "training remain limited until labels or events are added."
            )
        return ""

    def _user_label_source_row(self, source: str) -> tuple[str, str]:
        source_path = Path(source)
        source_type = "File path" if self._looks_like_file(source) else "Folder path"
        title = source_path.name or source
        return title, f"{source_type}: {source}"

    @staticmethod
    def _normalized_label_source_key(path: str) -> str:
        text = str(path).strip()
        if not text:
            return ""
        try:
            return Path(text).expanduser().resolve(strict=False).as_posix().rstrip("/")
        except (OSError, RuntimeError, ValueError):
            return Path(text).as_posix().rstrip("/")

    def _auto_label_source_keys(self) -> tuple[set[str], set[str]]:
        file_keys: set[str] = set()
        folder_keys: set[str] = set()
        for carrier in self._label_carrier_preview_rows():
            carrier_path = str(carrier.get("path") or "").strip()
            if carrier_path:
                file_keys.add(self._normalized_label_source_key(carrier_path))
                folder_keys.add(
                    self._normalized_label_source_key(
                        Path(carrier_path).parent.as_posix()
                    )
                )
            source_location = str(carrier.get("source_location") or "").strip()
            if source_location:
                target = (
                    file_keys if self._looks_like_file(source_location) else folder_keys
                )
                target.add(self._normalized_label_source_key(source_location))
        return file_keys, folder_keys

    def _user_label_source_keys(self) -> tuple[set[str], set[str]]:
        file_keys: set[str] = set()
        folder_keys: set[str] = set()
        for source in self._extra_label_sources:
            key = self._normalized_label_source_key(source)
            if not key:
                continue
            if self._looks_like_file(source):
                file_keys.add(key)
            else:
                folder_keys.add(key)
        return file_keys, folder_keys

    def _is_auto_label_source_duplicate(self, source: str) -> bool:
        key = self._normalized_label_source_key(source)
        if not key:
            return False
        auto_file_keys, auto_folder_keys = self._auto_label_source_keys()
        if self._looks_like_file(source):
            return key in auto_file_keys
        return key in auto_folder_keys

    def _is_label_carrier_excluded(self, carrier_path: str) -> bool:
        key = self._normalized_label_source_key(carrier_path)
        if not key:
            return False
        return any(
            self._normalized_label_source_key(item) == key
            for item in self._excluded_label_carriers
        )

    def _carrier_belongs_to_source(
        self,
        carrier: dict[str, Any],
        source: str,
    ) -> bool:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return False
        carrier_path = str(carrier.get("path") or "").strip()
        if (
            carrier_path
            and self._normalized_label_source_key(carrier_path) == source_key
        ):
            return True
        source_location = str(carrier.get("source_location") or "").strip()
        if (
            source_location
            and self._normalized_label_source_key(source_location) == source_key
        ):
            return True
        if carrier_path and not self._looks_like_file(source):
            parent_key = self._normalized_label_source_key(
                Path(carrier_path).parent.as_posix()
            )
            return parent_key == source_key
        return False

    def _is_duplicate_label_source(self, source: str) -> bool:
        key = self._normalized_label_source_key(source)
        if not key:
            return False
        auto_file_keys, auto_folder_keys = self._auto_label_source_keys()
        user_file_keys, user_folder_keys = self._user_label_source_keys()
        if self._looks_like_file(source):
            parent_key = self._normalized_label_source_key(
                Path(source).parent.as_posix()
            )
            return (
                key in auto_file_keys
                or key in user_file_keys
                or parent_key in user_folder_keys
            )
        return (
            key in auto_folder_keys
            or key in user_folder_keys
            or any(
                self._normalized_label_source_key(Path(user_file).parent.as_posix())
                == key
                for user_file in user_file_keys
            )
        )

    def _add_label_file(self) -> None:
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Load label file",
            "",
            "Label/Event Files (*.mat *.csv *.tsv *.txt);;All Files (*)",
        )
        self._add_label_sources(paths)

    def _add_label_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Load label folder",
            "",
        )
        self._add_label_sources([path] if path else [])

    def _show_converted_label_table_format(self) -> None:
        dialog = _ConvertedLabelTableDialog(self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.exec()

    def _add_label_sources(self, paths: list[str]) -> None:
        changed = False
        skipped_duplicate = False
        for path in paths:
            text = str(path).strip()
            if not text:
                continue
            if self._is_duplicate_label_source(text):
                skipped_duplicate = True
                continue
            self._extra_label_sources.append(text)
            changed = True
        if changed:
            self._skip_labels = False
            self._refresh_label_source_rows()
            self.label_sources_label.setText(
                "Already included sources were skipped." if skipped_duplicate else ""
            )
            self.label_sources_label.setVisible(skipped_duplicate)
        elif skipped_duplicate:
            self.label_sources_label.setText(
                "Already included. No new label source added."
            )
            self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _skip_labels_for_now(self) -> None:
        self._skip_labels = True
        self.label_sources_label.setText(self._label_sources_status_text())
        self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _run_smart_parse(self) -> None:
        filepaths = self._metadata_filepaths_for_smart_parse()
        if not filepaths:
            return
        dialog = SmartParserDialog(filepaths, self)
        if not dialog.exec():
            return
        results = dialog.get_result()
        if not isinstance(results, dict):
            return
        self._apply_smart_parse_results(results)

    def _metadata_filepaths_for_smart_parse(self) -> list[str]:
        paths: list[str] = []
        scanned_files = [
            str(path)
            for path in self.scan_result.get("eeg_files", []) or []
            if str(path).strip()
        ]
        by_name = {Path(path).name: path for path in scanned_files}
        for tree_item, original in self._metadata_items:
            file_text = str(original.get("file") or tree_item.text(0)).strip()
            if not file_text:
                continue
            path = (
                file_text
                if Path(file_text).is_absolute()
                else by_name.get(file_text, file_text)
            )
            if path not in paths:
                paths.append(path)
        return paths

    def _apply_smart_parse_results(self, results: dict[Any, Any]) -> None:
        result_by_name = {
            Path(str(path)).name: value for path, value in results.items()
        }
        for tree_item, original in self._metadata_items:
            file_text = str(original.get("file") or tree_item.text(0)).strip()
            parsed = results.get(file_text)
            if parsed is None:
                parsed = result_by_name.get(Path(file_text).name)
            if not isinstance(parsed, (tuple, list)) or len(parsed) < 2:
                continue
            subject, session = str(parsed[0]), str(parsed[1])
            if subject and subject != "-":
                tree_item.setText(1, subject)
            if session and session != "-":
                tree_item.setText(2, session)

    def _apply_product_tree_style(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog#DataImportWizardDialog,
            QDialog#DataImportConvertedLabelDialog {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_MUTED};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 12px;
            }}
            QWidget#DataImportStepPanel,
            QStackedWidget#DataImportWizardSteps,
            QScrollArea#DataImportStepScrollArea,
            QScrollArea#DataImportStepScrollArea > QWidget,
            QScrollArea#DataImportStepScrollArea > QWidget > QWidget {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_MUTED};
            }}
            QLabel {{
                color: {Theme.TEXT_MUTED};
                background-color: transparent;
                border: none;
            }}
            QLabel#InterpretationSummary {{
                color: #e8e8e8;
                font-size: 13px;
                font-weight: 600;
                padding: 2px 0 0 0;
            }}
            QLabel#InterpretationDecision {{
                color: {Theme.TEXT_MUTED};
                padding: 2px 0 8px 0;
            }}
            QLabel#InterpretationConfirmation {{
                color: {Theme.TEXT_SECONDARY};
                padding-top: 2px;
            }}
            QFrame#DataImportPanelHeader {{
                background-color: transparent;
                border: none;
                padding: 0 0 2px 0;
            }}
            QFrame#DataImportMetadataToolHolder {{
                background-color: transparent;
                border: none;
            }}
            QLabel#DataImportPanelTitle {{
                color: #f1f1f1;
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#DataImportPanelSubtitle {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QFrame#DataImportCard,
            QFrame#DataImportMetricCard {{
                background-color: #252526;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 6px;
            }}
            QLabel#DataImportCardTitle {{
                color: #eeeeee;
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#DataImportMetricTitle,
            QLabel#DataImportSummaryLabel,
            QLabel#DataImportActionKicker {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#DataImportMetricValue {{
                color: #eeeeee;
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#DataImportMetricDetail,
            QLabel#DataImportSummaryValue,
            QLabel#DataImportActionText,
            QLabel#DataImportSourceDetail,
            QLabel#DataImportEmptyState {{
                color: {Theme.TEXT_MUTED};
                font-size: 12px;
            }}
            QLabel#DataImportInlineNotice {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0 0 2px 0;
                font-size: 12px;
            }}
            QLabel#DataImportSourceTitle,
            QLabel#DataImportActionIssue {{
                color: #eeeeee;
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#DataImportCodeBlock {{
                color: #d8ecff;
                background-color: #1b1b1b;
                border: 1px solid #343434;
                border-radius: 4px;
                padding: 7px 9px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
            }}
            QLabel#DataImportCodeInline {{
                color: #d8ecff;
                background-color: #1b1b1b;
                border: 1px solid #343434;
                border-radius: 4px;
                padding: 3px 7px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
            }}
            QLabel#DataImportStepNumber {{
                color: #f7fbff;
                background-color: #0b6ea8;
                border: 1px solid #2d8fc3;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#DataImportChecklistLine {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0;
                font-size: 12px;
            }}
            QLabel#DataImportInternalGroupTitle {{
                color: #f0f0f0;
                background-color: transparent;
                border: none;
                padding: 0 0 4px 0;
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#DataImportInternalSummaryLine,
            QLabel#DataImportInternalCheckLine {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0 0 2px 0;
                font-size: 12px;
            }}
            QWidget#DataImportEventSectionSpacer {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportSourceRow,
            QFrame#DataImportConversionActionCard,
            QFrame#DataImportFormatRequirement,
            QFrame#DataImportFormatTile,
            QFrame#DataImportFormatChecklist,
            QFrame#DataImportActionCard,
            QFrame#DataImportAlignmentOption,
            QFrame#DataImportRuleControl,
            QFrame#DataImportInlineRuleControl,
            QFrame#DataImportPairingRow,
            QFrame#DataImportEventRulesTable,
            QFrame#DataImportClassMapTable,
            QFrame#DataImportInternalLabelsTable,
            QFrame#DataImportInternalOtherEventsTable {{
                background-color: #202020;
                border: 1px solid #343434;
                border-radius: 5px;
            }}
            QFrame#DataImportPairingBlock {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportPlacementSelector,
            QFrame#DataImportPlacementSectionTitle {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportPlacementOption {{
                background-color: #202020;
                border: 1px solid #343434;
                border-radius: 5px;
            }}
            QFrame#DataImportPlacementOption[selected="true"] {{
                background-color: #17354b;
                border: 1px solid #2f6690;
            }}
            QFrame#DataImportPlacementDetail {{
                background-color: #202020;
                border: 1px solid #343434;
                border-radius: 5px;
            }}
            QFrame#DataImportTargetEventRow {{
                background-color: #1b1b1b;
                border: 1px solid #303030;
                border-radius: 5px;
            }}
            QFrame#DataImportTargetEventRow[selected="true"] {{
                background-color: #1e2f3d;
                border: 1px solid #3b79a5;
            }}
            QFrame#DataImportPairingHeader {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportClassMapEntry {{
                background-color: #202020;
                border: 1px solid #343434;
                border-radius: 5px;
            }}
            QLabel#DataImportClassCode {{
                color: #eeeeee;
                background-color: #191919;
                border: 1px solid #303030;
                border-radius: 4px;
                padding: 3px 0;
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#DataImportRuleLabel {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QFrame#DataImportLabelSourceModeControl {{
                background-color: transparent;
                border: none;
            }}
            QLabel#DataImportLabelSourceChoiceLabel {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#DataImportPairingSummary {{
                color: #eeeeee;
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#DataImportPairingCaption {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#DataImportPairingHeaderLabel {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#DataImportPairingFile {{
                color: #eeeeee;
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#DataImportPlacementOptionDetail {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                font-size: 11px;
            }}
            QLabel#DataImportTargetEventCode {{
                color: #eeeeee;
                background-color: #191919;
                border: 1px solid #303030;
                border-radius: 4px;
                padding: 3px 0;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#DataImportPairingArrow {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#DataImportPairingBadge {{
                color: #cfe8ff;
                background-color: #17354b;
                border: 1px solid #2f6690;
                border-radius: 4px;
                padding: 4px 0;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#DataImportPairingBadge[pairingState="review"] {{
                color: #ffd9a1;
                background-color: #4a341a;
                border: 1px solid #8a6429;
            }}
            QLabel#DataImportPairingNotice {{
                color: #ffd9a1;
                background-color: transparent;
                border: none;
                padding: 2px 0 0 0;
                font-size: 12px;
            }}
            QLabel#DataImportRuleStatus {{
                color: {Theme.TEXT_MUTED};
                background-color: transparent;
                border: none;
                padding: 4px 2px 0 2px;
                font-size: 12px;
            }}
            QLabel#DataImportBadge {{
                color: #cfe8ff;
                background-color: #17354b;
                border: 1px solid #2f6690;
                border-radius: 4px;
                padding: 3px 7px;
                font-size: 11px;
                font-weight: 600;
            }}
            QFrame#DataImportSummaryLine {{
                background-color: transparent;
                border: none;
                padding: 2px 0;
            }}
            QLabel#DataImportStatusLabel {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 2px 0 0 0;
                font-size: 12px;
            }}
            QLabel#DataImportStepLabel {{
                color: {Theme.TEXT_SECONDARY};
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 7px 8px;
                font-weight: 600;
            }}
            QLabel#DataImportStepLabel[stepState="active"] {{
                color: #e8e8e8;
                background-color: {Theme.BLUE_PRESSED};
                border: 1px solid {Theme.BLUE_FOCUS_BORDER};
            }}
            QLabel#DataImportStepLabel[stepState="done"] {{
                color: {Theme.TEXT_MUTED};
                background-color: #23303a;
                border: 1px solid {Theme.ACCENT_PRIMARY};
            }}
            QLabel#DataImportStepLabel[stepState="upcoming"] {{
                color: {Theme.TEXT_SECONDARY};
            }}
            QGroupBox {{
                background-color: #252526;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 6px;
                margin-top: 10px;
                padding: 8px 8px 8px 8px;
                color: #e8e8e8;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                left: 8px;
                color: #e8e8e8;
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QPushButton#DataImportPrimaryButton {{
                background-color: {Theme.BLUE_PRIMARY};
                color: #e8e8e8;
                border: 1px solid {Theme.BLUE_HOVER};
                border-radius: 4px;
                padding: 6px 14px;
                min-height: 20px;
                font-weight: 600;
            }}
            QPushButton#DataImportPrimaryButton:hover {{
                background-color: {Theme.BLUE_HOVER};
            }}
            QPushButton#DataImportPrimaryButton:pressed {{
                background-color: {Theme.BLUE_PRESSED};
            }}
            QPushButton#DataImportPrimaryButton:disabled {{
                background-color: {Theme.BTN_DISABLED_BG};
                color: {Theme.BTN_DISABLED_TEXT};
                border: 1px solid {Theme.BTN_DISABLED_BORDER};
            }}
            QPushButton#DataImportSecondaryButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }}
            QPushButton#DataImportSecondaryButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.ACCENT_PRIMARY};
                background-color: {Theme.BACKGROUND_LIGHT};
            }}
            QPushButton#DataImportSecondaryButton:disabled {{
                color: {Theme.BTN_DISABLED_TEXT};
                background-color: {Theme.BTN_DISABLED_BG};
                border: 1px solid {Theme.BTN_DISABLED_BORDER};
            }}
            QPushButton#DataImportToolButton {{
                background-color: #17354b;
                color: #e8e8e8;
                border: 1px solid #2f6690;
                border-radius: 4px;
                padding: 5px 10px;
                min-height: 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#DataImportToolButton:hover {{
                background-color: #1f4561;
                border-color: {Theme.BLUE_FOCUS_BORDER};
            }}
            QPushButton#DataImportToolButton:pressed {{
                background-color: {Theme.BLUE_PRESSED};
            }}
            QPushButton#DataImportToolButton:disabled {{
                color: {Theme.BTN_DISABLED_TEXT};
                background-color: {Theme.BTN_DISABLED_BG};
                border: 1px solid {Theme.BTN_DISABLED_BORDER};
            }}
            QPushButton#DataImportTertiaryButton {{
                background-color: transparent;
                color: {Theme.TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 5px 10px;
                min-height: 18px;
                font-size: 12px;
            }}
            QPushButton#DataImportTertiaryButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.BACKGROUND_LIGHT};
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QPushButton#DataImportTertiaryButton:pressed {{
                background-color: {Theme.BACKGROUND_MID};
            }}
            QPushButton#DataImportInlineAction {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 2px 4px;
                min-height: 16px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton#DataImportInlineAction:hover {{
                color: #d8ecff;
                border-color: #3d4d58;
                background-color: #242a2e;
            }}
            QPushButton#DataImportInlineAction:pressed {{
                background-color: #1a1f22;
            }}
            QDialogButtonBox QPushButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }}
            QDialogButtonBox QPushButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.ACCENT_PRIMARY};
                background-color: {Theme.BACKGROUND_LIGHT};
            }}
            QDialogButtonBox QPushButton#DataImportPrimaryButton {{
                background-color: {Theme.BLUE_PRIMARY};
                color: #e8e8e8;
                border: 1px solid {Theme.BLUE_HOVER};
                font-weight: 600;
            }}
            QDialogButtonBox QPushButton#DataImportPrimaryButton:hover {{
                background-color: {Theme.BLUE_HOVER};
            }}
            QFrame#DataImportFooterSeparator {{
                background-color: {Theme.BACKGROUND_LIGHT};
                border: none;
                max-height: 1px;
            }}
            QFrame#DataImportFooter {{
                background-color: transparent;
                border: none;
            }}
            QCheckBox {{
                color: {Theme.TEXT_SECONDARY};
                spacing: 8px;
            }}
            QRadioButton#DataImportPlacementRadio {{
                color: #eeeeee;
                background-color: transparent;
                border: none;
                font-size: 12px;
                font-weight: 700;
                spacing: 7px;
            }}
            QCheckBox#DataImportTargetEventCheckbox {{
                color: #eeeeee;
                background-color: transparent;
                border: none;
                font-size: 11px;
                font-weight: 600;
                spacing: 6px;
            }}
            QRadioButton::indicator,
            QCheckBox::indicator {{
                width: 12px;
                height: 12px;
            }}
            QCheckBox#DataImportTargetEventCheckbox::indicator {{
                border: 1px solid #6b6b6b;
                border-radius: 2px;
                background-color: #1b1b1b;
            }}
            QCheckBox#DataImportTargetEventCheckbox::indicator:checked {{
                border: 1px solid #2d8fc3;
                background-color: #0b6ea8;
            }}
            QTreeWidget {{
                background-color: #1f1f1f;
                alternate-background-color: #242424;
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                selection-background-color: {Theme.BLUE_PRESSED};
                selection-color: {Theme.TEXT_MUTED};
            }}
            QTreeWidget#InterpretationReviewSummary {{
                background-color: #212121;
                alternate-background-color: #232323;
            }}
            QTreeWidget::item {{
                padding: 5px 7px;
                border-bottom: 1px solid #2a2a2a;
            }}
            QHeaderView::section {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_SECONDARY};
                padding: 5px 6px;
                border: 0;
                border-right: 1px solid {Theme.BACKGROUND_LIGHT};
                border-bottom: 1px solid {Theme.BACKGROUND_LIGHT};
            }}
            QComboBox {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 3px;
                padding: 2px 6px;
                min-width: 0px;
            }}
            QComboBox:hover {{
                border-color: {Theme.ACCENT_PRIMARY};
            }}
            QScrollBar:vertical {{
                border: none;
                background: {Theme.BACKGROUND_DARK};
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.SCROLLBAR_BG};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Theme.SCROLLBAR_HANDLE};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            """
        )

    def _fit_tree_columns(
        self,
        tree: QTreeWidget,
        widths: tuple[int, ...],
        *,
        stretch_column: int,  # retained for call-site readability
    ) -> None:
        _ = stretch_column
        tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        tree.setWordWrap(False)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._apply_tree_palette(tree)
        self._tree_column_specs[id(tree)] = widths
        header = tree.header()
        if header is None:
            return
        header.setMinimumSectionSize(56)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setStretchLastSection(False)
        for column in range(len(widths)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self._fit_tree_columns_to_viewport(tree)

    def _fit_all_tree_columns_to_viewport(self) -> None:
        for tree_name in (
            "file_tree",
            "label_carrier_tree",
            "event_tree",
            "review_tree",
        ):
            tree = getattr(self, tree_name, None)
            if isinstance(tree, QTreeWidget):
                self._fit_tree_columns_to_viewport(tree)

    def _fit_tree_columns_to_viewport(self, tree: QTreeWidget) -> None:
        widths = self._tree_column_specs.get(id(tree))
        if not widths:
            return
        viewport = tree.viewport()
        if viewport is None:
            return
        header = tree.header()
        min_width = header.minimumSectionSize() if header is not None else 56
        scaled = scaled_column_widths(
            widths,
            viewport.width(),
            min_width=min_width,
        )
        self._apply_widget_column_minimums(tree, scaled, min_width, viewport.width())
        for column, width in enumerate(scaled):
            tree.setColumnWidth(column, width)
        scrollbar = tree.horizontalScrollBar()
        if scrollbar is not None:
            scrollbar.setRange(0, 0)

    @staticmethod
    def _apply_widget_column_minimums(
        tree: QTreeWidget,
        widths: list[int],
        min_width: int,
        available_width: int,
    ) -> None:
        required = [min_width for _ in widths]
        header_item = tree.headerItem()
        for column in range(min(tree.columnCount(), len(widths))):
            if header_item is not None and header_item.text(column) == "Label file":
                required[column] = max(required[column], 96)
        for row in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(row)
            if item is None:
                continue
            for column in range(min(tree.columnCount(), len(widths))):
                widget = tree.itemWidget(item, column)
                if not isinstance(widget, QComboBox):
                    continue
                text_width = widget.fontMetrics().horizontalAdvance(
                    widget.currentText()
                )
                required[column] = max(required[column], text_width + 42)

        if sum(required) > available_width:
            return

        deficits = [
            max(required_width - widths[index], 0)
            for index, required_width in enumerate(required)
        ]
        deficit = sum(deficits)
        if deficit <= 0:
            return
        for index, required_width in enumerate(required):
            widths[index] = max(widths[index], required_width)

        shrink_order = sorted(
            range(len(widths)),
            key=lambda index: widths[index] - required[index],
            reverse=True,
        )
        remaining = deficit
        for index in shrink_order:
            capacity = max(widths[index] - required[index], 0)
            if capacity <= 0:
                continue
            shrink = min(capacity, remaining)
            widths[index] -= shrink
            remaining -= shrink
            if remaining <= 0:
                break

    def _fit_review_tree_height(self) -> None:
        if not hasattr(self, "review_tree"):
            return
        self._fit_compact_tree_height(self.review_tree, min_height=92, max_height=180)

    def _fit_metadata_tree_height(self) -> None:
        if not hasattr(self, "file_tree"):
            return
        self._fit_compact_tree_height(
            self.file_tree,
            min_height=90,
            max_height=260,
            row_height_extra=2,
        )

    def _fit_label_carrier_tree_height(self) -> None:
        if not hasattr(self, "label_carrier_tree"):
            return
        self._fit_compact_tree_height(
            self.label_carrier_tree,
            min_height=96,
            max_height=220,
            row_height_extra=2,
        )

    def _fit_event_tree_height(self) -> None:
        if not hasattr(self, "event_tree"):
            return
        self._fit_compact_tree_height(
            self.event_tree,
            min_height=72,
            max_height=210,
            max_visible_rows=6,
            row_height_extra=1,
        )
        if hasattr(self, "event_group"):
            if self.event_tree.isVisible() and not self._event_detail_widgets:
                self.event_group.setMaximumHeight(self.event_tree.maximumHeight() + 36)
            else:
                self.event_group.setMaximumHeight(16777215)
                self.event_group.updateGeometry()

    @staticmethod
    def _fit_compact_tree_height(
        tree: QTreeWidget,
        *,
        min_height: int,
        max_height: int,
        max_visible_rows: int = 5,
        row_height_extra: int = 0,
    ) -> None:
        _ = max_height
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row_count = max(1, tree.topLevelItemCount())
        visible_rows = row_count
        row_heights = [
            tree.sizeHintForRow(index) for index in range(min(row_count, visible_rows))
        ]
        positive_row_heights = [height for height in row_heights if height > 0]
        row_height = (
            max(positive_row_heights) + row_height_extra
            if positive_row_heights
            else 23 + row_height_extra
        )
        header = tree.header()
        header_height = header.height() if header is not None else 28
        frame_padding = tree.frameWidth() * 2
        target_height = header_height + (visible_rows * row_height) + frame_padding + 4
        bounded_height = max(target_height, min_height)
        tree.setMinimumHeight(bounded_height)
        tree.setMaximumHeight(bounded_height)

    @staticmethod
    def _apply_tree_palette(tree: QTreeWidget) -> None:
        palette = tree.palette()
        if tree.objectName() == "InterpretationReviewSummary":
            base = QColor("#212121")
            alternate = QColor("#232323")
        else:
            base = QColor("#202020")
            alternate = QColor("#242424")
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
        palette.setColor(QPalette.ColorRole.Text, QColor(Theme.TEXT_MUTED))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(Theme.BLUE_PRESSED))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.TEXT_MUTED))
        tree.setPalette(palette)

    def _file_count(self) -> int:
        preview_count = self.preview.get("file_count")
        if preview_count is not None:
            return int(preview_count or 0)
        files = self.scan_result.get("eeg_files", []) or []
        if isinstance(files, list):
            return len(files)
        return 0

    def _label_carrier_count(self) -> int:
        preview_count = self.preview.get("label_carrier_count")
        if preview_count is not None:
            return int(preview_count or 0)
        carriers = self.scan_result.get("label_carriers", []) or []
        if isinstance(carriers, list):
            return len(carriers)
        return 0

    def _source_file_preview_text(self) -> str:
        files = self._selected_scope_file_names()
        if not files:
            return "No EEG files discovered yet."
        visible = files[:3]
        suffix = (
            f" +{len(files) - len(visible)} more" if len(files) > len(visible) else ""
        )
        return ", ".join(visible) + suffix

    def _selected_scope_file_names(self) -> list[str]:
        return self._selected_eeg_file_names()

    def _selected_eeg_file_names(self) -> list[str]:
        selected_files = self.preview.get("selected_eeg_files")
        if isinstance(selected_files, list) and selected_files:
            return [
                Path(str(path)).name for path in selected_files if str(path).strip()
            ]

        metadata_preview = self.preview.get("metadata_preview")
        if isinstance(metadata_preview, list) and metadata_preview:
            names = [
                str(item.get("file") or "").strip()
                for item in metadata_preview
                if isinstance(item, dict) and str(item.get("file") or "").strip()
            ]
            if names:
                return [Path(name).name for name in names]

        scan_files = [
            Path(str(path)).name
            for path in self.scan_result.get("eeg_files", []) or []
            if str(path).strip()
        ]
        file_count = self.preview.get("file_count")
        selection = str(self.preview.get("source_selection") or "").lower()
        if (
            isinstance(file_count, int)
            and file_count >= 0
            and "selected" in selection
            and file_count < len(scan_files)
        ):
            return scan_files[:file_count]
        return scan_files

    def _metadata_completion_counts(self) -> tuple[int, set[str]]:
        fields = ("subject", "session", "task", "run")
        complete_count = 0
        missing_fields: set[str] = set()
        for tree_item, _original in self._metadata_items:
            row_complete = True
            for column, field in enumerate(fields, start=1):
                if not tree_item.text(column).strip():
                    row_complete = False
                    missing_fields.add(field)
            if row_complete:
                complete_count += 1
        return complete_count, missing_fields

    @staticmethod
    def _metadata_missing_text(missing_fields: set[str]) -> str:
        if not missing_fields:
            return "No missing metadata fields."
        ordered = [
            field
            for field in ("subject", "session", "task", "run")
            if field in missing_fields
        ]
        return "Missing: " + ", ".join(ordered)

    def _metadata_review_summary(
        self,
        complete_count: int,
        missing_fields: set[str],
    ) -> str:
        file_count = self.file_tree.topLevelItemCount()
        file_label = "file" if file_count == 1 else "files"
        if not missing_fields:
            return f"{file_count} {file_label} · Metadata complete"
        ordered = [
            field
            for field in ("subject", "session", "task", "run")
            if field in missing_fields
        ]
        missing_text = ", ".join(ordered)
        parts = [f"{file_count} {file_label}"]
        if file_count > 1:
            parts.append(f"{complete_count} complete")
        parts.append(f"Missing {missing_text}")
        parts.append("Double-click a cell to edit")
        return " · ".join(parts)

    @staticmethod
    def _metadata_missing_hint(missing_fields: set[str]) -> str:
        if not missing_fields:
            return ""
        ordered = [
            field.capitalize()
            for field in ("subject", "session", "task", "run")
            if field in missing_fields
        ]
        field_text = ", ".join(ordered)
        verb = "is" if len(ordered) == 1 else "are"
        return f"{field_text} {verb} missing. Double-click a cell to edit it."

    def _label_source_summary_text(self) -> str:
        carriers = self.label_carrier_tree.topLevelItemCount()
        if carriers <= 0:
            return "Internal events or no labels"
        if self._extra_label_sources:
            return "Detected and loaded separately"
        return "Detected near EEG"

    def _source_selection_text(self) -> str:
        selection = str(self.preview.get("source_selection") or "").strip()
        if selection:
            return selection
        source_kind = str(self.scan_result.get("source_kind") or "").lower()
        if source_kind == "file":
            return "Single file"
        if source_kind == "bids":
            return "BIDS folder"
        if source_kind == "folder":
            return "Folder"
        return source_kind or "Unknown source"

    def _bids_status(self) -> str:
        bids = self.scan_result.get("bids") or {}
        if not isinstance(bids, dict) or not bids.get("is_bids"):
            return "Not detected"
        subjects = ", ".join(str(item) for item in bids.get("subjects", []) or [])
        events = bids.get("events_files", []) or []
        event_count = len(events) if isinstance(events, list) else 0
        subject_text = subjects or "subjects pending"
        return f"BIDS-like source, {subject_text}, {event_count} events.tsv file(s)"

    def _decision_text(self) -> str:
        if self.decision == "blocked":
            has_eeg_remap = self._has_eeg_file_remap_options()
            has_label_remap = self._has_label_carrier_remap_options()
            if has_eeg_remap and has_label_remap:
                return "Choose replacement recipe files before applying."
            if has_eeg_remap:
                return "Choose the replacement EEG file before applying."
            if has_label_remap:
                return "Choose the replacement label/event carrier before applying."
            return "This source cannot be applied yet. Review the blocked items below."
        if self.decision == "needs_confirmation":
            return "Review and confirm these choices before applying."
        if self.decision == "safe":
            return "Ready to apply."
        return "Review status is unavailable."

    def _populate_files(self) -> None:
        metadata_preview = self.preview.get("metadata_preview") or []
        if isinstance(metadata_preview, list) and metadata_preview:
            for item in metadata_preview:
                if isinstance(item, dict):
                    tree_item = QTreeWidgetItem(
                        [
                            str(item.get("file", "")),
                            self._field_value(item.get("subject")),
                            self._field_value(item.get("session")),
                            self._field_value(item.get("task")),
                            self._field_value(item.get("run")),
                        ],
                    )
                    tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    for column in range(1, 5):
                        tree_item.setToolTip(
                            column,
                            self._field_tooltip(item, column),
                        )
                    self._metadata_items.append((tree_item, dict(item)))
                    self.file_tree.addTopLevelItem(tree_item)
            return

        for file_path in self.scan_result.get("eeg_files", []) or []:
            tree_item = QTreeWidgetItem([Path(str(file_path)).name, "", "", "", ""])
            tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._metadata_items.append(
                (
                    tree_item,
                    {
                        "file": Path(str(file_path)).name,
                        "subject": {},
                        "session": {},
                        "task": {},
                        "run": {},
                    },
                )
            )
            self.file_tree.addTopLevelItem(tree_item)

    def _populate_event_tree(self) -> None:
        class_map = self._class_map_for_current_label_source()
        has_class_map = bool(class_map)
        if has_class_map:
            self.event_group.setTitle("Class names")
            for code, label in sorted(class_map.items(), key=self._class_map_sort_key):
                tree_item = QTreeWidgetItem([str(code), "class name", str(label)])
                self._class_map_items.append((tree_item, str(code), str(label)))
                self.event_tree.addTopLevelItem(tree_item)
                self._install_class_map_selector(tree_item, str(label))
            return

        self.event_group.setTitle("Event use")
        event_roles = self.preview.get("event_roles") or {}
        if isinstance(event_roles, dict):
            for name, role in event_roles.items():
                tree_item = QTreeWidgetItem(
                    [self._event_role_display_name(str(name)), "event use", str(role)]
                )
                tree_item.setToolTip(0, f"Source event field: {name}")
                self._event_role_items.append((tree_item, str(name), str(role)))
                self.event_tree.addTopLevelItem(tree_item)
                self._install_event_role_selector(tree_item, str(role))

        if self.event_tree.topLevelItemCount() == 0:
            has_carriers = bool(self.scan_result.get("label_carriers") or [])
            item_text = (
                "No additional event choices"
                if has_carriers
                else "No label/event carrier detected"
            )
            meaning = (
                "Label files are already matched above."
                if has_carriers
                else "Supervised labels require events or a later label import."
            )
            self.event_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        item_text,
                        "recording only",
                        meaning,
                    ],
                ),
            )

    def _class_map_for_current_label_source(self) -> dict[str, str]:
        class_map = self.preview.get("class_map") or {}
        if not isinstance(class_map, dict) or not class_map:
            return {}
        class_map_source = str(self.preview.get("class_map_source") or "").strip()
        if (
            hasattr(self, "label_source_mode_combo")
            and self._label_source_mode() == "internal_events"
            and class_map_source == "label_carriers"
        ):
            return {}
        return {
            str(code): str(label)
            for code, label in class_map.items()
            if str(code).strip() and str(label).strip()
        }

    def _build_class_map_rows_widget(self) -> QWidget:
        container = QFrame()
        container.setObjectName("DataImportClassMapTable")
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        container.setMinimumHeight(34 + max(len(self._class_map_items), 1) * 30)
        grid = QGridLayout(container)
        grid.setContentsMargins(10, 7, 10, 8)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        code_header = QLabel("Code")
        code_header.setObjectName("DataImportPairingHeaderLabel")
        grid.addWidget(code_header, 0, 0)
        name_header = QLabel("Class name")
        name_header.setObjectName("DataImportPairingHeaderLabel")
        grid.addWidget(name_header, 0, 1)

        for index, (item, code, _original_label) in enumerate(self._class_map_items):
            code_label = QLabel(code)
            code_label.setObjectName("DataImportPairingFile")
            code_label.setMinimumHeight(24)
            grid.addWidget(code_label, index + 1, 0)

            visible_selector = self._clone_class_map_selector(item, container)
            visible_selector.setMinimumHeight(24)
            grid.addWidget(visible_selector, index + 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 6)
        return container

    @staticmethod
    def _class_map_sort_key(item: tuple[Any, Any]) -> str:
        return str(item[0]).casefold()

    def _clone_class_map_selector(
        self,
        item: QTreeWidgetItem,
        parent: QWidget,
    ) -> QComboBox:
        hidden_selector = self._class_map_widgets[id(item)]
        selector = QComboBox(parent)
        self._prepare_table_combo(selector)
        selector.setEditable(hidden_selector.isEditable())
        selector.setToolTip(hidden_selector.toolTip())
        for index in range(hidden_selector.count()):
            selector.addItem(
                hidden_selector.itemText(index),
                hidden_selector.itemData(index),
            )
        selector.setCurrentText(hidden_selector.currentText())
        selector.currentTextChanged.connect(hidden_selector.setCurrentText)
        return selector

    def _populate_label_carrier_tree(self) -> None:
        carriers = self._label_carrier_preview_rows()

        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            match_text = self._label_carrier_match_text(carrier)
            match_display = self._label_target_display(match_text)
            original = dict(carrier)
            original["_matched_eeg_text"] = match_text
            item = QTreeWidgetItem(
                [
                    str(carrier.get("name") or Path(str(carrier.get("path", ""))).name),
                    match_display,
                    str(carrier.get("selected_label_field") or ""),
                    self._alignment_text(carrier),
                    str(carrier.get("granularity") or ""),
                    str(carrier.get("role") or "external labels"),
                ],
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(1, Qt.ItemDataRole.UserRole, match_text)
            item.setData(
                3,
                Qt.ItemDataRole.UserRole,
                str(carrier.get("selected_anchor") or ""),
            )
            item.setToolTip(1, match_text)
            item.setToolTip(2, self._candidate_tooltip(carrier, "label_candidates"))
            item.setToolTip(3, self._candidate_tooltip(carrier, "anchor_candidates"))
            item.setToolTip(4, "The data unit each label describes.")
            item.setToolTip(5, "How this label file should be used in the recipe.")
            self._label_carrier_items.append((item, original))
            self.label_carrier_tree.addTopLevelItem(item)
            self._install_label_carrier_selectors(item, carrier)
        if self.label_carrier_tree.topLevelItemCount() == 0:
            self.label_carrier_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "No external label file",
                        "Recording",
                        "Use internal events",
                        "",
                        "",
                    ],
                ),
            )

    @staticmethod
    def _field_text(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        resolved = value.get("value")
        decision = value.get("decision")
        if resolved in (None, ""):
            return str(decision or "missing")
        return f"{resolved} ({decision})" if decision else str(resolved)

    @staticmethod
    def _field_value(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        resolved = value.get("override") or value.get("value")
        if resolved in (None, ""):
            return ""
        return str(resolved)

    @staticmethod
    def _field_tooltip(item: dict[str, Any], column: int) -> str:
        field = ("subject", "session", "task", "run")[column - 1]
        value = item.get(field)
        if not isinstance(value, dict):
            return ""
        source = str(value.get("source") or "unknown")
        decision = str(value.get("decision") or "unknown")
        reason = str(value.get("reason") or "")
        return " | ".join(part for part in [source, decision, reason] if part)

    def _edited_choices(self) -> dict[str, Any]:
        choices: dict[str, Any] = {}
        metadata_overrides = self._metadata_overrides()
        if metadata_overrides:
            choices["metadata_overrides"] = metadata_overrides
        class_map = self._class_map_overrides()
        if class_map:
            choices["class_map"] = class_map
        event_roles = self._event_role_overrides()
        if self._label_source_mode() == "internal_events":
            event_roles.update(self._internal_event_role_overrides())
        if event_roles:
            choices["event_roles"] = event_roles
        eeg_file_remap = self._eeg_file_remap_choices()
        if eeg_file_remap:
            choices["eeg_file_remap"] = eeg_file_remap
        if self._excluded_label_carriers:
            choices["excluded_label_carriers"] = list(self._excluded_label_carriers)
        label_carrier_source = self._label_carrier_source_choice()
        if label_carrier_source:
            choices["label_carrier"] = label_carrier_source
        if label_carrier_source != "embedded_events":
            label_carriers = self._label_carrier_choices()
            if label_carriers:
                choices["label_carrier_choices"] = label_carriers
        label_carrier_remap = self._label_carrier_remap_choices()
        if label_carrier_remap:
            choices["label_carrier_remap"] = label_carrier_remap
        return choices

    def _label_carrier_source_choice(self) -> str:
        if not hasattr(self, "label_source_mode_combo"):
            return ""
        mode = self._label_source_mode()
        if mode == "internal_events" and self._label_carrier_items:
            return "embedded_events"
        return ""

    def _remap_choices(self) -> dict[str, dict[str, str]]:
        choices: dict[str, dict[str, str]] = {}
        eeg_file_remap = self._eeg_file_remap_choices()
        if eeg_file_remap:
            choices["eeg_file_remap"] = eeg_file_remap
        label_carrier_remap = self._label_carrier_remap_choices()
        if label_carrier_remap:
            choices["label_carrier_remap"] = label_carrier_remap
        return choices

    def _metadata_overrides(self) -> dict[str, dict[str, str]]:
        overrides: dict[str, dict[str, str]] = {}
        fields = ("subject", "session", "task", "run")
        for tree_item, original in self._metadata_items:
            file_key = str(original.get("file") or tree_item.text(0)).strip()
            if not file_key:
                continue
            changed: dict[str, str] = {}
            for column, field in enumerate(fields, start=1):
                current = tree_item.text(column).strip()
                original_value = self._field_value(original.get(field))
                if current and current != original_value:
                    changed[field] = current
            if changed:
                overrides[file_key] = changed
        return overrides

    def _class_map_overrides(self) -> dict[str, str]:
        if not self._class_map_items:
            return {}
        current = {
            code: self._class_map_item_text(tree_item).strip()
            for tree_item, code, _original in self._class_map_items
            if self._class_map_item_text(tree_item).strip()
        }
        changed = any(
            current.get(code, "") != original
            for _tree_item, code, original in self._class_map_items
        )
        return current if changed else {}

    def _install_class_map_selector(
        self,
        item: QTreeWidgetItem,
        current_value: str,
    ) -> None:
        selector = QComboBox(self.event_tree)
        self._prepare_table_combo(selector)
        selector.setEditable(True)
        selector.setToolTip("Edit the class label used for training and recipe replay.")
        seen_values: set[str] = set()
        if not current_value:
            selector.addItem("", "")
            seen_values.add("")
        for display, value in self._class_label_choices(current_value):
            if value in seen_values:
                continue
            selector.addItem(display, value)
            seen_values.add(value)
        current_index = selector.findData(current_value)
        if current_index >= 0:
            selector.setCurrentIndex(current_index)
        elif current_value:
            selector.setEditText(self._label_choice_display(current_value))
        self._class_map_widgets[id(item)] = selector
        self.event_tree.setItemWidget(item, 2, selector)

    def _class_map_item_text(self, item: QTreeWidgetItem) -> str:
        selector = self._class_map_widgets.get(id(item))
        if selector is None:
            return item.text(2)
        current_text = selector.currentText().strip()
        original_text = item.text(2).strip()
        if current_text == original_text:
            return original_text
        matching_index = selector.findText(
            current_text,
            Qt.MatchFlag.MatchFixedString,
        )
        if matching_index >= 0:
            data = selector.itemData(matching_index)
            if isinstance(data, str) and data.strip():
                return data.strip()
        return current_text.replace("_", " ").strip()

    def _event_role_overrides(self) -> dict[str, str]:
        if not self._event_role_items:
            return {}
        current = {
            name: self._event_role_item_text(tree_item).strip()
            for tree_item, name, _original in self._event_role_items
            if self._event_role_item_text(tree_item).strip()
        }
        changed = any(
            current.get(name, "") != original
            for _tree_item, name, original in self._event_role_items
        )
        return current if changed else {}

    def _internal_event_role_overrides(self) -> dict[str, str]:
        return {
            code: role
            for code, role in sorted(
                self._internal_event_user_roles.items(),
                key=lambda item: item[0].casefold(),
            )
            if role in {"class label", "not a label"}
        }

    def _install_event_role_selector(
        self,
        item: QTreeWidgetItem,
        current_value: str,
    ) -> None:
        selector = QComboBox(self.event_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip("Choose how this event should be used in the recipe.")
        choices = [
            ("Class cue", "class cue"),
            ("Class label candidate", "class label candidate"),
            ("Time anchor", "time anchor"),
            ("Trial start", "trial start"),
            ("Response", "response"),
            ("Artifact", "artifact"),
            ("Boundary", "boundary"),
            ("Run marker", "run marker"),
            ("Ignored", "ignored"),
        ]
        seen_values: set[str] = set()
        for display, value in choices:
            selector.addItem(display, value)
            seen_values.add(value)
        if current_value and current_value not in seen_values:
            selector.addItem(self._label_choice_display(current_value), current_value)
        current_index = selector.findData(current_value)
        if current_index >= 0:
            selector.setCurrentIndex(current_index)
        self._event_role_widgets[id(item)] = selector
        self.event_tree.setItemWidget(item, 2, selector)

    def _event_role_item_text(self, item: QTreeWidgetItem) -> str:
        selector = self._event_role_widgets.get(id(item))
        if selector is not None:
            value = selector.currentData()
            return str(value) if value is not None else selector.currentText()
        return item.text(2)

    def _label_carrier_choices(self) -> dict[str, dict[str, Any]]:
        choices: dict[str, dict[str, Any]] = {}
        fields = (
            ("target_file", "_matched_eeg_text", 1),
            ("label_field", "selected_label_field", 2),
            ("anchor", "selected_anchor", 3),
            ("granularity", "granularity", 4),
            ("role", "role", 5),
        )
        global_rule_values = {
            "label_field": self._combo_current_data(self.rule_label_field_combo),
            "anchor": self._combo_current_data(self.rule_alignment_combo),
            "granularity": self._combo_current_data(self.rule_label_unit_combo),
            "role": self._combo_current_data(self.rule_use_as_combo),
        }
        for item, original in self._label_carrier_items:
            carrier_key = str(
                original.get("path") or original.get("name") or ""
            ).strip()
            if not carrier_key:
                continue
            if self._is_label_carrier_excluded(carrier_key):
                continue
            changed: dict[str, str] = {}
            for choice_key, original_key, column in fields:
                current = self._label_carrier_choice_text(
                    choice_key,
                    self._label_carrier_item_text(item, column),
                )
                if self._should_use_global_label_rule(choice_key, original):
                    current = global_rule_values.get(choice_key) or current
                original_value = str(original.get(original_key) or "").strip()
                if current and current != original_value:
                    changed[choice_key] = current
            for choice_key, original_key, current in (
                (
                    "placement_method",
                    "placement_method",
                    self._combo_current_data(self.rule_placement_method_combo),
                ),
                (
                    "duration_field",
                    "selected_duration_field",
                    self._combo_current_data(self.rule_duration_field_combo),
                ),
            ):
                original_value = str(original.get(original_key) or "").strip()
                if current and current != original_value:
                    changed[choice_key] = current
            if (
                self._combo_current_data(self.rule_placement_method_combo)
                == "eeg_event"
                and self._target_eeg_event_choices()
            ):
                target_event_codes = self._event_order_target_codes()
                original_target_event_codes = [
                    str(value).strip()
                    for value in original.get("selected_target_event_codes", [])
                    if str(value).strip()
                ]
                if (
                    target_event_codes
                    and target_event_codes != original_target_event_codes
                ):
                    changed["target_event_codes"] = target_event_codes
                    changed["anchor"] = target_event_codes[0]
            if changed:
                time_model = self._time_model_for_current_label_choice(original)
                if time_model:
                    changed["time_model"] = time_model
                for choice_key, _original_key, column in fields:
                    if choice_key == "target_file":
                        continue
                    current = self._label_carrier_choice_text(
                        choice_key,
                        self._label_carrier_item_text(item, column),
                    )
                    if self._should_use_global_label_rule(choice_key, original):
                        current = global_rule_values.get(choice_key) or current
                    if current and choice_key not in changed:
                        changed[choice_key] = current
                placement_method = self._combo_current_data(
                    self.rule_placement_method_combo
                )
                if placement_method and "placement_method" not in changed:
                    changed["placement_method"] = placement_method
                duration_field = self._combo_current_data(
                    self.rule_duration_field_combo
                )
                if duration_field and "duration_field" not in changed:
                    changed["duration_field"] = duration_field
                choices[carrier_key] = changed
        return choices

    def _should_use_global_label_rule(
        self,
        choice_key: str,
        original: dict[str, Any],
    ) -> bool:
        if choice_key == "target_file":
            return False
        if self._label_rule_controls_changed:
            return True
        if choice_key != "anchor":
            return False
        if self._combo_current_data(self.rule_placement_method_combo) != "eeg_event":
            return False
        current = self._combo_current_data(self.rule_alignment_combo)
        original_anchor = str(original.get("selected_anchor") or "").strip()
        return bool(self._target_event_row(current)) and original_anchor in {
            "",
            "trial order",
        }

    @staticmethod
    def _combo_current_data(selector: QComboBox) -> str:
        value = selector.currentData()
        return str(value).strip() if value is not None else ""

    def _time_model_for_current_label_choice(self, original: dict[str, Any]) -> str:
        original_time_model = str(original.get("time_model") or "").strip()
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        anchor = self._combo_current_data(self.rule_alignment_combo).lower()
        if placement_method == "eeg_event":
            return original_time_model or "trial_order"
        if "sample" in anchor:
            return "sample_index"
        if any(token in anchor for token in ("timestamp", "lsl")):
            return "relative_time"
        if any(token in anchor for token in ("onset", "time", "latency")):
            return (
                "seconds" if self._carrier_uses_seconds(original) else "relative_time"
            )
        return original_time_model or "trial_order"

    @staticmethod
    def _carrier_uses_seconds(original: dict[str, Any]) -> bool:
        carrier_format = str(original.get("format") or "").strip()
        return carrier_format in {"BIDS events", "CSV", "TSV"}

    def _eeg_file_remap_choices(self) -> dict[str, str]:
        choices: dict[str, str] = {}
        for saved, selector in self._eeg_file_remap_widgets.items():
            value = selector.currentData()
            replacement = str(value) if value is not None else ""
            if replacement:
                choices[saved] = replacement
        return choices

    def _label_carrier_remap_choices(self) -> dict[str, str]:
        choices: dict[str, str] = {}
        for saved, selector in self._label_carrier_remap_widgets.items():
            value = selector.currentData()
            replacement = str(value) if value is not None else ""
            if replacement:
                choices[saved] = replacement
        return choices

    def _has_remap_options(self) -> bool:
        return self._has_eeg_file_remap_options() or (
            self._has_label_carrier_remap_options()
        )

    def _apply_allowed(self) -> bool:
        return self.decision != "blocked" or self._has_complete_remap_choices()

    def _has_complete_remap_choices(self) -> bool:
        option_count = len(self._eeg_file_remap_options()) + len(
            self._label_carrier_remap_options()
        )
        if option_count == 0:
            return False
        choice_count = len(self._eeg_file_remap_choices()) + len(
            self._label_carrier_remap_choices()
        )
        return choice_count == option_count

    def _sync_apply_state(self, *_args: Any) -> None:
        if not hasattr(self, "apply_button"):
            return
        apply_allowed = self._apply_allowed()
        self.apply_button.setEnabled(apply_allowed)
        if hasattr(self, "save_recipe_check"):
            was_checked = self.save_recipe_check.isChecked()
            self.save_recipe_check.setEnabled(apply_allowed)
            if not apply_allowed:
                self.save_recipe_check.setChecked(False)
            elif self.decision == "blocked" and not was_checked:
                self.save_recipe_check.setChecked(True)

    def _has_eeg_file_remap_options(self) -> bool:
        return bool(self._eeg_file_remap_options())

    def _has_label_carrier_remap_options(self) -> bool:
        return bool(self._label_carrier_remap_options())

    def _eeg_file_remap_options(self) -> list[dict[str, Any]]:
        summary = self.preview.get("recipe_reload_summary")
        if not isinstance(summary, dict):
            return []
        options = summary.get("eeg_file_remap_options") or []
        return [dict(item) for item in options if isinstance(item, dict)]

    def _label_carrier_remap_options(self) -> list[dict[str, Any]]:
        summary = self.preview.get("recipe_reload_summary")
        if not isinstance(summary, dict):
            return []
        options = summary.get("label_carrier_remap_options") or []
        return [dict(item) for item in options if isinstance(item, dict)]

    def _install_label_carrier_selectors(
        self,
        item: QTreeWidgetItem,
        carrier: dict[str, Any],
    ) -> None:
        self._set_label_choice_selector(
            item,
            2,
            self._text_choices(carrier.get("label_candidates")),
            str(carrier.get("selected_label_field") or ""),
            "Choose the label or class column for this carrier.",
        )
        self._set_label_choice_selector(
            item,
            3,
            self._text_choices(carrier.get("anchor_candidates")),
            str(carrier.get("selected_anchor") or ""),
            "Choose how label timing aligns to the EEG recording.",
        )
        self._set_label_choice_selector(
            item,
            4,
            self._label_unit_choices(),
            str(carrier.get("granularity") or ""),
            "Choose the data unit each label describes.",
        )
        self._set_label_choice_selector(
            item,
            5,
            self._label_use_choices(),
            str(carrier.get("role") or "external labels"),
            "Choose how this carrier should be used in the recipe.",
        )

    def _set_label_choice_selector(
        self,
        item: QTreeWidgetItem,
        column: int,
        choices: list[tuple[str, str]],
        current_value: str,
        tooltip: str,
    ) -> None:
        if not choices and not current_value:
            return
        selector = QComboBox(self.label_carrier_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip(tooltip)
        if not current_value:
            selector.addItem("Needs review", "")
        seen_values: set[str] = {""} if not current_value else set()
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
        self._label_choice_widgets[(id(item), column)] = selector
        self.label_carrier_tree.setItemWidget(item, column, selector)

    @staticmethod
    def _text_choices(values: Any) -> list[tuple[str, str]]:
        if not isinstance(values, list):
            return []
        choices: list[tuple[str, str]] = []
        for value in values:
            text = str(value).strip()
            if text:
                choices.append(
                    (DataInterpretationPreviewDialog._label_choice_display(text), text)
                )
        return choices

    @staticmethod
    def _alignment_text(carrier: dict[str, Any]) -> str:
        anchor = str(carrier.get("selected_anchor") or "").strip()
        time_model = str(carrier.get("time_model") or "").strip()
        if anchor and time_model:
            return f"{anchor} / {time_model.replace('_', ' ')}"
        return anchor or time_model

    @staticmethod
    def _label_choice_display(value: str) -> str:
        cleaned = value.replace("_", " ").strip()
        return cleaned[:1].upper() + cleaned[1:] if cleaned else value

    @staticmethod
    def _class_label_choices(current_value: str) -> list[tuple[str, str]]:
        common_values = [
            "left",
            "left hand",
            "right hand",
            "feet",
            "tongue",
            "rest",
            "target",
            "non-target",
            "artifact",
            "ignored",
        ]
        normalized_current = current_value.replace("_", " ").strip().lower()
        values = (
            [normalized_current, *common_values]
            if normalized_current and normalized_current not in common_values
            else common_values
        )
        return [
            (DataInterpretationPreviewDialog._label_choice_display(value), value)
            for value in values
            if value
        ]

    @staticmethod
    def _event_role_display_name(value: str) -> str:
        if value == "label_carrier":
            return "External label source"
        if value == "internal_events":
            return "Internal EEG events"
        return DataInterpretationPreviewDialog._label_choice_display(value)

    def _label_target_selector(self, current_value: str = "") -> QComboBox:
        selector = QComboBox(self.label_carrier_tree)
        self._prepare_table_combo(selector)
        selector.addItem("Choose EEG file", "")
        for file_name in self._selected_eeg_file_names():
            text = Path(str(file_name)).name
            if text:
                selector.addItem(self._label_target_display(text), text)
        current = self._label_carrier_choice_text("target_file", current_value)
        if current:
            index = selector.findData(current)
            if index >= 0:
                selector.setCurrentIndex(index)
        selector.setToolTip("Choose the EEG file this label file applies to.")
        return selector

    def _label_carrier_item_text(self, item: QTreeWidgetItem, column: int) -> str:
        if column == 1:
            selector = self._label_target_widgets.get(id(item))
            if selector is not None:
                value = selector.currentData()
                return str(value) if value is not None else selector.currentText()
            value = item.data(1, Qt.ItemDataRole.UserRole)
            if isinstance(value, str) and value:
                return value
        choice_selector = self._label_choice_widgets.get((id(item), column))
        if choice_selector is not None:
            value = choice_selector.currentData()
            return str(value) if value is not None else choice_selector.currentText()
        return item.text(column)

    @staticmethod
    def _label_target_display(text: str) -> str:
        if text in {"", "Needs review", "Recording"}:
            return text
        name = Path(text).name
        lowered = name.lower()
        if lowered.endswith(".fif.gz"):
            stem = name[: -len(".fif.gz")]
        else:
            stem = Path(name).stem
        parts = [part for part in stem.split("_") if part]
        subject = next((part for part in parts if part.startswith("sub-")), "")
        session = next((part for part in parts if part.startswith("ses-")), "")
        run = next((part for part in parts if part.startswith("run-")), "")
        task = next((part for part in parts if part.startswith("task-")), "")
        compact_parts = [part for part in (subject, session, run) if part]
        if not compact_parts and task:
            compact_parts = [task]
        if len(compact_parts) == 1 and task and not run:
            compact_parts.append(task)
        return " ".join(compact_parts) if compact_parts else name

    @staticmethod
    def _label_carrier_choice_text(choice_key: str, value: str) -> str:
        text = value.strip()
        if choice_key != "target_file":
            return text
        if text in {"", "Choose EEG file", "Needs review", "Recording"}:
            return ""
        return text

    def _label_carrier_match_text(self, carrier: dict[str, Any]) -> str:
        eeg_files = self._selected_eeg_file_names()
        carrier_path = str(carrier.get("path") or carrier.get("name") or "").strip()
        if not eeg_files:
            return "Needs review"
        if len(eeg_files) == 1:
            return Path(eeg_files[0]).name

        carrier_key = self._label_mapping_key(carrier_path)
        matches = [
            Path(eeg_file).name
            for eeg_file in eeg_files
            if self._label_mapping_key(eeg_file) == carrier_key
        ]
        if len(matches) == 1:
            return matches[0]
        return "Needs review"

    @staticmethod
    def _label_mapping_key(path: str) -> str:
        name = Path(path).name
        lowered = name.lower()
        if lowered.endswith(".fif.gz"):
            stem = name[: -len(".fif.gz")]
        else:
            stem = Path(name).stem
        normalized = stem.lower()
        for suffix in (
            "_events",
            "-events",
            "_labels",
            "-labels",
            "_label",
            "-label",
            "_raw",
            "-raw",
            "_eeg",
            "-eeg",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.strip()

    @staticmethod
    def _candidate_tooltip(carrier: dict[str, Any], key: str) -> str:
        values = carrier.get(key) or []
        if isinstance(values, list) and values:
            return "Candidates: " + ", ".join(str(value) for value in values)
        reason = str(carrier.get("reason") or "")
        return reason or "No automatic candidates were found."

    def _populate_review_tree(self) -> None:
        rows = self._review_rows()
        remap_added = False
        for remap in self._eeg_file_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = QTreeWidgetItem(
                [
                    "Review and Import",
                    "Recipe EEG file",
                    f"Saved recipe file is missing: {saved_name}.",
                    "Choose file",
                ]
            )
            tree_item.setToolTip(
                2,
                "Choose the current EEG file that replaces this saved recipe file.",
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement EEG file.",
            )
            self._eeg_file_remap_widgets[saved] = selector
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        for remap in self._label_carrier_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = QTreeWidgetItem(
                [
                    "Review and Import",
                    "Recipe label file",
                    f"Saved recipe label is missing: {saved_name}.",
                    "Choose file",
                ]
            )
            tree_item.setToolTip(
                2,
                "Choose the current label/event carrier that replaces this "
                "saved recipe carrier.",
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement label/event carrier.",
            )
            self._label_carrier_remap_widgets[saved] = selector
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        for target_step, issue, impact, next_action in rows:
            tree_item = QTreeWidgetItem([target_step, issue, impact, next_action])
            for column in range(4):
                tree_item.setToolTip(column, next_action or impact or issue)
            self.review_tree.addTopLevelItem(tree_item)
        if not rows and not remap_added:
            self.review_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "Review and Import",
                        "Import settings",
                        "No warnings or confirmations.",
                        "Import can continue.",
                    ],
                )
            )

    def _remap_selector(self, remap: dict[str, Any], tooltip: str) -> QComboBox:
        selector = QComboBox(self.review_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip(tooltip)
        selector.addItem("Choose replacement", "")
        for candidate in remap.get("candidates", []) or []:
            if not isinstance(candidate, dict):
                continue
            path = str(candidate.get("path") or "").strip()
            if not path:
                continue
            name = str(candidate.get("name") or Path(path).name or path)
            selector.addItem(name, path)
        if selector.count() == 2:
            selector.setCurrentIndex(1)
        selector.currentIndexChanged.connect(self._sync_apply_state)
        return selector

    def _review_rows(self) -> list[tuple[str, str, str, str]]:
        action_items = self._action_item_rows(
            self.preview.get("action_items")
            or self.validation_decision.get("action_items")
        )
        if action_items:
            return action_items

        rows: list[tuple[str, str, str, str]] = []
        warnings = self._unique_strings(self.preview.get("warnings"))
        confirmations = self._unique_strings(
            [
                *(self.preview.get("confirmation_items") or []),
                *(self.validation_decision.get("required_confirmations") or []),
            ]
        )
        blocked = self._unique_strings(
            self.validation_decision.get("blocked_reasons")
            or self.preview.get("blocked_reasons")
        )
        recipe_reload_summary = self.preview.get("recipe_reload_summary")
        if isinstance(recipe_reload_summary, dict) and recipe_reload_summary:
            rows.append(
                (
                    "Review and Import",
                    "Reloaded recipe",
                    str(
                        recipe_reload_summary.get("message")
                        or "Saved recipe choices were reapplied before validation."
                    ),
                    "Review any changed files before importing.",
                )
            )
            for diff_row in recipe_reload_summary.get("diff_rows", []) or []:
                if not isinstance(diff_row, dict):
                    continue
                item = str(diff_row.get("item") or "Recipe reload")
                status = str(diff_row.get("status") or "Review")
                detail = str(diff_row.get("detail") or "").strip()
                if detail:
                    rows.append(("Review and Import", item, detail, status))
        for label, status, values in (
            ("Possible issue", "Check", warnings),
            ("Required choice", "Confirm", confirmations),
            ("Cannot import yet", "Fix first", blocked),
        ):
            rows.extend(
                (
                    self._target_step_for_review_text(item),
                    label,
                    item,
                    status,
                )
                for item in values
            )
        impacts = self.preview.get(
            "downstream_impacts"
        ) or self.validation_decision.get("downstream_impacts")
        if impacts:
            rows.extend(
                (
                    "Review and Import",
                    "After import",
                    str(item),
                    "No action needed.",
                )
                for item in impacts
            )
        trace = self.preview.get("recipe_trace") or self.scan_result.get("recipe_trace")
        if trace:
            rows.extend(self._recipe_trace_rows(trace))
        format_capabilities = self.preview.get(
            "format_capabilities",
        ) or self.scan_result.get("format_capabilities")
        rows.extend(self._format_capability_rows(format_capabilities))
        return rows

    @staticmethod
    def _unique_strings(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            text = str(value)
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _action_item_rows(values: Any) -> list[tuple[str, str, str, str]]:
        if not isinstance(values, list):
            return []
        step_order = {
            "Choose EEG Data": 0,
            "Load Labels": 1,
            "Review Metadata": 2,
            "Match Labels": 3,
            "Review and Import": 4,
        }
        rows: list[tuple[str, str, str, str]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            target_step = str(value.get("target_step") or "Review and Import")
            rows.append(
                (
                    target_step,
                    str(value.get("issue") or "Review item"),
                    str(value.get("impact") or ""),
                    str(value.get("next_action") or ""),
                )
            )
        return sorted(rows, key=lambda row: (step_order.get(row[0], 99), row[1]))

    @staticmethod
    def _target_step_for_review_text(text: str) -> str:
        lowered = str(text).lower()
        if "label" in lowered or "event" in lowered:
            return "Load Labels"
        if any(token in lowered for token in ("subject", "session", "task", "run")):
            return "Review Metadata"
        if "eeg" in lowered or "source" in lowered:
            return "Choose EEG Data"
        return "Review and Import"

    @staticmethod
    def _format_capability_rows(values: Any) -> list[tuple[str, str, str, str]]:
        if not isinstance(values, list):
            return []
        grouped: dict[tuple[str, str, str], int] = {}
        for value in values:
            if not isinstance(value, dict):
                continue
            format_name = str(value.get("format") or value.get("name") or "Source")
            status = str(value.get("status") or "review").replace("_", " ")
            message = str(value.get("message") or "").strip()
            grouped[(format_name, status, message)] = (
                grouped.get((format_name, status, message), 0) + 1
            )
        rows: list[tuple[str, str, str, str]] = []
        for (format_name, status, message), count in grouped.items():
            detail = f"{format_name}: {status}."
            if count > 1:
                detail = f"{detail} {count} matching source(s)."
            if message:
                detail = f"{detail} {message}"
            rows.append(("Review and Import", "Format support", detail, "Check format"))
        return rows

    @staticmethod
    def _recipe_trace_rows(values: Any) -> list[tuple[str, str, str, str]]:
        if not isinstance(values, list):
            return []
        rows: list[tuple[str, str, str, str]] = []
        trace_labels = {
            "scan": "Source scan",
            "candidate": "Interpretation candidate",
            "preview": "Interpretation preview",
            "validate": "Validation decision",
            "validation": "Validation decision",
            "apply": "Applied interpretation",
            "metadata": "Metadata decision",
            "metadata_override": "Metadata override",
            "label": "Label decision",
            "labels": "Label decision",
            "label_carrier": "Label carrier decision",
            "label_import": "Label import",
            "class_map": "Class map decision",
            "recipe": "Recipe",
        }
        choice_labels = {
            "metadata_overrides": "Metadata choices",
            "event_roles": "Event use choices",
            "label_carriers": "Label carrier choices",
            "class_map": "Class map choices",
            "eeg_file_remap": "EEG file remap",
            "label_carrier_remap": "Label carrier remap",
            "label_sources": "Label source choices",
            "skip_labels": "Label skip choice",
        }
        for value in values:
            raw = str(value).strip()
            if not raw:
                continue
            trace_key, _, trace_detail = raw.partition(":")
            trace_key = trace_key.strip().lower()
            trace_detail = trace_detail.strip().lower()
            item = trace_labels.get(trace_key)
            if trace_key == "choices":
                item = choice_labels.get(trace_detail, "Saved choices")
            if item is None:
                item = DataInterpretationPreviewDialog._label_choice_display(trace_key)
            rows.append(
                (
                    "Review and Import",
                    item,
                    f"{item} is saved in the import recipe.",
                    "No action needed.",
                )
            )
        return rows

    def _confirmation_text(self) -> str:
        if self.decision == "blocked":
            has_eeg_remap = self._has_eeg_file_remap_options()
            has_label_remap = self._has_label_carrier_remap_options()
            if has_eeg_remap and has_label_remap:
                return (
                    "Choose replacement EEG files and label/event carriers, then "
                    "apply the remap to recheck this saved recipe."
                )
            if has_eeg_remap:
                return (
                    "Choose a replacement EEG file, then apply the remap "
                    "to recheck this saved recipe."
                )
            if has_label_remap:
                return (
                    "Choose a replacement label/event carrier, then apply the remap "
                    "to recheck this saved recipe."
                )
            return "This interpretation is blocked and cannot be applied."
        if self.decision == "needs_confirmation":
            return "Review the items marked Needs confirmation, then confirm and apply."
        if self.decision == "safe":
            return "This interpretation can be applied."
        return "Review this interpretation before applying."

    @staticmethod
    def _prepare_table_combo(selector: QComboBox) -> None:
        selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        selector.setMinimumContentsLength(1)
        selector.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
