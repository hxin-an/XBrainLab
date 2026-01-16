"""Test to reproduce the epoch duration bug when generating training plan."""
from unittest.mock import Mock

import pytest
import torch

from XBrainLab.backend.dataset import Dataset, Epochs
from XBrainLab.backend.training import ModelHolder, TrainingOption, TrainingPlanHolder
from XBrainLab.backend.training.option import TRAINING_EVALUATION


def test_epoch_duration_too_short():
    """Test that generates the 'Epoch duration is too short' error.

    This test reproduces the bug: When samples are too few for model architecture.
    """
    from XBrainLab.backend.model_base import EEGNet

    # Create mock epoch data with very short duration
    mock_epoch = Mock(spec=Epochs)
    mock_epoch.get_model_args.return_value = {
        'n_classes': 10,
        'channels': 16,
        'samples': 1,  # Way too short!
        'sfreq': 250.0
    }

    # Create a mock dataset
    mock_dataset = Mock(spec=Dataset)
    mock_dataset.get_epoch_data.return_value = mock_epoch

    # Create model holder for EEGNet
    model_holder = ModelHolder(
        target_model=EEGNet,
        model_params_map={}
    )

    # Create training option
    training_option = TrainingOption(
        output_dir='./test_output',
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=32,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TRAINING_EVALUATION.LAST_EPOCH,
        repeat_num=1
    )

    # Try to create training plan - should raise ValueError with clear message
    with pytest.raises(ValueError) as excinfo:
        TrainingPlanHolder(model_holder, mock_dataset, training_option, None)

    # Verify the error message is helpful
    error_msg = str(excinfo.value)
    assert "Epoch duration is too short" in error_msg
    assert "EEGNet" in error_msg
    assert "samples" in error_msg
    print(f"✓ Test passed. Error message: {error_msg}")


def test_minimum_samples_required():
    """Test to verify minimum samples validation for each model."""
    from XBrainLab.backend.model_base import EEGNet, SCCNet, ShallowConvNet

    test_cases = [
        ('EEGNet', EEGNet, {'F1': 8, 'F2': 16, 'D': 2}),
        ('SCCNet', SCCNet, {'Ns': 22}),
        ('ShallowConvNet', ShallowConvNet, {'pool_len': 75, 'pool_stride': 15}),
    ]

    sfreq = 250.0
    channels = 16
    n_classes = 2

    for model_name, model_class, model_params in test_cases:
        print(f"\n=== Testing {model_name} ===")

        # Test with too few samples - should raise ValueError
        try:
            model = model_class(
                n_classes=n_classes,
                channels=channels,
                samples=1,  # Way too short
                sfreq=sfreq,
                **model_params
            )
            print(f"  ✗ {model_name} should have raised ValueError for samples=1")
            assert False, f"{model_name} did not validate minimum samples"
        except ValueError as e:
            error_msg = str(e)
            assert "Epoch duration is too short" in error_msg
            assert model_name in error_msg
            print(f"  ✓ {model_name} correctly raised ValueError: {error_msg[:100]}...")

        # Test with sufficient samples - should work
        test_samples = [128, 250, 500, 1000]
        for samples in test_samples:
            try:
                model = model_class(
                    n_classes=n_classes,
                    channels=channels,
                    samples=samples,
                    sfreq=sfreq,
                    **model_params
                )
                # Try forward pass
                x = torch.randn(2, 1, channels, samples)
                output = model(x)
                print(f"  ✓ {model_name} works with samples={samples}, output shape: {output.shape}")
                break
            except (RuntimeError, ValueError) as e:
                if "too short" in str(e).lower() or "too small" in str(e).lower():
                    continue
                raise


if __name__ == "__main__":
    print("=== Testing minimum sample requirements ===")
    test_minimum_samples_required()
    print("\n=== Testing epoch duration bug ===")
    test_epoch_duration_too_short()
