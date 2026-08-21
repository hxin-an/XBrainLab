import datetime
import time
from threading import Event
from unittest.mock import Mock, patch

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.dataset import (
    DatasetGenerator,
    DataSplitter,
    DataSplittingConfig,
    Epochs,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.exceptions import (
    SaliencyCancellationTimeoutError,
    StaleSaliencyUpdateError,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.option import TrainingEvaluation
from XBrainLab.backend.training.record import EvalRecord, RecordKey
from XBrainLab.backend.training.trainer import Trainer
from XBrainLab.backend.training.training_plan import (
    FinalEvaluationUnavailableError,
    ModelHolder,
    TrainingOption,
    TrainingPlanHolder,
    TrainRecord,
    publish_prepared_saliency_updates,
)
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    TrainingManager,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils import set_seed

CLASS_NUM = 4
ERROR_NUM = 3
SAMPLE_NUM = CLASS_NUM
REPEAT = 5
TOTAL_NUM = SAMPLE_NUM * REPEAT
BS = 2


def _prepared_saliency_record() -> Mock:
    """Return a contract-correct evaluator result for orchestration tests."""
    return Mock(spec=EvalRecord)


def _bind_selected_evaluation_checkpoint(base_holder, record) -> None:
    """Make a synthetic finished record satisfy the real checkpoint contract."""
    state = {
        name: value.detach().cpu().clone()
        for name, value in record.model.state_dict().items()
    }
    attribute = {
        TrainingEvaluation.VAL_LOSS: f"best_val_{RecordKey.LOSS}_model",
        TrainingEvaluation.VAL_ACC: f"best_val_{RecordKey.ACC}_model",
        TrainingEvaluation.VAL_AUC: f"best_val_{RecordKey.AUC}_model",
    }.get(base_holder.option.evaluation_option)
    if attribute is not None:
        setattr(record, attribute, state)


def _mark_process_local_evaluation_pause(record) -> None:
    """Represent completed in-memory training that still needs evaluation."""
    record.start_timestamp = 1.0
    record.end_timestamp = 2.0


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


class _FakeCudaTensor(torch.Tensor):
    """CPU-backed optimizer tensor that records a logical CUDA-to-CPU move."""

    @staticmethod
    def __new__(cls, value: torch.Tensor) -> "_FakeCudaTensor":
        return torch.Tensor._make_subclass(  # pyright: ignore[reportPrivateUsage]
            cls,
            value,
            value.requires_grad,
        )

    @property
    def device(self) -> torch.device:
        return torch.device("cuda")

    def to(self, *args, **kwargs) -> torch.Tensor:
        device = kwargs.get("device", args[0] if args else None)
        if device is not None and torch.device(device).type == "cpu":
            return self.as_subclass(torch.Tensor)
        return super().to(*args, **kwargs)


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

    ch_types = "eeg"
    ch_names = ["C1"]
    event_id = {"C1": 0, "C2": 1, "C3": 2, "C4": 3}
    fs = 1
    info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types=ch_types)
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
    return [
        _create_raw(y, "01", "01"),
        _create_raw(y, "02", "01"),
        _create_raw(y, "03", "01"),
    ]


@pytest.fixture
def epochs(preprocessed_data_list):
    return Epochs(preprocessed_data_list)


@pytest.fixture
def dataset(epochs):
    test_split_list = [DataSplitter(SplitByType.SUBJECT, "1", SplitUnit.NUMBER, True)]
    val_split_list = [DataSplitter(ValSplitByType.SUBJECT, "1", SplitUnit.NUMBER, True)]
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
def training_option(tmp_path):
    args = {
        "output_dir": str(tmp_path / "training-output"),
        "optim": torch.optim.Adam,
        "optim_params": {},
        "use_cpu": True,
        "gpu_idx": None,
        "epoch": 10,
        "bs": BS,
        "lr": 0.01,
        "checkpoint_epoch": 2,
        "evaluation_option": TrainingEvaluation.VAL_LOSS,
        "repeat_num": 5,
    }
    return TrainingOption(**args)


@pytest.fixture
def export_mocker():
    with patch("torch.save") as mock_save:
        yield mock_save


@pytest.fixture
def base_holder(export_mocker, model_holder, dataset, training_option):
    args = {
        "model_holder": model_holder,
        "dataset": dataset,
        "option": training_option,
        "saliency_params": {},
    }
    return TrainingPlanHolder(**args)


@pytest.mark.parametrize(
    "test_arg", ["model_holder", "dataset", "option", "saliency_params", None]
)
def test_training_plan_holder_check_data(
    export_mocker, model_holder, dataset, training_option, test_arg
):
    args = {
        "model_holder": model_holder,
        "dataset": dataset,
        "option": training_option,
        "saliency_params": {},
    }
    if test_arg is None:
        holder = TrainingPlanHolder(**args)
        assert len(holder.train_record_list) == REPEAT
        for record in holder.train_record_list:
            assert isinstance(record, TrainRecord)
    else:
        args[test_arg] = None
        if test_arg == "saliency_params":
            pass
        else:
            with pytest.raises(ValueError):
                TrainingPlanHolder(**args)


def test_training_plan_holder_rejects_nonfinite_epoch_data(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    dataset.get_epoch_data().data[0, 0, 0] = np.nan

    with pytest.raises(
        ValueError,
        match=(
            "Training dataset contains NaN or infinite values at epoch 0, "
            "channel 0, sample 0"
        ),
    ):
        TrainingPlanHolder(
            model_holder=model_holder,
            dataset=dataset,
            option=training_option,
            saliency_params={},
        )


def test_training_plan_fails_if_epoch_data_becomes_nonfinite_after_configuration(
    base_holder,
):
    base_holder.dataset.get_epoch_data().data[0, 0, 0] = np.inf

    base_holder.train()

    assert base_holder.error == (
        "Training dataset contains NaN or infinite values at epoch 0, channel 0, "
        "sample 0. Review channel selection and preprocessing before training."
    )
    assert all(not record.is_finished() for record in base_holder.get_plans())


def test_explicit_seed_derives_repeat_seeds_before_model_creation(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 3
    training_option.seed = 8128
    training_option.validate()

    first = TrainingPlanHolder(model_holder, dataset, training_option, {})
    second = TrainingPlanHolder(model_holder, dataset, training_option, {})

    assert [record.seed for record in first.get_plans()] == [8128, 8129, 8130]
    assert [record.seed for record in second.get_plans()] == [8128, 8129, 8130]
    for first_record, second_record in zip(
        first.get_plans(),
        second.get_plans(),
        strict=True,
    ):
        assert all(
            first_weight.equal(second_weight)
            for first_weight, second_weight in zip(
                first_record.model.state_dict().values(),
                second_record.model.state_dict().values(),
                strict=True,
            )
        )

    training_option.seed = 8129
    different = TrainingPlanHolder(model_holder, dataset, training_option, {})
    assert any(
        not first_weight.equal(different_weight)
        for first_weight, different_weight in zip(
            first.get_plans()[0].model.state_dict().values(),
            different.get_plans()[0].model.state_dict().values(),
            strict=True,
        )
    )


def test_explicit_repeat_seed_owns_each_data_loader_rng(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 2
    training_option.seed = 8128
    training_option.validate()
    holder = TrainingPlanHolder(model_holder, dataset, training_option, {})

    for repeat_index, record in enumerate(holder.get_plans()):
        expected_seed = 8128 + repeat_index
        train_loader, val_loader, test_loader = holder.get_loader(record)

        for loader in (train_loader, val_loader, test_loader):
            assert loader is not None
            assert loader.generator is not None
            assert loader.generator.initial_seed() == expected_seed

        expected_order = torch.randperm(
            len(train_loader.dataset),
            generator=torch.Generator().manual_seed(expected_seed),
        ).tolist()
        assert list(train_loader.sampler) == expected_order


def test_each_fresh_repeat_reapplies_seed_before_stochastic_training(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 2
    training_option.seed = 8128
    training_option.validate()
    holder = TrainingPlanHolder(model_holder, dataset, training_option, {})
    events = []
    expected_draws = {
        seed: torch.rand((), generator=torch.Generator().manual_seed(seed)).item()
        for seed in (8128, 8129)
    }

    def apply_seed(*, seed):
        events.append(("seed", seed))
        return set_seed(seed=seed)

    original_get_loader = holder.get_loader

    def observe_loader_creation(train_record):
        events.append(("loaders", train_record.repeat, torch.initial_seed()))
        return original_get_loader(train_record)

    def observe_training_start(*args):
        train_record = args[-1]
        events.append(
            (
                "train",
                train_record.repeat,
                torch.initial_seed(),
                torch.rand(()).item(),
            )
        )
        holder.set_interrupt()

    with (
        patch(
            "XBrainLab.backend.training.training_plan.set_seed",
            side_effect=apply_seed,
        ),
        patch.object(
            holder,
            "get_loader",
            side_effect=observe_loader_creation,
        ),
        patch.object(
            holder,
            "train_one_epoch",
            side_effect=observe_training_start,
        ),
    ):
        for record in reversed(holder.get_plans()):
            holder.clear_interrupt()
            holder.train_one_repeat(record)

    assert events == [
        ("seed", 8129),
        ("loaders", 1, 8129),
        ("train", 1, 8129, expected_draws[8129]),
        ("seed", 8128),
        ("loaders", 0, 8128),
        ("train", 0, 8128, expected_draws[8128]),
    ]


def test_process_local_partial_repeat_fails_closed_without_loader_rng_state(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 1
    training_option.seed = 8128
    training_option.validate()
    holder = TrainingPlanHolder(model_holder, dataset, training_option, {})
    record = holder.get_plans()[0]
    record.epoch = 1
    record.start_timestamp = 1.0
    record.end_timestamp = 2.0

    with (
        patch(
            "XBrainLab.backend.training.training_plan.set_seed",
            wraps=set_seed,
        ) as apply_seed,
        patch.object(record, "resume") as resume,
        patch.object(holder, "get_loader") as get_loader,
        patch.object(
            holder,
            "train_one_epoch",
            side_effect=AssertionError("stochastic training started"),
        ),
        pytest.raises(RuntimeError, match="cannot be resumed reproducibly"),
    ):
        holder.train_one_repeat(record)

    apply_seed.assert_not_called()
    resume.assert_not_called()
    get_loader.assert_not_called()
    assert record.end_timestamp == 2.0


def test_persisted_partial_repeat_fails_closed_without_optimizer_and_rng_state(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 1
    training_option.seed = 8128
    training_option.validate()
    holder = TrainingPlanHolder(model_holder, dataset, training_option, {})
    record = holder.get_plans()[0]
    record.epoch = 1
    record.start_timestamp = None
    record.end_timestamp = None

    with (
        patch.object(holder, "get_loader") as get_loader,
        patch.object(
            holder,
            "train_one_epoch",
            side_effect=AssertionError("stochastic training started"),
        ),
        pytest.raises(RuntimeError, match="cannot be resumed reproducibly"),
    ):
        holder.train_one_repeat(record)

    get_loader.assert_not_called()


def test_default_training_seed_resolves_one_base_for_all_repeats(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    training_option.repeat_num = 2

    with patch(
        "XBrainLab.backend.training.training_plan.set_seed",
        wraps=set_seed,
    ) as apply_seed:
        holder = TrainingPlanHolder(model_holder, dataset, training_option, {})

    assert type(training_option.seed) is int
    assert len(holder.get_plans()) == 2
    assert [record.seed for record in holder.get_plans()] == [
        training_option.seed,
        training_option.seed + 1,
    ]
    assert [item.kwargs["seed"] for item in apply_seed.call_args_list] == [
        training_option.seed,
        training_option.seed + 1,
    ]


def test_training_plan_holder_get_loader(base_holder):
    train_record = base_holder.get_plans()[0]
    trainHolder, valHolder, testHolder = base_holder.get_loader(train_record)
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

    np.testing.assert_array_equal(
        trainHolder.dataset.indices,
        np.where(base_holder.dataset.train_mask)[0],
    )
    np.testing.assert_array_equal(
        valHolder.dataset.indices,
        np.where(base_holder.dataset.val_mask)[0],
    )
    np.testing.assert_array_equal(
        testHolder.dataset.indices,
        np.where(base_holder.dataset.test_mask)[0],
    )
    assert isinstance(trainHolder.sampler, torch.utils.data.RandomSampler)
    assert isinstance(valHolder.sampler, torch.utils.data.SequentialSampler)
    assert isinstance(testHolder.sampler, torch.utils.data.SequentialSampler)


def test_training_plan_holder_keeps_saliency_empty_until_configured(
    export_mocker,
    model_holder,
    dataset,
    training_option,
):
    holder = TrainingPlanHolder(
        model_holder=model_holder,
        dataset=dataset,
        option=training_option,
        saliency_params=None,
    )

    assert holder.get_saliency_params() == {}


def test_saliency_producer_identity_is_stable_for_same_training_run(base_holder):
    record = base_holder.get_plans()[0]
    record.best_val_loss_model = record.model.state_dict()

    first = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    second = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )

    assert first == second
    assert first.fingerprint == second.fingerprint


def test_saliency_model_identity_includes_provider_and_revision(base_holder):
    record = base_holder.get_plans()[0]
    record.best_val_loss_model = record.model.state_dict()
    baseline = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    original_provider = base_holder.model_holder.provider
    original_revision = base_holder.model_holder.source_revision
    base_holder.model_holder.provider = "legacy-braindecode"
    base_holder.model_holder.source_revision = "braindecode==1.6.1+xbrainlab-reviewed"

    recovery = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )

    base_holder.model_holder.provider = original_provider
    base_holder.model_holder.source_revision = original_revision
    assert recovery.model_fingerprint != baseline.model_fingerprint
    assert recovery.dataset_fingerprint == baseline.dataset_fingerprint
    assert recovery.split_fingerprint == baseline.split_fingerprint


def test_saliency_producer_identity_separates_dataset_split_run_and_model(
    base_holder,
):
    record = base_holder.get_plans()[0]
    record.best_val_loss_model = record.model.state_dict()
    epoch_data = base_holder.dataset.get_epoch_data()
    baseline = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )

    original_value = float(epoch_data.data.flat[-1])
    epoch_data.data.flat[-1] = original_value + 1.0
    dataset_changed = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    epoch_data.data.flat[-1] = original_value

    original_test_mask = base_holder.dataset.test_mask.copy()
    base_holder.dataset.test_mask[0] = not base_holder.dataset.test_mask[0]
    split_changed = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    base_holder.dataset.test_mask = original_test_mask

    original_seed = record.seed
    record.seed = original_seed + 1
    run_changed = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    record.seed = original_seed

    with torch.no_grad():
        original_weight = record.model.fc.weight.flatten()[0].item()
        record.model.fc.weight.flatten()[0] = original_weight + 1.0
    model_state_changed = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    with torch.no_grad():
        record.model.fc.weight.flatten()[0] = original_weight

    original_model_holder = base_holder.model_holder
    base_holder.model_holder = ModelHolder(FakeModel, {"variant": 1})
    model_changed = base_holder.build_saliency_producer_identity(
        record,
        evaluation_split="test",
    )
    base_holder.model_holder = original_model_holder

    assert dataset_changed.dataset_fingerprint != baseline.dataset_fingerprint
    assert dataset_changed.split_fingerprint == baseline.split_fingerprint
    assert split_changed.dataset_fingerprint == baseline.dataset_fingerprint
    assert split_changed.split_fingerprint != baseline.split_fingerprint
    assert run_changed.run_fingerprint != baseline.run_fingerprint
    assert model_state_changed.model_fingerprint != baseline.model_fingerprint
    assert model_changed.model_fingerprint != baseline.model_fingerprint


@pytest.mark.parametrize(
    "val_loader, test_loader, expected_loader",
    [
        ("val", "test", "test"),
        (None, "test", "test"),
        ("val", None, "val"),
        (None, None, None),
    ],
)
def test_training_plan_holder_get_eval_loader(
    base_holder,
    dataset,
    model_holder,
    training_option,
    val_loader,
    test_loader,
    expected_loader,
):
    repeat = 0
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = TrainingEvaluation.VAL_LOSS
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )
    record.best_val_loss_model = record.model.state_dict()

    if expected_loader is None:
        with pytest.raises(FinalEvaluationUnavailableError):
            base_holder.get_eval_pair(record, val_loader, test_loader)
    else:
        _, target_loader = base_holder.get_eval_pair(record, val_loader, test_loader)
        assert target_loader == expected_loader


@pytest.mark.parametrize(
    "evaluation_option, state_dict_attr_name",
    [
        (TrainingEvaluation.VAL_LOSS, f"best_val_{RecordKey.LOSS}_model"),
        (TrainingEvaluation.VAL_AUC, f"best_val_{RecordKey.AUC}_model"),
        (TrainingEvaluation.VAL_ACC, f"best_val_{RecordKey.ACC}_model"),
    ],
)
@pytest.mark.parametrize("has_best_state", [True, False])
def test_training_plan_holder_get_eval_model(
    base_holder,
    dataset,
    model_holder,
    training_option,
    evaluation_option,
    state_dict_attr_name,
    has_best_state,
):
    repeat = 0
    val_loader = None
    test_loader = object()
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = evaluation_option
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )
    expected = np.random.rand(1) if has_best_state else None
    setattr(record, state_dict_attr_name, expected)

    if has_best_state:
        target_model, _ = base_holder.get_eval_pair(record, val_loader, test_loader)
        assert isinstance(target_model, FakeModel)
        assert target_model.my_state_dict == expected
    else:
        with pytest.raises(FinalEvaluationUnavailableError) as raised:
            base_holder.get_eval_pair(record, val_loader, test_loader)
        assert "selected validation checkpoint" in str(raised.value)


def test_train_one_repeat_does_not_evaluate_without_validation_checkpoint(
    base_holder,
):
    base_holder.option.evaluation_option = TrainingEvaluation.VAL_LOSS
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    _mark_process_local_evaluation_pause(record)
    record.eval_record = None
    record.best_val_loss_model = None

    with (
        patch.object(Evaluator, "evaluate") as evaluate,
        patch.object(record, "export_checkpoint") as export_checkpoint,
        pytest.raises(FinalEvaluationUnavailableError) as raised,
    ):
        base_holder.train_one_repeat(record)

    evaluate.assert_not_called()
    assert record.eval_record is None
    assert "selected validation checkpoint" in str(raised.value)
    export_checkpoint.assert_called_once()


def test_train_one_repeat_does_not_use_training_loader_for_final_evaluation(
    base_holder,
):
    base_holder.option.evaluation_option = TrainingEvaluation.LAST_EPOCH
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    _mark_process_local_evaluation_pause(record)
    record.eval_record = None
    base_holder.dataset.val_mask[:] = False
    base_holder.dataset.test_mask[:] = False

    with (
        patch.object(Evaluator, "evaluate") as evaluate,
        patch.object(record, "export_checkpoint") as export_checkpoint,
        pytest.raises(FinalEvaluationUnavailableError) as raised,
    ):
        base_holder.train_one_repeat(record)

    evaluate.assert_not_called()
    assert record.eval_record is None
    assert "no validation or test split" in str(raised.value)
    export_checkpoint.assert_called_once()


def test_training_plan_records_unavailable_final_evaluation_as_failure(base_holder):
    base_holder.option.repeat_num = 1
    base_holder.option.evaluation_option = TrainingEvaluation.LAST_EPOCH
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    _mark_process_local_evaluation_pause(record)
    base_holder.dataset.val_mask[:] = False
    base_holder.dataset.test_mask[:] = False

    with patch.object(record, "export_checkpoint"):
        base_holder.train()

    assert base_holder.error == (
        "Final evaluation unavailable: no validation or test split is configured."
    )
    assert base_holder.is_finished() is False


@pytest.mark.parametrize(
    "val_loader, test_loader, expected_loader",
    [
        ("val", "test", "test"),
        (None, "test", "test"),
        ("val", None, "val"),
        (None, None, None),
    ],
)
@pytest.mark.parametrize("evaluation_option", [*list(TrainingEvaluation), None])
def test_training_plan_holder_get_eval_pair_not_implemented(
    base_holder,
    dataset,
    model_holder,
    training_option,
    val_loader,
    test_loader,
    expected_loader,
    evaluation_option,
):
    repeat = 0
    seed = set_seed()
    model = model_holder.get_model({})
    training_option.evaluation_option = evaluation_option
    record = TrainRecord(
        repeat=repeat, dataset=dataset, model=model, option=training_option, seed=seed
    )

    if evaluation_option in {
        TrainingEvaluation.VAL_LOSS,
        TrainingEvaluation.VAL_ACC,
        TrainingEvaluation.VAL_AUC,
    }:
        selected_state_attributes = {
            TrainingEvaluation.VAL_LOSS: f"best_val_{RecordKey.LOSS}_model",
            TrainingEvaluation.VAL_ACC: f"best_val_{RecordKey.ACC}_model",
            TrainingEvaluation.VAL_AUC: f"best_val_{RecordKey.AUC}_model",
        }
        setattr(
            record,
            selected_state_attributes[evaluation_option],
            record.model.state_dict(),
        )

    if evaluation_option and expected_loader is not None:
        _, target_loader = base_holder.get_eval_pair(record, val_loader, test_loader)
        assert target_loader == expected_loader
    elif evaluation_option:
        with pytest.raises(FinalEvaluationUnavailableError):
            base_holder.get_eval_pair(record, val_loader, test_loader)
    else:
        with pytest.raises(NotImplementedError):
            base_holder.get_eval_pair(record, val_loader, test_loader)


def test_training_plan_holder_get_eval_model_by_lastest_model(
    base_holder, dataset, model_holder, training_option
):
    repeat = 0
    val_loader = None
    test_loader = object()
    seed = set_seed()
    model = model_holder.get_model({})

    with patch.object(model, "state_dict", return_value="test"):
        training_option.evaluation_option = TrainingEvaluation.LAST_EPOCH
        record = TrainRecord(
            repeat=repeat,
            dataset=dataset,
            model=model,
            option=training_option,
            seed=seed,
        )

        target_model, _ = base_holder.get_eval_pair(record, val_loader, test_loader)

        assert isinstance(target_model, FakeModel)
        assert target_model.my_state_dict == "test"


def test_training_plan_holder_set_interrupt(base_holder):
    assert base_holder.interrupt is False
    base_holder.set_interrupt()
    assert base_holder.interrupt
    base_holder.clear_interrupt()
    assert base_holder.interrupt is False


def test_training_plan_holder_trivial_getter(base_holder, dataset):
    assert base_holder.get_name() == "Fold_0"
    assert base_holder.get_dataset() == dataset
    assert len(base_holder.get_plans()) == REPEAT


def test_training_plan_ids_do_not_collide_within_one_second(
    dataset,
    model_holder,
    training_option,
):
    frozen = datetime.datetime(2026, 7, 30, 12, 0, 0)
    with patch("XBrainLab.backend.training.training_plan.datetime.datetime") as clock:
        clock.now.return_value = frozen
        first = TrainingPlanHolder(model_holder, dataset, training_option, {})
        second = TrainingPlanHolder(model_holder, dataset, training_option, {})

    assert first.plan_id != second.plan_id


@pytest.mark.timeout(10)
@pytest.mark.parametrize("interrupt", [True, False])
def test_training_plan_holder_one_epoch(base_holder, interrupt):
    model = base_holder.model_holder.get_model({})
    train_record = base_holder.train_record_list[0]
    trainLoader, valLoader, _ = base_holder.get_loader(train_record)
    optimizer = train_record.optim
    criterion = train_record.criterion

    fake_test_result = {"test": "test"}

    with (
        patch.object(train_record, "update_train") as update_train_mock,
        patch.object(train_record, "update_validation") as update_val_mock,
        patch.object(train_record, "update_statistic") as update_statistic_mock,
        patch.object(train_record, "export_checkpoint") as export_checkpoint_mock,
        patch(
            "XBrainLab.backend.training.evaluator.Evaluator.evaluate_metrics",
            return_value=fake_test_result,
        ),
    ):
        if interrupt:
            base_holder.set_interrupt()

        start_time = time.time()
        base_holder.train_one_epoch(
            model,
            trainLoader,
            valLoader,
            optimizer,
            criterion,
            train_record,
        )
        total_time = time.time() - start_time

        if interrupt:
            assert update_train_mock.call_count == 0
            assert update_val_mock.call_count == 0
            assert update_statistic_mock.call_count == 0
            assert export_checkpoint_mock.call_count == 0
            return

        update_train_mock.assert_called_once()
        update_val_mock.assert_called_once()
        update_statistic_mock.assert_called_once()
        export_checkpoint_mock.assert_not_called()

        step_called_args = update_statistic_mock.call_args[0]
        assert (step_called_args[0]["time"] - total_time) < 0.1
        assert step_called_args[0]["lr"] == 0.01

        update_val_called_args = update_val_mock.call_args[0][0]
        assert update_val_called_args == fake_test_result

        base_holder.train_one_epoch(
            model,
            trainLoader,
            valLoader,
            optimizer,
            criterion,
            train_record,
        )
        export_checkpoint_mock.assert_called_once()


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat(base_holder):
    train_record = base_holder.train_record_list[0]

    def set_interrupt(*args, **kwargs):
        base_holder.set_interrupt()

    with (
        patch.object(
            base_holder, "train_one_epoch", side_effect=set_interrupt
        ) as train_one_epoch_mock,
        patch.object(train_record, "export_checkpoint") as export_checkpoint_mock,
    ):
        base_holder.train_one_repeat(train_record)

        train_one_epoch_mock.assert_called_once()
        export_checkpoint_mock.assert_called_once()


@pytest.mark.timeout(15)
def test_training_saves_predictions_for_each_available_split_after_selection(
    base_holder,
):
    record = base_holder.train_record_list[0]
    train_loader, val_loader, test_loader = base_holder.get_loader(record)
    assert train_loader is not None
    assert val_loader is not None
    assert test_loader is not None
    base_holder.option.epoch = 2
    timeline: list[str] = []

    original_evaluate_metrics = Evaluator.evaluate_metrics
    original_evaluate = Evaluator.evaluate
    original_get_eval_pair = base_holder.get_eval_pair

    def validation_step(*args, **kwargs):
        timeline.append("validation")
        return original_evaluate_metrics(*args, **kwargs)

    def select_checkpoint(*args, **kwargs):
        timeline.append("select_checkpoint")
        return original_get_eval_pair(*args, **kwargs)

    def split_evaluation(*args, **kwargs):
        timeline.append(f"evaluate_{kwargs['evaluation_split']}")
        return original_evaluate(*args, **kwargs)

    with (
        patch.object(
            base_holder,
            "get_loader",
            return_value=(train_loader, val_loader, test_loader),
        ),
        patch.object(
            Evaluator,
            "evaluate_metrics",
            side_effect=validation_step,
        ) as evaluate_metrics,
        patch.object(
            base_holder,
            "get_eval_pair",
            side_effect=select_checkpoint,
        ),
        patch.object(
            Evaluator,
            "evaluate",
            side_effect=split_evaluation,
        ) as final_evaluate,
    ):
        base_holder.train_one_repeat(record)

    assert evaluate_metrics.call_count == 2
    assert all(call.args[1] is val_loader for call in evaluate_metrics.call_args_list)
    assert [call.args[1] for call in final_evaluate.call_args_list] == [
        train_loader,
        val_loader,
        test_loader,
    ]
    assert timeline == [
        "validation",
        "validation",
        "select_checkpoint",
        "evaluate_training",
        "evaluate_validation",
        "evaluate_test",
    ]
    assert record.eval_record is not None
    assert record.eval_record.evaluation_split == "test"
    assert set(record.evaluation_records) == {"training", "validation", "test"}
    assert not hasattr(record, "test")
    assert all(not values for values in record._legacy_test_history.values())


# check status
@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_status(base_holder):
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

    with patch.object(
        base_holder, "train_one_epoch", side_effect=train_one_epoch_side_effect
    ):
        train_record = base_holder.train_record_list[0]
        for i in base_holder.get_training_evaluation():
            assert i == "-"
        base_holder.train_one_repeat(train_record)


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_empty_training_data(base_holder):
    train_record = base_holder.train_record_list[0]
    with (
        patch.object(base_holder, "get_loader", return_value=(None, None, None)),
        pytest.raises(ValueError),
    ):
        base_holder.train_one_repeat(train_record)


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_eval(base_holder):
    train_record = base_holder.train_record_list[0]

    with patch.object(
        train_record,
        "set_evaluation_records",
    ) as set_evaluation_records_mock:
        base_holder.train_one_repeat(train_record)

        set_evaluation_records_mock.assert_called_once()


@pytest.mark.timeout(10)
def test_training_plan_holder_train_one_repeat_already_finished(base_holder):
    train_record = base_holder.train_record_list[0]

    with (
        patch.object(train_record, "is_finished", return_value=True),
        patch.object(base_holder, "train_one_epoch") as train_one_epoch_mock,
        patch.object(train_record, "export_checkpoint") as export_checkpoint_mock,
        patch.object(train_record, "set_eval_record") as set_eval_record_mock,
    ):
        base_holder.train_one_repeat(train_record)
        assert train_one_epoch_mock.call_count == 0
        assert export_checkpoint_mock.call_count == 0
        assert set_eval_record_mock.call_count == 0


@pytest.mark.timeout(10)
def test_training_plan_holder_train(base_holder):
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

    with (
        patch.object(
            base_holder, "train_one_repeat", side_effect=train_one_repeat_side_effect
        ) as train_one_repeat_mock,
        patch.object(
            base_holder, "get_eval_pair", side_effect=get_eval_pair_side_effect
        ) as get_eval_pair_mock,
    ):
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
    original_train_one_repeat = base_holder.train_one_repeat

    def train_one_repeat_side_effect(*args, **kwargs):
        base_holder.set_interrupt()
        original_train_one_repeat(*args, **kwargs)

    with patch.object(
        base_holder, "train_one_repeat", side_effect=train_one_repeat_side_effect
    ) as train_one_repeat_mock:
        base_holder.train()
        assert base_holder.is_finished() is False
        assert base_holder.get_training_status() == "Pending"
        train_one_repeat_mock.assert_called()


@pytest.mark.timeout(10)
def test_training_plan_holder_train_error(base_holder):
    def train_one_repeat_side_effect(*args, **kwargs):
        raise RuntimeError("test")

    with patch.object(
        base_holder, "train_one_repeat", side_effect=train_one_repeat_side_effect
    ) as train_one_repeat_mock:
        base_holder.train()
        assert base_holder.is_finished() is False
        assert base_holder.get_training_status() == "test"
        train_one_repeat_mock.assert_called()


def test_test_model_metrics():
    # Setup
    # model = FakeModel()
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
    # But FakeModel is simple linear. Let's just mock the forward pass or use
    # specific weights.
    # Easier: Mock the model object itself to return specific outputs

    mock_model = torch.nn.Linear(4, 4)  # Dummy

    # Batch 1 outputs (indices 0, 1) -> Labels 0, 1
    out1 = torch.tensor([[10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0]])
    # Batch 2 outputs (indices 2, 3) -> Labels 2, 3
    out2 = torch.tensor(
        [[0.0, 0.0, 10.0, 0.0], [0.0, 10.0, 0.0, 0.0]]
    )  # Last one wrong (pred 1, label 3)

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
    result = Evaluator.evaluate_metrics(mock_model, loader, criterion)

    assert result[RecordKey.ACC] == 75.0
    assert RecordKey.AUC in result
    assert RecordKey.LOSS in result


def test_train_one_repeat_uses_basic_evaluation_without_saliency(base_holder):
    base_holder.option.evaluation_option = TrainingEvaluation.LAST_EPOCH
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    _mark_process_local_evaluation_pause(record)
    record.eval_record = None

    sentinel = object()
    with (
        patch.object(Evaluator, "evaluate", return_value=sentinel) as mock_evaluate,
        patch.object(Evaluator, "evaluate_with_saliency") as mock_saliency,
        patch.object(record, "export_checkpoint"),
    ):
        base_holder.train_one_repeat(record)

    assert [
        call.kwargs["evaluation_split"] for call in mock_evaluate.call_args_list
    ] == [
        "training",
        "validation",
        "test",
    ]
    mock_saliency.assert_not_called()
    assert record.eval_record is sentinel


def test_train_one_repeat_keeps_saliency_out_of_training_thread_when_configured(
    base_holder,
):
    base_holder.option.evaluation_option = TrainingEvaluation.LAST_EPOCH
    base_holder.set_saliency_params(
        {
            "SmoothGrad": {"nt_samples": 1},
            "SmoothGrad_Squared": {"nt_samples": 1},
            "VarGrad": {"nt_samples": 1},
        }
    )
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    _mark_process_local_evaluation_pause(record)
    record.eval_record = None

    sentinel = object()
    with (
        patch.object(Evaluator, "evaluate", return_value=sentinel) as mock_evaluate,
        patch.object(Evaluator, "evaluate_with_saliency") as mock_saliency,
        patch.object(record, "export_checkpoint"),
    ):
        base_holder.train_one_repeat(record)

    assert [
        call.kwargs["evaluation_split"] for call in mock_evaluate.call_args_list
    ] == [
        "training",
        "validation",
        "test",
    ]
    mock_saliency.assert_not_called()
    assert record.eval_record is sentinel


def test_safe_move_to_cpu_preserves_optimizer_and_moves_nested_state(base_holder):
    record = base_holder.get_plans()[0]
    optimizer = record.optim
    parameter = next(record.model.parameters())
    optimizer.state[parameter] = {
        "exp_avg": torch.ones_like(parameter),
        "nested": [torch.ones(1), {"value": torch.ones(1)}],
    }

    base_holder._safe_move_to_cpu(record)

    assert record.optim is optimizer
    state = optimizer.state[parameter]
    assert state["exp_avg"].device.type == "cpu"
    assert state["nested"][0].device.type == "cpu"
    assert state["nested"][1]["value"].device.type == "cpu"


def test_safe_move_to_cpu_releases_model_and_optimizer_gpu_state(base_holder):
    record = base_holder.get_plans()[0]
    optimizer = record.optim
    parameter = next(record.model.parameters())
    optimizer.state[parameter] = {
        "exp_avg": _FakeCudaTensor(torch.ones_like(parameter)),
        "exp_avg_sq": _FakeCudaTensor(torch.ones_like(parameter)),
    }

    with patch.object(record.model, "cpu", wraps=record.model.cpu) as move_model:
        base_holder._safe_move_to_cpu(record)

    move_model.assert_called_once_with()
    assert all(
        value.device.type == "cpu"
        for state in optimizer.state.values()
        for value in state.values()
        if torch.is_tensor(value)
    )


def test_set_saliency_params_recomputes_finished_metric_only_record(base_holder):
    base_holder.option.repeat_num = 1
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    record.eval_record = object()
    _bind_selected_evaluation_checkpoint(base_holder, record)
    sentinel = _prepared_saliency_record()

    with (
        patch.object(base_holder, "get_loader", return_value=(None, None, "loader")),
        patch.object(base_holder, "get_eval_pair", return_value=("model", "loader")),
        patch.object(Evaluator, "evaluate") as mock_evaluate,
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            return_value=sentinel,
        ) as mock_saliency,
    ):
        base_holder.set_saliency_params(
            {
                "SmoothGrad": {"nt_samples": 1},
                "SmoothGrad_Squared": {"nt_samples": 1},
                "VarGrad": {"nt_samples": 1},
            }
        )

    mock_evaluate.assert_not_called()
    mock_saliency.assert_called_once_with(
        "model",
        "loader",
        base_holder.saliency_params,
        evaluation_split="test",
    )
    assert record.eval_record is sentinel


def test_saliency_uses_validation_when_test_split_misses_a_model_class(
    base_holder,
):
    """A held-out split without every class cannot produce complete saliency."""
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    record.eval_record = EvalRecord(
        np.array([0, 0]),
        np.array([[0.8, 0.2], [0.7, 0.3]]),
        {},
        {},
        {},
        {},
        {},
        evaluation_split="test",
    )
    record.evaluation_records = {
        "test": record.eval_record,
        "validation": EvalRecord(
            np.array([0, 1]),
            np.array([[0.8, 0.2], [0.3, 0.7]]),
            {},
            {},
            {},
            {},
            {},
            evaluation_split="validation",
        ),
    }
    _bind_selected_evaluation_checkpoint(base_holder, record)
    prepared = _prepared_saliency_record()
    prepared.evaluation_split = "validation"
    prepared.gradient = {0: np.ones((1, 1, 2)), 1: np.ones((1, 1, 2))}
    train_loader = object()
    validation_loader = object()
    test_loader = object()

    with (
        patch.object(
            base_holder,
            "get_loader",
            return_value=(train_loader, validation_loader, test_loader),
        ),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=("model", validation_loader),
        ) as get_eval_pair,
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            return_value=prepared,
        ) as evaluate_with_saliency,
    ):
        plan = base_holder.prepare_saliency_update_plan(
            {"_methods": ["Gradient"]},
            records=[record],
        )
        update = base_holder.compute_saliency_update(plan)

    assert update.eval_records[0][2] is prepared
    get_eval_pair.assert_called_once_with(record, validation_loader, None)
    evaluate_with_saliency.assert_called_once_with(
        "model",
        validation_loader,
        {"_methods": ["Gradient"]},
        evaluation_split="validation",
    )
    publish_prepared_saliency_updates([update])
    assert record.eval_record.evaluation_split == "test"
    assert record.evaluation_records["validation"] is prepared
    assert record.get_saliency_eval_record() is prepared


