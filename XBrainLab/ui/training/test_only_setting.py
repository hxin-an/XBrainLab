from PyQt6.QtWidgets import (
    QDialog,
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

from XBrainLab.backend.training import TestOnlyOption, parse_device_name

from .training_setting import SetDeviceWindow


class TestOnlySettingWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Test Only Setting")
        self.resize(400, 300)

        self.training_option = None
        self.output_dir = None
        self.use_cpu = None
        self.gpu_idx = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.bs_entry = QLineEdit()
        form_layout.addRow("Batch size", self.bs_entry)

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

        layout.addLayout(form_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_device(self):
        setter = SetDeviceWindow(self)
        if setter.exec() == QDialog.DialogCode.Accepted:
            self.use_cpu, self.gpu_idx = setter.get_result()
            self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))

    def set_output_dir(self):
        filepath = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if filepath:
            self.output_dir = filepath
            self.output_dir_label.setText(filepath)

    def confirm(self):
        try:
            self.training_option = TestOnlyOption(
                self.output_dir or "./output",
                self.use_cpu if self.use_cpu is not None else True,
                self.gpu_idx if self.gpu_idx is not None else 0,
                int(self.bs_entry.text()),
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Validation Error", str(e))

    def get_result(self):
        return self.training_option
