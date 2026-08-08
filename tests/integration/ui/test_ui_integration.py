from typing import Any, cast

import pytest
from PyQt6.QtCore import Qt

from XBrainLab.backend.application import CommandName, ErrorType
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import get_application_view_publication
from XBrainLab.ui.main_window import MainWindow

EXPECTED_NAV_TEXTS = [
    "Dataset",
    "Preprocess",
    "Training",
    "Evaluation",
    "Visualization",
]
EXPECTED_PANEL_ATTRS = [
    "dataset_panel",
    "preprocess_panel",
    "training_panel",
    "evaluation_panel",
    "visualization_panel",
]


def _checked_states(window):
    return [button.isChecked() for button in window.nav_btns]


def _checked_state_for(index: int) -> list[bool]:
    return [button_index == index for button_index in range(len(EXPECTED_NAV_TEXTS))]


def _switch_and_wait_for_panel(window: MainWindow, index: int, qtbot) -> Any:
    ready_panels: list[Any] = []
    window.switch_page(index, on_ready=ready_panels.append)
    qtbot.waitUntil(lambda: len(ready_panels) == 1, timeout=5_000)
    return ready_panels[0]


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
    assert window.agent_manager is None

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
        qtbot.waitUntil(
            lambda index=index: index in window._loaded_panel_indices,
            timeout=5_000,
        )
        panel = getattr(window, EXPECTED_PANEL_ATTRS[index])
        assert window.stack.currentIndex() == index
        assert _checked_states(window) == _checked_state_for(index)
        assert window.stack.currentWidget() is panel
        assert window.stack.widget(index) is panel

    window.close()


def test_evaluation_page_empty_state_uses_command_blocked_reason(qtbot, study):
    """Evaluation page should render backend blocked-state truth."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    eval_panel = _switch_and_wait_for_panel(window, 3, qtbot)
    eval_panel.update_panel()

    publication = get_application_view_publication(window)
    assert publication is not None
    assert publication.usable
    capability = publication.effective_capabilities.get(CommandName.EVALUATE)
    assert capability.enabled is False
    assert capability.reasons == ["Create a training plan before evaluating results."]
    blocked_reason = capability.reasons[0]
    assert eval_panel.model_combo.count() == 0
    assert eval_panel.model_combo.isEnabled() is False
    assert eval_panel.model_combo.toolTip() == blocked_reason
    assert eval_panel.no_data_label.text() == blocked_reason
    assert eval_panel.run_combo.count() == 0
    assert eval_panel.plot_stack.currentIndex() == 1
    assert eval_panel.bottom_tabs.tabText(0) == "Metrics Summary"
    assert eval_panel.bottom_tabs.tabText(1) == "Model Summary"

    window.close()


def test_visualization_page_empty_state_uses_command_blocked_reason(qtbot, study):
    """Visualization page should render backend blocked-state truth."""
    window = MainWindow(study)
    qtbot.addWidget(window)

    viz_panel = _switch_and_wait_for_panel(window, 4, qtbot)
    viz_panel.update_panel()

    publication = get_application_view_publication(window)
    assert publication is not None
    assert publication.usable
    capability = publication.effective_capabilities.get(CommandName.VISUALIZE)
    assert capability.enabled is False
    assert capability.reasons == [
        "Create EEG epochs, complete training, or configure saliency before "
        "opening visualization views."
    ]
    blocked_reason = capability.reasons[0]
    query_result = viz_panel.last_application_query
    assert query_result is not None
    assert query_result.failed
    assert query_result.error_type is ErrorType.PRECONDITION
    assert query_result.message == blocked_reason
    assert query_result.state == publication.state
    assert query_result.state is not publication.state
    assert query_result.diagnostics.get("exception_type") != "PreconditionError"
    assert viz_panel.plan_combo.count() == 1
    assert viz_panel.plan_combo.currentText() == "Select a fold"
    assert viz_panel.run_combo.count() == 0
    assert viz_panel.tabs.tabText(0) == "Saliency Map"
    assert viz_panel.tabs.tabText(1) == "Spectrogram"
    assert viz_panel.tabs.tabText(2) == "Topographic Map"
    current_widget = cast(Any, viz_panel.tabs.currentWidget())
    assert current_widget.error_label.isHidden() is False
    assert current_widget.error_label.text() == blocked_reason
    assert "Error:" not in current_widget.error_label.text()

    window.close()