def test_saliency_update_binds_epoch_identity_before_publication(base_holder):
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    record.eval_record = EvalRecord(
        np.array([0]),
        np.array([[1.0, 0.0, 0.0, 0.0]]),
        {},
        {},
        {},
        {},
        {},
    )
    _bind_selected_evaluation_checkpoint(base_holder, record)
    prepared = EvalRecord(
        np.arange(CLASS_NUM),
        np.eye(CLASS_NUM),
        {
            class_index: np.ones((1, 1, CLASS_NUM), dtype=np.float32)
            * (class_index + 1)
            for class_index in range(CLASS_NUM)
        },
        {},
        {},
        {},
        {},
    )

    with (
        patch.object(base_holder, "get_loader", return_value=(None, None, "loader")),
        patch.object(base_holder, "get_eval_pair", return_value=("model", "loader")),
        patch.object(Evaluator, "evaluate_with_saliency", return_value=prepared),
    ):
        plan = base_holder.prepare_saliency_update_plan(
            {"_methods": ["Gradient"]},
            records=[record],
        )
        update = base_holder.compute_saliency_update(plan)

    assert update.eval_records[0][2] is prepared
    assert prepared.saliency_context is not None
    assert prepared.saliency_context_status == "verified"
    assert prepared.saliency_context.channel_names == ("C1",)
    assert prepared.saliency_context.epoch_sample_count == CLASS_NUM


