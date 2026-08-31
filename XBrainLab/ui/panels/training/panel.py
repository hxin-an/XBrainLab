"""Training panel for configuring, running, and monitoring model training."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    CommandCapability,
    CommandName,
    QueryStateCommand,
)
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.training_history import (
    project_training_history_rows,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_capabilities import (
    TRAINING_PROGRESS_UPDATED_EVENT,
    ControllerCompatibilityUnavailableError,
    TrainingActionPort,
    TrainingPublicationPort,
    TrainingQueryPort,
    TrainingTransientProgressPort,
    application_runtime_initialized,
    application_ui_runtime,
    execute_application_command,
    get_controller_for_compatibility_context,
    run_controller_compatibility_call,
    training_transient_ui_port,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.refresh_coordinator import refresh_after_observer
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

from .components import MetricTab
from .history_table import TrainingHistoryTable
from .sidebar import TrainingSidebar


@dataclass(frozen=True, slots=True)
class _TrainingPublicationSignature:
    """Application fields that can change Training's rendered state."""

    usable: bool
    state_reliable: bool
    training_liveness_reliable: bool
    trainer_identity: str | None
    training_boundary_stable: bool
    active_dataset: ActiveDatasetSnapshot
    active_training: ActiveTrainingSnapshot
    training_model_name: str | None
    training_is_running: bool
    training_plan_count: int
    training_run_count: int
    training_finished_run_count: int
    training_terminal_outcome: TrainingTerminalOutcome
    training_missing_requirements: tuple[str, ...]
    training_history_signature: tuple[tuple[object, ...], ...] | None
    train_capability: CommandCapability | None


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
        current_plotting_identity: Stable plan/run identity displayed in
            the metric plots.
        tabs: ``QTabWidget`` holding accuracy, loss, and log tabs.
        tab_acc: ``MetricTab`` for accuracy plotting.
        tab_loss: ``MetricTab`` for loss plotting.
        log_text: ``QTextEdit`` for training log messages.
        history_table: ``TrainingHistoryTable`` for run status.
        sidebar: ``TrainingSidebar`` with configuration and execution buttons.

    """

    _MIN_PLOTS_GROUP_HEIGHT = 180

    def __init__(
        self,
        controller=None,
        dataset_controller=None,
        parent=None,
        preprocess_controller=None,
        *,
        query_port: TrainingQueryPort | None = None,
        publication_port: TrainingPublicationPort | None = None,
        action_port: TrainingActionPort | None = None,
        transient_port: TrainingTransientProgressPort | None = None,
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
        explicit_typed_ports = any(
            port is not None
            for port in (query_port, publication_port, action_port, transient_port)
        )
        runtime = application_ui_runtime(parent)
        self._typed_port_mode = explicit_typed_ports or runtime is not None

        # Controller resolution exists only for zero-port standalone/mock contexts.
        if self._typed_port_mode:
            controller = None
            dataset_controller = None
            preprocess_controller = None
        elif controller is None and parent and hasattr(parent, "study"):
            controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "training",
            )
        if (
            not self._typed_port_mode
            and dataset_controller is None
            and parent
            and hasattr(parent, "study")
        ):
            dataset_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "dataset",
            )
        if (
            not self._typed_port_mode
            and preprocess_controller is None
            and parent
            and hasattr(parent, "study")
        ):
            preprocess_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "preprocess",
            )

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        self.dataset_controller = dataset_controller
        self.preprocess_controller = preprocess_controller
        if explicit_typed_ports:
            self._query_port = query_port
            self._publication_port = publication_port
            self._action_port = action_port
            self._transient_port = transient_port
        else:
            self._query_port = runtime
            self._publication_port = runtime
            self._action_port = runtime
            self._transient_port = (
                training_transient_ui_port(self) if runtime is not None else None
            )
        self._application_view_publication: ApplicationViewPublication | None = None
        self._last_application_revision = 0
        self._last_training_publication_signature: (
            _TrainingPublicationSignature | None
        ) = None
        self._application_render_ledger = ApplicationPublicationRenderLedger(
            panel_name="Training",
            render_publication=self._render_application_publication,
            commit_publication=self._commit_application_publication,
            parent=self,
        )
        self._application_refresh_timer = self._application_render_ledger.timer
        self._rendered_training_running: bool | None = None
        self._rendered_terminal_outcome: TrainingTerminalOutcome | None = None

        self.current_plotting_identity: tuple[int, int] | None = None
        self.current_plotting_row: dict | None = None
        self._last_epoch_count: int = -1
        self._last_plot_signature = None
        self._logged_epoch_signatures_by_identity: dict[
            tuple[int, int],
            dict[int, tuple],
        ] = {}
        self._selection_pinned_by_user = False
        self._suppress_log_render_once = False
        self._history_query_unavailable_shown = False
        self._has_verified_history_render = False
        self._last_verified_history_rows: list[dict] = []
        self._rendered_history_rows: list[dict] = []
        self._latest_training_generation_by_trainer: dict[str, int] = {}
        self._terminal_training_generation_by_run: dict[tuple[str, int], int] = {}
        self._last_training_analysis_publication_generation = 0
        self._latest_terminal_outcome: TrainingTerminalOutcome | None = None
        self._terminal_event_log_expected = False
        self.plan_items: dict[str, object] = {}
        self.run_items: dict[str, object] = {}

        # 3. Setup bridges & UI
        self._setup_bridges()
        self.init_ui()

        self.training_completed_shown = False
        self._training_outcome_unverified_shown = False

    def _setup_bridges(self):
        """Register Qt observer bridges for training and dataset events."""
        if self._typed_port_mode:
            if self._publication_port is not None:
                self._create_bridge(
                    cast(Observable, self._publication_port),
                    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
                    self._on_application_view_publication_changed,
                )
            if self._transient_port is not None:
                self._create_bridge(
                    cast(Observable, self._transient_port),
                    TRAINING_PROGRESS_UPDATED_EVENT,
                    self._on_training_updated,
                )
            return
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
            "training_started_state",
            self._on_training_started_state,
        )
        self._create_bridge(
            self.controller,
            "training_stopped",
            self._on_training_stopped,
        )
        self._create_bridge(
            self.controller,
            "training_terminal_published",
            self._on_training_terminal_published,
        )
        self._create_bridge(
            self.controller,
            "training_analysis_published",
            self._on_training_analysis_published,
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

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Queue one Training render for each monotonic application revision."""
        if not self._valid_application_publication(publication):
            logger.error("Ignored malformed Training application publication.")
            return False
        typed_publication = cast(ApplicationViewPublication, publication)
        if typed_publication.revision <= self._last_application_revision:
            return True
        self._application_view_publication = typed_publication
        signature = self._training_publication_signature(typed_publication)
        if signature == self._last_training_publication_signature:
            return self._application_render_ledger.record_rendered(typed_publication)
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._application_view_publication = publication
        self.update_panel()

    def _commit_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._last_application_revision = max(
            self._last_application_revision,
            publication.revision,
        )
        self._last_training_publication_signature = (
            self._training_publication_signature(publication)
        )

    @staticmethod
    def _training_publication_signature(
        publication: ApplicationViewPublication,
    ) -> _TrainingPublicationSignature:
        """Project one publication onto state that Training actually renders."""
        state = publication.state
        training = state.training
        boundary = publication.training_boundary
        train_capability = publication.effective_capabilities.capabilities.get(
            CommandName.TRAIN.value
        )
        return _TrainingPublicationSignature(
            usable=publication.usable,
            state_reliable=state.state_reliable,
            training_liveness_reliable=state.training_liveness_reliable,
            trainer_identity=boundary.trainer_identity,
            training_boundary_stable=boundary.stable,
            active_dataset=state.active_dataset,
            active_training=state.active_training,
            training_model_name=training.model_name,
            training_is_running=training.is_running,
            training_plan_count=training.plan_count,
            training_run_count=training.run_count,
            training_finished_run_count=training.finished_run_count,
            training_terminal_outcome=training.terminal_outcome,
            training_missing_requirements=tuple(training.missing_requirements),
            training_history_signature=TrainingPanel._training_history_signature(
                publication.training_history
            ),
            train_capability=train_capability,
        )

    @classmethod
    def _training_history_signature(
        cls,
        rows: tuple[dict, ...] | None,
    ) -> tuple[tuple[object, ...], ...] | None:
        """Project publication rows onto values rendered by the Training panel."""
        if rows is None:
            return None
        signatures: list[tuple[object, ...]] = []
        for row in rows:
            train_metrics, validation_metrics = cls._history_metrics(row)
            test_metrics = cls._history_test_metrics(row)
            signatures.append(
                (
                    cls._history_identity(row),
                    row.get("group_name"),
                    row.get("run_name"),
                    row.get("model_name"),
                    row.get("status"),
                    row.get("status_detail"),
                    row.get("epoch"),
                    row.get("max_epochs"),
                    row.get("is_active"),
                    row.get("is_current_run"),
                    row.get("start_timestamp"),
                    row.get("end_timestamp"),
                    cls._series_signature(train_metrics, TrainRecordKey.ACC),
                    cls._series_signature(train_metrics, TrainRecordKey.LOSS),
                    cls._series_signature(train_metrics, TrainRecordKey.AUC),
                    cls._series_signature(train_metrics, TrainRecordKey.LR),
                    cls._series_signature(train_metrics, TrainRecordKey.TIME),
                    cls._series_signature(validation_metrics, RecordKey.ACC),
                    cls._series_signature(validation_metrics, RecordKey.LOSS),
                    cls._series_signature(validation_metrics, RecordKey.AUC),
                    cls._series_signature(test_metrics, RecordKey.ACC),
                )
            )
        return tuple(signatures)

    @staticmethod
    def _valid_application_publication(publication: object) -> bool:
        return (
            isinstance(publication, ApplicationViewPublication)
            and not isinstance(publication.revision, bool)
            and isinstance(publication.revision, int)
            and publication.revision >= 1
        )

    def _read_application_publication(self) -> ApplicationViewPublication | None:
        pending = self._application_render_ledger.pending_publication
        if pending is not None and pending.revision > self._last_application_revision:
            self._application_view_publication = pending
            return pending
        port = self._publication_port
        if port is None:
            return None
        try:
            publication = port.get_view_publication()
        except Exception:
            logger.error(
                "Training application publication is unavailable.",
                exc_info=True,
            )
            self._application_view_publication = None
            return None
        if not self._valid_application_publication(publication):
            self._application_view_publication = None
            return None
        typed_publication = cast(ApplicationViewPublication, publication)
        if typed_publication.revision >= self._last_application_revision:
            self._application_view_publication = typed_publication
        return self._application_view_publication

    def _render_training_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        training = publication.state.training
        if training.is_running:
            if self._rendered_training_running is not True:
                self._render_training_started()
        else:
            outcome = training.terminal_outcome
            if outcome.is_terminal and outcome != self._rendered_terminal_outcome:
                self.training_completed_shown = False
                self._latest_terminal_outcome = outcome
                self.training_finished(
                    refresh_ready=False,
                    report_unverified=False,
                    outcome=outcome,
                )
            if hasattr(self, "sidebar"):
                self.sidebar.on_training_stopped(refresh_ready=False)
            self._rendered_terminal_outcome = outcome
        self._rendered_training_running = training.is_running

    def init_ui(self):
        """Build the panel layout with metric plots, history table, log, and sidebar."""
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Full width
        main_layout.setSpacing(0)

        # --- Left Column: Training Status (Main Content) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 8, 20, 8)
        left_layout.setSpacing(0)

        # Training Plots Group
        self.plots_group = QGroupBox("TRAINING PLOTS")
        plots_layout = QVBoxLayout(self.plots_group)
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
        left_layout.addWidget(self.plots_group, stretch=1)

        # Training history is already visually framed by its table. Keep the
        # section title, but avoid a redundant outer group-box border.
        self.history_group = QWidget()
        self.history_group.setObjectName("TrainingHistorySection")
        history_layout = QVBoxLayout(self.history_group)
        history_layout.setContentsMargins(0, 6, 0, 0)
        history_layout.setSpacing(6)

        self.history_title = QLabel("TRAINING HISTORY")
        self.history_title.setObjectName("TrainingHistoryTitle")
        self.history_title.setStyleSheet(
            f"background: transparent; color: {Theme.TEXT_MUTED}; "
            "font-size: 13px; font-weight: bold;"
        )
        history_layout.addWidget(self.history_title)

        # History Table
        self.history_table = TrainingHistoryTable()
        self.history_table.selection_changed_identity.connect(
            self.on_history_selection_changed,
        )

        history_layout.addWidget(self.history_table)

        self.history_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.history_group.setFixedHeight(self.history_group.sizeHint().height())
        left_layout.addWidget(self.history_group, stretch=0)
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
        self._logged_epoch_signatures_by_identity.clear()
        self._suppress_log_render_once = True
        refresh_after_observer(self, event_name="config_changed")

    def _on_training_started(self):
        """Event handler: Training has started."""
        if application_runtime_initialized(self):
            return
        self._render_training_started()
        refresh_after_observer(self, event_name="training_started")
        self.log_text.append("Training started (event).")

    def _on_training_started_state(self, event: TrainingLifecycleEvent) -> None:
        """Apply a started edge only while its generation is still current."""
        if not self._accept_started_event(event):
            return
        self._render_training_started()
        refresh_after_observer(self, event_name="training_started")
        self.log_text.append("Training started (event).")

    def _render_training_started(self) -> None:
        """Render one accepted running generation."""
        self.training_completed_shown = False
        self._training_outcome_unverified_shown = False
        self._latest_terminal_outcome = None
        self._terminal_event_log_expected = False
        self.show_status_message("Training started")
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_started(refresh_ready=False)

    def _on_training_stopped(self):
        """Event handler: Training has stopped."""
        if application_runtime_initialized(self):
            return
        self.reconcile_training_terminal_outcome()
        self.log_text.append("Training stopped (event).")
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_stopped(refresh_ready=False)
        refresh_after_observer(self, event_name="training_stopped")

    def _on_training_terminal_published(
        self,
        event: TrainingLifecycleEvent,
    ) -> None:
        """Render one authoritative terminal publication on the GUI thread."""
        if not self._accept_terminal_event(event):
            return
        self.training_completed_shown = False
        self._training_outcome_unverified_shown = False
        self._latest_terminal_outcome = event.outcome
        self._terminal_event_log_expected = True
        self.training_finished(
            refresh_ready=False,
            report_unverified=False,
            outcome=event.outcome,
        )
        self.log_text.append("Training stopped (event).")
        if hasattr(self, "sidebar"):
            self.sidebar.on_training_stopped(refresh_ready=False)
        refresh_after_observer(
            self,
            event_name="training_terminal_published",
        )

    def _accept_started_event(self, event: TrainingLifecycleEvent) -> bool:
        if not isinstance(event, TrainingLifecycleEvent) or not event.token.stable:
            return False
        outcome = event.outcome
        run = outcome.run
        if outcome.state is not TrainingOutcomeState.RUNNING or run is None:
            return False
        trainer_id = run.trainer_id
        generation = event.token.generation
        if generation < self._latest_training_generation_by_trainer.get(
            trainer_id,
            -1,
        ):
            return False
        terminal_generation = self._terminal_training_generation_by_run.get(
            (trainer_id, run.run_id),
        )
        if terminal_generation is not None and generation <= terminal_generation:
            return False
        self._latest_training_generation_by_trainer[trainer_id] = generation
        return True

    def _on_training_analysis_published(
        self,
        event: TrainingLifecycleEvent,
    ) -> None:
        """Fan out one final automatic-analysis publication."""
        if not self._accept_analysis_event(event):
            return
        refresh_after_observer(
            self,
            event_name="training_analysis_published",
        )

    def _accept_analysis_event(self, event: TrainingLifecycleEvent) -> bool:
        if (
            not isinstance(event, TrainingLifecycleEvent)
            or not event.token.stable
            or event.publication_generation is None
            or event.outcome.state is not TrainingOutcomeState.COMPLETED
            or event.outcome.run is None
        ):
            return False
        publication_generation = event.publication_generation
        if (
            publication_generation
            <= self._last_training_analysis_publication_generation
        ):
            return False
        run = event.outcome.run
        training_generation = event.token.generation
        latest = self._latest_training_generation_by_trainer.get(run.trainer_id, -1)
        if training_generation < latest:
            return False
        self._latest_training_generation_by_trainer[run.trainer_id] = (
            training_generation
        )
        self._last_training_analysis_publication_generation = publication_generation
        return True

    def _accept_terminal_event(self, event: TrainingLifecycleEvent) -> bool:
        if (
            not isinstance(event, TrainingLifecycleEvent)
            or not event.token.stable
            or event.publication_generation is None
            or not event.outcome.is_terminal
            or event.outcome.run is None
        ):
            return False
        run = event.outcome.run
        key = (run.trainer_id, run.run_id)
        generation = event.token.generation
        if generation <= self._terminal_training_generation_by_run.get(key, -1):
            return False
        latest = self._latest_training_generation_by_trainer.get(run.trainer_id, -1)
        if generation < latest:
            return False
        self._latest_training_generation_by_trainer[run.trainer_id] = generation
        self._terminal_training_generation_by_run[key] = generation
        return True

    def _on_training_updated(self):
        """Refresh live training progress and shared observer status."""
        self.update_loop(log_epochs=True)
        if self._publication_port is None:
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
        self.current_plotting_identity = None
        self.current_plotting_row = None
        self._last_epoch_count = -1
        self._last_plot_signature = None
        self._selection_pinned_by_user = False
        self._logged_epoch_signatures_by_identity.clear()
        self._last_verified_history_rows = []
        self._rendered_history_rows = []
        self.history_table.clear_history()

    def _select_preferred_plot_row(self, rows, force_active=False):
        """Choose which detached history row the plots should track.

        Args:
            rows: Detached history rows from the application query.
            force_active: When ``True``, prefer the currently running row
                even if an older row is still selected.

        Returns:
            The selected row or ``None`` when no rows exist.

        """
        if not rows:
            return None

        if (
            not force_active
            and self._selection_pinned_by_user
            and self.current_plotting_identity is not None
        ):
            selected = self._history_row_for_identity(
                rows,
                self.current_plotting_identity,
            )
            if selected is not None:
                return selected

        for row in rows:
            if row.get("is_current_run"):
                return row

        if not force_active and self.current_plotting_identity is not None:
            selected = self._history_row_for_identity(
                rows,
                self.current_plotting_identity,
            )
            if selected is not None:
                return selected

        return rows[-1]

    # Clear history method moved to Sidebar

    def on_history_selection_changed(self, identity):
        """Handle history-table selection change.

        Args:
            identity: The selected primitive plan/run identity, or ``None``.

        """
        selected_identity = self._history_identity(identity)
        if selected_identity is None:
            self._selection_pinned_by_user = False
            return
        row = self._history_row_for_identity(
            self._rendered_history_rows,
            selected_identity,
        )
        if row is None:
            self._selection_pinned_by_user = False
            return
        self.current_plotting_identity = selected_identity
        self.current_plotting_row = row
        self._selection_pinned_by_user = True
        self._last_plot_signature = None
        self.refresh_plot(row)
        self._render_epoch_logs_for_row(row)

    def refresh_plot(self, row):
        """Re-draw accuracy and loss plots from one detached history row.

        Args:
            row: Detached history row whose copied series should be plotted.

        """
        self.tab_acc.clear()
        self.tab_loss.clear()
        train_metrics, validation_metrics = self._history_metrics(row)
        test_metrics = self._history_test_metrics(row)

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
        epochs = len(train_metrics.get(TrainRecordKey.ACC, []))
        epoch_values = []
        train_acc_values = []
        val_acc_values = []
        train_loss_values = []
        val_loss_values = []
        for i in range(epochs):
            epoch = i + 1

            epoch_values.append(epoch)
            train_acc_values.append(get_val(TrainRecordKey.ACC, train_metrics, i))
            val_acc_values.append(get_val(RecordKey.ACC, validation_metrics, i))
            train_loss_values.append(get_val(TrainRecordKey.LOSS, train_metrics, i))
            val_loss_values.append(get_val(RecordKey.LOSS, validation_metrics, i))

        test_acc_values = [
            get_val(RecordKey.ACC, test_metrics, index)
            for index in range(len(test_metrics.get(RecordKey.ACC, [])))
        ]
        self.tab_acc.set_series(
            epoch_values,
            train_acc_values,
            val_acc_values,
            test_acc_values,
        )
        self.tab_loss.set_series(epoch_values, train_loss_values, val_loss_values)

    def training_finished(
        self,
        *,
        refresh_ready: bool = True,
        report_unverified: bool = True,
        outcome: TrainingTerminalOutcome | None = None,
    ) -> bool:
        """Report one verified backend terminal outcome.

        A controller stop notification can reach Qt while the asynchronous
        ``TrainCommand`` is still publishing its result.  In that window the
        state query is intentionally non-authoritative.  Do not latch that
        transient read as completion; callers can reconcile after command
        delivery without losing the eventual typed failure.
        """
        if refresh_ready and hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train()

        if self.training_completed_shown:
            return True

        if outcome is None:
            terminal_state, terminal_detail = self._training_terminal_outcome()
        else:
            terminal_state, terminal_detail = outcome.state, outcome.detail
        if terminal_state not in {
            TrainingOutcomeState.COMPLETED,
            TrainingOutcomeState.FAILED,
            TrainingOutcomeState.CANCELLED,
        }:
            if report_unverified and not self._training_outcome_unverified_shown:
                self._training_outcome_unverified_shown = True
                self.log_text.append(
                    "Training outcome could not be verified. Refresh the workflow "
                    "status before using the results."
                )
                self.show_status_message(
                    "Training outcome could not be verified · Refresh status"
                )
            return False

        self.training_completed_shown = True
        if terminal_state is TrainingOutcomeState.FAILED:
            detail = terminal_detail or "Training stopped unexpectedly."
            self._ensure_terminal_log_visible(terminal_state, detail)
            self.show_status_message("Training failed · Adjust settings")
            return True
        if terminal_state is TrainingOutcomeState.CANCELLED:
            self._ensure_terminal_log_visible(terminal_state, terminal_detail)
            self.show_status_message("Training stopped")
            return True
        if terminal_state is not TrainingOutcomeState.COMPLETED:
            return False
        self._ensure_terminal_log_visible(
            TrainingOutcomeState.COMPLETED,
            terminal_detail,
        )
        self.show_status_message("Training complete · Review results")
        return True

    def _ensure_terminal_log_visible(
        self,
        terminal_state: TrainingOutcomeState,
        terminal_detail: str | None,
    ) -> None:
        """Keep one terminal line visible after history-log reconstruction."""
        if terminal_state is TrainingOutcomeState.FAILED:
            detail = terminal_detail or "Training stopped unexpectedly."
            message = f"Training failed: {detail}"
        elif terminal_state is TrainingOutcomeState.CANCELLED:
            message = "Training stopped before completion."
        elif terminal_state is TrainingOutcomeState.COMPLETED:
            message = "All training jobs finished."
        else:
            return
        if message not in self.log_text.toPlainText():
            self.log_text.append(message)

    def reconcile_training_terminal_outcome(self) -> bool:
        """Re-read a terminal outcome after async command publication."""
        return self.training_finished(
            refresh_ready=False,
            report_unverified=False,
        )

    def _training_terminal_outcome(
        self,
    ) -> tuple[TrainingOutcomeState | None, str | None]:
        """Read the backend's typed terminal outcome without inferring from copy."""
        if self._typed_port_mode:
            publication = self._read_application_publication()
            if publication is None or not publication.usable:
                return None, None
            outcome = publication.state.training.terminal_outcome
            return outcome.state, outcome.detail
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None:
            return None, None
        # A concurrent analysis command can mark the global view stale, but this
        # query still carries the immutable last-committed training publication.
        state = result.diagnostics.get("state")
        if not isinstance(state, dict):
            return None, None
        training = state.get("training") if isinstance(state, dict) else None
        if not isinstance(training, dict):
            return None, None
        outcome_data = training.get("terminal_outcome")
        if not isinstance(outcome_data, dict):
            return None, None
        try:
            terminal_state = TrainingOutcomeState(str(outcome_data.get("state", "")))
        except ValueError:
            return None, None
        detail = outcome_data.get("detail")
        return terminal_state, str(detail).strip() if detail else None

    def show_status_message(self, message: str, timeout_ms: int = 7000) -> bool:
        """Show a non-modal status message on the application status bar."""
        return show_status_message(self, message, timeout_ms)

    def update_info(self):
        """Delegate info-panel updates to the sidebar."""
        # Info display is handled entirely by the Sidebar component.
        if hasattr(self, "sidebar"):
            self.sidebar.update_info()

    def update_panel(self, *args):
        """Refresh Training and commit a direct render only after success."""
        self._update_panel_content(*args)
        if self._application_render_ledger.render_in_progress:
            return
        publication = self._application_view_publication
        if publication is not None:
            self._application_render_ledger.record_rendered(publication)

    def _update_panel_content(self, *args):
        """Update state-changing content from committed application truth."""
        self.update_info()
        publication = self._read_application_publication()
        if self._publication_port is not None and (
            publication is None or not publication.usable
        ):
            if hasattr(self, "sidebar"):
                self.sidebar.check_ready_to_train(publication=None)
            return
        if publication is not None:
            self._render_training_publication(publication)
        if hasattr(self, "sidebar"):
            self.sidebar.check_ready_to_train(publication=publication)
        self.update_loop()

    def refresh_terminal_publication(self) -> None:
        """Render one accepted terminal generation after observer coalescing."""
        self.update_panel()
        if not self.training_completed_shown or not hasattr(self, "sidebar"):
            return
        outcome = self._latest_terminal_outcome
        if (
            self._terminal_event_log_expected
            and "Training stopped (event)." not in self.log_text.toPlainText()
        ):
            self.log_text.append("Training stopped (event).")
        if outcome is not None:
            self._ensure_terminal_log_visible(outcome.state, outcome.detail)
        else:
            terminal_state, terminal_detail = self._training_terminal_outcome()
            if terminal_state is not None:
                self._ensure_terminal_log_visible(
                    terminal_state,
                    terminal_detail,
                )
        self.sidebar.btn_stop.setEnabled(False)

    def update_loop(self, force_active=False, log_epochs=False):
        """Handle real-time training updates."""
        # 1. Update History Table
        rows = self._history_for_render()
        if rows is None:
            if self.training_completed_shown and self._last_verified_history_rows:
                rows = self._rows_with_terminal_status(
                    self._last_verified_history_rows,
                )
                self._history_query_unavailable_shown = False
            else:
                self._report_history_query_unavailable()
                return
        self._history_query_unavailable_shown = False
        if not rows:
            self._has_verified_history_render = False
            self._clear_training_display()
            return
        if self.training_completed_shown:
            rows = self._rows_with_terminal_status(rows)

        previous_log_signature = self._history_log_signature(
            self.current_plotting_row,
        )
        self._rendered_history_rows = list(rows)
        self.history_table.update_table(rows)
        preferred_row = self._select_preferred_plot_row(
            rows,
            force_active=force_active,
        )
        preferred_identity = self._history_identity(preferred_row)
        selection_changed = preferred_identity != self.current_plotting_identity
        self.current_plotting_identity = preferred_identity
        self.current_plotting_row = preferred_row
        if selection_changed:
            self._last_epoch_count = -1
            self._last_plot_signature = None
            self._selection_pinned_by_user = False
            if self._suppress_log_render_once:
                self._suppress_log_render_once = False
            else:
                self._render_epoch_logs_for_row(preferred_row)
        elif previous_log_signature != self._history_log_signature(preferred_row):
            if self._suppress_log_render_once:
                self._suppress_log_render_once = False
            else:
                self._render_epoch_logs_for_row(preferred_row)

        # 3. Update plots if the selected row has new copied data.
        if self.current_plotting_row:
            try:
                train_metrics, _validation_metrics = self._history_metrics(
                    self.current_plotting_row,
                )
                current_epochs = len(
                    train_metrics.get(TrainRecordKey.ACC, []),
                )
                current_signature = self._row_plot_signature(
                    self.current_plotting_row,
                )
                last_count = getattr(self, "_last_epoch_count", -1)
                if (
                    last_count != current_epochs
                    or self._last_plot_signature != current_signature
                ):
                    self._last_epoch_count = current_epochs
                    self._last_plot_signature = current_signature
                    self.refresh_plot(self.current_plotting_row)
                if log_epochs:
                    self._append_epoch_logs(self.current_plotting_row)
            except Exception:
                logger.warning(
                    "Error reading training epoch data, refreshing plot",
                    exc_info=True,
                )
                self.refresh_plot(self.current_plotting_row)

    def _rows_with_terminal_status(self, rows):
        """Apply an accepted terminal event to a detached busy-query fallback."""
        outcome = self._latest_terminal_outcome
        status_by_outcome = {
            TrainingOutcomeState.COMPLETED: "Completed",
            TrainingOutcomeState.FAILED: "Failed",
            TrainingOutcomeState.CANCELLED: "Stopped",
        }
        status = status_by_outcome.get(outcome.state) if outcome is not None else None
        copied_rows = [dict(row) for row in rows]
        if status is None or not copied_rows:
            return copied_rows
        target_index = next(
            (
                index
                for index, row in enumerate(copied_rows)
                if row.get("is_current_run")
            ),
            len(copied_rows) - 1,
        )
        copied_rows[target_index] = {
            **copied_rows[target_index],
            "status": status,
            "status_detail": (
                outcome.detail
                if outcome is not None and outcome.state is TrainingOutcomeState.FAILED
                else copied_rows[target_index].get("status_detail")
            ),
            "is_active": False,
            "is_current_run": False,
        }
        return copied_rows

    def _row_plot_signature(self, row):
        """Return a compact signature for every series rendered in the plots."""
        train_metrics, validation_metrics = self._history_metrics(row)
        test_metrics = self._history_test_metrics(row)
        return (
            self._series_signature(train_metrics, TrainRecordKey.ACC),
            self._series_signature(train_metrics, TrainRecordKey.LOSS),
            self._series_signature(validation_metrics, RecordKey.ACC),
            self._series_signature(validation_metrics, RecordKey.LOSS),
            self._series_signature(test_metrics, RecordKey.ACC),
        )

    @staticmethod
    def _series_signature(source, key):
        values = source.get(key, []) if hasattr(source, "get") else []
        return tuple(repr(value) for value in values)

    def _append_epoch_logs(self, row) -> None:
        completed_epochs = self._completed_epoch_count(row)
        if completed_epochs <= 0:
            return
        identity = self._history_identity(row)
        if identity is None:
            return
        row_logs = self._logged_epoch_signatures_by_identity.setdefault(identity, {})
        for epoch_index in range(completed_epochs):
            signature = self._epoch_log_signature(row, epoch_index)
            if row_logs.get(epoch_index) == signature:
                continue
            row_logs[epoch_index] = signature
            self.log_text.append(self._format_epoch_log_line(row, epoch_index))

    def _history_log_signature(self, row) -> tuple | None:
        """Return every value currently represented in the selected-row log."""
        if self._history_identity(row) is None:
            return None
        completed_epochs = self._completed_epoch_count(row)
        return (
            row.get("status"),
            row.get("status_detail"),
            tuple(
                self._epoch_log_signature(row, epoch_index)
                for epoch_index in range(completed_epochs)
            ),
        )

    def _render_epoch_logs_for_row(self, row) -> None:
        """Replace the log tab with epoch logs for the selected history row."""
        self.log_text.clear()
        if row is None:
            return
        identity = self._history_identity(row)
        if identity is None:
            return
        completed_epochs = self._completed_epoch_count(row)
        if completed_epochs <= 0:
            self.log_text.setPlaceholderText(
                "No training epoch logs for the selected run yet."
            )
            self._logged_epoch_signatures_by_identity[identity] = {}
            self._append_history_terminal_log(row)
            return

        row_logs: dict[int, tuple] = {}
        for epoch_index in range(completed_epochs):
            signature = self._epoch_log_signature(row, epoch_index)
            row_logs[epoch_index] = signature
            self.log_text.append(self._format_epoch_log_line(row, epoch_index))
        self._logged_epoch_signatures_by_identity[identity] = row_logs
        self._append_history_terminal_log(row)

    def _append_history_terminal_log(self, row) -> None:
        """Render terminal copy owned by the selected detached history row."""
        if not isinstance(row, dict):
            return
        status = row.get("status")
        detail = row.get("status_detail")
        if status == "Failed":
            message = (
                str(detail).strip()
                if isinstance(detail, str) and detail.strip()
                else "Training stopped unexpectedly."
            )
            self.log_text.append(f"Training failed: {message}")
        elif status == "Stopped":
            self.log_text.append("Training stopped before completion.")
        elif status in {"Completed", "Completed early"}:
            self.log_text.append(
                str(detail).strip()
                if status == "Completed early"
                and isinstance(detail, str)
                and detail.strip()
                else "All training jobs finished."
            )

    @staticmethod
    def _completed_epoch_count(row) -> int:
        train_metrics, _validation_metrics = TrainingPanel._history_metrics(row)
        train_values = train_metrics.get(TrainRecordKey.ACC, [])
        if not train_values:
            train_values = train_metrics.get(TrainRecordKey.LOSS, [])
        train_count = len(train_values)
        try:
            value = row.get("epoch", train_count)
            if not isinstance(value, (int, str)):
                return train_count
            row_epoch = int(value)
        except (TypeError, ValueError):
            return train_count
        if row_epoch <= 0:
            return train_count
        return min(train_count, row_epoch)

    def _epoch_log_signature(self, row, epoch_index: int) -> tuple:
        train_metrics, validation_metrics = self._history_metrics(row)
        return (
            self._metric_at(train_metrics, TrainRecordKey.LOSS, epoch_index),
            self._metric_at(train_metrics, TrainRecordKey.ACC, epoch_index),
            self._metric_at(train_metrics, TrainRecordKey.AUC, epoch_index),
            self._metric_at(validation_metrics, RecordKey.LOSS, epoch_index),
            self._metric_at(validation_metrics, RecordKey.ACC, epoch_index),
            self._metric_at(validation_metrics, RecordKey.AUC, epoch_index),
            self._metric_at(train_metrics, TrainRecordKey.LR, epoch_index),
            self._metric_at(train_metrics, TrainRecordKey.TIME, epoch_index),
        )

    def _format_epoch_log_line(self, row, epoch_index: int) -> str:
        train_metrics, validation_metrics = self._history_metrics(row)
        values = {
            "train_loss": self._metric_at(
                train_metrics,
                TrainRecordKey.LOSS,
                epoch_index,
            ),
            "train_acc": self._metric_at(
                train_metrics,
                TrainRecordKey.ACC,
                epoch_index,
            ),
            "train_auc": self._metric_at(
                train_metrics,
                TrainRecordKey.AUC,
                epoch_index,
            ),
            "val_loss": self._metric_at(
                validation_metrics,
                RecordKey.LOSS,
                epoch_index,
            ),
            "val_acc": self._metric_at(
                validation_metrics,
                RecordKey.ACC,
                epoch_index,
            ),
            "val_auc": self._metric_at(
                validation_metrics,
                RecordKey.AUC,
                epoch_index,
            ),
            "lr": self._metric_at(train_metrics, TrainRecordKey.LR, epoch_index),
            "time": self._metric_at(train_metrics, TrainRecordKey.TIME, epoch_index),
        }
        epoch = epoch_index + 1
        return (
            f"Training epoch {epoch}: "
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

    @staticmethod
    def _history_metrics(row) -> tuple[dict, dict]:
        metrics = row.get("metrics", {}) if isinstance(row, dict) else {}
        if not isinstance(metrics, dict):
            return {}, {}
        train_metrics = metrics.get("train", {})
        validation_metrics = metrics.get("validation", {})
        return (
            train_metrics if isinstance(train_metrics, dict) else {},
            validation_metrics if isinstance(validation_metrics, dict) else {},
        )

    @staticmethod
    def _history_test_metrics(row) -> dict:
        metrics = row.get("metrics", {}) if isinstance(row, dict) else {}
        if not isinstance(metrics, dict):
            return {}
        test_metrics = metrics.get("test", {})
        return test_metrics if isinstance(test_metrics, dict) else {}

    @staticmethod
    def _history_identity(row_or_identity) -> tuple[int, int] | None:
        if not isinstance(row_or_identity, dict):
            return None
        identity = row_or_identity.get("identity", row_or_identity)
        if not isinstance(identity, dict):
            return None
        plan_index = identity.get("plan_index")
        run_index = identity.get("run_index")
        if (
            isinstance(plan_index, bool)
            or not isinstance(plan_index, int)
            or plan_index < 0
            or isinstance(run_index, bool)
            or not isinstance(run_index, int)
            or run_index < 0
        ):
            return None
        return plan_index, run_index

    @classmethod
    def _history_row_for_identity(cls, rows, identity):
        return next(
            (row for row in rows if cls._history_identity(row) == identity),
            None,
        )

    def _history_for_render(self):
        result: CommandResult | None
        if self._typed_port_mode:
            publication = self._read_application_publication()
            if publication is None or not publication.usable:
                self._has_verified_history_render = False
                return None
            if publication.training_history is not None:
                rows = deepcopy(list(publication.training_history))
                self._has_verified_history_render = bool(rows)
                self._last_verified_history_rows = rows
                return deepcopy(rows)
            query_port = self._query_port
            if query_port is None:
                self._has_verified_history_render = False
                return None
            try:
                result = query_port.query_training_history(
                    expected_publication_generation=publication.generation,
                )
            except Exception:
                logger.error(
                    "Training history publication is unavailable.",
                    exc_info=True,
                )
                self._has_verified_history_render = False
                return None
        else:
            result = execute_application_command(
                self,
                QueryStateCommand(query="training_history"),
                refresh=False,
            )
        if result is None:
            self._has_verified_history_render = False
            if self._typed_port_mode:
                return None
            return self._compatibility_history_for_render()
        if result.failed:
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "training_history":
            return None
        diagnostic_rows = diagnostics.get("rows")
        if not isinstance(diagnostic_rows, list):
            return None
        self._has_verified_history_render = bool(diagnostic_rows)
        self._last_verified_history_rows = list(diagnostic_rows)
        return list(self._last_verified_history_rows)

    def _compatibility_history_for_render(self):
        if self.controller is None:
            return []
        try:
            rows = run_controller_compatibility_call(
                self,
                self.controller.get_formatted_history,
            )
        except ControllerCompatibilityUnavailableError:
            return None
        return project_training_history_rows(rows)

    def _report_history_query_unavailable(self) -> None:
        """Keep the last verified render while a history query is unstable."""
        if (
            self._history_query_unavailable_shown
            or not self._has_verified_history_render
        ):
            return
        self._history_query_unavailable_shown = True
        self.show_status_message(
            "Training view is updating · Keeping the last verified results"
        )

    # check_ready_to_train moved to Sidebar

    def closeEvent(self, event):  # noqa: N802
        """Handle panel close, delegating to base cleanup.

        Args:
            event: The ``QCloseEvent``.

        """
        for attribute_name in ("tab_acc", "tab_loss"):
            metric_tab = getattr(self, attribute_name, None)
            if metric_tab is not None:
                metric_tab.close()
        self.cleanup()
        super().closeEvent(event)

    def begin_training_resource_preview_shutdown(self) -> None:
        """Fence advisory preview work without blocking the GUI thread."""
        sidebar = getattr(self, "sidebar", None)
        shutdown = getattr(sidebar, "_shutdown_training_resource_previews", None)
        if callable(shutdown):
            shutdown()

    def cancel_training_resource_preview_shutdown(self) -> None:
        """Reopen advisory previews after a cancelled desktop close attempt."""
        sidebar = getattr(self, "sidebar", None)
        cancel_shutdown = getattr(
            sidebar,
            "_cancel_training_resource_preview_shutdown",
            None,
        )
        if callable(cancel_shutdown):
            cancel_shutdown()

    def training_resource_preview_background_work_snapshot(
        self,
    ) -> dict[str, int | bool]:
        """Return exact backend preview ownership for desktop close accounting."""
        query_port = self._query_port
        get_snapshot = getattr(
            query_port,
            "training_resource_preview_background_work_snapshot",
            None,
        )
        if not callable(get_snapshot):
            return {"idle": True, "remaining_workers": 0, "alive_workers": 0}
        try:
            snapshot = get_snapshot()
        except Exception:
            logger.exception("Could not verify Training resource preview cleanup.")
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        if not isinstance(snapshot, Mapping):
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        remaining = snapshot.get("remaining_workers", 0)
        alive = snapshot.get("alive_workers", 0)
        if (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or remaining < 0
            or isinstance(alive, bool)
            or not isinstance(alive, int)
            or alive < 0
        ):
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        return {
            "idle": remaining == 0,
            "remaining_workers": remaining,
            "alive_workers": alive,
        }

    def cleanup(self) -> None:
        """Cancel queued publication work and release observer bridges."""
        self.begin_training_resource_preview_shutdown()
        self._application_render_ledger.cleanup()
        super().cleanup()
