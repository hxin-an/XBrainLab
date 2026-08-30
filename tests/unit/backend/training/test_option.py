from typing import Any
from unittest.mock import patch

import pytest
import torch

from XBrainLab.backend.training import (
    TestOnlyOption,
    TrainingEvaluation,
    TrainingOption,
    parse_device_name,
    parse_optim_name,
)
from XBrainLab.backend.training.option import (
    class_map_fingerprint,
    normalize_custom_class_weights,
)


def test_class_weighting_helpers_reject_invalid_custom_values_and_stabilize_map_identity():
    assert class_map_fingerprint({1: "right", 0: "left"}) == class_map_fingerprint(
        {0: "left", 1: "right"}
    )
    assert normalize_custom_class_weights({"left": 1, "right": 2.5}) == {
        "left": 1.0,
        "right": 2.5,
    }
    for bad in ({}, {"left": 0}, {"left": float("nan")}, {1: 1}):
        with pytest.raises(ValueError):
            normalize_custom_class_weights(bad)


@pytest.mark.parametrize(
    "use_cpu, gpu_idx, expected",
    [
        (True, None, "cpu"),
        (True, 0, "cpu"),
        (False, 0, "0 - test"),
        (False, 1, "1 - test"),
        (False, None, None),
    ],
)
def test_parse_device_name(use_cpu, gpu_idx, expected):
    with patch("torch.cuda.get_device_name", return_value="test"):
        if expected is None:
            with pytest.raises(ValueError):
                parse_device_name(use_cpu, gpu_idx)
        else:
            assert parse_device_name(use_cpu, gpu_idx) == expected


class FakeOptim:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = torch.nn.Linear(4, 4)


def test_parse_optim_name():
    target = FakeOptim
    params_map = {"a": 1, "b": 2}
    assert parse_optim_name(target, params_map) == "FakeOptim (a=1, b=2)"


def test_training_evaluation_exposes_validation_only_selection() -> None:
    assert [option.name for option in TrainingEvaluation] == [
        "VAL_LOSS",
        "VAL_AUC",
        "VAL_ACC",
        "LAST_EPOCH",
    ]
    assert TrainingEvaluation("Best testing performance") is TrainingEvaluation.VAL_ACC
    assert TrainingEvaluation("Best testing AUC") is TrainingEvaluation.VAL_AUC


@pytest.mark.parametrize(
    "kwargs, has_error",
    [
        ({"output_dir": None}, True),
        ({"output_dir": 123}, True),
        ({"optim": None}, True),
        ({"optim": int}, True),
        ({"optim_params": None}, True),
        ({"optim_params": []}, True),
        ({"use_cpu": None, "gpu_idx": None}, True),
        ({"use_cpu": None, "gpu_idx": 1}, True),
        ({"use_cpu": False, "gpu_idx": None}, True),
        ({"use_cpu": False, "gpu_idx": 1}, False),
        ({"use_cpu": False, "gpu_idx": "cuda:0"}, True),
        ({"use_cpu": True, "gpu_idx": None}, False),
        ({"use_cpu": True, "gpu_idx": 1}, False),
        ({"use_cpu": 1, "gpu_idx": 0}, True),
        ({"use_cpu": "true", "gpu_idx": 0}, True),
        ({"epoch": 10.5}, True),
        ({"epoch": 10}, False),
        ({"epoch": -5}, True),
        ({"epoch": "error"}, True),
        ({"epoch": None}, True),
        ({"bs": None}, True),
        ({"bs": "error"}, True),
        ({"lr": None}, True),
        ({"lr": "error"}, True),
        ({"lr": float("nan")}, True),
        ({"checkpoint_epoch": None}, True),
        ({"checkpoint_epoch": 0}, False),
        ({"checkpoint_epoch": "error"}, True),
        ({"checkpoint_epoch": 2.5}, True),
        ({"evaluation_option": None}, True),
        ({"evaluation_option": "mystery"}, True),
        ({"repeat_num": None}, True),
        ({"repeat_num": "error"}, True),
        ({"repeat_num": 1.5}, True),
    ],
)
def test_option(kwargs, has_error):
    args = {
        "output_dir": "ok",
        "optim": torch.optim.Adam,
        "optim_params": {"weight_decay": 0.01},
        "use_cpu": False,
        "gpu_idx": 0,
        "epoch": 10,
        "bs": 20,
        "lr": 0.01,
        "checkpoint_epoch": 10,
        "evaluation_option": TrainingEvaluation.VAL_LOSS,
        "repeat_num": 5,
    }

    for k in kwargs:
        args[k] = kwargs[k]

    with (
        patch("torch.cuda.is_available", return_value=True),
        patch("torch.cuda.device_count", return_value=2),
        patch("torch.cuda.get_device_name", return_value="test_gpu"),
        patch(
            "XBrainLab.backend.training.option.is_cuda_device_usable",
            return_value=(True, None),
        ),
    ):
        if has_error:
            with pytest.raises(ValueError):
                option = TrainingOption(**args)
            return

        option = TrainingOption(**args)

        assert option.get_output_dir() == "ok"
        assert option.get_evaluation_option_repr() == "TrainingEvaluation.VAL_LOSS"
        if args["use_cpu"] or (not args["use_cpu"] and torch.cuda.is_available()):
            assert option.get_device_name() == parse_device_name(
                args["use_cpu"], args["gpu_idx"]
            )
        if args["use_cpu"]:
            assert option.get_device() == "cpu"
        else:
            assert option.get_device() == "cuda:" + str(args["gpu_idx"])

        assert option.get_optimizer_name_repr() == "Adam"
        assert option.get_optim_desc_str() == parse_optim_name(
            torch.optim.Adam, args["optim_params"]
        )

        model = FakeModel()
        optim_instance = option.get_optim(model)
        assert isinstance(optim_instance, torch.optim.Adam)
        assert optim_instance.param_groups[0]["lr"] == args["lr"]
        assert optim_instance.param_groups[0]["weight_decay"] == 0.01


