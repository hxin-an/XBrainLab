"""Base dialog class providing standardized initialization for all dialogs."""

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QPushButton


class BaseDialog(QDialog):
    """Abstract base class for all application dialogs.

    Standardizes initialization (title, size, controller binding) and
    enforces subclass implementation of ``init_ui`` and ``get_result``.

    Attributes:
        controller: Optional backend controller bound to this dialog.

    """

    def __init__(
        self,
        parent=None,
        title: str = "",
        width: int | None = None,
        height: int | None = None,
        controller=None,
    ):
        """Initialize the dialog with optional size and controller.

        Args:
            parent: Optional parent widget.
            title: The dialog window title.
            width: Optional initial width in pixels.
            height: Optional initial height in pixels.
            controller: Optional backend controller for data access.

        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.controller = controller

        if width and height:
            self.resize(width, height)
        elif width:
            self.resize(width, self.height())
        elif height:
            self.resize(self.width(), height)
        self.init_ui()
        self._normalize_dialog_buttons()

    def _normalize_dialog_buttons(self) -> None:
        """Normalize dialog buttons without removing intentional action icons.

        Some Qt platform styles draw an enter/return indicator for default or
        auto-default buttons. XBrainLab dialogs use explicit button labels, so
        the platform glyph adds noise. Standard OK/Cancel icons are also hidden,
        while icons on explicit product actions remain intact.
        """
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        for button_box in self.findChildren(QDialogButtonBox):
            for standard_button in (
                QDialogButtonBox.StandardButton.Ok,
                QDialogButtonBox.StandardButton.Cancel,
            ):
                button = button_box.button(standard_button)
                if button is not None:
                    button.setIcon(QIcon())

    def init_ui(self) -> None:
        """Initialize dialog UI components.

        Must be implemented by subclasses.

        Raises:
            NotImplementedError: Always, unless overridden.

        """
        raise NotImplementedError

    def get_result(self):
        """Return the result data from the dialog after acceptance.

        Must be implemented by subclasses.

        Returns:
            Dialog-specific result data.

        Raises:
            NotImplementedError: Always, unless overridden.

        """
        raise NotImplementedError
