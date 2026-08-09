"""Lightweight serialization helpers for training configuration state."""

from __future__ import annotations

from typing import Any


def model_name(model_holder: Any) -> str | None:
    """Return the configured model class name without importing model modules."""
    display_name = getattr(model_holder, "display_name", None)
    if isinstance(display_name, str) and display_name:
        return display_name
    target_model = getattr(model_holder, "target_model", None)
    if target_model is None:
        return None
    return getattr(target_model, "__name__", str(target_model))


def model_params_snapshot(model_holder: Any) -> dict[str, Any]:
    """Return a detached copy of configured model parameters."""
    params = getattr(model_holder, "model_params_map", None)
    if not isinstance(params, dict):
        return {}
    return dict(params)


def training_option_snapshot(option: Any) -> dict[str, Any]:
    """Return every user-editable training option needed to reopen the dialog."""
    if option is None:
        return {}
    evaluation_option = getattr(option, "evaluation_option", None)
    evaluation_value = getattr(evaluation_option, "value", evaluation_option)
    optimizer_params = getattr(option, "optim_params", None)
    repeat_seed_getter = getattr(option, "get_configured_repeat_seeds", None)
    return {
        "epoch": getattr(option, "epoch", None),
        "batch_size": getattr(option, "bs", None),
        "learning_rate": getattr(option, "lr", None),
        "repeat": getattr(option, "repeat_num", None),
        "seed": getattr(option, "seed", None),
        "repeat_seeds": (
            repeat_seed_getter() if callable(repeat_seed_getter) else None
        ),
        "device": option.get_device() if hasattr(option, "get_device") else None,
        "optimizer": option.get_optim_name()
        if hasattr(option, "get_optim_name")
        else None,
        "optimizer_params": dict(optimizer_params)
        if isinstance(optimizer_params, dict)
        else {},
        "checkpoint_epoch": getattr(option, "checkpoint_epoch", None),
        "output_dir": getattr(option, "output_dir", None),
        "evaluation_option": evaluation_value,
    }