def _completed_saliency_run(
    run_id: int = 1,
) -> tuple[
    TrainingRunIdentity,
    TrainingTerminalOutcome,
]:
    run = TrainingRunIdentity(trainer_id="trainer-under-test", run_id=run_id)
    return run, TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=run,
    )


def _mark_finished_records(base_holder, count: int) -> tuple[list, list[object]]:
    records = base_holder.get_plans()[:count]
    eval_records = [object() for _record in records]
    for record, eval_record in zip(records, eval_records, strict=True):
        record.epoch = base_holder.option.epoch
        record.eval_record = eval_record
        _bind_selected_evaluation_checkpoint(base_holder, record)
    return records, eval_records


def test_post_training_saliency_append_only_computes_new_records_off_thread(
    base_holder,
):
    records, old_eval_records = _mark_finished_records(base_holder, 2)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, outcome = _completed_saliency_run()
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=1,
        finished_runs_after=2,
        append=True,
    )
    params = {
        "_profile": "recommended",
        "_methods": ["Gradient", "Gradient * Input"],
    }
    compute_started = Event()
    release_compute = Event()
    prepared_eval = _prepared_saliency_record()

    def evaluate(*_args, **_kwargs):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return prepared_eval

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=(Mock(), "test"),
        ) as get_eval_pair,
        patch.object(Evaluator, "evaluate_with_saliency", side_effect=evaluate),
    ):
        with post_training_saliency_target(target):
            manager.set_saliency_params(params)

        assert compute_started.wait(timeout=2.0)
        assert records[0].eval_record is old_eval_records[0]
        assert records[1].eval_record is old_eval_records[1]
        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert get_eval_pair.call_args.args[0] is records[1]
    assert records[0].eval_record is old_eval_records[0]
    assert records[1].eval_record is prepared_eval
    assert manager.saliency_params == params


