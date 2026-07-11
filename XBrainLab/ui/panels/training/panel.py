"""Training panel for configuring, running, and monitoring model training."""

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
    execute_application_command,
    get_controller_for_compatibility_context,
    local_result_payload,
    run_controller_compatibility_call,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.refresh_coordinator import refresh_after_observer
from XBrainLab.ui.status import show_status_message
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
        preprocess_controller: Injected ``PreprocessController`` for
            preprocess-state change events.
        current_plotting_record: The ``TrainRecord`` currently displayed
            in the metric plots.
        tabs: ``QTabWidget`` holding accuracy, loss, and log tabs.
        tab_acc: ``MetricTab`` for accuracy plotting.
        tab_loss: ``MetricTab`` for loss plotting.
        log_text: ``QTextEdit`` for training log messages.
        history_table: ``TrainingHistoryTable`` for run status.
        sidebar: ``TrainingSidebar`` with configuration and execution buttons.

    """

    def __init__(
        self,
        controller=None,
        dataset_controller=None,
        parent=None,
        preprocess_controller=None,
    ):
        """Initialize the training panel.

        Args:
            controller: Optional ``TrainingController``. Resolved from
                the parent study if not provided.
            dataset_controller: Optional ``DatasetController`` for
                data-change event subscription.
            preprocess_controller: Optional ``PreprocessController`` for
                preprocess-state change subscription.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "training",
            )
        if dataset_controller is None and parent and hasattr(parent, "study"):
            dataset_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "dataset",
            )
        if preprocess_controller is None and parent and hasattr(parent, "study"):
            preprocess_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "preprocess",
            )

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        self.dataset_controller = dataset_controller
        self.preprocess_controller = preprocess_controller

        self.current_plotting_record = None
        self._last_epoch_count: int = -1
        self._last_plot_signature = None
        self._logged_epoch_signatures_by_record: dict[int, dict[int, tuple]] = {}
        self._selection_pinned_by_user = False
        self._suppress_log_render_once = False
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
        self._create_bridge(
            self.controller,
            "training_started",
            self._on_training_started,
        )
        self._create_bridge(
            self.controller,
            "training_stopped",
            self._on_training_stopped,
        )
        self._create_bridge(
            self.controller,
            "config_changed",
            self._on_config_changed,
        )
        self._create_bridge(
            self.controller,
            "training_updated",
            self._on_training_updated,
        )
        self._create_bridge(
            self.controller,
            "history_cleared",
            self._on_history_cleared,
        )

        # Connect to Dataset events (Updates info panel and check readiness)
        if self.dataset_controller:
            self._create_refresh_bridge(self.dataset_controller, "data_changed")
        if self.preprocess_controller:
            self._create_refresh_bridge(
                self.preprocess_controller,
                "preprocess_changed",
            )

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
        self.log_text.clear()
        self._logged_epoch_signatures_by_record.clear()
        self._suppress_log_render_once = True
        refresh_after_observer(self, event_name="config_changed")

    def _on_training_started(self):
        """Event handler: Training has started."""
        self.log_text.append("Training started (event).")
        self.training_completed_shown = False
        self.show_status_message("Training started")
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_started(refresh_ready=False)
        refresh_after_observer(self, event_name="training_started")

    def _on_training_stopped(self):
        """Event handler: Training has stopped."""
        self.training_finished(refresh_ready=False)
        self.log_text.append("Training stopped (event).")
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_stopped(refresh_ready=False)
        refresh_after_observer(self, event_name="training_stopped")

    def _on_training_updated(self):
        """Refresh live training progress and shared observer status."""
        self.update_loop(log_epochs=True)
        refresh_after_observer(self, event_name="training_updated")

    def _on_history_cleared(self):
        """Event handler: History cleared."""
        self.log_text.clear()
        self._clear_training_display()
        refresh_after_observer(self, event_name="history_cleared")

    def _clear_training_display(self):
        """Clear plot selection state when no valid training history remains."""
        self.tab_acc.clear(redraw=False)
        self.tab_loss.clear(redraw=False)
        self.current_plotting_record = None
        self._last_epoch_count = -1
        self._last_plot_signature = None
        self._selection_pinned_by_user = False
        self._logged_epoch_signatures_by_record.clear()
        self.history_table.clear_history()

    def _select_preferred_plot_record(self, plans, force_active=False):
        """Choose which record the training plots should track.

        Args:
            plans: Formatted history rows from the controller.
            force_active: When ``True``, prefer the currently running record
                even if an older record is still selected.

        Returns:
            The selected ``TrainRecord`` or ``None`` when no plans exist.

        """
        if not plans:
            return None

        if (
            not force_active
            and self._selection_pinned_by_user
            and self.current_plotting_record is not None
        ):
            for plan_info in plans:
                if plan_info["record"] is self.current_plotting_record:
                    return self.current_plotting_record

        for plan_info in plans:
            if plan_info.get("is_current_run"):
                return plan_info["record"]

        if not force_active and self.current_plotting_record is not None:
            for plan_info in plans:
                if plan_info["record"] is self.current_plotting_record:
                    return self.current_plotting_record

        return plans[-1]["record"]

    # Clear history method moved to Sidebar

    def on_history_selection_changed(self, record):
        """Handle history-table selection change.

        Args:
            record: The newly selected ``TrainRecord``, or ``None``.

        """
        self.current_plotting_record = record
        if record:
            self._selection_pinned_by_user = True
            self._last_plot_signature = None
            self.refresh_plot(record)
            self._render_epoch_logs_for_record(record)
        else:
            self._selection_pinned_by_user = False

    def refresh_plot(self, record):
        """Re-draw the accuracy and loss plots with the full history of a record.

        Args:
            record: The ``TrainRecord`` whose history should be plotted.

        """
        self.tab_acc.clear()
        self.tab_loss.clear()

        def get_val(key, source, idx):
            values = source.get(key, [])
            if idx < len(values):
                val = values[idx]
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None
            return None

        # Re-populate data
        epochs = len(record.train.get(TrainRecordKey.ACC, []))
        epoch_values = []
        train_acc_values = []
        val_acc_values = []
        train_loss_values = []
        val_loss_values = []
        for i in range(epochs):
            epoch = i + 1

            epoch_values.append(epoch)
            train_acc_values.append(get_val(TrainRecordKey.ACC, record.train, i))
            val_acc_values.append(get_val(RecordKey.ACC, record.val, i))
            train_loss_values.append(get_val(TrainRecordKey.LOSS, record.train, i))
            val_loss_values.append(get_val(RecordKey.LOSS, record.val, i))

        self.tab_acc.set_series(epoch_values, train_acc_values, val_acc_values)
        self.tab_loss.set_series(epoch_values, train_loss_values, val_loss_values)

    def training_finished(self, *, refresh_ready: bool = True):
        """Report completion without interrupting the workflow."""
        if refresh_ready and hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()

        if not self.training_completed_shown:
            self.training_completed_shown = True
            self.log_text.append("All training jobs finished.")
            self.show_status_message("Training complete · Review results")

    def show_status_message(self, message: str, timeout_ms: int = 7000) -> bool:
        """Show a non-modal status message on the application status bar."""
        return show_status_message(self, message, timeout_ms)

    def update_info(self):
        """Delegate info-panel updates to the sidebar."""
        # Info display is handled entirely by the Sidebar component.
        if hasattr(self, "sidebar"):
            self.sidebar.update_info()

    def update_panel(self, *args):
        """Update panel content when switched to or data changes."""
        self.update_info()
        if hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()
        self.update_loop()

    def update_loop(self, force_active=False, log_epochs=False):
        """Handle real-time training updates."""
        # 1. Update History Table
        plans = self._history_from_application_query()
        if plans is None:
            plans = self._compatibility_history_for_render()
        if plans is not None:
            if not plans:
                self._clear_training_display()
                return

            self.history_table.update_table(plans)
            preferred_record = self._select_preferred_plot_record(
                plans,
                force_active=force_active,
            )
            if preferred_record is not self.current_plotting_record:
                self.current_plotting_record = preferred_record
                self._last_epoch_count = -1
                self._last_plot_signature = None
                self._selection_pinned_by_user = False
                if self._suppress_log_render_once:
                    self._suppress_log_render_once = False
                else:
                    self._render_epoch_logs_for_record(preferred_record)

        # 3. Update Plots if the current record is active and has new data
        if self.current_plotting_record:
            try:
                current_epochs = len(
                    self.current_plotting_record.train.get(TrainRecordKey.ACC, []),
                )
                current_signature = self._record_plot_signature(
                    self.current_plotting_record,
                )
                last_count = getattr(self, "_last_epoch_count", -1)
                if (
                    last_count != current_epochs
                    or self._last_plot_signature != current_signature
                ):
                    self._last_epoch_count = current_epochs
                    self._last_plot_signature = current_signature
                    self.refresh_plot(self.current_plotting_record)
                if log_epochs:
                    self._append_epoch_logs(self.current_plotting_record)
            except Exception:
                # Fallback: just refresh
                logger.warning(
                    "Error reading training epoch data, refreshing plot",
                    exc_info=True,
                )
                self.refresh_plot(self.current_plotting_record)

    def _record_plot_signature(self, record):
        """Return a compact signature for plot-relevant train/val metric changes."""
        return (
            self._series_signature(record.train, TrainRecordKey.ACC),
            self._series_signature(record.train, TrainRecordKey.LOSS),
            self._series_signature(record.val, RecordKey.ACC),
            self._series_signature(record.val, RecordKey.LOSS),
            self._series_signature(getattr(record, "test", {}), RecordKey.ACC),
            self._series_signature(getattr(record, "test", {}), RecordKey.LOSS),
        )

    @staticmethod
    def _series_signature(source, key):
        values = source.get(key, []) if hasattr(source, "get") else []
        tail = tuple(repr(value) for value in values[-3:])
        return len(values), tail

    def _append_epoch_logs(self, record) -> None:
        completed_epochs = self._completed_epoch_count(record)
        if completed_epochs <= 0:
            return
        record_logs = self._logged_epoch_signatures_by_record.setdefault(id(record), {})
        for epoch_index in range(completed_epochs):
            signature = self._epoch_log_signature(record, epoch_index)
            if record_logs.get(epoch_index) == signature:
                continue
            record_logs[epoch_index] = signature
            self.log_text.append(self._format_epoch_log_line(record, epoch_index))

    def _render_epoch_logs_for_record(self, record) -> None:
        """Replace the log tab with epoch logs for the selected history row."""
        self.log_text.clear()
        if record is None:
            return
        completed_epochs = self._completed_epoch_count(record)
        if completed_epochs <= 0:
            self.log_text.setPlaceholderText("No epoch logs for the selected run yet.")
            self._logged_epoch_signatures_by_record[id(record)] = {}
            return

        record_logs: dict[int, tuple] = {}
        for epoch_index in range(completed_epochs):
            signature = self._epoch_log_signature(record, epoch_index)
            record_logs[epoch_index] = signature
            self.log_text.append(self._format_epoch_log_line(record, epoch_index))
        self._logged_epoch_signatures_by_record[id(record)] = record_logs

    @staticmethod
    def _completed_epoch_count(record) -> int:
        train_values = record.train.get(TrainRecordKey.ACC, [])
        if not train_values:
            train_values = record.train.get(TrainRecordKey.LOSS, [])
        train_count = len(train_values)
        get_epoch = getattr(record, "get_epoch", None)
        if not callable(get_epoch):
            return train_count
        try:
            value = get_epoch()
            if not isinstance(value, (int, str)):
                return train_count
            record_epoch = int(value)
        except (TypeError, ValueError):
            return train_count
        if record_epoch <= 0:
            return train_count
        return min(train_count, record_epoch)

    def _epoch_log_signature(self, record, epoch_index: int) -> tuple:
        return (
            self._metric_at(record.train, TrainRecordKey.LOSS, epoch_index),
            self._metric_at(record.train, TrainRecordKey.ACC, epoch_index),
            self._metric_at(record.train, TrainRecordKey.AUC, epoch_index),
            self._metric_at(record.val, RecordKey.LOSS, epoch_index),
            self._metric_at(record.val, RecordKey.ACC, epoch_index),
            self._metric_at(record.val, RecordKey.AUC, epoch_index),
            self._metric_at(record.train, TrainRecordKey.LR, epoch_index),
            self._metric_at(record.train, TrainRecordKey.TIME, epoch_index),
        )

    def _format_epoch_log_line(self, record, epoch_index: int) -> str:
        values = {
            "train_loss": self._metric_at(
                record.train,
                TrainRecordKey.LOSS,
                epoch_index,
            ),
            "train_acc": self._metric_at(record.train, TrainRecordKey.ACC, epoch_index),
            "train_auc": self._metric_at(record.train, TrainRecordKey.AUC, epoch_index),
            "val_loss": self._metric_at(record.val, RecordKey.LOSS, epoch_index),
            "val_acc": self._metric_at(record.val, RecordKey.ACC, epoch_index),
            "val_auc": self._metric_at(record.val, RecordKey.AUC, epoch_index),
            "lr": self._metric_at(record.train, TrainRecordKey.LR, epoch_index),
            "time": self._metric_at(record.train, TrainRecordKey.TIME, epoch_index),
        }
        epoch = epoch_index + 1
        return (
            f"Epoch {epoch}: "
            f"train loss={self._format_metric(values['train_loss'])} "
            f"acc={self._format_metric(values['train_acc'])} "
            f"auc={self._format_metric(values['train_auc'])}; "
            f"val loss={self._format_metric(values['val_loss'])} "
            f"acc={self._format_metric(values['val_acc'])} "
            f"auc={self._format_metric(values['val_auc'])}; "
            f"lr={self._format_metric(values['lr'])} "
            f"time={self._format_metric(values['time'])}"
        )

    @staticmethod
    def _metric_at(source, key, epoch_index: int):
        values = source.get(key, []) if hasattr(source, "get") else []
        if epoch_index >= len(values):
            return None
        return values[epoch_index]

    @staticmethod
    def _format_metric(value) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value):.4g}"
        except (TypeError, ValueError):
            return str(value)

    def _history_from_application_query(self):
        result = execute_application_command(
            self,
            QueryStateCommand(query="training_history", include_objects=True),
            refresh=False,
        )
        if result is None or result.failed:
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "training_history":
            return None
        rows = local_result_payload(result).get("rows")
        return list(rows) if isinstance(rows, list) else []

    def _compatibility_history_for_render(self):
        if self.controller is None:
            return []
        try:
            return run_controller_compatibility_call(
                self,
                self.controller.get_formatted_history,
            )
        except ControllerCompatibilityUnavailableError:
            return []

    # check_ready_to_train moved to Sidebar

    def closeEvent(self, event):  # noqa: N802
        """Handle panel close, delegating to base cleanup.

        Args:
            event: The ``QCloseEvent``.

        """
        super().closeEvent(event)
