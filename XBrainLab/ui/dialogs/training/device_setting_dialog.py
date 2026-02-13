from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QListWidget,
    QVBoxLayout,
)

from XBrainLab.backend.training.utils import (
    get_device_count,
    get_device_name,
)
from XBrainLab.ui.core.base_dialog import BaseDialog


class DeviceSettingDialog(BaseDialog):
    """
    Dialog for selecting the computation device (CPU or specific GPU).
    Lists available CUDA devices if present.
    """

    def __init__(self, parent):
        self.use_cpu = None
        self.gpu_idx = None

        # UI
        self.device_list = None

        super().__init__(parent, title="Device Setting")
        self.resize(300, 400)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def confirm(self):
        # Override accept? Or confirm is accept logic?
        # Original called confirm() on accepted signal.
        # I'll rename to accept? No, standard is accept() overrides QDialog.accept
        # But BaseDialog doesn't enforce. UI connects logic.
        pass

    def accept(self):
        # Logic from confirm()
        if not self.device_list:
            super().accept()
            return

        row = self.device_list.currentRow()
        if row == -1:
            return

        self.use_cpu = row == 0
        if row > 0:
            self.gpu_idx = row - 1
        super().accept()

    def get_result(self):
        return self.use_cpu, self.gpu_idx
