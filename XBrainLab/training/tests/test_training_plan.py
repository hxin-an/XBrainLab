import time

import mne
import numpy as np
import pytest
import torch

from XBrainLab.dataset import (
    DatasetGenerator,
    DataSplitter,
    DataSplittingConfig,
    Epochs,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.load_data import Raw
from XBrainLab.training.option import TRAINING_EVALUATION
from XBrainLab.training.record import RecordKey
from XBrainLab.training.training_plan import (
    ModelHolder,
    TrainingOption,
    TrainingPlanHolder,
    TrainRecord,
)
from XBrainLab.utils import set_seed

CLASS_NUM = 4
ERROR_NUM = 3
SAMPLE_NUM = CLASS_NUM
REPEAT = 5
TOTAL_NUM = SAMPLE_NUM * REPEAT
BS = 2

class FakeModel(torch.nn.Module):
    def __init__(self, **kwargs):
        super().__init__()
        self.fc = torch.nn.Linear(CLASS_NUM, CLASS_NUM)
        self.my_state_dict = None

    def load_state_dict(self, state_dict):
        self.my_state_dict = state_dict

    def forward(self, x):
        x = self.fc(x)
        x = x.squeeze(1)
        return x


@pytest.fixture
def y():
    return np.arange(SAMPLE_NUM).repeat(REPEAT)

def _create_raw(y, subject, session):
    """
    X = [[[1, 0, 0, 0]],
         [[1, 0, 0, 0]],
         [[1, 0, 0, 0]],
          ...
         [[0, 0, 0, 1]]]
    y = [0, 0, 0, 0, 0, 1, ...]
    """
    events = np.zeros((TOTAL_NUM, 3), dtype=int)
    events[:, 0] = np.arange(CLASS_NUM * REPEAT)
    events[:, 2] = y.copy()

    ch_types = 'eeg'
    ch_names = ['C1']
    event_id = {'C1': 0, 'C2': 1, 'C3': 2, 'C4': 3}
    fs = 1
    info = mne.create_info(ch_names=ch_names,
                    sfreq=fs,
                    ch_types=ch_types)
    data = np.zeros((len(events), len(ch_names), CLASS_NUM))
    for idx, gt in enumerate(y):
        data[idx, 0, gt] = gt

    epochs = mne.EpochsArray(data, info, events=events, tmin=0, event_id=event_id)
    raw = Raw(f"test/sub-{subject}_ses-{session}.fif", epochs)
    raw.set_subject_name(subject)
    raw.set_session_name(session)
    return raw

@pytest.fixture
def preprocessed_data_list(y):
    return [_create_raw(y, '01', '01'),
            _create_raw(y, '02', '01'),
            _create_raw(y, '03', '01')
    ]

@pytest.fixture
def epochs(preprocessed_data_list):
    return Epochs(preprocessed_data_list)

@pytest.fixture
def dataset(epochs):
    test_split_list = [
        DataSplitter(SplitByType.SUBJECT, '1', SplitUnit.NUMBER, True)
    ]
    val_split_list = [
        DataSplitter(ValSplitByType.SUBJECT, '1', SplitUnit.NUMBER, True)
    ]
    config = DataSplittingConfig(
        TrainingType.FULL, False, val_split_list, test_split_list
    )
    generator = DatasetGenerator(epochs, config)
    dataset = generator.generate()[0]
    return dataset

@pytest.fixture
def model_holder():
    args = {}
    path = None
    return ModelHolder(FakeModel, args, path)

@pytest.fixture
def training_option():
    args = {
        'output_dir': 'ok',
        'optim': torch.optim.Adam,
        'optim_params': {},
        'use_cpu': True,
        'gpu_idx': None,
        'epoch': 10,
        'bs': BS,
        'lr': 0.01,
        'checkpoint_epoch': 2,
        'evaluation_option': TRAINING_EVALUATION.VAL_LOSS,
        'repeat_num': 5
    }
    return TrainingOption(**args)

@pytest.fixture
def export_mocker():
    from unittest.mock import patch
    with patch('torch.save') as mock_save, \
         patch('os.makedirs') as mock_makedirs:
        yield mock_save, mock_makedirs

@pytest.fixture
def base_holder(export_mocker, model_holder, dataset, training_option):
    args = {
        'model_holder': model_holder,
        'dataset': dataset,
        'option': training_option,
        'saliency_params': {}
    }
    return TrainingPlanHolder(**args)



@pytest.mark.parametrize("test_arg", [
    'model_holder', 'dataset', 'option', 'saliency_params', None
])
def test_training_plan_holder_check_data(
    export_mocker, model_holder, dataset, training_option, test_arg
):
    args = {
        'model_holder': model_holder,
        'dataset': dataset,
        'option': training_option,
        'saliency_params': {}
    }
    if test_arg is None:
        holder = TrainingPlanHolder(**args)
        assert len(holder.train_record_list) == REPEAT
        for record in holder.train_record_list:
            assert isinstance(record, TrainRecord)
    else:
        args[test_arg] = None
        if test_arg == 'saliency_params':
            pass
        else:
            with pytest.raises(ValueError):
                TrainingPlanHolder(**args)

def test_training_plan_holder_get_loader(base_holder):
    set_seed(0)
    trainHolder, valHolder, testHolder = base_holder.get_loader()
    assert isinstance(trainHolder, torch.utils.data.DataLoader)
    assert isinstance(valHolder, torch.utils.data.DataLoader)
    assert isinstance(testHolder, torch.utils.data.DataLoader)

    train_data = next(iter(trainHolder))
    assert train_data[0].shape == (BS, 1, CLASS_NUM)
    assert train_data[1].shape == (BS,)
    val_data = next(iter(valHolder))
    assert val_data[0].shape == (BS, 1, CLASS_NUM)
    assert val_data[1].shape == (BS,)
    test_data = next(iter(testHolder))
    assert test_data[0].shape == (BS, 1, CLASS_NUM)
    assert test_data[1].shape == (BS,)

    torch.testing.assert_close(test_data[0], val_data[0])
    torch.testing.assert_close(test_data[1], val_data[1])
    with pytest.raises(AssertionError):
        torch.testing.assert_close(test_data[0], train_data[0])
    with pytest.raises(AssertionError):
        torch.testing.assert_close(test_data[1], train_data[1])

@pytest.mark.parametrize("val_loader, test_loader, expected_loader", [
    ('val', 'test', 'test'),
    (None, 'test', 'test'),
    ('val', None, 'val'),
    (None, None, None),
])
def test_training_plan_holder_get_eval_loader(
    base_holder, dataset, model_holder, training_option,
    val_loader, test_loader, expected_loader
):
    repeat = 0
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = TRAINING_EVALUATION.VAL_LOSS
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )

    _, target_loader = base_holder.get_eval_pair(record, val_loader, test_loader)
    assert target_loader == expected_loader

