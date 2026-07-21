"""Main application window module for XBrainLab.

Provides the top-level QMainWindow that manages navigation, panel switching,
and AI assistant integration.
"""

import contextlib
import sys
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from threading import RLock
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import QueryStateCommand, StopTrainingCommand
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    application_background_tasks_idle,
    application_runtime_initialized,
    execute_application_command,
    execute_application_command_async,
    has_real_application_context,
    local_result_payload,
    release_application_shutdown_fence,
    request_application_shutdown_fence,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.controller_compatibility_bootstrap import (
    get_compatibility_workflow_controllers_for_panel_bootstrap,
)
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.panel_navigation import PanelPreparationFailure
from XBrainLab.ui.product_language import workflow_stage_hint
from XBrainLab.ui.refresh_coordinator import refresh_after_navigation
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
        ("dataset",),
    ),
    _PanelSpec(
        "preprocess_panel",
        "Preprocess",
        "XBrainLab.ui.panels.preprocess.panel",
        "PreprocessPanel",
        ("preprocess", "dataset"),
    ),
    _PanelSpec(
        "training_panel",
        "Training",
        "XBrainLab.ui.panels.training.panel",
        "TrainingPanel",
        ("training", "dataset"),
        background_import_safe=False,
    ),
    _PanelSpec(
        "evaluation_panel",
        "Evaluation",
        "XBrainLab.ui.panels.evaluation.panel",
        "EvaluationPanel",
        ("evaluation", "training"),
        background_import_safe=False,
    ),
    _PanelSpec(
        "visualization_panel",
        "Visualization",
        "XBrainLab.ui.panels.visualization.panel",
        "VisualizationPanel",
        ("visualization", "training"),
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


def _load_info_panel_service_class():
    """Load the full aggregate info service only after the UI is visible."""
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


class _StartupInfoPanelService:
    """Lightweight proxy that defers full info-service imports until needed."""

    def __init__(
        self,
        study,
        *,
        observe_controller_events: bool = True,
    ) -> None:
        self.study = study
        self._observes_controller_events = observe_controller_events
        self._listeners: weakref.WeakSet = weakref.WeakSet()
        self._real_service = None

    def _service(self):
        if self._real_service is None:
            service_class = _load_info_panel_service_class()
            self._real_service = service_class(
                self.study,
                observe_controller_events=self._observes_controller_events,
            )
            for panel in list(self._listeners):
                self._real_service.register(panel)
        return self._real_service

    def register(self, panel) -> None:
        self._listeners.add(panel)
        if self._real_service is not None:
            self._real_service.register(panel)
            return
        panel.update_info(loaded_data_list=[], preprocessed_data_list=[])

    def unregister(self, panel) -> None:
        self._listeners.discard(panel)
        if self._real_service is not None:
            self._real_service.unregister(panel)

    def notify_all(self, *args, **kwargs) -> None:
        if self._real_service is not None:
            self._real_service.notify_all(*args, **kwargs)
            return
        loaded, preprocessed = self._query_data_lists()
        for panel in list(self._listeners):
            with contextlib.suppress(RuntimeError):
                panel.update_info(
                    loaded_data_list=loaded,
                    preprocessed_data_list=preprocessed,
                )

    def update_single(self, panel) -> None:
        if self._real_service is not None:
            self._real_service.update_single(panel)
            return
        loaded, preprocessed = self._query_data_lists()
        panel.update_info(loaded_data_list=loaded, preprocessed_data_list=preprocessed)

    def _query_data_lists(self) -> tuple[list[Any], list[Any]]:
        if not application_runtime_initialized(self):
            return [], []
        try:
            from XBrainLab.backend.application.commands import (  # noqa: PLC0415
                QueryStateCommand,
            )
            from XBrainLab.ui.application_capabilities import (  # noqa: PLC0415
                execute_application_command,
            )

            result = execute_application_command(
                self,
                QueryStateCommand(query="data_lists", include_objects=True),
                refresh=False,
            )
        except Exception:
            logger.debug("Startup info state query failed", exc_info=True)
            return [], []
        if result is None or result.failed:
            return [], []
        payload = local_result_payload(result)
        return (
            list(payload.get("loaded_data_list", [])),
            list(payload.get("preprocessed_data_list", [])),
        )


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
    COMPACT_NAV_BREAKPOINT = 720

    def __init__(self, study):
        """Initialize the main window.

        Args:
            study: The application Study instance providing controllers
                and shared state.

        """
        super().__init__()
        self.study = study
        self.setWindowTitle("XBrainLab")
        self.window_geometry = WindowGeometryLifecycle(self)
        self.window_geometry.restore_initial_geometry()

        self.agent_initialized = False  # Flag for lazy loading
        self.agent_manager = None
        self._workflow_controllers = None
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
        self._shutdown_fence_active = False
        self._training_close_check_in_flight = False
        self._training_close_ready = False
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._shutdown_only_mode = False
        self._force_shutdown_requested = False
        self._assistant_shutdown_attempts = 0
        self._assistant_cleanup_signal = None
        self._assistant_cleanup_runtime = None
        self._model_download_terminal_signal = None
        self._model_download_lifecycle = None
        self._defer_initial_application_runtime = True
        self._startup_prewarm_retry_pending = False

        # Apply VS Code Dark Theme (Adjusted for Top Bar)
        self.apply_vscode_theme()

        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

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

        self.top_bar_layout.addStretch()

        # AI Toggle Button
        self.ai_btn = QPushButton("AI Assistant")
        self.ai_btn.setCheckable(True)
        self.ai_btn.setChecked(False)  # Default Off
        self.ai_btn.clicked.connect(self.toggle_ai_dock)
        self.ai_btn.setObjectName("ActionBtn")
        self.top_bar_layout.addWidget(self.ai_btn)

        main_layout.addWidget(self.top_bar)
        QTimer.singleShot(0, self._update_navigation_layout)

        # 2. Services (Must be before panels to allow registration)
        self.info_service = _StartupInfoPanelService(
            self.study,
            observe_controller_events=False,
        )

        # 3. Stacked Widget (Content Area)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

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

    def _update_navigation_layout(self) -> None:
        """Keep every workflow destination readable in the available top bar."""
        if not hasattr(self, "compact_nav_combo"):
            return
        compact = self.top_bar.contentsRect().width() < self.COMPACT_NAV_BREAKPOINT
        self.compact_nav_combo.setVisible(compact)
        for button in self.nav_btns:
            button.setVisible(not compact)

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
        if self.agent_manager is None:
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

    def init_panels(self):
        """Create the first panel now and defer hidden panels until first use."""
        self._workflow_controllers = (
            get_compatibility_workflow_controllers_for_panel_bootstrap(self.study)
        )

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

        controllers = self._workflow_controllers
        if controllers is None:
            controllers = get_compatibility_workflow_controllers_for_panel_bootstrap(
                self.study,
            )
            self._workflow_controllers = controllers

        resolved_panel_class = panel_class or self._prepared_panel_classes.get(index)
        if resolved_panel_class is None:
            resolved_panel_class = _load_panel_class(spec.module, spec.class_name)
        if not callable(resolved_panel_class):
            raise TypeError(f"{spec.class_name} did not resolve to a panel class")
        controller_args = [getattr(controllers, name) for name in spec.controller_names]
        panel = resolved_panel_class(*controller_args, self)
        if not isinstance(panel, QWidget):
            if isinstance(panel, QObject):
                panel.setParent(None)
                panel.deleteLater()
            raise TypeError(f"{spec.class_name} did not create a QWidget")

        old_widget = self.stack.widget(index)
        was_current = self.stack.currentIndex() == index
        try:
            if old_widget is not None:
                self.stack.removeWidget(old_widget)
                old_widget.setParent(None)
            self.stack.insertWidget(index, panel)
            if was_current:
                self.stack.setCurrentIndex(index)
            setattr(self, spec.attr, panel)
            self._loaded_panel_indices.add(index)
            self._prepared_panel_classes.pop(index, None)
            self._panel_materialization_pending.discard(index)
        except Exception:
            if self.stack.indexOf(panel) >= 0:
                self.stack.removeWidget(panel)
            panel.setParent(None)
            panel.deleteLater()
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
        return panel

    def init_agent(self):
        """Initialize the AI agent system via AgentManager.

        Creates the ``AgentManager``, sets up its UI, and connects
        the debug tool execution signal.
        """
        if self.agent_manager is not None:
            return

        agent_manager_class = _load_agent_manager_class()
        self.agent_manager = agent_manager_class(self, self.study)
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
        self._connect_assistant_cleanup_signal()
        self._connect_agent_visualization_monitor()

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
        """Log prewarm outcome for profiling without surfacing UI noise."""
        loaded = result.get("loaded", [])
        failed = result.get("failed", [])
        logger.debug(
            "Startup prewarm finished: loaded=%s failed=%s",
            len(loaded),
            failed,
        )

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

    def closeEvent(self, event):  # noqa: N802
        """Handle application close by cleaning up the agent manager.

        Args:
            event: The QCloseEvent triggered on window close.

        """
        if sip.isdeleted(self):
            event.accept()
            return
        logger.info("Closing application...")
        if self._force_shutdown_requested:
            if not self._closing_in_progress:
                self._begin_close_attempt()
            if not self._owned_ui_background_work_idle():
                event.ignore()
                self._schedule_close_retry()
                status_bar = self.statusBar()
                if status_bar is not None:
                    status_bar.showMessage(
                        "Finishing background interface work before closing...",
                        3000,
                    )
                return
            if not self._finalize_visualization_native_render_resources():
                event.ignore()
                self._schedule_close_retry()
                return
            logger.critical("Forcing GUI shutdown after safe recovery failed.")
            if not self._close_assistant_for_shutdown():
                self._handle_assistant_shutdown_failure(event)
                return
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
            event.ignore()
            self._schedule_close_retry()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Finishing background interface work before closing...",
                    3000,
                )
            return
        if not self._finalize_visualization_native_render_resources():
            event.ignore()
            self._schedule_close_retry()
            return
        if not self._close_assistant_for_shutdown():
            self._handle_assistant_shutdown_failure(event)
            return
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
        self._closing_in_progress = True
        self._startup_prewarm_retry_pending = False
        self._training_close_ready = False
        self._shutdown_release_retry_pending = False
        self._shutdown_release_attempts = 0
        self._assistant_shutdown_attempts = 0
        self._set_close_interaction_enabled(False)
        self._prepare_preprocess_native_plots_for_shutdown()
        self._begin_visualization_render_shutdown()

    def _prepare_preprocess_native_plots_for_shutdown(self) -> None:
        """Quiesce deferred PyQtGraph paint work before window destruction."""
        panel = getattr(self, "preprocess_panel", None)
        preview = getattr(panel, "preview_widget", None)
        prepare = getattr(preview, "prepare_for_shutdown", None)
        if callable(prepare):
            prepare()

    def _owned_ui_background_work_idle(self) -> bool:
        """Return whether every UI-owned background worker is terminal."""
        return (
            self._startup_prewarm_worker is None
            and not self._panel_prepare_workers
            and self._panel_prepare_active_index is None
            and self._visualization_native_render_idle()
        )

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
            logger.warning(
                "Assistant teardown incomplete; scheduling retry %s of %s.",
                attempts + 1,
                ASSISTANT_SHUTDOWN_MAX_ATTEMPTS,
            )
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Assistant is still stopping. "
                    "XBrainLab will close when it is safe.",
                )
            self._connect_assistant_cleanup_signal()
            self._schedule_close_retry()
            return

        logger.warning(
            "Assistant teardown is taking longer than %s attempts; continuing "
            "safe shutdown retries.",
            attempts,
        )
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
            self._shutdown_fence_active = True
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
        """Coalesce close retries while training or assistant workers stop."""
        if self._close_retry_pending:
            return
        self._close_retry_pending = True
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

        self._training_close_check_in_flight = True

        def _handle_result(result) -> None:
            self._training_close_check_in_flight = False
            if self._training_stop_result_allows_close(result):
                self._training_close_ready = application_background_tasks_idle(
                    self,
                    timeout=0.0,
                )
                if not self._training_close_ready:
                    status_bar = self.statusBar()
                    if status_bar is not None:
                        status_bar.showMessage(
                            "Finishing background analysis before closing...",
                        )
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
