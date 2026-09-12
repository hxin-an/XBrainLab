"""Concrete Qt presentation for the fixed-right Assistant dock."""

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QWidget,
)

from XBrainLab.config import AppConfig
from XBrainLab.ui.styles.stylesheets import Stylesheets

from .panel import ChatPanel


class AssistantDockTitleBar(QWidget):
    """Product header for the fixed-right assistant dock."""

    MINIMUM_DOCK_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title_label: QLabel | None = None
        self.status_indicator: QWidget | None = None
        self.status_dot: QFrame | None = None
        self.status_badge: QLabel | None = None

    def set_assistant_status(self, text: str) -> None:
        """Expose runtime status without adding a competing header badge."""
        normalized = " ".join(str(text or "Local · Setup").split())
        state_text = normalized.rsplit("·", 1)[-1].strip() or "Setup"
        state = state_text.lower()
        self.setProperty("assistantState", state)
        self.setToolTip(normalized)
        self.setAccessibleDescription(f"Assistant status: {normalized}")
        if self.title_label is not None:
            self.title_label.setToolTip(normalized)
            self.title_label.setAccessibleDescription(f"Assistant status: {normalized}")

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Do not let platform font hints widen the dock past its product floor."""
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self.MINIMUM_DOCK_WIDTH), hint.height())

    def resizeEvent(self, event):  # noqa: N802
        """Keep essential title actions readable at narrow dock widths."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._finalize_title_layout)

    def showEvent(self, event):  # noqa: N802
        """Settle action geometry after the dock installs its title bar."""
        super().showEvent(event)
        QTimer.singleShot(0, self._finalize_title_layout)

    def _finalize_title_layout(self) -> None:
        """Reflow once after Qt applies the parent dock geometry."""
        layout = self.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()
        self.updateGeometry()


class AssistantDockView(QDockWidget):
    """Own the Assistant dock's concrete Qt widgets and fixed topology.

    This view deliberately owns no runtime, workflow, confirmation, or transcript
    policy.  Its signals report direct title-bar requests to the composing host.
    """

    new_conversation_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__("XBrainLab", parent)
        chat_panel = ChatPanel()
        self.chat_panel = chat_panel
        self.title_bar: AssistantDockTitleBar | None = None
        self.new_conversation_button: QPushButton | None = None
        self.settings_button: QPushButton | None = None
        self.close_button: QPushButton | None = None

        self.setWidget(chat_panel)
        # QDockWidget's native frame consumes platform-dependent horizontal
        # chrome. Keep the supported 320 px floor on the actual assistant
        # surface so Windows does not receive a narrower first layout.
        chat_panel.setMinimumWidth(320)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def install_title_bar(self) -> None:
        """Install title presentation after the host has replayed runtime state."""
        title_bar = AssistantDockTitleBar(self)
        self.title_bar = title_bar
        title_bar.setStyleSheet(Stylesheets.AGENT_TITLE_BAR)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 6, 6, 6)
        title_layout.setSpacing(6)

        title_label = QLabel("XBrainLab Assistant")
        title_label.setObjectName("AssistantDockTitle")
        title_label.setStyleSheet(Stylesheets.AGENT_TITLE_LABEL)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_label.setMinimumWidth(title_label.sizeHint().width())
        title_bar.title_label = title_label
        title_layout.addWidget(title_label)
        title_bar.set_assistant_status(self.chat_panel.header_status_text)
        title_layout.addStretch()
        self.chat_panel.header_status_changed.connect(title_bar.set_assistant_status)

        title_style = title_bar.style()
        if title_style is None:
            title_style = QApplication.style()
        if title_style is None:
            raise RuntimeError("Qt application style is unavailable.")

        # New chat clears only the assistant conversation, never workflow state.
        new_conversation_button = QPushButton("+")
        self.new_conversation_button = new_conversation_button
        new_conversation_button.setAutoDefault(False)
        new_conversation_button.setDefault(False)
        new_conversation_button.setIconSize(QSize(16, 16))
        new_conversation_button.setFixedSize(30, 30)
        new_conversation_button.setToolTip("New chat")
        new_conversation_button.setAccessibleName("New chat")
        new_conversation_button.setAccessibleDescription(
            "Clear the assistant conversation without changing the EEG workflow."
        )
        new_conversation_button.setStyleSheet(Stylesheets.AGENT_NEW_CONV_BTN)
        new_conversation_button.clicked.connect(
            lambda _checked=False: self.new_conversation_requested.emit()
        )
        title_layout.addWidget(new_conversation_button)

        # Settings is a direct action; dock controls have their own buttons.
        settings_button = QPushButton()
        self.settings_button = settings_button
        settings_icon = QIcon(AppConfig.get_icon_path("settings.svg"))
        if settings_icon.isNull():
            settings_icon = title_style.standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
            )
        settings_button.setIcon(settings_icon)
        settings_button.setIconSize(QSize(16, 16))
        settings_button.setFixedSize(30, 30)
        settings_button.setToolTip("Assistant settings")
        settings_button.setAccessibleName("Assistant settings")
        settings_button.setAccessibleDescription("Open Assistant settings.")
        settings_button.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        settings_button.clicked.connect(
            lambda _checked=False: self.settings_requested.emit()
        )
        title_layout.addWidget(settings_button)

        close_button = QPushButton()
        self.close_button = close_button
        close_button.setIcon(
            title_style.standardIcon(QStyle.StandardPixmap.SP_DockWidgetCloseButton)
        )
        close_button.setIconSize(QSize(16, 16))
        close_button.setFixedSize(30, 30)
        close_button.setToolTip("Hide assistant")
        close_button.setAccessibleName("Hide assistant")
        close_button.setAccessibleDescription(
            "Hide the Assistant panel without ending the conversation."
        )
        close_button.setStyleSheet(Stylesheets.AGENT_TITLE_BTN)
        close_button.clicked.connect(self.close)
        title_layout.addWidget(close_button)

        self.setTitleBarWidget(title_bar)
