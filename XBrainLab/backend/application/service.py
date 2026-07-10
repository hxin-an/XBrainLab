"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger

from .capabilities import CapabilityPolicy, build_capability_policy
from .command_gate import ensure_command_allowed
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
    ReviewInterpretationCommand,
    SaliencyCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    command_name,
)
from .controller_adapters import (
    DatasetControllerAdapter,
    EvaluationControllerAdapter,
    PreprocessControllerAdapter,
    TrainingControllerAdapter,
    VisualizationControllerAdapter,
)
from .data_table_service import DataTableCommandService
from .errors import (
    ApplicationError,
    map_exception,
)
from .lifecycle_service import LifecycleCommandService
from .preprocess_service import PreprocessCommandService
from .results import ChangedState, CommandResult, ErrorType
from .state import ApplicationStateSnapshot, ErrorSnapshot
from .state_read_models import EvaluationStateReadModel, TrainingStateReadModel
from .state_service import QueryStateCommandService, StateSnapshotService

HandlerResult = str | tuple[str, dict[str, Any]]


class _LazyDataInterpretationCommandService:
    """Defer Data Interpretation imports until an interpretation command runs."""

    def __init__(self, dataset: Any) -> None:
        self.dataset = dataset
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .data_interpretation_service import (  # noqa: PLC0415
                DataInterpretationCommandService,
            )

            self._service_instance = DataInterpretationCommandService(
                self.dataset,
                data_filename=StateSnapshotService.data_filename,
                data_filepath=StateSnapshotService.data_filepath,
            )
        return self._service_instance

    def snapshot(self):
        if self._service_instance is None:
            from .state import InterpretationStateSnapshot  # noqa: PLC0415

            return InterpretationStateSnapshot()
        return self._service_instance.snapshot()

    def clear(self) -> None:
        if self._service_instance is not None:
            self._service_instance.clear()

    def handle_scan_source(self, command: Command) -> CommandResult:
        return self._service().handle_scan_source(command)

    def handle_review_interpretation(self, command: Command) -> CommandResult:
        return self._service().handle_review_interpretation(command)

    def handle_preview_interpretation(self, command: Command) -> CommandResult:
        return self._service().handle_preview_interpretation(command)

    def handle_validate_interpretation(self, command: Command) -> CommandResult:
        return self._service().handle_validate_interpretation(command)

    def handle_apply_interpretation(self, command: Command) -> CommandResult:
        return self._service().handle_apply_interpretation(command)

    def handle_save_interpretation_recipe(self, command: Command) -> CommandResult:
        return self._service().handle_save_interpretation_recipe(command)

    def handle_reload_interpretation_recipe(self, command: Command) -> CommandResult:
        return self._service().handle_reload_interpretation_recipe(command)

    def record_label_import_for_recipe(self, *args: Any, **kwargs: Any) -> Any:
        return self._service().record_label_import_for_recipe(*args, **kwargs)


class _LazyDataCompatibilityCommandService:
    """Defer label/data compatibility imports until compatibility commands run."""

    def __init__(self, *, dataset: Any, interpretation: Any) -> None:
        self.dataset = dataset
        self.interpretation = interpretation
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .data_compatibility_service import (  # noqa: PLC0415
                DataCompatibilityCommandService,
            )

            self._service_instance = DataCompatibilityCommandService(
                dataset=self.dataset,
                interpretation=self.interpretation,
            )
        return self._service_instance

    def handle_load_data(self, command: Command) -> CommandResult:
        return self._service().handle_load_data(command)

    def handle_attach_labels(self, command: Command) -> CommandResult:
        return self._service().handle_attach_labels(command)

    def handle_import_labels(self, command: Command) -> CommandResult:
        return self._service().handle_import_labels(command)


class _LazyDatasetGenerationCommandService:
    """Defer dataset-generation imports until dataset split commands run."""

    def __init__(self, *, study: Any, training: Any) -> None:
        self.study = study
        self.training = training
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .dataset_generation_service import (  # noqa: PLC0415
                DatasetGenerationCommandService,
            )

            self._service_instance = DatasetGenerationCommandService(
                study=self.study,
                training=self.training,
            )
        return self._service_instance

    def restore_generation_state(
        self,
        *,
        datasets: list[Any],
        generator: Any,
        trainer: Any,
    ) -> None:
        if self._service_instance is not None:
            self._service_instance.restore_generation_state(
                datasets=datasets,
                generator=generator,
                trainer=trainer,
            )
            return
        data_manager = getattr(self.study, "data_manager", None)
        if data_manager is not None:
            data_manager.datasets = datasets
            data_manager.dataset_generator = generator
        else:
            self.study.datasets = datasets
            self.study.dataset_generator = generator

        training_manager = getattr(self.study, "training_manager", None)
        if training_manager is not None:
            training_manager.trainer = trainer
        else:
            self.study.trainer = trainer

    def dataset_split_summary(self, datasets: list[Any]) -> dict[str, Any]:
        if not datasets:
            return {}
        return self._service().dataset_split_summary(datasets)

    def handle_generate_dataset(self, command: Command) -> CommandResult:
        return self._service().handle_generate_dataset(command)

    def handle_clear_datasets(self, command: Command) -> CommandResult:
        return self._service().handle_clear_datasets(command)


