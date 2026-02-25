"""Legacy standalone training manager window with real-time status table."""

import contextlib

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.training import Trainer
from XBrainLab.backend.visualization import PlotType
from XBrainLab.ui.components import PlotFigureWindow
from XBrainLab.ui.core.base_dialog import BaseDialog


class TrainingManagerWindow(BaseDialog):
    """
    Standalone window for managing training process.
    Displays real-time status table and controls.
    NOTE: Appears to be legacy/alternative to `TrainingPanel`.
    """

    def __init__(self, parent, trainer):
        """Initialize the training manager window.

        Args:
            parent: Parent widget.
            trainer: A ``Trainer`` instance managing the training loop.
        """
        self.trainer = trainer
        self.training_plan_holders = trainer.get_training_plan_holders()

        self.check_data()

        super().__init__(parent, title="Training Manager", height=400)

        # Start update loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(100)

        if trainer.is_running():
            self.start_training()

    def check_data(self):
        """Validate that the trainer and training plans are valid."""
        if not isinstance(self.trainer, Trainer):
            QMessageBox.critical(self, "Error", "Invalid trainer object")
        if not isinstance(self.training_plan_holders, list):
            QMessageBox.critical(self, "Error", "Invalid training plans")

    def init_ui(self):
        """Build the layout with menu bar, status table, status label, and buttons."""
        layout = QVBoxLayout(self)

        # Menu Bar (Simulated or real QMenuBar)
        # QDialog doesn't have menuBar() by default, but we can add one
        menubar = QMenuBar()
        plot_menu = menubar.addMenu("Plot")
        if plot_menu:
            plot_menu.addAction("Loss", self.plot_loss)
            plot_menu.addAction("Accuracy", self.plot_acc)
            plot_menu.addAction("AUC", self.plot_auc)
            plot_menu.addAction("Learning Rate", self.plot_lr)
        layout.setMenuBar(menubar)

        # Table
        self.plan_table = QTableWidget()
        columns = [
            "Plan name",
            "Status",
            "Epoch",
            "lr",
            "loss",
            "acc (%)",
            "auc",
            "val_loss",
            "val_acc (%)",
            "val_auc",
        ]
        self.plan_table.setColumnCount(len(columns))
        self.plan_table.setHorizontalHeaderLabels(columns)
        header = self.plan_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.plan_table)

        # Status Bar
        self.status_bar = QLabel("IDLE")
        layout.addWidget(self.status_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("start")
        self.start_btn.clicked.connect(self.start_training)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("stop")
        self.stop_btn.clicked.connect(self.stop_training)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        self.update_table()

    def plot_loss(self):
        """Open a loss-curve plot dialog."""
        win = PlotFigureWindow(
            self, self.training_plan_holders, PlotType.LOSS, title="Loss Plot"
        )
        win.show()
        # Keep reference to the window to prevent garbage collection if non-modal.
        # Using exec() blocks to ensure the window persists until closed.
        win.exec()

    def plot_acc(self):
        """Open an accuracy-curve plot dialog."""
        win = PlotFigureWindow(
            self, self.training_plan_holders, PlotType.ACCURACY, title="Accuracy Plot"
        )
        win.exec()

    def plot_auc(self):
        """Open an AUC-curve plot dialog."""
        win = PlotFigureWindow(
            self, self.training_plan_holders, PlotType.AUC, title="AUC Plot"
        )
        win.exec()

    def plot_lr(self):
        """Open a learning-rate plot dialog."""
        win = PlotFigureWindow(
            self, self.training_plan_holders, PlotType.LR, title="Learning Rate Plot"
        )
        win.exec()

    def start_training(self):
        """Disable the start button and launch the trainer."""
        self.start_btn.setEnabled(False)
        if not self.trainer.is_running():
            self.trainer.run(interact=True)

    def stop_training(self):
        """Request the trainer to stop the current run."""
        if not self.trainer.is_running():
            QMessageBox.warning(self, "Warning", "No training is in progress")
            return
        with contextlib.suppress(Exception):
            self.trainer.set_interrupt()

    def finish_training(self):
        """Re-enable the start button and show a completion dialog."""
        self.start_btn.setEnabled(True)
        self.status_bar.setText("IDLE")
        self.update_table()
        QMessageBox.information(self, "Success", "Training has stopped")

    def update_loop(self):
        """Periodic callback to refresh the table and detect training completion."""
        if not self.isVisible():
            return

        self.update_table()
        if not self.trainer.is_running() and not self.start_btn.isEnabled():
            self.finish_training()

    def update_table(self):
        """Synchronize the status table rows with current trainer state."""

        def get_table_values(plan):
            return (
                plan.get_name(),
                plan.get_training_status(),
                str(plan.get_training_epoch()),
                *[str(x) for x in plan.get_training_evaluation()],
            )

        if self.plan_table.rowCount() == 0:
            self.plan_table.setRowCount(len(self.training_plan_holders))
            for i, plan in enumerate(self.training_plan_holders):
                values = get_table_values(plan)
                for j, val in enumerate(values):
                    self.plan_table.setItem(i, j, QTableWidgetItem(str(val)))
        else:
            for i, plan in enumerate(self.training_plan_holders):
                values = get_table_values(plan)
                for j, val in enumerate(values):
                    self.plan_table.setItem(i, j, QTableWidgetItem(str(val)))

        self.status_bar.setText(self.trainer.get_progress_text())
