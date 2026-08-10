"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from threading import Lock, RLock
from time import monotonic
from typing import Any

from XBrainLab.backend.services.dataset_state_service import (
    DatasetProductPort,
)
from XBrainLab.backend.services.preprocess_state_service import PreprocessProductPort
from XBrainLab.backend.services.training_state_service import TrainingProductPort
from XBrainLab.backend.services.visualization_state_service import (
    VisualizationProductPort,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.backend.utils.public_diagnostics import (
    public_exception_message,
    safe_exception_type_name,
)

from .application_publication_lifecycle import ApplicationPublicationLifecycle
from .application_shutdown_lifecycle import (
    ApplicationShutdownLifecycleCoordinator,
)
from .capabilities import (
    RECOVERY_COMMAND_NAMES,
    CapabilityPolicy,
)
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
    DiscardTrainingPreparationCommand,
    EvaluateCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreviewInterpretationCommand,
    PreviewLabelImportCommand,
    QueryStateCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    ReviewInterpretationCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    command_name,
)
from .data_table_service import DataTableCommandService
from .dataset_split_preview import (
    DatasetSplitContextPublication,
    DatasetSplitContextRequest,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewPublisher,
    DatasetSplitPreviewRequest,
)
from .epoch_context import (
    EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE,
    EpochDialogContext,
    build_epoching_context,
    require_epoch_context_available,
    validated_epoch_handoff,
)
from .errors import (
    ApplicationError,
    PreconditionError,
    map_exception,
)
from .evaluation_render import (
    EvaluationRenderPublication,
    EvaluationRenderPublisher,
    EvaluationRenderRequest,
)
from .lifecycle_service import LifecycleCommandService
from .pipeline_stage import pipeline_stage_readiness_summary
from .pipeline_transaction import PipelineStateTransaction
from .post_training_saliency import PostTrainingSaliencyAutomation
from .preprocess_render import (
    PreprocessRenderPublication,
    PreprocessRenderPublisher,
    PreprocessRenderRequest,
)
from .preprocess_service import PreprocessCommandService
from .query_state_service import QueryStateCommandService
from .resource_guard import ResourceConfirmationRequiredError, ResourcePreflightResult
from .results import ChangedState, CommandResult, ErrorType
from .saliency_coverage import SaliencyCoverageProjector
from .saliency_render import (
    SaliencyRenderPublication,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
)
from .state import (
    ApplicationStateSnapshot,
    DatasetSplitLifecycle,
    ErrorSnapshot,
    InterpretationStateSnapshot,
)
from .state_read_models import EvaluationStateReadModel, TrainingStateReadModel
from .state_service import StateSnapshotService
from .synchronous_training_lifecycle import (
    SynchronousTrainingLifecycleCoordinator,
)
from .training_configuration_reset import TrainingConfigurationResetService
from .training_recommendation import (
    TrainingRecommendation,
    TrainingRecommendationService,
)
from .training_runtime import (
    StudyTrainingRuntime,
    TrainingProjectionReadPort,
    TrainingRuntimePort,
)
from .training_snapshot import (
    model_name as snapshot_model_name,
)
from .training_snapshot import (
    model_params_snapshot as build_model_params_snapshot,
)
from .training_snapshot import (
    training_option_snapshot as build_training_option_snapshot,
)
from .view_event_publisher import (
    ApplicationViewEventPublisher,
    UnobservedDeliveryPolicy,
)
from .view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewCoordinator,
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)

HandlerResult = str | tuple[str, dict[str, Any]]
_ObserverCleanup = tuple[Callable[..., Any], tuple[Any, ...]]
_CLOSED_SERVICE_MESSAGE = (
    "This XBrainLab application service is closed. Use the current application "
    "service instance."
)
_UNRECOGNIZED_COMMAND_NAME = "unsupported_command"
_TRAINING_RESTART_SAFETY_WAIT_SECONDS = 2.0
_SYNCHRONOUS_BACKGROUND_WAIT_SECONDS = 300.0


class _LegacyRawMutationLifecycleCoordinator:
    """Keep legacy raw edits and Data Interpretation truth in one lifecycle."""

    COMMAND_TYPES = (
        LoadDataCommand,
        AttachLabelsCommand,
        UpdateMetadataCommand,
        ApplySmartParseCommand,
        RemoveFilesCommand,
    )

    def __init__(self, interpretation: Any) -> None:
        self._interpretation = interpretation

    @classmethod
    def manages(cls, command: Command | Any) -> bool:
        return isinstance(command, cls.COMMAND_TYPES)

    def commit(
        self,
        *,
        command: Command,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """Invalidate interpretation only after a reported raw-data mutation."""
        if not self.manages(command):
            return diagnostics
        success_count = diagnostics.get("success_count")
        if isinstance(success_count, bool) or not isinstance(success_count, int):
            self._interpretation.invalidate_for_legacy_raw_mutation()
            raise RuntimeError(
                "Legacy raw mutation handlers must report an integer success_count."
            )
        if success_count < 0:
            self._interpretation.invalidate_for_legacy_raw_mutation()
            raise RuntimeError(
                "Legacy raw mutation handlers cannot report a negative success_count."
            )
        if success_count == 0:
            return diagnostics
        invalidated = self._interpretation.invalidate_for_legacy_raw_mutation()
        return {
            **diagnostics,
            "interpretation_lifecycle": {
                "invalidated": invalidated,
                "reason": "legacy_raw_mutation",
            },
        }

    def fail_closed(self, *, command: Command, error: Exception) -> None:
        """Drop possibly stale truth unless the handler proves full rollback."""
        if not self.manages(command):
            return
        diagnostics = getattr(error, "diagnostics", {})
        if isinstance(diagnostics, dict) and (
            diagnostics.get("rolled_back") is True
            or diagnostics.get("state_preserved") is True
        ):
            return
        if isinstance(error, ApplicationError) and error.error_type in {
            ErrorType.CONFIRMATION_REQUIRED,
            ErrorType.PRECONDITION,
            ErrorType.VALIDATION,
        }:
            return
        if isinstance(error, (TypeError, ValueError)):
            return
        self._interpretation.invalidate_for_legacy_raw_mutation()


class _LazyDataInterpretationCommandService:
    """Defer Data Interpretation imports until an interpretation command runs."""

    def __init__(
        self,
        dataset: DatasetProductPort,
        pipeline_transaction: PipelineStateTransaction,
    ) -> None:
        self.dataset = dataset
        self.pipeline_transaction = pipeline_transaction
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
                pipeline_transaction=self.pipeline_transaction,
            )
        return self._service_instance

    def snapshot(self):
        if self._service_instance is None:
            from .state import InterpretationStateSnapshot  # noqa: PLC0415

            return InterpretationStateSnapshot()
        return self._service_instance.snapshot()

    def current_review(self) -> dict[str, Any]:
        return self._service().current_review()

    def clear(self) -> None:
        if self._service_instance is not None:
            self._service_instance.clear()

    def invalidate_for_legacy_raw_mutation(self) -> bool:
        if self._service_instance is None:
            return False
        return bool(self._service_instance.invalidate_for_legacy_raw_mutation())

    def handle_scan_source(self, command: Command) -> HandlerResult:
        return self._service().handle_scan_source(command)

    def handle_review_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_review_interpretation(command)

    def handle_preview_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_preview_interpretation(command)

    def handle_validate_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_validate_interpretation(command)

    def handle_apply_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_apply_interpretation(command)

    def handle_save_interpretation_recipe(self, command: Command) -> HandlerResult:
        return self._service().handle_save_interpretation_recipe(command)

    def handle_reload_interpretation_recipe(self, command: Command) -> HandlerResult:
        return self._service().handle_reload_interpretation_recipe(command)

    def record_label_import_for_recipe(self, *args: Any, **kwargs: Any) -> Any:
        return self._service().record_label_import_for_recipe(*args, **kwargs)


class _LazyDataCompatibilityCommandService:
    """Defer label/data compatibility imports until compatibility commands run."""

    def __init__(
        self,
        *,
        dataset: DatasetProductPort,
        interpretation: Any,
        pipeline_transaction: PipelineStateTransaction,
    ) -> None:
        self.dataset = dataset
        self.interpretation = interpretation
        self.pipeline_transaction = pipeline_transaction
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .data_compatibility_service import (  # noqa: PLC0415
                DataCompatibilityCommandService,
            )

            self._service_instance = DataCompatibilityCommandService(
                dataset=self.dataset,
                interpretation=self.interpretation,
                pipeline_transaction=self.pipeline_transaction,
            )
        return self._service_instance

    def handle_load_data(self, command: Command) -> HandlerResult:
        return self._service().handle_load_data(command)

    def handle_attach_labels(self, command: Command) -> HandlerResult:
        return self._service().handle_attach_labels(command)

    def handle_import_labels(self, command: Command) -> HandlerResult:
        return self._service().handle_import_labels(command)