@pytest.mark.parametrize("evaluation_option, state_dict_attr_name", [
    (TRAINING_EVALUATION.VAL_LOSS, f'best_val_{RecordKey.LOSS}_model'),
    (TRAINING_EVALUATION.VAL_LOSS, f'best_val_{RecordKey.LOSS}_model'),
    (TRAINING_EVALUATION.TEST_AUC, f'best_test_{RecordKey.AUC}_model'),
    (TRAINING_EVALUATION.TEST_AUC, f'best_test_{RecordKey.AUC}_model'),
    (TRAINING_EVALUATION.TEST_ACC, f'best_test_{RecordKey.ACC}_model'),
    (TRAINING_EVALUATION.TEST_ACC, f'best_test_{RecordKey.ACC}_model'),
])
@pytest.mark.parametrize("expected", ['test', None])
def test_training_plan_holder_get_eval_model(
    base_holder, dataset, model_holder, training_option,
    evaluation_option, state_dict_attr_name, expected
):
    repeat = 0
    val_loader = None
    test_loader = None
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = evaluation_option
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )
    if expected:
        expected = np.random.rand(1)
    setattr(record, state_dict_attr_name, expected)

    target_model, _ = base_holder.get_eval_pair(record, val_loader, test_loader)
    if expected:
        assert isinstance(target_model, FakeModel)
        assert target_model.my_state_dict == expected
    else:
        assert target_model is None