def test_post_training_saliency_append_race_discards_prepared_result(base_holder):
    records, old_eval_records = _mark_finished_records(base_holder, 2)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, outcome = _completed_saliency_run()
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=1,
        finished_runs_after=2,
        append=True,
    )
    params = {
        "_profile": "recommended",
        "_methods": ["Gradient", "Gradient * Input"],
    }

    def race_with_append(*_args, **_kwargs):
        trainer.add_training_plan_holders([])
        return _prepared_saliency_record()

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=(Mock(), "test")),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=race_with_append,
        ),
    ):
        with post_training_saliency_target(target):
            manager.set_saliency_params(params)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert [record.eval_record for record in records] == old_eval_records
    assert manager.saliency_params is old_params
    assert base_holder.saliency_params is old_params
    assert (
        manager.get_post_training_saliency_status().phase
        is PostTrainingSaliencyPhase.CANCELLED
    )


@pytest.mark.parametrize(
    "state",
    [TrainingOutcomeState.FAILED, TrainingOutcomeState.CANCELLED],
)
def test_post_training_saliency_never_schedules_non_completed_run(base_holder, state):
    _records, old_eval_records = _mark_finished_records(base_holder, 1)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, _completed = _completed_saliency_run()
    outcome = TrainingTerminalOutcome(state=state, run=run)
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(Evaluator, "evaluate_with_saliency") as evaluate,
        post_training_saliency_target(target),
    ):
        manager.set_saliency_params(
            {
                "_profile": "recommended",
                "_methods": ["Gradient", "Gradient * Input"],
            }
        )

    evaluate.assert_not_called()
    assert manager.wait_for_saliency_job(timeout=0.1)
    assert manager.saliency_params is old_params
    assert base_holder.get_plans()[0].eval_record is old_eval_records[0]


