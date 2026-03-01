"""Backend class resolver for real tool implementations.

Maps string identifiers (from LLM tool calls) to concrete backend
Python classes for models, preprocessors, and optimisers.
"""

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


class BackendClassRegistry:
    """Registry for mapping string identifiers to backend classes.

    Used by real tool implementations to resolve user/agent inputs
    to concrete Python objects.

    Attributes:
        _MODELS: Mapping from lowercase model name to ``torch.nn.Module``
            subclass.
        _PREPROCESSORS: Mapping from preprocessing operation name to
            the corresponding backend class.
        _OPTIMIZERS: Mapping from lowercase optimiser name to
            ``torch.optim.Optimizer`` subclass.

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
        """Get model class by name (case-insensitive).

        Args:
            name: Model architecture name (e.g., ``'EEGNet'``).

        Returns:
            The corresponding ``torch.nn.Module`` subclass, or ``None``
            if the name is not recognised.

        """
        return cls._MODELS.get(name.lower())

    @classmethod
    def get_preprocessor_class(cls, name: str) -> type | None:
        """Get preprocessor class by name (case-insensitive).

        Args:
            name: Preprocessing operation name (e.g., ``'bandpass'``).

        Returns:
            The corresponding preprocessor class, or ``None`` if the
            name is not recognised.

        """
        return cls._PREPROCESSORS.get(name.lower())

    @classmethod
    def get_optimizer_class(cls, name: str) -> type[torch.optim.Optimizer]:
        """Get optimiser class by name (case-insensitive).

        Falls back to ``torch.optim.Adam`` when the name is not found.

        Args:
            name: Optimiser name (e.g., ``'adamw'``).

        Returns:
            The corresponding ``torch.optim.Optimizer`` subclass.

        """
        return cls._OPTIMIZERS.get(name.lower(), torch.optim.Adam)


# Backward-compatible alias (deprecated — use BackendClassRegistry)
BackendRegistryCompat = BackendClassRegistry
