import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.ui.styles.theme import Theme


class BaseSaliencyView(QWidget):
    """Abstract base class for all Saliency views (Map, Spectrogram, Topo, 3D).
    Standardizes layout, error handling, and placeholder display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = (
            parent.main_window if parent and hasattr(parent, "main_window") else None
        )
        # Try to resolve controller from parent panel (VisualizationPanel)
        self.controller = (
            parent.controller if parent and hasattr(parent, "controller") else None
        )

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Matplotlib Canvas (Default, subclasses can override)
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.fig)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig)

        self.main_layout.addWidget(self.canvas)

        # 2. Error Message (Hidden by default)
        self.error_label = QLabel()
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.hide()
        self.main_layout.addWidget(self.error_label)

    def show_error(self, message):
        """Display an error message overlaid on the view."""
        self.canvas.hide()
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()

    def clear_plot(self):
        """Clear the plot and reset error state."""
        self.error_label.hide()
        self.canvas.show()
        self.fig.clear()
        self.canvas.draw()

    def update_view(self, result, params):
        """Update the view with calculation results.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def closeEvent(self, event):  # noqa: N802
        """Release matplotlib Figure to prevent memory leaks."""
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
        super().closeEvent(event)
