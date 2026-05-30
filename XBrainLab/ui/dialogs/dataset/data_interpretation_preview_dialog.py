"""Preview dialog for Data Interpretation import decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPalette, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
from XBrainLab.ui.dialogs.dataset.internal_event_step import InternalEventStepMixin
from XBrainLab.ui.dialogs.dataset.label_placement_step import LabelPlacementStepMixin
from XBrainLab.ui.dialogs.dataset.load_labels_step import LoadLabelsStepMixin
from XBrainLab.ui.dialogs.dataset.review_import_step import ReviewImportStepMixin
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


class DataInterpretationPreviewDialog(
    InternalEventStepMixin,
    LabelPlacementStepMixin,
    LoadLabelsStepMixin,
    ReviewImportStepMixin,
    BaseDialog,
):
    """Show scan, metadata, warning, and validation details before apply."""

    def __init__(
        self,
        parent=None,
        scan_result: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
        validation_decision: dict[str, Any] | None = None,
        initial_step: str | None = None,
    ):
        self.scan_result = dict(scan_result or {})
        self.preview = dict(preview or {})
        self.validation_decision = dict(validation_decision or {})
        self._initial_step = str(initial_step or "")
        self._resume_step_after_accept = ""
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
        self.rule_time_model_combo: QComboBox
        self.rule_label_unit_combo: QComboBox
        self.rule_use_as_combo: QComboBox
        self.label_values_status_label: QLabel
        self.target_event_status_label: QLabel
        self.time_field_check_label: QLabel
        self.time_field_preview_empty_label: QLabel
        self.time_field_preview_caption_label: QLabel
        self.time_field_preview_row_widgets: list[QFrame]
        self.time_field_preview_row_labels: list[tuple[QLabel, QLabel]]
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
        self.review_recipe_note_label: QLabel
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
        self._review_summary_value_labels: dict[str, QLabel] = {}
        self._event_role_widgets: dict[int, QComboBox] = {}
        self._event_role_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._class_map_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._class_map_widgets: dict[int, QComboBox] = {}
        self._internal_event_user_roles: dict[str, str] = {}
        self._internal_class_name_edits: dict[str, str] = {}
        self._target_event_code_selection: list[str] = []
        self._target_event_selection_touched = False
        self._time_model_rule_touched = False
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
        if self._is_bids_like_source():
            bids_source_card, bids_source_layout = self._card("BIDS-aware import")
            self._build_bids_source_card(bids_source_layout)
            source_panel_layout.addWidget(bids_source_card)
        source_panel_layout.addStretch()
        self.step_stack.addWidget(source_panel)

        attach_panel, attach_panel_layout = self._step_panel()
        attach_panel_layout.addWidget(
            self._panel_header(
                "Load Labels",
                self._load_labels_panel_detail(),
            )
        )
        label_sources_card, label_sources_layout = self._card(
            "BIDS events detected" if self._has_bids_events() else "Label files"
        )
        self.label_sources_card_title_label = label_sources_card.findChild(
            QLabel,
            "DataImportCardTitle",
        )
        self.label_detection_label = self._wrapped_label(self._label_detection_text())
        label_sources_layout.addWidget(self.label_detection_label)
        if self._has_bids_events():
            label_sources_layout.addWidget(self._bids_label_source_summary())
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
        if self._has_bids_events():
            self.add_label_file_btn.setText("Add extra label file")
        self.add_label_file_btn.setObjectName("DataImportToolButton")
        self.add_label_file_btn.setToolTip("Load a label file from another location.")
        self.add_label_file_btn.clicked.connect(self._add_label_file)
        self.add_label_folder_btn = QPushButton("Load label folder")
        if self._has_bids_events():
            self.add_label_folder_btn.setText("Add extra label folder")
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
        self.skip_labels_btn.setVisible(not self._has_bids_events())
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
                self._metadata_panel_detail(),
            )
        )
        self.smart_parse_btn = QPushButton(
            "Adjust parsing" if self._is_bids_like_source() else "Smart Parse metadata"
        )
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
        missing_fields = self._metadata_required_missing_fields(missing_fields)
        if self._is_bids_like_source():
            bids_metadata_card, bids_metadata_layout = self._card("BIDS metadata")
            self._build_bids_metadata_card(bids_metadata_layout)
            metadata_panel_layout.addWidget(bids_metadata_card)
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

        self.bids_event_review_card, bids_event_review_layout = self._card(
            "BIDS events.tsv"
        )
        self._build_bids_event_review_card(bids_event_review_layout)
        label_panel_layout.addWidget(self.bids_event_review_card)

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

        self.confirmation_label = QLabel(self._confirmation_text())
        self.confirmation_label.setObjectName("InterpretationConfirmation")
        self.confirmation_label.setWordWrap(True)
        self.save_recipe_check = QCheckBox("Save reusable import recipe")
        self.save_recipe_check.setObjectName("DataImportSaveRecipeCheck")
        apply_allowed = self._apply_allowed()
        self.save_recipe_check.setChecked(apply_allowed)
        self.save_recipe_check.setEnabled(apply_allowed)
        self.save_recipe_check.setToolTip(
            "Save the selected source, metadata, label source, and label placement."
        )

        review_panel, review_panel_layout = self._step_panel()
        review_panel_layout.addWidget(
            self._panel_header(
                "Review and Import",
                "Review what will be imported. Epoch settings are configured later.",
            )
        )
        import_summary_card, import_summary_layout = self._card("Import summary")
        self._build_review_import_summary(import_summary_layout)
        review_panel_layout.addWidget(import_summary_card)
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
        self.apply_button.setEnabled(self._apply_allowed())
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
        self._sync_apply_state()
        self._apply_initial_step()
        self._sync_step_state()
        self._fit_all_tree_columns_to_viewport()

    def _apply_initial_step(self) -> None:
        if not self._initial_step or not hasattr(self, "step_stack"):
            return
        try:
            index = self._step_titles.index(self._initial_step)
        except ValueError:
            return
        self.step_stack.setCurrentIndex(index)

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
        loaded_label = (
            "BIDS events.tsv" if self._has_bids_events() else "Loaded label files"
        )
        choices = [
            ("Labels inside EEG files", "internal_events"),
            (loaded_label, "loaded_label_files"),
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
            if self._has_bids_events():
                return (
                    "Use BIDS events.tsv for labels and timing; add extra labels "
                    "only if this dataset needs them."
                )
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
        if hasattr(self, "bids_event_review_card"):
            self.bids_event_review_card.setVisible(
                use_loaded and bool(self._bids_event_review_rows())
            )
        for widget in (
            getattr(self, "label_values_card", None),
            getattr(self, "placement_card", None),
        ):
            if widget is not None:
                widget.setVisible(use_loaded and not fallback_visible)
        self._refresh_label_table_fallback()
        self._refresh_pairing_badges()
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
            "Label files are paired automatically; adjust individual rows below.",
        )
        self.label_match_mode_combo.setVisible(False)
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

        badge_text, badge_state = self._pairing_badge_text(selector)
        badge = QLabel(badge_text)
        badge.setObjectName("DataImportPairingBadge")
        badge.setProperty("pairingState", badge_state)
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
            badge_text, badge_state = self._pairing_badge_text(selector)
            badge.setText(badge_text)
            badge.setProperty("pairingState", badge_state)
            style = badge.style()
            if style is not None:
                style.unpolish(badge)
                style.polish(badge)
        if hasattr(self, "pairing_status_label"):
            self.pairing_status_label.setText(self._pairing_summary_text())
        self._refresh_label_rule_status()

    def _refresh_pairing_badges(self) -> None:
        for eeg_file, selector in getattr(self, "_eeg_label_widgets", {}).items():
            badge = self._eeg_label_status_widgets.get(eeg_file)
            if badge is None:
                continue
            badge_text, badge_state = self._pairing_badge_text(selector)
            badge.setText(badge_text)
            badge.setProperty("pairingState", badge_state)
            style = badge.style()
            if style is not None:
                style.unpolish(badge)
                style.polish(badge)

    def _pairing_badge_text(self, selector: QComboBox) -> tuple[str, str]:
        if not bool(selector.currentData()):
            return "Needs label", "review"
        fallback_reason = (
            self._label_table_fallback_reason()
            if hasattr(self, "rule_label_field_combo")
            else ""
        )
        if fallback_reason:
            return "Needs setup", "review"
        return "Paired", "matched"

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
        if self._label_sources_need_rescan_before_matching():
            self._resume_step_after_accept = "Review Metadata"
            self.accept()
            return
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
        self.confirmation_label.setVisible(
            final_step and bool(self.confirmation_label.text())
        )
        self.save_recipe_check.setVisible(final_step)
        self._fit_metadata_tree_height()
        self._fit_label_carrier_tree_height()
        self._fit_all_tree_columns_to_viewport()
        self._fit_event_tree_height()
        self._fit_review_tree_height()
        if final_step:
            self._refresh_review_import_summary()
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
            "confirmed": self.decision in {"safe", "needs_confirmation"}
            or (self.decision == "blocked" and self._has_complete_remap_choices()),
            "save_recipe": self.save_recipe_check.isChecked(),
            "choices": choices,
        }
        if self._extra_label_sources != self._initial_label_sources:
            result["label_sources"] = list(self._extra_label_sources)
            result["label_sources_changed"] = True
            if self._resume_step_after_accept:
                result["resume_step"] = self._resume_step_after_accept
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
        if self._has_bids_events():
            return (
                f"{self._bids_event_count_text()} will be used as the default "
                "label and timing source."
            )
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

    def _load_labels_panel_detail(self) -> str:
        if self._has_bids_events():
            return (
                "BIDS events.tsv files are detected automatically; add extra "
                "label files only if this dataset needs them."
            )
        return "Load the label files that will be matched to this EEG data."

    def _metadata_panel_detail(self) -> str:
        if self._is_bids_like_source():
            return (
                "BIDS-style subject, session, task, and run entities are saved "
                "into the recipe."
            )
        return "Subject, session, task, and run choices are saved into the recipe."

    def _user_label_source_row(self, source: str) -> tuple[str, str]:
        source_path = Path(source)
        if not self._looks_like_file(source):
            return "Loaded folder", f"Folder path: {source}"
        source_type = "File path"
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

    def _label_sources_need_rescan_before_matching(self) -> bool:
        if not hasattr(self, "step_stack"):
            return False
        load_labels_index = self._step_titles.index("Load Labels")
        return (
            self.step_stack.currentIndex() == load_labels_index
            and self._label_sources_changed()
        )

    def _initial_label_source_for(self, source: str) -> str:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return ""
        for initial_source in self._initial_label_sources:
            if self._normalized_label_source_key(initial_source) == source_key:
                return initial_source
        return ""

    def _has_extra_label_source(self, source: str) -> bool:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return False
        return any(
            self._normalized_label_source_key(item) == source_key
            for item in self._extra_label_sources
        )

    def _has_loaded_source_covering(self, source: str) -> bool:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return False
        source_parent_key = (
            self._normalized_label_source_key(Path(source).parent.as_posix())
            if self._looks_like_file(source)
            else ""
        )
        for existing_source in self._extra_label_sources:
            existing_key = self._normalized_label_source_key(existing_source)
            if not existing_key:
                continue
            if existing_key == source_key:
                return True
            if (
                source_parent_key
                and not self._looks_like_file(existing_source)
                and existing_key == source_parent_key
            ):
                return True
        return False

    def _restore_excluded_label_source(self, source: str) -> bool:
        if not self._excluded_label_carriers:
            return False
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return False
        restored_keys: set[str] = set()
        if self._looks_like_file(source):
            restored_keys.add(source_key)
        for carrier in self._label_carrier_preview_rows(include_excluded=True):
            carrier_path = str(carrier.get("path") or "").strip()
            if carrier_path and self._carrier_belongs_to_source(carrier, source):
                restored_keys.add(self._normalized_label_source_key(carrier_path))
        if not restored_keys:
            return False
        before = list(self._excluded_label_carriers)
        self._excluded_label_carriers = [
            item
            for item in self._excluded_label_carriers
            if self._normalized_label_source_key(item) not in restored_keys
        ]
        return self._excluded_label_carriers != before

    def _restored_source_is_auto_detected(self, source: str) -> bool:
        matching_carriers = [
            carrier
            for carrier in self._label_carrier_preview_rows(include_excluded=True)
            if self._carrier_belongs_to_source(carrier, source)
        ]
        if not matching_carriers:
            return False
        carrier_sources = self.scan_result.get("label_carrier_sources")
        if not isinstance(carrier_sources, dict):
            carrier_sources = {}
        for carrier in matching_carriers:
            carrier_path = str(carrier.get("path") or "").strip()
            source_kind = str(
                carrier.get("source_kind")
                or carrier_sources.get(carrier_path)
                or "auto",
            ).strip()
            if source_kind != "auto":
                return False
        return True

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
        restored_source = False
        for path in paths:
            text = str(path).strip()
            if not text:
                continue
            if self._restore_excluded_label_source(text):
                initial_source = self._initial_label_source_for(text)
                if self._has_loaded_source_covering(text):
                    pass
                elif initial_source and not self._has_extra_label_source(
                    initial_source
                ):
                    self._extra_label_sources.append(initial_source)
                elif not self._restored_source_is_auto_detected(
                    text
                ) and not self._has_extra_label_source(text):
                    self._extra_label_sources.append(text)
                restored_source = True
                changed = True
                continue
            if self._is_duplicate_label_source(text):
                skipped_duplicate = True
                continue
            self._extra_label_sources.append(text)
            changed = True
        if changed:
            self._skip_labels = False
            self._refresh_label_source_rows()
            self._refresh_label_matching_after_source_change()
            self._select_loaded_label_source_if_available()
            self.label_sources_label.setText(
                "Label source restored."
                if restored_source
                else "Already included sources were skipped."
                if skipped_duplicate
                else ""
            )
            self.label_sources_label.setVisible(restored_source or skipped_duplicate)
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
            parsed_fields = self._normalized_smart_parse_fields(parsed)
            if not parsed_fields:
                continue
            for offset, field in enumerate(("subject", "session", "task", "run"), 1):
                value = parsed_fields.get(field, "")
                if value and value != "-":
                    tree_item.setText(offset, value)

    @staticmethod
    def _normalized_smart_parse_fields(parsed: Any) -> dict[str, str]:
        if isinstance(parsed, dict):
            return {
                field: str(parsed.get(field) or "").strip()
                for field in ("subject", "session", "task", "run")
            }
        if not isinstance(parsed, (tuple, list)) or len(parsed) < 2:
            return {}
        values = [str(value or "").strip() for value in parsed[:4]]
        values.extend([""] * (4 - len(values)))
        return dict(zip(("subject", "session", "task", "run"), values, strict=False))

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
            QLabel#DataImportActionMeta,
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
            QLabel#DataImportStepChip {{
                color: #d8ecff;
                background-color: #17354b;
                border: 1px solid #2f6690;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QWidget#DataImportEventSectionSpacer {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportSourceRow,
            QFrame#DataImportSourceScopeRow,
            QFrame#DataImportConversionActionCard,
            QFrame#DataImportFormatRequirement,
            QFrame#DataImportFormatTile,
            QFrame#DataImportFormatChecklist,
            QFrame#DataImportActionCard,
            QFrame#DataImportAlignmentOption,
            QFrame#DataImportRuleControl,
            QFrame#DataImportInlineRuleControl,
            QFrame#DataImportPairingRow,
            QFrame#DataImportTimePreviewTable,
            QFrame#DataImportTimeCheckPanel,
            QFrame#DataImportEventRulesTable,
            QFrame#DataImportClassMapTable,
            QFrame#DataImportInternalLabelsTable,
            QFrame#DataImportInternalOtherEventsTable,
            QFrame#DataImportApplyConfirmPanel {{
                background-color: #202020;
                border: 1px solid #343434;
                border-radius: 5px;
            }}
            QFrame#DataImportSourceScopeRow {{
                background-color: #1b242b;
                border: 1px solid #2a3f4f;
            }}
            QLabel#DataImportSourceScopeText {{
                color: {Theme.TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0;
                font-size: 12px;
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
            QFrame#DataImportTimePreviewHeader {{
                background-color: transparent;
                border: none;
            }}
            QFrame#DataImportTimePreviewRow {{
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
            QLabel#DataImportTimePreviewTime {{
                color: #eeeeee;
                background-color: transparent;
                border: none;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#DataImportTimePreviewValue {{
                color: #eeeeee;
                background-color: transparent;
                border: none;
                font-size: 12px;
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
            QFrame#DataImportSummaryCell {{
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
                background-color: #243240;
                color: #d8ecff;
                border: 1px solid #3b5f7b;
                border-radius: 4px;
                padding: 4px 9px;
                min-height: 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#DataImportInlineAction:hover {{
                background-color: #2b3d4e;
                border-color: #4b7798;
            }}
            QPushButton#DataImportInlineAction:pressed {{
                background-color: #1f2b36;
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
            QCheckBox#DataImportSaveRecipeCheck {{
                color: #e8e8e8;
                font-size: 12px;
                font-weight: 600;
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

    def _metadata_required_missing_fields(self, missing_fields: set[str]) -> set[str]:
        required = set(missing_fields)
        required.discard("session")
        required.discard("run")
        return required

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
        return f"{self._bids_entities_summary_text()} · {self._bids_event_count_text()}"

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
            return "Review these choices before applying."
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
        selector.setPlaceholderText("Optional class name")
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
        event_roles = self.preview.get("event_roles")
        has_internal_evidence = (
            bool(self._selected_eeg_file_names())
            or bool(self._internal_event_preview_payload())
            or (
                isinstance(event_roles, dict)
                and "internal_events" in {str(key) for key in event_roles}
            )
        )
        if mode == "internal_events" and has_internal_evidence:
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
            changed: dict[str, Any] = {}
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
        selector.setPlaceholderText("Optional class name")
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
            changed: dict[str, Any] = {}
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
            placement_method = self._combo_current_data(
                self.rule_placement_method_combo
            )
            current_time_model = self._time_model_for_current_label_choice(original)
            original_time_model = str(original.get("time_model") or "").strip()
            if (
                placement_method == "time_field"
                and current_time_model
                and current_time_model != original_time_model
            ):
                changed["time_model"] = current_time_model
            if placement_method == "eeg_event" and self._target_eeg_event_choices():
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
        if placement_method == "time_field" and hasattr(
            self,
            "rule_time_model_combo",
        ):
            explicit = self._combo_current_data(self.rule_time_model_combo)
            if explicit:
                return explicit
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
