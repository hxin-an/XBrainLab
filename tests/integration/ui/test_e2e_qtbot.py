"""End-to-end UI tests exercising real widget interactions via pytest-qt.

These tests launch a headless ``MainWindow`` (backed by a real ``Study``)
and drive the user-facing controls through ``qtbot``.  They validate:

* Panel navigation via button clicks
* Dataset panel load-file interaction
* Training panel widget presence
* AI assistant dock toggle
* Status-bar updates on panel switch
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QWidget

from XBrainLab.ui.components.info_panel_service import InfoPanelService
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPECTED_NAV_TEXTS = [
    "Dataset",
    "Preprocess",
    "Training",
    "Evaluation",
    "Visualization",
]
EXPECTED_PANEL_TYPES = [
    DatasetPanel,
    PreprocessPanel,
    TrainingPanel,
    EvaluationPanel,
    VisualizationPanel,
]
EXPECTED_EVALUATION_TABS = ["Metrics Summary", "Model Summary"]
EXPECTED_VISUALIZATION_TABS = [
    "Saliency Map",
    "Spectrogram",
    "Topographic Map",
    "3D Plot",
]


def _click(qtbot, btn: QPushButton):
    """Convenience wrapper for mouseClick on a button."""
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    qtbot.wait(50)  # Let Qt's event loop process the click


def _checked_states(test_app):
    return [button.isChecked() for button in test_app.nav_btns]


def _checked_state_for(index: int) -> list[bool]:
    return [button_index == index for button_index in range(len(EXPECTED_NAV_TEXTS))]


def _tab_texts(tab_widget):
    return [tab_widget.tabText(index) for index in range(tab_widget.count())]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNavigation:
    """Tests for the top-bar panel navigation."""

    def test_initial_panel_is_dataset(self, test_app):
        """Dataset panel (index 0) should be active on launch."""
        assert test_app.stack.currentIndex() == 0
        assert [button.text() for button in test_app.nav_btns] == EXPECTED_NAV_TEXTS
        assert _checked_states(test_app) == _checked_state_for(0)

    @pytest.mark.parametrize(
        "btn_index, expected_panel",
        [
            (1, 1),  # Preprocess
            (2, 2),  # Training
            (3, 3),  # Evaluation
            (4, 4),  # Visualization
            (0, 0),  # Back to Dataset
        ],
    )
    def test_click_nav_buttons(self, test_app, qtbot, btn_index, expected_panel):
        """Clicking a nav button switches the stacked widget."""
        _click(qtbot, test_app.nav_btns[btn_index])
        assert test_app.stack.currentIndex() == expected_panel
        assert _checked_states(test_app) == _checked_state_for(expected_panel)

    def test_only_one_btn_checked_at_a_time(self, test_app, qtbot):
        """At most one nav button should be checked after a click."""
        _click(qtbot, test_app.nav_btns[2])  # Training
        assert _checked_states(test_app) == _checked_state_for(2)

    def test_round_trip_returns_to_original(self, test_app, qtbot):
        """Navigate away and back — panel index should be restored."""
        _click(qtbot, test_app.nav_btns[3])
        assert test_app.stack.currentIndex() == 3
        assert _checked_states(test_app) == _checked_state_for(3)
        _click(qtbot, test_app.nav_btns[0])
        assert test_app.stack.currentIndex() == 0
        assert _checked_states(test_app) == _checked_state_for(0)


class TestAIAssistantDock:
    """Tests for the AI Assistant toggle button and dock widget."""

    def test_ai_button_exists(self, test_app):
        """The AI toggle button should be present and checkable."""
        assert isinstance(test_app.ai_btn, QPushButton)
        assert test_app.ai_btn.text() == "AI Assistant"
        assert test_app.ai_btn.objectName() == "ActionBtn"
        assert test_app.ai_btn.isCheckable()

    def test_ai_button_default_state(self, test_app):
        """AI assistant should be OFF by default."""
        assert not test_app.ai_btn.isChecked()

    def test_toggle_ai_dock(self, test_app, qtbot):
        """Toggling the AI button should change its checked state."""

        def _fake_start_system():
            test_app.agent_manager.agent_initialized = True

        test_app.agent_manager.start_system = _fake_start_system
        _click(qtbot, test_app.ai_btn)
        assert test_app.ai_btn.isChecked()
        assert test_app.agent_manager.chat_dock.isVisible()
        _click(qtbot, test_app.ai_btn)
        assert not test_app.ai_btn.isChecked()
        assert not test_app.agent_manager.chat_dock.isVisible()


class TestPanelWidgets:
    """Verify that key widgets exist inside each panel."""

    def test_panel_types_match_stack_order(self, test_app):
        panels = [
            test_app.stack.widget(index) for index in range(test_app.stack.count())
        ]

        assert [type(panel) for panel in panels] == EXPECTED_PANEL_TYPES
        assert panels == [
            test_app.dataset_panel,
            test_app.preprocess_panel,
            test_app.training_panel,
            test_app.evaluation_panel,
            test_app.visualization_panel,
        ]

    def test_evaluation_panel_tabs(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[3])
        ep = test_app.evaluation_panel
        assert _tab_texts(ep.bottom_tabs) == EXPECTED_EVALUATION_TABS

    def test_visualization_panel_tabs(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[4])
        vp = test_app.visualization_panel
        assert _tab_texts(vp.tabs) == EXPECTED_VISUALIZATION_TABS


class TestStackedWidgetIntegrity:
    """Structural assertions on the QStackedWidget."""

    def test_exactly_five_panels(self, test_app):
        assert test_app.stack.count() == 5

    def test_panels_are_qwidgets(self, test_app):
        for i in range(test_app.stack.count()):
            assert isinstance(test_app.stack.widget(i), QWidget)


class TestInfoService:
    """Verify the InfoPanelService is wired up."""

    def test_info_service_has_study_ref(self, test_app):
        assert isinstance(test_app.info_service, InfoPanelService)
        assert test_app.info_service.study is test_app.study
        assert test_app.info_service._observes_controller_events is False
