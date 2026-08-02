from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import torch

from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    TrainingType,
)
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training_state_contract import TrainingOutcomeState

WAIT_TIMEOUT_SECONDS = 2.0


class TinyClassifier(torch.nn.Module):
    def __init__(
        self,
        *,
        n_classes: int,
        channels: int,
        samples: int,
        sfreq: float,
    ) -> None:
        super().__init__()
        assert (n_classes, channels, samples, sfreq) == (2, 1, 2, 1.0)
        self.linear = torch.nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.linear.weight.copy_(torch.eye(2))

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.linear(inputs.flatten(start_dim=1))


def _real_holder(tmp_path: Path, name: str) -> TrainingPlanHolder:
    epoch_data = object.__new__(Epochs)
    epoch_data.data = np.array(
        [
            [[1.0, 0.0]],
            [[0.0, 1.0]],
        ],
        dtype=np.float32,
    )
    epoch_data.label = np.array([0, 1], dtype=np.int64)
    epoch_data.label_map = {0: "left", 1: "right"}
    epoch_data.ch_names = ["Cz"]
    epoch_data.sfreq = 1.0

    split_config = DataSplittingConfig(TrainingType.FULL, False, [], [])
    dataset = Dataset(epoch_data, split_config)
    dataset.set_name(name)
    dataset.train_mask[0] = True
    dataset.val_mask[1] = True
    dataset.remaining_mask[:] = False
    assert set(dataset.get_training_indices()) == {0}
    assert set(dataset.get_val_indices()) == {1}

    option = TrainingOption(
        output_dir=str(tmp_path / name),
        optim=torch.optim.SGD,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=2,
        lr=0.1,
        checkpoint_epoch=0,
        evaluation_option=TrainingEvaluation.LAST_EPOCH,
        repeat_num=1,
    )
    return TrainingPlanHolder(
        ModelHolder(TinyClassifier, {}),
        dataset,
        option,
        saliency_params=None,
    )


def test_stop_after_optimizer_step_retires_old_run_before_fresh_plan(
    tmp_path: Path,
) -> None:
    old_active = _real_holder(tmp_path, "old-active")
    old_queued = _real_holder(tmp_path, "old-queued")
    trainer = Trainer([old_active, old_queued])
    old_step_finished = threading.Event()
    release_old_worker = threading.Event()
    execution_trace: list[str] = []

    old_active_record = old_active.get_plans()[0]
    old_queued_record = old_queued.get_plans()[0]
    old_optimizer = old_active_record.optim
    queued_optimizer = old_queued_record.optim
    assert old_optimizer is not None
    assert queued_optimizer is not None

    def barrier_after_old_step(
        _optimizer: torch.optim.Optimizer,
        _args: tuple[object, ...],
        _kwargs: dict[str, object],
    ) -> None:
        execution_trace.append("old-active")
        old_step_finished.set()
        assert release_old_worker.wait(timeout=WAIT_TIMEOUT_SECONDS)

    def record_queued_step(
        _optimizer: torch.optim.Optimizer,
        _args: tuple[object, ...],
        _kwargs: dict[str, object],
    ) -> None:
        execution_trace.append("old-queued")

    old_hook = old_optimizer.register_step_post_hook(barrier_after_old_step)
    queued_hook = queued_optimizer.register_step_post_hook(record_queued_step)
    old_weights_before = [
        parameter.detach().clone() for parameter in old_active_record.model.parameters()
    ]

    try:
        trainer.run(interact=True)
        assert old_step_finished.wait(timeout=WAIT_TIMEOUT_SECONDS)
        assert execution_trace == ["old-active"]
        assert any(
            not torch.equal(before, after)
            for before, after in zip(
                old_weights_before,
                old_active_record.model.parameters(),
                strict=True,
            )
        )

        running = trainer.get_terminal_outcome()
        assert running.state is TrainingOutcomeState.RUNNING
        assert running.run is not None

        assert trainer.stop(wait_timeout=0.01) is False
        stop_requested = trainer.get_terminal_outcome()
        assert stop_requested.state is TrainingOutcomeState.STOP_REQUESTED
        assert stop_requested.run == running.run
        assert trainer.is_running() is True

        release_old_worker.set()
        assert trainer.wait_for_completion(timeout=WAIT_TIMEOUT_SECONDS) is True
    finally:
        release_old_worker.set()
        assert trainer.wait_for_completion(timeout=WAIT_TIMEOUT_SECONDS)
        old_hook.remove()
        queued_hook.remove()

    cancelled = trainer.get_terminal_outcome()
    assert cancelled.state is TrainingOutcomeState.CANCELLED
    assert cancelled.run == running.run
    assert trainer.get_current_index() == 2
    assert old_active.get_training_status() == "Cancelled"
    assert old_queued.get_training_status() == "Cancelled"
    assert old_active_record.get_epoch() == 0
    assert old_queued_record.get_epoch() == 0
    assert execution_trace == ["old-active"]

    fresh = _real_holder(tmp_path, "fresh")
    fresh_record = fresh.get_plans()[0]
    fresh_optimizer = fresh_record.optim
    assert fresh_optimizer is not None

    def record_fresh_step(
        _optimizer: torch.optim.Optimizer,
        _args: tuple[object, ...],
        _kwargs: dict[str, object],
    ) -> None:
        execution_trace.append("fresh")

    fresh_hook = fresh_optimizer.register_step_post_hook(record_fresh_step)
    trainer.add_plan(fresh)
    try:
        trainer.run(interact=False)
    finally:
        fresh_hook.remove()

    completed = trainer.get_terminal_outcome()
    assert completed.state is TrainingOutcomeState.COMPLETED
    assert completed.run is not None
    assert completed.run.trainer_id == cancelled.run.trainer_id
    assert completed.run.run_id == cancelled.run.run_id + 1
    assert trainer.get_current_index() == 3
    assert old_active.get_training_status() == "Cancelled"
    assert old_queued.get_training_status() == "Cancelled"
    assert old_active_record.get_epoch() == 0
    assert old_queued_record.get_epoch() == 0
    assert fresh_record.get_epoch() == 1
    assert fresh_record.eval_record is not None
    assert execution_trace == ["old-active", "fresh"]
