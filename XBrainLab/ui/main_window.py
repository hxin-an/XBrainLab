"""Main application window module for XBrainLab.

Provides the top-level QMainWindow that manages navigation, panel switching,
AI assistant integration, and debug tool execution.
"""

import sys

from PyQt6 import sip
from PyQt6.QtCore import QRect, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger

# M3.1: Debug Executor
from XBrainLab.debug.tool_executor import ToolExecutor
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.info_panel_service import InfoPanelService

# LLMController, ChatPanel, PickMontageDialog moved to AgentManager
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel
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

        # M3.1: Tool Executor for Debug Mode
        self.debug_executor = ToolExecutor(self.study)

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
        self.info_service = InfoPanelService(self.study)

        # 3. Stacked Widget (Content Area)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Initialize Panels
        self.init_panels()

        # Initialize Agent System
        self.init_agent()

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
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)

        refresh_after_navigation(self, index)

    def init_panels(self):
        """Initializes and adds all main functional panels to the stacked widget.
        The order of addition corresponds to the index used in navigation.
        """
        # Get Controllers
        dataset_ctrl = self.study.get_controller("dataset")
        preprocess_ctrl = self.study.get_controller("preprocess")
        training_ctrl = self.study.get_controller("training")
        eval_ctrl = self.study.get_controller("evaluation")
        viz_ctrl = self.study.get_controller("visualization")

        # 0. Dataset
        self.dataset_panel = DatasetPanel(dataset_ctrl, self)
        self.stack.addWidget(self.dataset_panel)

        # 1. Preprocess
        self.preprocess_panel = PreprocessPanel(preprocess_ctrl, dataset_ctrl, self)
        self.stack.addWidget(self.preprocess_panel)

        # 2. Training
        self.training_panel = TrainingPanel(training_ctrl, dataset_ctrl, self)
        self.stack.addWidget(self.training_panel)

        # 3. Evaluation
        self.evaluation_panel = EvaluationPanel(eval_ctrl, training_ctrl, self)
        self.stack.addWidget(self.evaluation_panel)

        # 4. Visualization
        self.visualization_panel = VisualizationPanel(viz_ctrl, training_ctrl, self)
        self.stack.addWidget(self.visualization_panel)

    def init_agent(self):
        """Initialize the AI agent system via AgentManager.

        Creates the ``AgentManager``, sets up its UI, and connects
        the debug tool execution signal.
        """
        # Delegate to AgentManager
        self.agent_manager = AgentManager(self, self.study)
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
        result = self.debug_executor.execute(tool_name, params)

        # Feedback to Chat
        if self.agent_manager.chat_panel:
            # We use the legacy or proper method to append message
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
            if panel:
                self.agent_manager.switch_panel({"panel": panel, "view_mode": view})

    def toggle_ai_dock(self):
        """Toggle the AI assistant dock widget visibility."""
        self.agent_manager.toggle()

    def update_info_panel(self):
        """Refresh the aggregate info panel if it exists."""
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
        if hasattr(self, "agent_manager"):
            self.agent_manager.close()
        super().closeEvent(event)


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
