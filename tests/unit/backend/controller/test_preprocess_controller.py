
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.controller.preprocess_controller import PreprocessController


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.preprocessed_data_list = []
    study.reset_preprocess = MagicMock()
    study.set_preprocessed_data_list = MagicMock()
    study.lock_dataset = MagicMock()
    return study

@pytest.fixture
def controller(mock_study):
    return PreprocessController(mock_study)

def test_init_and_properties(controller, mock_study):
    # Setup
    d1 = MagicMock()
    d1.get_mne.return_value.ch_names = ['C3', 'C4']
    d1.is_raw.return_value = True

    # Test empty
    assert controller.get_preprocessed_data_list() == []
    assert controller.has_data() is False
    assert controller.get_channel_names() == []
    assert controller.get_first_data() is None
    assert controller.is_epoched() is False

    # Test populated
    mock_study.preprocessed_data_list = [d1]
    assert controller.has_data() is True
    assert controller.get_channel_names() == ['C3', 'C4']
    assert controller.get_first_data() == d1
    assert controller.is_epoched() is False # is_raw is True

    # Test epoched state
    d1.is_raw.return_value = False
    assert controller.is_epoched() is True

def test_reset_preprocess(controller, mock_study):
    controller.reset_preprocess()
    mock_study.reset_preprocess.assert_called_with(force_update=True)

def test_processor_helper_no_data(controller, mock_study):
    # Ensure empty
    mock_study.preprocessed_data_list = []
    with pytest.raises(ValueError, match="No data to preprocess"):
        controller.apply_filter(1, 40)

def test_apply_filter(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch('XBrainLab.backend.controller.preprocess_controller.Preprocessor.Filtering') as MockProc:
        instance = MockProc.return_value
        processed_data = [MagicMock()]
        instance.data_preprocess.return_value = processed_data

        result = controller.apply_filter(1.0, 40.0, [50.0])

        assert result is True
        instance.data_preprocess.assert_called_with(1.0, 40.0, notch_freqs=[50.0])
        mock_study.set_preprocessed_data_list.assert_called_with(processed_data)

def test_apply_resample(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch('XBrainLab.backend.controller.preprocess_controller.Preprocessor.Resample') as MockProc:
        instance = MockProc.return_value
        result = controller.apply_resample(256.0)

        assert result is True
        instance.data_preprocess.assert_called_with(256.0)

def test_apply_rereference(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch('XBrainLab.backend.controller.preprocess_controller.Preprocessor.Rereference') as MockProc:
        instance = MockProc.return_value
        result = controller.apply_rereference(['Cz'])

        assert result is True
        instance.data_preprocess.assert_called_with(ref_channels=['Cz'])

def test_apply_normalization(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch('XBrainLab.backend.controller.preprocess_controller.Preprocessor.Normalize') as MockProc:
        instance = MockProc.return_value
        result = controller.apply_normalization('z-score')

        assert result is True
        instance.data_preprocess.assert_called_with(norm='z-score')

def test_apply_epoching_and_locking(controller, mock_study):
    mock_study.preprocessed_data_list = [MagicMock()]

    with patch('XBrainLab.backend.controller.preprocess_controller.Preprocessor.TimeEpoch') as MockProc:
        instance = MockProc.return_value
        instance.data_preprocess.return_value = [MagicMock()] # Success

        result = controller.apply_epoching(None, ['Event1'], -0.2, 0.5)

        assert result is True
        instance.data_preprocess.assert_called_with(None, ['Event1'], -0.2, 0.5)
        # Verify dataset is locked
        mock_study.lock_dataset.assert_called_once()

def test_get_unique_events(controller, mock_study):
    d1 = MagicMock()
    d1.get_event_list.return_value = (None, {'EventA': 1, 'EventB': 2})
    d2 = MagicMock()
    d2.get_event_list.return_value = (None, {'EventB': 2, 'EventC': 3})
    d3 = MagicMock()
    d3.get_event_list.side_effect = Exception("No events")

    mock_study.preprocessed_data_list = [d1, d2, d3]

    events = controller.get_unique_events()
    assert events == ['EventA', 'EventB', 'EventC']
