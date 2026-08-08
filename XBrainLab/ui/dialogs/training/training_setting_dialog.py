"""Training settings dialog for configuring model training parameters.

Aggregates settings for epochs, batch size, learning rate, optimizer,
device, output directory, evaluation strategy, and repeat count.
"""

from typing import Any

from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QVBoxLayout,
)

from XBrainLab.backend.training import (
    TrainingEvaluation,
    TrainingOption,
    parse_device_name,
    parse_optim_name,
)
from XBrainLab.backend.training.input_contract import DEFAULT_TRAINING_OUTPUT_DIR
from XBrainLab.backend.training.utils import (
    get_device_count,
    get_optimizer_classes,
)
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
    run_controller_compatibility_call,
)
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

    def __init__(self, parent, controller, initial_option: Any | None = None):
        # self.controller is handled by BaseDialog

        self.training_option: TrainingOption | None = None
        self.initial_option = initial_option
        self.output_dir = DEFAULT_TRAINING_OUTPUT_DIR
        self.optim_classes = get_optimizer_classes()
        self.optim = self.optim_classes.get("Adam")
        self.optim_params: dict[str, Any] = {}
        self.use_cpu, self.gpu_idx = self._default_device()

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

        super().__init__(parent, title="Training Setting", controller=controller)
        self.setStyleSheet(dark_dialog_stylesheet())
        self._fit_dialog_to_content()

        # Set default values in UI
        if self.optim and self.opt_label:
            self.opt_label.setText(
                self._optimizer_summary(self.optim, self.optim_params)
            )
        if self.dev_label:
            self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))
        if self.output_dir_label:
            self.output_dir_label.setText(self.output_dir)

        self.load_settings()

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
        label_text_width = max(
            (label.fontMetrics().horizontalAdvance(label.text()) for label in labels),
            default=128,
        )
        label_column_width = min(max(label_text_width + 24, 160), 260)
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
            if style is not None:
                edit_rect = style.subControlRect(
                    QStyle.ComplexControl.CC_ComboBox,
                    option,
                    QStyle.SubControl.SC_ComboBoxEditField,
                    self.evaluation_combo,
                )
                native_chrome_width = max(probe_width - edit_rect.width(), 0)
            evaluation_width = max(
                self.evaluation_combo.sizeHint().width(),
                widest_item + native_chrome_width + 8,
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
        layout = self.layout()
        if layout is not None:
            layout.activate()
        target_height = max(390, self.sizeHint().height())
        self.setMinimumSize(target_width, target_height)
        self.resize(max(self.width(), target_width), max(self.height(), target_height))

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
            self.use_cpu = opt.use_cpu
            self.gpu_idx = opt.gpu_idx
            if self.dev_label:
                self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))

            # Restore output dir
            self.output_dir = opt.output_dir
            if self.output_dir and self.output_dir_label:
                self.output_dir_label.setText(self.output_dir)

            # Restore evaluation
            if opt.evaluation_option and self.evaluation_combo:
                self.evaluation_combo.setCurrentText(opt.evaluation_option.value)

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
            self.use_cpu = not device.startswith("cuda")
            self.gpu_idx = self._gpu_index_from_device(device)
            if self.dev_label:
                self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))

        output_dir = option.get("output_dir")
        if output_dir:
            self.output_dir = str(output_dir)
            if self.output_dir_label:
                self.output_dir_label.setText(self.output_dir)

        evaluation = option.get("evaluation_option")
        if evaluation and self.evaluation_combo:
            self.evaluation_combo.setCurrentText(str(evaluation))

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
    def _optimizer_summary(optim: Any, optim_params: dict[str, Any]) -> str:
        if not optim_params:
            return str(getattr(optim, "__name__", optim))
        return parse_optim_name(optim, optim_params)

    @staticmethod
    def _default_device() -> tuple[bool, int | None]:
        try:
            count = get_device_count()
        except Exception:
            return True, None
        if count > 0:
            return False, count - 1
        return True, None

    def init_ui(self):
        """Initialize the dialog UI with training parameter controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
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
        self.epoch_entry = QLineEdit("10")
        add_simple_row(0, "Training epochs", self.epoch_entry)

        self.bs_entry = QLineEdit("32")
        add_simple_row(1, "Batch size", self.bs_entry)

        self.lr_entry = QLineEdit("0.001")
        add_simple_row(2, "Learning rate", self.lr_entry)

        # Optimizer
        self.opt_label = QLabel("")
        self.opt_btn = QPushButton("Set")
        self.opt_btn.clicked.connect(self.set_optimizer)
        add_set_row(3, "Optimizer", self.opt_label, self.opt_btn)

        # Device
        self.dev_label = QLabel("")
        self.dev_btn = QPushButton("Set")
        self.dev_btn.clicked.connect(self.set_device)
        add_set_row(4, "Device", self.dev_label, self.dev_btn)

        # Output Directory
        self.output_dir_label = QLabel("")
        self.output_dir_label.setTextInteractionFlags(
            self.output_dir_label.textInteractionFlags()
        )
        self.out_btn = QPushButton("Set")
        self.out_btn.clicked.connect(self.set_output_dir)
        add_set_row(5, "Output directory", self.output_dir_label, self.out_btn)

        self.checkpoint_entry = QLineEdit("0")
        add_simple_row(
            6,
            "Checkpoint interval (training epochs)",
            self.checkpoint_entry,
        )

        # Evaluation
        self.evaluation_combo = QComboBox()
        self.evaluation_list = [i.value for i in TrainingEvaluation]
        self.evaluation_combo.addItems(self.evaluation_list)
        self.evaluation_combo.setCurrentText(TrainingEvaluation.VAL_LOSS.value)
        add_simple_row(7, "Evaluation", self.evaluation_combo)

        self.repeat_entry = QLineEdit("1")
        add_simple_row(8, "Repeat number", self.repeat_entry)

        layout.addLayout(form_layout)

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
        setter = OptimizerSettingDialog(self)
        if setter.exec():
            optim, optim_params = setter.get_result()
            if optim:  # Params can be empty
                self.optim = optim
                self.optim_params = dict(optim_params or {})
                if self.opt_label:
                    self.opt_label.setText(
                        self._optimizer_summary(optim, self.optim_params)
                    )

    def set_device(self):
        """Open the device setting dialog and apply the result."""
        setter = DeviceSettingDialog(self)
        if setter.exec():
            self.use_cpu, self.gpu_idx = setter.get_result()
            if self.dev_label:
                self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))

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
        if (
            not self.evaluation_combo
            or not self.epoch_entry
            or not self.bs_entry
            or not self.lr_entry
            or not self.checkpoint_entry
            or not self.repeat_entry
        ):
            return

        evaluation_option = TrainingEvaluation.VAL_LOSS
        for i in TrainingEvaluation:
            if i.value == self.evaluation_combo.currentText():
                evaluation_option = i

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
