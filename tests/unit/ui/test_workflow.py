import pytest
from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.study import Study
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, qtbot):
    study = Study()
    window = MainWindow(study)
    qtbot.addWidget(window)
    return window


def test_full_workflow(main_window, qtbot):
    """
    Simulate a full workflow:
    1. Check Dataset Panel
    2. Check Training Panel
    3. Check Evaluation Panel
    4. Check Visualization Panel
    """
    # 1. Dataset Panel
    main_window.switch_page(0)
    assert isinstance(main_window.stack.currentWidget(), DatasetPanel)

    # 2. Training Panel
    training_ready = []
    main_window.switch_page(2, on_ready=training_ready.append)
    qtbot.waitUntil(lambda: bool(training_ready), timeout=5_000)
    assert isinstance(main_window.stack.currentWidget(), TrainingPanel)
    assert training_ready == [main_window.stack.currentWidget()]

    # 3. Evaluation Panel
    evaluation_ready = []
    main_window.switch_page(3, on_ready=evaluation_ready.append)
    qtbot.waitUntil(lambda: bool(evaluation_ready), timeout=5_000)
    assert main_window.stack.currentIndex() == 3
    assert evaluation_ready == [main_window.stack.currentWidget()]

    # 4. Visualization Panel
    visualization_ready = []
    main_window.switch_page(4, on_ready=visualization_ready.append)
    qtbot.waitUntil(lambda: bool(visualization_ready), timeout=5_000)
    assert main_window.stack.currentIndex() == 4
    assert visualization_ready == [main_window.stack.currentWidget()]
