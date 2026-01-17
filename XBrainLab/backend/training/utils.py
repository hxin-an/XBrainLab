import inspect

import torch


def get_optimizer_classes():
    """Returns a dictionary of available PyTorch optimizer classes."""
    return {c[0]: c[1] for c in inspect.getmembers(torch.optim, inspect.isclass)}


def get_optimizer_params(optimizer_class):
    """
    Returns a list of (param_name, default_value) for the given optimizer class.
    Skips 'params' and 'lr'.
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
    """Instantiates the optimizer with dummy parameters to validate configuration."""
    # We use a dummy tensor to validate the optimizer init
    return optimizer_class([torch.Tensor()], lr=lr, **optim_params)


def get_device_count():
    """Returns the number of available CUDA devices."""
    return torch.cuda.device_count()


def get_device_name(index):
    """Returns the name of the CUDA device at the given index."""
    return torch.cuda.get_device_name(index)
