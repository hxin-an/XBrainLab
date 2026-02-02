from PyQt6.QtWidgets import QDialog


class BaseDialog(QDialog):
    """
    Abstract base class for all application dialogs.
    Standardizes initialization and result retrieval.
    """

    def __init__(
        self,
        parent=None,
        title: str = "",
        width: int | None = None,
        height: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        if parent and hasattr(parent, "study") and parent.study:
            # Apply theme from study config or global?
            # For now just apply global stylesheet
            pass
        if width and height:
            self.resize(width, height)
        elif width:
            self.resize(width, self.height())
        elif height:
            self.resize(self.width(), height)
        self.init_ui()

    def init_ui(self) -> None:
        """
        Initialize dialog UI components.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def get_result(self):
        """
        Return the result data from the dialog after acceptance.
        Must be implemented by subclasses.
        """
        raise NotImplementedError
