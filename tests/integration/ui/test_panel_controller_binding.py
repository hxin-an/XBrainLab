"""Integration tests ensuring UI panels respond to injected controller events."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.controller.training_controller import TrainingController
from XBrainLab.backend.study import Study
from XBrainLab.ui.panels.training.panel import TrainingPanel

# Mocking the TrainingPanel dependencies is tricky because it's complex.
# We'll rely on the existing codebase's structure where panels accept 'parent' which has 'study'.


class TestPanelControllerBinding:
    """Test UI <-> controller event wiring without legacy Study lookup evidence."""

    @pytest.fixture
    def training_controller(self):
        controller = MagicMock(spec=TrainingController)
        controller.validate_ready.return_value = False
        return controller

    @pytest.fixture
    def dataset_controller(self):
        return MagicMock()

    @pytest.fixture
    def preprocess_controller(self):
        return MagicMock()

    @pytest.fixture
    def training_panel(
        self,
        qtbot,
        training_controller,
        dataset_controller,
        preprocess_controller,
    ):
        parent = cast(Any, QWidget())
        parent.study = MagicMock(spec=Study)
        parent.study.get_controller = MagicMock(
            side_effect=AssertionError("legacy Study controller lookup is not allowed"),
        )

        panel = TrainingPanel(
            controller=training_controller,
            dataset_controller=dataset_controller,
            preprocess_controller=preprocess_controller,
            parent=parent,
        )
        qtbot.addWidget(panel)
        return panel

    def test_training_start_event_updates_ui(self, training_panel):
        """Test 'training_started' event updates sidebar."""
        training_panel.sidebar = MagicMock()

        training_panel._on_training_started()

        training_panel.sidebar.on_training_started.assert_called_once()
        assert "started" in training_panel.log_text.toPlainText()

    def test_training_update_event_clears_empty_history(self, training_panel):
        """Test 'training_updated' clears stale display state when history is empty."""
        stale_record = object()
        training_panel.current_plotting_record = stale_record
        training_panel._last_epoch_count = 3
        training_panel.history_table = MagicMock()
        training_panel.tab_acc = MagicMock()
        training_panel.tab_loss = MagicMock()
        training_panel._history_from_application_query = MagicMock(return_value=[])
        training_panel._legacy_history_for_render = MagicMock()

        with patch(
            "XBrainLab.ui.panels.training.panel.refresh_after_observer",
        ) as refresh_after_observer:
            training_panel._on_training_updated()

        training_panel.history_table.clear_history.assert_called_once()
        training_panel.history_table.update_table.assert_not_called()
        training_panel.tab_acc.clear.assert_called_once()
        training_panel.tab_loss.clear.assert_called_once()
        assert training_panel.current_plotting_record is None
        assert training_panel._last_epoch_count == -1
        training_panel._legacy_history_for_render.assert_not_called()
        refresh_after_observer.assert_called_once_with(
            training_panel,
            event_name="training_updated",
        )

    def test_uses_injected_controller_without_study_lookup(
        self,
        training_panel,
        training_controller,
    ):
        """Panel event wiring should use injected controllers, not Study lookup."""
        assert training_panel.controller is training_controller
        training_panel.main_window.study.get_controller.assert_not_called()
