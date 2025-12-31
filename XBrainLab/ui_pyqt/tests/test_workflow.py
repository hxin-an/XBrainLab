import pytest
from PyQt6.QtWidgets import QApplication
from XBrainLab import Study
from XBrainLab.ui_pyqt.main_window import MainWindow
from XBrainLab.ui_pyqt.dashboard_panel.dataset import DatasetPanel
from XBrainLab.ui_pyqt.training.panel import TrainingPanel

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
    main_window.switch_page(2)
    assert isinstance(main_window.stack.currentWidget(), TrainingPanel)
    
    # 3. Evaluation Panel
    main_window.switch_page(3)
    # This might trigger the AttributeError if it happens on switch/show
    assert main_window.stack.currentIndex() == 3
    
    # 4. Visualization Panel
    main_window.switch_page(4)
    # This might trigger the NameError if it happens on switch/show
    assert main_window.stack.currentIndex() == 4
