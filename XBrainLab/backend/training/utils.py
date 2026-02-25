"""Utility functions for optimizer introspection, instantiation, and device queries."""

import inspect

import torch


def get_optimizer_classes():
    """Return a dictionary of all available PyTorch optimizer classes.

    Returns:
        A dictionary mapping optimizer class names to their class objects.
    """
    return {c[0]: c[1] for c in inspect.getmembers(torch.optim, inspect.isclass)}


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
    sigs = inspect.signature(optimizer_class.__init__)
    params = list(sigs.parameters)[2:]  # skip self and params/lr usually

    result = []
    for param in params:
        if "lr" in param:
            continue

        default_val = ""
        if (
            sigs.parameters[param].default != inspect._empty
            and sigs.parameters[param].default is not None
        ):
            default_val = str(sigs.parameters[param].default)

        result.append((param, default_val))
    return result


def instantiate_optimizer(optimizer_class, optim_params, lr=1):
    """Instantiate an optimizer with a dummy parameter to validate configuration.

    Args:
        optimizer_class: The optimizer class to instantiate.
        optim_params: Dictionary of optimizer-specific parameters.
        lr: Learning rate for validation. Defaults to ``1``.

    Returns:
        An instantiated optimizer bound to a dummy tensor.
    """
    # We use a dummy tensor to validate the optimizer init
    return optimizer_class([torch.Tensor()], lr=lr, **optim_params)


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