def test_training_option_falls_back_to_cpu_when_cuda_probe_fails():
    args = {
        "output_dir": "ok",
        "optim": torch.optim.Adam,
        "optim_params": {"weight_decay": 0.01},
        "use_cpu": False,
        "gpu_idx": 0,
        "epoch": 10,
        "bs": 20,
        "lr": 0.01,
        "checkpoint_epoch": 1,
        "evaluation_option": TrainingEvaluation.VAL_LOSS,
        "repeat_num": 1,
    }

    with (
        patch("torch.cuda.is_available", return_value=True),
        patch("torch.cuda.device_count", return_value=1),
        patch("torch.cuda.get_device_name", return_value="test_gpu"),
        patch(
            "XBrainLab.backend.training.option.is_cuda_device_usable",
            return_value=(False, "probe failed"),
        ),
    ):
        option = TrainingOption(**args)

    assert option.use_cpu is True
    assert option.gpu_idx is None
    assert option.get_device() == "cpu"
    assert option.get_device_name() == "cpu"


@pytest.mark.parametrize(
    ("seed", "repeat_num"),
    [
        (0, 1),
        (0xFFFF_FFFF, 1),
        (0xFFFF_FFFF - 4, 5),
        (None, 5),
    ],
)
def test_training_option_accepts_portable_repeat_seed_range(
    seed: int | None,
    repeat_num: int,
) -> None:
    option = TrainingOption(
        output_dir="ok",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=2,
        lr=0.001,
        checkpoint_epoch=0,
        evaluation_option=TrainingEvaluation.LAST_EPOCH,
        repeat_num=repeat_num,
        seed=seed,
    )

    if seed is None:
        assert type(option.seed) is int
        assert 0 <= option.seed <= 0xFFFF_FFFF - (repeat_num - 1)
        assert option.get_configured_repeat_seeds() == [
            option.seed + repeat_index for repeat_index in range(repeat_num)
        ]
    else:
        assert option.seed == seed


@pytest.mark.parametrize(
    ("seed", "repeat_num"),
    [
        (True, 1),
        (-1, 1),
        (1.5, 1),
        (0x1_0000_0000, 1),
        (0xFFFF_FFFF, 2),
    ],
)
def test_training_option_rejects_nonportable_or_overflowing_seed(
    seed: Any,
    repeat_num: int,
) -> None:
    with pytest.raises(ValueError, match="Invalid seed"):
        TrainingOption(
            output_dir="ok",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=2,
            lr=0.001,
            checkpoint_epoch=0,
            evaluation_option=TrainingEvaluation.LAST_EPOCH,
            repeat_num=repeat_num,
            seed=seed,
        )


@pytest.mark.parametrize(
    "kwargs, has_error",
    [
        ({"output_dir": None}, True),
        ({"output_dir": 123}, True),
        ({"use_cpu": None, "gpu_idx": None}, True),
        ({"use_cpu": None, "gpu_idx": 1}, True),
        ({"use_cpu": False, "gpu_idx": None}, True),
        ({"use_cpu": False, "gpu_idx": 1}, False),
        ({"use_cpu": False, "gpu_idx": "cuda:0"}, True),
        ({"use_cpu": True, "gpu_idx": None}, False),
        ({"use_cpu": True, "gpu_idx": 1}, False),
        ({"use_cpu": True, "gpu_idx": 1.5}, True),
        ({"bs": None}, True),
        ({"bs": "error"}, True),
        ({"bs": 2.5}, True),
    ],
)
def test_test_only_option(kwargs, has_error):
    args = {"output_dir": "ok", "use_cpu": False, "gpu_idx": 0, "bs": 20}

    for k in kwargs:
        args[k] = kwargs[k]

    with (
        patch("torch.cuda.is_available", return_value=True),
        patch("torch.cuda.device_count", return_value=2),
        patch("torch.cuda.get_device_name", return_value="test_gpu"),
        patch(
            "XBrainLab.backend.training.option.is_cuda_device_usable",
            return_value=(True, None),
        ),
    ):
        if has_error:
            with pytest.raises(ValueError):
                option = TestOnlyOption(**args)
            return

        option = TestOnlyOption(**args)

        assert option.get_output_dir() == "ok"
        assert option.get_evaluation_option_repr() == "TrainingEvaluation.LAST_EPOCH"

        if args["use_cpu"] or (not args["use_cpu"] and torch.cuda.is_available()):
            assert option.get_device_name() == parse_device_name(
                args["use_cpu"], args["gpu_idx"]
            )
        if args["use_cpu"]:
            assert option.get_device() == "cpu"
        else:
            assert option.get_device() == "cuda:" + str(args["gpu_idx"])

        assert option.get_optimizer_name_repr() == "-"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("epoch", 0.5),
        ("epoch", 1),
        ("lr", float("nan")),
        ("lr", 0.1),
        ("checkpoint_epoch", 0.5),
        ("checkpoint_epoch", 1),
        ("repeat_num", 1.5),
        ("repeat_num", 2),
    ],
)
def test_test_only_option_rejects_mutated_fixed_runtime_fields(
    field,
    invalid_value,
):
    option = TestOnlyOption("./output", True, 0, 20)
    setattr(option, field, invalid_value)

    with pytest.raises(ValueError):
        option.validate()
        assert option.get_optim_desc_str() == "-"

        assert option.get_optim(None) is None
        assert option.get_optim(10) is None