def test_post_training_saliency_publishes_multiple_records_atomically(base_holder):
    records, old_eval_records = _mark_finished_records(base_holder, 2)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, outcome = _completed_saliency_run()
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=2,
        append=True,
    )
    prepared = [_prepared_saliency_record(), _prepared_saliency_record()]
    observed = []

    def evaluate(*_args, **_kwargs):
        observed.append([record.eval_record for record in records])
        return prepared[len(observed) - 1]

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=(Mock(), "test")),
        patch.object(Evaluator, "evaluate_with_saliency", side_effect=evaluate),
    ):
        with post_training_saliency_target(target):
            manager.set_saliency_params(
                {
                    "_profile": "recommended",
                    "_methods": ["Gradient", "Gradient * Input"],
                }
            )
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert observed == [old_eval_records, old_eval_records]
    assert [record.eval_record for record in records] == prepared


def test_post_training_saliency_oom_preserves_existing_record_state(base_holder):
    records, old_eval_records = _mark_finished_records(base_holder, 1)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, outcome = _completed_saliency_run()
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )
    params = {
        "_profile": "recommended",
        "_methods": ["Gradient", "Gradient * Input"],
    }

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=(Mock(), "test")),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=torch.cuda.OutOfMemoryError("private allocation details"),
        ),
        patch("XBrainLab.backend.training_manager.release_cuda_cache") as release_cache,
    ):
        with post_training_saliency_target(target):
            manager.set_saliency_params(params)
        assert manager.wait_for_saliency_job(timeout=2.0)

    status = manager.get_post_training_saliency_status()
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == "cuda_oom"
    assert "private allocation details" not in (status.message or "")
    assert records[0].eval_record is old_eval_records[0]
    assert manager.saliency_params is old_params
    assert base_holder.saliency_params is old_params
    release_cache.assert_called_once()


