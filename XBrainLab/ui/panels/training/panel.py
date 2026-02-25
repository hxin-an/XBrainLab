"""Training panel for configuring, running, and monitoring model training."""

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

from .components import MetricTab
from .history_table import TrainingHistoryTable
from .sidebar import TrainingSidebar


class TrainingPanel(BasePanel):
    """Panel for managing the model-training workflow.

    Provides real-time accuracy/loss plots, a training-history table,
    log output, and a sidebar for configuration and execution controls.
    Subscribes to controller events for live updates.

    Attributes:
        dataset_controller: Injected ``DatasetController`` for data-change
            events.
        current_plotting_record: The ``TrainRecord`` currently displayed
            in the metric plots.
        tabs: ``QTabWidget`` holding accuracy, loss, and log tabs.
        tab_acc: ``MetricTab`` for accuracy plotting.
        tab_loss: ``MetricTab`` for loss plotting.
        log_text: ``QTextEdit`` for training log messages.
        history_table: ``TrainingHistoryTable`` for run status.
        sidebar: ``TrainingSidebar`` with configuration and execution buttons.

    """

    def __init__(self, controller=None, dataset_controller=None, parent=None):
        """Initialize the training panel.

        Args:
            controller: Optional ``TrainingController``. Resolved from
                the parent study if not provided.
            dataset_controller: Optional ``DatasetController`` for
                data-change event subscription.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("training")
        if dataset_controller is None and parent and hasattr(parent, "study"):
            dataset_controller = parent.study.get_controller("dataset")

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        self.dataset_controller = dataset_controller

        self.current_plotting_record = None
        self.plan_items = {}
        self.run_items = {}

        # 3. Setup bridges & UI
        self._setup_bridges()
        self.init_ui()

        self.training_completed_shown = False

    def _setup_bridges(self):
        """Register Qt observer bridges for training and dataset events."""
        if not self.controller:
            return

        # Connect to controller events for automatic UI updates
        self.bridge_started = QtObserverBridge(
            self.controller,
            "training_started",
            self,
        )
        self.bridge_started.connect_to(self._on_training_started)

        self.bridge_stopped = QtObserverBridge(
            self.controller,
            "training_stopped",
            self,
        )
        self.bridge_stopped.connect_to(self._on_training_stopped)

        self.bridge_config = QtObserverBridge(self.controller, "config_changed", self)
        # Config changes update toolbar state
        self.bridge_config.connect_to(self._on_config_changed)

        # Connect to training updates
        self.bridge_updated = QtObserverBridge(
            self.controller,
            "training_updated",
            self,
        )
        # We wrap update_loop to accept *args, **kwargs safely
        self.bridge_updated.connect_to(lambda *args, **kwargs: self.update_loop())

        self.bridge_cleared = QtObserverBridge(self.controller, "history_cleared", self)
        self.bridge_cleared.connect_to(self._on_history_cleared)

        # Connect to Dataset events (Updates info panel and check readiness)
        if self.dataset_controller:
            self.data_bridge = QtObserverBridge(
                self.dataset_controller,
                "data_changed",
                self,
            )
            self.data_bridge.connect_to(self.update_panel)

            self.import_bridge = QtObserverBridge(
                self.dataset_controller,
                "import_finished",
                self,
            )
            self.import_bridge.connect_to(
                self.update_panel,
            )  # Or specific handler if needed

        # Event-driven update: 'training_updated' signal triggers update_loop
        self.training_completed_shown = False

    def init_ui(self):
        """Build the panel layout with metric plots, history table, log, and sidebar."""
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Full width
        main_layout.setSpacing(0)

        # --- Left Column: Training Status (Main Content) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(0)

        # Training Plots Group
        plots_group = QGroupBox("TRAINING PLOTS")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(Stylesheets.TAB_WIDGET_CLEAN)

        # Tab 1: Accuracy
        # 2. Metric Tabs
        self.tab_acc = MetricTab("Accuracy", color=Theme.ACCENT_SUCCESS)
        self.tab_loss = MetricTab("Loss", color=Theme.ACCENT_ERROR)

        self.tabs.addTab(self.tab_acc, "Accuracy")
        self.tabs.addTab(self.tab_loss, "Loss")

        # 4. Logs
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Training logs will appear here...")
        self.log_text.setStyleSheet(Stylesheets.LOG_TEXT)
        self.tabs.addTab(self.log_text, "Log")

        plots_layout.addWidget(self.tabs)
        left_layout.addWidget(plots_group, stretch=2)

        # Training History Group
        history_group = QGroupBox("TRAINING HISTORY")
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(10, 20, 10, 10)

        # History Table
        self.history_table = TrainingHistoryTable()
        self.history_table.selection_changed_record.connect(
            self.on_history_selection_changed,
        )

        history_layout.addWidget(self.history_table)

        # Internal map to track rows: row_index -> (plan, run)
        self.row_map = {}

        left_layout.addWidget(history_group, stretch=1)
        main_layout.addWidget(left_widget, stretch=1)

        # --- Right Side: Sidebar ---
        self.sidebar = TrainingSidebar(self, self)
        main_layout.addWidget(self.sidebar, stretch=0)

        # Initial Check
        # Sidebar does its own check on init

    # --- Event Handlers ---

    # Removed action methods (now in Sidebar)

    def _on_config_changed(self):
        """Re-evaluate the ready-to-train state when configuration changes."""
        if hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()

    def _on_training_started(self):
        """Event handler: Training has started."""
        self.log_text.append("Training started (event).")
        self.training_completed_shown = False
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_started()

    def _on_training_stopped(self):
        """Event handler: Training has stopped."""
        self.training_finished()
        self.log_text.append("Training stopped (event).")
        # FORCE update to ensure the Table shows "Done" or "Stopped"
        self.update_loop()
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_stopped()

    def _on_history_cleared(self):
        """Event handler: History cleared."""
        self.tab_acc.clear()
        self.tab_loss.clear()
        self.current_plotting_record = None
        self.update_loop()  # Will clear table if history is empty

    # Clear history method moved to Sidebar

    def on_history_selection_changed(self, record):
        """Handle history-table selection change.

        Args:
            record: The newly selected ``TrainRecord``, or ``None``.

        """
        self.current_plotting_record = record
        if record:
            self.refresh_plot(record)

    def refresh_plot(self, record):
        """Re-draw the accuracy and loss plots with the full history of a record.

        Args:
            record: The ``TrainRecord`` whose history should be plotted.

        """
        self.tab_acc.clear()
        self.tab_loss.clear()

        def get_val(key, source, idx):
            if idx < len(source[key]):
                val = source[key][idx]
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            return 0.0

        # Re-populate data
        epochs = len(record.train[TrainRecordKey.ACC])
        for i in range(epochs):
            epoch = i + 1

            train_acc = get_val(TrainRecordKey.ACC, record.train, i)
            val_acc = get_val(RecordKey.ACC, record.val, i)
            train_loss = get_val(TrainRecordKey.LOSS, record.train, i)
            val_loss = get_val(RecordKey.LOSS, record.val, i)

            self.tab_acc.update_plot(epoch, train_acc, val_acc)
            self.tab_loss.update_plot(epoch, train_loss, val_loss)

    def training_finished(self):
        """Display a completion dialog when all training jobs finish."""
        if hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()

        # Only show message once

        if not self.training_completed_shown:
            self.training_completed_shown = True
            QMessageBox.information(self, "Done", "All training jobs finished.")

    def update_info(self):
        """Delegate info-panel updates to the sidebar."""
        self.info_panel = None  # Handled by Sidebar
        # But the Controller logic might call update_info on Panel
        if hasattr(self, "sidebar"):
            self.sidebar.update_info()

    def update_panel(self, *args):
        """Update panel content when switched to or data changes."""
        self.update_info()
        if hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()

    def update_loop(self):
        """Handle real-time training updates."""
        # 1. Update History Table
        if self.controller:
            plans = self.controller.get_formatted_history()
            self.history_table.update_table(plans)

            # 2. Auto-select a record if none is selected
            if not self.current_plotting_record and plans:
                # Prefer the currently running record, else the last one
                for p in plans:
                    if p.get("is_current_run"):
                        self.current_plotting_record = p["record"]
                        break
                else:
                    # No active run, select the last record
                    self.current_plotting_record = plans[-1]["record"]

        # 3. Update Plots if the current record is active and has new data
        if self.current_plotting_record:
            try:
                current_epochs = len(
                    self.current_plotting_record.train.get(TrainRecordKey.ACC, []),
                )
                last_count = getattr(self, "_last_epoch_count", -1)
                if last_count != current_epochs:
                    self._last_epoch_count = current_epochs
                    self.refresh_plot(self.current_plotting_record)
            except Exception:
                # Fallback: just refresh
                logger.warning(
                    "Error reading training epoch data, refreshing plot",
                    exc_info=True,
                )
                self.refresh_plot(self.current_plotting_record)

    # check_ready_to_train moved to Sidebar

    def closeEvent(self, event):  # noqa: N802
        """Stop the update timer on close.

        Args:
            event: The ``QCloseEvent``.

        """
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)
