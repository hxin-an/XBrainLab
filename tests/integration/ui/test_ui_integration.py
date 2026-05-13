from typing import Any, cast

import pytest
from PyQt6.QtCore import Qt

from XBrainLab.backend.study import Study
from XBrainLab.ui.main_window import MainWindow

EXPECTED_NAV_TEXTS = [
    "Dataset",
    "Preprocess",
    "Training",
    "Evaluation",
    "Visualization",
]


def _checked_states(window):
    return [button.isChecked() for button in window.nav_btns]


def _checked_state_for(index: int) -> list[bool]:
    return [button_index == index for button_index in range(len(EXPECTED_NAV_TEXTS))]


@pytest.fixture
def study():
    """Return a real empty Study for UI integration startup/navigation checks."""
    return Study()


def test_mainwindow_launches_with_product_shell_contract(qtbot, study):
    """MainWindow launch should expose the product shell contract."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    assert window.windowTitle() == "XBrainLab"
    assert window.stack.count() == 5
    assert [button.text() for button in window.nav_btns] == EXPECTED_NAV_TEXTS
    assert [button.objectName() for button in window.nav_btns] == [
        "NavButton",
        "NavButton",
        "NavButton",
        "NavButton",
        "NavButton",
    ]
    assert window.stack.currentIndex() == 0
    assert _checked_states(window) == _checked_state_for(0)
    assert window.ai_btn.text() == "AI Assistant"
    assert window.ai_btn.objectName() == "ActionBtn"
    assert window.ai_btn.isCheckable()
    assert window.ai_btn.isChecked() is False
    assert window.info_service.study is study
    assert window.info_service._observes_controller_events is False
    assert window.agent_manager.preprocess_controller is None

    window.show()
    assert window.isVisible()
    window.close()


def test_navigation_buttons_keep_page_and_checked_state_in_sync(qtbot, study):
    """Navigation should keep page index and checked state in sync."""
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()

    assert window.stack.currentIndex() == 0
    assert _checked_states(window) == _checked_state_for(0)

    for index in (1, 2, 3, 4, 0):
        qtbot.mouseClick(window.nav_btns[index], Qt.MouseButton.LeftButton)
        assert window.stack.currentIndex() == index
        assert _checked_states(window) == _checked_state_for(index)
        assert window.stack.currentWidget() is window.stack.widget(index)

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
