"""Shared pytest fixtures and fail-closed test-environment defaults."""

# Global mocks have been disabled as the environment has all dependencies installed.
# Previously, this file mocked mne, captum, and torch, which caused import errors.

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn

from scripts.dev.test_runtime_paths import (
    configure_test_temp_root,
    matplotlib_cache_root,
)

# --- PYTEST COLLECTION FIX ---
# Prevent pytest from scanning XBrainLab source directory as tests
collect_ignore_glob = ["../XBrainLab/**"]

# --- HEADLESS DEFAULTS FOR THIS WORKSPACE ---
# Direct unattended pytest invocations in the current Codex/WSL workspace can
# otherwise abort during pytest-qt qapp startup or fall back to flaky fd
# capture behavior. Set conservative defaults here so the repo itself carries
# the known-good test environment, instead of relying only on wrappers.
repo_root = Path(__file__).resolve().parents[1]
test_temp_root = configure_test_temp_root(repo_root)
matplotlib_cache_dir = matplotlib_cache_root(test_temp_root)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ["MPLCONFIGDIR"] = str(matplotlib_cache_dir)
os.makedirs(matplotlib_cache_dir, exist_ok=True)

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


def _unexpected_modal(*_args: Any, **_kwargs: Any) -> NoReturn:
    raise AssertionError(
        "Unexpected blocking Qt modal. Request auto_accept_modals for a bounded "
        "component test or allow_real_modals for a qtbot-driven modal test."
    )


@pytest.fixture(autouse=True)
def guard_unexpected_modal_interactions(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast instead of silently accepting an undeclared product decision."""
    if "allow_real_modals" in request.fixturenames:
        return
    for method_name in ("information", "warning", "critical", "question", "exec"):
        monkeypatch.setattr(QMessageBox, method_name, _unexpected_modal)
    monkeypatch.setattr(QDialog, "exec", _unexpected_modal)


@pytest.fixture
def auto_accept_modals(
    guard_unexpected_modal_interactions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opt into the former non-blocking accepted result for component tests."""
    del guard_unexpected_modal_interactions
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda *_args, **_kwargs: QDialog.DialogCode.Accepted,
    )


@pytest.fixture
def allow_real_modals() -> None:
    """Mark a test as using real modals driven through the Qt event loop."""


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


@pytest.fixture
def capture_product_logs(caplog):
    """Capture records after the central XBrainLab disclosure filter ran."""

    @contextmanager
    def capture(
        level: int = logging.INFO,
        *,
        logger_name: str = "XBrainLab",
    ):
        product_logger = logging.getLogger("XBrainLab")
        product_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(level, logger=logger_name):
                yield caplog
        finally:
            product_logger.removeHandler(caplog.handler)

    return capture