def test_noncooperative_saliency_cancel_is_bounded_and_never_publishes(
    base_holder,
):
    records, old_eval_records = _mark_finished_records(base_holder, 1)
    trainer = Trainer([base_holder])
    manager = TrainingManager()
    manager.trainer = trainer
    old_params = {"_methods": ["Gradient"]}
    manager.saliency_params = old_params
    base_holder.saliency_params = old_params
    run, outcome = _completed_saliency_run()
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )
    params = {
        "_profile": "recommended",
        "_methods": ["Gradient", "Gradient * Input"],
    }
    compute_started = Event()
    release_compute = Event()

    def noncooperative_evaluate(*_args, **_kwargs):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return _prepared_saliency_record()

    with (
        patch.object(trainer, "get_terminal_outcome", return_value=outcome),
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=(Mock(), "test")),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=noncooperative_evaluate,
        ),
        patch(
            "XBrainLab.backend.training_manager."
            "_POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS",
            0.01,
        ),
    ):
        with post_training_saliency_target(target):
            manager.set_saliency_params(params)
        assert compute_started.wait(timeout=2.0)

        started = time.monotonic()
        with pytest.raises(SaliencyCancellationTimeoutError):
            manager.clean_trainer(force_update=True)
        assert time.monotonic() - started < 0.5

        assert manager.trainer is trainer
        assert records[0].eval_record is old_eval_records[0]
        assert manager.saliency_params is old_params
        assert (
            manager.get_post_training_saliency_status().phase
            is PostTrainingSaliencyPhase.CANCELLED
        )
        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert records[0].eval_record is old_eval_records[0]
    assert manager.saliency_params is old_params


