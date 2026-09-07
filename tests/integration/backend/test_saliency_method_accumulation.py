"""Real repeated saliency commands preserve cumulative per-method results."""

from threading import Event

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.application import (
    ApplicationService,
    SaliencyCommand,
    SaliencyPlanIdentity,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.backend.dataset import Dataset, DataSplittingConfig, Epochs, TrainingType
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.evaluator import Evaluator


@pytest.fixture
def real_saliency_service(tmp_path):
    labels = np.tile(np.arange(4), 4)
    info = mne.create_info(["C3", "C4", "Cz", "Pz"], 64.0, "eeg")
    epochs = mne.EpochsArray(
        np.random.default_rng(51).standard_normal((16, 4, 128)),
        info,
        events=np.column_stack((np.arange(16), np.zeros(16, dtype=int), labels)),
        event_id={str(label): label for label in range(4)},
        verbose=False,
    )
    epoch_data = Epochs([Raw("saliency-repeat-epo.fif", epochs)])
    option = TrainingOption(
        output_dir=str(tmp_path),
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=4,
        lr=0.001,
        checkpoint_epoch=1,
        evaluation_option=TrainingEvaluation.VAL_LOSS,
        repeat_num=1,
        seed=51,
    )
    model_holder = ModelHolder(EEGNet, {"f1": 2, "f2": 4, "d": 1})
    holders = []
    for fold in range(2):
        dataset = Dataset(
            epoch_data, DataSplittingConfig(TrainingType.IND, True, [], [])
        )
        dataset.set_name(f"fold-{fold}")
        dataset.set_test((np.arange(16) // 4) == fold)
        dataset.set_val((np.arange(16) // 4) == ((fold + 1) % 4))
        dataset.set_remaining_to_train()
        holders.append(TrainingPlanHolder(model_holder, dataset, option, {}))
    trainer = Trainer(holders)
    trainer.run(interact=False)
    assert all(holder.get_plans()[0].is_finished() for holder in holders)
    study = Study()
    study.training_manager.set_model_holder(model_holder)
    study.training_manager.set_training_option(option)
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    try:
        yield service, holders
    finally:
        service.wait_for_background_tasks(timeout=10.0)
        service.close()


def test_real_commands_accumulate_methods_and_keep_last_success_after_failure(
    real_saliency_service, monkeypatch
):
    service, holders = real_saliency_service
    study = service.study

    def compute(method, params):
        result = service.execute(SaliencyCommand(method=method, params=params))
        assert result.ok, result.message
        assert study.training_manager.wait_for_saliency_job(timeout=10)
        assert service.training_runtime.wait_for_saliency_delivery(timeout=10)
        return service.get_view_publication()

    expected = {"Gradient", "Gradient * Input"}
    baseline_arrays = []
    for method, params in (
        ("Gradient", {"profile": "recommended"}),
        ("SmoothGrad", {"methods": ["SmoothGrad"], "nt_samples": 2, "stdevs": 0.1}),
        ("SmoothGrad_Squared", {"methods": ["SmoothGrad_Squared"], "nt_samples": 2}),
        ("VarGrad", {"methods": ["VarGrad"], "nt_samples": 3, "stdevs": 0.2}),
        ("SmoothGrad", {"methods": ["SmoothGrad"], "nt_samples": 4, "stdevs": 0.3}),
    ):
        publication = compute(method, params)
        assert (
            publication.state.visualization.post_training_saliency.phase.value
            == "succeeded"
        )
        expected.add(method)
        for index, holder in enumerate(holders):
            record = holder.get_plans()[0].get_saliency_eval_record()
            assert set(record.saliency_method_parameters) == expected
            if method == "Gradient":
                baseline_arrays.append(
                    {label: values.copy() for label, values in record.gradient.items()}
                )
            else:
                for label, values in record.gradient.items():
                    np.testing.assert_array_equal(values, baseline_arrays[index][label])
            for retained in expected:
                rendered = service.get_saliency_render(
                    SaliencyRenderRequest(
                        publication_generation=publication.generation,
                        run=SaliencyRunIdentity(SaliencyPlanIdentity(index), 0),
                        method=retained,
                    )
                )
                assert set(rendered.data.saliency_by_class) == {0, 1, 2, 3}
        assert all(
            coverage.complete
            for run in publication.state.visualization.saliency_coverage
            for coverage in run.methods
            if coverage.method in expected
        )

    prior_records = [
        holder.get_plans()[0].get_saliency_eval_record() for holder in holders
    ]
    assert prior_records[0].saliency_method_parameters["SmoothGrad"]["nt_samples"] == 4
    assert prior_records[0].saliency_method_parameters["VarGrad"]["nt_samples"] == 3
    evaluate = Evaluator.evaluate_with_saliency
    calls = 0

    def fail_second_fold(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Second-fold attribution failed")
        return evaluate(*args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(Evaluator, "evaluate_with_saliency", fail_second_fold)
        failed = compute("SmoothGrad", {"methods": ["SmoothGrad"], "nt_samples": 5})
    assert failed.state.visualization.post_training_saliency.phase.value == "failed"
    assert [
        holder.get_plans()[0].get_saliency_eval_record() for holder in holders
    ] == prior_records
    retried = compute("SmoothGrad", {"methods": ["SmoothGrad"], "nt_samples": 5})
    assert retried.state.visualization.post_training_saliency.phase.value == "succeeded"
    for holder in holders:
        record = holder.get_plans()[0].get_saliency_eval_record()
        assert set(record.saliency_method_parameters) == expected
        assert record.saliency_method_parameters["SmoothGrad"]["nt_samples"] == 5


@pytest.mark.parametrize("cancel", [False, True])
def test_running_saliency_rejects_recompute_or_cancels_without_losing_results(
    real_saliency_service, monkeypatch, cancel
):
    service, holders = real_saliency_service
    manager = service.study.training_manager
    assert service.execute(
        SaliencyCommand(method="Gradient", params={"profile": "recommended"})
    ).ok
    assert manager.wait_for_saliency_job(timeout=10)
    assert service.training_runtime.wait_for_saliency_delivery(timeout=10)
    previous = [holder.get_plans()[0].get_saliency_eval_record() for holder in holders]
    entered = Event()
    release = Event()
    evaluate = Evaluator.evaluate_with_saliency

    def paused_evaluate(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return evaluate(*args, **kwargs)

    monkeypatch.setattr(Evaluator, "evaluate_with_saliency", paused_evaluate)
    first = service.execute(
        SaliencyCommand(method="SmoothGrad", params={"nt_samples": 2})
    )
    assert first.ok, first.message
    assert entered.wait(timeout=10)
    try:
        if cancel:
            service.training_runtime.cancel_saliency_job()
            assert (
                manager.get_post_training_saliency_status().phase.value == "cancelled"
            )
        else:
            second = service.execute(
                SaliencyCommand(method="VarGrad", params={"nt_samples": 2})
            )
            assert not second.ok
            assert manager.get_post_training_saliency_status().phase.value == "running"
            assert "already" in second.message.lower()
        assert [
            holder.get_plans()[0].get_saliency_eval_record() for holder in holders
        ] == previous
    finally:
        release.set()
        assert manager.wait_for_saliency_job(timeout=10)
        assert service.training_runtime.wait_for_saliency_delivery(timeout=10)
    for index, holder in enumerate(holders):
        record = holder.get_plans()[0].get_saliency_eval_record()
        if cancel:
            assert record is previous[index]
        else:
            assert set(record.saliency_method_parameters) == {
                "Gradient",
                "Gradient * Input",
                "SmoothGrad",
            }
