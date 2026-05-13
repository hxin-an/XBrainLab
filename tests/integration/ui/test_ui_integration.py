import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.study import Study
from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def study():
    """Return a real empty Study for UI integration startup/navigation checks."""
    return Study()


def test_mainwindow_launch(qtbot, study):
    """Test that MainWindow launches without error."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    # Check window title and visibility
    assert window.windowTitle() == "XBrainLab"
    window.show()
    assert window.isVisible()
    window.close()


def test_navigation(qtbot, study):
    """Test navigation between main panels."""
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()

    # 1. Dataset (Default)
    assert window.stack.currentIndex() == 0

    # 2. Preprocess
    qtbot.mouseClick(window.nav_btns[1], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 1

    # 3. Training
    qtbot.mouseClick(window.nav_btns[2], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 2

    # 4. Evaluation
    qtbot.mouseClick(window.nav_btns[3], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 3

    # 5. Visualization
    qtbot.mouseClick(window.nav_btns[4], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 4

    window.close()


def test_evaluation_panel_init(qtbot, study):
    """Test EvaluationPanel initialization and tab loading."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    # Switch to Evaluation
    window.switch_page(3)
    eval_panel = window.evaluation_panel

    # Check widgets exist (Matrix and Metrics Table are now separate/in
    # different layout)
    assert isinstance(eval_panel.matrix_widget, QWidget)
    assert isinstance(eval_panel.metrics_table, QWidget)

    # Check bottom tabs (Metrics Summary, Model Summary)
    assert eval_panel.bottom_tabs.count() >= 2
    assert eval_panel.bottom_tabs.tabText(0) == "Metrics Summary"
    assert eval_panel.bottom_tabs.tabText(1) == "Model Summary"

    window.close()


def test_visualization_panel_init(qtbot, study):
    """Test VisualizationPanel initialization and tab loading."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    # Switch to Visualization
    window.switch_page(4)
    viz_panel = window.visualization_panel

    # Check tabs exist (Saliency Map, Topographic Map, Spectrogram, 3D Plot)
    assert viz_panel.tabs.count() >= 4
    assert viz_panel.tabs.tabText(0) == "Saliency Map"
    assert viz_panel.tabs.tabText(1) == "Spectrogram"
    assert viz_panel.tabs.tabText(2) == "Topographic Map"

    # Check if widgets inside tabs are initialized
    assert isinstance(viz_panel.tab_map, QWidget)
    assert isinstance(viz_panel.tab_topo, QWidget)

    window.close()