def test_set_saliency_params_atomically_recomputes_multiple_finished_records(
    base_holder,
):
    records = base_holder.get_plans()[:2]
    old_params = {"Gradient": {}}
    old_eval_records = [object(), object()]
    new_eval_records = [
        _prepared_saliency_record(),
        _prepared_saliency_record(),
    ]
    for record, old_eval_record in zip(records, old_eval_records, strict=True):
        record.epoch = base_holder.option.epoch
        record.eval_record = old_eval_record
        _bind_selected_evaluation_checkpoint(base_holder, record)
    base_holder.saliency_params = old_params
    trainer = Trainer([base_holder])
    train_loader, val_loader, test_loader = object(), object(), object()
    observed_tokens = []

    def evaluate_with_saliency(*args, **kwargs):
        observed_tokens.append(trainer.get_state_snapshot_token())
        assert base_holder.saliency_params is old_params
        assert [record.eval_record for record in records] == old_eval_records
        return new_eval_records[len(observed_tokens) - 1]

    generation_before = trainer.get_state_generation()
    params = {"SmoothGrad": {"nt_samples": 1}}
    with (
        patch.object(
            base_holder,
            "get_loader",
            return_value=(train_loader, val_loader, test_loader),
        ),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=("model", test_loader),
        ),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=evaluate_with_saliency,
        ) as evaluate,
    ):
        base_holder.set_saliency_params(params)

    assert all(token.stable for token in observed_tokens)
    assert trainer.get_state_generation() == generation_before + 2
    assert base_holder.saliency_params == params
    assert [record.eval_record for record in records] == new_eval_records
    assert [call.kwargs["evaluation_split"] for call in evaluate.call_args_list] == [
        "test",
        "test",
    ]
    for eval_record in new_eval_records:
        producer_identity = eval_record.bind_saliency_context.call_args.kwargs[
            "producer_identity"
        ]
        assert producer_identity.dataset_fingerprint
        assert producer_identity.split_fingerprint
        assert producer_identity.run_fingerprint
        assert producer_identity.model_fingerprint


def test_saliency_update_rejects_split_change_during_expensive_compute(base_holder):
    record = base_holder.get_plans()[0]
    record.epoch = base_holder.option.epoch
    previous_eval_record = object()
    record.eval_record = previous_eval_record
    _bind_selected_evaluation_checkpoint(base_holder, record)
    original_test_mask = base_holder.dataset.test_mask.copy()

    def mutate_split_during_compute(*_args, **_kwargs):
        base_holder.dataset.test_mask[0] = not base_holder.dataset.test_mask[0]
        return _prepared_saliency_record()

    try:
        with (
            patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
            patch.object(
                base_holder,
                "get_eval_pair",
                return_value=("model", "test"),
            ),
            patch.object(
                Evaluator,
                "evaluate_with_saliency",
                side_effect=mutate_split_during_compute,
            ),
            pytest.raises(StaleSaliencyUpdateError),
        ):
            base_holder.set_saliency_params({"Gradient": {}})
    finally:
        base_holder.dataset.test_mask = original_test_mask

    assert record.eval_record is previous_eval_record


def test_set_saliency_params_second_record_failure_preserves_previous_state(
    base_holder,
):
    records = base_holder.get_plans()[:2]
    old_params = {"Gradient": {}}
    old_eval_records = [object(), object()]
    for record, old_eval_record in zip(records, old_eval_records, strict=True):
        record.epoch = base_holder.option.epoch
        record.eval_record = old_eval_record
        _bind_selected_evaluation_checkpoint(base_holder, record)
    base_holder.saliency_params = old_params
    prepared_first_record = _prepared_saliency_record()

    with (
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=("model", "test")),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=[prepared_first_record, RuntimeError("second record failed")],
        ),
        pytest.raises(RuntimeError, match="second record failed"),
    ):
        base_holder.set_saliency_params({"SmoothGrad": {"nt_samples": 1}})

    assert base_holder.saliency_params is old_params
    assert [record.eval_record for record in records] == old_eval_records


