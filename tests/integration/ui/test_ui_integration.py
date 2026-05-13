from typing import Any, cast

import pytest
from PyQt6.QtCore import Qt

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


def test_evaluation_page_empty_state_uses_command_blocked_reason(qtbot, study):
    """Evaluation page should render backend blocked-state truth."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    window.switch_page(3)
    eval_panel = window.evaluation_panel
    eval_panel.update_panel()

    assert eval_panel.last_application_query is not None
    assert eval_panel.last_application_query.failed
    assert (
        eval_panel.last_application_query.message
        == "Create a training plan before evaluating results."
    )
    assert (
        eval_panel.last_application_query.diagnostics.get("exception_type")
        == "PreconditionError"
    )
    assert eval_panel.model_combo.count() == 1
    assert eval_panel.model_combo.currentText() == "No Data Available"
    assert eval_panel.run_combo.count() == 0
    assert eval_panel.plot_stack.currentIndex() == 1
    assert eval_panel.bottom_tabs.tabText(0) == "Metrics Summary"
    assert eval_panel.bottom_tabs.tabText(1) == "Model Summary"

    window.close()


def test_visualization_page_empty_state_uses_command_blocked_reason(qtbot, study):
    """Visualization page should render backend blocked-state truth."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    window.switch_page(4)
    viz_panel = window.visualization_panel
    viz_panel.update_panel()

    assert viz_panel.last_application_query is not None
    assert viz_panel.last_application_query.failed
    assert (
        viz_panel.last_application_query.message
        == "Create epochs, complete training, or configure saliency before "
        "opening visualization views."
    )
    assert (
        viz_panel.last_application_query.diagnostics.get("exception_type")
        == "PreconditionError"
    )
    assert viz_panel.plan_combo.count() == 1
    assert viz_panel.plan_combo.currentText() == "Select a plan"
    assert viz_panel.run_combo.count() == 0
    assert viz_panel.tabs.tabText(0) == "Saliency Map"
    assert viz_panel.tabs.tabText(1) == "Spectrogram"
    assert viz_panel.tabs.tabText(2) == "Topographic Map"
    current_widget = cast(Any, viz_panel.tabs.currentWidget())
    assert current_widget.error_label.isHidden() is False
    assert (
        current_widget.error_label.text()
        == "Error: Create epochs, complete training, or configure saliency "
        "before opening visualization views."
    )

    window.close()