class _LazyDatasetGenerationCommandService:
    """Defer dataset-generation imports until dataset split commands run."""

    def __init__(
        self,
        *,
        study: Any,
        training: Any,
        has_trainer: Callable[[], bool],
        pipeline_transaction: PipelineStateTransaction,
        get_publication_generation: Callable[[], int],
    ) -> None:
        self.study = study
        self.training = training
        self.has_trainer = has_trainer
        self.pipeline_transaction = pipeline_transaction
        self.get_publication_generation = get_publication_generation
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .dataset_generation_service import (  # noqa: PLC0415
                DatasetGenerationCommandService,
            )

            self._service_instance = DatasetGenerationCommandService(
                study=self.study,
                training=self.training,
                has_trainer=self.has_trainer,
                pipeline_transaction=self.pipeline_transaction,
                get_publication_generation=self.get_publication_generation,
            )
        return self._service_instance

    def active_split_summary(self, datasets: list[Any]) -> dict[str, Any]:
        if not datasets:
            return {}
        return self._service().active_split_summary(datasets)

    def dataset_split_state(self, datasets: list[Any]) -> dict[str, Any]:
        if self._service_instance is None:
            return {
                "split_spec_saved": False,
                "split_specification": {},
                "split_specification_fingerprint": None,
                "split_epoch_revision": None,
                "split_preview_summary": {},
                "split_lifecycle": DatasetSplitLifecycle.UNCONFIGURED,
                "split_materialized": False,
                "active_split_summary": {},
                "last_split_attempt": {},
            }
        return self._service().dataset_split_state(datasets)

    def prepare_saved_split_candidate(self) -> Any:
        return self._service().prepare_saved_split_candidate()

    def commit_prepared_split(self, candidate: Any) -> dict[str, Any]:
        return self._service().commit_prepared_split(candidate)

    def discard_prepared_split(self) -> bool:
        return self._service().discard_prepared_split()

    def restore_committed_candidate(self, candidate: Any) -> None:
        self._service().restore_committed_candidate(candidate)

    def handle_save_dataset_split(self, command: Command) -> HandlerResult:
        return self._service().handle_save_dataset_split(command)

    def handle_clear_datasets(self, command: Command) -> HandlerResult:
        return self._service().handle_clear_datasets(command)


class _LazyTrainingCommandService:
    """Defer torch/model/training imports until training commands run."""

    def __init__(
        self,
        *,
        training: Any,
        training_runtime: TrainingRuntimePort,
        get_state: Callable[[], ApplicationStateSnapshot],
        configuration_reset: TrainingConfigurationResetService,
        recommendation: TrainingRecommendationService,
    ) -> None:
        self.training = training
        self.training_runtime = training_runtime
        self._get_state = get_state
        self._configuration_reset = configuration_reset
        self._recommendation = recommendation
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .training_service import TrainingCommandService  # noqa: PLC0415

            self._service_instance = TrainingCommandService(
                training=self.training,
                training_runtime=self.training_runtime,
                get_state=self._get_state,
                recommendation=self._recommendation,
            )
        return self._service_instance

    def clear_configuration(self) -> None:
        self._configuration_reset.clear()
        self._recommendation.clear()

    @staticmethod
    def model_name(model_holder: Any) -> str | None:
        return snapshot_model_name(model_holder)

    @staticmethod
    def model_params_snapshot(model_holder: Any) -> dict[str, Any]:
        return build_model_params_snapshot(model_holder)

    @staticmethod
    def training_option_snapshot(option: Any) -> dict[str, Any]:
        return build_training_option_snapshot(option)

    def get_resource_preflight(self) -> ResourcePreflightResult:
        return self._service().get_resource_preflight()

    def handle_configure_training(self, command: Command) -> HandlerResult:
        return self._service().handle_configure_training(command)

    def handle_train(
        self,
        command: Command,
        *,
        defer_synchronous_completion: bool = False,
    ) -> HandlerResult:
        return self._service().handle_train(
            command,
            defer_synchronous_completion=defer_synchronous_completion,
        )

    def resolve_train_preflight(
        self,
        command: Command,
        *,
        datasets: Any,
    ) -> tuple[ResourcePreflightResult, bool]:
        return self._service().resolve_train_preflight(
            command,
            datasets=datasets,
        )

    def start_train_after_preflight(
        self,
        command: Command,
        *,
        preflight: ResourcePreflightResult,
        receipt_reused: bool,
        defer_synchronous_completion: bool = False,
    ) -> HandlerResult:
        return self._service().start_train_after_preflight(
            command,
            preflight=preflight,
            receipt_reused=receipt_reused,
            defer_synchronous_completion=defer_synchronous_completion,
        )

    def discard_train_preflight(self, token: str | None) -> None:
        self._service().discard_train_preflight(token)

    def complete_synchronous_training(
        self,
        expected_trainer_identity: str,
    ) -> tuple[str, dict[str, Any]]:
        return self._service().complete_synchronous_training(expected_trainer_identity)

    def handle_stop_training(self, command: Command) -> HandlerResult:
        return self._service().handle_stop_training(command)

    def handle_clear_training_history(self, command: Command) -> HandlerResult:
        return self._service().handle_clear_training_history(command)


