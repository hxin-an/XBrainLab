"""
Training UI and Study compatibility regression tests.

These tests exercise UI panel update behavior and lower-level Study training
delegation with mocked trainers. Product workflow success evidence belongs in
ApplicationService command/query smokes, not direct mutable Study assertions.
"""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import torch
from PyQt6.QtWidgets import QWidget

from XBrainLab import Study
from XBrainLab.backend.application import (
    ApplicationService,
    ConfigureTrainingCommand,
    QueryStateCommand,
)
from XBrainLab.backend.model_base import SCCNet
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.model_holder import ModelHolder
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel
from XBrainLab.ui.panels.training.panel import MetricTab, TrainingPanel
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


def _ui_text(value: str) -> Any:
    """Represent text-field values passed through runtime validation."""
    return cast(Any, value)


@pytest.fixture
def real_training_option():
    """Create a real TrainingOption with minimal epochs for testing."""
    return TrainingOption(
        output_dir="./test_output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=_ui_text("2"),  # Minimal epochs for fast testing
        bs=_ui_text("4"),
        lr=_ui_text("0.001"),
        checkpoint_epoch=_ui_text("1"),
        evaluation_option=TrainingEvaluation.TEST_ACC,
        repeat_num=_ui_text("1"),
    )


class TestTrainingPanelRealUsage:
    """Test TrainingPanel with realistic user workflow."""

    def test_repeated_training_no_duplicate_messages(self, qtbot, real_training_option):
        """
        Verify that training completion message only shows once,
        not on every update.
        """
        # Setup study with real option

        study = Study()
        study.set_training_option(real_training_option)
        model_holder = ModelHolder(SCCNet, {})
        study.set_model_holder(model_holder)

        # Create panel
        parent = cast(Any, QWidget())
        parent.study = study
        panel = TrainingPanel(parent=parent)
        qtbot.addWidget(panel)

        # Verify flag is initialized
        assert isinstance(panel.training_completed_shown, bool)
        assert panel.training_completed_shown is False

        # Simulate starting training
        panel.training_completed_shown = False

        # Simulate multiple calls to training_finished (like update_loop does)
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_msg:
            panel.training_finished()
            assert mock_msg.call_count == 1, "First call should show message"

            # Simulate update_loop calling it again
            panel.training_finished()
            assert mock_msg.call_count == 1, "Should not show message again"

            panel.training_finished()
            assert mock_msg.call_count == 1, "Should still not show message"

    def test_update_loop_type_safety(self, qtbot, real_training_option):
        """Verify that update_loop handles type conversions correctly."""

        study = Study()
        study.set_training_option(real_training_option)
        model_holder = ModelHolder(SCCNet, {})
        study.set_model_holder(model_holder)

        parent = cast(Any, QWidget())
        parent.study = study

        panel = TrainingPanel(parent=parent)
        qtbot.addWidget(panel)

        # Mock trainer and plan
        mock_trainer = MagicMock()
        mock_plan = MagicMock()

        # Simulate get_training_epoch returning int
        mock_plan.get_training_epoch.return_value = 1
        mock_plan.get_training_status.return_value = "Running"
        mock_plan.get_training_evaluation.return_value = (
            0.001,
            0.5,
            0.8,
            0.9,
            0.6,
            0.75,
            0.85,
        )

        mock_trainer.get_training_plan_holders.return_value = [mock_plan]
        mock_trainer.is_running.return_value = True
        mock_trainer.current_idx = 0
        mock_trainer.get_progress_text.return_value = "Training..."
        mock_plan.get_epoch_progress_text.return_value = "Epoch 1/10"
        mock_plan.model_holder.target_model.__name__ = "TestModel"
        mock_plan.get_training_repeat.return_value = 0

        # Mock get_plans
        mock_record = MagicMock()
        mock_record.repeat = 0
        mock_record.is_finished.return_value = False
        mock_record.get_epoch.return_value = 1
        mock_record.train = {
            "loss": [0.5],
            "accuracy": [0.8],
            "auc": [0.9],
            "lr": [0.001],
        }
        mock_record.val = {"loss": [0.6], "accuracy": [0.75], "auc": [0.85]}
        mock_plan.get_plans.return_value = [mock_record]
        mock_plan.option.epoch = 10

        study.trainer = mock_trainer

        panel.update_loop()

        assert panel.history_table.rowCount() == 1

        def cell_text(column: int) -> str:
            item = panel.history_table.item(0, column)
            assert item is not None
            return item.text()

        assert cell_text(0) == "Group 1"
        assert cell_text(1) == "1"
        assert cell_text(2) == "TestModel"
        assert cell_text(3) == "Running"
        assert cell_text(4) == "1/10"
        assert cell_text(5) == "0.5000"
        assert cell_text(6) == "0.80%"
        assert cell_text(7) == "0.6000"
        assert cell_text(8) == "0.75%"
        assert cell_text(9) == "0.001000"