@pytest.mark.parametrize("val_loader, test_loader, expected_loader", [
    ('val', 'test', 'test'),
    (None, 'test', 'test'),
    ('val', None, 'val'),
    (None, None, None),
])
@pytest.mark.parametrize("evaluation_option", [*list(TRAINING_EVALUATION), None])
def test_training_plan_holder_get_eval_pair_not_implemented(
    base_holder, dataset, model_holder, training_option,
    val_loader, test_loader, expected_loader, evaluation_option
):
    repeat = 0
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = evaluation_option
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )

    if evaluation_option:
        _, target_loader = base_holder.get_eval_pair(record, val_loader, test_loader)
        assert target_loader == expected_loader
    else:
        with pytest.raises(NotImplementedError):
            base_holder.get_eval_pair(record, val_loader, test_loader)

def test_training_plan_holder_get_eval_model_by_lastest_model(
    base_holder, dataset, model_holder, training_option
):
    from unittest.mock import patch
    repeat = 0
    val_loader = None
    test_loader = None
    seed = set_seed()
    model = model_holder.get_model({})
    
    with patch.object(model, 'state_dict', return_value='test'):
        training_option.evaluation_option = TRAINING_EVALUATION.LAST_EPOCH
        record = TrainRecord(
            repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
        )

        target_model, _ = base_holder.get_eval_pair(record, val_loader, test_loader)

        assert isinstance(target_model, FakeModel)
        assert target_model.my_state_dict == 'test'

def test_training_plan_holder_set_interrupt(base_holder):
    assert base_holder.interrupt is False
    base_holder.set_interrupt()
    assert base_holder.interrupt
    base_holder.clear_interrupt()
    assert base_holder.interrupt is False

def test_training_plan_holder_trivial_getter(base_holder, dataset):
    assert base_holder.get_name() == "0-Group_0"
    assert base_holder.get_dataset() == dataset
    assert len(base_holder.get_plans()) == REPEAT

@pytest.mark.timeout(10)
@pytest.mark.parametrize("interrupt", [True, False])
def test_training_plan_holder_one_epoch(base_holder, interrupt):
    from unittest.mock import patch
    model = base_holder.model_holder.get_model({})
    trainLoader, valLoader, testLoader = base_holder.get_loader()
    train_record = base_holder.train_record_list[0]
    optimizer = train_record.optim
    criterion = train_record.criterion

    fake_test_result = {'test': 'test'}
    
    with patch.object(train_record, 'update_train') as update_train_mock, \
         patch.object(train_record, 'update_eval') as update_val_mock, \
         patch.object(train_record, 'update_test') as update_test_mock, \
         patch.object(train_record, 'update_statistic') as update_statistic_mock, \
         patch.object(train_record, 'export_checkpoint') as export_checkpoint_mock, \
         patch('XBrainLab.training.training_plan._test_model', return_value=fake_test_result):
        
        if interrupt:
            base_holder.set_interrupt()

        start_time = time.time()
        base_holder.train_one_epoch(
            model, trainLoader, valLoader, testLoader, optimizer, criterion, train_record
        )
        total_time = time.time() - start_time

        if interrupt:
            assert update_train_mock.call_count == 0
            assert update_val_mock.call_count == 0
            assert update_test_mock.call_count == 0
            assert update_statistic_mock.call_count == 0
            assert export_checkpoint_mock.call_count == 0
            return

        update_train_mock.assert_called_once()
        update_val_mock.assert_called_once()
        update_test_mock.assert_called_once()
        update_statistic_mock.assert_called_once()
        export_checkpoint_mock.assert_not_called()

        step_called_args = update_statistic_mock.call_args[0]
        assert (step_called_args[0]["time"]  - total_time) < 0.1
        assert step_called_args[0]["lr"] == 0.01

        update_val_called_args = update_val_mock.call_args[0][0]
        assert update_val_called_args == fake_test_result

        update_test_called_args = update_test_mock.call_args[0][0]
        assert update_test_called_args == fake_test_result

        base_holder.train_one_epoch(
            model, trainLoader, valLoader, testLoader, optimizer, criterion, train_record
        )
        export_checkpoint_mock.assert_called_once()

@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat(base_holder):
    from unittest.mock import patch
    train_record = base_holder.train_record_list[0]

    def set_interrupt(*args, **kwargs):
        base_holder.set_interrupt()
    
    with patch.object(base_holder, 'train_one_epoch', side_effect=set_interrupt) as train_one_epoch_mock, \
         patch.object(train_record, 'export_checkpoint') as export_checkpoint_mock:

        base_holder.train_one_repeat(train_record)

        train_one_epoch_mock.assert_called_once()
        export_checkpoint_mock.assert_called_once()

