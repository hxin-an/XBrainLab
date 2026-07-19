"""Model holder for storing model class, parameters, and pretrained weights."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import torch


class ModelHolder:
    """Class for storing model information

    Holds the model class, model parameters, and pretrained weight path.

    Attributes:
        target_model (type): Model class, inherited from `torch.nn.Module`
        model_params_map (dict): Model parameters
        pretrained_weight_path (str): Path to pretrained weight

    """

    def __init__(
        self,
        target_model: type,
        model_params_map: dict,
        pretrained_weight_path: str | None = None,
    ):
        self.target_model = target_model
        self._model_params_map = deepcopy(model_params_map)
        self.pretrained_weight_path = pretrained_weight_path

    @property
    def model_params_map(self) -> dict[str, Any]:
        """Return an isolated snapshot of configured model parameters."""
        return deepcopy(self._model_params_map)

    def get_model_desc_str(self) -> str:
        """Get a human-readable model description string.

        Returns:
            A string containing the model name and its non-empty parameters,
            formatted as ``'ModelName (param1=val1, param2=val2)'``.

        """
        option_list = [
            f"{name}={value}"
            for name, value in self._model_params_map.items()
            if value is not None
        ]
        options = ", ".join(option_list)
        return f"{self.target_model.__name__} ({options})"

    def get_model(self, args) -> torch.nn.Module:
        """Instantiate the model with stored and additional parameters.

        If a pretrained weight path is set, loads the state dict into the model.

        Args:
            args: Additional keyword arguments to pass to the model constructor
                (e.g., input shape parameters from the dataset).

        Returns:
            A new instance of the target model with weights loaded if applicable.

        """
        model = self.target_model(**self._model_params_map, **args)
        if self.pretrained_weight_path:
            model.load_state_dict(
                torch.load(self.pretrained_weight_path, weights_only=True),
            )
        return model
