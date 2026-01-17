from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from XBrainLab.backend.controller.evaluation_controller import EvaluationController


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.trainer = MagicMock()
    return study


@pytest.fixture
def controller(mock_study):
    return EvaluationController(mock_study)


def test_get_plans(controller, mock_study):
    # Case 1: Trainer exists
    plans = [MagicMock()]
    mock_study.trainer.get_training_plan_holders.return_value = plans
    assert controller.get_plans() == plans

    # Case 2: No trainer
    mock_study.trainer = None
    assert controller.get_plans() == []


def test_get_pooled_eval_result_empty(controller, mock_study):
    plan = MagicMock()
    plan.get_plans.return_value = []  # No records

    labels, o, m = controller.get_pooled_eval_result(plan)
    assert labels is None
    assert o is None
    assert m == {}


def test_get_pooled_eval_result_success(controller, mock_study):
    # Setup records
    r1 = MagicMock()
    r1.is_finished.return_value = True
    r1.eval_record.label = np.array([0, 1])
    r1.eval_record.output = np.array([[0.9, 0.1], [0.1, 0.9]])

    r2 = MagicMock()
    r2.is_finished.return_value = True
    r2.eval_record.label = np.array([1, 0])
    r2.eval_record.output = np.array([[0.2, 0.8], [0.8, 0.2]])

    plan = MagicMock()
    plan.get_plans.return_value = [r1, r2]

    # Needs to mock EvalRecord inside the controller logic
    # The controller does: temp_record = EvalRecord(...)
    with patch(
        "XBrainLab.backend.controller.evaluation_controller.EvalRecord"
    ) as MockRecord:
        instance = MockRecord.return_value
        instance.get_per_class_metrics.return_value = {"acc": 0.9}

        labels, outputs, metrics = controller.get_pooled_eval_result(plan)

        # Check concatenation happened
        assert len(labels) == 4
        assert len(outputs) == 4
        assert metrics == {"acc": 0.9}

        # Verify call to EvalRecord
        # Should have concatenated arrays
        args = MockRecord.call_args[0]
        assert np.array_equal(args[0], np.array([0, 1, 1, 0]))


def test_get_model_summary_str_from_record(controller):
    plan = MagicMock()
    record = MagicMock()
    record.model = MagicMock()
    record.get_name.return_value = "Run 1"

    with patch(
        "XBrainLab.backend.controller.evaluation_controller.summary"
    ) as mock_summary:
        mock_summary.return_value = "Model Summary"

        # Setup dataset shape
        plan.dataset.get_training_data.return_value = (np.zeros((10, 1, 100)), None)
        plan.option.bs = 32

        s = controller.get_model_summary_str(plan, record)
        assert "=== Run: Run 1 ===" in s
        assert "Model Summary" in s


def test_get_model_summary_str_new_model(controller):
    plan = MagicMock()
    plan.dataset.get_epoch_data().get_model_args.return_value = {}
    plan.dataset.get_training_data.return_value = (np.zeros((10, 1, 100)), None)

    mock_model = MagicMock()
    plan.model_holder.get_model.return_value = mock_model

    with patch(
        "XBrainLab.backend.controller.evaluation_controller.summary"
    ) as mock_summary:
        mock_summary.return_value = "Fresh Model"

        s = controller.get_model_summary_str(plan, None)
        assert "Fresh Model" in s
        assert "=== Run:" not in s


def test_get_model_summary_error(controller):
    plan = MagicMock()
    plan.dataset.get_training_data.side_effect = Exception("Shape error")

    s = controller.get_model_summary_str(plan)
    assert "Error generating summary" in s
    assert "Shape error" in s
