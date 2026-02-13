# Global mocks have been disabled as the environment has all dependencies installed.
# Previously, this file mocked mne, captum, and torch, which caused import errors.

import sys
from unittest.mock import MagicMock, patch

# --- PYTEST COLLECTION FIX ---
# Prevent pytest from scanning XBrainLab source directory as tests
collect_ignore_glob = ["../XBrainLab/**"]

# --- KNOWN ISSUE: pytest-cov / PyTorch Conflict ---
# Coverage.py's trace instrumentation conflicts with PyTorch's C-extension docstring
# registration. The error "_has_torch_function already has a docstring" occurs because
# coverage traces the import, causing torch/overrides.py to execute twice.
#
# WORKAROUND (tested successfully):
# Run tests WITHOUT --cov flag: poetry run pytest tests/unit
# Coverage must be measured using slipcover or alternative tools.
#
# STATUS: This is a known upstream issue affecting pytest-cov + torch on Windows.
# See: https://github.com/pytorch/pytorch/issues/96606

try:
    import matplotlib
except ImportError:
    matplotlib = None
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
    if matplotlib:
        matplotlib.use("Agg")


@pytest.fixture
def test_app(qtbot):
    """
    Create a Headless MainWindow for testing.
    Uses 'qtbot' from pytest-qt to handle the event loop.
    """
    # Import locally to avoid circular imports or early init issues
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    # 1. Create Study (Backend)
    study = Study()

    # 2. Create Window (UI)
    window = MainWindow(study)

    # 3. Register widget with qtbot
    qtbot.addWidget(window)

    # 4. Wait for exposure
    window.show()
    qtbot.waitExposed(window)

    yield window

    # 5. Cleanup
    window.close()