class _LazyAnalysisCommandService:
    """Defer NumPy/visualization analysis service until analysis commands run."""

    def __init__(
        self,
        *,
        training_runtime: TrainingProjectionReadPort,
        visualization: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.training_runtime = training_runtime
        self.visualization = visualization
        self._get_state = get_state
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .analysis_service import AnalysisCommandService  # noqa: PLC0415

            self._service_instance = AnalysisCommandService(
                training_runtime=self.training_runtime,
                visualization=self.visualization,
                get_state=self._get_state,
            )
        return self._service_instance

    def handle_evaluate(self, command: Command) -> HandlerResult:
        return self._service().handle_evaluate(command)

    def handle_visualize(self, command: Command) -> HandlerResult:
        return self._service().handle_visualize(command)

    def handle_saliency(self, command: Command) -> HandlerResult:
        return self._service().handle_saliency(command)


class ApplicationService(Observable):
    """Command spine composed from Study-owned domain ports."""

    def __init__(self, study: Study | None = None) -> None:
        super().__init__()
        target_study = study if study is not None else Study()
        command_lock = getattr(target_study, "_application_command_lock", RLock())
        self._initialize_components(target_study, command_lock)

    def _initialize_components(self, study: Study, command_lock: RLock) -> None:
        self.study = study
        self._command_lock = command_lock
        self.training_runtime = StudyTrainingRuntime(self.study)
        self.dataset = self.study.dataset_state_service
        self.dataset_state = self.dataset
        self.preprocess: PreprocessProductPort = self.study.preprocess_state_service
        self.training: TrainingProductPort = self.study.training_state_service
        self.training_lifecycle_events = self.study.training_state_service
        self.visualization: VisualizationProductPort = (
            self.study.visualization_state_service
        )
        self.training_state = TrainingStateReadModel(self.training_runtime)
        self.evaluation_state = EvaluationStateReadModel(self.training_runtime)
        self._last_error: ErrorSnapshot | None = None
        self._command_admission_lock = Lock()
        self._synchronous_training_lifecycle_lock = (
            self.study._synchronous_training_lifecycle_lock
        )
        self._mutation_in_progress = False
        self._publication_delivery_fence_depth = 0
        self.pipeline_transaction = PipelineStateTransaction(
            self.study,
            training_runtime=self.training_runtime,
        )
        self.interpretation = _LazyDataInterpretationCommandService(
            self.dataset,
            self.pipeline_transaction,
        )
        self.data_compatibility = _LazyDataCompatibilityCommandService(
            dataset=self.dataset,
            interpretation=self.interpretation,
            pipeline_transaction=self.pipeline_transaction,
        )
        self.legacy_raw_mutation_lifecycle = _LegacyRawMutationLifecycleCoordinator(
            self.interpretation,
        )
        self.data_table = DataTableCommandService(dataset=self.dataset_state)
        self.preprocess_commands = PreprocessCommandService(
            preprocess=self.preprocess,
            dataset=self.dataset,
            get_state=self.get_state,
        )
        self.dataset_generation = _LazyDatasetGenerationCommandService(
            study=self.study,
            training=self.training,
            has_trainer=self.training_runtime.has_trainer,
            pipeline_transaction=self.pipeline_transaction,
            get_publication_generation=(
                lambda: self._committed_view_publication().generation
            ),
        )
        self.training_configuration_reset = TrainingConfigurationResetService(
            training=self.training,
            training_runtime=self.training_runtime,
        )
        self.training_recommendation = TrainingRecommendationService()
        self.training_commands = _LazyTrainingCommandService(
            training=self.training,
            training_runtime=self.training_runtime,
            get_state=self.get_state,
            configuration_reset=self.training_configuration_reset,
            recommendation=self.training_recommendation,
        )
        self.saliency_coverage_projector = SaliencyCoverageProjector()
        self.state_snapshot = StateSnapshotService(
            study=self.study,
            dataset=self.dataset_state,
            preprocess=self.preprocess,
            training=self.training_state,
            training_runtime=self.training_runtime,
            evaluation=self.evaluation_state,
            visualization=self.visualization,
            dataset_generation=self.dataset_generation,
            training_commands=self.training_commands,
            interpretation=self.interpretation,
            saliency_coverage_projector=self.saliency_coverage_projector,
            training_recommendation=self.training_recommendation,
        )
        initial_training_boundary = self.state_snapshot.capture_training_read_boundary()
        initial_state = self.state_snapshot.build(last_error=self._last_error)
        initial_training_history = (
            tuple(self.state_snapshot.training_history())
            if initial_state.state_reliable and initial_training_boundary.stable
            else ()
        )
        initial_data_summary_rows = (
            tuple(self._build_data_summary_rows())
            if initial_state.state_reliable and initial_training_boundary.stable
            else None
        )
        final_initial_training_boundary = (
            self.state_snapshot.capture_training_read_boundary()
        )
        self._view_coordinator = ApplicationViewCoordinator(
            initial_state,
            initial_training_boundary=final_initial_training_boundary,
            build_state=lambda: self.state_snapshot.build(last_error=self._last_error),
            build_training_history=self.state_snapshot.training_history,
            build_data_summary_rows=self._build_data_summary_rows,
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
            initial_training_history=initial_training_history,
            initial_data_summary_rows=initial_data_summary_rows,
        )
        if (
            initial_training_boundary != final_initial_training_boundary
            or not final_initial_training_boundary.stable
        ):
            self._view_coordinator.mark_stale(
                "Training state changed during application initialization."
            )
        initial_publication = self._view_coordinator.committed()
        self._view_event_publisher = ApplicationViewEventPublisher(
            initial_revision=initial_publication.revision,
            deliver=lambda publication: self.notify_delivery(
                APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
                publication,
            ),
            unobserved_delivery_policy=(
                UnobservedDeliveryPolicy.ACKNOWLEDGE_WITHOUT_RENDER
            ),
        )
        self.publication_lifecycle = ApplicationPublicationLifecycle(
            training_events=self.training_lifecycle_events,
            training_runtime=self.training_runtime,
            visualization=self.visualization,
            state_snapshot=self.state_snapshot,
            command_lock=self._command_lock,
            command_admission_lock=self._command_admission_lock,
            is_closed=(
                lambda: self.shutdown_lifecycle.is_closing
                or self.shutdown_lifecycle.is_closed
            ),
            is_mutation_in_progress=self._publication_delivery_is_fenced,
            is_shutdown_fenced=(lambda: self.shutdown_lifecycle.is_shutdown_fenced),
            refresh_training_publication=self._refresh_training_publication_strict,
            committed_view_publication=self._committed_view_publication,
            publish_view_changed=self._publish_view_changed,
            view_revision_delivered=(self._view_event_publisher.has_delivered_revision),
        )
        self.training_publications = self.publication_lifecycle.coordinator
        self.saliency_render = SaliencyRenderPublisher(
            training_runtime=self.training_runtime,
            get_publication=self._committed_view_publication,
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
        )
        self.evaluation_render = EvaluationRenderPublisher(
            training_runtime=self.training_runtime,
            get_publication=self._committed_view_publication,
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
        )
        self.preprocess_render = PreprocessRenderPublisher(
            dataset=self.dataset_state,
            get_publication=self._committed_view_publication,
        )
        self.dataset_split_preview = DatasetSplitPreviewPublisher(
            dataset=self.dataset_state,
            generator_factory=self.study.get_datasets_generator,
            get_publication=self._committed_view_publication,
        )
        self.query_state_commands = QueryStateCommandService(
            study=self.study,
            dataset=self.dataset_state,
            state_builder=self.state_snapshot,
            get_state=self.get_state,
        )
        self.analysis = _LazyAnalysisCommandService(
            training_runtime=self.training_runtime,
            visualization=self.visualization,
            get_state=self.get_state,
        )
        self.lifecycle = LifecycleCommandService(
            study=self.study,
            dataset=self.dataset,
            preprocess=self.preprocess,
            training=self.training,
            training_commands=self.training_commands,
            interpretation=self.interpretation,
            get_state=self.get_state,
            pipeline_transaction=self.pipeline_transaction,
        )
        self.post_training_saliency = PostTrainingSaliencyAutomation(
            training=self.training,
            get_state=self.get_state,
            configure_saliency=self._configure_post_training_saliency,
            publish_submission_failure=(
                self.training_runtime.publish_saliency_submission_failure
            ),
            read_terminal_outcome=self.training_runtime.terminal_outcome,
        )
        self.shutdown_lifecycle = ApplicationShutdownLifecycleCoordinator(
            command_admission_lock=self._command_admission_lock,
            command_lock=self._command_lock,
            synchronous_training_lifecycle_lock=(
                self._synchronous_training_lifecycle_lock
            ),
            training=self.training,
            training_runtime=self.training_runtime,
            dataset_split_preview=self.dataset_split_preview,
            post_training_saliency=self.post_training_saliency,
            publication_lifecycle=self.publication_lifecycle,
            refresh_training_publication=self._refresh_training_publication_strict,
            committed_view_publication=self._committed_view_publication,
            wait_for_synchronous_training_quiescence=(
                self._wait_for_synchronous_training_quiescence
            ),
        )
        self.synchronous_training_lifecycle = SynchronousTrainingLifecycleCoordinator(
            training_runtime=self.training_runtime,
            terminal_notifications=self.training,
            retry_terminal_delivery=(
                self._retry_synchronous_training_terminal_delivery
            ),
            command_lock=self._command_lock,
            complete_training=(self.training_commands.complete_synchronous_training),
            committed_publication=self._committed_view_publication,
            clear_last_error=self._clear_last_error,
            state_after_command=self._state_after_command,
            changed_state=self._changed_state,
            post_state_verification_failure=(
                self._post_state_verification_failure_result
            ),
            handler_failure=self._handler_failure_result,
            completion_is_closed=lambda: self.shutdown_lifecycle.is_closed,
        )
        self._command_handlers = self._build_command_handlers()
        self.publication_lifecycle.start()

    def _wait_for_synchronous_training_quiescence(self, timeout: float) -> bool:
        return self.synchronous_training_lifecycle.wait_until_quiescent(timeout=timeout)

    def _build_data_summary_rows(self) -> list[dict[str, Any]]:
        """Return the active detached dataset rows for one view publication."""
        preprocessed_rows = self.dataset.get_preprocessed_data_rows()
        if preprocessed_rows:
            return preprocessed_rows
        return self.dataset.get_loaded_data_rows()

    def close(self) -> None:
        """Idempotently detach lifecycle observers and release runtime ownership."""
        from .runtime import begin_application_service_close  # noqa: PLC0415

        if not begin_application_service_close(
            self.study,
            self,
            self.shutdown_lifecycle.begin_close,
        ):
            return
        self.shutdown_lifecycle.cancel_close_automation()
        self.publication_lifecycle.close()

    @property
    def is_closed(self) -> bool:
        """Return whether this service instance has released runtime ownership."""
        return self.shutdown_lifecycle.is_closed

    def _closed_command_result(self, command: Command | Any) -> CommandResult:
        """Return a stable rejection without rebuilding closed backend state."""
        publication = self._committed_view_publication()
        try:
            name = command_name(command).value
        except Exception:
            name = _UNRECOGNIZED_COMMAND_NAME
        return CommandResult.failure_result(
            command_name=name,
            message=_CLOSED_SERVICE_MESSAGE,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=_CLOSED_SERVICE_MESSAGE,
            diagnostics={
                "application_service_closed": True,
                "publication_generation": publication.generation,
                "publication_revision": publication.revision,
            },
        )

    def _closed_command_result_if_any(
        self,
        command: Command | Any,
    ) -> CommandResult | None:
        """Check command admission against the service lifetime boundary."""
        if not self.shutdown_lifecycle.snapshot().closed:
            return None
        return self._closed_command_result(command)

    def _ensure_open(self) -> None:
        """Reject direct API reads after this service released ownership."""
        if self.shutdown_lifecycle.snapshot().closed:
            raise RuntimeError(_CLOSED_SERVICE_MESSAGE)

    def dispose(self) -> None:
        """Compatibility alias for explicit ApplicationService cleanup."""
        self.close()

    def _publish_training_terminal_state(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> bool:
        """Compatibility delegate retained for out-of-scope UI lifecycle callers."""
        return self.publication_lifecycle.publish_training_terminal_state(
            *_args,
            **_kwargs,
        )

    def _configure_post_training_saliency(
        self,
        params: dict[str, object],
    ) -> CommandResult:
        """Run the recommended baseline through the normal command boundary."""
        result = self.execute(SaliencyCommand(method="Gradient", params=params))
        if result.failed:
            logger.warning(
                "Automatic post-training saliency failed: %s",
                result.message,
            )
        return result

    def _handle_train_with_automation(self, command: Command) -> HandlerResult:
        """Admit candidate resources before publishing the saved data split."""
        if not isinstance(command, TrainCommand):
            raise TypeError("Invalid command for train")
        candidate = self.dataset_generation.prepare_saved_split_candidate()
        try:
            preflight, receipt_reused = self.training_commands.resolve_train_preflight(
                command,
                datasets=candidate.datasets,
            )
        except ResourceConfirmationRequiredError:
            raise
        except Exception as exc:
            candidate_discarded = self.dataset_generation.discard_prepared_split()
            application_error = map_exception(exc)
            raise ApplicationError(
                message=application_error.message,
                error_type=application_error.error_type,
                recoverable=application_error.recoverable,
                diagnostics={
                    **application_error.diagnostics,
                    "state_preserved": True,
                    "split_candidate_discarded": candidate_discarded,
                },
            ) from exc

        split_preparation: dict[str, Any] | None = None
        try:
            split_preparation = self.dataset_generation.commit_prepared_split(candidate)
            self.post_training_saliency.arm(append=command.append)
            result = self.training_commands.start_train_after_preflight(
                command,
                preflight=preflight,
                receipt_reused=receipt_reused,
                defer_synchronous_completion=not command.interactive,
            )
        except Exception as exc:
            self.post_training_saliency.cancel()
            if split_preparation is not None:
                try:
                    self.dataset_generation.restore_committed_candidate(candidate)
                except Exception as rollback_exc:
                    rollback_error = map_exception(rollback_exc)
                    raise ApplicationError(
                        message=rollback_error.message,
                        error_type=rollback_error.error_type,
                        recoverable=rollback_error.recoverable,
                        diagnostics={
                            **rollback_error.diagnostics,
                            "state_preserved": False,
                            "split_rollback": False,
                            "rollback_failed": True,
                        },
                    ) from rollback_exc
                application_error = map_exception(exc)
                raise ApplicationError(
                    message=application_error.message,
                    error_type=application_error.error_type,
                    recoverable=application_error.recoverable,
                    diagnostics={
                        **application_error.diagnostics,
                        "state_preserved": True,
                        "split_rollback": True,
                    },
                ) from exc
            else:
                self.dataset_generation.discard_prepared_split()
            raise
        message, diagnostics = self._normalize_handler_result(result)
        return message, {
            **diagnostics,
            "split_preparation": split_preparation,
        }

    def _handle_discard_training_preparation(
        self,
        command: Command,
    ) -> HandlerResult:
        """Discard warning confirmation and candidate without active mutation."""
        if not isinstance(command, DiscardTrainingPreparationCommand):
            raise TypeError("Invalid command for discard_training_preparation")
        try:
            self.training_commands.discard_train_preflight(
                command.resource_preflight_token
            )
        finally:
            candidate_discarded = self.dataset_generation.discard_prepared_split()
        self.post_training_saliency.cancel()
        return (
            "Training preparation discarded.",
            {
                "candidate_discarded": candidate_discarded,
                "resource_preflight_discarded": bool(command.resource_preflight_token),
                "state_preserved": True,
            },
        )

    def get_state(self) -> ApplicationStateSnapshot:
        """Return a fresh serializable snapshot of backend state."""
        with self.training_publications.capture_saliency_notifications():
            with self._command_lock:
                self._ensure_open()
                mutation_in_progress = self._mutation_in_progress
                if mutation_in_progress:
                    state = self._view_coordinator.refresh_strict(publish=False)
                else:
                    state = self._refresh_training_publication_strict()
            if not mutation_in_progress:
                self.publication_lifecycle.reconcile_pending_saliency_terminal()
            return state

    def _refresh_training_publication_strict(self) -> ApplicationStateSnapshot:
        """Publish state and its stable trainer identity as one generation."""
        return self._view_coordinator.refresh_strict()

    def _refresh_training_publication_opportunistic(
        self,
    ) -> ApplicationViewPublication:
        """Recover one stale state/boundary publication without raising."""
        return self._view_coordinator.refresh_opportunistic()

    def get_capabilities(self) -> CapabilityPolicy:
        """Return capabilities from one committed application publication."""
        return self.get_view_publication().effective_capabilities

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return committed truth, recovering a stale view only when reads are safe."""
        self._ensure_open()
        publication = self._committed_view_publication()
        if publication.usable:
            return publication

        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return publication
        try:
            self._ensure_open()
            publication = self._committed_view_publication()
            if publication.usable or self._mutation_in_progress:
                return publication
            self._refresh_training_publication_opportunistic()
        finally:
            self._command_lock.release()
        # Recovery can change publication health without changing domain
        # generation. Deliver the latest committed revision after releasing the
        # mutation lock so Qt and headless observers converge on the same truth.
        publication = self._committed_view_publication()
        self._publish_view_changed(publication)
        return publication

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Return one detached render DTO guarded by publication/training identity."""
        self._ensure_open()
        return self.saliency_render.publish(request)

    def get_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Return detached Evaluation data guarded by publication/training identity."""
        self._ensure_open()
        return self.evaluation_render.publish(request)

    def get_preprocess_render(
        self,
        request: PreprocessRenderRequest,
    ) -> PreprocessRenderPublication:
        """Return one bounded signal DTO without transferring mutable EEG objects."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            raise PreconditionError(
                "Signal preview is busy. Wait for the current action and retry.",
                diagnostics={
                    "preprocess_render_unavailable": True,
                    "retryable": True,
                },
            )
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                raise PreconditionError(
                    "Signal preview is changing. Wait for the action to finish.",
                    diagnostics={
                        "preprocess_render_unavailable": True,
                        "retryable": True,
                    },
                )
            return self.preprocess_render.publish(request)
        finally:
            self._command_lock.release()

    def get_epoch_dialog_context(self) -> EpochDialogContext:
        """Return one detached epoch setup bound to a committed publication."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return EpochDialogContext.unavailable(
                reason="EEG epoch setup is busy. Wait for the current action and retry."
            )
        try:
            self._ensure_open()
            publication = self._committed_view_publication()
            capability = publication.effective_capabilities.get(
                CommandName.CREATE_EPOCH
            )
            if self._mutation_in_progress or not publication.usable:
                return EpochDialogContext.unavailable(
                    reason=(
                        publication.public_unavailable_reason
                        or EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE
                    ),
                    capability=capability,
                    publication_generation=publication.generation,
                )
            state = publication.state
            if (
                not isinstance(state, ApplicationStateSnapshot)
                or state.state_reliable is not True
                or state.read_errors
                or not isinstance(state.interpretation, InterpretationStateSnapshot)
            ):
                return EpochDialogContext.unavailable(
                    capability=capability,
                    publication_generation=publication.generation,
                )
            handoff = validated_epoch_handoff(state.interpretation.epoch_handoff)
            setup = build_epoching_context(
                self.dataset_state.get_preprocessed_data_list(),
                epoch_handoff=handoff,
            )
            require_epoch_context_available(setup)
            return EpochDialogContext(
                capability=capability,
                epoch_handoff=handoff,
                epoch_setup=setup,
                publication_generation=publication.generation,
                usable=True,
                unavailable_reason=None,
            )
        except PreconditionError as exc:
            publication = self._committed_view_publication()
            return EpochDialogContext.unavailable(
                reason=str(exc),
                capability=publication.effective_capabilities.get(
                    CommandName.CREATE_EPOCH
                ),
                publication_generation=publication.generation,
            )
        except (TypeError, ValueError):
            logger.error("Failed to build detached EEG epoch setup.", exc_info=True)
            publication = self._committed_view_publication()
            return EpochDialogContext.unavailable(
                publication_generation=publication.generation,
            )
        finally:
            self._command_lock.release()

    def get_training_recommendation(
        self,
        *,
        expected_publication_generation: int | None = None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
        prospective_device: str | None = None,
    ) -> TrainingRecommendation:
        """Return a metadata-only recommendation at the dialog boundary."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            raise PreconditionError("Training recommendation is busy. Wait and retry.")
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                raise PreconditionError("Training context is changing. Wait and retry.")
            publication = self._committed_view_publication()
            if (
                expected_publication_generation is not None
                and publication.generation != expected_publication_generation
            ):
                raise PreconditionError(
                    "Training context changed. Review the settings again."
                )
            if not publication.usable:
                raise PreconditionError(
                    publication.public_unavailable_reason
                    or "Training recommendation is unavailable."
                )
            if prospective_model_name is not None:
                if not isinstance(prospective_model_name, str) or not (
                    prospective_model_name.strip()
                ):
                    raise PreconditionError("Prospective model name is invalid.")
                try:
                    prospective_model_params = dict(prospective_model_params or {})
                except (TypeError, ValueError) as exc:
                    raise PreconditionError(
                        "Prospective model parameters are invalid."
                    ) from exc
                prospective_model_name = prospective_model_name.strip()
            elif prospective_model_params:
                raise PreconditionError(
                    "Prospective model parameters require a model name."
                )
            if prospective_device is not None:
                if not isinstance(prospective_device, str) or not (
                    prospective_device.strip()
                ):
                    raise PreconditionError("Prospective training device is invalid.")
                prospective_device = prospective_device.strip()
            return self.state_snapshot.refresh_training_recommendation(
                publication.state,
                prospective_model_name=prospective_model_name,
                prospective_model_params=prospective_model_params,
                prospective_device=prospective_device,
            )
        finally:
            self._command_lock.release()

    def get_dataset_split_context(
        self,
        request: DatasetSplitContextRequest,
    ) -> DatasetSplitContextPublication:
        """Return detached split choices without transferring live Epochs."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            raise PreconditionError(
                "Dataset splitting is busy. Wait for the current action and retry.",
                diagnostics={
                    "dataset_split_context_unavailable": True,
                    "retryable": True,
                },
            )
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                raise PreconditionError(
                    "Dataset splitting is changing. Wait for the action to finish.",
                    diagnostics={
                        "dataset_split_context_unavailable": True,
                        "retryable": True,
                    },
                )
            return self.dataset_split_preview.publish_context(request)
        finally:
            self._command_lock.release()

    def get_dataset_split_preview(
        self,
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        """Return detached speculative split rows under the command lock."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            raise PreconditionError(
                "Dataset split preview is busy. Wait and retry.",
                diagnostics={
                    "dataset_split_preview_unavailable": True,
                    "retryable": True,
                },
            )
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                raise PreconditionError(
                    "Dataset splitting is changing. Wait for the action to finish.",
                    diagnostics={
                        "dataset_split_preview_unavailable": True,
                        "retryable": True,
                    },
                )
            return self.dataset_split_preview.publish_preview(request)
        finally:
            self._command_lock.release()

    def cancel_dataset_split_preview(self, request_id: str) -> bool:
        """Cancel one preview without waiting on the command lock it occupies."""
        if self.shutdown_lifecycle.is_closed:
            return False
        return self.dataset_split_preview.cancel_preview(request_id)

    def get_training_resource_preflight(self) -> ResourcePreflightResult | None:
        """Check current training resources without waiting on an active command."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return None
        try:
            self._ensure_open()
            return self.training_commands.get_resource_preflight()
        finally:
            self._command_lock.release()

    def get_interpretation_review(
        self,
        *,
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> dict[str, Any]:
        """Return the exact pending Data Import review without blocking the UI."""
        if expected_identity is not None and not isinstance(
            expected_identity,
            InterpretationReviewIdentity,
        ):
            raise TypeError("Expected interpretation review identity must be typed.")
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            raise PreconditionError(
                "Data Import review is busy. Wait for the current action and retry."
            )
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                raise PreconditionError(
                    "Data Import review is changing. Wait for the action to finish."
                )
            publication = self._committed_view_publication()
            if expected_identity is not None:
                current = publication.state.interpretation
                matches = bool(
                    publication.usable
                    and publication.generation
                    == expected_identity.publication_generation
                    and current.latest_scan_id == expected_identity.scan_id
                    and current.latest_candidate_id == expected_identity.candidate_id
                )
                if not matches:
                    raise PreconditionError(
                        "The Data Import review changed before it could be opened. "
                        "Open the current review and try again.",
                        diagnostics={
                            "stale_interpretation_review": True,
                            "publication_usable": publication.usable,
                            "expected_publication_generation": (
                                expected_identity.publication_generation
                            ),
                            "current_publication_generation": publication.generation,
                            "expected_scan_id": expected_identity.scan_id,
                            "current_scan_id": current.latest_scan_id,
                            "expected_candidate_id": expected_identity.candidate_id,
                            "current_candidate_id": current.latest_candidate_id,
                        },
                    )
            review = self.interpretation.current_review()
            if expected_identity is not None:
                scan = review.get("scan_result")
                candidate = review.get("candidate")
                scan_id = scan.get("scan_id") if isinstance(scan, dict) else None
                candidate_id = (
                    candidate.get("candidate_id")
                    if isinstance(candidate, dict)
                    else None
                )
                if (
                    scan_id != expected_identity.scan_id
                    or candidate_id != expected_identity.candidate_id
                ):
                    raise PreconditionError(
                        "The Data Import review identity could not be verified.",
                        diagnostics={
                            "stale_interpretation_review": True,
                            "review_payload_mismatch": True,
                            "expected_scan_id": expected_identity.scan_id,
                            "current_scan_id": scan_id,
                            "expected_candidate_id": expected_identity.candidate_id,
                            "current_candidate_id": candidate_id,
                        },
                    )
            return review
        finally:
            self._command_lock.release()

    def wait_for_background_tasks(
        self,
        timeout: float | None = None,
        *,
        training_handoff_generation: int | None = None,
    ) -> bool:
        """Wait for application-owned background work at a lifecycle boundary.

        Desktop UI code must remain non-blocking and should observe published state.
        This explicit wait is for headless workflows, integration gates, and shutdown
        coordination that require a stable object-bearing read after training.
        """

        deadline = None if timeout is None else monotonic() + max(0.0, timeout)

        def remaining() -> float | None:
            if deadline is None:
                return None
            return max(0.0, deadline - monotonic())

        if not self.training.wait_for_terminal_notification(
            training_handoff_generation,
            timeout=remaining(),
        ):
            return False
        terminal_reconciled = (
            self.publication_lifecycle.publish_training_terminal_state()
        )
        if not self.training_publications.wait_for_training_delivery(
            timeout=remaining()
        ):
            return False
        if not self.post_training_saliency.wait_for_idle(timeout=remaining()):
            return False
        if not self.training_runtime.wait_for_saliency_job(timeout=remaining()):
            return False
        if not self.training_runtime.wait_for_saliency_delivery(timeout=remaining()):
            return False
        if not self.training_publications.wait_for_saliency_delivery(
            timeout=remaining()
        ):
            return False
        return terminal_reconciled or (
            self.publication_lifecycle.publish_training_terminal_state()
        )

    def _committed_view_publication(self) -> ApplicationViewPublication:
        """Copy the internal publication without exposing mutable nested values."""
        return self._view_coordinator.committed()

    def query_published_state(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Return a safe UI read model without waiting for an active mutation."""
        command = QueryStateCommand(query="state")
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed
        publication = self._committed_view_publication()
        if (
            not publication.usable
            and self.publication_lifecycle.pending_saliency_terminal() is not None
        ):
            self.publication_lifecycle.reconcile_pending_saliency_terminal(
                blocking=False
            )
            publication = self._committed_view_publication()
        if expected_publication_generation is not None:
            rejection = self._expected_publication_rejection_for_publication(
                command,
                expected_publication_generation,
                publication,
            )
            if rejection is not None:
                return rejection
        diagnostics = {
            "state": publication.state.to_dict(),
            "capabilities": publication.effective_capabilities.to_dict(),
            "publication_generation": publication.generation,
            "publication_revision": publication.revision,
            "state_reliable": publication.state.state_reliable,
            "view_verified": publication.verified,
            "view_stale": publication.stale,
        }
        if publication.refresh_error is not None:
            diagnostics["view_refresh_error"] = publication.refresh_error
        if not publication.usable:
            message = publication.unavailable_reason or (
                "Application state could not be verified. Retry shortly."
            )
            return CommandResult.failure_result(
                command_name=CommandName.QUERY_STATE.value,
                message=message,
                state=publication.state,
                changed_state=ChangedState(state_unknown=True),
                error_type=ErrorType.PRECONDITION,
                recoverable=True,
                error_message=message,
                diagnostics=diagnostics,
            )
        return CommandResult.success_result(
            command_name=CommandName.QUERY_STATE.value,
            message=pipeline_stage_readiness_summary(publication.state),
            state=publication.state,
            changed_state=ChangedState(),
            diagnostics=diagnostics,
        )

    def execute(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Execute one command inside the typed notification boundary."""
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed
        if isinstance(command, QueryStateCommand):
            result, completion_release = self._execute_at_command_boundary(
                command,
                expected_publication_generation=expected_publication_generation,
            )
            try:
                self._publish_committed_view()
                return result
            finally:
                if completion_release is not None:
                    completion_release()
        visualization_notifications = (
            self.visualization.batch_notifications()
            if isinstance(command, SaliencyCommand)
            else nullcontext()
        )
        manager_notifications = self.training_runtime.defer_saliency_terminal(
            self.publication_lifecycle.commit_post_training_saliency_terminal_state
        )
        visualization_batch_generation: int | None = None
        completion_release: Callable[[], None] | None = None
        try:
            with (
                self.training_publications.capture_saliency_notifications(),
                visualization_notifications,
                manager_notifications,
            ):
                if isinstance(command, SaliencyCommand):
                    visualization_batch_generation = (
                        self.publication_lifecycle.visualization_batch_generation()
                    )
                result, completion_release = self._execute_at_command_boundary(
                    command,
                    expected_publication_generation=expected_publication_generation,
                )
            result = self._retry_failed_manual_saliency_delivery(
                command,
                result,
                visualization_batch_generation,
            )
            self._publish_committed_view()
            return result
        finally:
            if completion_release is not None:
                completion_release()

    def _publish_committed_view(self) -> bool:
        """Deliver unseen committed truth and retry unacknowledged revisions."""
        shutdown = self.shutdown_lifecycle.snapshot()
        if (
            shutdown.closing
            or shutdown.closed
            or self._publication_delivery_is_fenced()
        ):
            return False
        return self._publish_view_changed(self._committed_view_publication())

    def _publication_delivery_is_fenced(self) -> bool:
        """Whether observers must wait for the active command to verify its view."""
        return self._mutation_in_progress or self._publication_delivery_fence_depth > 0

    def _publish_view_changed(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Notify consumers with one immutable committed publication."""
        if not isinstance(publication, ApplicationViewPublication):
            raise TypeError(
                "Application publication events require ApplicationViewPublication."
            )
        return self._view_event_publisher.publish(publication)

    def acknowledge_view_publication_delivery(
        self,
        revision: int,
        *,
        owner: object | None = None,
    ) -> bool:
        """Acknowledge that a product consumer rendered one publication revision."""
        acknowledged = self._view_event_publisher.acknowledge(
            revision,
            owner=owner,
        )
        if acknowledged:
            self.training_publications.retry_training_terminal_delivery()
        return acknowledged

    def require_visible_view_publication_acknowledgement(self, owner: object) -> None:
        """Claim desktop-visible acknowledgement ownership from now on."""
        self._view_event_publisher.require_acknowledging_subscriber(owner)

    def reject_view_publication_delivery(
        self,
        publication: ApplicationViewPublication,
        *,
        owner: object | None = None,
    ) -> bool:
        """Release one deferred publication after a visible render failure."""
        return self._view_event_publisher.reject(publication, owner=owner)

    def _retry_failed_manual_saliency_delivery(
        self,
        command: Command | Any,
        result: CommandResult,
        batch_generation: int | None,
    ) -> CommandResult:
        """Retry one failed manual saliency observer delivery after batch flush."""
        if (
            not isinstance(command, SaliencyCommand)
            or not result.ok
            or result.diagnostics.get("action") != "configure"
            or batch_generation is None
        ):
            return result
        delivered = self.visualization.consume_batched_delivery(
            "saliency_changed",
            batch_generation,
        )
        if delivered is not False:
            return result
        retry_delivered = self.visualization.notify("saliency_changed") is not False
        diagnostics = {
            **result.diagnostics,
            "view_notification_retry_attempted": True,
            "view_notification_delivered": retry_delivered,
        }
        if not retry_delivered:
            diagnostics["view_refresh_error"] = (
                "Saliency changed, but the visualization observer rejected both "
                "delivery attempts."
            )
            logger.error(diagnostics["view_refresh_error"])
        return replace(result, diagnostics=diagnostics)

    def _execute_at_command_boundary(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None = None,
    ) -> tuple[CommandResult, Callable[[], None] | None]:
        """Execute a command and return a result envelope."""
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed, None
        if self._is_published_state_query(command):
            return (
                self.query_published_state(
                    expected_publication_generation=expected_publication_generation,
                ),
                None,
            )
        if isinstance(command, QueryStateCommand):
            return (
                self._execute_query_without_wait(
                    command,
                    expected_publication_generation=expected_publication_generation,
                ),
                None,
            )

        train_command = command if isinstance(command, TrainCommand) else None
        synchronous_train = train_command is not None and not train_command.interactive
        lifecycle_boundary = (
            self._synchronous_training_lifecycle_lock
            if train_command is not None
            else nullcontext()
        )
        completion_release: Callable[[], None] | None = None
        with lifecycle_boundary:
            if (
                train_command is not None
                and not self.training.is_training()
                and not self.training.wait_until_restart_safe(
                    timeout=_TRAINING_RESTART_SAFETY_WAIT_SECONDS,
                )
            ):
                return self._training_restart_pending_result(), None
            result = self._execute_with_command_lock(
                command,
                expected_publication_generation=expected_publication_generation,
            )
            if (
                synchronous_train
                and result.ok
                and result.diagnostics.get("synchronous_completion_deferred") is True
            ):
                completion_release = (
                    self.synchronous_training_lifecycle.admit_deferred_completion()
                )

        try:
            if completion_release is not None:
                result = self.synchronous_training_lifecycle.complete_deferred(result)

            if not self.shutdown_lifecycle.is_closed:
                try:
                    self.training_publications.retry_training_terminal_delivery()
                except Exception:
                    logger.exception(
                        "Could not retry retained terminal training publication"
                    )
            if synchronous_train and result.ok:
                generation = self.synchronous_training_lifecycle.handoff_generation(
                    result
                )
                if generation is None:
                    result = (
                        self.synchronous_training_lifecycle.background_delivery_failure(
                            result,
                            reason=(
                                "Training completed, but its terminal handoff identity "
                                "was unavailable."
                            ),
                            invalid_handoff=True,
                        )
                    )
                elif not self.wait_for_background_tasks(
                    timeout=_SYNCHRONOUS_BACKGROUND_WAIT_SECONDS,
                    training_handoff_generation=generation,
                ):
                    result = (
                        self.synchronous_training_lifecycle.background_delivery_failure(
                            result,
                            reason=(
                                "Training completed, but its final application updates "
                                "could not be delivered. Retry after the application "
                                "becomes idle."
                            ),
                        )
                    )
        except BaseException:
            if completion_release is not None:
                completion_release()
            raise
        return result, completion_release

    def _retry_synchronous_training_terminal_delivery(
        self,
        _generation: int,
    ) -> bool:
        """Retry the retained terminal publication outside lifecycle locks."""
        return bool(self.training_publications.retry_training_terminal_delivery())

    def _training_restart_pending_result(self) -> CommandResult:
        """Return a retryable result when terminal monitor cleanup is incomplete."""
        publication = self._committed_view_publication()
        message = (
            "The previous training run is still finalizing. Retry after its final "
            "status is published."
        )
        return CommandResult.failure_result(
            command_name=CommandName.TRAIN.value,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={"training_restart_pending": True},
        )

    def _execute_with_command_lock(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Serialize command admission and its immediate backend mutation."""
        with self._command_lock:
            self._publication_delivery_fence_depth += 1
            try:
                admission = self.shutdown_lifecycle.snapshot()
                closed = admission.closed
                rejected_by_shutdown = admission.fenced and not isinstance(
                    command,
                    (
                        QueryStateCommand,
                        StopTrainingCommand,
                    ),
                )
                if closed:
                    result = self._closed_command_result(command)
                elif rejected_by_shutdown:
                    result = self._shutdown_fence_rejection(command)
                elif expected_publication_generation is not None:
                    expected_rejection = self._expected_publication_rejection(
                        command,
                        expected_publication_generation,
                    )
                    result = (
                        expected_rejection
                        if expected_rejection is not None
                        else self._execute_serialized(command)
                    )
                else:
                    result = self._execute_serialized(command)
            finally:
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )
        return result

    def _expected_publication_rejection(
        self,
        command: Command | Any,
        expected_generation: int,
    ) -> CommandResult | None:
        """Reject a generation-bound mutation against any other committed view."""
        return self._expected_publication_rejection_for_publication(
            command,
            expected_generation,
            self._committed_view_publication(),
        )

    @staticmethod
    def _expected_publication_rejection_for_publication(
        command: Command | Any,
        expected_generation: int,
        publication: ApplicationViewPublication,
    ) -> CommandResult | None:
        """Validate a command against the exact publication it will consume."""
        if (
            isinstance(expected_generation, bool)
            or not isinstance(expected_generation, int)
            or expected_generation < 0
        ):
            raise ValueError(
                "Expected publication generation must be a non-negative integer."
            )
        if publication.usable and publication.generation == expected_generation:
            return None
        try:
            name = command_name(command).value
        except Exception:
            name = _UNRECOGNIZED_COMMAND_NAME
        message = (
            "Workflow state changed while this confirmed action was pending. "
            "Review the action again before continuing."
            if publication.usable
            else (
                "Workflow state is unavailable. Review the action again after "
                "it recovers."
            )
        )
        return CommandResult.failure_result(
            command_name=name,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={
                "stale_publication": True,
                "publication_usable": publication.usable,
                "expected_publication_generation": expected_generation,
                "current_publication_generation": publication.generation,
                "view_verified": publication.verified,
                "view_stale": publication.stale,
            },
        )

    @staticmethod
    def _is_published_state_query(command: Command | Any) -> bool:
        """Whether a query can use the immutable last-committed read model."""
        return (
            isinstance(command, QueryStateCommand)
            and str(command.query or "state").lower() == "state"
        )

    def _execute_query_without_wait(
        self,
        command: QueryStateCommand,
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Serialize mutable-object reads only when the command lock is available."""
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            publication = self._committed_view_publication()
            message = "Application state is changing. Retry this query shortly."
            return CommandResult.failure_result(
                command_name=CommandName.QUERY_STATE.value,
                message=message,
                state=publication.state,
                changed_state=ChangedState(),
                error_type=ErrorType.PRECONDITION,
                recoverable=True,
                error_message=message,
                diagnostics={
                    "application_busy": True,
                    "query": command.query,
                    "publication_generation": publication.generation,
                    "publication_revision": publication.revision,
                },
            )
        try:
            if self.shutdown_lifecycle.snapshot().closed:
                return self._closed_command_result(command)
            if expected_publication_generation is not None:
                rejection = self._expected_publication_rejection(
                    command,
                    expected_publication_generation,
                )
                if rejection is not None:
                    return rejection
            return self._execute_serialized(command)
        finally:
            self._command_lock.release()

    def request_shutdown_fence(self) -> None:
        """Atomically reject new mutations without waiting for command execution."""
        self.shutdown_lifecycle.request_fence()

    def release_shutdown_fence(self) -> bool:
        """Reopen admission and reconcile state hidden by the shutdown fence."""
        return self.shutdown_lifecycle.release_fence()

    def _shutdown_fence_rejection(self, command: Command | Any) -> CommandResult:
        """Return a structured rejection for commands denied at admission time."""
        try:
            name = command_name(command).value
        except Exception:
            name = _UNRECOGNIZED_COMMAND_NAME
        try:
            state = self.get_state()
        except Exception as exc:
            state = self._state_fallback(exc)
        message = "XBrainLab is closing. Wait for shutdown to finish or cancel closing."
        return CommandResult.failure_result(
            command_name=name,
            message=message,
            state=state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={"shutdown_fenced": True},
        )

    def _execute_serialized(self, command: Command | Any) -> CommandResult:
        """Execute one command while the shared service mutation lock is held."""
        try:
            name = command_name(command)
        except Exception as exc:
            return self._unsupported_command_result(self._state_fallback(exc), exc)
        try:
            before = self._state_before_command(command)
        except Exception as exc:
            if isinstance(command, QueryStateCommand):
                return self._query_state_read_failure_result(command, exc)
            if not self._is_recovery_command(command):
                return self._state_read_failure_result(name.value, exc)
            before = self._state_fallback(exc)
        before_publication = self._committed_view_publication()
        try:
            return self._execute_verified_command(command, name, before)
        except Exception as exc:
            return self._handler_failure_result(
                name,
                before,
                before_publication,
                exc,
                read_only=self._is_read_only_command(command, name),
            )

    def _state_before_command(self, command: Command | Any) -> ApplicationStateSnapshot:
        """Use committed state for queries; only mutations rebuild backend truth."""
        if isinstance(command, QueryStateCommand):
            publication = self._committed_view_publication()
            if not publication.usable:
                raise PreconditionError(
                    publication.unavailable_reason
                    or "Application state could not be verified. Retry shortly."
                )
            if not self._is_training_history_query(command):
                return publication.state
            boundary = self.state_snapshot.capture_training_read_boundary()
            if boundary.stable and boundary == publication.training_boundary:
                return publication.state
            raise self._training_read_changed_error(
                publication.training_boundary,
                boundary,
            )
        return self.get_state()

    def _execute_verified_command(
        self,
        command: Command | Any,
        name: CommandName,
        before: ApplicationStateSnapshot,
    ) -> CommandResult:
        """Run an allowed handler and verify the complete post-command state."""
        self._ensure_command_allowed(command, before)
        training_boundary = self._training_read_boundary(command, name)
        if training_boundary is not None and not training_boundary.stable:
            raise self._training_read_changed_error(training_boundary, None)
        read_only = self._is_read_only_command(command, name)
        if not read_only:
            self._view_coordinator.mark_stale(
                "Application state is changing while a command is running.",
            )
            self._mutation_in_progress = True
        try:
            try:
                handler_result = (
                    self.query_state_commands.handle_query_state(command, state=before)
                    if name is CommandName.QUERY_STATE
                    and isinstance(command, QueryStateCommand)
                    else self._execute_allowed(command, name)
                )
                message, diagnostics = self._normalize_handler_result(handler_result)
                diagnostics = self.legacy_raw_mutation_lifecycle.commit(
                    command=command,
                    diagnostics=diagnostics,
                )
            except Exception as exc:
                self.legacy_raw_mutation_lifecycle.fail_closed(
                    command=command,
                    error=exc,
                )
                raise
        finally:
            self._mutation_in_progress = False
        if training_boundary is not None:
            after_boundary = self.state_snapshot.capture_training_read_boundary()
            if after_boundary != training_boundary or not after_boundary.stable:
                raise self._training_read_changed_error(
                    training_boundary,
                    after_boundary,
                )
            diagnostics = {
                **diagnostics,
                "training_read_verified": True,
                "training_read_generation": after_boundary.token.generation,
                "training_read_trainer_identity": after_boundary.trainer_identity,
            }
        if name is CommandName.EVALUATE:
            publication = self._committed_view_publication()
            diagnostics = {
                **diagnostics,
                "evaluation_publication_generation": publication.generation,
            }
        if read_only:
            return CommandResult.success_result(
                command_name=name.value,
                message=message,
                state=before,
                changed_state=ChangedState(),
                diagnostics=diagnostics,
            )
        self._last_error = None
        after, refresh_error = self._state_after_command()
        if refresh_error is not None or not after.state_reliable:
            verification_error = refresh_error or RuntimeError(
                "; ".join(after.read_errors)
                or "updated application state is unreliable",
            )
            return self._post_state_verification_failure_result(
                name=name,
                state=after,
                diagnostics=diagnostics,
                error=verification_error,
            )
        return CommandResult.success_result(
            command_name=name.value,
            message=message,
            state=after,
            changed_state=self._changed_state(before, after),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _needs_training_read_guard(command: Command, name: CommandName) -> bool:
        if name is CommandName.EVALUATE:
            return True
        if name is CommandName.QUERY_STATE:
            return ApplicationService._is_training_history_query(command)
        return name is CommandName.VISUALIZE and isinstance(command, VisualizeCommand)

    @staticmethod
    def _is_training_history_query(command: Command | Any) -> bool:
        return isinstance(command, QueryStateCommand) and (
            str(command.query or "").lower() == "training_history"
        )

    def _training_read_boundary(
        self,
        command: Command,
        name: CommandName,
    ) -> TrainingReadBoundary | None:
        if not self._needs_training_read_guard(command, name):
            return None
        return self.state_snapshot.capture_training_read_boundary()

    @staticmethod
    def _training_read_changed_error(
        before: TrainingReadBoundary,
        after: TrainingReadBoundary | None,
    ) -> PreconditionError:
        return PreconditionError(
            "Training state changed while results were being read. Retry after "
            "the current training update finishes.",
            diagnostics={
                "training_state_changed": True,
                "retryable": True,
                "training_generation_before": before.token.generation,
                "training_generation_after": (
                    after.token.generation if after is not None else None
                ),
                "trainer_identity_changed": bool(
                    after is not None
                    and before.trainer_identity != after.trainer_identity
                ),
            },
        )

    def _handler_failure_result(
        self,
        name: CommandName,
        before: ApplicationStateSnapshot,
        before_publication: ApplicationViewPublication,
        exc: Exception,
        *,
        read_only: bool = False,
    ) -> CommandResult:
        """Map one handler failure and fail closed when post-state is uncertain."""
        app_error = map_exception(exc)
        if app_error.error_type is ErrorType.INTERNAL:
            logger.exception("%s command failed unexpectedly", name.value)
        public_message = str(app_error)
        failure_diagnostics = {
            **app_error.diagnostics,
            "exception_type": safe_exception_type_name(exc),
            "handler_error_type": app_error.error_type.value,
            "handler_error_message": public_message,
            "handler_error_recoverable": app_error.recoverable,
        }
        if read_only or name is CommandName.QUERY_STATE:
            return CommandResult.failure_result(
                command_name=name.value,
                message=public_message,
                state=before,
                changed_state=ChangedState(),
                error_type=app_error.error_type,
                recoverable=app_error.recoverable,
                error_message=public_message,
                diagnostics={
                    **failure_diagnostics,
                    "read_only_query": True,
                    "state_preserved": True,
                    "publication_generation": before_publication.generation,
                    "publication_revision": before_publication.revision,
                },
            )
        schedule = app_error.diagnostics.get("post_training_saliency_schedule")
        stale_saliency_control_flow = bool(
            name is CommandName.SALIENCY
            and isinstance(schedule, dict)
            and schedule.get("disposition") == "stale"
        )
        if (
            app_error.error_type is ErrorType.CONFIRMATION_REQUIRED
            or stale_saliency_control_flow
        ):
            try:
                after, unchanged = (
                    self._view_coordinator.restore_control_flow_if_unchanged(
                        before_publication,
                    )
                )
            except Exception as control_flow_refresh_error:
                return self._post_state_verification_failure_result(
                    name=name,
                    state=self._state_fallback(control_flow_refresh_error),
                    diagnostics=failure_diagnostics,
                    error=control_flow_refresh_error,
                )
            if unchanged:
                return CommandResult.failure_result(
                    command_name=name.value,
                    message=public_message,
                    state=after,
                    changed_state=ChangedState(),
                    error_type=app_error.error_type,
                    recoverable=app_error.recoverable,
                    error_message=public_message,
                    diagnostics={
                        **failure_diagnostics,
                        "control_flow_outcome": True,
                        "state_preserved": True,
                        "publication_generation": before_publication.generation,
                        "publication_revision": before_publication.revision,
                    },
                )
        self._last_error = ErrorSnapshot(
            error_type=app_error.error_type.value,
            message=public_message,
            recoverable=app_error.recoverable,
        )
        after, refresh_error = self._state_after_command()
        if refresh_error is not None:
            failure_diagnostics.update(
                {
                    "state_refresh_error": public_exception_message(refresh_error),
                    "state_refresh_exception_type": safe_exception_type_name(
                        refresh_error
                    ),
                },
            )
        if refresh_error is not None or not after.state_reliable:
            verification_error = refresh_error or RuntimeError(
                "; ".join(after.read_errors)
                or "updated application state is unreliable",
            )
            return self._post_state_verification_failure_result(
                name=name,
                state=after,
                diagnostics=failure_diagnostics,
                error=verification_error,
            )
        explicit_state_unknown = bool(app_error.diagnostics.get("state_unknown"))
        if explicit_state_unknown:
            read_errors = list(after.read_errors)
            if public_message not in read_errors:
                read_errors.append(public_message)
            after = replace(
                after,
                state_reliable=False,
                read_errors=read_errors,
            )
        changed_state = self._changed_state(before, after)
        if explicit_state_unknown:
            changed_state = replace(changed_state, state_unknown=True)
        return CommandResult.failure_result(
            command_name=name.value,
            message=public_message,
            state=after,
            changed_state=changed_state,
            error_type=app_error.error_type,
            recoverable=app_error.recoverable,
            error_message=public_message,
            diagnostics=failure_diagnostics,
        )

    @staticmethod
    def _is_recovery_command(command: Command | Any) -> bool:
        """Return whether a command may act from a conservative fallback state."""
        try:
            return command_name(command).value in RECOVERY_COMMAND_NAMES
        except Exception:
            return False

    def _state_after_command(
        self,
    ) -> tuple[ApplicationStateSnapshot, Exception | None]:
        try:
            return self.get_state(), None
        except Exception as exc:
            fallback = self._state_fallback(exc)
            return fallback, exc

    def _clear_last_error(self) -> None:
        """Clear application error state after verified command completion."""
        self._last_error = None

    def _post_state_verification_failure_result(
        self,
        *,
        name: CommandName,
        state: ApplicationStateSnapshot,
        diagnostics: dict[str, Any],
        error: Exception,
    ) -> CommandResult:
        message = (
            "The action finished, but XBrainLab could not verify the updated state. "
            "Do not retry automatically; refresh or reset the session."
        )
        self._last_error = ErrorSnapshot(
            error_type=ErrorType.INTERNAL.value,
            message=message,
            recoverable=False,
        )
        failure_state = replace(
            state,
            last_error=self._last_error,
            state_reliable=False,
        )
        return CommandResult.failure_result(
            command_name=name.value,
            message=message,
            state=failure_state,
            changed_state=ChangedState(error_changed=True, state_unknown=True),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            error_message=message,
            diagnostics={
                **diagnostics,
                "state_refresh_failed": True,
                "state_refresh_error": public_exception_message(error),
                "state_refresh_exception_type": safe_exception_type_name(error),
                "command_effect_may_have_applied": True,
            },
        )

    def _state_fallback(self, exc: Exception) -> ApplicationStateSnapshot:
        message = f"state snapshot unavailable: {public_exception_message(exc)}"
        last_state = self._view_coordinator.committed().state
        errors = [message]
        return replace(
            last_state,
            pipeline_stage="unavailable",
            training=replace(
                last_state.training,
                is_running=True,
                terminal_outcome=TrainingTerminalOutcome(
                    state=TrainingOutcomeState.UNKNOWN,
                    detail=message,
                ),
            ),
            active_training=replace(
                last_state.active_training,
                is_running=True,
            ),
            state_reliable=False,
            training_liveness_reliable=False,
            read_errors=errors,
        )

    def _state_read_failure_result(
        self,
        command_name_value: str,
        exc: Exception,
    ) -> CommandResult:
        app_error = map_exception(exc)
        message = f"Unable to verify application state: {app_error}"
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
            changed_state=ChangedState(error_changed=True, state_unknown=True),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            error_message=message,
            diagnostics={
                "exception_type": safe_exception_type_name(exc),
                "state_read_failed": True,
            },
        )

    def _query_state_read_failure_result(
        self,
        command: QueryStateCommand,
        exc: Exception,
    ) -> CommandResult:
        """Reject an object query without refreshing or mutating error truth."""
        publication = self._committed_view_publication()
        app_error = map_exception(exc)
        message = str(app_error) or (
            "Application state is changing. Retry this query shortly."
        )
        return CommandResult.failure_result(
            command_name=CommandName.QUERY_STATE.value,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={
                **app_error.diagnostics,
                "read_only_query": True,
                "query": command.query,
                "publication_generation": publication.generation,
                "publication_revision": publication.revision,
                "publication_usable": publication.usable,
                "exception_type": safe_exception_type_name(exc),
            },
        )

    def _execute_allowed(self, command: Command, name: CommandName) -> HandlerResult:
        handler = self._command_handlers.get(name)
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

    def _build_command_handlers(
        self,
    ) -> dict[CommandName, Callable[[Command], HandlerResult]]:
        """Bind the complete command registry while service contracts are visible."""
        handlers: dict[CommandName, Callable[[Command], HandlerResult]] = {
            CommandName.SCAN_SOURCE: self.interpretation.handle_scan_source,
            CommandName.REVIEW_INTERPRETATION: (
                self.interpretation.handle_review_interpretation
            ),
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
            CommandName.CONFIGURE_DATASET_SPLIT: (
                self.dataset_generation.handle_save_dataset_split
            ),
            CommandName.CLEAR_DATASETS: self.dataset_generation.handle_clear_datasets,
            CommandName.CONFIGURE_TRAINING: (
                self.training_commands.handle_configure_training
            ),
            CommandName.TRAIN: self._handle_train_with_automation,
            CommandName.DISCARD_TRAINING_PREPARATION: (
                self._handle_discard_training_preparation
            ),
            CommandName.STOP_TRAINING: self.training_commands.handle_stop_training,
            CommandName.CLEAR_TRAINING_HISTORY: (
                self.training_commands.handle_clear_training_history
            ),
            CommandName.EVALUATE: self.analysis.handle_evaluate,
            CommandName.VISUALIZE: self.analysis.handle_visualize,
            CommandName.SALIENCY: self.analysis.handle_saliency,
            CommandName.APPLY_MONTAGE: self.preprocess_commands.handle_apply_montage,
            CommandName.QUERY_STATE: self.query_state_commands.handle_query_state,
            CommandName.RESET_PREPROCESS: self.lifecycle.handle_reset_preprocess,
            CommandName.RESET_SESSION: self.lifecycle.handle_reset_session,
            CommandName.NEW_SESSION: self.lifecycle.handle_new_session,
        }
        missing = set(CommandName).difference(handlers)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise RuntimeError(f"Application command handlers missing: {names}")
        return handlers

    def load_data(self, paths: list[str]) -> CommandResult:
        """Execute a load-data command."""
        return self.execute(LoadDataCommand(paths=paths))

    def attach_labels(
        self,
        mapping: dict[str, str],
        *,
        selected_event_names: list[str] | set[str] | None = None,
    ) -> CommandResult:
        """Execute an attach-labels command."""
        return self.execute(
            AttachLabelsCommand(
                mapping=mapping,
                label_paths=list(dict.fromkeys(mapping.values())),
                selected_event_names=selected_event_names,
            )
        )

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
        resource_preflight_confirmed: bool = False,
        resource_preflight_token: str | None = None,
    ) -> CommandResult:
        """Scan, preview, and validate a data interpretation."""
        return self.execute(
            ReviewInterpretationCommand(
                source_path=source_path,
                source_hint=source_hint,
                label_sources=list(label_sources or []),
                choices=dict(choices or {}),
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
            ),
        )

    def preview_interpretation(
        self,
        scan_id: str | None = None,
        choices: dict[str, Any] | None = None,
        resource_preflight_confirmed: bool = False,
        resource_preflight_token: str | None = None,
    ) -> CommandResult:
        """Preview a candidate data interpretation."""
        return self.execute(
            PreviewInterpretationCommand(
                scan_id=scan_id,
                choices=dict(choices or {}),
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
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
        resource_preflight_confirmed: bool = False,
        resource_preflight_token: str | None = None,
    ) -> CommandResult:
        """Apply a validated data interpretation."""
        return self.execute(
            ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=confirmed,
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
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

    def configure_dataset_split(
        self,
        command: SaveDatasetSplitCommand,
    ) -> CommandResult:
        """Save one data splitting specification."""
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
        shutdown_fenced = self.shutdown_lifecycle.snapshot().fenced
        if shutdown_fenced and not isinstance(
            command,
            (QueryStateCommand, StopTrainingCommand),
        ):
            raise PreconditionError(
                "XBrainLab is closing. Wait for shutdown to finish or cancel closing."
            )
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
            message=public_exception_message(exc),
            recoverable=True,
        )
        after, refresh_error = self._state_after_command()
        diagnostics = {"exception_type": safe_exception_type_name(exc)}
        if refresh_error is not None:
            diagnostics.update(
                {
                    "state_refresh_error": public_exception_message(refresh_error),
                    "state_refresh_exception_type": safe_exception_type_name(
                        refresh_error
                    ),
                },
            )
        return CommandResult.failure_result(
            command_name=ErrorType.UNSUPPORTED_COMMAND.value,
            message=public_exception_message(exc),
            state=after,
            changed_state=self._changed_state(before, after),
            error_type=ErrorType.UNSUPPORTED_COMMAND,
            recoverable=True,
            error_message=public_exception_message(exc),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _is_read_only_command(command: Command, name: CommandName) -> bool:
        if isinstance(command, ScanSourceCommand) and command.catalog_only:
            # Subject discovery inspects only bounded directory metadata and does
            # not enter the Data Interpretation lifecycle. Preserve the current
            # publication identity so an open review cannot become stale merely
            # because another catalog was inspected.
            return True
        if isinstance(command, PreviewLabelImportCommand):
            # Preview materialization only populates an opaque, one-shot backend
            # cache. It does not change published application state, so the
            # reviewed generation remains valid for the matching commit.
            return True
        if name in {
            CommandName.QUERY_STATE,
            CommandName.EVALUATE,
            CommandName.VISUALIZE,
        }:
            return True
        return (
            name == CommandName.SALIENCY
            and isinstance(command, SaliencyCommand)
            and not command.method
            and not command.params
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
