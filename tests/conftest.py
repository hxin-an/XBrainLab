# Global mocks have been disabled as the environment has all dependencies installed.
# Previously, this file mocked mne, captum, and torch, which caused import errors.

import sys
from unittest.mock import MagicMock, patch

import matplotlib
import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

# --- MOCK VISUALIZATION LIBRARIES ---
# This must be done at module level to prevent import errors during test collection
# because the environment (headless/no-opengl) cannot support real VTK/PyVista.


class MockBackgroundPlotter(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.app_window = MagicMock()
        self.ren_win = MagicMock()
        self.interactor = MagicMock()

    def add_mesh(self, *args, **kwargs):
        pass

    def add_text(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def close(self):
        pass


mock_pv = MagicMock()
mock_pvqt = MagicMock()
mock_pvqt.BackgroundPlotter = MockBackgroundPlotter

sys.modules["pyvista"] = mock_pv
sys.modules["pyvistaqt"] = mock_pvqt
sys.modules["pyvista.plotting"] = MagicMock()
sys.modules["vtkmodules"] = MagicMock()
sys.modules["vtkmodules.vtkRenderingOpenGL2"] = MagicMock()


@pytest.fixture(autouse=True)
def mock_ui_blocking():
    """
    Globally mock blocking UI calls to prevent tests from hanging.
    This handles QMessageBox and QDialog.exec().
    """
    # Patch QMessageBox static methods
    with (
        patch("PyQt6.QtWidgets.QMessageBox.information"),
        patch("PyQt6.QtWidgets.QMessageBox.warning"),
        patch("PyQt6.QtWidgets.QMessageBox.critical"),
        patch("PyQt6.QtWidgets.QMessageBox.question") as mock_quest,
        patch(
            "PyQt6.QtWidgets.QMessageBox.exec",
            return_value=QMessageBox.StandardButton.Ok,
        ),
        patch("PyQt6.QtWidgets.QDialog.exec", return_value=QDialog.DialogCode.Accepted),
    ):
        # Configure defaults
        mock_quest.return_value = QMessageBox.StandardButton.Yes

        yield


@pytest.fixture(scope="session", autouse=True)
def configure_matplotlib():
    """Force matplotlib to use non-interactive backend for testing."""
    matplotlib.use("Agg")
