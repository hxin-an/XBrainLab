"""Fail fast when a standalone validation script imports another checkout."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType

_REPO_MODULE_PREFIXES = ("XBrainLab", "scripts.dev")


def assert_active_checkout_import(repo_root: Path) -> None:
    """Bootstrap and require imports from the script's own checkout."""
    expected_root = repo_root.resolve()
    _assert_loaded_repo_modules(expected_root)

    sys.path[:] = [
        entry for entry in sys.path if Path(entry or ".").resolve() != expected_root
    ]
    sys.path.insert(0, str(expected_root))

    import_module("XBrainLab")

    _assert_loaded_repo_modules(expected_root)


def _assert_loaded_repo_modules(expected_root: Path) -> None:
    """Reject any loaded product or validation module from another checkout."""
    for module_name, module in tuple(sys.modules.items()):
        if not _is_repo_module(module_name) or module is None:
            continue
        locations = _module_locations(module)
        if not locations:
            raise RuntimeError(
                f"Validation cannot verify the checkout for loaded module "
                f"{module_name!r}."
            )
        for location in locations:
            if not location.is_relative_to(expected_root):
                raise RuntimeError(
                    "Validation imported a module from a different checkout. "
                    f"Expected {expected_root}, got {location} for {module_name}. "
                    "Run the script from the intended checkout."
                )


def _is_repo_module(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in _REPO_MODULE_PREFIXES
    )


def _module_locations(module: ModuleType | object) -> tuple[Path, ...]:
    locations: list[Path] = []
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str) and module_file:
        locations.append(Path(module_file).resolve())
    module_path = getattr(module, "__path__", None)
    if module_path is not None:
        for entry in module_path:
            locations.append(Path(entry).resolve())
    return tuple(dict.fromkeys(locations))
