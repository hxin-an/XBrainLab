"""Training settings dialog for configuring model training parameters.

Aggregates settings for epochs, batch size, learning rate, optimizer,
device, output directory, evaluation strategy, and repeat count.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any, ClassVar

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.resource_guard import (
    TrainingResourcePreviewReceipt,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationField,
)
from XBrainLab.backend.training import (
    TrainingEvaluation,
    TrainingOption,
    parse_optim_name,
)
from XBrainLab.backend.training.input_contract import DEFAULT_TRAINING_OUTPUT_DIR
from XBrainLab.backend.training.utils import get_optimizer_classes
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.modal_message_box import ModalMessageBox as QMessageBox
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    dark_dialog_stylesheet,
    normalize_dialog_button_box,
)

from .device_setting_dialog import DeviceSettingDialog
from .optimizer_setting_dialog import OptimizerSettingDialog


class TrainingSettingDialog(BaseDialog):
    """Main configuration dialog for training parameters.

    Aggregates settings for epochs, batch size, learning rate, optimizer,
    device, output directory, evaluation strategy, and repeat count.

    Attributes:
        training_option: Configured TrainingOption after acceptance.
        output_dir: Path to the training output directory.
        optim_classes: Dictionary of available optimizer classes.
        optim: Currently selected optimizer class.
        optim_params: Dictionary of optimizer parameters.
        use_cpu: Whether to use CPU for training.
        gpu_idx: Index of the selected GPU, or None.
        epoch_entry: QLineEdit for number of training epochs.
        bs_entry: QLineEdit for batch size.
        lr_entry: QLineEdit for learning rate.
        checkpoint_entry: QLineEdit for checkpoint save interval.
        repeat_entry: QLineEdit for number of training repeats.
        evaluation_combo: QComboBox for evaluation strategy selection.

    """

    # ``dark_dialog_stylesheet`` reserves 28 px for the combo arrow in
    # addition to the shared horizontal input padding. Some native Windows
    # styles report an edit-field rectangle that excludes only part of that
    # stylesheet chrome, so keep a platform-independent lower bound too.
    _COMBO_HORIZONTAL_CHROME_FALLBACK = 64
    _EVALUATION_DISPLAY_LABELS: ClassVar[dict[TrainingEvaluation, str]] = {
        TrainingEvaluation.VAL_LOSS: "Validation loss",
        TrainingEvaluation.VAL_AUC: "Validation AUC",
        TrainingEvaluation.VAL_ACC: "Validation accuracy",
        TrainingEvaluation.LAST_EPOCH: "Last epoch",
    }

    def __init__(
        self,
        parent,
        controller,
        initial_option: Any | None = None,
        *,
        recommendation: TrainingRecommendation | None = None,
        proposed_values: dict[str, Any] | None = None,
        device_recommendation_provider: (
            Callable[[str], TrainingRecommendation | None] | None
        ) = None,
        resource_preview_request: TrainingResourcePreviewRequest | None = None,
        resource_preview_dispatcher: (
            Callable[
                [
                    TrainingResourcePreviewRequest,
                    Callable[[TrainingResourcePreviewResult], object],
                ],
                object,
            ]
            | None
        ) = None,
    ):
        # self.controller is handled by BaseDialog

        self.training_option: TrainingOption | None = None
        self.initial_option = initial_option
        self.output_dir = DEFAULT_TRAINING_OUTPUT_DIR
        self.optim_classes = get_optimizer_classes()
        self.optim = self.optim_classes.get("Adam")
        self.optim_params: dict[str, Any] = {}
        self.device = "auto"
        self.use_cpu = True
        self.gpu_idx: int | None = None
        self._recommendation: TrainingRecommendation | None = None
        self._recommendation_invalid_fields: set[TrainingRecommendationField] = set()
        self._edited_recommendation_fields: set[TrainingRecommendationField] = set()
        self._device_recommendation_provider = device_recommendation_provider
        self._device_recommendation_refresh_failed = False
        self._resource_preview_request_template = resource_preview_request
        self._resource_preview_dispatcher = resource_preview_dispatcher
        self._resource_preview_generation = (
            resource_preview_request.request_generation
            if resource_preview_request is not None
            else 0
        )
        self._resource_preview_timer: QTimer | None = None
        self._accepted_resource_preview_receipt: (
            TrainingResourcePreviewReceipt | None
        ) = None

        # UI Elements (Init them to None)
        self.epoch_entry: QLineEdit | None = None
        self.bs_entry: QLineEdit | None = None
        self.lr_entry: QLineEdit | None = None
        self.checkpoint_entry: QLineEdit | None = None
        self.repeat_entry: QLineEdit | None = None
        self.opt_label: QLabel | None = None
        self.dev_label: QLabel | None = None
        self.output_dir_label: QLabel | None = None
        self.evaluation_combo: QComboBox | None = None
        self.recommendation_note: QLabel | None = None
        self.resource_preview_note: QLabel | None = None
        self.content_scroll: QScrollArea | None = None
        self.content_widget: QWidget | None = None

        super().__init__(parent, title="Training Setting", controller=controller)
        self.setStyleSheet(dark_dialog_stylesheet())
        self._fit_dialog_to_content()

        # Set default values in UI
        if self.optim and self.opt_label:
            self.opt_label.setText(
                self._optimizer_summary(self.optim, self.optim_params)
            )
        if self.dev_label:
            self.dev_label.setText(self._device_display_name(self.device))
        if self.output_dir_label:
            self.output_dir_label.setText(self.output_dir)

        self.load_settings()
        if recommendation is not None:
            self.apply_recommendation(recommendation)
        if proposed_values:
            self.apply_proposed_values(proposed_values)
        self._connect_recommendation_tracking()
        self._initialize_resource_preview()
        self._fit_dialog_to_content()

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        """Keep the form readable after application font or DPI changes."""
        super().changeEvent(event)
        if event is not None and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        }:
            self._fit_dialog_to_content()

    def _fit_dialog_to_content(self) -> None:
        """Keep form labels readable without overlapping adjacent controls."""
        self.ensurePolished()
        labels = self.findChildren(QLabel, "TrainingSettingLabel")
        for label in labels:
            label.ensurePolished()
        label_text_width = max(
            (label.fontMetrics().horizontalAdvance(label.text()) for label in labels),
            default=128,
        )
        label_column_width = min(max(label_text_width + 24, 160), 200)
        for label in labels:
            label.setWordWrap(True)
            label.setMinimumWidth(label_column_width)
            label.setMaximumWidth(label_column_width)
            label.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Preferred,
            )
            label.setMinimumHeight(
                max(
                    label.fontMetrics().lineSpacing() + 4,
                    label.heightForWidth(label_column_width) + 4,
                )
            )
        form_layout = getattr(self, "form_layout", None)
        input_column_width = 240
        if self.evaluation_combo is not None:
            self.evaluation_combo.ensurePolished()
            metrics = self.evaluation_combo.fontMetrics()
            widest_item = max(
                (
                    metrics.horizontalAdvance(self.evaluation_combo.itemText(index))
                    for index in range(self.evaluation_combo.count())
                ),
                default=0,
            )
            fixed_dialog_width = 36 + label_column_width + 12 + 12 + 72
            screen = self.screen()
            available_dialog_width = (
                max(screen.availableGeometry().width() - 48, 1)
                if screen is not None
                else 800
            )
            input_width_ceiling = max(
                min(available_dialog_width - fixed_dialog_width, 440),
                240,
            )
            probe_width = max(
                self.evaluation_combo.width(),
                self.evaluation_combo.sizeHint().width(),
                240,
            )
            option = QStyleOptionComboBox()
            option.initFrom(self.evaluation_combo)
            option.rect = QRect(
                0,
                0,
                probe_width,
                max(self.evaluation_combo.sizeHint().height(), 1),
            )
            option.currentText = self.evaluation_combo.currentText()
            style = self.evaluation_combo.style()
            native_chrome_width = 0
            native_content_width = 0
            if style is not None:
                edit_rect = style.subControlRect(
                    QStyle.ComplexControl.CC_ComboBox,
                    option,
                    QStyle.SubControl.SC_ComboBoxEditField,
                    self.evaluation_combo,
                )
                native_chrome_width = max(probe_width - edit_rect.width(), 0)
                native_content_width = style.sizeFromContents(
                    QStyle.ContentsType.CT_ComboBox,
                    option,
                    QSize(widest_item, metrics.height()),
                    self.evaluation_combo,
                ).width()
            evaluation_width = max(
                self.evaluation_combo.sizeHint().width(),
                widest_item + native_chrome_width + 8,
                native_content_width,
                widest_item + self._COMBO_HORIZONTAL_CHROME_FALLBACK,
            )
            input_column_width = min(
                max(input_column_width, evaluation_width),
                input_width_ceiling,
            )
            self.evaluation_combo.setMinimumWidth(input_column_width)
        if form_layout is not None:
            form_layout.setColumnMinimumWidth(0, label_column_width)
            form_layout.setColumnMinimumWidth(1, input_column_width)
        target_width = max(
            520,
            36 + label_column_width + 12 + input_column_width + 12 + 72,
        )
        resource_preview_note = self.resource_preview_note
        if resource_preview_note is not None and not resource_preview_note.isHidden():
            resource_preview_note.ensurePolished()
            note_width = max(target_width - 36, 1)
            wrapped_height = resource_preview_note.heightForWidth(note_width)
            resource_preview_note.setMinimumHeight(
                max(
                    resource_preview_note.sizeHint().height(),
                    wrapped_height if wrapped_height >= 0 else 0,
                    resource_preview_note.fontMetrics().lineSpacing(),
                )
                + 4
            )
        layout = self.layout()
        if layout is not None:
            layout.activate()
        content_hint = (
            self.content_widget.sizeHint().height()
            if self.content_widget is not None
            else self.sizeHint().height()
        )
        target_height = max(390, min(content_hint + 92, 620))
        self.setMinimumSize(target_width, 390)
        self.resize(max(self.width(), target_width), max(self.height(), target_height))

    def _set_evaluation_option(self, option: Any) -> None:
        """Select one backend strategy through its compact UI label."""
        if self.evaluation_combo is None:
            return
        normalized = option
        if not isinstance(normalized, TrainingEvaluation):
            normalized = getattr(normalized, "value", normalized)
            try:
                normalized = TrainingEvaluation(str(normalized))
            except ValueError:
                return
        index = self.evaluation_combo.findData(normalized)
        if index >= 0:
            self.evaluation_combo.setCurrentIndex(index)

    def load_settings(self):
        """Load settings from a snapshot or controller compatibility."""
        opt = self.initial_option
        if opt is None:
            opt = self._compatibility_training_option()
        if opt:
            if isinstance(opt, dict):
                self._load_settings_snapshot(opt)
                return
            if self.epoch_entry:
                self.epoch_entry.setText(str(opt.epoch))
            if self.bs_entry:
                self.bs_entry.setText(str(opt.bs))
            if self.lr_entry:
                self.lr_entry.setText(str(opt.lr))
            if self.checkpoint_entry:
                self.checkpoint_entry.setText(str(opt.checkpoint_epoch))
            if self.repeat_entry:
                self.repeat_entry.setText(str(opt.repeat_num))

            # Restore optimizer
            self.optim = opt.optim
            self.optim_params = opt.optim_params
            if self.optim and self.opt_label:
                self.opt_label.setText(
                    self._optimizer_summary(self.optim, self.optim_params)
                )

            # Restore device
            restored_use_cpu = getattr(opt, "use_cpu", True)
            self.use_cpu = (
                restored_use_cpu if isinstance(restored_use_cpu, bool) else True
            )
            self.gpu_idx = opt.gpu_idx
            self.device = (
                "cpu"
                if self.use_cpu
                else f"cuda:{self.gpu_idx if self.gpu_idx is not None else 0}"
            )
            if self.dev_label:
                self.dev_label.setText(self._device_display_name(self.device))

            # Restore output dir
            self.output_dir = opt.output_dir
            if self.output_dir and self.output_dir_label:
                self.output_dir_label.setText(self.output_dir)

            # Restore evaluation
            if opt.evaluation_option and self.evaluation_combo:
                self._set_evaluation_option(opt.evaluation_option)

    def _compatibility_training_option(self) -> Any | None:
        """Read training option only for mock / compatibility dialog contexts."""
        if not self.controller:
            return None
        try:
            return run_controller_compatibility_call(
                self,
                self.controller.get_training_option,
            )
        except ControllerCompatibilityUnavailableError:
            return None

    def _load_settings_snapshot(self, option: dict[str, Any]) -> None:
        """Load saved settings from an ApplicationService state snapshot."""
        if self.epoch_entry and option.get("epoch") is not None:
            self.epoch_entry.setText(str(option["epoch"]))
        if self.bs_entry and option.get("batch_size") is not None:
            self.bs_entry.setText(str(option["batch_size"]))
        if self.lr_entry and option.get("learning_rate") is not None:
            self.lr_entry.setText(str(option["learning_rate"]))
        if self.checkpoint_entry and option.get("checkpoint_epoch") is not None:
            self.checkpoint_entry.setText(str(option["checkpoint_epoch"]))
        if self.repeat_entry and option.get("repeat") is not None:
            self.repeat_entry.setText(str(option["repeat"]))

        optimizer_name = option.get("optimizer")
        if optimizer_name:
            optimizer_key = str(optimizer_name).lower()
            self.optim = next(
                (
                    klass
                    for name, klass in self.optim_classes.items()
                    if name.lower() == optimizer_key
                ),
                self.optim,
            )
            self.optim_params = dict(option.get("optimizer_params", {}) or {})
            if self.optim and self.opt_label:
                self.opt_label.setText(
                    self._optimizer_summary(self.optim, self.optim_params)
                )

        device = str(option.get("device") or "")
        if device:
            self.device = self._normalize_device_value(device)
            self.use_cpu = not self.device.startswith("cuda")
            self.gpu_idx = self._gpu_index_from_device(self.device)
            if self.dev_label:
                self.dev_label.setText(self._device_display_name(self.device))

        output_dir = option.get("output_dir")
        if output_dir:
            self.output_dir = str(output_dir)
            if self.output_dir_label:
                self.output_dir_label.setText(self.output_dir)

        evaluation = option.get("evaluation_option")
        if evaluation and self.evaluation_combo:
            self._set_evaluation_option(evaluation)

    def apply_recommendation(
        self,
        recommendation: TrainingRecommendation,
    ) -> None:
        """Apply backend effective values while preserving draft manual fields."""
        if not isinstance(recommendation, TrainingRecommendation):
            raise TypeError("recommendation must be a TrainingRecommendation")
        effective = (
            self._recommendation.refresh_from(recommendation)
            if self._recommendation is not None
            else recommendation
        )
        self._recommendation = effective
        values = effective.values.to_mapping()
        for field, value in values.items():
            if field in self._recommendation_invalid_fields:
                continue
            self._set_recommendation_field(field, value)
        self._update_recommendation_note()

    def get_recommendation(self) -> TrainingRecommendation | None:
        """Return the current backend-owned recommendation/provenance contract."""
        return self._recommendation

    def get_edited_recommendation_fields(
        self,
    ) -> frozenset[TrainingRecommendationField]:
        """Return recommendation fields explicitly edited in this dialog."""
        return frozenset(self._edited_recommendation_fields)

    def get_device_value(self) -> str:
        """Return the detached device choice without resolving local hardware."""
        return self.device

    def get_applied_resource_preview_receipt(
        self,
    ) -> TrainingResourcePreviewReceipt | None:
        """Return proof for the resource refinement visible in this dialog."""
        return self._accepted_resource_preview_receipt

    def apply_proposed_values(self, values: dict[str, Any]) -> None:
        """Apply an explicit user/agent proposal after recommendation defaults."""
        snapshot_values = dict(values)
        if (
            "evaluation_strategy" in snapshot_values
            and "evaluation_option" not in snapshot_values
        ):
            snapshot_values["evaluation_option"] = snapshot_values[
                "evaluation_strategy"
            ]
        self._load_settings_snapshot(snapshot_values)
        proposed_fields = {
            "epoch": TrainingRecommendationField.EPOCHS,
            "batch_size": TrainingRecommendationField.BATCH_SIZE,
            "learning_rate": TrainingRecommendationField.LEARNING_RATE,
            "optimizer": TrainingRecommendationField.OPTIMIZER,
            "evaluation_option": TrainingRecommendationField.EVALUATION_STRATEGY,
            "evaluation_strategy": TrainingRecommendationField.EVALUATION_STRATEGY,
        }
        for key, field in proposed_fields.items():
            if key in values:
                self._track_recommendation_edit(field)
        if "device" in values:
            self._refresh_recommendation_for_device()

    def _connect_recommendation_tracking(self) -> None:
        """Track actual user edits without treating programmatic fills as manual."""
        for entry, field in (
            (self.epoch_entry, TrainingRecommendationField.EPOCHS),
            (self.bs_entry, TrainingRecommendationField.BATCH_SIZE),
            (self.lr_entry, TrainingRecommendationField.LEARNING_RATE),
        ):
            if entry is not None:
                entry.textEdited.connect(
                    lambda _text, target=field: self._track_recommendation_edit(target)
                )
        if self.evaluation_combo is not None:
            self.evaluation_combo.activated.connect(
                lambda _index: self._track_recommendation_edit(
                    TrainingRecommendationField.EVALUATION_STRATEGY
                )
            )

    def _track_recommendation_edit(
        self,
        field: TrainingRecommendationField,
    ) -> None:
        value = self._recommendation_field_value(field)
        self._edited_recommendation_fields.add(field)
        if field in {
            TrainingRecommendationField.BATCH_SIZE,
            TrainingRecommendationField.OPTIMIZER,
        }:
            self._accepted_resource_preview_receipt = None
        if field is TrainingRecommendationField.BATCH_SIZE:
            self._resource_preview_generation += 1
            if self.resource_preview_note is not None:
                self.resource_preview_note.clear()
                self.resource_preview_note.hide()
        if value is None:
            self._recommendation_invalid_fields.add(field)
            self._update_recommendation_note()
            return
        self._recommendation_invalid_fields.discard(field)
        recommendation = self._recommendation
        if recommendation is None:
            self._update_recommendation_note()
            return
        self._recommendation = recommendation.with_user_values({field: value})
        self._update_recommendation_note()

    def _update_recommendation_note(self) -> None:
        """Keep provenance internal; first-layer UI has no persistent note."""

    def _recommendation_field_value(
        self,
        field: TrainingRecommendationField,
    ) -> int | float | str | None:
        try:
            if field is TrainingRecommendationField.EPOCHS:
                return int(self.epoch_entry.text()) if self.epoch_entry else None
            if field is TrainingRecommendationField.BATCH_SIZE:
                return int(self.bs_entry.text()) if self.bs_entry else None
            if field is TrainingRecommendationField.LEARNING_RATE:
                return float(self.lr_entry.text()) if self.lr_entry else None
        except ValueError:
            return None
        if field is TrainingRecommendationField.OPTIMIZER:
            return str(getattr(self.optim, "__name__", self.optim) or "")
        if field is TrainingRecommendationField.EVALUATION_STRATEGY:
            if self.evaluation_combo is None:
                return None
            option = self.evaluation_combo.currentData()
            return str(getattr(option, "value", option) or "")
        return None

    def _set_recommendation_field(
        self,
        field: TrainingRecommendationField,
        value: int | float | str,
    ) -> None:
        if field is TrainingRecommendationField.EPOCHS and self.epoch_entry:
            self.epoch_entry.setText(str(int(value)))
            return
        if field is TrainingRecommendationField.BATCH_SIZE and self.bs_entry:
            self.bs_entry.setText(str(int(value)))
            return
        if field is TrainingRecommendationField.LEARNING_RATE and self.lr_entry:
            self.lr_entry.setText(format(float(value), ".12g"))
            return
        if field is TrainingRecommendationField.OPTIMIZER:
            optimizer_name = str(value).strip().casefold()
            selected = next(
                (
                    optimizer
                    for name, optimizer in self.optim_classes.items()
                    if name.casefold() == optimizer_name
                ),
                None,
            )
            if selected is not None:
                current_name = str(
                    getattr(self.optim, "__name__", self.optim) or ""
                ).casefold()
                if current_name != optimizer_name:
                    self.optim_params = {}
                self.optim = selected
                if self.opt_label is not None:
                    self.opt_label.setText(
                        self._optimizer_summary(selected, self.optim_params)
                    )
            return
        if field is TrainingRecommendationField.EVALUATION_STRATEGY:
            self._set_evaluation_option(value)

    @staticmethod
    def _gpu_index_from_device(device: str) -> int | None:
        if not device.startswith("cuda"):
            return None
        _, _, suffix = device.partition(":")
        if not suffix:
            return 0
        try:
            return int(suffix)
        except ValueError:
            return 0

    @staticmethod
    def _normalize_device_value(device: str) -> str:
        normalized = str(device or "auto").strip().lower()
        if normalized == "cpu":
            return "cpu"
        if normalized == "auto":
            return "auto"
        if normalized == "cuda":
            return "cuda:0"
        if normalized.startswith("cuda:"):
            return normalized
        return "auto"

    @staticmethod
    def _device_display_name(device: str) -> str:
        normalized = TrainingSettingDialog._normalize_device_value(device)
        if normalized == "auto":
            return "Auto"
        if normalized == "cpu":
            return "CPU"
        return f"GPU {TrainingSettingDialog._gpu_index_from_device(normalized) or 0}"

    @staticmethod
    def _optimizer_summary(optim: Any, optim_params: dict[str, Any]) -> str:
        if not optim_params:
            return str(getattr(optim, "__name__", optim))
        return parse_optim_name(optim, optim_params)

    def init_ui(self):
        """Initialize the dialog UI with training parameter controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        content_scroll = QScrollArea(self)
        self.content_scroll = content_scroll
        content_scroll.setObjectName("TrainingSettingContentScroll")
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setStyleSheet(
            "QScrollArea#TrainingSettingContentScroll, "
            "QScrollArea#TrainingSettingContentScroll > QWidget > QWidget {"
            "border: none; background: transparent;"
            "}"
        )
        content_widget = QWidget(content_scroll)
        self.content_widget = content_widget
        content_widget.setObjectName("TrainingSettingContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        form_layout = QGridLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(9)
        form_layout.setColumnMinimumWidth(0, 128)
        form_layout.setColumnStretch(1, 1)
        self.form_layout = form_layout

        def add_simple_row(row: int, label: str, widget) -> None:
            lbl = QLabel(label)
            lbl.setObjectName("TrainingSettingLabel")
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form_layout.addWidget(lbl, row, 0)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            form_layout.addWidget(widget, row, 1)

        def add_set_row(
            row: int,
            label: str,
            value_label: QLabel,
            button: QPushButton,
        ) -> None:
            lbl = QLabel(label)
            lbl.setObjectName("TrainingSettingLabel")
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value_label.setObjectName("TrainingSettingValue")
            value_label.setMinimumHeight(28)
            value_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setText("Set")
            button.setFixedWidth(72)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            form_layout.addWidget(lbl, row, 0)
            form_layout.addWidget(value_label, row, 1)
            form_layout.addWidget(button, row, 2)

        # Entries with default values for easier testing
        epoch_entry = QLineEdit("10")
        self.epoch_entry = epoch_entry
        epoch_entry.setObjectName("TrainingEpochsInput")
        add_simple_row(0, "Training epochs", epoch_entry)

        bs_entry = QLineEdit("32")
        self.bs_entry = bs_entry
        bs_entry.setObjectName("TrainingBatchSizeInput")
        add_simple_row(1, "Batch size", bs_entry)

        lr_entry = QLineEdit("0.001")
        self.lr_entry = lr_entry
        lr_entry.setObjectName("TrainingLearningRateInput")
        add_simple_row(2, "Learning rate", lr_entry)

        # Optimizer
        opt_label = QLabel("")
        self.opt_label = opt_label
        opt_label.setObjectName("TrainingOptimizerValue")
        self.opt_btn = QPushButton("Set")
        self.opt_btn.clicked.connect(self.set_optimizer)
        add_set_row(3, "Optimizer", opt_label, self.opt_btn)

        # Device
        dev_label = QLabel("")
        self.dev_label = dev_label
        dev_label.setObjectName("TrainingDeviceValue")
        self.dev_btn = QPushButton("Set")
        self.dev_btn.clicked.connect(self.set_device)
        add_set_row(4, "Device", dev_label, self.dev_btn)

        # Output Directory
        output_dir_label = QLabel("")
        self.output_dir_label = output_dir_label
        output_dir_label.setTextInteractionFlags(
            output_dir_label.textInteractionFlags()
        )
        self.out_btn = QPushButton("Set")
        self.out_btn.clicked.connect(self.set_output_dir)
        add_set_row(5, "Output directory", output_dir_label, self.out_btn)

        self.checkpoint_entry = QLineEdit("0")
        add_simple_row(
            6,
            "Checkpoint interval (training epochs)",
            self.checkpoint_entry,
        )

        # Evaluation
        evaluation_combo = QComboBox()
        self.evaluation_combo = evaluation_combo
        evaluation_combo.setObjectName("TrainingEvaluationInput")
        self.evaluation_list = [
            self._EVALUATION_DISPLAY_LABELS[option] for option in TrainingEvaluation
        ]
        for option in TrainingEvaluation:
            evaluation_combo.addItem(
                self._EVALUATION_DISPLAY_LABELS[option],
                option,
            )
        self._set_evaluation_option(TrainingEvaluation.VAL_LOSS)
        add_simple_row(7, "Evaluation", evaluation_combo)

        repeat_entry = QLineEdit("1")
        self.repeat_entry = repeat_entry
        repeat_entry.setObjectName("TrainingRepeatsInput")
        add_simple_row(8, "Repeat number", repeat_entry)

        resource_preview_note = QLabel("")
        self.resource_preview_note = resource_preview_note
        resource_preview_note.setObjectName("TrainingResourcePreviewNote")
        resource_preview_note.setWordWrap(True)
        resource_preview_note.setStyleSheet(
            "QLabel#TrainingResourcePreviewNote {"
            "color: #b9c6d4; background: transparent; padding: 2px 0;"
            "}"
        )
        resource_preview_note.hide()
        content_layout.addWidget(resource_preview_note)

        content_layout.addLayout(form_layout)

        content_layout.addStretch(1)
        content_scroll.setWidget(content_widget)
        layout.addWidget(content_scroll, stretch=1)

        # Buttons
        footer = QHBoxLayout()
        footer.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)

    def set_optimizer(self):
        """Open the optimizer setting dialog and apply the result."""
        setter = OptimizerSettingDialog(
            self,
            optimizer=self.optim,
            optimizer_params=self.optim_params,
        )
        if setter.exec():
            optim, optim_params = setter.get_result()
            if optim:  # Params can be empty
                self._resource_preview_generation += 1
                self.optim = optim
                self.optim_params = dict(optim_params or {})
                if self.opt_label:
                    self.opt_label.setText(
                        self._optimizer_summary(optim, self.optim_params)
                    )
                self._track_recommendation_edit(TrainingRecommendationField.OPTIMIZER)
                self._schedule_resource_preview()

    def set_device(self):
        """Open the device setting dialog and apply the result."""
        setter = DeviceSettingDialog(self)
        if setter.exec():
            previous_device = self.device
            use_cpu, self.gpu_idx = setter.get_result()
            self.use_cpu = bool(use_cpu)
            self.device = (
                "cpu"
                if self.use_cpu
                else f"cuda:{self.gpu_idx if self.gpu_idx is not None else 0}"
            )
            if self.dev_label:
                self.dev_label.setText(self._device_display_name(self.device))
            if self.device != previous_device:
                self._accepted_resource_preview_receipt = None
                self._resource_preview_generation += 1
                self._refresh_recommendation_for_device()

    def _refresh_recommendation_for_device(self) -> None:
        """Refresh device-sensitive defaults while retaining explicit edits."""
        if self._recommendation is None:
            return
        provider = self._device_recommendation_provider
        if provider is None:
            self._device_recommendation_refresh_failed = True
            return
        try:
            recommendation = provider(self.device)
        except Exception:
            recommendation = None
        if not isinstance(recommendation, TrainingRecommendation):
            self._device_recommendation_refresh_failed = True
            return
        self.apply_recommendation(recommendation)
        self._device_recommendation_refresh_failed = False
        self._schedule_resource_preview()

    def _initialize_resource_preview(self) -> None:
        """Start advisory refinement after deterministic fields are visible."""
        preview_timer = QTimer(self)
        self._resource_preview_timer = preview_timer
        preview_timer.setSingleShot(True)
        preview_timer.setInterval(150)
        preview_timer.timeout.connect(self._dispatch_resource_preview)
        if (
            self._resource_preview_request_template is not None
            and self._resource_preview_dispatcher is not None
        ):
            preview_timer.start(0)

    def _schedule_resource_preview(self) -> None:
        timer = self._resource_preview_timer
        if (
            timer is not None
            and self._resource_preview_request_template is not None
            and self._resource_preview_dispatcher is not None
        ):
            timer.start()

    def build_training_resource_preview_request(
        self,
    ) -> TrainingResourcePreviewRequest | None:
        """Snapshot current draft fields and advance the dialog generation."""
        template = self._resource_preview_request_template
        if template is None or self.bs_entry is None:
            return None
        try:
            batch_size = int(self.bs_entry.text())
        except ValueError:
            return None
        if batch_size <= 0:
            return None
        self._resource_preview_generation += 1
        return replace(
            template,
            request_generation=self._resource_preview_generation,
            device=self.device,
            batch_size=batch_size,
            optimizer=str(getattr(self.optim, "__name__", self.optim) or "Adam"),
        )

    def _dispatch_resource_preview(self) -> None:
        request = self.build_training_resource_preview_request()
        dispatcher = self._resource_preview_dispatcher
        if request is None or dispatcher is None:
            return
        try:
            dispatcher(request, self.apply_training_resource_preview)
        except Exception:
            return

    def apply_training_resource_preview(
        self,
        result: TrainingResourcePreviewResult,
    ) -> bool:
        """Apply only the newest reduction to a still-untouched batch field."""
        template = self._resource_preview_request_template
        if not isinstance(result, TrainingResourcePreviewResult) or template is None:
            return False
        if (
            result.request_generation != self._resource_preview_generation
            or result.publication_generation != template.publication_generation
            or TrainingRecommendationField.BATCH_SIZE
            in self._edited_recommendation_fields
            or self.bs_entry is None
        ):
            return False
        try:
            current_batch = int(self.bs_entry.text())
        except ValueError:
            return False
        if (
            current_batch != result.requested_batch_size
            or result.suggested_batch_size >= current_batch
        ):
            return False
        self.bs_entry.setText(str(result.suggested_batch_size))
        self._accepted_resource_preview_receipt = result.receipt
        if self.resource_preview_note is not None:
            self.resource_preview_note.setText(
                result.warning
                or (
                    f"Batch size was adjusted to {result.suggested_batch_size} "
                    "for the available GPU memory."
                )
            )
            self.resource_preview_note.show()
            self.resource_preview_note.updateGeometry()
            self._fit_dialog_to_content()
            self._reveal_resource_preview_note()
            QTimer.singleShot(0, self._reveal_resource_preview_note)
        return True

    def _reveal_resource_preview_note(self) -> None:
        """Keep an automatic draft change and its explanation visible together."""
        note = self.resource_preview_note
        scroll = self.content_scroll
        if note is None or scroll is None or note.isHidden():
            return
        layout = self.layout()
        if layout is not None:
            layout.activate()
        content_layout = self.content_widget.layout() if self.content_widget else None
        if content_layout is not None:
            content_layout.activate()
        scroll.ensureWidgetVisible(note, 0, 8)

    def set_output_dir(self):
        """Open a directory picker for the training output path."""
        filepath = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if filepath:
            self.output_dir = filepath
            if self.output_dir_label:
                self.output_dir_label.setText(filepath)

    def accept(self):
        """Validate all inputs, build TrainingOption, and accept the dialog.

        Raises:
            QMessageBox: Warning if input validation fails.

        """
        if self._device_recommendation_refresh_failed:
            QMessageBox.warning(
                self,
                "Training Recommendation Changed",
                "The selected device could not be reconciled with the current "
                "training recommendation. Review the settings again.",
            )
            return

        if (
            not self.evaluation_combo
            or not self.epoch_entry
            or not self.bs_entry
            or not self.lr_entry
            or not self.checkpoint_entry
            or not self.repeat_entry
        ):
            return

        selected_evaluation = self.evaluation_combo.currentData()
        evaluation_option = (
            selected_evaluation
            if isinstance(selected_evaluation, TrainingEvaluation)
            else TrainingEvaluation.VAL_LOSS
        )

        try:
            # Validate inputs
            try:
                epoch = int(self.epoch_entry.text())
                bs = int(self.bs_entry.text())
                ckpt = int(self.checkpoint_entry.text())
                repeat = int(self.repeat_entry.text())
                lr = float(self.lr_entry.text())
            except ValueError as e:
                msg = (
                    "Training epochs, Batch Size, Checkpoint, Repeat must be "
                    "integers.\n"
                    "Learning Rate must be Float."
                )
                raise ValueError(msg) from e

            if epoch <= 0 or bs <= 0:
                self._raise_value_error(
                    "Training epochs and Batch Size must be positive."
                )

            self.training_option = TrainingOption(
                self.output_dir,
                self.optim,
                self.optim_params,
                self.use_cpu,
                self.gpu_idx,
                epoch,
                bs,
                lr,
                ckpt,
                evaluation_option,
                repeat,
            )
            super().accept()
        except ValueError:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Review the numeric training values and configuration, then try again.",
            )
        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_SETTINGS,
            )

    def _raise_value_error(self, msg: str):
        """Raise a ValueError with the given message.

        Args:
            msg: Error message string.

        Raises:
            ValueError: Always raised with the provided message.

        """
        raise ValueError(msg)

    def get_result(self):
        """Return the configured training option.

        Returns:
            TrainingOption instance with all training parameters, or None.

        """
        return self.training_option