class TestEvaluationPanelIntegration:
    """Test that evaluation panel works with trained models."""

    def test_evaluation_panel_with_no_trainer(self, qtbot):
        """Verify evaluation panel handles missing trainer gracefully."""

        study = Study()
        # No trainer set

        parent = cast(Any, QWidget())
        parent.study = study

        panel = EvaluationPanel(parent=parent)
        qtbot.addWidget(panel)

        # Verify panel state when no trainer
        panel.update_panel()
        assert panel.last_application_query is not None
        assert panel.last_application_query.failed
        assert (
            panel.last_application_query.message
            == "Create a training plan before evaluating results."
        )
        assert (
            panel.last_application_query.diagnostics.get("exception_type")
            == "PreconditionError"
        )
        assert panel.model_combo.count() == 1
        assert panel.model_combo.currentText() == "No Data Available"
        assert panel.run_combo.count() == 0

    def test_evaluation_panel_with_unfinished_trainer_shows_unavailable_state(
        self,
        qtbot,
    ):
        """Verify unfinished trainer data does not render as evaluation success."""

        study = Study()

        # Mock trainer with plan holders that have proper methods
        mock_trainer = MagicMock()
        mock_plan = MagicMock()
        mock_plan.get_name.return_value = "TestPlan"

        # Configure plan properties needed by EvaluationController.get_model_summary_str
        mock_plan.dataset.get_training_data.return_value = (
            torch.randn(4, 1, 20, 100),
            None,
        )
        mock_plan.dataset.get_epoch_data().get_model_args.return_value = {}
        mock_plan.model_holder.get_model.return_value = MagicMock()
        mock_plan.option.bs = 4
        mock_plan.option.get_device.return_value = "cpu"

        mock_trainer.training_plan_holders = [mock_plan]
        mock_trainer.get_training_plan_holders.return_value = [mock_plan]
        study.trainer = mock_trainer

        parent = cast(Any, QWidget())
        parent.study = study

        # The important thing is that service-backed evaluation state owns display.
        panel = EvaluationPanel(parent=parent)
        qtbot.addWidget(panel)

        panel.update_panel()
        assert panel.last_application_query is not None
        assert panel.last_application_query.ok
        diagnostics = panel.last_application_query.diagnostics
        assert diagnostics.get("payload_type") == "evaluation_summary"
        assert diagnostics.get("available") is False
        assert diagnostics.get("plan_count") == 1
        assert diagnostics.get("finished_run_count") == 0
        assert panel.model_combo.count() == 1
        assert panel.model_combo.currentText() == "No Data Available"
        assert panel.run_combo.count() == 0


class TestVisualizationPanelIntegration:
    """Test that visualization panel works correctly."""

    def test_visualization_panel_initialization(self, qtbot):
        """Verify visualization panel initializes without errors."""

        study = Study()

        parent = cast(Any, QWidget())
        parent.study = study

        panel = VisualizationPanel(parent=parent)
        qtbot.addWidget(panel)

        assert isinstance(panel, VisualizationPanel)