def test_training_manager_saliency_success_commits_all_holders_once(base_holder):
    second_holder = TrainingPlanHolder(
        base_holder.model_holder,
        base_holder.dataset,
        base_holder.option,
        {},
    )
    holders = [base_holder, second_holder]
    old_params = {"Gradient": {}}
    old_eval_records = [object(), object()]
    new_eval_records = [
        _prepared_saliency_record(),
        _prepared_saliency_record(),
    ]
    for holder, old_eval_record in zip(holders, old_eval_records, strict=True):
        record = holder.get_plans()[0]
        record.epoch = holder.option.epoch
        record.eval_record = old_eval_record
        _bind_selected_evaluation_checkpoint(holder, record)
        holder.saliency_params = old_params

    trainer = Trainer(holders)
    manager = TrainingManager()
    manager.trainer = trainer
    manager.saliency_params = old_params
    observed_tokens = []
    commit_tokens = []

    def evaluate_with_saliency(*args, **kwargs):
        observed_tokens.append(trainer.get_state_snapshot_token())
        assert manager.saliency_params is old_params
        assert all(holder.saliency_params is old_params for holder in holders)
        assert [holder.get_plans()[0].eval_record for holder in holders] == (
            old_eval_records
        )
        return new_eval_records[len(observed_tokens) - 1]

    original_publish_manager_params = manager._publish_saliency_params

    def publish_manager_params(params):
        original_publish_manager_params(params)
        commit_tokens.append(trainer.get_state_snapshot_token())
        assert manager.saliency_params == params
        assert all(holder.saliency_params is old_params for holder in holders)
        assert [holder.get_plans()[0].eval_record for holder in holders] == (
            old_eval_records
        )

    generation_before = trainer.get_state_generation()
    params = {"SmoothGrad": {"nt_samples": 1}}
    with (
        patch.object(
            base_holder,
            "get_loader",
            return_value=(None, None, "first-test"),
        ),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=("first-model", "first-test"),
        ),
        patch.object(
            second_holder,
            "get_loader",
            return_value=(None, None, "second-test"),
        ),
        patch.object(
            second_holder,
            "get_eval_pair",
            return_value=("second-model", "second-test"),
        ),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=evaluate_with_saliency,
        ),
        patch.object(
            manager,
            "_publish_saliency_params",
            side_effect=publish_manager_params,
        ),
    ):
        manager.set_saliency_params(params)

    assert all(token.stable for token in observed_tokens)
    assert [token.stable for token in commit_tokens] == [False]
    assert trainer.get_state_generation() == generation_before + 2
    assert manager.saliency_params == params
    assert [holder.saliency_params for holder in holders] == [params, params]
    assert [holder.get_plans()[0].eval_record for holder in holders] == new_eval_records


def test_training_manager_saliency_second_holder_failure_preserves_all_state(
    base_holder,
):
    second_holder = TrainingPlanHolder(
        base_holder.model_holder,
        base_holder.dataset,
        base_holder.option,
        {},
    )
    holders = [base_holder, second_holder]
    old_manager_params = {"Gradient": {"source": "manager"}}
    old_holder_params = [
        {"Gradient": {"source": "first"}},
        {"Gradient": {"source": "second"}},
    ]
    old_eval_records = [object(), object()]
    for holder, holder_params, old_eval_record in zip(
        holders,
        old_holder_params,
        old_eval_records,
        strict=True,
    ):
        record = holder.get_plans()[0]
        record.epoch = holder.option.epoch
        record.eval_record = old_eval_record
        _bind_selected_evaluation_checkpoint(holder, record)
        holder.saliency_params = holder_params

    manager = TrainingManager()
    manager.trainer = Trainer(holders)
    manager.saliency_params = old_manager_params
    failure = RuntimeError("second holder failed")

    with (
        patch.object(
            base_holder,
            "get_loader",
            return_value=(None, None, "first-test"),
        ),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=("first-model", "first-test"),
        ),
        patch.object(
            second_holder,
            "get_loader",
            return_value=(None, None, "second-test"),
        ),
        patch.object(
            second_holder,
            "get_eval_pair",
            return_value=("second-model", "second-test"),
        ),
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            side_effect=[_prepared_saliency_record(), failure],
        ),
        pytest.raises(type(failure)) as raised,
    ):
        manager.set_saliency_params({"SmoothGrad": {"nt_samples": 1}})

    assert raised.value is failure
    assert manager.saliency_params is old_manager_params
    assert [holder.saliency_params for holder in holders] == old_holder_params
    assert [holder.get_plans()[0].eval_record for holder in holders] == old_eval_records


def test_set_empty_saliency_params_atomically_recomputes_metric_only(base_holder):
    records = base_holder.get_plans()[:2]
    old_params = {"SmoothGrad": {"nt_samples": 1}}
    old_eval_records = [object(), object()]
    new_eval_records = [object(), object()]
    for record, old_eval_record in zip(records, old_eval_records, strict=True):
        record.epoch = base_holder.option.epoch
        record.eval_record = old_eval_record
    base_holder.saliency_params = old_params

    with (
        patch.object(
            base_holder, "get_loader", return_value=(None, "validation", None)
        ),
        patch.object(
            base_holder,
            "get_eval_pair",
            return_value=("model", "validation"),
        ),
        patch.object(
            Evaluator,
            "evaluate",
            side_effect=new_eval_records,
        ) as evaluate,
        patch.object(Evaluator, "evaluate_with_saliency") as evaluate_with_saliency,
    ):
        base_holder.set_saliency_params({})

    assert base_holder.saliency_params == {}
    assert [record.eval_record for record in records] == new_eval_records
    assert [call.kwargs["evaluation_split"] for call in evaluate.call_args_list] == [
        "validation",
        "validation",
    ]
    evaluate_with_saliency.assert_not_called()


def test_set_empty_saliency_params_propagates_oom_and_preserves_previous_state(
    base_holder,
):
    records = base_holder.get_plans()[:2]
    old_params = {"SmoothGrad": {"nt_samples": 1}}
    old_eval_records = [object(), object()]
    for record, old_eval_record in zip(records, old_eval_records, strict=True):
        record.epoch = base_holder.option.epoch
        record.eval_record = old_eval_record
    base_holder.saliency_params = old_params
    oom = torch.cuda.OutOfMemoryError("metric-only recomputation OOM")

    with (
        patch.object(base_holder, "get_loader", return_value=(None, None, "test")),
        patch.object(base_holder, "get_eval_pair", return_value=("model", "test")),
        patch.object(Evaluator, "evaluate", side_effect=[object(), oom]),
        pytest.raises(torch.cuda.OutOfMemoryError) as raised,
    ):
        base_holder.set_saliency_params({})

    assert raised.value is oom
    assert base_holder.saliency_params is old_params
    assert [record.eval_record for record in records] == old_eval_records


def test_set_saliency_params_does_not_open_test_split_before_training_finishes(
    base_holder,
):
    record = base_holder.get_plans()[0]
    assert record.is_finished() is False

    with (
        patch.object(base_holder, "get_loader") as get_loader,
        patch.object(base_holder, "get_eval_pair") as get_eval_pair,
        patch.object(Evaluator, "evaluate") as evaluate,
        patch.object(Evaluator, "evaluate_with_saliency") as evaluate_with_saliency,
    ):
        base_holder.set_saliency_params({"SmoothGrad": {"nt_samples": 1}})

    assert base_holder.saliency_params == {"SmoothGrad": {"nt_samples": 1}}
    get_loader.assert_not_called()
    get_eval_pair.assert_not_called()
    evaluate.assert_not_called()
    evaluate_with_saliency.assert_not_called()


def test_training_plan_holder_init_error(
    base_holder, model_holder, dataset, training_option
):
    # Mock model_holder.get_model to raise RuntimeError
    with patch.object(
        model_holder,
        "get_model",
        side_effect=RuntimeError(
            "Given input size: (16x1x1). Calculated output size: (16x1x0). "
            "Output size is too small"
        ),
    ):
        args = {
            "model_holder": model_holder,
            "dataset": dataset,
            "option": training_option,
            "saliency_params": {},
        }

        # Should raise ValueError with specific message (now includes model name)
        with pytest.raises(
            ValueError, match=r"Failed to create model.*Output size is too small"
        ):
            TrainingPlanHolder(**args)

    # Verify other RuntimeErrors are re-raised
    with (
        patch.object(
            model_holder, "get_model", side_effect=RuntimeError("Other error")
        ),
        pytest.raises(RuntimeError, match="Other error"),
    ):
        TrainingPlanHolder(**args)