class _LazyTrainingCommandService:
    """Defer torch/model/training imports until training commands run."""

    def __init__(
        self,
        *,
        training: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.training = training
        self._get_state = get_state
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .training_service import TrainingCommandService  # noqa: PLC0415

            self._service_instance = TrainingCommandService(
                training=self.training,
                get_state=self._get_state,
            )
        return self._service_instance

    def clear_configuration(self, training_manager: Any | None) -> None:
        if self._service_instance is not None:
            self._service_instance.clear_configuration(training_manager)
            return
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

    def handle_configure_training(self, command: Command) -> CommandResult:
        return self._service().handle_configure_training(command)

    def handle_train(self, command: Command) -> CommandResult:
        return self._service().handle_train(command)

    def handle_stop_training(self, command: Command) -> CommandResult:
        return self._service().handle_stop_training(command)

    def handle_clear_training_history(self, command: Command) -> CommandResult:
        return self._service().handle_clear_training_history(command)


class _LazyAnalysisCommandService:
    """Defer NumPy/visualization analysis service until analysis commands run."""

    def __init__(
        self,
        *,
        evaluation: Any,
        visualization: Any,
        preprocess: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.evaluation = evaluation
        self.visualization = visualization
        self.preprocess = preprocess
        self._get_state = get_state
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .analysis_service import AnalysisCommandService  # noqa: PLC0415

            self._service_instance = AnalysisCommandService(
                evaluation=self.evaluation,
                visualization=self.visualization,
                preprocess=self.preprocess,
                get_state=self._get_state,
            )
        return self._service_instance

    def handle_evaluate(self, command: Command) -> CommandResult:
        return self._service().handle_evaluate(command)

    def handle_visualize(self, command: Command) -> CommandResult:
        return self._service().handle_visualize(command)

    def handle_saliency(self, command: Command) -> CommandResult:
        return self._service().handle_saliency(command)

    def handle_apply_montage(self, command: Command) -> CommandResult:
        return self._service().handle_apply_montage(command)


class ApplicationService:
    """Command-oriented application layer over the existing backend controllers."""

    def __init__(self, study: Study | None = None):
        self.study = study if study is not None else Study()
        self.study._application_service = self
        self.dataset = DatasetControllerAdapter(self.study)
        self.preprocess = PreprocessControllerAdapter(self.study)
        self.training = TrainingControllerAdapter(self.study)
        self.evaluation = EvaluationControllerAdapter(self.study)
        self.visualization = VisualizationControllerAdapter(self.study)
        self.training_state = TrainingStateReadModel(self.study)
        self.evaluation_state = EvaluationStateReadModel(self.study)
        self._last_error: ErrorSnapshot | None = None
        self._last_state: ApplicationStateSnapshot | None = None
        self.interpretation = _LazyDataInterpretationCommandService(self.dataset)
        self.data_compatibility = _LazyDataCompatibilityCommandService(
            dataset=self.dataset,
            interpretation=self.interpretation,
        )
        self.data_table = DataTableCommandService(dataset=self.dataset)
        self.preprocess_commands = PreprocessCommandService(
            preprocess=self.preprocess,
            dataset=self.dataset,
            get_state=self.get_state,
        )
        self.dataset_generation = _LazyDatasetGenerationCommandService(
            study=self.study,
            training=self.training,
        )
        self.training_commands = _LazyTrainingCommandService(
            training=self.training,
            get_state=self.get_state,
        )
        self.state_snapshot = StateSnapshotService(
            study=self.study,
            dataset=self.dataset,
            preprocess=self.preprocess,
            training=self.training,
            training_state=self.training_state,
            evaluation=self.evaluation,
            evaluation_state=self.evaluation_state,
            visualization=self.visualization,
            dataset_generation=self.dataset_generation,
            training_commands=self.training_commands,
            interpretation=self.interpretation,
        )
        self.query_state_commands = QueryStateCommandService(
            study=self.study,
            dataset=self.dataset,
            state_builder=self.state_snapshot,
            get_state=self.get_state,
            get_capabilities=self.get_capabilities,
        )
        self.analysis = _LazyAnalysisCommandService(
            evaluation=self.evaluation,
            visualization=self.visualization,
            preprocess=self.preprocess,
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
        state = self.state_snapshot.build(last_error=self._last_error)
        self._last_state = state
        return state

    def get_capabilities(self) -> CapabilityPolicy:
        """Return command capabilities for the current state."""
        return build_capability_policy(self.get_state())

    def execute(self, command: Command | Any) -> CommandResult:
        """Execute a command and return a result envelope."""
        try:
            name = command_name(command)
        except Exception as exc:
            return self._unsupported_command_result(self._state_fallback(exc), exc)
        try:
            before = self.get_state()
        except Exception as exc:
            return self._state_read_failure_result(name.value, exc)
        try:
            self._ensure_command_allowed(command, before)
            message, diagnostics = self._normalize_handler_result(
                self._execute_allowed(command, name),
            )
            is_read_only = self._is_read_only_command(command, name)
            if is_read_only:
                return CommandResult.success_result(
                    command_name=name.value,
                    message=message,
                    state=before,
                    changed_state=ChangedState(),
                    diagnostics=diagnostics,
                )
            self._last_error = None
            after, refresh_error = self._state_after_command(before)
            if refresh_error is not None:
                diagnostics = {
                    **diagnostics,
                    "state_refresh_error": str(refresh_error),
                    "state_refresh_exception_type": refresh_error.__class__.__name__,
                }
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
            after, refresh_error = self._state_after_command(before)
            failure_diagnostics = {
                **app_error.diagnostics,
                "exception_type": exc.__class__.__name__,
            }
            if refresh_error is not None:
                failure_diagnostics.update(
                    {
                        "state_refresh_error": str(refresh_error),
                        "state_refresh_exception_type": (
                            refresh_error.__class__.__name__
                        ),
                    },
                )
            return CommandResult.failure_result(
                command_name=name.value,
                message=app_error.message,
                state=after,
                changed_state=self._changed_state(before, after),
                error_type=app_error.error_type,
                recoverable=app_error.recoverable,
                error_message=app_error.message,
                diagnostics=failure_diagnostics,
            )

    def _state_after_command(
        self,
        before: ApplicationStateSnapshot,
    ) -> tuple[ApplicationStateSnapshot, Exception | None]:
        try:
            return self.get_state(), None
        except Exception as exc:
            return before, exc

    def _state_fallback(self, exc: Exception) -> ApplicationStateSnapshot:
        message = f"state snapshot unavailable: {exc}"
        if self._last_state is not None:
            errors = [*self._last_state.read_errors, message]
            return replace(
                self._last_state,
                state_reliable=False,
                read_errors=errors,
            )
        return ApplicationStateSnapshot.empty(read_errors=[message])

    def _state_read_failure_result(
        self,
        command_name_value: str,
        exc: Exception,
    ) -> CommandResult:
        app_error = map_exception(exc)
        message = f"Unable to verify application state: {app_error.message}"
        self._last_error = ErrorSnapshot(
            error_type=ErrorType.INTERNAL.value,
            message=message,
            recoverable=False,
        )
        state = replace(
            self._state_fallback(exc),
            last_error=self._last_error,
        )
        return CommandResult.failure_result(
            command_name=command_name_value,
            message=message,
            state=state,
            changed_state=ChangedState(error_changed=True),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            error_message=message,
            diagnostics={
                "exception_type": exc.__class__.__name__,
                "state_read_failed": True,
            },
        )

    def _execute_allowed(self, command: Command, name: CommandName) -> HandlerResult:
        route = self._handler_route(name)
        if route is None:
            raise ApplicationError(
                message=(
                    f"{name.value} is reserved in the command contract but is "
                    "not implemented by ApplicationService yet."
                ),
                error_type=ErrorType.UNSUPPORTED_COMMAND,
                recoverable=True,
            )
        service_name, handler_name = route
        handler = getattr(getattr(self, service_name), handler_name)
        return handler(command)

    @staticmethod
    def _handler_route(name: CommandName) -> tuple[str, str] | None:
        """Return the target service lazily so read-only commands stay light."""
        routes = {
            CommandName.SCAN_SOURCE: ("interpretation", "handle_scan_source"),
            CommandName.REVIEW_INTERPRETATION: (
                "interpretation",
                "handle_review_interpretation",
            ),
            CommandName.PREVIEW_INTERPRETATION: (
                "interpretation",
                "handle_preview_interpretation",
            ),
            CommandName.VALIDATE_INTERPRETATION: (
                "interpretation",
                "handle_validate_interpretation",
            ),
            CommandName.APPLY_INTERPRETATION: (
                "interpretation",
                "handle_apply_interpretation",
            ),
            CommandName.SAVE_INTERPRETATION_RECIPE: (
                "interpretation",
                "handle_save_interpretation_recipe",
            ),
            CommandName.RELOAD_INTERPRETATION_RECIPE: (
                "interpretation",
                "handle_reload_interpretation_recipe",
            ),
            CommandName.LOAD_DATA: ("data_compatibility", "handle_load_data"),
            CommandName.ATTACH_LABELS: ("data_compatibility", "handle_attach_labels"),
            CommandName.IMPORT_LABELS: ("data_compatibility", "handle_import_labels"),
            CommandName.UPDATE_METADATA: ("data_table", "handle_update_metadata"),
            CommandName.APPLY_SMART_PARSE: ("data_table", "handle_apply_smart_parse"),
            CommandName.REMOVE_FILES: ("data_table", "handle_remove_files"),
            CommandName.PREPROCESS: ("preprocess_commands", "handle_preprocess"),
            CommandName.CREATE_EPOCH: ("preprocess_commands", "handle_create_epoch"),
            CommandName.GENERATE_DATASET: (
                "dataset_generation",
                "handle_generate_dataset",
            ),
            CommandName.CLEAR_DATASETS: (
                "dataset_generation",
                "handle_clear_datasets",
            ),
            CommandName.CONFIGURE_TRAINING: (
                "training_commands",
                "handle_configure_training",
            ),
            CommandName.TRAIN: ("training_commands", "handle_train"),
            CommandName.STOP_TRAINING: ("training_commands", "handle_stop_training"),
            CommandName.CLEAR_TRAINING_HISTORY: (
                "training_commands",
                "handle_clear_training_history",
            ),
            CommandName.EVALUATE: ("analysis", "handle_evaluate"),
            CommandName.VISUALIZE: ("analysis", "handle_visualize"),
            CommandName.SALIENCY: ("analysis", "handle_saliency"),
            CommandName.APPLY_MONTAGE: ("analysis", "handle_apply_montage"),
            CommandName.QUERY_STATE: ("query_state_commands", "handle_query_state"),
            CommandName.RESET_PREPROCESS: ("lifecycle", "handle_reset_preprocess"),
            CommandName.RESET_SESSION: ("lifecycle", "handle_reset_session"),
            CommandName.NEW_SESSION: ("lifecycle", "handle_new_session"),
        }
        return routes.get(name)

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
        label_sources: list[str] | None = None,
    ) -> CommandResult:
        """Scan a source path for a data interpretation."""
        return self.execute(
            ScanSourceCommand(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=list(label_sources or []),
            ),
        )

    def review_interpretation(
        self,
        source_path: str,
        source_hint: str = "auto",
        label_sources: list[str] | None = None,
        choices: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Scan, preview, and validate a data interpretation."""
        return self.execute(
            ReviewInterpretationCommand(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=list(label_sources or []),
                choices=dict(choices or {}),
            ),
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

    def train(
        self,
        command: TrainCommand | None = None,
        *,
        confirmed: bool = False,
    ) -> CommandResult:
        """Execute a train command."""
        return self.execute(command or TrainCommand(confirmed=confirmed))

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
        ensure_command_allowed(command, state)

    @staticmethod
    def _normalize_handler_result(result: HandlerResult) -> tuple[str, dict[str, Any]]:
        if isinstance(result, tuple):
            return result
        return result, {}

    def _unsupported_command_result(
        self,
        before: ApplicationStateSnapshot,
        exc: Exception,
    ) -> CommandResult:
        self._last_error = ErrorSnapshot(
            error_type=ErrorType.UNSUPPORTED_COMMAND.value,
            message=str(exc),
            recoverable=True,
        )
        after, refresh_error = self._state_after_command(before)
        diagnostics = {"exception_type": exc.__class__.__name__}
        if refresh_error is not None:
            diagnostics.update(
                {
                    "state_refresh_error": str(refresh_error),
                    "state_refresh_exception_type": refresh_error.__class__.__name__,
                },
            )
        return CommandResult.failure_result(
            command_name=ErrorType.UNSUPPORTED_COMMAND.value,
            message=str(exc),
            state=after,
            changed_state=self._changed_state(before, after),
            error_type=ErrorType.UNSUPPORTED_COMMAND,
            recoverable=True,
            error_message=str(exc),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _is_read_only_command(command: Command, name: CommandName) -> bool:
        if name in {
            CommandName.QUERY_STATE,
            CommandName.EVALUATE,
            CommandName.VISUALIZE,
        }:
            return True
        return (
            name == CommandName.SALIENCY
            and isinstance(command, SaliencyCommand)
            and command.method is None
            and command.params is None
        )

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
