"""Main application window module for XBrainLab.

Provides the top-level QMainWindow that manages navigation, panel switching,
and AI assistant integration.
"""

import contextlib
import sys
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from threading import RLock
from typing import Any, cast
from uuid import uuid4

from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QSignalBlocker,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.commands import (
    QueryStateCommand,
    StopTrainingCommand,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    application_background_tasks_idle,
    application_runtime_initialized,
    application_ui_runtime,
    close_application_runtime,
    execute_application_command,
    execute_application_command_async,
    has_real_application_context,
    release_application_shutdown_fence,
    request_application_shutdown_fence,
    training_transient_ui_port,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
    DesktopApplicationPublicationRenderer,
)
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.panel_navigation import PanelPreparationFailure
from XBrainLab.ui.product_language import workflow_stage_hint
from XBrainLab.ui.refresh_coordinator import refresh_after_navigation
from XBrainLab.ui.status import transient_status_remaining_ms
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.window_geometry_lifecycle import WindowGeometryLifecycle

# Compatibility hooks for older tests and debug fixtures that patch these names
# directly. Runtime loading still happens through the lazy loader helpers below.
AgentManager = None
InfoPanelService = None
DatasetPanel = None
PreprocessPanel = None
TrainingPanel = None
EvaluationPanel = None
VisualizationPanel = None


class _ResponsiveTopBar(QFrame):
    """Notify the shell when docks change the navigation's usable width."""

    resized = pyqtSignal()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.resized.emit()


SHUTDOWN_FENCE_RELEASE_RETRY_MS = 250
SHUTDOWN_FENCE_RELEASE_MAX_ATTEMPTS = 8
ASSISTANT_SHUTDOWN_RETRY_INTERVAL_MS = 250
# Controller cleanup can spend up to four seconds fencing optional RAG work,
# three seconds stopping generation, and two seconds releasing its worker thread.
# Keep the GUI responsive while allowing that bounded ownership chain to finish.
ASSISTANT_SHUTDOWN_MAX_WAIT_MS = 12_000
ASSISTANT_SHUTDOWN_MAX_ATTEMPTS = (
    ASSISTANT_SHUTDOWN_MAX_WAIT_MS // ASSISTANT_SHUTDOWN_RETRY_INTERVAL_MS
)


@dataclass(frozen=True)
class _PanelSpec:
    attr: str
    label: str
    module: str
    class_name: str
    controller_names: tuple[str, ...]
    background_import_safe: bool = True


_PANEL_SPECS: tuple[_PanelSpec, ...] = (
    _PanelSpec(
        "dataset_panel",
        "Dataset",
        "XBrainLab.ui.panels.dataset.panel",
        "DatasetPanel",
        (),
    ),
    _PanelSpec(
        "preprocess_panel",
        "Preprocess",
        "XBrainLab.ui.panels.preprocess.panel",
        "PreprocessPanel",
        (),
    ),
    _PanelSpec(
        "training_panel",
        "Training",
        "XBrainLab.ui.panels.training.panel",
        "TrainingPanel",
        (),
        background_import_safe=False,
    ),
    _PanelSpec(
        "evaluation_panel",
        "Evaluation",
        "XBrainLab.ui.panels.evaluation.panel",
        "EvaluationPanel",
        (),
        background_import_safe=False,
    ),
    _PanelSpec(
        "visualization_panel",
        "Visualization",
        "XBrainLab.ui.panels.visualization.panel",
        "VisualizationPanel",
        (),
        background_import_safe=False,
    ),
)

_STARTUP_PREWARM_MODULES: tuple[str, ...] = (
    "XBrainLab.backend.application.service",
    "XBrainLab.backend.load_data.raw_data_loader",
)
_LAZY_IMPORT_LOCK = RLock()


def _load_panel_class(module_name: str, class_name: str) -> Any:
    """Load a workflow panel class only when the panel is first opened."""
    patched = globals().get(class_name)
    if patched is not None:
        return patched
    with _LAZY_IMPORT_LOCK:
        module = import_module(module_name)
    return getattr(module, class_name)


def _load_agent_manager_class():
    """Load the AI assistant stack only when the user opens it."""
    patched = globals().get("AgentManager")
    if patched is not None:
        return patched
    module = import_module("XBrainLab.ui.components.agent_manager")
    return module.AgentManager


def _load_info_panel_service_class() -> Callable[..., Any]:
    """Load the aggregate publication service during desktop composition."""
    patched = globals().get("InfoPanelService")
    if patched is not None:
        return patched
    module = import_module("XBrainLab.ui.components.info_panel_service")
    return module.InfoPanelService


def _prewarm_startup_modules(
    modules: tuple[str, ...] = _STARTUP_PREWARM_MODULES,
) -> dict[str, list[str]]:
    """Import non-UI heavy modules after startup so first use is less abrupt."""
    loaded: list[str] = []
    failed: list[str] = []
    for module_name in modules:
        try:
            with _LAZY_IMPORT_LOCK:
                import_module(module_name)
        except Exception:  # noqa: PERF203
            logger.debug("Startup prewarm failed for %s", module_name, exc_info=True)
            failed.append(module_name)
        else:
            loaded.append(module_name)
    return {"loaded": loaded, "failed": failed}


def _require_global_thread_pool() -> QThreadPool:
    """Return the Qt pool before a caller commits background task ownership."""
    thread_pool = QThreadPool.globalInstance()
    if thread_pool is None:
        raise RuntimeError("Qt thread pool is unavailable.")
    return thread_pool


