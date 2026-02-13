from typing import ClassVar

import torch

# Backend classes
from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.model_base.SCCNet import SCCNet
from XBrainLab.backend.model_base.ShallowConvNet import ShallowConvNet
from XBrainLab.backend.preprocessor.filtering import Filtering
from XBrainLab.backend.preprocessor.normalize import Normalize
from XBrainLab.backend.preprocessor.resample import Resample
from XBrainLab.backend.preprocessor.time_epoch import TimeEpoch


class ToolRegistry:
    """
    Registry for mapping string identifiers to backend classes.
    Used by Real Tools to resolve user/agent inputs to Python objects.
    """

    _MODELS: ClassVar[dict[str, type[torch.nn.Module]]] = {
        "eegnet": EEGNet,
        "sccnet": SCCNet,
        "shallowconvnet": ShallowConvNet,
    }

    _PREPROCESSORS: ClassVar[dict[str, type]] = {
        "bandpass": Filtering,  # Maps to Filtering class
        "notch": Filtering,  # Maps to Filtering class
        "resample": Resample,
        "normalize": Normalize,
        "epoch": TimeEpoch,
    }

    _OPTIMIZERS: ClassVar[dict[str, type[torch.optim.Optimizer]]] = {
        "adam": torch.optim.Adam,
        "sgd": torch.optim.SGD,
        "adamw": torch.optim.AdamW,
    }

    @classmethod
    def get_model_class(cls, name: str) -> type[torch.nn.Module] | None:
        """Get model class by name (case-insensitive)."""
        return cls._MODELS.get(name.lower())

    @classmethod
    def get_preprocessor_class(cls, name: str) -> type | None:
        """Get preprocessor class by name (case-insensitive)."""
        return cls._PREPROCESSORS.get(name.lower())

    @classmethod
    def get_optimizer_class(cls, name: str) -> type[torch.optim.Optimizer]:
        """Get optimizer class by name (case-insensitive), default to Adam."""
        return cls._OPTIMIZERS.get(name.lower(), torch.optim.Adam)
