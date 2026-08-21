"""Real training, artifact, evaluation, and saliency paths by model family."""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.dataset import Dataset, DataSplittingConfig, Epochs, TrainingType
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.model_base.model_catalog import (
    BraindecodeProviderStatus,
    get_model_spec,
)
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.record import EvalRecord, RecordKey
from XBrainLab.backend.training.record.artifact_store import load_model_state_dict

_HEALTHY_PROVIDER = BraindecodeProviderStatus(
    available=True,
    installed_version="1.6.1",
    reason="",
    checked=True,
)
_CHANNEL_NAMES = (
    "Fp1",
    "Fp2",
    "F7",
    "F3",
    "Fz",
    "F4",
    "F8",
    "T7",
    "C3",
    "Cz",
    "C4",
    "T8",
    "P7",
    "P3",
    "Pz",
    "P4",
    "P8",
    "O1",
    "Oz",
    "O2",
    "FC1",
    "FC2",
)
_FAMILY_REPRESENTATIVES = (
    ("Convolutional", "braindecode.eegnet"),
    ("Attention", "braindecode.eegconformer"),
    ("Filter bank", "braindecode.fbcnet"),
    ("Foundation", "braindecode.biot"),
    ("Graph", "braindecode.dgcnn"),
    ("Sleep", "braindecode.deepsleepnet"),
)


def _make_dataset(model_id: str) -> Dataset:
    trial_count = 12
    channel_count = len(_CHANNEL_NAMES)
    sample_count = 256
    class_count = 2
    rng = np.random.default_rng(2401)
    data = rng.standard_normal(
        (trial_count, channel_count, sample_count),
        dtype=np.float32,
    )
    labels = np.arange(trial_count, dtype=int) % class_count
    events = np.column_stack(
        (np.arange(trial_count), np.zeros(trial_count, dtype=int), labels),
    )
    info = mne.create_info(_CHANNEL_NAMES, sfreq=128.0, ch_types="eeg")
    info.set_montage(mne.channels.make_standard_montage("standard_1020"))
    mne_epochs = mne.EpochsArray(
        data,
        info,
        events=events,
        event_id={"class-0": 0, "class-1": 1},
        verbose=False,
    )
    epoch_data = Epochs([Raw(f"{model_id}-workflow-epo.fif", mne_epochs)])
    epoch_data.set_channels(
        list(_CHANNEL_NAMES),
        [tuple(channel["loc"][:3]) for channel in info["chs"]],
    )
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.FULL, False, [], []),
    )
    dataset.set_name(model_id)
    dataset.train_mask[:8] = True
    dataset.val_mask[8:10] = True
    dataset.test_mask[10:] = True
    dataset.remaining_mask[:] = False
    return dataset


def _model_holder(model_id: str, dataset: Dataset) -> ModelHolder:
    signal_context = dataset.get_epoch_data().get_model_args()
    spec = get_model_spec(
        model_id,
        provider_status=_HEALTHY_PROVIDER,
        signal_context=signal_context,
    )
    assert spec.available, spec.unavailable_reason
    return ModelHolder(
        spec.factory,
        spec.default_parameters(),
        None,
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        source_revision=spec.source_revision,
    )


def _training_option(output_dir: Path) -> TrainingOption:
    return TrainingOption(
        output_dir=str(output_dir),
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=2,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.VAL_LOSS,
        repeat_num=1,
        seed=2407,
    )


@pytest.mark.parametrize(
    ("expected_family", "model_id"),
    _FAMILY_REPRESENTATIVES,
    ids=lambda value: value.removeprefix("braindecode."),
)
def test_braindecode_family_real_workflow(
    expected_family: str,
    model_id: str,
    tmp_path: Path,
) -> None:
    dataset = _make_dataset(model_id)
    holder = _model_holder(model_id, dataset)
    spec = get_model_spec(
        model_id,
        provider_status=_HEALTHY_PROVIDER,
        signal_context=dataset.get_epoch_data().get_model_args(),
    )
    assert spec.family == expected_family

    plan = TrainingPlanHolder(
        holder,
        dataset,
        _training_option(tmp_path / model_id),
        {},
    )
    Trainer([plan]).job()

    assert plan.error is None
    assert len(plan.train_record_list) == 1
    record = plan.train_record_list[0]
    assert record.is_finished()
    assert record.epoch == 1
    assert len(record.train[RecordKey.LOSS]) == 1
    assert record.eval_record is not None
    assert record.model_identity == holder.catalog_identity
    assert record.best_val_loss_model is not None

    artifact_dir = Path(record.target_path or "")
    selected_checkpoint = artifact_dir / "best_val_loss_model"
    assert selected_checkpoint.is_file()
    selected_state = load_model_state_dict(selected_checkpoint)
    fresh_model = holder.get_model(dataset.get_epoch_data().get_model_args())
    fresh_model.load_state_dict(selected_state, strict=True)

    _train_loader, _val_loader, test_loader = plan.get_loader(record)
    assert test_loader is not None
    reloaded_evaluation = Evaluator.evaluate(
        fresh_model.eval(),
        test_loader,
        evaluation_split="test",
    )
    assert reloaded_evaluation.output.shape == (2, 2)
    assert np.isfinite(reloaded_evaluation.output).all()

    persisted_evaluation = EvalRecord.load(str(artifact_dir))
    assert persisted_evaluation is not None
    assert persisted_evaluation.evaluation_split == "test"
    assert np.isfinite(persisted_evaluation.output).all()

    plan.set_saliency_params({"_methods": ["Gradient"]})
    saliency_record = record.get_saliency_eval_record()
    assert saliency_record is not None
    assert saliency_record.has_saliency_data()
    assert saliency_record.saliency_context_status == "verified"
    assert set(saliency_record.gradient) == {0, 1}
    assert all(
        np.isfinite(attribution).all()
        for attribution in saliency_record.gradient.values()
    )

    record.export_checkpoint()
    persisted_saliency = EvalRecord.load(str(artifact_dir))
    assert persisted_saliency is not None
    assert persisted_saliency.has_saliency_data()
    assert persisted_saliency.saliency_context_status == "verified"
