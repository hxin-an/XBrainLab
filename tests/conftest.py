"""Shared pytest fixtures and global test configuration.

This conftest module provides:

* Mocks for visualisation libraries (PyVista / VTK) that cannot run in a
  headless CI environment.
* An ``autouse`` fixture that patches blocking Qt dialog calls so tests
  never hang waiting for user interaction.
* A session-scoped fixture that forces matplotlib to a non-interactive
  backend.
* A ``test_app`` fixture that spins up a headless
  :class:`~XBrainLab.ui.main_window.MainWindow` for integration tests.
"""

# Global mocks have been disabled as the environment has all dependencies installed.
# Previously, this file mocked mne, captum, and torch, which caused import errors.

import sys
from typing import Any
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
    """Lightweight stand-in for ``pyvistaqt.BackgroundPlotter``.

    Provides no-op implementations of commonly called plotter methods so
    that code importing PyVista/VTK can be exercised in environments
    without GPU or OpenGL support.

    Attributes:
        app_window: Mock application window handle.
        ren_win: Mock render-window object.
        interactor: Mock interactor object.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise the mock plotter with mock sub-components."""
        super().__init__()
        self.app_window = MagicMock()
        self.ren_win = MagicMock()
        self.interactor = MagicMock()

    def add_mesh(self, *args: Any, **kwargs: Any) -> None:
        """No-op replacement for ``BackgroundPlotter.add_mesh``."""

    def add_text(self, *args: Any, **kwargs: Any) -> None:
        """No-op replacement for ``BackgroundPlotter.add_text``."""

    def show(self) -> None:
        """No-op replacement for ``BackgroundPlotter.show``."""

    def close(self) -> None:
        """No-op replacement for ``BackgroundPlotter.close``."""


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
    """Globally mock blocking UI calls to prevent tests from hanging.

    Patches every ``QMessageBox`` static convenience method and both
    ``QMessageBox.exec`` / ``QDialog.exec`` so that no modal dialog
    blocks the event loop during test execution.

    Yields:
        None. The patches are active for the duration of each test.
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
    """Force matplotlib to use the non-interactive ``Agg`` backend.

    This session-scoped, auto-used fixture ensures that matplotlib never
    tries to open a GUI window during the test run.
    """
    if matplotlib:
        matplotlib.use("Agg")


@pytest.fixture
def test_app(qtbot):
    """Create a headless ``MainWindow`` for integration testing.

    Instantiates a :class:`~XBrainLab.backend.study.Study` and a
    :class:`~XBrainLab.ui.main_window.MainWindow`, registers the widget
    with *qtbot*, and waits until it is exposed before yielding.

    Args:
        qtbot: The ``pytest-qt`` bot that manages the Qt event loop.

    Yields:
        MainWindow: The fully initialised and visible main window
        instance.  The window is automatically closed during teardown.
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
