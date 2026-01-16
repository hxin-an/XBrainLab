from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.training import (
    TRAINING_EVALUATION,
    TrainingOption,
    parse_device_name,
    parse_optim_name,
)
from XBrainLab.backend.training.utils import (
    get_device_count,
    get_device_name,
    get_optimizer_classes,
    get_optimizer_params,
    instantiate_optimizer,
)


class TrainingSettingWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Training Setting")
        self.resize(500, 600)

        self.training_option = None
        self.output_dir = "./output"  # Default output directory
        self.optim_classes = get_optimizer_classes()
        self.optim = self.optim_classes.get('Adam')  # Default optimizer: Adam
        self.optim_params = {}  # Default: no extra params (lr is separate)
        self.use_cpu = True  # Default: use CPU
        self.gpu_idx = None

        self.init_ui()
        # Set default values in UI
        self.opt_label.setText(parse_optim_name(self.optim, self.optim_params))
        self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))
        self.output_dir_label.setText(self.output_dir)
        self.load_settings()

    def load_settings(self):
        if hasattr(self.parent(), 'study') and self.parent().study.training_option:
            opt = self.parent().study.training_option
            self.epoch_entry.setText(str(opt.epoch))
            self.bs_entry.setText(str(opt.bs))
            self.lr_entry.setText(str(opt.lr))
            self.checkpoint_entry.setText(str(opt.checkpoint_epoch))
            self.repeat_entry.setText(str(opt.repeat_num))

            # Restore optimizer
            self.optim = opt.optim
            self.optim_params = opt.optim_params
            if self.optim and self.optim_params:
                self.opt_label.setText(parse_optim_name(self.optim, self.optim_params))

            # Restore device
            self.use_cpu = opt.use_cpu
            self.gpu_idx = opt.gpu_idx
            self.dev_label.setText(parse_device_name(self.use_cpu, self.gpu_idx))

            # Restore output dir
            self.output_dir = opt.output_dir
            if self.output_dir:
                self.output_dir_label.setText(self.output_dir)

            # Restore evaluation
            if opt.evaluation_option:
                self.evaluation_combo.setCurrentText(opt.evaluation_option.value)

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Entries with default values for easier testing
        self.epoch_entry = QLineEdit("10")  # Default: 10 epochs
        form_layout.addRow("Epoch", self.epoch_entry)

        self.bs_entry = QLineEdit("32")  # Default: batch size 32
        form_layout.addRow("Batch size", self.bs_entry)

        self.lr_entry = QLineEdit("0.001")  # Default: learning rate 0.001
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

        self.checkpoint_entry = QLineEdit("1")  # Default: checkpoint every 1 epoch
        form_layout.addRow("CheckPoint epoch", self.checkpoint_entry)

        # Evaluation
        self.evaluation_combo = QComboBox()
        self.evaluation_list = [i.value for i in TRAINING_EVALUATION]
        self.evaluation_combo.addItems(self.evaluation_list)
        self.evaluation_combo.setCurrentIndex(2)  # Default: Best testing performance
        form_layout.addRow("Evaluation", self.evaluation_combo)

        self.repeat_entry = QLineEdit("1")  # Default: 1 repeat
        form_layout.addRow("Repeat Number", self.repeat_entry)

        layout.addLayout(form_layout)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_optimizer(self):
        setter = SetOptimizerWindow(self)
        if setter.exec() == QDialog.DialogCode.Accepted:
            optim, optim_params = setter.get_result()
            if optim and optim_params:
                self.optim = optim
                self.optim_params = optim_params
                self.opt_label.setText(parse_optim_name(optim, optim_params))

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
        evaluation_option = None
        for i in TRAINING_EVALUATION:
            if i.value == self.evaluation_combo.currentText():
                evaluation_option = i

        try:
            self.training_option = TrainingOption(
                self.output_dir, self.optim, self.optim_params,
                self.use_cpu, self.gpu_idx,
                self.epoch_entry.text(),
                self.bs_entry.text(),
                self.lr_entry.text(),
                self.checkpoint_entry.text(),
                evaluation_option,
                self.repeat_entry.text()
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Validation Error", str(e))

    def get_result(self):
        return self.training_option


class SetOptimizerWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Optimizer Setting")
        self.resize(400, 500)

        self.optim = None
        self.optim_params = None

        self.algo_map = get_optimizer_classes()

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Algorithm Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Algorithm"))
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(list(self.algo_map.keys()))
        self.algo_combo.currentTextChanged.connect(self.on_algo_select)
        top_layout.addWidget(self.algo_combo)
        layout.addLayout(top_layout)

        # Parameters Table
        group = QGroupBox("Parameters")
        group_layout = QVBoxLayout(group)
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        group_layout.addWidget(self.params_table)
        layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Init with first algo
        if self.algo_map:
            self.on_algo_select(list(self.algo_map.keys())[0])

    def on_algo_select(self, algo_name):
        target = self.algo_map[algo_name]
        self.params_table.setRowCount(0)

        if target:
            rows = get_optimizer_params(target)

            self.params_table.setRowCount(len(rows))
            for i, (param, val) in enumerate(rows):
                item_param = QTableWidgetItem(param)
                item_param.setFlags(item_param.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.params_table.setItem(i, 0, item_param)
                self.params_table.setItem(i, 1, QTableWidgetItem(val))

    def confirm(self):
        optim_params = {}
        target = self.algo_map[self.algo_combo.currentText()]

        try:
            for row in range(self.params_table.rowCount()):
                param = self.params_table.item(row, 0).text()
                value_text = self.params_table.item(row, 1).text()

                if value_text:
                    if len(value_text.split()) > 1:
                        value = [float(v) for v in value_text.split()]
                    elif value_text == 'True':
                        value = True
                    elif value_text == 'False':
                        value = False
                    else:
                        value = float(value_text)
                    optim_params[param] = value

            # Test instantiation
            instantiate_optimizer(target, optim_params)

            self.optim_params = optim_params
            self.optim = target
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Validation Error", f"Invalid parameter: {e}")

    def get_result(self):
        return self.optim, self.optim_params


class SetDeviceWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Device Setting")
        self.resize(300, 400)

        self.use_cpu = None
        self.gpu_idx = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.device_list = QListWidget()
        self.device_list.addItem("CPU")
        for i in range(get_device_count()):
            name = f"{i} - {get_device_name(i)}"
            self.device_list.addItem(name)

        # Select last item (usually GPU if available) or CPU
        count = self.device_list.count()
        if count > 1:
            self.device_list.setCurrentRow(count - 1)
        else:
            self.device_list.setCurrentRow(0)

        layout.addWidget(self.device_list)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirm(self):
        row = self.device_list.currentRow()
        if row == -1:
            return

        self.use_cpu = (row == 0)
        if row > 0:
            self.gpu_idx = row - 1
        self.accept()

    def get_result(self):
        return self.use_cpu, self.gpu_idx
