"""Training command handlers for the application command spine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import torch

from XBrainLab.backend.model_base.model_catalog import get_model_spec
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.input_contract import (
    normalize_non_negative_integer,
    normalize_positive_integer,
    normalize_training_input,
)
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger

from .commands import (
    ClearTrainingHistoryCommand,
    Command,
    ConfigureTrainingCommand,
    StopTrainingCommand,
    TrainCommand,
)
from .errors import ApplicationError, PreconditionError
from .resource_guard import (
    ResourcePreflightResult,
    check_training_resource_preflight,
)
from .results import ErrorType
from .state import ApplicationStateSnapshot
from .training_resource_receipt import (
    TrainingResourceReceiptAuthority,
)
from .training_runtime import TrainingCommandRuntimePort
from .training_snapshot import (
    model_name as snapshot_model_name,
)
from .training_snapshot import (
    model_params_snapshot as build_model_params_snapshot,
)
from .training_snapshot import (
    training_option_snapshot as build_training_option_snapshot,
)

HandlerResult = str | tuple[str, dict[str, Any]]


class TrainingCommandService:
    """Handle model configuration and training lifecycle commands."""

    def __init__(
        self,
        *,
        training: Any,
        training_runtime: TrainingCommandRuntimePort,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.training = training
        self.training_runtime = training_runtime
        self._get_state = get_state
        self._resource_receipts = TrainingResourceReceiptAuthority()

    def handle_configure_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, ConfigureTrainingCommand):
            raise TypeError("Invalid command for configure_training")

        option_values = (command.epoch, command.batch_size, command.learning_rate)
        wants_option = (
            any(value is not None for value in option_values)
            or command.seed is not None
        )
        if wants_option and not all(value is not None for value in option_values):
            raise PreconditionError(
                "Training epochs, batch size, and learning rate are required.",
            )
        if not command.model_name and not wants_option:
            raise PreconditionError(
                "Training epochs, batch size, and learning rate are required.",
            )

        repeat = normalize_positive_integer("repeat", command.repeat)
        save_checkpoints_every = normalize_non_negative_integer(
            "save_checkpoints_every",
            command.save_checkpoints_every,
        )
        optim_class = self._resolve_optimizer(command.optimizer)
        use_cpu, gpu_idx = self._resolve_training_device(command.device)
        evaluation_option = self._resolve_training_evaluation(
            command.evaluation_option,
        )

        option: TrainingOption | None = None
        if wants_option:
            epoch, batch_size, learning_rate = self._normalize_training_numbers(
                command,
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
                checkpoint_epoch=save_checkpoints_every,
                evaluation_option=evaluation_option,
                repeat_num=repeat,
                seed=command.seed,
            )

        holder: ModelHolder | None = None
        if command.model_name:
            model_spec = get_model_spec(command.model_name)
            holder = ModelHolder(
                model_spec.factory,
                dict(command.model_params),
                command.pretrained_weight_path,
                model_id=model_spec.model_id,
                display_name=model_spec.display_name,
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

    def handle_train(
        self,
        command: Command,
        *,
        defer_synchronous_completion: bool = False,
    ) -> HandlerResult:
        if not isinstance(command, TrainCommand):
            raise TypeError("Invalid command for train")
        preflight, receipt_reused = self._resolve_resource_preflight(
            command,
        )
        handoff_generation = self.training.start_training(
            append=command.append,
            interactive=command.interactive or defer_synchronous_completion,
        )
        if (
            isinstance(handoff_generation, bool)
            or not isinstance(handoff_generation, int)
            or handoff_generation < 1
        ):
            raise RuntimeError(
                "Training controller returned an invalid terminal handoff generation."
            )
        trainer_identity = self._require_training_identity(
            self._training_terminal_outcome()
        )
        completion_diagnostics: dict[str, Any] = {}
        if defer_synchronous_completion and not command.interactive:
            completion_diagnostics["synchronous_completion_deferred"] = True
        elif not command.interactive:
            _message, completion_diagnostics = self.complete_synchronous_training(
                trainer_identity
            )
        return (
            (
                "Training started."
                if command.interactive or defer_synchronous_completion
                else "Training completed."
            ),
            {
                "append": command.append,
                "interactive": command.interactive,
                "training_handoff_generation": handoff_generation,
                "training_trainer_identity": trainer_identity,
                "resource_preflight": {
                    **preflight.to_diagnostics(),
                    "confirmation_receipt_reused": receipt_reused,
                },
                **completion_diagnostics,
            },
        )

    def complete_synchronous_training(
        self,
        expected_trainer_identity: str,
    ) -> tuple[str, dict[str, Any]]:
        """Verify one deferred synchronous run after its worker has exited."""
        self._raise_for_synchronous_training_failure(expected_trainer_identity)
        outcome = self._training_terminal_outcome(expected_trainer_identity)
        return (
            "Training completed.",
            {
                "terminal_outcome": outcome.state.value,
                "training_run": (
                    outcome.run.to_dict() if outcome.run is not None else None
                ),
            },
        )

    def _raise_for_synchronous_training_failure(
        self,
        expected_trainer_identity: str,
    ) -> None:
        """Require typed completion before publishing synchronous success."""
        outcome = self._training_terminal_outcome(expected_trainer_identity)
        if outcome.state is TrainingOutcomeState.COMPLETED:
            return
        if outcome.state is TrainingOutcomeState.FAILED:
            failure = outcome.detail or "Training failed."
        elif outcome.state is TrainingOutcomeState.CANCELLED:
            failure = "Training was cancelled."
        elif outcome.state is TrainingOutcomeState.STOP_REQUESTED:
            failure = "Training stop was requested, but the worker has not exited."
        elif outcome.state is TrainingOutcomeState.RUNNING:
            failure = "Training did not reach a terminal outcome."
        else:
            failure = "Training outcome could not be verified."
        raise ApplicationError(
            message=failure,
            error_type=ErrorType.TRAINING,
            recoverable=True,
            diagnostics={
                "training_failed": True,
                "cuda_oom": "out of memory" in failure.lower(),
                "terminal_outcome": outcome.state.value,
                "training_run": (
                    outcome.run.to_dict() if outcome.run is not None else None
                ),
            },
        )

    def _training_terminal_outcome(
        self,
        expected_trainer_identity: str | None = None,
    ) -> TrainingTerminalOutcome:
        outcome = self.training_runtime.terminal_outcome()
        if expected_trainer_identity is None:
            return outcome
        run = outcome.run
        if run is None or run.trainer_id != expected_trainer_identity:
            raise ApplicationError(
                message=(
                    "Training runtime changed before completion could be verified."
                ),
                error_type=ErrorType.TRAINING,
                recoverable=True,
                diagnostics={
                    "training_failed": True,
                    "training_trainer_identity": expected_trainer_identity,
                    "observed_training_trainer_identity": (
                        run.trainer_id if run is not None else None
                    ),
                },
            )
        return outcome

    @staticmethod
    def _require_training_identity(outcome: TrainingTerminalOutcome) -> str:
        run = outcome.run
        if run is None or not run.trainer_id.strip():
            raise ApplicationError(
                message="Training runtime identity is unavailable.",
                error_type=ErrorType.TRAINING,
                recoverable=True,
                diagnostics={
                    "training_failed": True,
                    "training_trainer_identity_invalid": True,
                },
            )
        return run.trainer_id

    def get_resource_preflight(self) -> ResourcePreflightResult:
        """Check the current application-owned training configuration."""
        context = self._resource_preflight_context()
        return self._build_resource_preflight(TrainCommand(), context)

    def _build_resource_preflight(
        self,
        command: TrainCommand,
        context: dict[str, Any],
    ) -> ResourcePreflightResult:
        """Build preflight diagnostics and fingerprints for one train command."""
        preflight = check_training_resource_preflight(
            context.get("datasets", []),
            context.get("training_option"),
            context.get("model_holder"),
        )
        option = context.get("training_option")
        diagnostics = {
            **preflight.diagnostics,
            "payload_type": "training_resource_preflight",
            "model_name": self.model_name(context.get("model_holder")),
            "training_batch_size": getattr(option, "bs", None),
        }
        return self._resource_receipts.annotate(
            command,
            context,
            ResourcePreflightResult(
                issues=preflight.issues,
                warnings=preflight.warnings,
                unknowns=preflight.unknowns,
                diagnostics=diagnostics,
            ),
        )

    def _resource_preflight_context(self) -> dict[str, Any]:
        return self.training_runtime.resource_context().to_mapping()

    def _resolve_resource_preflight(
        self,
        command: TrainCommand,
    ) -> tuple[ResourcePreflightResult, bool]:
        """Atomically validate and consume one exact warning receipt."""
        context = self._resource_preflight_context()
        preflight = self._build_resource_preflight(command, context)
        receipt_reused = self._resource_receipts.authorize(command, preflight)
        return preflight, receipt_reused

    def handle_stop_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, StopTrainingCommand):
            raise TypeError("Invalid command for stop_training")
        stopped = self.training_runtime.stop_training(
            wait_timeout=command.wait_timeout,
        )
        outcome = self._training_terminal_outcome()
        return (
            "Training stopped." if stopped else "Training stop requested.",
            {
                "stopped": bool(stopped),
                "wait_timeout": command.wait_timeout,
                "terminal_outcome": outcome.state.value,
                "training_run": (
                    outcome.run.to_dict() if outcome.run is not None else None
                ),
            },
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

    @staticmethod
    def model_name(model_holder: Any) -> str | None:
        return snapshot_model_name(model_holder)

    @staticmethod
    def model_params_snapshot(model_holder: Any) -> dict[str, Any]:
        return build_model_params_snapshot(model_holder)

    @staticmethod
    def training_option_snapshot(option: Any) -> dict[str, Any]:
        return build_training_option_snapshot(option)

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
        legacy_aliases = {
            "test_acc": TrainingEvaluation.VAL_ACC,
            "best testing performance": TrainingEvaluation.VAL_ACC,
            "test_auc": TrainingEvaluation.VAL_AUC,
            "best testing auc": TrainingEvaluation.VAL_AUC,
        }
        migrated = legacy_aliases.get(normalized)
        if migrated is not None:
            logger.warning(
                "Migrating legacy test-based model selection %r to %s",
                value,
                migrated.value,
            )
            return migrated
        for option in TrainingEvaluation:
            if normalized in {option.name.lower(), option.value.lower()}:
                return option
        raise ValueError(f"Unknown training evaluation: {value}")

    @staticmethod
    def _normalize_training_numbers(
        command: ConfigureTrainingCommand,
    ) -> tuple[int, int, float]:
        training_input = normalize_training_input(
            {
                "epoch": command.epoch,
                "batch_size": command.batch_size,
                "learning_rate": command.learning_rate,
            }
        )

        return (
            training_input.epoch,
            training_input.batch_size,
            training_input.learning_rate,
        )
