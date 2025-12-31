import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from XBrainLab.ui_pyqt.main_window import MainWindow

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

from XBrainLab import Study

@pytest.fixture
def main_window(qapp, qtbot):
    study = Study()
    window = MainWindow(study)
    qtbot.addWidget(window)
    return window

def test_mainwindow_launch(main_window, qtbot):
    """Smoke test: Ensure MainWindow launches and is visible."""
    main_window.show()
    qtbot.waitUntil(lambda: main_window.isVisible())
    assert main_window.isVisible()

def test_navigation(main_window, qtbot):
    """Test that clicking navigation buttons switches the stacked widget page."""
    # Define expected mapping: Button Text -> Stack Index
    # Based on MainWindow.init_panels:
    # 0: Dataset, 1: Preprocess, 2: Training, 3: Evaluation, 4: Visualization
    nav_map = {
        "Dataset": 0,
        "Preprocess": 1,
        "Training": 2,
        "Evaluation": 3,
        "Visualization": 4
    }
    
    for btn_text, expected_index in nav_map.items():
        # Find the button by text
        btn = None
        for b in main_window.nav_btns:
            if b.text() == btn_text:
                btn = b
                break
        
        assert btn is not None, f"Navigation button '{btn_text}' not found."
        
        # Click the button
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        
        # Verify stack index
        assert main_window.stack.currentIndex() == expected_index, \
            f"Failed to switch to {btn_text} (Index {expected_index})"
        
        # Verify button is checked
        assert btn.isChecked(), f"Button '{btn_text}' should be checked."
