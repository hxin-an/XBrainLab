"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any, cast

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger

from .analysis_service import AnalysisCommandService
from .capabilities import CapabilityPolicy, build_capability_policy
from .commands import (
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    Command,
    CommandName,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    SaliencyCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    command_name,
)
from .data_compatibility_service import DataCompatibilityCommandService
from .data_interpretation_service import DataInterpretationCommandService
from .data_table_service import DataTableCommandService
from .dataset_generation_service import DatasetGenerationCommandService
from .errors import (
    ApplicationError,
    ConfirmationRequiredError,
    PreconditionError,
    map_exception,
)
from .lifecycle_service import LifecycleCommandService
from .preprocess_service import PreprocessCommandService
from .results import ChangedState, CommandResult, ErrorType
from .state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    ErrorSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from .training_service import TrainingCommandService

HandlerResult = str | tuple[str, dict[str, Any]]


class ApplicationService:
    """Command-oriented application layer over the existing backend controllers."""

    def __init__(self, study: Study | None = None):
        self.study = study if study is not None else Study()
        self.study._application_service = self
        self.dataset = self.study.get_controller("dataset")
        self.preprocess = self.study.get_controller("preprocess")
        self.training = self.study.get_controller("training")
        self.evaluation = self.study.get_controller("evaluation")
        self.visualization = self.study.get_controller("visualization")
        self._last_error: ErrorSnapshot | None = None
        self.interpretation = DataInterpretationCommandService(
            self.dataset,
            data_filename=self._data_filename,
            data_filepath=self._data_filepath,
        )
        self.data_compatibility = DataCompatibilityCommandService(
            dataset=self.dataset,
            interpretation=self.interpretation,
        )
        self.data_table = DataTableCommandService(dataset=self.dataset)
        self.preprocess_commands = PreprocessCommandService(
            preprocess=self.preprocess,
            dataset=self.dataset,
        )
        self.analysis = AnalysisCommandService(
            evaluation=self.evaluation,
            visualization=self.visualization,
            preprocess=self.preprocess,
            get_state=self.get_state,
        )
        self.dataset_generation = DatasetGenerationCommandService(
            study=self.study,
            training=self.training,
        )
        self.training_commands = TrainingCommandService(
            training=self.training,
            get_state=self.get_state,
        )
        self.lifecycle = LifecycleCommandService(
            study=self.study,
            dataset=self.dataset,
            preprocess=self.preprocess,
            training=self.training,
            dataset_generation=self.dataset_generation,
            training_commands=self.training_commands,
            interpretation=self.interpretation,
            get_state=self.get_state,
        )

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
            metadata=self._raw_metadata(raw_data),
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
            split_summary=self.dataset_generation.dataset_split_summary(datasets),
        )
        training = TrainingStateSnapshot(
            has_model=model_holder is not None,
            model_name=self.training_commands.model_name(model_holder),
            has_training_option=training_option is not None,
            training_option=self.training_commands.training_option_snapshot(
                training_option,
            ),
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
        interpretation = self._interpretation_snapshot()
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
            interpretation=interpretation,
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
            CommandName.SCAN_SOURCE: self.interpretation.handle_scan_source,
            CommandName.PREVIEW_INTERPRETATION: (
                self.interpretation.handle_preview_interpretation
            ),
            CommandName.VALIDATE_INTERPRETATION: (
                self.interpretation.handle_validate_interpretation
            ),
            CommandName.APPLY_INTERPRETATION: (
                self.interpretation.handle_apply_interpretation
            ),
            CommandName.SAVE_INTERPRETATION_RECIPE: (
                self.interpretation.handle_save_interpretation_recipe
            ),
            CommandName.RELOAD_INTERPRETATION_RECIPE: (
                self.interpretation.handle_reload_interpretation_recipe
            ),
            CommandName.LOAD_DATA: self.data_compatibility.handle_load_data,
            CommandName.ATTACH_LABELS: self.data_compatibility.handle_attach_labels,
            CommandName.IMPORT_LABELS: self.data_compatibility.handle_import_labels,
            CommandName.UPDATE_METADATA: self.data_table.handle_update_metadata,
            CommandName.APPLY_SMART_PARSE: self.data_table.handle_apply_smart_parse,
            CommandName.REMOVE_FILES: self.data_table.handle_remove_files,
            CommandName.PREPROCESS: self.preprocess_commands.handle_preprocess,
            CommandName.CREATE_EPOCH: self.preprocess_commands.handle_create_epoch,
            CommandName.GENERATE_DATASET: (
                self.dataset_generation.handle_generate_dataset
            ),
            CommandName.CLEAR_DATASETS: self.dataset_generation.handle_clear_datasets,
            CommandName.CONFIGURE_TRAINING: (
                self.training_commands.handle_configure_training
            ),
            CommandName.TRAIN: self.training_commands.handle_train,
            CommandName.STOP_TRAINING: self.training_commands.handle_stop_training,
            CommandName.CLEAR_TRAINING_HISTORY: (
                self.training_commands.handle_clear_training_history
            ),
            CommandName.EVALUATE: self.analysis.handle_evaluate,
            CommandName.VISUALIZE: self.analysis.handle_visualize,
            CommandName.SALIENCY: self.analysis.handle_saliency,
            CommandName.APPLY_MONTAGE: self.analysis.handle_apply_montage,
            CommandName.QUERY_STATE: self._handle_query_state,
            CommandName.RESET_PREPROCESS: self.lifecycle.handle_reset_preprocess,
            CommandName.RESET_SESSION: self.lifecycle.handle_reset_session,
            CommandName.NEW_SESSION: self.lifecycle.handle_new_session,
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

    def scan_source(
        self,
        source_path: str,
        source_hint: str = "auto",
    ) -> CommandResult:
        """Scan a source path for a data interpretation."""
        return self.execute(
            ScanSourceCommand(source_path=source_path, source_hint=source_hint),
        )

    def preview_interpretation(
        self,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Preview a candidate data interpretation."""
        return self.execute(
            PreviewInterpretationCommand(
                scan_id=scan_id,
                choices=dict(choices or {}),
            ),
        )

    def validate_interpretation(
        self,
        candidate_id: str | None = None,
    ) -> CommandResult:
        """Validate a candidate data interpretation."""
        return self.execute(ValidateInterpretationCommand(candidate_id=candidate_id))

    def apply_interpretation(
        self,
        candidate_id: str | None = None,
        confirmed: bool = False,
    ) -> CommandResult:
        """Apply a validated data interpretation."""
        return self.execute(
            ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=confirmed,
            ),
        )

    def import_labels(self, plan: LabelImportPlan) -> CommandResult:
        """Execute a label import plan command."""
        return self.execute(ImportLabelsCommand(plan=plan))

    def update_metadata(
        self,
        index: int,
        subject: str | None = None,
        session: str | None = None,
    ) -> CommandResult:
        """Execute a metadata update command."""
        return self.execute(
            UpdateMetadataCommand(index=index, subject=subject, session=session),
        )

    def apply_smart_parse(
        self,
        results: dict[str, tuple[str, str] | list[str] | Any],
    ) -> CommandResult:
        """Execute a smart-parse metadata update command."""
        return self.execute(ApplySmartParseCommand(results=results))

    def remove_files(self, indices: list[int]) -> CommandResult:
        """Execute a remove-files command."""
        return self.execute(RemoveFilesCommand(indices=indices))

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

    def clear_datasets(self, confirmed: bool = False) -> CommandResult:
        """Execute a dataset cleanup command."""
        return self.execute(ClearDatasetsCommand(confirmed=confirmed))

    def configure_training(self, command: ConfigureTrainingCommand) -> CommandResult:
        """Execute a training-configuration command."""
        return self.execute(command)

    def train(self, command: TrainCommand | None = None) -> CommandResult:
        """Execute a train command."""
        return self.execute(command or TrainCommand())

    def stop_training(self) -> CommandResult:
        """Execute a stop-training command."""
        return self.execute(StopTrainingCommand())

    def clear_training_history(self, confirmed: bool = False) -> CommandResult:
        """Execute a training-history cleanup command."""
        return self.execute(ClearTrainingHistoryCommand(confirmed=confirmed))

    def reset_preprocess(self, confirmed: bool = False) -> CommandResult:
        """Execute a preprocessing reset command."""
        return self.execute(ResetPreprocessCommand(confirmed=confirmed))

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

    def apply_montage(self, command: ApplyMontageCommand) -> CommandResult:
        """Execute a confirmed montage application command."""
        return self.execute(command)

    def query_state(self, command: QueryStateCommand | None = None) -> CommandResult:
        """Execute a read-only state query command."""
        return self.execute(command or QueryStateCommand())

    def _ensure_command_allowed(
        self,
        command: Command,
        state: ApplicationStateSnapshot,
    ) -> None:
        name = command_name(command)
        capability = build_capability_policy(state).get(name)
        if (
            name
            in (
                CommandName.APPLY_INTERPRETATION,
                CommandName.CLEAR_DATASETS,
                CommandName.CLEAR_TRAINING_HISTORY,
                CommandName.RESET_PREPROCESS,
                CommandName.RESET_SESSION,
                CommandName.NEW_SESSION,
            )
            and capability.confirmation_required
            and isinstance(
                command,
                (
                    ClearDatasetsCommand,
                    ClearTrainingHistoryCommand,
                    ApplyInterpretationCommand,
                    ResetPreprocessCommand,
                    ResetSessionCommand,
                    NewSessionCommand,
                ),
            )
            and not command.confirmed
        ):
            raise ConfirmationRequiredError(f"{name.value} requires confirmation.")
        if not capability.enabled:
            raise PreconditionError("; ".join(capability.reasons))

    def _handle_query_state(self, command: Command) -> HandlerResult:
        if not isinstance(command, QueryStateCommand):
            raise TypeError("Invalid command for query_state")

        query = str(command.query or "state").lower()
        state = self.get_state()
        if query == "state":
            return (
                "Application state snapshot ready.",
                {
                    "state": state.to_dict(),
                    "capabilities": self.get_capabilities().to_dict(),
                },
            )
        if query == "data_lists":
            loaded = list(getattr(self.study, "loaded_data_list", []) or [])
            preprocessed = list(
                getattr(self.study, "preprocessed_data_list", []) or [],
            )
            diagnostics: dict[str, Any] = {
                "raw_count": len(loaded),
                "preprocessed_count": len(preprocessed),
                "raw_files": state.raw.files,
                "preprocessed_files": state.preprocessed.files,
            }
            if command.include_objects:
                diagnostics["loaded_data_list"] = loaded
                diagnostics["preprocessed_data_list"] = preprocessed
            return "Data list query ready.", diagnostics
        if query == "data_summary":
            return "Dataset summary ready.", self._data_summary_from_state(state)
        if query == "preprocess_diagnostics":
            return (
                "Preprocess diagnostics ready.",
                dict(state.preprocessed.diagnostics),
            )
        if query == "smart_filter_suggestions":
            suggestions = self._smart_filter_suggestions(command.params)
            return (
                "Smart filter suggestions ready.",
                {"suggestions": suggestions},
            )
        raise ValueError(f"Unknown query_state request: {command.query}")

    def _interpretation_snapshot(self) -> InterpretationStateSnapshot:
        return self.interpretation.snapshot()

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
    def _raw_metadata(raw_data: list[Any]) -> list[dict[str, str]]:
        metadata = []
        for idx, item in enumerate(raw_data):
            metadata.append(
                {
                    "index": str(idx),
                    "file": ApplicationService._data_filename(item),
                    "subject": ApplicationService._safe_string_attr(
                        item,
                        "get_subject_name",
                    ),
                    "session": ApplicationService._safe_string_attr(
                        item,
                        "get_session_name",
                    ),
                },
            )
        return metadata

    @staticmethod
    def _safe_string_attr(item: Any, method_name: str) -> str:
        method = getattr(item, method_name, None)
        if not callable(method):
            return ""
        try:
            return str(method())
        except Exception:
            return ""

    @staticmethod
    def _data_filepath(item: Any) -> str:
        method = getattr(item, "get_filepath", None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                logger.debug("Failed to read raw file path", exc_info=True)
        return ApplicationService._data_filename(item)

    def _data_summary_from_state(
        self,
        state: ApplicationStateSnapshot,
    ) -> dict[str, Any]:
        data_list = list(self.dataset.get_loaded_data_list() or [])
        summary: dict[str, Any] = {
            "count": len(data_list) if data_list else state.raw.count,
            "files": [self._data_filename(item) for item in data_list]
            if data_list
            else state.raw.files,
            "formats": (
                self._raw_formats(data_list) if data_list else state.raw.formats
            ),
            "channels": (
                self._raw_channels(data_list) if data_list else state.raw.channels
            ),
            "metadata": self._raw_metadata(data_list)
            if data_list
            else state.raw.metadata,
            "total": state.raw.event_total,
            "unique_count": len(state.raw.unique_events),
            "unique_labels": state.raw.unique_events,
        }
        summary.update(self._safe_call_dict(self.dataset.get_event_info))
        summary.update(state.raw.diagnostics)
        return summary

    def _smart_filter_suggestions(self, params: dict[str, Any]) -> list[int]:
        target_index = params.get("target_index")
        target_count = params.get("target_count")
        if target_index is None or target_count is None:
            raise PreconditionError("target_index and target_count are required.")
        data_list = list(self.dataset.get_loaded_data_list() or [])
        index = int(target_index)
        if index < 0 or index >= len(data_list):
            raise PreconditionError("target_index does not reference a loaded file.")
        return [
            int(item)
            for item in self.dataset.get_smart_filter_suggestions(
                data_list[index],
                int(target_count),
            )
        ]

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
            interpretation_changed=(
                before_dict["interpretation"] != after_dict["interpretation"]
            ),
            error_changed=before_dict["last_error"] != after_dict["last_error"],
        )
