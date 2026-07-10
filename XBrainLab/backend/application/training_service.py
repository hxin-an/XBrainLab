"""Training command handlers for the application command spine."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import torch

from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.model_base.SCCNet import SCCNet
from XBrainLab.backend.model_base.ShallowConvNet import ShallowConvNet
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.backend.utils.logger import logger

from .commands import (
    ClearTrainingHistoryCommand,
    Command,
    ConfigureTrainingCommand,
    StopTrainingCommand,
    TrainCommand,
)
from .errors import PreconditionError
from .resource_guard import check_training_resource_preflight
from .state import ApplicationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]


class TrainingCommandService:
    """Handle model configuration and training lifecycle commands."""

    def __init__(
        self,
        *,
        training: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.training = training
        self._get_state = get_state

    def handle_configure_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, ConfigureTrainingCommand):
            raise TypeError("Invalid command for configure_training")
        if command.training_option is not None:
            self.training.apply_configuration(
                model_holder=None,
                training_option=command.training_option,
                update_model=False,
                update_option=True,
            )
            return "Training configured.", {
                "training_option": self.training_option_snapshot(
                    command.training_option,
                ),
            }

        option_values = (command.epoch, command.batch_size, command.learning_rate)
        wants_option = any(value is not None for value in option_values)
        if wants_option and not all(value is not None for value in option_values):
            raise PreconditionError(
                "epoch, batch_size, and learning_rate are required.",
            )
        if not command.model_name and not wants_option:
            raise PreconditionError(
                "epoch, batch_size, and learning_rate are required.",
            )

        option: TrainingOption | None = None
        if wants_option:
            self._validate_training_numbers(command)
            epoch = command.epoch
            batch_size = command.batch_size
            learning_rate = command.learning_rate
            if epoch is None or batch_size is None or learning_rate is None:
                raise AssertionError("Validated training values must be present")
            optim_class = self._resolve_optimizer(command.optimizer)
            use_cpu, gpu_idx = self._resolve_training_device(command.device)
            evaluation_option = self._resolve_training_evaluation(
                command.evaluation_option,
            )
            option = TrainingOption(
                output_dir=command.output_dir,
                optim=optim_class,
                optim_params=dict(command.optimizer_params),
                use_cpu=use_cpu,
                gpu_idx=gpu_idx,
                epoch=epoch,
                bs=batch_size,
                lr=learning_rate,
                checkpoint_epoch=command.save_checkpoints_every,
                evaluation_option=evaluation_option,
                repeat_num=command.repeat,
            )

        holder: ModelHolder | None = None
        if command.model_name:
            model_class = self._resolve_model_class(command.model_name)
            holder = ModelHolder(
                model_class,
                dict(command.model_params),
                command.pretrained_weight_path,
            )

        self.training.apply_configuration(
            model_holder=holder,
            training_option=option,
            update_model=holder is not None,
            update_option=option is not None,
        )
        if option is None:
            return f"Model configured: {command.model_name}."
        diagnostics: dict[str, Any] = {
            "training_option": self.training_option_snapshot(option),
        }
        if holder is not None:
            diagnostics["model_name"] = self.model_name(holder)
        return "Training configured.", diagnostics

    def handle_train(self, command: Command) -> HandlerResult:
        if not isinstance(command, TrainCommand):
            raise TypeError("Invalid command for train")
        context = self._resource_preflight_context()
        preflight = check_training_resource_preflight(
            context.get("datasets", []),
            context.get("training_option"),
            context.get("model_holder"),
        )
        if not preflight.ok:
            raise PreconditionError(
                preflight.message,
                diagnostics={"resource_preflight": preflight.diagnostics},
            )
        self.training.start_training(
            append=command.append,
            interactive=command.interactive,
        )
        return (
            "Training started.",
            {
                "append": command.append,
                "interactive": command.interactive,
                "resource_preflight": preflight.diagnostics,
            },
        )

    def _resource_preflight_context(self) -> dict[str, Any]:
        getter = getattr(self.training, "get_resource_preflight_context", None)
        if callable(getter):
            value = getter()
            if isinstance(value, dict):
                return dict(value)
        return {"datasets": [], "training_option": None}

    def handle_stop_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, StopTrainingCommand):
            raise TypeError("Invalid command for stop_training")
        stopped = self.training.stop_training(wait_timeout=command.wait_timeout)
        return (
            "Training stopped." if stopped else "Training stop requested.",
            {"stopped": bool(stopped), "wait_timeout": command.wait_timeout},
        )

    def handle_clear_training_history(self, command: Command) -> HandlerResult:
        if not isinstance(command, ClearTrainingHistoryCommand):
            raise TypeError("Invalid command for clear_training_history")
        before = self._get_state().evaluation
        self.training.clear_history()
        try:
            self.training.notify("training_updated")
        except Exception:
            logger.debug("Training-history clear notification failed", exc_info=True)
        return (
            "Training history cleared.",
            {
                "plan_count_before": before.total_plans,
                "run_count_before": before.total_runs,
                "finished_run_count_before": before.finished_runs,
            },
        )

    def clear_configuration(self, training_manager: Any | None) -> None:
        """Clear model/training/saliency configuration for the active dataset."""
        if training_manager is None:
            return
        training_manager.model_holder = None
        training_manager.training_option = None
        training_manager.saliency_params = None
        try:
            self.training.notify("config_changed")
        except Exception:
            logger.debug("Training config reset notification failed", exc_info=True)

    @staticmethod
    def model_name(model_holder: Any) -> str | None:
        target_model = getattr(model_holder, "target_model", None)
        if target_model is None:
            return None
        return getattr(target_model, "__name__", str(target_model))

    @staticmethod
    def model_params_snapshot(model_holder: Any) -> dict[str, Any]:
        params = getattr(model_holder, "model_params_map", None)
        if not isinstance(params, dict):
            return {}
        return dict(params)

    @staticmethod
    def training_option_snapshot(option: Any) -> dict[str, Any]:
        if option is None:
            return {}
        return {
            "epoch": getattr(option, "epoch", None),
            "batch_size": getattr(option, "bs", None),
            "learning_rate": getattr(option, "lr", None),
            "repeat": getattr(option, "repeat_num", None),
            "device": option.get_device() if hasattr(option, "get_device") else None,
            "optimizer": option.get_optim_name()
            if hasattr(option, "get_optim_name")
            else None,
            "checkpoint_epoch": getattr(option, "checkpoint_epoch", None),
            "output_dir": getattr(option, "output_dir", None),
        }

    @staticmethod
    def _resolve_model_class(model_name: str) -> type:
        models_map = {
            "eegnet": EEGNet,
            "sccnet": SCCNet,
            "shallowconvnet": ShallowConvNet,
        }
        model_class = models_map.get(model_name.lower())
        if model_class is None:
            raise ValueError(f"Unknown model architecture: {model_name}")
        return model_class

    @staticmethod
    def _resolve_optimizer(name: str) -> type[torch.optim.Optimizer]:
        optimizers_map: dict[str, type[torch.optim.Optimizer]] = {
            "adam": torch.optim.Adam,
            "sgd": torch.optim.SGD,
            "adamw": torch.optim.AdamW,
        }
        optimizer = optimizers_map.get(str(name).strip().lower())
        if optimizer is None:
            raise ValueError(f"Unknown optimizer: {name}")
        return optimizer

    @staticmethod
    def _resolve_training_device(device: str) -> tuple[bool, int | None]:
        normalized = str(device or "auto").strip().lower()
        if normalized in {"cpu", "none"}:
            return True, None
        if normalized in {"auto", "cuda", "gpu"}:
            return False, 0
        if normalized.startswith("cuda:"):
            try:
                index = int(normalized.split(":", 1)[1])
            except (TypeError, ValueError):
                raise ValueError(f"Unknown training device: {device}") from None
            if index < 0:
                raise ValueError(f"Unknown training device: {device}")
            return False, index
        try:
            index = int(normalized)
        except ValueError:
            raise ValueError(f"Unknown training device: {device}") from None
        if index < 0:
            raise ValueError(f"Unknown training device: {device}")
        return False, index

    @staticmethod
    def _resolve_training_evaluation(
        value: str | None,
    ) -> TrainingEvaluation:
        if value is None:
            return TrainingEvaluation.LAST_EPOCH
        normalized = str(value).strip().lower()
        for option in TrainingEvaluation:
            if normalized in {option.name.lower(), option.value.lower()}:
                return option
        raise ValueError(f"Unknown training evaluation: {value}")

    @staticmethod
    def _validate_training_numbers(command: ConfigureTrainingCommand) -> None:
        if command.epoch is None or command.epoch <= 0:
            raise ValueError("epoch must be greater than zero")
        if command.batch_size is None or command.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if (
            command.learning_rate is None
            or not math.isfinite(command.learning_rate)
            or command.learning_rate <= 0
        ):
            raise ValueError("learning_rate must be greater than zero")
        if command.repeat <= 0:
            raise ValueError("repeat must be greater than zero")
        if command.save_checkpoints_every < 0:
            raise ValueError("save_checkpoints_every cannot be negative")
