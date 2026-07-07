"""Resource-failure handling tests for training plans."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from XBrainLab.backend.training.training_plan import Status, TrainingPlanHolder


class _Record:
    def __init__(self) -> None:
        self.model = SimpleNamespace(cpu=lambda: None)
        self.resumed = False
        self.paused = False

    def get_name(self) -> str:
        return "repeat-1"

    def resume(self) -> None:
        self.resumed = True

    def pause(self) -> None:
        self.paused = True


def test_training_plan_marks_cuda_oom_as_failed_and_releases_cache(monkeypatch) -> None:
    calls: list[str] = []
    holder = cast(Any, TrainingPlanHolder.__new__(TrainingPlanHolder))
    holder.option = SimpleNamespace(repeat_num=1)
    holder.train_record_list = [_Record()]
    holder.status = Status.PENDING.value
    holder.error = None

    def raise_oom(_record) -> None:
        raise RuntimeError("CUDA out of memory. Tried to allocate 1.00 GiB")

    holder.train_one_repeat = raise_oom
    holder.is_finished = lambda: False
    monkeypatch.setattr(
        "XBrainLab.backend.training.training_plan.torch.cuda.is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.training.training_plan.torch.cuda.empty_cache",
        lambda: calls.append("empty"),
    )

    holder.train()

    assert holder.status == "Failed: CUDA out of memory"
    assert holder.error is not None
    assert "CUDA out of memory during training" in holder.error
    assert calls