class _LazyPanelPlaceholder(QWidget):
    """Lightweight stand-in for workflow panels that are not opened yet."""

    def __init__(self, panel_label: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"Loading {panel_label}...")
        label.setObjectName("LazyPanelPlaceholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel("Please wait.")
        self.detail.setObjectName("LazyPanelPlaceholderDetail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(label)
        layout.addWidget(self.detail)
        layout.addStretch()

    def show_prepare_failure(self) -> None:
        """Keep a failed first-open recoverable without showing a modal popup."""
        self.detail.setText("Could not open this panel. Select it again to retry.")

    def show_preparing(self) -> None:
        """Reset a prior failure message when the user retries preparation."""
        self.detail.setText("Please wait.")


class _PanelPrepareDelivery(QObject):
    """Deliver background import completion to one live MainWindow."""

    def __init__(self, window: Any, panel_index: int) -> None:
        super().__init__(window)
        self._window_ref = weakref.ref(window)
        self._panel_index = panel_index

    @pyqtSlot(object)
    def handle_result(self, panel_class: Any) -> None:
        window = self._window_ref()
        if window is None or sip.isdeleted(window):
            return
        window._on_panel_prepare_result(self._panel_index, panel_class)

    @pyqtSlot(tuple)
    def handle_error(self, error: tuple) -> None:
        window = self._window_ref()
        if window is None or sip.isdeleted(window):
            return
        window._on_panel_prepare_error(self._panel_index, error)

    @pyqtSlot()
    def handle_finished(self) -> None:
        window = self._window_ref()
        if window is not None and not sip.isdeleted(window):
            window._clear_panel_prepare_worker(self._panel_index, self)
        if not sip.isdeleted(self):
            self.deleteLater()


class MainWindow(QMainWindow):
    """The main application window for XBrainLab (PyQt6 version).

    This window manages the overall layout, including:

    - Top Navigation Bar: For switching between main panels (Dataset,
      Preprocess, Training, etc.).
    - Stacked Widget: Holds the content of each panel.
    - Dock Widgets: For the AI Assistant and Data Info panel.
    - Agent System: Initializes and manages the background AI agent thread.

    Attributes:
        study: The application Study instance holding controllers and data.
        agent_initialized: Whether the AI agent has been lazily initialized.
        info_service: InfoPanelService managing aggregate info panel updates.
        stack: QStackedWidget holding all main functional panels.
        nav_btns: List of navigation QPushButtons in the top bar.
        ai_btn: Toggle button for the AI assistant dock.
        agent_manager: AgentManager orchestrating AI agent lifecycle.

    """

    # Signals to control the worker
    sig_init_agent = pyqtSignal()
    sig_generate = pyqtSignal(str, str)
    shutdown_completed = pyqtSignal(object)
    _close_retry_requested = pyqtSignal(int)
    COMPACT_NAV_BREAKPOINT = 720
    ASSISTANT_DOCK_STANDARD_WIDTH = 420
    ASSISTANT_DOCK_MINIMUM_WIDTH = 320
    ASSISTANT_CENTRAL_WIDGET_MINIMUM_WIDTH = 436
    ASSISTANT_DOCK_CENTRAL_MINIMUM_WIDTH = 440

    def __init__(self, study):
        """Initialize the main window.

        Args:
            study: The application Study instance providing controllers
                and shared state.

        """
        super().__init__()
        self.study = study
        cast(Any, self._close_retry_requested.connect)(
            self._arm_close_retry,
            Qt.ConnectionType.QueuedConnection,
        )
        self.setWindowTitle("XBrainLab")
        self.window_geometry = WindowGeometryLifecycle(self)
        self.window_geometry.restore_initial_geometry()

        self.agent_initialized = False  # Flag for lazy loading
        self.agent_manager = None
        self._loaded_panel_indices: set[int] = set()
        self._startup_prewarm_worker = None
        self._panel_prepare_workers: dict[
            int,
            tuple[Worker, _PanelPrepareDelivery],
        ] = {}
        self._panel_prepare_queue: list[int] = []
        self._panel_prepare_active_index: int | None = None
        self._prepared_panel_classes: dict[int, Any] = {}
        self._panel_materialization_pending: set[int] = set()
        self._panel_ready_callbacks: dict[
            int,
            list[Callable[[QWidget], None]],
        ] = {}
        self._panel_failed_callbacks: dict[
            int,
            list[Callable[[PanelPreparationFailure], None]],
        ] = {}
        self._close_retry_pending = False
        self._closing_in_progress = False
        self._close_attempt_id: str | None = None
        self._pre_close_background_snapshot: dict[str, Any] | None = None
        self._shutdown_terminal_snapshot_emitted = False
        self._desktop_render_shutdown_started = False
        self._shutdown_fence_active = False
        self._training_close_check_in_flight = False
        self._training_close_ready = False
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._shutdown_only_mode = False
        self._force_shutdown_requested = False
        self._assistant_shutdown_attempts = 0
        self._assistant_shutdown_pending_logged = False
        self._assistant_shutdown_slow_logged = False
        self._assistant_cleanup_signal = None
        self._assistant_cleanup_runtime = None
        self._model_download_terminal_signal = None
        self._model_download_lifecycle = None
        self._defer_initial_application_runtime = True
        self._deferred_application_subscriptions: list[
            tuple[str, Callable[..., Any]]
        ] = []
        self._startup_prewarm_retry_pending = False
        self._assistant_dock_resize_pending = False

        # Apply VS Code Dark Theme (Adjusted for Top Bar)
        self.apply_vscode_theme()

        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # This is the existing product status surface, not an automation-only
        # widget. Long-running UI commands project their public operation
        # identity and progress here so assistive technology and GUI drivers
        # can observe the same state a user sees.
        owned_operation_progress = self.statusBar()
        owned_operation_progress.setObjectName("OwnedOperationProgress")
        owned_operation_progress.setProperty("operationId", "")
        owned_operation_progress.setProperty("stage", "Idle")
        owned_operation_progress.setProperty("progress", "idle")
        owned_operation_progress.setProperty("indeterminate", False)
        owned_operation_progress.setProperty("operationPhase", "idle")

        # Vertical Layout: Top Bar | Main Content
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Top Navigation Bar
        self.top_bar = _ResponsiveTopBar()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.setFixedHeight(50)
        self.top_bar.resized.connect(
            lambda: QTimer.singleShot(0, self._update_navigation_layout)
        )
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(10, 0, 10, 0)
        self.top_bar_layout.setSpacing(10)

        # Navigation Buttons
        self.compact_nav_combo = QComboBox()
        self.compact_nav_combo.setObjectName("CompactNavigation")
        self.compact_nav_combo.setToolTip("Workflow page")
        self.compact_nav_combo.setMinimumWidth(150)
        self.compact_nav_combo.setMaximumWidth(220)
        self.compact_nav_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.compact_nav_combo.addItems(
            [spec.label for spec in _PANEL_SPECS],
        )
        self.compact_nav_combo.currentIndexChanged.connect(
            self._request_page_from_navigation,
        )
        self.compact_nav_combo.hide()
        self.top_bar_layout.addWidget(self.compact_nav_combo)

        self.nav_btns = []
        self.add_nav_btn("Dataset", 0, "Dataset")
        self.add_nav_btn("Preprocess", 1, "Preprocess")
        self.add_nav_btn("Training", 2, "Training")
        self.add_nav_btn("Evaluation", 3, "Evaluation")
        self.add_nav_btn("Visualization", 4, "Visualization")

        self.top_bar_spacer = QWidget()
        self.top_bar_spacer.setObjectName("TopBarFlexibleSpace")
        self.top_bar_spacer.setStyleSheet("background-color: transparent;")
        self.top_bar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.top_bar_layout.addWidget(self.top_bar_spacer)

        # AI Toggle Button
        self.ai_btn = QPushButton("AI Assistant")
        self.ai_btn.setCheckable(True)
        self.ai_btn.setChecked(False)  # Default Off
        self.ai_btn.clicked.connect(self.toggle_ai_dock)
        self.ai_btn.setObjectName("ActionBtn")
        self.ai_btn.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.ai_btn.ensurePolished()
        self._sync_assistant_entry_width()
        self.top_bar_layout.addWidget(self.ai_btn)

        main_layout.addWidget(self.top_bar)
        QTimer.singleShot(0, self._update_navigation_layout)

        # 2. Services (Must be before panels to allow registration)
        info_service_class = _load_info_panel_service_class()
        self.info_service = info_service_class(self.study)

        # 3. Stacked Widget (Content Area)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self._application_publication_renderer = None
        self._last_rendered_application_publication: (
            ApplicationViewPublication | None
        ) = None
        self._last_fully_rendered_application_publication: (
            ApplicationViewPublication | None
        ) = None
        self._application_status_restore_timer = QTimer(self)
        self._application_status_restore_timer.setSingleShot(True)
        self._application_status_restore_timer.timeout.connect(
            self._restore_application_publication_status
        )

        # Initialize Panels
        self.init_panels()

        self._schedule_initial_panel_load()
        self._schedule_startup_prewarm()

        logger.info("MainWindow initialized")

    def apply_vscode_theme(self):
        """Apply the VS Code dark theme stylesheet to the main window."""
        self.setStyleSheet(Stylesheets.MAIN_WINDOW)

    def add_nav_btn(self, name, index, text):
        """Create and add a navigation button to the top bar.

        Args:
            name: Tooltip name for the button.
            index: Panel index in the stacked widget to switch to.
            text: Display text for the button.

        """
        btn = QPushButton(text)
        btn.setToolTip(name)
        btn.setCheckable(True)
        btn.setObjectName("NavButton")

        btn.clicked.connect(lambda: self._request_page_from_navigation(index))

        self.top_bar_layout.addWidget(btn)
        self.nav_btns.append(btn)

        if index == 0:
            btn.setChecked(True)

    def switch_page(
        self,
        index: int,
        *,
        on_ready: Callable[[QWidget], None] | None = None,
        on_failed: Callable[[PanelPreparationFailure], None] | None = None,
    ) -> bool:
        """Activate a ready panel or asynchronously prepare its first open.

        Public programmatic navigation follows the same non-blocking path as a
        navigation click. Only a materialized panel is activated synchronously.

        Args:
            index: Zero-based index of the panel to display.
            on_ready: Optional one-shot callback delivered on the GUI thread
                after the target panel is materialized.
            on_failed: Optional one-shot callback delivered on the GUI thread
                when this panel preparation attempt fails terminally.

        Returns:
            ``True`` when the panel was already materialized and activated,
            otherwise ``False`` while preparation continues.
        """
        return self._request_page_from_navigation(
            index,
            on_ready=on_ready,
            on_failed=on_failed,
        )

    def _request_page_from_navigation(
        self,
        index: int,
        *,
        on_ready: Callable[[QWidget], None] | None = None,
        on_failed: Callable[[PanelPreparationFailure], None] | None = None,
    ) -> bool:
        """Show a first-open placeholder and prepare expensive imports off-thread."""
        if index < 0 or index >= len(_PANEL_SPECS):
            return False
        if self._closing_in_progress or sip.isdeleted(self):
            return False

        self._show_page(index)
        panel = self._materialized_panel(index)
        if panel is not None:
            self._finish_page_activation(index)
            if on_ready is not None:
                self._deliver_panel_ready_callback(index, on_ready, panel)
            return True

        if on_ready is not None:
            self._panel_ready_callbacks.setdefault(index, []).append(on_ready)
        if on_failed is not None:
            self._panel_failed_callbacks.setdefault(index, []).append(on_failed)
        placeholder = self.stack.widget(index)
        if isinstance(placeholder, _LazyPanelPlaceholder):
            placeholder.show_preparing()

        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(f"Opening {_PANEL_SPECS[index].label}...")
        self._request_panel_prepare(index)
        return False

    def _materialized_panel(self, index: int) -> QWidget | Any | None:
        """Return a ready panel while preserving legacy injected test panels."""
        if index < 0 or index >= len(_PANEL_SPECS):
            return None
        spec = _PANEL_SPECS[index]
        panel = getattr(self, spec.attr, None)
        if index in self._loaded_panel_indices:
            return panel
        if panel is None or isinstance(panel, _LazyPanelPlaceholder):
            return None
        self._loaded_panel_indices.add(index)
        return panel

    def _deliver_panel_ready_callback(
        self,
        index: int,
        callback: Callable[[QWidget], None],
        panel: QWidget | Any,
    ) -> None:
        try:
            callback(panel)
        except Exception:
            logger.exception(
                "Panel-ready callback failed for %s",
                _PANEL_SPECS[index].label,
            )

    def _deliver_panel_ready_callbacks(self, index: int, panel: QWidget) -> None:
        """Deliver and release callbacks waiting for one materialized panel."""
        callbacks = self._panel_ready_callbacks.pop(index, [])
        self._panel_failed_callbacks.pop(index, None)
        for callback in callbacks:
            self._deliver_panel_ready_callback(index, callback, panel)

    def _deliver_panel_failed_callback(
        self,
        index: int,
        callback: Callable[[PanelPreparationFailure], None],
        failure: PanelPreparationFailure,
    ) -> None:
        try:
            callback(failure)
        except Exception:
            logger.exception(
                "Panel-failed callback failed for %s",
                _PANEL_SPECS[index].label,
            )

    def _deliver_panel_failed_callbacks(self, index: int) -> None:
        """Fail and release every callback waiting on this preparation attempt."""
        self._panel_ready_callbacks.pop(index, None)
        callbacks = self._panel_failed_callbacks.pop(index, [])
        if not callbacks:
            return
        spec = _PANEL_SPECS[index]
        failure = PanelPreparationFailure(
            panel_index=index,
            panel_name=spec.label,
            message=f"Could not open {spec.label}.",
        )
        for callback in callbacks:
            self._deliver_panel_failed_callback(index, callback, failure)

    def _show_page(self, index: int) -> None:
        """Select one stack page and synchronize navigation controls."""
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        with QSignalBlocker(self.compact_nav_combo):
            self.compact_nav_combo.setCurrentIndex(index)

    def resizeEvent(self, event):  # noqa: N802
        """Use a page selector when the assistant leaves little nav width."""
        super().resizeEvent(event)
        if hasattr(self, "top_bar"):
            QTimer.singleShot(0, self._update_navigation_layout)
        self._schedule_assistant_dock_resize()

    def _update_navigation_layout(self) -> None:
        """Keep every workflow destination readable in the available top bar."""
        if not hasattr(self, "compact_nav_combo"):
            return
        self._sync_assistant_entry_width()
        compact = self.top_bar.contentsRect().width() < self.COMPACT_NAV_BREAKPOINT
        self.compact_nav_combo.setVisible(compact)
        self.top_bar_spacer.setVisible(not compact)
        for button in self.nav_btns:
            button.setVisible(not compact)
        self.top_bar_layout.invalidate()
        self.top_bar_layout.activate()

    def _sync_assistant_entry_width(self) -> None:
        """Reserve the current styled font width for the Assistant entry point."""
        if not hasattr(self, "ai_btn"):
            return
        self.ai_btn.ensurePolished()
        required_width = max(
            self.ai_btn.sizeHint().width(),
            self.ai_btn.fontMetrics().horizontalAdvance(self.ai_btn.text()) + 32,
        )
        if self.ai_btn.minimumWidth() != required_width:
            self.ai_btn.setMinimumWidth(required_width)

    def _activate_page(self, index: int) -> None:
        """Activate an already materialized page through the synchronous API."""
        self._show_page(index)
        self._finish_page_activation(index)

    def _finish_page_activation(self, index: int) -> None:
        """Refresh and repaint one materialized page after navigation."""
        if index not in self._loaded_panel_indices:
            return
        if self.stack.count() > index and self.stack.currentIndex() != index:
            return

        refresh_after_navigation(self, index)
        self._repaint_navigation_surface()
        QTimer.singleShot(0, self._repaint_navigation_surface)
        if has_real_application_context(self):
            self._restore_application_publication_status()
        elif self.agent_manager is None:
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(self._backend_status_bar_hint())

    def _request_panel_prepare(self, index: int) -> None:
        """Start at most one background class import for a hidden panel."""
        if (
            index in self._loaded_panel_indices
            or index in self._panel_materialization_pending
            or self._closing_in_progress
        ):
            return
        if index in self._prepared_panel_classes:
            self._schedule_panel_materialization(index)
            return
        if (
            index in self._panel_prepare_workers
            or index in self._panel_prepare_queue
            or self._panel_prepare_active_index == index
        ):
            return

        if (
            self._startup_prewarm_worker is not None
            or self._panel_prepare_active_index is not None
        ):
            self._panel_prepare_queue.append(index)
            return
        self._start_panel_prepare(index)

    def _start_panel_prepare(self, index: int) -> None:
        """Start one queued panel import without another import worker in flight."""
        spec = _PANEL_SPECS[index]
        if not spec.background_import_safe:
            self._panel_prepare_active_index = index
            QTimer.singleShot(0, lambda: self._prepare_panel_class_on_gui(index))
            return

        delivery: _PanelPrepareDelivery | None = None
        try:
            worker = Worker(_load_panel_class, spec.module, spec.class_name)
            delivery = _PanelPrepareDelivery(self, index)
            worker.signals.result.connect(delivery.handle_result)
            worker.signals.error.connect(delivery.handle_error)
            worker.signals.finished.connect(delivery.handle_finished)
            self._panel_prepare_workers[index] = (worker, delivery)
            self._panel_prepare_active_index = index

            thread_pool = _require_global_thread_pool()
            thread_pool.start(worker)
        except Exception as exc:
            self._panel_prepare_workers.pop(index, None)
            if self._panel_prepare_active_index == index:
                self._panel_prepare_active_index = None
            if delivery is not None:
                delivery.deleteLater()
            logger.warning("Could not start %s panel preparation: %s", spec.label, exc)
            self._show_panel_prepare_failure(index)
            QTimer.singleShot(0, self._start_next_panel_prepare)

    def _prepare_panel_class_on_gui(self, index: int) -> None:
        """Resolve Qt-native panel modules on the application thread."""
        if self._closing_in_progress or self._panel_prepare_active_index != index:
            if self._panel_prepare_active_index == index:
                self._panel_prepare_active_index = None
            return
        spec = _PANEL_SPECS[index]
        try:
            panel_class = _load_panel_class(spec.module, spec.class_name)
        except Exception as exc:
            logger.warning("Could not prepare %s panel: %s", spec.label, exc)
            self._panel_prepare_active_index = None
            self._show_panel_prepare_failure(index)
            QTimer.singleShot(0, self._start_next_panel_prepare)
            return

        self._panel_prepare_active_index = None
        self._on_panel_prepare_result(index, panel_class)
        QTimer.singleShot(0, self._start_next_panel_prepare)

    def _start_next_panel_prepare(self) -> None:
        """Start the next valid first-open request after prior ownership ends."""
        if (
            self._closing_in_progress
            or self._startup_prewarm_worker is not None
            or self._panel_prepare_active_index is not None
        ):
            return
        while self._panel_prepare_queue:
            index = self._panel_prepare_queue.pop(0)
            if (
                index in self._loaded_panel_indices
                or index in self._panel_materialization_pending
                or index in self._prepared_panel_classes
            ):
                continue
            self._start_panel_prepare(index)
            if self._panel_prepare_active_index is not None:
                return

    def _on_panel_prepare_result(self, index: int, panel_class: Any) -> None:
        """Cache a prepared class and queue QWidget creation on the GUI thread."""
        if self._closing_in_progress or sip.isdeleted(self):
            return
        self._prepared_panel_classes[index] = panel_class
        if self.stack.currentIndex() == index:
            self._schedule_panel_materialization(index)

    def _on_panel_prepare_error(self, index: int, error: tuple) -> None:
        """Expose a recoverable inline first-open failure without a modal dialog."""
        message = error[1] if len(error) > 1 else error
        logger.warning(
            "Could not prepare %s panel: %s",
            _PANEL_SPECS[index].label,
            message,
        )
        self._show_panel_prepare_failure(index)

    def _show_panel_prepare_failure(self, index: int) -> None:
        placeholder = self.stack.widget(index)
        if isinstance(placeholder, _LazyPanelPlaceholder):
            placeholder.show_prepare_failure()
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(
                f"Could not open {_PANEL_SPECS[index].label} · Select it to retry",
                6000,
            )
        self._deliver_panel_failed_callbacks(index)

    def _clear_panel_prepare_worker(
        self,
        index: int,
        delivery: _PanelPrepareDelivery | None = None,
    ) -> None:
        """Release one background import owner after its terminal signal."""
        owner = self._panel_prepare_workers.get(index)
        if delivery is not None and (owner is None or owner[1] is not delivery):
            return
        self._panel_prepare_workers.pop(index, None)
        if self._panel_prepare_active_index == index:
            self._panel_prepare_active_index = None
        QTimer.singleShot(0, self._start_next_panel_prepare)

    def _restore_panel_placeholder(self, index: int) -> _LazyPanelPlaceholder:
        """Restore the pre-materialization widget after a failed construction."""
        spec = _PANEL_SPECS[index]
        current = self.stack.widget(index)
        if isinstance(current, _LazyPanelPlaceholder):
            placeholder = current
        else:
            was_current = self.stack.currentIndex() == index
            if current is not None:
                self.stack.removeWidget(current)
                current.setParent(None)
                current.deleteLater()
            placeholder = _LazyPanelPlaceholder(spec.label, self)
            self.stack.insertWidget(index, placeholder)
            if was_current:
                self.stack.setCurrentIndex(index)
        setattr(self, spec.attr, placeholder)
        return placeholder

    def _handle_panel_materialization_failure(
        self,
        index: int,
        error: Exception,
    ) -> None:
        """Rollback a failed prepared class without poisoning the next attempt."""
        spec = _PANEL_SPECS[index]
        logger.warning(
            "Could not construct prepared %s panel: %s",
            spec.label,
            error,
            exc_info=True,
        )
        self._prepared_panel_classes.pop(index, None)
        self._panel_materialization_pending.discard(index)
        self._loaded_panel_indices.discard(index)
        self._clear_panel_prepare_worker(index)
        self._restore_panel_placeholder(index)
        self._show_panel_prepare_failure(index)

    def _schedule_panel_materialization(self, index: int) -> None:
        """Queue QWidget creation after the navigation click has returned."""
        if (
            index in self._loaded_panel_indices
            or index in self._panel_materialization_pending
            or index not in self._prepared_panel_classes
            or self._closing_in_progress
        ):
            return
        self._panel_materialization_pending.add(index)
        window_ref = weakref.ref(self)

        def _materialize_if_alive() -> None:
            window = window_ref()
            if window is None or sip.isdeleted(window):
                return
            window._panel_materialization_pending.discard(index)
            if window._closing_in_progress or window.stack.currentIndex() != index:
                return
            panel_class = window._prepared_panel_classes.get(index)
            try:
                panel = window._materialize_panel(index, panel_class=panel_class)
            except Exception as exc:
                window._handle_panel_materialization_failure(index, exc)
                return
            if panel is not None:
                window._finish_page_activation(index)
                window._deliver_panel_ready_callbacks(index, panel)

        QTimer.singleShot(0, _materialize_if_alive)

    def _repaint_navigation_surface(self) -> None:
        """Flush page and navigation paints after a stacked-page transition."""
        for button in self.nav_btns:
            button.updateGeometry()
            button.repaint()
        current = self.stack.currentWidget()
        if current is not None:
            current.updateGeometry()
            current.repaint()
            for right_panel in current.findChildren(QWidget, "RightPanel"):
                if right_panel.isVisible():
                    right_panel.repaint()

    def _backend_status_bar_hint(self) -> str:
        """Return a user-facing workflow hint without requiring the AI dock."""
        if not application_runtime_initialized(self):
            return workflow_stage_hint("empty")
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None or result.failed:
            logger.debug("Failed to read backend status bar hint", exc_info=True)
            return "Workflow status unavailable"
        if result.diagnostics.get("view_stale") or not result.diagnostics.get(
            "view_verified",
            True,
        ):
            return "Workflow status unavailable · Try again"
        state = result.diagnostics.get("state", {})
        return workflow_stage_hint(state.get("pipeline_stage"))

    def _render_application_view_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Render committed workflow truth on the always-present desktop shell."""
        if not isinstance(publication, ApplicationViewPublication) or sip.isdeleted(
            self
        ):
            return False
        info_service = getattr(self, "info_service", None)
        render_info = getattr(info_service, "render_publication", None)
        if not callable(render_info) or render_info(publication) is not True:
            return False
        shell_rendered = self._show_application_publication_status(publication)
        if shell_rendered:
            self._last_rendered_application_publication = publication
        panels_rendered = all(
            self._panel_rendered_application_revision(index, publication.revision)
            for index in tuple(self._loaded_panel_indices)
        )
        fully_rendered = shell_rendered and panels_rendered
        if fully_rendered:
            self._last_fully_rendered_application_publication = publication
        return fully_rendered

    def _restore_application_publication_status(self) -> bool:
        """Restore the last shell-rendered revision after transient navigation UI."""
        publication = self._last_rendered_application_publication
        if publication is None:
            return False
        return self._show_application_publication_status(publication)

    def _show_application_publication_status(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Render one publication-derived workflow status without a state query."""
        status_bar = self.statusBar()
        if status_bar is None or sip.isdeleted(status_bar):
            return False
        transient_remaining_ms = transient_status_remaining_ms(status_bar)
        if transient_remaining_ms > 0:
            self._application_status_restore_timer.start(transient_remaining_ms + 1)
            status_bar.repaint()
            return True
        self._application_status_restore_timer.stop()
        message = self._application_publication_status_message(publication)
        status_bar.showMessage(message)
        status_bar.repaint()
        return status_bar.currentMessage() == message

    @staticmethod
    def _application_publication_status_message(
        publication: ApplicationViewPublication,
    ) -> str:
        """Project the highest-priority committed workflow state to the shell."""
        if not publication.usable:
            return "Workflow status unavailable · Try again"
        if (
            publication.state.training.terminal_outcome.state
            is TrainingOutcomeState.FAILED
        ):
            return "Training failed · Adjust settings"
        return workflow_stage_hint(publication.state.pipeline_stage)

    def _panel_rendered_application_revision(
        self,
        index: int,
        revision: int,
    ) -> bool:
        """Return whether one materialized workflow panel committed a revision."""
        if index < 0 or index >= len(_PANEL_SPECS):
            return False
        panel = getattr(self, _PANEL_SPECS[index].attr, None)
        if panel is None or isinstance(panel, _LazyPanelPlaceholder):
            return False
        if isinstance(panel, QObject) and sip.isdeleted(panel):
            return False
        ledger = getattr(panel, "_application_render_ledger", None)
        if not isinstance(ledger, ApplicationPublicationRenderLedger):
            return False
        return ledger.last_rendered_revision >= revision

    def init_panels(self):
        """Create the first panel now and defer hidden panels until first use."""
        for spec in _PANEL_SPECS:
            placeholder = _LazyPanelPlaceholder(spec.label, self)
            setattr(self, spec.attr, placeholder)
            self.stack.addWidget(placeholder)

        self.stack.setCurrentIndex(0)

    def _schedule_initial_panel_load(self) -> None:
        """Materialize the initial panel while the startup splash is still visible."""
        self._load_initial_panel_if_alive()

    def _load_initial_panel_if_alive(self) -> None:
        """Materialize the initial panel unless the window was already destroyed."""
        if sip.isdeleted(self):
            return
        if self.stack.currentIndex() == 0 and 0 not in self._loaded_panel_indices:
            self._ensure_panel_loaded(0)
            refresh_after_navigation(self, 0)

    def _ensure_panel_loaded(self, index: int) -> QWidget | None:
        """Instantiate a workflow panel on first navigation to that panel."""
        return self._materialize_panel(index)

    def _materialize_panel(
        self,
        index: int,
        *,
        panel_class: Any | None = None,
    ) -> QWidget | None:
        """Create one QWidget panel on the GUI thread after class preparation."""
        if index < 0 or index >= len(_PANEL_SPECS):
            return None

        application = QCoreApplication.instance()
        if application is not None and QThread.currentThread() != application.thread():
            raise RuntimeError("Workflow panels must be created on the GUI thread")

        spec = _PANEL_SPECS[index]
        existing = getattr(self, spec.attr, None)
        if index in self._loaded_panel_indices:
            return existing
        if existing is not None and not isinstance(existing, _LazyPanelPlaceholder):
            self._loaded_panel_indices.add(index)
            return existing
        if self.stack.count() <= index:
            return existing

        resolved_panel_class = panel_class or self._prepared_panel_classes.get(index)
        if resolved_panel_class is None:
            resolved_panel_class = _load_panel_class(spec.module, spec.class_name)
        if not callable(resolved_panel_class):
            raise TypeError(f"{spec.class_name} did not resolve to a panel class")
        if spec.attr in {"dataset_panel", "preprocess_panel"}:
            runtime = application_ui_runtime(self)
            panel = resolved_panel_class(
                parent=self,
                publication_port=runtime,
            )
        elif spec.attr == "training_panel":
            runtime = application_ui_runtime(self)
            panel = resolved_panel_class(
                parent=self,
                query_port=runtime,
                publication_port=runtime,
                action_port=runtime,
                transient_port=training_transient_ui_port(self),
            )
        elif spec.attr in {"evaluation_panel", "visualization_panel"}:
            runtime = application_ui_runtime(self)
            panel = resolved_panel_class(
                parent=self,
                query_port=runtime,
                publication_port=runtime,
                action_port=runtime,
            )
        else:
            raise RuntimeError(f"No typed product bootstrap for {spec.class_name}")
        if not isinstance(panel, QWidget):
            if isinstance(panel, QObject) and not sip.isdeleted(panel):
                qt_object = cast(QObject, panel)
                qt_object.setParent(None)
                sip.delete(qt_object)
            raise TypeError(f"{spec.class_name} did not create a QWidget")
        panel_widget = cast(QWidget, panel)

        old_widget = self.stack.widget(index)
        was_current = self.stack.currentIndex() == index
        try:
            if old_widget is not None:
                self.stack.removeWidget(old_widget)
                old_widget.setParent(None)
            self.stack.insertWidget(index, panel_widget)
            if was_current:
                self.stack.setCurrentIndex(index)
            setattr(self, spec.attr, panel_widget)
            self._loaded_panel_indices.add(index)
            self._prepared_panel_classes.pop(index, None)
            self._panel_materialization_pending.discard(index)
        except Exception:
            if self.stack.indexOf(panel_widget) >= 0:
                self.stack.removeWidget(panel_widget)
            panel_widget.setParent(None)
            panel_widget.deleteLater()
            if old_widget is not None and self.stack.indexOf(old_widget) < 0:
                self.stack.insertWidget(index, old_widget)
                if was_current:
                    self.stack.setCurrentIndex(index)
                setattr(self, spec.attr, old_widget)
            raise

        if old_widget is not None:
            old_widget.deleteLater()

        if spec.attr == "visualization_panel":
            self._connect_agent_visualization_monitor()
        return panel_widget

    def init_agent(self):
        """Initialize the AI agent system via AgentManager.

        Creates the ``AgentManager``, sets up its UI, and connects
        the debug tool execution signal.
        """
        if self.agent_manager is not None:
            return

        renderer = self._ensure_application_publication_renderer()
        if renderer is None:
            logger.error(
                "AI assistant initialization requires the desktop publication owner."
            )
            self.ai_btn.setChecked(False)
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "AI Assistant could not connect to the application. Try again.",
                    6000,
                )
            return

        agent_manager_class = _load_agent_manager_class()
        self.agent_manager = agent_manager_class(
            self,
            self.study,
            application_service=renderer.service,
        )
        try:
            self.agent_manager.init_ui()
        except Exception:
            failed_manager = self.agent_manager
            self.agent_manager = None
            logger.exception("AI assistant UI initialization failed")
            with contextlib.suppress(Exception):
                failed_manager.close()
            self.ai_btn.setChecked(False)
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "AI Assistant could not open. Try again.",
                    6000,
                )
            return

        # Connect Status Updates
        self.agent_manager.status_message_received.connect(
            self._on_agent_status_message,
        )
        self._bind_assistant_dock_presentation()
        self._connect_assistant_cleanup_signal()
        self._connect_agent_visualization_monitor()

    def _assistant_dock(self) -> QDockWidget | None:
        """Return the live Assistant dock when its UI has been constructed."""
        dock = getattr(self.agent_manager, "chat_dock", None)
        return dock if isinstance(dock, QDockWidget) else None

    def _bind_assistant_dock_presentation(self) -> None:
        """Keep dock sizing under the product shell's presentation policy."""
        dock = self._assistant_dock()
        if dock is None:
            return
        dock.installEventFilter(self)
        dock.visibilityChanged.connect(self._on_assistant_dock_visibility_changed)
        dock.topLevelChanged.connect(self._on_assistant_dock_top_level_changed)
        self._sync_assistant_central_width_floor()

    def eventFilter(self, watched, event):  # noqa: N802
        """Reapply dock policy after Qt or child layouts resize the Assistant."""
        dock = self._assistant_dock()
        if watched is dock and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
        ):
            self._schedule_assistant_dock_resize()
        return super().eventFilter(watched, event)

    def _on_assistant_dock_visibility_changed(self, visible: bool) -> None:
        """Restore the standard dock width after every open."""
        self._sync_assistant_central_width_floor()
        if visible:
            self._schedule_assistant_dock_resize()

    def _on_assistant_dock_top_level_changed(self, floating: bool) -> None:
        """Restore the docked width after a floating Assistant is reattached."""
        self._sync_assistant_central_width_floor()
        if not floating:
            self._schedule_assistant_dock_resize()

    def _sync_assistant_central_width_floor(self) -> None:
        """Protect workflow controls while the Assistant consumes shell width."""
        dock = self._assistant_dock()
        central = self.centralWidget()
        if dock is None or central is None:
            return
        target = (
            self.ASSISTANT_CENTRAL_WIDGET_MINIMUM_WIDTH
            if dock.isVisible() and not dock.isFloating()
            else 0
        )
        if central.minimumWidth() != target:
            central.setMinimumWidth(target)
            central.updateGeometry()

    def _schedule_assistant_dock_resize(self) -> None:
        """Apply dock geometry after Qt has settled the current shell layout."""
        if self._assistant_dock_resize_pending:
            return
        dock = self._assistant_dock()
        if dock is None or not dock.isVisible() or dock.isFloating():
            return
        self._assistant_dock_resize_pending = True
        QTimer.singleShot(0, self._apply_assistant_dock_width)

    def _apply_assistant_dock_width(self) -> None:
        """Use 420 px normally and shrink only to preserve workflow space."""
        self._assistant_dock_resize_pending = False
        dock = self._assistant_dock()
        if dock is None or not dock.isVisible() or dock.isFloating():
            return
        available_for_dock = (
            self.contentsRect().width() - self.ASSISTANT_DOCK_CENTRAL_MINIMUM_WIDTH
        )
        target_width = min(
            self.ASSISTANT_DOCK_STANDARD_WIDTH,
            max(self.ASSISTANT_DOCK_MINIMUM_WIDTH, available_for_dock),
        )
        # Make the responsive target authoritative over competing central-panel
        # size hints. Narrow shells lower this back to the supported 320 px floor.
        dock.setMinimumWidth(target_width)
        self.resizeDocks(
            [dock],
            [target_width],
            Qt.Orientation.Horizontal,
        )

    def _connect_agent_visualization_monitor(self) -> None:
        """Connect VRAM monitoring once both agent and visualization panel exist."""
        agent_manager = getattr(self, "agent_manager", None)
        if agent_manager is None:
            return
        connect = getattr(agent_manager, "connect_visualization_monitor", None)
        if callable(connect):
            connect()

    def _on_agent_status_message(self, msg: str):
        """Update status bar safely."""
        sb = self.statusBar()
        if sb:
            sb.showMessage(msg, 6000)

    def toggle_ai_dock(self):
        """Toggle the AI assistant dock widget visibility."""
        if self.agent_manager is None:
            self.init_agent()
        if self.agent_manager is None:
            return
        self.agent_manager.toggle()

    def _schedule_startup_prewarm(self) -> None:
        """Schedule safe background imports after the first UI frame."""
        if self._closing_in_progress or sip.isdeleted(self):
            return
        QTimer.singleShot(1400, self._start_startup_prewarm)

    def _start_startup_prewarm(self) -> None:
        """Start non-UI background import prewarm without blocking startup."""
        if (
            self._closing_in_progress
            or sip.isdeleted(self)
            or self._startup_prewarm_worker is not None
        ):
            return
        if self._panel_prepare_active_index is not None or self._panel_prepare_queue:
            if not self._startup_prewarm_retry_pending:
                self._startup_prewarm_retry_pending = True
                QTimer.singleShot(250, self._retry_startup_prewarm)
            return
        try:
            worker = Worker(_prewarm_startup_modules)
            worker.signals.result.connect(self._on_startup_prewarm_result)
            worker.signals.finished.connect(self._clear_startup_prewarm_worker)
            self._startup_prewarm_worker = worker
            thread_pool = _require_global_thread_pool()
            thread_pool.start(worker)
        except Exception as exc:
            self._startup_prewarm_worker = None
            logger.warning("Could not start background module prewarm: %s", exc)
            QTimer.singleShot(0, self._start_next_panel_prepare)

    def _retry_startup_prewarm(self) -> None:
        """Retry prewarm only after lazy panel imports release the Qt pool."""
        self._startup_prewarm_retry_pending = False
        if not self._closing_in_progress:
            self._start_startup_prewarm()

    def _on_startup_prewarm_result(self, result: dict[str, list[str]]) -> None:
        """Bind publication delivery after heavy imports leave the first paint."""
        loaded = result.get("loaded", [])
        failed = result.get("failed", [])
        logger.debug(
            "Startup prewarm finished: loaded=%s failed=%s",
            len(loaded),
            failed,
        )
        self._ensure_application_publication_renderer()

    def _ensure_application_publication_renderer(
        self,
    ) -> DesktopApplicationPublicationRenderer | None:
        """Create the canonical desktop publication owner on first backend use."""
        renderer = self._application_publication_renderer
        if renderer is not None:
            return renderer
        if (
            self._closing_in_progress
            or sip.isdeleted(self)
            or not has_real_application_context(self)
        ):
            return None
        from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
            get_application_service,
        )

        renderer = DesktopApplicationPublicationRenderer(
            service=get_application_service(self.study),
            render_publication=self._render_application_view_publication,
            parent=self,
        )
        self._application_publication_renderer = renderer
        self._defer_initial_application_runtime = False
        initial_publication = self._flush_deferred_application_subscriptions(
            renderer.service,
        )
        if initial_publication is not None:
            renderer.render_initial_publication(initial_publication)
        return renderer

    def _defer_application_runtime_subscription(
        self,
        event_name: str,
        callback: Callable[..., Any],
    ) -> bool:
        """Queue a panel subscription without constructing the command runtime."""
        if (
            not self._defer_initial_application_runtime
            or self._application_publication_renderer is not None
            or self._closing_in_progress
        ):
            return False
        subscription = (str(event_name), callback)
        if subscription not in self._deferred_application_subscriptions:
            self._deferred_application_subscriptions.append(subscription)
        return True

    def _cancel_deferred_application_runtime_subscription(
        self,
        event_name: str,
        callback: Callable[..., Any],
    ) -> bool:
        """Remove a bridge that was disposed before runtime initialization."""
        subscription = (str(event_name), callback)
        try:
            self._deferred_application_subscriptions.remove(subscription)
        except ValueError:
            return False
        return True

    def _flush_deferred_application_subscriptions(
        self,
        service: Any,
    ) -> ApplicationViewPublication | None:
        """Bind queued observers and replay the latest committed publication."""
        pending = tuple(self._deferred_application_subscriptions)
        self._deferred_application_subscriptions.clear()
        try:
            publication = service.get_view_publication()
        except Exception:
            logger.exception("Could not read the initial application publication.")
            self._deferred_application_subscriptions.extend(pending)
            return None
        for event_name, callback in pending:
            try:
                service.subscribe(event_name, callback)
            except Exception:
                logger.exception(
                    "Could not bind a deferred application publication observer.",
                )
                self._deferred_application_subscriptions.append(
                    (event_name, callback),
                )
                continue
            callback(publication)
        return publication

    def _clear_startup_prewarm_worker(self) -> None:
        """Release the worker reference after the background task completes."""
        self._startup_prewarm_worker = None
        QTimer.singleShot(0, self._start_next_panel_prepare)

    def update_info_panel(self):
        """Refresh the aggregate info panel if it exists."""
        info_service = getattr(self, "info_service", None)
        notify_all = getattr(info_service, "notify_all", None)
        if callable(notify_all):
            notify_all()
            return

        if hasattr(self, "info_panel"):
            self.info_panel.update_info()

    def showEvent(self, event):  # noqa: N802
        """Clamp restored geometry once the window has a native frame."""
        super().showEvent(event)
        self.window_geometry.handle_window_shown()

    def keyPressEvent(self, event):  # noqa: N802
        """Route the user-visible Alt+F4 shortcut through the safe close path."""
        if (
            event.key() == Qt.Key.Key_F4
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            event.accept()
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):  # noqa: N802
        """Handle application close by cleaning up the agent manager.

        Args:
            event: The QCloseEvent triggered on window close.

        """
        if sip.isdeleted(self):
            event.accept()
            return
        if self._force_shutdown_requested:
            if not self._closing_in_progress:
                self._begin_close_attempt()
            if not self._owned_ui_background_work_idle():
                self._pre_close_background_snapshot = None
                event.ignore()
                self._schedule_close_retry()
                status_bar = self.statusBar()
                if status_bar is not None:
                    status_bar.showMessage(
                        "Finishing background interface work before closing...",
                        3000,
                    )
                return
            if not self._capture_pre_close_background_snapshot():
                event.ignore()
                self._schedule_close_retry()
                return
            self._begin_desktop_render_shutdown()
            if not self._finalize_visualization_native_render_resources():
                event.ignore()
                self._schedule_close_retry()
                return
            if not self._finalize_preprocess_native_plots_for_shutdown():
                event.ignore()
                self._schedule_close_retry()
                return
            if not self._close_assistant_for_shutdown():
                self._handle_assistant_shutdown_failure(event)
                return
            if not self._finalize_application_publication_renderer_for_shutdown():
                event.ignore()
                self._schedule_close_retry()
                return
            if not close_application_runtime(self):
                event.ignore()
                self._schedule_close_retry()
                return
            self._publish_terminal_shutdown_snapshot()
            self._delegate_close_event_if_alive(event)
            return
        if not self._closing_in_progress:
            self._begin_close_attempt()
        if not self._ensure_shutdown_fence_for_close():
            event.ignore()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Preparing a safe shutdown. XBrainLab will close when it is safe.",
                    3000,
                )
            return
        if not self._stop_training_for_close():
            event.ignore()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Training is still stopping. XBrainLab will close when it is safe.",
                    3000,
                )
            return
        if not self._owned_ui_background_work_idle():
            self._pre_close_background_snapshot = None
            event.ignore()
            self._schedule_close_retry()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Finishing background interface work before closing...",
                    3000,
                )
            return
        if not self._capture_pre_close_background_snapshot():
            event.ignore()
            self._schedule_close_retry()
            return
        self._begin_desktop_render_shutdown()
        if not self._finalize_visualization_native_render_resources():
            event.ignore()
            self._schedule_close_retry()
            return
        if not self._finalize_preprocess_native_plots_for_shutdown():
            event.ignore()
            self._schedule_close_retry()
            return
        if not self._close_assistant_for_shutdown():
            self._handle_assistant_shutdown_failure(event)
            return
        if not self._finalize_application_publication_renderer_for_shutdown():
            event.ignore()
            self._schedule_close_retry()
            return
        if not close_application_runtime(self):
            event.ignore()
            self._schedule_close_retry()
            return
        self._publish_terminal_shutdown_snapshot()
        if not self.window_geometry.persist_before_close():
            event.accept()
            return
        self._delegate_close_event_if_alive(event)

    def _delegate_close_event_if_alive(self, event: Any) -> bool:
        """Finish Qt close without touching an already deleted C++ wrapper."""
        if sip.isdeleted(self):
            event.accept()
            return False
        try:
            super().closeEvent(event)
        except RuntimeError:
            if sip.isdeleted(self):
                event.accept()
                return False
            raise
        return True

    def _begin_close_attempt(self) -> None:
        """Freeze user actions while worker ownership is being released."""
        logger.info("Closing application...")
        if self._force_shutdown_requested:
            logger.critical("Forcing GUI shutdown after safe recovery failed.")
        self._closing_in_progress = True
        self._close_attempt_id = uuid4().hex
        self._pre_close_background_snapshot = None
        self._shutdown_terminal_snapshot_emitted = False
        self._startup_prewarm_retry_pending = False
        self._training_close_ready = False
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._assistant_shutdown_attempts = 0
        self._assistant_shutdown_pending_logged = False
        self._assistant_shutdown_slow_logged = False
        self._set_close_interaction_enabled(False)
        self._begin_training_resource_preview_shutdown()
        self._begin_evaluation_render_shutdown()
        self._begin_visualization_render_shutdown()

    def _begin_desktop_render_shutdown(self) -> None:
        """Quiesce visible native surfaces after final publications are delivered."""
        if self._desktop_render_shutdown_started:
            return
        self._desktop_render_shutdown_started = True
        self._pause_application_publication_renderer_for_shutdown()
        self._prepare_preprocess_native_plots_for_shutdown()
        self._begin_visualization_render_shutdown()

    def _pause_application_publication_renderer_for_shutdown(self) -> None:
        """Suspend visible delivery while materialized panels become quiescent."""
        renderer = self._application_publication_renderer
        pause = getattr(renderer, "pause_for_shutdown", None)
        if callable(pause):
            pause()

    def _finalize_application_publication_renderer_for_shutdown(self) -> bool:
        """Detach publication delivery before Qt destroys rendered surfaces."""
        renderer = self._application_publication_renderer
        if renderer is None:
            return True
        cleanup = getattr(renderer, "cleanup", None)
        try:
            if callable(cleanup):
                cleanup()
        except Exception:
            logger.exception("Could not finalize desktop publication delivery.")
            return False
        self._application_publication_renderer = None
        return True

    def _prepare_preprocess_native_plots_for_shutdown(self) -> None:
        """Quiesce deferred PyQtGraph paint work before window destruction."""
        panel = getattr(self, "preprocess_panel", None)
        preview = getattr(panel, "preview_widget", None)
        prepare = getattr(preview, "prepare_for_shutdown", None)
        if callable(prepare):
            prepare()

    def _finalize_preprocess_native_plots_for_shutdown(self) -> bool:
        """Close loaded PyQtGraph roots before Qt destroys their scene items."""
        panel = getattr(self, "preprocess_panel", None)
        preview = getattr(panel, "preview_widget", None)
        finalize = getattr(preview, "finalize_native_plot_shutdown", None)
        if not callable(finalize):
            return True
        try:
            return bool(finalize())
        except Exception:
            logger.exception("Could not finalize Preprocess native plot resources.")
            return False

    def _resume_preprocess_native_plots_after_cancelled_shutdown(self) -> None:
        """Reconnect Preprocess plot callbacks after a cancelled close."""
        panel = getattr(self, "preprocess_panel", None)
        preview = getattr(panel, "preview_widget", None)
        resume = getattr(preview, "resume_after_cancelled_shutdown", None)
        if callable(resume):
            resume()

    def _owned_ui_background_work_idle(self) -> bool:
        """Return whether every UI-owned background worker is terminal."""
        return bool(self.background_work_snapshot()["idle"])

    def _capture_pre_close_background_snapshot(self) -> bool:
        """Bind exact idle ownership evidence to the active close attempt."""
        attempt_id = self._close_attempt_id
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            self._pre_close_background_snapshot = None
            logger.error("Close ownership evidence lacks an active attempt identity.")
            return False
        snapshot = self.background_work_snapshot()
        workers = snapshot.get("remaining_workers")
        subprocesses = snapshot.get("remaining_subprocesses")
        verified = (
            snapshot.get("idle") is True
            and snapshot.get("application_idle") is True
            and isinstance(workers, int)
            and not isinstance(workers, bool)
            and workers == 0
            and isinstance(subprocesses, int)
            and not isinstance(subprocesses, bool)
            and subprocesses == 0
        )
        if not verified:
            self._pre_close_background_snapshot = None
            logger.error("Close ownership evidence was not exactly idle.")
            return False
        self._pre_close_background_snapshot = {
            "close_attempt_id": attempt_id,
            "pre_close_application_idle": True,
            "pre_close_remaining_workers": workers,
            "pre_close_remaining_subprocesses": subprocesses,
        }
        return True

    def _begin_evaluation_render_shutdown(self) -> None:
        """Cancel Evaluation render work early without blocking the GUI thread."""
        panel = getattr(self, "evaluation_panel", None)
        begin_shutdown = getattr(panel, "begin_evaluation_render_shutdown", None)
        if callable(begin_shutdown):
            begin_shutdown()

    def _begin_training_resource_preview_shutdown(self) -> None:
        """Fence Training resource previews without blocking the GUI thread."""
        panel = getattr(self, "training_panel", None)
        begin_shutdown = getattr(
            panel,
            "begin_training_resource_preview_shutdown",
            None,
        )
        if callable(begin_shutdown):
            begin_shutdown()

    def _training_resource_preview_background_work_snapshot(
        self,
    ) -> dict[str, int | bool]:
        """Read exact Training preview worker ownership from the loaded panel."""
        panel = getattr(self, "training_panel", None)
        get_snapshot = getattr(
            panel,
            "training_resource_preview_background_work_snapshot",
            None,
        )
        if not callable(get_snapshot):
            return {"idle": True, "remaining_workers": 0, "alive_workers": 0}
        try:
            snapshot = get_snapshot()
            if not isinstance(snapshot, Mapping):
                logger.error("Training preview worker snapshot is not a mapping.")
                return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
            remaining = snapshot.get("remaining_workers", 0)
            alive = snapshot.get("alive_workers", 0)
        except Exception:
            logger.exception("Could not verify Training resource preview cleanup.")
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        if (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or remaining < 0
            or isinstance(alive, bool)
            or not isinstance(alive, int)
            or alive < 0
        ):
            logger.error("Training preview worker snapshot contains invalid counts.")
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        return {
            "idle": remaining == 0,
            "remaining_workers": remaining,
            "alive_workers": alive,
        }

    def _evaluation_background_work_snapshot(self) -> dict[str, int | bool]:
        """Read exact Evaluation worker ownership from the loaded panel."""
        panel = getattr(self, "evaluation_panel", None)
        get_snapshot = getattr(panel, "evaluation_background_work_snapshot", None)
        if not callable(get_snapshot):
            return {"idle": True, "remaining_workers": 0, "alive_workers": 0}
        try:
            snapshot = get_snapshot()
            if not isinstance(snapshot, Mapping):
                logger.error("Evaluation worker snapshot is not a mapping.")
                return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
            remaining = snapshot.get("remaining_workers", 0)
            alive = snapshot.get("alive_workers", 0)
        except Exception:
            logger.exception("Could not verify Evaluation render cleanup.")
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        if (
            isinstance(remaining, bool)
            or not isinstance(remaining, int)
            or remaining < 0
            or isinstance(alive, bool)
            or not isinstance(alive, int)
            or alive < 0
        ):
            logger.error("Evaluation worker snapshot contains invalid counts.")
            return {"idle": False, "remaining_workers": 1, "alive_workers": 0}
        return {
            "idle": remaining == 0,
            "remaining_workers": remaining,
            "alive_workers": alive,
        }

    def background_work_snapshot(self) -> dict[str, int | bool]:
        """Expose non-blocking close ownership evidence to product diagnostics."""
        startup_workers = int(self._startup_prewarm_worker is not None)
        panel_workers = len(self._panel_prepare_workers) + int(
            self._panel_prepare_active_index is not None
        )
        command_workers = application_command_registry().active_count()
        visualization_idle = self._visualization_native_render_idle()
        evaluation_snapshot = self._evaluation_background_work_snapshot()
        evaluation_workers = int(evaluation_snapshot["remaining_workers"])
        preview_snapshot = self._training_resource_preview_background_work_snapshot()
        training_preview_workers = int(preview_snapshot["remaining_workers"])
        application_idle = application_background_tasks_idle(self, timeout=0.0)
        remaining_subprocesses = self._assistant_owned_subprocess_count()
        remaining_workers = (
            startup_workers
            + panel_workers
            + command_workers
            + int(not visualization_idle)
            + evaluation_workers
            + training_preview_workers
        )
        return {
            "idle": (
                remaining_workers == 0
                and remaining_subprocesses == 0
                and application_idle
            ),
            "application_idle": application_idle,
            "remaining_workers": remaining_workers,
            "evaluation_workers": evaluation_workers,
            "training_preview_workers": training_preview_workers,
            "remaining_subprocesses": remaining_subprocesses,
        }

    def workflow_state_snapshot(self) -> dict[str, Any]:
        """Return only fully rendered and backend-current workflow evidence."""
        publication = self._last_fully_rendered_application_publication
        if publication is None or not publication.usable:
            raise RuntimeError("A verified workflow publication is not visible.")
        runtime = application_ui_runtime(self)
        if runtime is None:
            raise RuntimeError("The workflow publication runtime is unavailable.")
        current = runtime.get_view_publication()
        if (
            not isinstance(current, ApplicationViewPublication)
            or not current.usable
            or current.generation != publication.generation
            or current.revision != publication.revision
        ):
            raise RuntimeError(
                "The visible workflow publication has not acknowledged current truth."
            )
        return {
            "generation": publication.generation,
            "revision": publication.revision,
            "state": publication.state.to_dict(),
        }

    def _publish_terminal_shutdown_snapshot(self) -> None:
        """Emit the verified pre-close evidence after runtime teardown."""
        if self._shutdown_terminal_snapshot_emitted:
            return
        attempt_id = self._close_attempt_id
        snapshot = self._pre_close_background_snapshot
        workers = (
            snapshot.get("pre_close_remaining_workers")
            if isinstance(snapshot, Mapping)
            else None
        )
        subprocesses = (
            snapshot.get("pre_close_remaining_subprocesses")
            if isinstance(snapshot, Mapping)
            else None
        )
        if (
            not isinstance(attempt_id, str)
            or not attempt_id.strip()
            or not isinstance(snapshot, Mapping)
            or snapshot.get("close_attempt_id") != attempt_id
            or snapshot.get("pre_close_application_idle") is not True
            or not isinstance(workers, int)
            or isinstance(workers, bool)
            or workers != 0
            or not isinstance(subprocesses, int)
            or isinstance(subprocesses, bool)
            or subprocesses != 0
        ):
            logger.error(
                "Refused to publish stale or incomplete pre-close ownership evidence."
            )
            return
        self._shutdown_terminal_snapshot_emitted = True
        self.shutdown_completed.emit({**snapshot, "application_closed": True})

    def _assistant_owned_subprocess_count(self) -> int:
        """Return exact known Assistant/model-download process ownership."""
        agent_manager = getattr(self, "agent_manager", None)
        if agent_manager is None:
            return 0
        declared_snapshot_getter = getattr(
            type(agent_manager),
            "background_work_snapshot",
            None,
        )
        snapshot_getter = getattr(agent_manager, "background_work_snapshot", None)
        if callable(declared_snapshot_getter) and callable(snapshot_getter):
            try:
                snapshot = snapshot_getter()
                count = (
                    snapshot.get("remaining_subprocesses", 0)
                    if isinstance(snapshot, Mapping)
                    else 1
                )
            except Exception:
                logger.exception("Could not verify Assistant subprocess ownership.")
                return 1
            if type(count) is int and count >= 0:
                return count
        runtime = getattr(agent_manager, "assistant_runtime", None)
        if runtime is None or not isinstance(
            getattr(type(runtime), "controller", None),
            property,
        ):
            return 0
        controller = getattr(runtime, "controller", None)
        worker = getattr(controller, "worker", None)
        engine = getattr(worker, "engine", None)
        engine_processes = int(bool(getattr(engine, "is_alive", False)))
        rag_lifecycle = getattr(controller, "_rag_lifecycle", None)
        has_active_process = getattr(rag_lifecycle, "has_active_process", None)
        rag_processes = int(
            bool(has_active_process) if isinstance(has_active_process, bool) else 0
        )
        return engine_processes + rag_processes

    def _begin_visualization_render_shutdown(self) -> None:
        """Ask the loaded Visualization panel to reject new native work."""
        panel = getattr(self, "visualization_panel", None)
        begin_shutdown = getattr(panel, "begin_native_render_shutdown", None)
        if callable(begin_shutdown):
            begin_shutdown()

    def _visualization_native_render_idle(self) -> bool:
        """Return true when loaded saliency views released terminal ownership."""
        panel = getattr(self, "visualization_panel", None)
        is_idle = getattr(panel, "native_render_work_idle", None)
        if not callable(is_idle):
            return True
        try:
            return bool(is_idle())
        except Exception:
            logger.exception("Could not verify Visualization native render cleanup.")
            return False

    def _finalize_visualization_native_render_resources(self) -> bool:
        """Finalize loaded saliency widgets after their workers are terminal."""
        panel = getattr(self, "visualization_panel", None)
        finalize = getattr(panel, "finalize_native_render_resources", None)
        if not callable(finalize):
            return True
        if QThread.currentThread() is not self.thread():
            logger.error(
                "Visualization native resources cannot be finalized off the GUI thread."
            )
            return False
        try:
            return bool(finalize())
        except Exception:
            logger.exception("Could not finalize Visualization native resources.")
            return False

    def _close_assistant_for_shutdown(self) -> bool:
        """Return true only after assistant-owned Qt resources have stopped."""
        agent_manager = self.agent_manager
        if agent_manager is None:
            self._assistant_shutdown_attempts = 0
            return True
        self._connect_assistant_cleanup_signal()
        try:
            stopped = bool(agent_manager.close())
        except Exception:
            stopped = False
            logger.exception("Assistant teardown failed during GUI shutdown")
        if stopped:
            self._assistant_shutdown_attempts = 0
            self._assistant_shutdown_pending_logged = False
            self._assistant_shutdown_slow_logged = False
            return True
        self._assistant_shutdown_attempts = min(
            self._assistant_shutdown_attempts + 1,
            ASSISTANT_SHUTDOWN_MAX_ATTEMPTS,
        )
        return False

    def _connect_assistant_cleanup_signal(self) -> bool:
        """Observe the runtime's terminal cleanup signal exactly once."""
        agent_manager = self.agent_manager
        self._connect_model_download_terminal_signal()
        runtime = getattr(agent_manager, "assistant_runtime", None)
        signal = getattr(runtime, "cleanup_finished", None)
        if signal is None or not callable(getattr(signal, "connect", None)):
            return False
        if runtime is self._assistant_cleanup_runtime:
            return True
        previous = self._assistant_cleanup_signal
        if previous is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                previous.disconnect(self._on_assistant_cleanup_finished)
        signal.connect(self._on_assistant_cleanup_finished)
        self._assistant_cleanup_signal = signal
        self._assistant_cleanup_runtime = runtime
        return True

    def _connect_model_download_terminal_signal(self) -> bool:
        """Resume close promptly when app-owned model download cleanup ends."""
        agent_manager = self.agent_manager
        lifecycle = getattr(agent_manager, "model_download_lifecycle", None)
        signal = getattr(lifecycle, "terminal", None)
        if signal is None or not callable(getattr(signal, "connect", None)):
            return False
        if lifecycle is self._model_download_lifecycle:
            return True
        previous = self._model_download_terminal_signal
        if previous is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                previous.disconnect(self._on_model_download_terminal)
        signal.connect(self._on_model_download_terminal)
        self._model_download_terminal_signal = signal
        self._model_download_lifecycle = lifecycle
        return True

    @pyqtSlot(bool, str)
    def _on_model_download_terminal(self, _ok: bool, _message: str) -> None:
        """Retry a fenced app close after subprocess and QThread terminal."""
        if sip.isdeleted(self) or not (
            self._closing_in_progress or self._force_shutdown_requested
        ):
            return
        self._schedule_close_retry(delay_ms=0)

    @pyqtSlot(bool, str)
    def _on_assistant_cleanup_finished(self, ok: bool, message: str) -> None:
        """Resume a fenced close only after assistant ownership is terminal."""
        if sip.isdeleted(self) or not (
            self._closing_in_progress or self._force_shutdown_requested
        ):
            return
        if not ok:
            detail = str(message or "Assistant cleanup did not finish.")
            logger.error("Assistant teardown completed with errors: %s", detail)
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Assistant shutdown needs another cleanup attempt.",
                )
            self._schedule_close_retry()
            return
        self._assistant_shutdown_attempts = 0
        self._schedule_close_retry(delay_ms=0)

    def _handle_assistant_shutdown_failure(self, event: Any) -> None:
        """Keep the window fenced until assistant-owned resources are released."""
        if sip.isdeleted(self):
            event.accept()
            return
        event.ignore()
        attempts = self._assistant_shutdown_attempts
        if attempts < ASSISTANT_SHUTDOWN_MAX_ATTEMPTS:
            if not self._assistant_shutdown_pending_logged:
                logger.info(
                    "Assistant teardown is pending; waiting for terminal cleanup."
                )
                self._assistant_shutdown_pending_logged = True
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Assistant is still stopping. "
                    "XBrainLab will close when it is safe.",
                )
            self._connect_assistant_cleanup_signal()
            self._schedule_close_retry()
            return

        if not self._assistant_shutdown_slow_logged:
            logger.warning(
                "Assistant teardown exceeded the %sms shutdown watchdog; "
                "continuing safe cleanup.",
                ASSISTANT_SHUTDOWN_MAX_WAIT_MS,
            )
            self._assistant_shutdown_slow_logged = True
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(
                "XBrainLab is in shutdown-only recovery while model and "
                "assistant resources are still owned.",
            )
        self._assistant_shutdown_attempts = ASSISTANT_SHUTDOWN_MAX_ATTEMPTS
        self._shutdown_only_mode = True
        self._set_close_interaction_enabled(False)
        self._connect_assistant_cleanup_signal()
        self._schedule_close_retry()

    def _cancel_close_attempt(self) -> None:
        """Release the backend fence before restoring user interaction."""
        if not self._shutdown_fence_active or not has_real_application_context(self):
            self._shutdown_fence_active = False
            self._restore_close_interaction()
            return
        try:
            released = release_application_shutdown_fence(self)
        except Exception as exc:
            logger.error("Could not release shutdown fence: %s", exc)
            self._schedule_shutdown_release_retry()
            return
        if not released:
            logger.error("Could not release shutdown fence.")
            self._schedule_shutdown_release_retry()
            return
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._shutdown_fence_active = False
        self._restore_close_interaction()

    def _schedule_shutdown_release_retry(self) -> None:
        """Retry a failed fence release without reopening unsafe command surfaces."""
        if self._shutdown_release_retry_pending or sip.isdeleted(self):
            return
        if self._shutdown_release_attempts >= SHUTDOWN_FENCE_RELEASE_MAX_ATTEMPTS:
            logger.critical(
                "Shutdown fence could not be released after %s attempts.",
                self._shutdown_release_attempts,
            )
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "XBrainLab could not resume normal operation safely. "
                    "Choose Retry or Close in the recovery dialog.",
                )
            self._enter_shutdown_only_mode()
            return
        self._shutdown_release_attempts += 1
        self._shutdown_release_retry_pending = True
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(
                "Restoring XBrainLab after the cancelled close attempt...",
            )
        QTimer.singleShot(
            SHUTDOWN_FENCE_RELEASE_RETRY_MS,
            self._retry_shutdown_fence_release,
        )

    def _retry_shutdown_fence_release(self) -> None:
        """Run one bounded release retry while the close fence stays active."""
        self._shutdown_release_retry_pending = False
        if not sip.isdeleted(self) and self._closing_in_progress:
            self._cancel_close_attempt()

    def _enter_shutdown_only_mode(self) -> None:
        """Offer an explicit exit when normal command admission cannot be restored."""
        if self._shutdown_only_mode or sip.isdeleted(self):
            return
        self._shutdown_only_mode = True
        reply = QMessageBox.question(
            self,
            "XBrainLab cannot resume safely",
            "The application could not restore its command state after the close "
            "attempt. Retry recovery, or close XBrainLab now. Unsaved work may be "
            "lost if you close.",
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Retry,
        )
        if reply == QMessageBox.StandardButton.Close:
            self._assistant_shutdown_attempts = 0
            self._force_shutdown_requested = True
            QTimer.singleShot(0, self.close)
            return
        self._shutdown_only_mode = False
        self._shutdown_release_attempts = 0
        self._schedule_shutdown_release_retry()

    def _restore_close_interaction(self) -> None:
        """Restore the desktop shell after a cancelled close attempt."""
        self._closing_in_progress = False
        self._close_attempt_id = None
        self._pre_close_background_snapshot = None
        self._shutdown_terminal_snapshot_emitted = False
        self._desktop_render_shutdown_started = False
        self._training_close_ready = False
        self._training_close_check_in_flight = False
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._shutdown_only_mode = False
        self._assistant_shutdown_attempts = 0
        panel = getattr(self, "visualization_panel", None)
        cancel_render_shutdown = getattr(
            panel,
            "cancel_native_render_shutdown",
            None,
        )
        if callable(cancel_render_shutdown):
            cancel_render_shutdown()
        evaluation_panel = getattr(self, "evaluation_panel", None)
        cancel_evaluation_shutdown = getattr(
            evaluation_panel,
            "cancel_evaluation_render_shutdown",
            None,
        )
        if callable(cancel_evaluation_shutdown):
            cancel_evaluation_shutdown()
        training_panel = getattr(self, "training_panel", None)
        cancel_preview_shutdown = getattr(
            training_panel,
            "cancel_training_resource_preview_shutdown",
            None,
        )
        if callable(cancel_preview_shutdown):
            cancel_preview_shutdown()
        self._resume_preprocess_native_plots_after_cancelled_shutdown()
        renderer = self._application_publication_renderer
        resume = getattr(renderer, "resume_after_cancelled_shutdown", None)
        if callable(resume):
            resume()
        self._set_close_interaction_enabled(True)

    def _set_close_interaction_enabled(self, enabled: bool) -> None:
        """Enable or disable every user command surface, including docks."""
        central_widget = self.centralWidget()
        if central_widget is not None:
            central_widget.setEnabled(enabled)
        for dock_widget in self.findChildren(QDockWidget):
            dock_widget.setEnabled(enabled)

    def _ensure_shutdown_fence_for_close(self) -> bool:
        """Install the backend command fence before stopping owned workers."""
        if self._shutdown_fence_active:
            return True
        if not has_real_application_context(self):
            return True
        if not application_runtime_initialized(self):
            return True
        try:
            installed = request_application_shutdown_fence(self)
        except Exception as exc:
            logger.warning("Could not enable shutdown fence: %s", exc)
            self._restore_close_interaction()
            return False
        self._shutdown_fence_active = bool(installed)
        if not installed:
            self._restore_close_interaction()
        return bool(installed)

    def _schedule_close_retry(
        self,
        *,
        delay_ms: int = ASSISTANT_SHUTDOWN_RETRY_INTERVAL_MS,
    ) -> None:
        """Coalesce close retries and always arm their timer on the GUI thread."""
        if self._close_retry_pending or sip.isdeleted(self):
            return
        self._close_retry_pending = True
        delay = max(0, int(delay_ms))
        if QThread.currentThread() is self.thread():
            self._arm_close_retry(delay)
            return
        self._close_retry_requested.emit(delay)

    @pyqtSlot(int)
    def _arm_close_retry(self, delay_ms: int) -> None:
        """Create the close timer only on the MainWindow's Qt event loop."""
        if sip.isdeleted(self):
            return
        QTimer.singleShot(max(0, int(delay_ms)), self._retry_close)

    def _retry_close(self) -> None:
        """Retry a deferred close only while this Qt window still exists."""
        self._close_retry_pending = False
        if not sip.isdeleted(self):
            self.close()

    def _stop_training_for_close(self) -> bool:
        """Start a non-blocking training stop check before window teardown."""
        if self._training_close_ready:
            if self._closing_in_progress:
                return True
            self._training_close_ready = False
        if self._training_close_check_in_flight:
            return False
        if not has_real_application_context(self):
            return True
        if not application_runtime_initialized(self):
            return True

        self._training_close_check_in_flight = True

        def _handle_result(result) -> None:
            self._training_close_check_in_flight = False
            if self._training_stop_result_allows_close(result):
                # The result callback runs before its own async command handle is
                # released. Waiting for application background idleness here can
                # therefore wait on the callback that is performing the check and
                # dispatch Stop Training forever. A terminal stop result is the
                # training-liveness gate; subsequent close stages independently
                # quiesce UI and native-render owners.
                self._training_close_ready = True
                self._schedule_close_retry()
                return
            if not result.failed and result.diagnostics.get("stopped") is False:
                self._schedule_close_retry()
                return
            logger.warning("Close-time training stop failed: %s", result.message)
            self._cancel_close_attempt()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Training status could not be verified. Close again to retry.",
                    5000,
                )

        def _handle_error(error: tuple) -> None:
            self._training_close_check_in_flight = False
            message = error[1] if len(error) > 1 else error
            logger.warning("Close-time training stop failed: %s", message)
            self._cancel_close_attempt()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Training status could not be verified. Close again to retry.",
                    5000,
                )

        started = execute_application_command_async(
            self,
            StopTrainingCommand(wait_timeout=0.0),
            on_result=_handle_result,
            on_error=_handle_error,
            refresh=False,
            allow_during_shutdown=True,
        )
        if started:
            return False
        self._cancel_close_attempt()
        logger.warning("Could not start close-time training status check.")
        return False

    @staticmethod
    def _training_stop_result_allows_close(result: Any) -> bool:
        """Trust only the command result's field-level training liveness state."""
        if not result.failed and result.diagnostics.get("stopped") is True:
            return True
        state = getattr(result, "state", None)
        active_training = getattr(state, "active_training", None)
        return bool(getattr(state, "training_liveness_reliable", False)) and not bool(
            getattr(active_training, "is_running", True)
        )


def global_exception_handler(exctype, value, tb):
    """Global exception handler that logs errors and displays an error dialog.

    Args:
        exctype: The exception class.
        value: The exception instance.
        tb: The traceback object.

    """
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tb)
        return
    app = QApplication.instance()
    if app is None:
        return
    present_unexpected_error(
        None,
        UnexpectedErrorContext.APPLICATION_UNEXPECTED,
        error_info=(exctype, value, tb),
    )


# Only set exception hook if not running under pytest

if "pytest" not in sys.modules:
    sys.excepthook = global_exception_handler
