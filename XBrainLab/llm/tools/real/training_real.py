"""Real implementations of model training tools.

These tools interact with the ApplicationService command spine to configure
and launch actual deep-learning training runs.
"""

from typing import Any

from .. import execute_real_application_tool
from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
    BaseStopTrainingTool,
)
from ..result_contract import ToolResult

_HOST_SETTING_CONFIRMATION_PARAM = "assistant_setting_confirmation"


def _preserve_host_setting_confirmation(
    params: dict[str, Any],
    kwargs: dict[str, Any],
) -> None:
    if _HOST_SETTING_CONFIRMATION_PARAM in kwargs:
        params[_HOST_SETTING_CONFIRMATION_PARAM] = kwargs[
            _HOST_SETTING_CONFIRMATION_PARAM
        ]


class RealSetModelTool(BaseSetModelTool):
    """Real implementation of :class:`BaseSetModelTool`."""

    def execute(
        self,
        study: Any,
        model_name: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Set the deep learning model architecture.

        Args:
            study: The global ``Study`` instance.
            model_name: Name of the model architecture (e.g.,
                ``'EEGNet'``, ``'SCCNet'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.

        """
        params = {"model_name": model_name}
        _preserve_host_setting_confirmation(params, kwargs)
        return execute_real_application_tool(study, self.name, params)


class RealConfigureTrainingTool(BaseConfigureTrainingTool):
    """Real implementation of :class:`BaseConfigureTrainingTool`."""

    def execute(
        self,
        study: Any,
        model_name: str | None = None,
        epoch: int | None = None,
        batch_size: int | None = None,
        learning_rate: float | None = None,
        repeat: int = 1,
        device: str = "cpu",
        optimizer: str = "adam",
        evaluation_option: str = "last_epoch",
        save_checkpoints_every: int = 0,
        output_dir: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Configure training hyperparameters via the backend.

        Args:
            study: The global ``Study`` instance.
            model_name: Optional architecture configured atomically with options.
            epoch: Number of training epochs.
            batch_size: Mini-batch size.
            learning_rate: Optimiser learning rate.
            repeat: Number of experiment repetitions.
            device: Compute device (``'cpu'`` or ``'cuda'``).
            optimizer: Optimiser name (``'adam'``, ``'sgd'``, ``'adamw'``).
            evaluation_option: Validation metric used to select the saved model.
            save_checkpoints_every: Checkpoint save interval (0 = disabled).
            output_dir: Directory for saving training outputs.
            **kwargs: Additional keyword arguments.

        Returns:
            A summary of the configured parameters, or an error message.

        """
        params: dict[str, Any] = {
            "epoch": epoch,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "repeat": repeat,
            "device": device,
            "optimizer": optimizer,
            "evaluation_option": evaluation_option,
            "save_checkpoints_every": save_checkpoints_every,
        }
        if model_name is not None:
            params["model_name"] = model_name
        if output_dir is not None:
            params["output_dir"] = output_dir
        _preserve_host_setting_confirmation(params, kwargs)
        return execute_real_application_tool(
            study,
            self.name,
            params,
        )


class RealStartTrainingTool(BaseStartTrainingTool):
    """Real implementation of :class:`BaseStartTrainingTool`.

    Launches the training process through ApplicationService.
    """

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Start the training process in a background thread.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {
                "append": kwargs.get("append", True),
                "interactive": kwargs.get("interactive", True),
                "confirmed": kwargs.get("confirmed", False),
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealStopTrainingTool(BaseStopTrainingTool):
    """Request training cancellation through ApplicationService."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Stop the active run without waiting on the UI thread."""
        return execute_real_application_tool(study, self.name, {})
