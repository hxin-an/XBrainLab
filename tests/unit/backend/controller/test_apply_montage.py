from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.controller.preprocess_controller import PreprocessController


@pytest.fixture
def mock_study():
    return MagicMock()


@pytest.fixture
def controller(mock_study):
    return PreprocessController(mock_study)


def test_apply_montage(controller, mock_study):
    """Test applying montage via controller delegates to study and notifies."""
    mapped_channels = ["Fp1", "Fp2"]
    mapped_positions = [(0, 1, 0), (0, 1, 0)]

    # Spy on notify
    with patch.object(controller, "notify") as mock_notify:
        success = controller.apply_montage(mapped_channels, mapped_positions)

        assert success is True
        # Check delegation
        mock_study.set_channels.assert_called_once_with(
            mapped_channels, mapped_positions
        )
        # Check notification
        mock_notify.assert_called_once_with("preprocess_changed")
