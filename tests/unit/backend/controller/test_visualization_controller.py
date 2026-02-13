from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from XBrainLab.backend.controller.visualization_controller import (
    VisualizationController,
)


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.trainer = MagicMock()
    study.epoch_data = MagicMock()
    return study


@pytest.fixture
def controller(mock_study):
    return VisualizationController(mock_study)


def test_get_trainers(controller, mock_study):
    # Case 1: Trainer exists
    plans = [MagicMock()]
    mock_study.trainer.get_training_plan_holders.return_value = plans
    assert controller.get_trainers() == plans

    # Case 2: No trainer
    mock_study.trainer = None
    assert controller.get_trainers() == []


def test_set_montage(controller, mock_study):
    chs = ["C3", "C4"]
    pos = [(0, 0, 0), (1, 1, 1)]
    controller.set_montage(chs, pos)
    mock_study.set_channels.assert_called_with(chs, pos)


def test_has_epoch_data(controller, mock_study):
    assert controller.has_epoch_data() is True
    mock_study.epoch_data = None
    assert controller.has_epoch_data() is False


def test_get_channel_names(controller, mock_study):
    mock_study.epoch_data.get_channel_names.return_value = ["C3"]
    assert controller.get_channel_names() == ["C3"]

    mock_study.epoch_data = None
    assert controller.get_channel_names() == []


def test_saliency_params(controller, mock_study):
    p = {"param": 1}
    mock_study.get_saliency_params.return_value = p
    assert controller.get_saliency_params() == p

    p2 = {"param": 2}
    controller.set_saliency_params(p2)
    mock_study.set_saliency_params.assert_called_with(p2)


def test_get_averaged_record(controller):
    holder = MagicMock()

    # R1: Valid record
    r1 = MagicMock()
    rec1 = MagicMock()
    rec1.label = np.array([0])
    rec1.output = np.array([[0.9]])
    rec1.gradient = {"pool": np.array([1.0])}
    rec1.gradient_input = {"pool": np.array([2.0])}
    rec1.smoothgrad = {"pool": np.array([3.0])}
    rec1.smoothgrad_sq = {"pool": np.array([4.0])}
    rec1.vargrad = {"pool": np.array([5.0])}
    r1.get_eval_record.return_value = rec1

    # R2: Valid record
    r2 = MagicMock()
    rec2 = MagicMock()
    rec2.gradient = {"pool": np.array([2.0])}  # Mean should be 1.5
    rec2.gradient_input = {"pool": np.array([4.0])}  # Mean 3.0
    rec2.smoothgrad = {"pool": np.array([3.0])}  # Mean 3.0
    rec2.smoothgrad_sq = {"pool": np.array([4.0])}
    rec2.vargrad = {"pool": np.array([5.0])}
    r2.get_eval_record.return_value = rec2

    # R3: Invalid record (None)
    r3 = MagicMock()
    r3.get_eval_record.return_value = None

    holder.get_plans.return_value = [r1, r2, r3]

    # Patch EvalRecord to check constructor call
    with patch(
        "XBrainLab.backend.controller.visualization_controller.EvalRecord"
    ) as MockRecord:
        controller.get_averaged_record(holder)

        args, kwargs = MockRecord.call_args
        # Args order: label, output, gradient, gradient_input, smoothgrad,
        # smoothgrad_sq, vargrad
        # Check gradient
        avg_grad = kwargs.get("gradient") or args[2]
        assert avg_grad["pool"] == 1.5

        avg_grad_input = kwargs.get("gradient_input") or args[3]
        assert avg_grad_input["pool"] == 3.0


def test_get_averaged_record_empty(controller):
    holder = MagicMock()
    holder.get_plans.return_value = []
    assert controller.get_averaged_record(holder) is None


def test_set_montage_observer(controller, mock_study):
    # Setup observer
    mock_callback = MagicMock()
    controller.subscribe("montage_changed", mock_callback)

    chs = ["C3", "C4"]
    pos = [(0, 0, 0), (1, 1, 1)]
    controller.set_montage(chs, pos)

    mock_study.set_channels.assert_called_with(chs, pos)
    mock_callback.assert_called_once()


def test_set_saliency_params_observer(controller, mock_study):
    # Setup observer
    mock_callback = MagicMock()
    controller.subscribe("saliency_changed", mock_callback)

    params = {"method": "grad"}
    controller.set_saliency_params(params)

    mock_study.set_saliency_params.assert_called_with(params)
    mock_callback.assert_called_once()


def test_get_preprocessed_data_list(controller, mock_study):
    mock_data = [MagicMock(), MagicMock()]
    mock_study.preprocessed_data_list = mock_data

    result = controller.get_preprocessed_data_list()
    assert result == mock_data

    # Test valid loaded data list
    mock_study.loaded_data_list = mock_data
    assert controller.get_loaded_data_list() == mock_data