# check status
@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_status(base_holder):
    from unittest.mock import patch
    original_train_one_epoch = base_holder.train_one_epoch
    epoch_counter = 0
    def train_one_epoch_side_effect(*args, **kwargs):
        nonlocal epoch_counter
        assert base_holder.get_training_status().startswith("Training")
        assert base_holder.get_training_epoch() == epoch_counter
        assert base_holder.get_epoch_progress_text() == str(epoch_counter) + " / 50"
        assert base_holder.is_finished() is False
        original_train_one_epoch(*args, **kwargs)
        epoch_counter += 1
        assert base_holder.get_training_epoch() == epoch_counter
        assert base_holder.get_epoch_progress_text() == str(epoch_counter) + " / 50"
        for i in base_holder.get_training_evaluation():
            assert i != "-"
    
    with patch.object(base_holder, 'train_one_epoch', side_effect=train_one_epoch_side_effect) as train_one_epoch_mock:
        train_record = base_holder.train_record_list[0]
        for i in base_holder.get_training_evaluation():
            assert i == "-"
        base_holder.train_one_repeat(train_record)


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_empty_training_data(
    base_holder
):
    from unittest.mock import patch
    train_record = base_holder.train_record_list[0]
    with patch.object(base_holder, 'get_loader', return_value=(None, None, None)):
        with pytest.raises(ValueError):
            base_holder.train_one_repeat(train_record)


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_eval(base_holder):
    from unittest.mock import patch
    train_record = base_holder.train_record_list[0]

    with patch.object(train_record, 'set_eval_record') as set_eval_record_mock:
        base_holder.train_one_repeat(train_record)

        set_eval_record_mock.assert_called_once()

@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_already_finished(base_holder):
    from unittest.mock import patch
    train_record = base_holder.train_record_list[0]

    with patch.object(train_record, 'is_finished', return_value=True), \
         patch.object(base_holder, 'train_one_epoch') as train_one_epoch_mock, \
         patch.object(train_record, 'export_checkpoint') as export_checkpoint_mock, \
         patch.object(train_record, 'set_eval_record') as set_eval_record_mock:

        base_holder.train_one_repeat(train_record)
        assert train_one_epoch_mock.call_count == 0
        assert export_checkpoint_mock.call_count == 0
        assert set_eval_record_mock.call_count == 0

@pytest.mark.timeout(10)
def test_training_plan_holder_train(base_holder):
    from unittest.mock import patch
    original_train_one_repeat = base_holder.train_one_repeat

    repeat_counter = 0
    def train_one_repeat_side_effect(*args, **kwargs):
        nonlocal repeat_counter
        assert base_holder.get_training_status().startswith("Initializing")
        assert base_holder.get_training_repeat() == repeat_counter
        assert base_holder.is_finished() is False
        original_train_one_repeat(*args, **kwargs)
        repeat_counter += 1

    original_get_eval_record = base_holder.get_eval_pair
    def get_eval_pair_side_effect(*args, **kwargs):
        assert base_holder.get_training_status().startswith("Evaluating")
        return original_get_eval_record(*args, **kwargs)

    with patch.object(base_holder, 'train_one_repeat', side_effect=train_one_repeat_side_effect) as train_one_repeat_mock, \
         patch.object(base_holder, 'get_eval_pair', side_effect=get_eval_pair_side_effect) as get_eval_pair_mock:

        assert base_holder.get_training_status() == "Pending"
        assert base_holder.is_finished() is False
        assert base_holder.get_training_repeat() == 0
        assert base_holder.get_training_epoch() == 0
        for i in base_holder.get_training_evaluation():
            assert i == "-"
        assert base_holder.get_epoch_progress_text() == "0 / 50"
        base_holder.train()
        assert base_holder.get_training_status() == "Finished"
        assert base_holder.is_finished()
        assert base_holder.get_training_repeat() == 4
        assert base_holder.get_training_epoch() == 10
        for i in base_holder.get_training_evaluation():
            assert i != "-"
        assert base_holder.get_epoch_progress_text() == "50 / 50"
        train_one_repeat_mock.assert_called()
        get_eval_pair_mock.assert_called()