class TestTrainingWorkflowWithUI:
    """Test complete training workflow including UI updates."""

    def test_progress_bar_calculation_with_string_epoch(self, qtbot):
        """Test that progress bar works even if epoch types are mixed."""

        service = ApplicationService()
        study = service.study
        configure_result = service.execute(
            ConfigureTrainingCommand(
                output_dir="./test_output",
                device="cpu",
                epoch=_ui_text("10"),
                batch_size=_ui_text("4"),
                learning_rate=_ui_text("0.001"),
                save_checkpoints_every=_ui_text("1"),
                evaluation_option="test_acc",
                repeat=_ui_text("1"),
            ),
        )
        assert configure_result.ok is True

        query_result = service.execute(QueryStateCommand(query="state"))
        assert query_result.ok is True
        training_option = query_result.diagnostics["state"]["training"][
            "training_option"
        ]
        assert isinstance(training_option["epoch"], int)
        assert training_option["epoch"] == 10

        # Create panel
        parent = cast(Any, QWidget())
        parent.study = study
        panel = TrainingPanel(parent=parent)
        qtbot.addWidget(panel)

        # Simulate update with epoch from trainer
        mock_trainer = MagicMock()
        mock_plan = MagicMock()
        mock_plan.get_training_epoch.return_value = 5
        mock_plan.get_training_status.return_value = "Running"
        mock_plan.get_training_evaluation.return_value = (
            0.001,
            0.5,
            0.8,
            0.9,
            0.6,
            0.75,
            0.85,
        )
        mock_trainer.get_training_plan_holders.return_value = [mock_plan]
        mock_trainer.is_running.return_value = True
        mock_trainer.current_idx = 0
        mock_trainer.get_progress_text.return_value = "Epoch 5/10"
        mock_plan.get_epoch_progress_text.return_value = "Epoch 5/10"
        mock_plan.model_holder.target_model.__name__ = "TestModel"
        mock_plan.get_training_repeat.return_value = 0

        # Mock get_plans
        mock_record = MagicMock()
        mock_record.repeat = 0
        mock_record.is_finished.return_value = False
        mock_record.get_epoch.return_value = 5
        mock_record.train = {
            "loss": [0.5],
            "accuracy": [0.8],
            "auc": [0.9],
            "lr": [0.001],
        }
        mock_record.val = {"loss": [0.6], "accuracy": [0.75], "auc": [0.85]}
        mock_plan.get_plans.return_value = [mock_record]
        mock_plan.option.epoch = 10
        study.trainer = mock_trainer

        # Update should work without type errors
        panel.update_loop()

        assert panel.history_table.rowCount() == 1
        status_item = panel.history_table.item(0, 3)
        assert status_item is not None
        assert status_item.text() == "Running"
        progress_item = panel.history_table.item(0, 4)
        assert progress_item is not None
        assert progress_item.text() == "5/10"

    def test_metric_tab_accumulates_history(self, qtbot):
        """Test that MetricTab correctly accumulates training history."""

        tab = MetricTab("Accuracy", color="#4CAF50")
        qtbot.addWidget(tab)

        # Simulate multiple epoch updates
        tab.update_plot(1, 0.7, 0.6)
        assert len(tab.epochs) == 1
        assert len(tab.train_vals) == 1
        assert len(tab.val_vals) == 1

        tab.update_plot(2, 0.75, 0.65)
        assert len(tab.epochs) == 2
        assert tab.epochs == [1, 2]
        assert tab.train_vals == [0.7, 0.75]
        assert tab.val_vals == [0.6, 0.65]

        # Clear should reset history completely
        tab.clear()
        assert len(tab.epochs) == 0, "Epochs should be cleared"
        assert len(tab.train_vals) == 0, "Train values should be cleared"
        assert len(tab.val_vals) == 0, "Val values should be cleared"

        # After clear, should be able to accumulate again
        tab.update_plot(1, 0.8, 0.7)
        assert len(tab.epochs) == 1
        assert tab.epochs == [1]

    def test_update_loop_handles_string_metrics(self, qtbot, real_training_option):
        """Test that update_loop handles string metrics from trainer correctly."""

        study = Study()
        study.set_training_option(real_training_option)
        model_holder = ModelHolder(SCCNet, {})
        study.set_model_holder(model_holder)

        parent = cast(Any, QWidget())
        parent.study = study

        panel = TrainingPanel(parent=parent)
        qtbot.addWidget(panel)

        # Mock trainer with STRING metrics (this was the bug)
        mock_trainer = MagicMock()
        mock_plan = MagicMock()
        mock_plan.get_training_epoch.return_value = 1
        mock_plan.get_training_status.return_value = "Running"
        # Return string values to simulate the actual bug
        mock_plan.get_training_evaluation.return_value = (
            "0.001",
            "0.5",
            "0.8",
            "0.9",
            "0.6",
            "0.75",
            "0.85",
        )

        mock_trainer.get_training_plan_holders.return_value = [mock_plan]
        mock_trainer.is_running.return_value = True
        mock_trainer.current_idx = 0
        mock_trainer.get_progress_text.return_value = "Training..."
        mock_plan.get_epoch_progress_text.return_value = "Epoch 1/10"
        mock_plan.model_holder.target_model.__name__ = "TestModel"
        mock_plan.get_best_performance.return_value = 0.75
        mock_plan.get_training_repeat.return_value = 0

        # Mock get_plans
        mock_record = MagicMock()
        mock_record.repeat = 0
        mock_record.is_finished.return_value = False
        mock_record.get_epoch.return_value = 1
        # Use string values in record to simulate the issue
        mock_record.train = {
            "loss": ["0.5"],
            "accuracy": ["0.8"],
            "auc": ["0.9"],
            "lr": ["0.001"],
        }
        mock_record.val = {"loss": ["0.6"], "accuracy": ["0.75"], "auc": ["0.85"]}
        mock_plan.get_plans.return_value = [mock_record]
        mock_plan.option.epoch = 10
        study.trainer = mock_trainer

        panel.update_loop()

        assert panel.tab_acc.epochs == [1]
        assert panel.tab_acc.train_vals == [0.8]
        assert panel.tab_acc.val_vals == [0.75]
        assert panel.tab_loss.epochs == [1]
        assert panel.tab_loss.train_vals == [0.5]
        assert panel.tab_loss.val_vals == [0.6]
        assert isinstance(panel.tab_acc.val_vals[0], float)

    def test_metric_tab_only_shows_one_point_initially(self, qtbot):
        """Test that plots show proper line progression, not just one point."""

        tab = MetricTab("Accuracy", color="#4CAF50")
        qtbot.addWidget(tab)

        # First epoch - should show one point
        tab.update_plot(1, 0.7, 0.6)
        assert len(tab.epochs) == 1

        # Second epoch - should now show a line
        tab.update_plot(2, 0.75, 0.65)
        assert len(tab.epochs) == 2

        # Third epoch - line should continue
        tab.update_plot(3, 0.78, 0.68)
        assert len(tab.epochs) == 3

        # Verify data is accumulated correctly
        assert tab.epochs == [1, 2, 3]
        assert len(tab.train_vals) == 3
        assert len(tab.val_vals) == 3
