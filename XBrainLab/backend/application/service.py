"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XBrainLab.backend.study import Study

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
from .state import ApplicationStateSnapshot, ErrorSnapshot
from .state_service import QueryStateCommandService, StateSnapshotService
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
            data_filename=StateSnapshotService.data_filename,
            data_filepath=StateSnapshotService.data_filepath,
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
        self.dataset_generation = DatasetGenerationCommandService(
            study=self.study,
            training=self.training,
        )
        self.training_commands = TrainingCommandService(
            training=self.training,
            get_state=self.get_state,
        )
        self.state_snapshot = StateSnapshotService(
            study=self.study,
            dataset=self.dataset,
            preprocess=self.preprocess,
            training=self.training,
            evaluation=self.evaluation,
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
        self.analysis = AnalysisCommandService(
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
        return self.state_snapshot.build(last_error=self._last_error)

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
            CommandName.QUERY_STATE: self.query_state_commands.handle_query_state,
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

    @staticmethod
    def _normalize_handler_result(result: HandlerResult) -> tuple[str, dict[str, Any]]:
        if isinstance(result, tuple):
            return result
        return result, {}

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
