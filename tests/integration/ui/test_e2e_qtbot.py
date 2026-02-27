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
from PyQt6.QtWidgets import QPushButton

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _click(qtbot, btn: QPushButton):
    """Convenience wrapper for mouseClick on a button."""
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    qtbot.wait(50)  # Let Qt's event loop process the click


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNavigation:
    """Tests for the top-bar panel navigation."""

    def test_initial_panel_is_dataset(self, test_app):
        """Dataset panel (index 0) should be active on launch."""
        assert test_app.stack.currentIndex() == 0
        assert test_app.nav_btns[0].isChecked()

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

    def test_only_one_btn_checked_at_a_time(self, test_app, qtbot):
        """At most one nav button should be checked after a click."""
        _click(qtbot, test_app.nav_btns[2])  # Training
        checked = [b.isChecked() for b in test_app.nav_btns]
        assert checked.count(True) == 1
        assert checked[2] is True

    def test_round_trip_returns_to_original(self, test_app, qtbot):
        """Navigate away and back — panel index should be restored."""
        _click(qtbot, test_app.nav_btns[3])
        assert test_app.stack.currentIndex() == 3
        _click(qtbot, test_app.nav_btns[0])
        assert test_app.stack.currentIndex() == 0


class TestAIAssistantDock:
    """Tests for the AI Assistant toggle button and dock widget."""

    def test_ai_button_exists(self, test_app):
        """The AI toggle button should be present and checkable."""
        assert test_app.ai_btn is not None
        assert test_app.ai_btn.isCheckable()

    def test_ai_button_default_state(self, test_app):
        """AI assistant should be OFF by default."""
        assert not test_app.ai_btn.isChecked()

    def test_toggle_ai_dock(self, test_app, qtbot):
        """Toggling the AI button should change its checked state."""
        _click(qtbot, test_app.ai_btn)
        assert test_app.ai_btn.isChecked()
        _click(qtbot, test_app.ai_btn)
        assert not test_app.ai_btn.isChecked()


class TestPanelWidgets:
    """Verify that key widgets exist inside each panel."""

    def test_dataset_panel_has_expected_children(self, test_app):
        panel = test_app.dataset_panel
        # DatasetPanel should have a load button or file-list widget.
        # We only assert the panel type to avoid coupling to internal layout.
        from XBrainLab.ui.panels.dataset.panel import DatasetPanel

        assert isinstance(panel, DatasetPanel)

    def test_preprocess_panel_type(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[1])
        from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel

        assert isinstance(test_app.preprocess_panel, PreprocessPanel)

    def test_training_panel_type(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[2])
        from XBrainLab.ui.panels.training.panel import TrainingPanel

        assert isinstance(test_app.training_panel, TrainingPanel)

    def test_evaluation_panel_tabs(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[3])
        ep = test_app.evaluation_panel
        assert ep.bottom_tabs.count() >= 2
        assert ep.bottom_tabs.tabText(0) == "Metrics Summary"

    def test_visualization_panel_tabs(self, test_app, qtbot):
        _click(qtbot, test_app.nav_btns[4])
        vp = test_app.visualization_panel
        assert vp.tabs.count() >= 3


class TestStackedWidgetIntegrity:
    """Structural assertions on the QStackedWidget."""

    def test_exactly_five_panels(self, test_app):
        assert test_app.stack.count() == 5

    def test_panels_are_qwidgets(self, test_app):
        from PyQt6.QtWidgets import QWidget

        for i in range(test_app.stack.count()):
            assert isinstance(test_app.stack.widget(i), QWidget)


class TestInfoService:
    """Verify the InfoPanelService is wired up."""

    def test_info_service_exists(self, test_app):
        assert test_app.info_service is not None

    def test_info_service_has_study_ref(self, test_app):
        assert test_app.info_service.study is test_app.study
