"""Training settings dialog for configuring model training parameters.

Aggregates settings for epochs, batch size, learning rate, optimizer,
device, output directory, evaluation strategy, and repeat count.
"""

from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.backend.training import (
    TrainingEvaluation,
    TrainingOption,
    parse_device_name,
    parse_optim_name,
)
from XBrainLab.backend.training.utils import (
    get_optimizer_classes,
)
from XBrainLab.ui.core.base_dialog import BaseDialog

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

    def __init__(self, parent, controller):
        # self.controller is handled by BaseDialog

        self.training_option = None
        self.output_dir = "./output"
        self.optim_classes = get_optimizer_classes()
        self.optim = self.optim_classes.get("Adam")
        self.optim_params: dict[str, Any] = {}
        self.use_cpu = True
        self.gpu_idx = None

        # UI Elements (Init them to None)
        self.epoch_entry = None
        self.bs_entry = None
        self.lr_entry = None
        self.checkpoint_entry = None
        self.repeat_entry = None
        self.opt_label = None
        self.dev_label = None
        self.output_dir_label = None
        self.evaluation_combo = None

        super().__init__(parent, title="Training Setting", controller=controller)
        self.resize(500, 600)

        # Set default values in UI
        if self.optim and self.opt_label:
            self.opt_label.setText(parse_optim_name(self.optim, self.optim_params))
        if self.dev_label:
            self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))
        if self.output_dir_label:
            self.output_dir_label.setText(self.output_dir)

        self.load_settings()

    def load_settings(self):
        """Load previously saved training settings from the controller."""
        if not self.controller:
            return
        opt = self.controller.get_training_option()
        if opt:
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
            if self.optim and self.optim_params and self.opt_label:
                self.opt_label.setText(parse_optim_name(self.optim, self.optim_params))

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

    def init_ui(self):
        """Initialize the dialog UI with training parameter controls."""
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Entries with default values for easier testing
        self.epoch_entry = QLineEdit("10")
        form_layout.addRow("Epoch", self.epoch_entry)

        self.bs_entry = QLineEdit("32")
        form_layout.addRow("Batch size", self.bs_entry)

        self.lr_entry = QLineEdit("0.001")
        form_layout.addRow("Learning rate", self.lr_entry)

        # Optimizer
        optim_layout = QHBoxLayout()
        self.opt_label = QLabel("")
        optim_layout.addWidget(self.opt_label)
        self.opt_btn = QPushButton("set")
        self.opt_btn.clicked.connect(self.set_optimizer)
        optim_layout.addWidget(self.opt_btn)
        form_layout.addRow("Optimizer", optim_layout)

        # Device
        dev_layout = QHBoxLayout()
        self.dev_label = QLabel("")
        dev_layout.addWidget(self.dev_label)
        self.dev_btn = QPushButton("set")
        self.dev_btn.clicked.connect(self.set_device)
        dev_layout.addWidget(self.dev_btn)
        form_layout.addRow("device", dev_layout)

        # Output Directory
        out_layout = QHBoxLayout()
        self.output_dir_label = QLabel("")
        out_layout.addWidget(self.output_dir_label)
        self.out_btn = QPushButton("set")
        self.out_btn.clicked.connect(self.set_output_dir)
        out_layout.addWidget(self.out_btn)
        form_layout.addRow("Output Directory", out_layout)

        self.checkpoint_entry = QLineEdit("1")
        form_layout.addRow("CheckPoint epoch", self.checkpoint_entry)

        # Evaluation
        self.evaluation_combo = QComboBox()
        self.evaluation_list = [i.value for i in TrainingEvaluation]
        self.evaluation_combo.addItems(self.evaluation_list)
        self.evaluation_combo.setCurrentIndex(2)  # Default: Best testing performance
        form_layout.addRow("Evaluation", self.evaluation_combo)

        self.repeat_entry = QLineEdit("1")
        form_layout.addRow("Repeat Number", self.repeat_entry)

        layout.addLayout(form_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_optimizer(self):
        """Open the optimizer setting dialog and apply the result."""
        setter = OptimizerSettingDialog(self)
        if setter.exec():
            optim, optim_params = setter.get_result()
            if optim:  # Params can be empty
                self.optim = optim
                self.optim_params = optim_params
                if self.opt_label:
                    self.opt_label.setText(parse_optim_name(optim, optim_params))

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

        evaluation_option = TrainingEvaluation.TEST_ACC
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
                    "Epoch, Batch Size, Checkpoint, Repeat must be Integers.\n"
                    "Learning Rate must be Float."
                )
                raise ValueError(msg) from e

            if epoch <= 0 or bs <= 0:
                self._raise_value_error("Epoch and Batch Size must be positive.")

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
        except Exception as e:
            QMessageBox.warning(self, "Validation Error", str(e))

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
