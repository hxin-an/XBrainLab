"""Utility functions for optimizer introspection, instantiation, and device queries."""

import ast
import inspect
import math
from typing import Any, get_args

import torch


class OptimizerParameterError(ValueError):
    """A field-specific optimizer parameter parsing failure."""

    def __init__(self, parameter: str, message: str) -> None:
        self.parameter = parameter
        super().__init__(f"{parameter}: {message}")


def get_optimizer_classes() -> dict[str, type[torch.optim.Optimizer]]:
    """Return the optimizer choices supported by the training command contract.

    The UI and :class:`TrainingService` must expose the same finite set.  PyTorch
    may add optimizer classes between releases, so runtime introspection is not
    an appropriate product capability contract.
    """
    return {
        "Adam": torch.optim.Adam,
        "AdamW": torch.optim.AdamW,
        "SGD": torch.optim.SGD,
    }


def get_optimizer_params(optimizer_class):
    """Return constructor parameters for the given optimizer class.

    Inspects the ``__init__`` signature and returns parameter names with
    their default values, skipping ``self``, ``params``, and any parameter
    containing ``'lr'``.

    Args:
        optimizer_class: A PyTorch optimizer class to inspect.

    Returns:
        A list of ``(param_name, default_value_str)`` tuples.

    """
    signature = inspect.signature(optimizer_class.__init__)

    result = []
    for name, parameter in signature.parameters.items():
        if name in {"self", "params", "lr"} or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue

        default = parameter.default
        default_val = "" if default is inspect.Parameter.empty else repr(default)

        result.append((name, default_val))
    return result


def parse_optimizer_param(
    optimizer_class: type[torch.optim.Optimizer],
    parameter_name: str,
    value_text: str,
) -> float | int | bool | tuple[int | float | None, ...] | None:
    """Parse one optimizer field using its native constructor default type."""
    try:
        parameter = inspect.signature(optimizer_class.__init__).parameters[
            parameter_name
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise OptimizerParameterError(parameter_name, "unknown parameter.") from exc

    text = str(value_text).strip()
    default = parameter.default
    if not text:
        if default is inspect.Parameter.empty:
            raise OptimizerParameterError(parameter_name, "a value is required.")
        return _supported_optimizer_default(parameter_name, default)

    if text.casefold() == "none":
        if default is None:
            return None
        raise OptimizerParameterError(parameter_name, "None is not allowed.")

    if isinstance(default, bool):
        if text.casefold() == "true":
            return True
        if text.casefold() == "false":
            return False
        raise OptimizerParameterError(parameter_name, "enter True or False.")

    if isinstance(default, tuple):
        return _parse_numeric_tuple(parameter_name, text)

    if isinstance(default, int) and not isinstance(default, bool):
        if _optimizer_parameter_accepts_float(parameter.annotation):
            return _parse_finite_float(parameter_name, text)
        try:
            return int(text)
        except ValueError as exc:
            raise OptimizerParameterError(
                parameter_name,
                "enter a whole number.",
            ) from exc

    if isinstance(default, float):
        return _parse_finite_float(parameter_name, text)

    if default is None:
        lowered = text.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if text.startswith("("):
            return _parse_numeric_tuple(parameter_name, text)

    try:
        return int(text)
    except ValueError:
        return _parse_finite_float(parameter_name, text)


def _optimizer_parameter_accepts_float(annotation: Any) -> bool:
    """Return whether an inspected optimizer annotation admits real values."""
    if annotation is float or float in get_args(annotation):
        return True
    if annotation is inspect.Parameter.empty:
        return False
    return "float" in str(annotation).casefold()


def _supported_optimizer_default(
    parameter_name: str,
    default: Any,
) -> float | int | bool | tuple[int | float | None, ...] | None:
    if default is None or isinstance(default, (float, int, bool)):
        return default
    if isinstance(default, tuple):
        return _validate_numeric_tuple(parameter_name, default)
    raise OptimizerParameterError(
        parameter_name,
        "this parameter type is not editable.",
    )


def _parse_numeric_tuple(
    parameter_name: str,
    text: str,
) -> tuple[int | float | None, ...]:
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, ValueError) as exc:
        raise OptimizerParameterError(
            parameter_name,
            "enter a numeric tuple such as (0.9, 0.999).",
        ) from exc
    if not isinstance(value, tuple):
        raise OptimizerParameterError(
            parameter_name,
            "enter a numeric tuple such as (0.9, 0.999).",
        )
    return _validate_numeric_tuple(parameter_name, value)


def _validate_numeric_tuple(
    parameter_name: str,
    value: tuple[Any, ...],
) -> tuple[int | float | None, ...]:
    if not value or any(
        item is not None
        and (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
        )
        for item in value
    ):
        raise OptimizerParameterError(
            parameter_name,
            "enter a tuple containing only finite numbers or None.",
        )
    return tuple(value)


def _parse_finite_float(parameter_name: str, text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise OptimizerParameterError(parameter_name, "enter a number.") from exc
    if not math.isfinite(value):
        raise OptimizerParameterError(parameter_name, "enter a finite number.")
    return value


def instantiate_optimizer(optimizer_class, optim_params, lr=1):
    """Instantiate an optimizer with a dummy parameter to validate configuration.

    Args:
        optimizer_class: The optimizer class to instantiate.
        optim_params: Dictionary of optimizer-specific parameters.
        lr: Learning rate for validation. Defaults to ``1``.

    Returns:
        An instantiated optimizer bound to a dummy tensor.

    """
    # Use a real trainable tensor so native optimizer validation follows the
    # same parameter contract as training without allocating a model.
    parameter = torch.nn.Parameter(torch.zeros((1, 1)))
    return optimizer_class([parameter], lr=lr, **optim_params)


def get_device_count():
    """Return the number of available CUDA GPU devices.

    Returns:
        An integer representing the number of CUDA devices.

    """
    return torch.cuda.device_count()


def get_device_name(index):
    """Return the name of the CUDA device at the given index.

    Args:
        index: Zero-based CUDA device index.

    Returns:
        A string with the device name (e.g., ``'NVIDIA GeForce RTX 3090'``).

    """
    return torch.cuda.get_device_name(index)
