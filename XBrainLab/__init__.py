"""XBrainLab: An EEG brain-computer interface analysis platform.

This package provides the core modules for EEG data loading, preprocessing,
model training, evaluation, and visualization through a PyQt6-based GUI.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend.study import Study

try:
    __version__ = version("xbrainlab")
except PackageNotFoundError:
    __version__ = "0.5.6"  # fallback for editable / non-installed mode

__all__ = ["Study", "__version__"]


def __getattr__(name: str):
    """Load heavy public exports only when callers request them."""
    if name == "Study":
        from .backend.study import Study  # noqa: PLC0415

        return Study
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
