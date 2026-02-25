"""XBrainLab: An EEG brain-computer interface analysis platform.

This package provides the core modules for EEG data loading, preprocessing,
model training, evaluation, and visualization through a PyQt6-based GUI.
"""

from importlib.metadata import PackageNotFoundError, version

from .backend.study import Study

try:
    __version__ = version("xbrainlab")
except PackageNotFoundError:
    __version__ = "0.5.2"  # fallback for editable / non-installed mode

__all__ = ["Study", "__version__"]