@pytest.mark.timeout(10)
def test_training_plan_holder_train_status(base_holder):
    from unittest.mock import patch
    original_train_one_repeat = base_holder.train_one_repeat
    
    def train_one_repeat_side_effect(*args, **kwargs):
        base_holder.set_interrupt()
        original_train_one_repeat(*args, **kwargs)
    
    with patch.object(base_holder, 'train_one_repeat', side_effect=train_one_repeat_side_effect) as train_one_repeat_mock:
        base_holder.train()
        assert base_holder.is_finished() is False
        assert base_holder.get_training_status() == "Pending"
        train_one_repeat_mock.assert_called()

@pytest.mark.timeout(10)
def test_training_plan_holder_train_error(base_holder):
    from unittest.mock import patch
    def train_one_repeat_side_effect(*args, **kwargs):
        raise RuntimeError("test")
    
    with patch.object(base_holder, 'train_one_repeat', side_effect=train_one_repeat_side_effect) as train_one_repeat_mock:
        base_holder.train()
        assert base_holder.is_finished() is False
        assert base_holder.get_training_status() == "test"
        train_one_repeat_mock.assert_called()

def test_test_model_metrics():
    from XBrainLab.training.training_plan import _test_model
    
    # Setup
    model = FakeModel()
    criterion = torch.nn.CrossEntropyLoss()
    
    # Create dummy data
    # 2 batches, batch size 2
    # Batch 1: 
    #   Input: random
    #   Labels: [0, 1]
    #   Preds: [[10, 0, 0, 0], [0, 10, 0, 0]] -> Argmax: [0, 1] (Correct)
    # Batch 2:
    #   Input: random
    #   Labels: [2, 3]
    #   Preds: [[0, 0, 10, 0], [0, 10, 0, 0]] -> Argmax: [2, 1] (1 Correct, 1 Wrong)
    
    # Total: 4 samples, 3 correct -> Acc = 75%
    
    class MockDataset(torch.utils.data.Dataset):
        def __len__(self):
            return 4
        def __getitem__(self, idx):
            return torch.randn(CLASS_NUM), torch.tensor(idx)

    # Mock model output
    # We need to mock the model call to return specific predictions
    # But FakeModel is simple linear. Let's just mock the forward pass or use specific weights.
    # Easier: Mock the model object itself to return specific outputs
    
    mock_model = torch.nn.Linear(4, 4) # Dummy
    
    # Batch 1 outputs (indices 0, 1) -> Labels 0, 1
    out1 = torch.tensor([[10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0]])
    # Batch 2 outputs (indices 2, 3) -> Labels 2, 3
    out2 = torch.tensor([[0.0, 0.0, 10.0, 0.0], [0.0, 10.0, 0.0, 0.0]]) # Last one wrong (pred 1, label 3)
    
    from unittest.mock import Mock
    mock_model = Mock()
    mock_model.eval.return_value = None
    mock_model.side_effect = [out1, out2]
    
    # DataLoader
    # We need a dataloader that yields 2 batches
    # Inputs don't matter as we mock model output
    inputs = torch.randn(2, 4)
    labels1 = torch.tensor([0, 1])
    labels2 = torch.tensor([2, 3])
    
    loader = [(inputs, labels1), (inputs, labels2)]
    
    # Run
    result = _test_model(mock_model, loader, criterion)
    
    assert result[RecordKey.ACC] == 75.0
    assert RecordKey.AUC in result
    assert RecordKey.LOSS in result

def test_training_plan_holder_init_error(base_holder, model_holder, dataset, training_option):
    from unittest.mock import patch
    
    # Mock model_holder.get_model to raise RuntimeError
    with patch.object(model_holder, 'get_model', side_effect=RuntimeError("Given input size: (16x1x1). Calculated output size: (16x1x0). Output size is too small")):
        args = {
            'model_holder': model_holder,
            'dataset': dataset,
            'option': training_option,
            'saliency_params': {}
        }
        
        # Should raise ValueError with specific message (now includes model name)
        with pytest.raises(ValueError, match="Failed to create model.*Output size is too small"):
            TrainingPlanHolder(**args)
            
    # Verify other RuntimeErrors are re-raised
    with patch.object(model_holder, 'get_model', side_effect=RuntimeError("Other error")):
        with pytest.raises(RuntimeError, match="Other error"):
            TrainingPlanHolder(**args)
