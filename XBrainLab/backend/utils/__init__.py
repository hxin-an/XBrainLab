"""Backend utility sub-package: validation, seeding, and random state."""

from importlib import import_module
from typing import Any

from .check import validate_issubclass, validate_list_type, validate_type

__all__ = [
    "get_random_state",
    "set_random_state",
    "set_seed",
    "validate_issubclass",
    "validate_list_type",
    "validate_type",
]


def get_random_state() -> tuple:
    """Return the current RNG state, importing torch-backed helpers on demand."""
    seed_module = import_module(f"{__name__}.seed")
    return seed_module.get_random_state()


def set_random_state(state: tuple) -> None:
    """Restore RNG state, importing torch-backed helpers on demand."""
    seed_module = import_module(f"{__name__}.seed")
    seed_module.set_random_state(state)


def set_seed(seed: int | None = None, deterministic: bool = False) -> int:
    """Set random seeds, importing torch-backed helpers on demand."""
    seed_module = import_module(f"{__name__}.seed")
    return seed_module.set_seed(seed=seed, deterministic=deterministic)


def __getattr__(name: str) -> Any:
    """Load the seed submodule only when callers explicitly request it."""
    if name == "seed":
        module = import_module(f"{__name__}.seed")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
