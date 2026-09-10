"""Model holder for storing model class, parameters, and pretrained weights."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import torch

ModelFactory = Callable[..., torch.nn.Module]


class ModelHolder:
    """Class for storing model information

    Holds the model class, model parameters, and pretrained weight path.

    Attributes:
        target_model: Model class or factory returning a `torch.nn.Module`.
        model_params_map (dict): Model parameters
        pretrained_weight_path (str): Path to pretrained weight

    """

    def __init__(
        self,
        target_model: ModelFactory,
        model_params_map: dict[str, Any],
        pretrained_weight_path: str | None = None,
        *,
        model_id: str | None = None,
        display_name: str | None = None,
        provider: str = "xbrainlab",
        source_revision: str = "xbrainlab",
    ):
        self.target_model = target_model
        self._model_params_map = deepcopy(model_params_map)
        self.pretrained_weight_path = pretrained_weight_path
        self.model_id = model_id or getattr(target_model, "__name__", str(target_model))
        self.display_name = display_name or getattr(
            target_model,
            "__name__",
            str(target_model),
        )
        self.provider = str(provider)
        self.source_revision = str(source_revision)

    @property
    def model_params_map(self) -> dict[str, Any]:
        """Return an isolated snapshot of configured model parameters."""
        return deepcopy(self._model_params_map)

    @property
    def catalog_identity(self) -> dict[str, str]:
        """Return the stable model/provider identity bound to new artifacts."""
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "source_revision": self.source_revision,
        }

    def effective_model_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Select channel metadata using the model factory contract."""
        model_args = dict(args)
        accepts_signal_context = bool(
            getattr(self.target_model, "__xbrainlab_accepts_signal_context__", False)
        )
        required_inputs = getattr(
            self.target_model,
            "__xbrainlab_required_signal_context_inputs__",
            None,
        )
        if not accepts_signal_context or (
            required_inputs is not None and "chs_info" not in required_inputs
        ):
            model_args.pop("chs_info", None)
        return model_args

    def get_model(self, args) -> torch.nn.Module:
        """Instantiate the model with stored and additional parameters.

        If a pretrained weight path is set, loads the state dict into the model.

        Args:
            args: Additional keyword arguments to pass to the model constructor
                (e.g., input shape parameters from the dataset).

        Returns:
            A new instance of the target model with weights loaded if applicable.

        """
        model_args = self.effective_model_args(args)
        model = self.target_model(**self._model_params_map, **model_args)
        if self.pretrained_weight_path:
            model.load_state_dict(
                torch.load(self.pretrained_weight_path, weights_only=True),
            )
        return model
