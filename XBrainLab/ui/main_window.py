"""Main application window module for XBrainLab.

Provides the top-level QMainWindow that manages navigation, panel switching,
AI assistant integration, and debug tool execution.
"""

import contextlib
import sys
import weakref
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QRect, QSettings, QSize, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
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

from XBrainLab.backend.application import (
    QueryStateCommand,
    StopTrainingCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    execute_application_shutdown_command,
    local_result_payload,
)
from XBrainLab.ui.controller_compatibility_bootstrap import (
    get_compatibility_workflow_controllers_for_panel_bootstrap,
)
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.refresh_coordinator import refresh_after_navigation
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.window_placement import (
    bounded_window_position,
    choose_screen_for_rect,
    default_window_size_for_available,
    frame_extents_for,
    is_window_geometry_usable,
    screen_geometry_for,
    startup_geometry_diagnostics_enabled,
    startup_screen_hint,
    usable_window_position_bounds,
    widget_geometry_diagnostic_line,
)

# Compatibility hooks for older tests and debug fixtures that patch these names
# directly. Runtime loading still happens through the lazy loader helpers below.
ToolExecutor = None
AgentManager = None
InfoPanelService = None
DatasetPanel = None
PreprocessPanel = None
TrainingPanel = None
EvaluationPanel = None
VisualizationPanel = None


@dataclass(frozen=True)
class _PanelSpec:
    attr: str
    label: str
    module: str
    class_name: str
    controller_names: tuple[str, ...]


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
    ),
    _PanelSpec(
        "evaluation_panel",
        "Evaluation",
        "XBrainLab.ui.panels.evaluation.panel",
        "EvaluationPanel",
        ("evaluation", "training"),
    ),
    _PanelSpec(
        "visualization_panel",
        "Visualization",
        "XBrainLab.ui.panels.visualization.panel",
        "VisualizationPanel",
        ("visualization", "training"),
    ),
)

_STARTUP_PREWARM_MODULES: tuple[str, ...] = (
    "XBrainLab.backend.application.service",
    "XBrainLab.backend.load_data.raw_data_loader",
)


def _load_panel_class(module_name: str, class_name: str) -> Any:
    """Load a workflow panel class only when the panel is first opened."""
    patched = globals().get(class_name)
    if patched is not None:
        return patched
    module = import_module(module_name)
    return getattr(module, class_name)


def _load_agent_manager_class():
    """Load the AI assistant stack only when the user opens it."""
    patched = globals().get("AgentManager")
    if patched is not None:
        return patched
    module = import_module("XBrainLab.ui.components.agent_manager")
    return module.AgentManager


def _load_tool_executor_class():
    """Load debug tool execution only when a debug request is emitted."""
    patched = globals().get("ToolExecutor")
    if patched is not None:
        return patched
    module = import_module("XBrainLab.debug.tool_executor")
    return module.ToolExecutor


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
            import_module(module_name)
        except Exception:  # noqa: PERF203
            logger.debug("Startup prewarm failed for %s", module_name, exc_info=True)
            failed.append(module_name)
        else:
            loaded.append(module_name)
    return {"loaded": loaded, "failed": failed}


