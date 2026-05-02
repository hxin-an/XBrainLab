"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any, cast

import numpy as np
import torch

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
    audit_dataset_splits,
)
from XBrainLab.backend.load_data.label_loader import load_label_file
from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.model_base.SCCNet import SCCNet
from XBrainLab.backend.model_base.ShallowConvNet import ShallowConvNet
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import ModelHolder, TrainingEvaluation, TrainingOption
from XBrainLab.backend.utils.logger import logger

from .capabilities import CapabilityPolicy, build_capability_policy
from .commands import (
    AttachLabelsCommand,
    Command,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    ResetSessionCommand,
    SaliencyCommand,
    StopTrainingCommand,
    TrainCommand,
    VisualizeCommand,
    command_name,
)
from .errors import (
    ApplicationError,
    ConfirmationRequiredError,
    PreconditionError,
    map_exception,
)
from .results import ChangedState, CommandResult, ErrorType
from .state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    ErrorSnapshot,
    EvaluationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)

HandlerResult = str | tuple[str, dict[str, Any]]


class ApplicationService:
    """Command-oriented application layer over the existing backend controllers."""

    def __init__(self, study: Study | None = None):
        self.study = study if study is not None else Study()
        self.dataset = self.study.get_controller("dataset")
        self.preprocess = self.study.get_controller("preprocess")
        self.training = self.study.get_controller("training")
        self.evaluation = self.study.get_controller("evaluation")
        self.visualization = self.study.get_controller("visualization")
        self._last_error: ErrorSnapshot | None = None

    def get_state(self) -> ApplicationStateSnapshot:
        """Return a fresh serializable snapshot of backend state."""
        raw_data = list(getattr(self.study, "loaded_data_list", []) or [])
        preprocessed = list(getattr(self.study, "preprocessed_data_list", []) or [])
        epoch_data = getattr(self.study, "epoch_data", None)
        datasets = list(getattr(self.study, "datasets", []) or [])
        trainer = getattr(self.study, "trainer", None)
        model_holder = getattr(self.study, "model_holder", None)
        training_option = getattr(self.study, "training_option", None)
        pipeline_stage = self._pipeline_stage()

        raw_diagnostics = self._safe_call_dict(self.dataset.get_runtime_diagnostics)
        preprocess_diagnostics = self._safe_call_dict(
            self.preprocess.get_runtime_diagnostics,
        )
        event_info = self._safe_call_dict(self.dataset.get_event_info)
        evaluation = self._evaluation_snapshot()

        raw = RawStateSnapshot(
            loaded=bool(raw_data),
            count=len(raw_data),
            files=[self._data_filename(item) for item in raw_data],
            formats=self._raw_formats(raw_data),
            channels=self._raw_channels(raw_data),
            event_total=int(event_info.get("total", 0) or 0),
            unique_events=[
                str(item) for item in event_info.get("unique_labels", []) or []
            ],
            locked=self._safe_bool(self.dataset.is_locked),
            diagnostics=raw_diagnostics,
        )
        preprocessed_state = PreprocessedStateSnapshot(
            available=bool(preprocessed),
            count=len(preprocessed),
            files=[self._data_filename(item) for item in preprocessed],
            is_epoched=self._safe_bool(self.preprocess.is_epoched),
            channel_names=self._safe_list(self.preprocess.get_channel_names),
            operations=self._preprocess_history(preprocessed),
            diagnostics=preprocess_diagnostics,
        )
        epoch = EpochStateSnapshot(
            available=epoch_data is not None,
            exists=epoch_data is not None,
            epoch_count=self._epoch_count(epoch_data),
            n_channels=self._epoch_n_channels(epoch_data),
            n_times=self._epoch_n_times(epoch_data),
            event_names=self._epoch_event_names(epoch_data),
            event_ids=self._epoch_event_ids(epoch_data),
            channel_names=self._epoch_channel_names(epoch_data),
        )
        dataset = DatasetStateSnapshot(
            available=bool(datasets),
            count=len(datasets),
            names=[self._dataset_name(item, idx) for idx, item in enumerate(datasets)],
            locked=raw.locked,
            generator_exists=getattr(self.study, "dataset_generator", None) is not None,
            split_summary=self._dataset_split_summary(datasets),
        )
        training = TrainingStateSnapshot(
            has_model=model_holder is not None,
            model_name=self._model_name(model_holder),
            has_training_option=training_option is not None,
            training_option=self._training_option_snapshot(training_option),
            has_trainer=trainer is not None,
            is_running=self._safe_bool(self.training.is_training),
            plan_count=evaluation.total_plans,
            run_count=evaluation.total_runs,
            finished_run_count=evaluation.finished_runs,
            missing_requirements=self._safe_list(
                self.training.get_missing_requirements
            ),
        )
        visualization = VisualizationStateSnapshot(
            saliency_configured=(
                getattr(self.study, "saliency_params", None) is not None
            ),
            saliency_available=evaluation.finished_runs > 0
            and getattr(self.study, "saliency_params", None) is not None,
            montage_available=self._montage_available(epoch_data),
            channel_positions_available=self._channel_positions_available(epoch_data),
            channel_count=len(epoch.channel_names),
        )
        active_dataset = ActiveDatasetSnapshot(
            has_raw_data=raw.count > 0,
            has_preprocessed_data=preprocessed_state.count > 0,
            has_epoch_data=epoch.exists,
            has_datasets=dataset.count > 0,
            is_locked=raw.locked,
        )
        active_training = ActiveTrainingSnapshot(
            has_model=training.has_model,
            has_training_option=training.has_training_option,
            has_trainer=training.has_trainer,
            is_running=training.is_running,
        )
        return ApplicationStateSnapshot(
            pipeline_stage=pipeline_stage,
            raw=raw,
            preprocessed=preprocessed_state,
            epoch=epoch,
            dataset=dataset,
            training=training,
            evaluation=evaluation,
            visualization=visualization,
            active_dataset=active_dataset,
            active_training=active_training,
            last_error=self._last_error,
        )

    def get_capabilities(self) -> CapabilityPolicy:
        """Return command capabilities for the current state."""
        return build_capability_policy(self.get_state())

    def execute(self, command: Command) -> CommandResult:
        """Execute a command and return a result envelope."""
        before = self.get_state()
        name = command_name(command)
        try:
            self._ensure_command_allowed(command, before)
            message, diagnostics = self._normalize_handler_result(
                self._execute_allowed(command, name),
            )
            self._last_error = None
            after = self.get_state()
            return CommandResult.success_result(
                command_name=name.value,
                message=message,
                state=after,
                changed_state=self._changed_state(before, after),
                diagnostics=diagnostics,
            )
        except Exception as exc:
            app_error = map_exception(exc)
            self._last_error = ErrorSnapshot(
                error_type=app_error.error_type.value,
                message=app_error.message,
                recoverable=app_error.recoverable,
            )
            after = self.get_state()
            return CommandResult.failure_result(
                command_name=name.value,
                message=app_error.message,
                state=after,
                changed_state=self._changed_state(before, after),
                error_type=app_error.error_type,
                recoverable=app_error.recoverable,
                error_message=app_error.message,
                diagnostics={
                    **app_error.diagnostics,
                    "exception_type": exc.__class__.__name__,
                },
            )

    def _execute_allowed(self, command: Command, name: CommandName) -> HandlerResult:
        handlers: dict[CommandName, Callable[[Command], HandlerResult]] = {
            CommandName.LOAD_DATA: self._handle_load_data,
            CommandName.ATTACH_LABELS: self._handle_attach_labels,
            CommandName.PREPROCESS: self._handle_preprocess,
            CommandName.CREATE_EPOCH: self._handle_create_epoch,
            CommandName.GENERATE_DATASET: self._handle_generate_dataset,
            CommandName.CONFIGURE_TRAINING: self._handle_configure_training,
            CommandName.TRAIN: self._handle_train,
            CommandName.STOP_TRAINING: self._handle_stop_training,
            CommandName.EVALUATE: self._handle_evaluate,
            CommandName.VISUALIZE: self._handle_visualize,
            CommandName.SALIENCY: self._handle_saliency,
            CommandName.RESET_SESSION: self._handle_reset_session,
            CommandName.NEW_SESSION: self._handle_new_session,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ApplicationError(
                message=(
                    f"{name.value} is reserved in the command contract but is "
                    "not implemented by ApplicationService yet."
                ),
                error_type=ErrorType.UNSUPPORTED_COMMAND,
                recoverable=True,
            )
        return handler(command)

    def load_data(self, paths: list[str]) -> CommandResult:
        """Execute a load-data command."""
        return self.execute(LoadDataCommand(paths=paths))

    def attach_labels(self, mapping: dict[str, str]) -> CommandResult:
        """Execute an attach-labels command."""
        return self.execute(AttachLabelsCommand(mapping=mapping))

    def preprocess_data(self, command: PreprocessCommand) -> CommandResult:
        """Execute a preprocessing command."""
        return self.execute(command)

    def create_epoch(
        self,
        t_min: float,
        t_max: float,
        baseline: list[float] | tuple[float | None, float | None] | None = None,
        event_ids: list[str] | dict[str, int] | None = None,
    ) -> CommandResult:
        """Execute an epoching command."""
        return self.execute(
            CreateEpochCommand(
                t_min=t_min,
                t_max=t_max,
                baseline=baseline,
                event_ids=event_ids,
            ),
        )

    def generate_dataset(self, command: GenerateDatasetCommand) -> CommandResult:
        """Execute a dataset-generation command."""
        return self.execute(command)

    def configure_training(self, command: ConfigureTrainingCommand) -> CommandResult:
        """Execute a training-configuration command."""
        return self.execute(command)

    def train(self, command: TrainCommand | None = None) -> CommandResult:
        """Execute a train command."""
        return self.execute(command or TrainCommand())

    def stop_training(self) -> CommandResult:
        """Execute a stop-training command."""
        return self.execute(StopTrainingCommand())

    def reset_session(self, confirmed: bool = False) -> CommandResult:
        """Execute a session reset command."""
        return self.execute(ResetSessionCommand(confirmed=confirmed))

    def new_session(self, confirmed: bool = False) -> CommandResult:
        """Execute a new-session command for the single-session shell."""
        return self.execute(NewSessionCommand(confirmed=confirmed))

    def evaluate(self, command: EvaluateCommand | None = None) -> CommandResult:
        """Execute an evaluation query command."""
        return self.execute(command or EvaluateCommand())

    def visualize(self, command: VisualizeCommand | None = None) -> CommandResult:
        """Execute a visualization query command."""
        return self.execute(command or VisualizeCommand())

    def saliency(self, command: SaliencyCommand | None = None) -> CommandResult:
        """Execute a saliency setup/query command."""
        return self.execute(command or SaliencyCommand())

    def _ensure_command_allowed(
        self,
        command: Command,
        state: ApplicationStateSnapshot,
    ) -> None:
        name = command_name(command)
        capability = build_capability_policy(state).get(name)
        if (
            name in (CommandName.RESET_SESSION, CommandName.NEW_SESSION)
            and capability.confirmation_required
            and isinstance(command, (ResetSessionCommand, NewSessionCommand))
            and not command.confirmed
        ):
            raise ConfirmationRequiredError(f"{name.value} requires confirmation.")
        if not capability.enabled:
            raise PreconditionError("; ".join(capability.reasons))

    def _handle_load_data(self, command: Command) -> HandlerResult:
        if not isinstance(command, LoadDataCommand):
            raise TypeError("Invalid command for load_data")
        if not command.paths:
            raise PreconditionError("paths list cannot be empty.")
        count, errors = self.dataset.import_files(command.paths)
        if count == 0 and errors:
            error_text = "; ".join(str(error) for error in errors)
            error_type = ErrorType.RUNTIME
            if "Unsupported format" in error_text:
                error_type = ErrorType.UNSUPPORTED_FORMAT
            elif "File corrupted" in error_text:
                error_type = ErrorType.FILE_CORRUPTED
            raise ApplicationError(
                message=f"Failed to load data: {errors}",
                error_type=error_type,
                recoverable=True,
                diagnostics={"success_count": 0, "errors": errors},
            )
        if errors:
            return (
                f"Loaded {count} file(s) with errors: {errors}",
                {"success_count": count, "errors": errors},
            )
        return f"Loaded {count} file(s).", {"success_count": count, "errors": []}

    def _handle_attach_labels(self, command: Command) -> HandlerResult:
        if not isinstance(command, AttachLabelsCommand):
            raise TypeError("Invalid command for attach_labels")
        if not command.mapping:
            raise PreconditionError("mapping is required.")

        data_list = self.dataset.get_loaded_data_list()
        label_map: dict[str, Any] = {}
        file_mapping: dict[str, str] = {}
        target_files: list[Any] = []
        errors: list[str] = []

        for raw in data_list:
            label_path = self._resolve_label_attachment_path(raw, command.mapping)
            if not label_path:
                continue
            try:
                if label_path not in label_map:
                    label_map[label_path] = load_label_file(label_path)
                target_files.append(raw)
                file_mapping[raw.get_filepath()] = label_path
            except Exception as exc:
                filename = self._data_filename(raw)
                errors.append(f"{filename}: {exc!s}")
                logger.error(
                    "Failed to attach label for %s: %s",
                    filename,
                    exc,
                    exc_info=True,
                )

        if not target_files:
            return (
                "No labels attached. Check file name mapping.",
                {"success_count": 0, "errors": errors},
            )

        event_name_map = self._build_default_label_name_map(label_map)
        count = self.dataset.apply_labels_batch(
            target_files,
            label_map,
            file_mapping,
            event_name_map,
            None,
        )
        return (
            f"Attached labels to {count} file(s).",
            {"success_count": count, "errors": errors},
        )

    def _handle_preprocess(self, command: Command) -> HandlerResult:
        if not isinstance(command, PreprocessCommand):
            raise TypeError("Invalid command for preprocess")
        operation = PreprocessOperation(command.operation)
        if operation == PreprocessOperation.BANDPASS:
            low_freq = self._require(command.low_freq, "low_freq")
            high_freq = self._require(command.high_freq, "high_freq")
            notch_freqs = [command.notch_freq] if command.notch_freq else None
            self.preprocess.apply_filter(low_freq, high_freq, notch_freqs)
            return f"Applied bandpass filter ({low_freq}-{high_freq} Hz)."
        if operation == PreprocessOperation.NOTCH:
            freq = self._require(command.notch_freq, "notch_freq")
            self.preprocess.apply_filter(None, None, [freq])
            return f"Applied notch filter ({freq} Hz)."
        if operation == PreprocessOperation.RESAMPLE:
            rate = self._require(command.rate, "rate")
            self.preprocess.apply_resample(rate)
            return f"Resampled data to {rate} Hz."
        if operation == PreprocessOperation.NORMALIZE:
            method = self._require(command.method, "method")
            self.preprocess.apply_normalization(method)
            return f"Normalized data using {method}."
        if operation == PreprocessOperation.REREFERENCE:
            if command.channels:
                ref_channels = command.channels
                method = ", ".join(command.channels)
            else:
                method = self._require(command.method, "method")
                ref_channels: str | list[str] = (
                    "average" if method == "average" else [method]
                )
            self.preprocess.apply_rereference(ref_channels)
            return f"Applied reference: {method}."
        if operation in (
            PreprocessOperation.CHANNEL_SELECTION,
            PreprocessOperation.SELECT_CHANNELS,
        ):
            channels = self._require(command.channels, "channels")
            self.dataset.apply_channel_selection(channels)
            return f"Selected {len(channels)} channel(s)."
        if operation == PreprocessOperation.SET_MONTAGE:
            montage_name = self._require(command.montage_name, "montage_name")
            raise ConfirmationRequiredError(
                "set_montage requires UI confirmation and remains on the "
                f"BackendFacade legacy path for '{montage_name}'."
            )
        if operation == PreprocessOperation.STANDARD:
            return self._handle_standard_preprocess(command)
        raise ValueError(f"Unsupported preprocess operation: {operation}")

    def _handle_standard_preprocess(self, command: PreprocessCommand) -> HandlerResult:
        low_freq = command.low_freq if command.low_freq is not None else 4
        high_freq = command.high_freq if command.high_freq is not None else 40
        with self.preprocess.batch_notifications():
            self.preprocess.apply_filter(low_freq, high_freq, None)
            if command.notch_freq:
                self.preprocess.apply_filter(None, None, [command.notch_freq])
            if command.rate:
                self.preprocess.apply_resample(command.rate)
            if command.method:
                self.preprocess.apply_normalization(command.method)
        return "Standard preprocessing applied."

    def _handle_create_epoch(self, command: Command) -> HandlerResult:
        if not isinstance(command, CreateEpochCommand):
            raise TypeError("Invalid command for create_epoch")
        self.preprocess.apply_epoching(
            command.baseline,
            command.event_ids,
            command.t_min,
            command.t_max,
        )
        return f"Created epochs from {command.t_min}s to {command.t_max}s."

    def _handle_generate_dataset(self, command: Command) -> HandlerResult:
        if not isinstance(command, GenerateDatasetCommand):
            raise TypeError("Invalid command for generate_dataset")
        generator = command.generator
        if generator is None:
            config = self._build_data_splitting_config(command)
            generator = self.study.get_datasets_generator(config)
        self.training.apply_data_splitting(generator)
        count = len(getattr(self.study, "datasets", []) or [])
        return (
            f"Generated {count} dataset(s).",
            {
                "dataset_count": count,
                "split_summary": self._dataset_split_summary(
                    list(getattr(self.study, "datasets", []) or [])
                ),
            },
        )

    def _handle_configure_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, ConfigureTrainingCommand):
            raise TypeError("Invalid command for configure_training")
        if command.training_option is not None:
            self.training.set_training_option(command.training_option)
            return "Training configured.", {
                "training_option": self._training_option_snapshot(
                    command.training_option,
                ),
            }

        if command.model_name:
            model_class = self._resolve_model_class(command.model_name)
            holder = ModelHolder(
                model_class,
                dict(command.model_params),
                command.pretrained_weight_path,
            )
            self.training.set_model_holder(holder)

        if (
            command.epoch is None
            and command.batch_size is None
            and command.learning_rate is None
        ):
            if command.model_name:
                return f"Model configured: {command.model_name}."
            raise PreconditionError(
                "epoch, batch_size, and learning_rate are required.",
            )
        if (
            command.epoch is None
            or command.batch_size is None
            or command.learning_rate is None
        ):
            raise PreconditionError(
                "epoch, batch_size, and learning_rate are required.",
            )

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
            epoch=command.epoch,
            bs=command.batch_size,
            lr=command.learning_rate,
            checkpoint_epoch=command.save_checkpoints_every,
            evaluation_option=evaluation_option,
            repeat_num=command.repeat,
        )
        self.training.set_training_option(option)
        return "Training configured.", {
            "training_option": self._training_option_snapshot(option),
        }

    def _handle_train(self, command: Command) -> HandlerResult:
        if not isinstance(command, TrainCommand):
            raise TypeError("Invalid command for train")
        self.training.start_training()
        return "Training started."

    def _handle_stop_training(self, command: Command) -> HandlerResult:
        if not isinstance(command, StopTrainingCommand):
            raise TypeError("Invalid command for stop_training")
        self.training.stop_training()
        return "Training stop requested."

    def _handle_reset_session(self, command: Command) -> HandlerResult:
        if not isinstance(command, ResetSessionCommand):
            raise TypeError("Invalid command for reset_session")
        self.dataset.clean_dataset()
        self._clear_training_configuration()
        return "Session reset."

    def _handle_new_session(self, command: Command) -> HandlerResult:
        if not isinstance(command, NewSessionCommand):
            raise TypeError("Invalid command for new_session")
        self.dataset.clean_dataset()
        self._clear_training_configuration()
        return "New session started.", {"single_session_backend": True}

    def _handle_evaluate(self, command: Command) -> HandlerResult:
        if not isinstance(command, EvaluateCommand):
            raise TypeError("Invalid command for evaluate")
        plans = self._safe_call_list(self.evaluation.get_plans)
        summaries = []
        for plan_idx, plan in enumerate(plans):
            runs = self._safe_plan_runs(plan)
            finished = [run for run in runs if self._run_finished(run)]
            metrics: dict[str, Any] = {}
            if finished:
                try:
                    _labels, _outputs, metrics = self.evaluation.get_pooled_eval_result(
                        plan,
                    )
                except Exception:
                    logger.debug("Failed to pool evaluation metrics", exc_info=True)
                    metrics = {}
            summaries.append(
                {
                    "index": plan_idx,
                    "name": self._safe_plan_name(plan, plan_idx),
                    "run_count": len(runs),
                    "finished_run_count": len(finished),
                    "metrics": self._json_safe(metrics),
                }
            )
        finished_total = sum(item["finished_run_count"] for item in summaries)
        message = (
            "Evaluation summary ready."
            if finished_total
            else "No completed training runs are available for evaluation yet."
        )
        return (
            message,
            {
                "available": finished_total > 0,
                "target": command.target,
                "plan_count": len(plans),
                "finished_run_count": finished_total,
                "plans": summaries,
            },
        )

    def _handle_visualize(self, command: Command) -> HandlerResult:
        if not isinstance(command, VisualizeCommand):
            raise TypeError("Invalid command for visualize")
        state = self.get_state()
        trainers = self._safe_call_list(self.visualization.get_trainers)
        available_views = []
        if state.epoch.available:
            available_views.extend(["epoch overview", "channel montage"])
        if state.evaluation.finished_runs:
            available_views.extend(["confusion matrix", "metrics", "saliency setup"])
        if state.visualization.saliency_available:
            available_views.extend(
                ["saliency map", "spectrogram", "topographic map", "3D plot"],
            )
        message = (
            "Visualization summary ready."
            if available_views
            else "No visualization views are ready yet."
        )
        return (
            message,
            {
                "available": bool(available_views),
                "view": command.view,
                "available_views": available_views,
                "trainer_count": len(trainers),
                "channel_count": state.visualization.channel_count,
                "montage_available": state.visualization.montage_available,
                "saliency_configured": state.visualization.saliency_configured,
                "saliency_available": state.visualization.saliency_available,
            },
        )

    def _handle_saliency(self, command: Command) -> HandlerResult:
        if not isinstance(command, SaliencyCommand):
            raise TypeError("Invalid command for saliency")
        params = dict(command.params or {})
        if command.method:
            params.setdefault("method", command.method)
        if params:
            self.visualization.set_saliency_params(params)
            return (
                "Saliency parameters configured.",
                {
                    "saliency_configured": True,
                    "params": self._json_safe(params),
                },
            )

        current_params = self.visualization.get_saliency_params()
        state = self.get_state()
        return (
            (
                "Saliency summary ready."
                if current_params
                else "Saliency parameters are not configured yet."
            ),
            {
                "saliency_configured": current_params is not None,
                "saliency_available": state.visualization.saliency_available,
                "params": self._json_safe(current_params or {}),
                "finished_run_count": state.evaluation.finished_runs,
            },
        )

    def _clear_training_configuration(self) -> None:
        """Clear training config that belongs to the previous active dataset."""
        training_manager = getattr(self.study, "training_manager", None)
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
    def _normalize_handler_result(result: HandlerResult) -> tuple[str, dict[str, Any]]:
        if isinstance(result, tuple):
            return result
        return result, {}

    def _pipeline_stage(self) -> str:
        stage = getattr(self.study, "pipeline_stage", None)
        value = getattr(stage, "value", None)
        if isinstance(value, str):
            return value
        if isinstance(stage, str):
            return stage
        return str(stage) if stage is not None else "unknown"

    @staticmethod
    def _raw_formats(raw_data: list[Any]) -> list[str]:
        formats = []
        for item in raw_data:
            filename = ApplicationService._data_filename(item)
            _, ext = os.path.splitext(filename)
            if ext:
                formats.append(ext.lower())
        return sorted(set(formats))

    @staticmethod
    def _raw_channels(raw_data: list[Any]) -> list[str]:
        if not raw_data:
            return []
        try:
            return [str(ch) for ch in raw_data[0].get_mne().ch_names]
        except Exception:
            return []

    @staticmethod
    def _preprocess_history(preprocessed: list[Any]) -> list[str]:
        history: list[str] = []
        for item in preprocessed:
            getter = getattr(item, "get_preprocess_history", None)
            if not callable(getter):
                continue
            try:
                steps = getter()
                if steps is None:
                    continue
                for step in cast(Iterable[Any], steps):
                    text = str(step)
                    if text and text not in history:
                        history.append(text)
            except Exception as exc:
                logger.debug(
                    "Failed to read preprocess history from %s: %s",
                    ApplicationService._data_filename(item),
                    exc,
                )
                continue
        return history

    @staticmethod
    def _build_data_splitting_config(
        command: GenerateDatasetCommand,
    ) -> DataSplittingConfig:
        split_strategy = command.split_strategy.lower()
        split_by = {
            "trial": SplitByType.TRIAL,
            "session": SplitByType.SESSION,
            "subject": SplitByType.SUBJECT,
        }.get(split_strategy)
        if split_by is None:
            raise ValueError(f"Unknown split strategy: {command.split_strategy}")

        val_split_by = {
            SplitByType.TRIAL: ValSplitByType.TRIAL,
            SplitByType.SESSION: ValSplitByType.SESSION,
            SplitByType.SUBJECT: ValSplitByType.SUBJECT,
        }[split_by]
        training_mode = command.training_mode.lower()
        training_type = {
            "individual": TrainingType.IND,
            "group": TrainingType.FULL,
        }.get(training_mode)
        if training_type is None:
            raise ValueError(f"Unknown training mode: {command.training_mode}")

        return DataSplittingConfig(
            train_type=training_type,
            is_cross_validation=False,
            val_splitter_list=[
                DataSplitter(
                    split_type=val_split_by,
                    value_var=str(command.val_ratio),
                    split_unit=SplitUnit.RATIO,
                ),
            ],
            test_splitter_list=[
                DataSplitter(
                    split_type=split_by,
                    value_var=str(command.test_ratio),
                    split_unit=SplitUnit.RATIO,
                ),
            ],
        )

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
        return optimizers_map.get(name.lower(), torch.optim.Adam)

    @staticmethod
    def _resolve_training_device(device: str) -> tuple[bool, int | None]:
        normalized = str(device or "auto").strip().lower()
        if normalized in {"cpu", "none"}:
            return True, None
        if normalized in {"auto", "cuda", "gpu"}:
            return False, 0
        if normalized.startswith("cuda:"):
            try:
                return False, int(normalized.split(":", 1)[1])
            except (TypeError, ValueError):
                return False, 0
        try:
            return False, int(normalized)
        except ValueError:
            return False, 0

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
        return TrainingEvaluation.LAST_EPOCH

    @staticmethod
    def _resolve_label_attachment_path(raw: Any, mapping: dict[str, str]) -> str | None:
        filepath = raw.get_filepath()
        filename = raw.get_filename()
        return (
            mapping.get(filepath)
            or mapping.get(filename)
            or mapping.get(os.path.basename(filepath))
        )

    @staticmethod
    def _build_default_label_name_map(label_map: dict[str, Any]) -> dict[Any, str]:
        event_name_map: dict[Any, str] = {}
        for labels in label_map.values():
            if (
                isinstance(labels, list)
                and len(labels) > 0
                and isinstance(labels[0], dict)
            ):
                continue
            for label in np.array(labels).flatten():
                normalized = label.item() if isinstance(label, np.generic) else label
                event_name_map.setdefault(normalized, str(normalized))
        return event_name_map

    @staticmethod
    def _require(value: Any, name: str) -> Any:
        if value is None:
            raise PreconditionError(f"{name} is required.")
        return value

    @staticmethod
    def _data_filename(data: Any) -> str:
        try:
            return str(data.get_filename())
        except Exception:
            return str(data)

    @staticmethod
    def _dataset_name(dataset: Any, idx: int) -> str:
        for attr in ("name", "dataset_name"):
            value = getattr(dataset, attr, None)
            if value:
                return str(value)
        getter = getattr(dataset, "get_name", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                pass
        return f"Dataset {idx + 1}"

    @staticmethod
    def _model_name(model_holder: Any) -> str | None:
        target_model = getattr(model_holder, "target_model", None)
        if target_model is None:
            return None
        return getattr(target_model, "__name__", str(target_model))

    @staticmethod
    def _training_option_snapshot(option: Any) -> dict[str, Any]:
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

    def _evaluation_snapshot(self) -> EvaluationStateSnapshot:
        plans = self._safe_call_list(self.evaluation.get_plans)
        total_runs = 0
        finished_runs = 0
        metrics_available = False
        for plan in plans:
            runs = self._safe_plan_runs(plan)
            total_runs += len(runs)
            for run in runs:
                if self._run_finished(run):
                    finished_runs += 1
                if getattr(run, "eval_record", None) is not None:
                    metrics_available = True
        return EvaluationStateSnapshot(
            available=finished_runs > 0,
            total_plans=len(plans),
            total_runs=total_runs,
            finished_runs=finished_runs,
            metrics_available=metrics_available,
        )

    @staticmethod
    def _safe_plan_runs(plan: Any) -> list[Any]:
        try:
            return list(plan.get_plans())
        except Exception:
            return []

    @staticmethod
    def _safe_plan_name(plan: Any, idx: int) -> str:
        try:
            return str(plan.get_name())
        except Exception:
            return f"Plan {idx + 1}"

    @staticmethod
    def _run_finished(run: Any) -> bool:
        try:
            return bool(run.is_finished())
        except Exception:
            return False

    @staticmethod
    def _shape(value: Any) -> tuple[int, ...] | None:
        shape = getattr(value, "shape", None)
        if shape is None:
            return None
        try:
            return tuple(int(dim) for dim in shape)
        except Exception:
            return None

    @staticmethod
    def _epoch_count(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        for attr in ("epoch_count", "n_epochs"):
            value = getattr(epoch_data, attr, None)
            if isinstance(value, int):
                return value
        shape = ApplicationService._shape(getattr(epoch_data, "data", None))
        if shape:
            return shape[0]
        getter = getattr(epoch_data, "get_data", None)
        if callable(getter):
            try:
                value = getter()
                shape = ApplicationService._shape(value)
                if shape:
                    return shape[0]
            except Exception:
                pass
        try:
            return len(epoch_data)
        except Exception:
            return None

    @staticmethod
    def _epoch_event_names(epoch_data: Any) -> list[str]:
        if epoch_data is None:
            return []
        event_ids = ApplicationService._epoch_event_ids(epoch_data)
        if event_ids:
            return sorted(event_ids)
        try:
            _, event_ids = epoch_data.get_event_list()
            if isinstance(event_ids, dict):
                return sorted(str(name) for name in event_ids)
        except Exception:
            pass
        return []

    @staticmethod
    def _epoch_event_ids(epoch_data: Any) -> dict[str, int] | None:
        if epoch_data is None:
            return None
        event_id = getattr(epoch_data, "event_id", None)
        if isinstance(event_id, dict):
            return {str(k): int(v) for k, v in event_id.items()}
        return None

    @staticmethod
    def _epoch_n_channels(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        shape = ApplicationService._shape(getattr(epoch_data, "data", None))
        if shape and len(shape) >= 2:
            return shape[1]
        return None

    @staticmethod
    def _epoch_n_times(epoch_data: Any) -> int | None:
        if epoch_data is None:
            return None
        shape = ApplicationService._shape(getattr(epoch_data, "data", None))
        if shape and len(shape) >= 3:
            return shape[2]
        return None

    @staticmethod
    def _epoch_channel_names(epoch_data: Any) -> list[str]:
        if epoch_data is None:
            return []
        for method_name in ("get_channel_names",):
            method = getattr(epoch_data, method_name, None)
            if callable(method):
                try:
                    values = cast(Iterable[Any], method())
                    return [str(ch) for ch in values]
                except Exception:
                    pass
        try:
            return [str(ch) for ch in epoch_data.get_mne().ch_names]
        except Exception:
            return []

    @staticmethod
    def _dataset_split_summary(datasets: list[Any]) -> dict[str, Any]:
        if not datasets:
            return {}
        summary: dict[str, Any] = {"count": len(datasets)}
        first = datasets[0]
        for mask_name in ("train_mask", "val_mask", "test_mask"):
            mask = getattr(first, mask_name, None)
            if mask is not None and hasattr(mask, "sum"):
                try:
                    summary[mask_name.replace("_mask", "_count")] = int(mask.sum())
                except Exception as exc:
                    logger.debug("Failed to summarize %s: %s", mask_name, exc)
                    continue
        try:
            audit = audit_dataset_splits(cast(list[Any], datasets))
            summary["audit"] = audit.to_dict()
        except Exception:
            logger.debug("Failed to audit dataset splits", exc_info=True)
        return summary

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {str(k): cls._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _montage_available(epoch_data: Any) -> bool:
        if epoch_data is None:
            return False
        return bool(getattr(epoch_data, "channel_position", None))

    @staticmethod
    def _channel_positions_available(epoch_data: Any) -> bool:
        return ApplicationService._montage_available(epoch_data)

    @staticmethod
    def _safe_call_dict(call: Callable[[], Any]) -> dict[str, Any]:
        try:
            value = call()
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_call_list(call: Callable[[], Any]) -> list[Any]:
        try:
            value = call()
        except Exception:
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _safe_list(call: Callable[[], Any]) -> list[Any]:
        try:
            value = call()
        except Exception:
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _safe_bool(call: Callable[[], Any]) -> bool:
        try:
            return bool(call())
        except Exception:
            return False

    @staticmethod
    def _changed_state(
        before: ApplicationStateSnapshot,
        after: ApplicationStateSnapshot,
    ) -> ChangedState:
        before_dict = before.to_dict()
        after_dict = after.to_dict()
        return ChangedState(
            raw_changed=before_dict["raw"] != after_dict["raw"],
            preprocessed_changed=(
                before_dict["preprocessed"] != after_dict["preprocessed"]
            ),
            epoch_changed=before_dict["epoch"] != after_dict["epoch"],
            datasets_changed=before_dict["dataset"] != after_dict["dataset"],
            training_changed=before_dict["training"] != after_dict["training"],
            evaluation_changed=before_dict["evaluation"] != after_dict["evaluation"],
            visualization_changed=(
                before_dict["visualization"] != after_dict["visualization"]
            ),
            error_changed=before_dict["last_error"] != after_dict["last_error"],
        )