class _LazyPanelPlaceholder(QWidget):
    """Lightweight stand-in for workflow panels that are not opened yet."""

    def __init__(self, panel_label: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"Loading {panel_label}...")
        label.setObjectName("LazyPanelPlaceholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail = QLabel("Please wait.")
        detail.setObjectName("LazyPanelPlaceholderDetail")
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(label)
        layout.addWidget(detail)
        layout.addStretch()


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
        debug_executor: ToolExecutor for offline debug-mode tool execution.
        info_service: InfoPanelService managing aggregate info panel updates.
        stack: QStackedWidget holding all main functional panels.
        nav_btns: List of navigation QPushButtons in the top bar.
        ai_btn: Toggle button for the AI assistant dock.
        agent_manager: AgentManager orchestrating AI agent lifecycle.

    """

    # Signals to control the worker
    sig_init_agent = pyqtSignal()
    sig_generate = pyqtSignal(str, str)
    DEFAULT_WINDOW_SIZE = QSize(1280, 800)
    MIN_WINDOW_SIZE = QSize(760, 520)
    WINDOW_EDGE_MARGIN = 24
    WINDOW_TOP_DRAG_MARGIN = 72
    WINDOW_BOTTOM_MARGIN = 48

    def __init__(self, study):
        """Initialize the main window.

        Args:
            study: The application Study instance providing controllers
                and shared state.

        """
        super().__init__()
        self.study = study
        self.setWindowTitle("XBrainLab")
        self.setMinimumSize(self.MIN_WINDOW_SIZE)
        self._post_show_geometry_recovery_scheduled = False
        self._restore_or_place_window()

        self.agent_initialized = False  # Flag for lazy loading
        self.agent_manager = None
        self.debug_executor = None
        self._workflow_controllers = None
        self._loaded_panel_indices: set[int] = set()
        self._startup_prewarm_worker = None

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
        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.setFixedHeight(50)
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(10, 0, 10, 0)
        self.top_bar_layout.setSpacing(10)

        # Navigation Buttons
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

    def _restore_or_place_window(self) -> None:
        """Restore healthy saved geometry or recover to a draggable placement."""
        settings = self._window_settings()
        saved_geometry = settings.value("main_window/geometry", None)
        self._log_startup_geometry_message(
            "restore start saved_geometry=%s",
            "yes" if saved_geometry is not None else "no",
        )
        restored = False
        if saved_geometry is not None:
            try:
                restored = bool(self.restoreGeometry(saved_geometry))
            except TypeError:
                logger.debug("Ignoring invalid saved main-window geometry")
        self._log_startup_geometry_message("restoreGeometry result=%s", restored)

        target_screen = self._target_screen_for_window()
        if restored and self._is_current_window_geometry_usable(target_screen):
            self._log_startup_geometry("main_window.after_restore_healthy")
            return

        if saved_geometry is not None:
            logger.info("Resetting unusable saved main-window geometry")
            settings.remove("main_window/geometry")
            self._log_startup_geometry_message("removed unusable saved geometry")

        self._place_maximized_fallback(target_screen)
        self._log_startup_geometry("main_window.after_maximized_fallback")

    def _place_default_window(self, screen=None) -> None:
        """Place a default-size window where the native title bar is reachable."""
        target_screen = screen or self._target_screen_for_window()
        self.resize(self._default_window_size_for_screen(target_screen))
        self._center_window_on_available_screen(target_screen)

    def _place_maximized_fallback(self, screen=None) -> None:
        """Place the window on a valid screen, then start maximized."""
        self.setWindowState(Qt.WindowState.WindowNoState)
        self._place_default_window(screen)
        self.setWindowState(Qt.WindowState.WindowMaximized)

    @staticmethod
    def _window_settings() -> QSettings:
        """Return persistent UI shell settings."""
        return QSettings("XBrainLab", "XBrainLab")

    def _default_window_size_for_screen(self, screen=None) -> QSize:
        """Scale the initial size down while leaving room to drag the title bar."""
        return default_window_size_for_available(
            self.DEFAULT_WINDOW_SIZE,
            self.MIN_WINDOW_SIZE,
            self._available_screen_geometry(screen),
            edge_margin=self.WINDOW_EDGE_MARGIN,
            top_drag_margin=self.WINDOW_TOP_DRAG_MARGIN,
            bottom_margin=self.WINDOW_BOTTOM_MARGIN,
        )

    def _available_screen_geometry(self, screen=None) -> QRect:
        """Return the usable geometry for a selected screen."""
        target_screen = screen or self._target_screen_for_window()
        return screen_geometry_for(target_screen, self.DEFAULT_WINDOW_SIZE).available

    def _screen_geometry(self, screen=None) -> QRect:
        """Return full screen geometry for frame-aware placement."""
        target_screen = screen or self._target_screen_for_window()
        return screen_geometry_for(target_screen, self.DEFAULT_WINDOW_SIZE).full

    def _target_screen_for_window(self):
        """Choose a target screen from frame/client geometry, startup hint, cursor."""
        candidate = self._window_rect_for_screen_choice()
        startup_hint = startup_screen_hint()
        if not self.isVisible() and self._is_unshown_default_rect(candidate):
            candidate = None
        return choose_screen_for_rect(candidate, preferred_screen=startup_hint)

    def _window_rect_for_screen_choice(self) -> QRect | None:
        """Return the best current rectangle for screen selection."""
        frame = self.frameGeometry()
        if frame.isValid():
            return frame
        current = self.geometry()
        if current.isValid():
            return current
        return None

    def _is_unshown_default_rect(self, candidate: QRect | None) -> bool:
        """Return whether a hidden widget rect is only Qt's default origin."""
        if candidate is None or not candidate.isValid():
            return False
        return candidate.x() == 0 and candidate.y() == 0

    def _center_window_on_available_screen(self, screen=None) -> None:
        """Center the current window rectangle on the available screen."""
        target_screen = screen or self._target_screen_for_window()
        available = self._available_screen_geometry(target_screen)
        screen_geometry = self._screen_geometry(target_screen)
        width = min(self.width(), available.width())
        height = min(self.height(), available.height())
        x = available.left() + max((available.width() - width) // 2, 0)
        y = available.top() + max((available.height() - height) // 2, 0)
        x, y = self._bounded_window_position(
            available,
            width,
            height,
            x,
            y,
            screen_geometry=screen_geometry,
        )
        self.setGeometry(QRect(x, y, width, height))

    def _clamp_window_to_available_screen(self) -> None:
        """Move/resize the window into the usable screen title-bar bounds."""
        if self.isMaximized() or self.isFullScreen():
            return

        target_screen = self._target_screen_for_window()
        available = self._available_screen_geometry(target_screen)
        screen_geometry = self._screen_geometry(target_screen)
        current = self.geometry()
        width = min(
            max(current.width(), self.MIN_WINDOW_SIZE.width()),
            available.width(),
        )
        height = min(
            max(current.height(), self.MIN_WINDOW_SIZE.height()),
            available.height(),
        )
        x, y = self._bounded_window_position(
            available,
            width,
            height,
            current.x(),
            current.y(),
            screen_geometry=screen_geometry,
        )
        self.setGeometry(QRect(x, y, width, height))

    def _is_current_window_geometry_usable(self, screen=None) -> bool:
        """Return whether current geometry is safe to restore or persist."""
        if self.isFullScreen():
            return False
        if self.isMaximized():
            return True

        target_screen = screen or self._target_screen_for_window()
        available = self._available_screen_geometry(target_screen)
        screen_geometry = self._screen_geometry(target_screen)
        current = self.geometry()
        frame = self.frameGeometry()
        return is_window_geometry_usable(
            current,
            available_geometry=available,
            screen_geometry=screen_geometry,
            frame_geometry=frame,
            min_size=self.MIN_WINDOW_SIZE,
            edge_margin=self.WINDOW_EDGE_MARGIN,
            top_drag_margin=self.WINDOW_TOP_DRAG_MARGIN,
            bottom_margin=self.WINDOW_BOTTOM_MARGIN,
        )

    def _bounded_window_position(
        self,
        available: QRect,
        width: int,
        height: int,
        preferred_x: int,
        preferred_y: int,
        *,
        screen_geometry: QRect | None = None,
    ) -> tuple[int, int]:
        """Clamp a window position while preserving drag-safe top margins."""
        frame_extents = frame_extents_for(self.geometry(), self.frameGeometry())
        return bounded_window_position(
            available,
            width,
            height,
            preferred_x,
            preferred_y,
            edge_margin=self.WINDOW_EDGE_MARGIN,
            top_drag_margin=self.WINDOW_TOP_DRAG_MARGIN,
            bottom_margin=self.WINDOW_BOTTOM_MARGIN,
            screen_geometry=screen_geometry,
            frame_extents=frame_extents,
        )

    def _usable_window_position_bounds(
        self,
        available: QRect,
        width: int,
        height: int,
        *,
        screen_geometry: QRect | None = None,
    ) -> tuple[int, int, int, int]:
        """Return screen bounds that leave room for native window dragging."""
        frame_extents = frame_extents_for(self.geometry(), self.frameGeometry())
        return usable_window_position_bounds(
            available,
            width,
            height,
            edge_margin=self.WINDOW_EDGE_MARGIN,
            top_drag_margin=self.WINDOW_TOP_DRAG_MARGIN,
            bottom_margin=self.WINDOW_BOTTOM_MARGIN,
            screen_geometry=screen_geometry,
            frame_extents=frame_extents,
        )

    def _log_startup_geometry(self, label: str) -> None:
        """Log current geometry only when startup diagnostics are enabled."""
        if startup_geometry_diagnostics_enabled():
            logger.info(widget_geometry_diagnostic_line(label, self))

    def _log_startup_geometry_message(self, message: str, *args: object) -> None:
        """Log a startup diagnostic message without affecting normal UI."""
        if startup_geometry_diagnostics_enabled():
            logger.info("startup geometry: " + message, *args)

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

        btn.clicked.connect(lambda: self.switch_page(index))

        self.top_bar_layout.addWidget(btn)
        self.nav_btns.append(btn)

        if index == 0:
            btn.setChecked(True)

    def switch_page(self, index):
        """Switch the active panel in the stacked widget.

        Updates button check states and delegates target-panel refresh to the
        UI refresh coordinator.

        Args:
            index: Zero-based index of the panel to display.

        """
        self._ensure_panel_loaded(index)
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)

        refresh_after_navigation(self, index)
        if self.agent_manager is None:
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(self._backend_status_bar_hint())

    def _backend_status_bar_hint(self) -> str:
        """Return a user-facing workflow hint without requiring the AI dock."""
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None or result.failed:
            logger.debug("Failed to read backend status bar hint", exc_info=True)
            return "Workflow status unavailable"
        state = result.diagnostics.get("state", {})
        active_training = state.get("active_training", {})
        active_dataset = state.get("active_dataset", {})
        evaluation = state.get("evaluation", {})
        if active_training.get("is_running"):
            return "Training in progress"
        if evaluation.get("finished_runs", 0) > 0:
            return "Training complete · Review results"
        if active_dataset.get("has_datasets"):
            return "Dataset ready · Train model"
        if active_dataset.get("has_epoch_data"):
            return "Epochs ready · Generate dataset"
        if active_dataset.get("has_preprocessed_data"):
            return "Preprocessed data ready · Create epochs"
        if active_dataset.get("has_raw_data"):
            return "EEG data loaded · Preprocess data"
        return "No EEG data open · Scan a data source to begin"

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
        if index < 0 or index >= len(_PANEL_SPECS):
            return None

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

        panel_class = _load_panel_class(spec.module, spec.class_name)
        controller_args = [getattr(controllers, name) for name in spec.controller_names]
        panel = panel_class(*controller_args, self)

        old_widget = self.stack.widget(index)
        was_current = self.stack.currentIndex() == index
        if old_widget is not None:
            self.stack.removeWidget(old_widget)
            old_widget.setParent(None)
        self.stack.insertWidget(index, panel)
        if was_current:
            self.stack.setCurrentIndex(index)
        setattr(self, spec.attr, panel)
        self._loaded_panel_indices.add(index)

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
        self.agent_manager.init_ui()

        # M3.1: Debug tool execution handled by MainWindow for offline support
        if self.agent_manager.chat_panel:
            self.agent_manager.chat_panel.debug_tool_requested.connect(
                self._on_debug_tool_requested,
            )

        # Connect Status Updates
        self.agent_manager.status_message_received.connect(
            self._on_agent_status_message,
        )
        self._connect_agent_visualization_monitor()

    def _connect_agent_visualization_monitor(self) -> None:
        """Connect VRAM monitoring once both agent and visualization panel exist."""
        agent_manager = getattr(self, "agent_manager", None)
        if agent_manager is None:
            return
        connect = getattr(agent_manager, "connect_visualization_monitor", None)
        if callable(connect):
            connect()

    def _debug_executor_for_request(self):
        """Create the debug executor only when a debug request is made."""
        if self.debug_executor is None:
            tool_executor_class = _load_tool_executor_class()
            self.debug_executor = tool_executor_class(self.study)
        return self.debug_executor

    def _on_agent_status_message(self, msg: str):
        """Update status bar safely."""
        sb = self.statusBar()
        if sb:
            sb.showMessage(msg)

    def _on_debug_tool_requested(self, tool_name: str, params: dict):
        """Handle debug tool execution request (M3.1).

        Executes the requested tool via ``debug_executor`` and posts the
        result back to the chat panel. Also handles ``switch_panel``
        commands that would normally be parsed by the LLM controller.

        Args:
            tool_name: Name of the tool to execute.
            params: Dictionary of parameters to pass to the tool.

        """
        logger.info("Debug Mode: Requesting %s", tool_name)
        result = self._debug_executor_for_request().execute(tool_name, params)

        # Feedback to Chat
        if self.agent_manager and self.agent_manager.chat_panel:
            # We use the compatibility or proper method to append message
            # Ideally via chat_controller but for Direct UI debug feedback:
            self.agent_manager.chat_panel.append_message(
                "System",
                "Diagnostic action completed. Details were saved to logs.",
            )
            # Ensure we scroll to bottom
            self.agent_manager.chat_panel._scroll_to_bottom()

        # M3.1 FIX: Handle Switch Panel in Debug Mode
        # In normal agent flow, LLMController parses the "Request:" string.
        # In Debug Mode, we must handle it explicitly here.
        if tool_name == "switch_panel" and result and "Request: Switch UI" in result:
            # Map 'panel_name' (Tool param) to 'panel' (AgentManager param)
            panel = params.get("panel_name")
            view = params.get("view_mode")
            if panel and self.agent_manager:
                self.agent_manager.switch_panel({"panel": panel, "view_mode": view})

    def toggle_ai_dock(self):
        """Toggle the AI assistant dock widget visibility."""
        if self.agent_manager is None:
            self.init_agent()
        if self.agent_manager is None:
            return
        self.agent_manager.toggle()

    def _schedule_startup_prewarm(self) -> None:
        """Schedule safe background imports after the first UI frame."""
        QTimer.singleShot(1400, self._start_startup_prewarm)

    def _start_startup_prewarm(self) -> None:
        """Start non-UI background import prewarm without blocking startup."""
        if self._startup_prewarm_worker is not None:
            return
        worker = Worker(_prewarm_startup_modules)
        worker.signals.result.connect(self._on_startup_prewarm_result)
        worker.signals.finished.connect(self._clear_startup_prewarm_worker)
        self._startup_prewarm_worker = worker
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is not None:
            thread_pool.start(worker)

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
        if not self._post_show_geometry_recovery_scheduled:
            self._post_show_geometry_recovery_scheduled = True
            self._log_startup_geometry("main_window.show_event")
            QTimer.singleShot(
                0,
                lambda: self._recover_unusable_window_geometry_if_alive(
                    "post_show_0ms"
                ),
            )
            QTimer.singleShot(
                250,
                lambda: self._recover_unusable_window_geometry_if_alive(
                    "post_show_250ms"
                ),
            )

    def _recover_unusable_window_geometry_if_alive(self, recovery_label: str) -> None:
        """Run delayed recovery only while the underlying Qt window still exists."""
        if sip.isdeleted(self):
            return
        self._recover_unusable_window_geometry(recovery_label)

    def _recover_unusable_window_geometry(
        self,
        recovery_label: str = "post_show",
    ) -> None:
        """Recenter after show if the window manager produced bad geometry."""
        self._log_startup_geometry(f"main_window.{recovery_label}.before")
        if self._is_current_window_geometry_usable():
            self._log_startup_geometry_message("%s usable=True", recovery_label)
            return
        logger.info(
            "Recovering unusable main-window geometry after show (%s)",
            recovery_label,
        )
        self._place_maximized_fallback()
        self._log_startup_geometry(f"main_window.{recovery_label}.after")

    def closeEvent(self, event):  # noqa: N802
        """Handle application close by cleaning up the agent manager.

        Args:
            event: The QCloseEvent triggered on window close.

        """
        logger.info("Closing application...")
        self._stop_training_for_close()
        if not self.isMaximized() and not self.isFullScreen():
            settings = self._window_settings()
            if self._is_current_window_geometry_usable():
                settings.setValue(
                    "main_window/geometry",
                    self.saveGeometry(),
                )
            else:
                logger.info("Discarding unusable main-window geometry on close")
                settings.remove("main_window/geometry")
        if self.agent_manager is not None and not self.agent_manager.close():
            event.ignore()
            status_bar = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(
                    "Assistant is still stopping. "
                    "XBrainLab will close when it is safe.",
                    3000,
                )
            QTimer.singleShot(250, self.close)
            return
        super().closeEvent(event)

    def _stop_training_for_close(self) -> None:
        """Request bounded training shutdown before the window disappears."""
        result = execute_application_shutdown_command(
            self,
            StopTrainingCommand(wait_timeout=2.0),
        )
        if result is None:
            return
        if result.failed:
            logger.debug("Close-time training stop skipped: %s", result.message)
            return
        stopped = result.diagnostics.get("stopped")
        if stopped is False:
            logger.warning(
                "Training is still stopping after main-window close timeout.",
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
    logger.error("Uncaught exception", exc_info=(exctype, value, tb))
    app = QApplication.instance()
    if app is None:
        return
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("An unexpected error occurred.")
    msg.setInformativeText(str(value))
    msg.setWindowTitle("Error")
    msg.exec()


# Only set exception hook if not running under pytest

if "pytest" not in sys.modules:
    sys.excepthook = global_exception_handler
