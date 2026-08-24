"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from threading import Lock, RLock, Thread, current_thread
from time import monotonic
from typing import Any, cast

from XBrainLab.backend.services.dataset_state_service import (
    DatasetProductPort,
)
from XBrainLab.backend.services.preprocess_state_service import PreprocessProductPort
from XBrainLab.backend.services.training_state_service import TrainingProductPort
from XBrainLab.backend.services.visualization_state_service import (
    VisualizationProductPort,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    current_post_training_saliency_target,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
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
from .bids_montage_coordinator import BidsMontagePreparationCoordinator
from .bids_montage_preparation import MontagePreparationSnapshot
from .capabilities import (
    RECOVERY_COMMAND_NAMES,
    CapabilityPolicy,
    build_capability_policy,
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
    PreprocessOperation,
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
from .data_interpretation_apply_preparation import (
    ApplicationApplyBoundary,
    InterpretationApplyPlan,
    PreparedInterpretationApply,
)
from .data_interpretation_discovery_preparation import (
    ApplicationDiscoveryBoundary,
    InterpretationDiscoveryPlan,
    PreparedInterpretationDiscovery,
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
    EvaluationModelSummary,
    EvaluationModelSummaryPreparation,
    EvaluationRenderPublication,
    EvaluationRenderPublisher,
    EvaluationRenderRequest,
    build_evaluation_cross_fold_choices,
)
from .evaluation_work import EvaluationWorkController
from .lifecycle_service import LifecycleCommandService
from .montage_preparation_lifecycle import MontagePreparationWork
from .owned_work import (
    OwnedOperationCancelledError,
    OwnedOperationClaimError,
    OwnedOperationSnapshot,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    current_owned_operation_id,
    owned_operation_diagnostics,
    owned_work_checkpoint,
)
from .pipeline_stage import pipeline_stage_readiness_summary
from .pipeline_transaction import PipelineStateTransaction
from .post_training_saliency import PostTrainingSaliencyAutomation
from .preprocess_preparation import (
    ApplicationPreprocessBoundary,
    PreprocessMutationPlan,
)
from .preprocess_render import (
    PreprocessRenderPublication,
    PreprocessRenderPublisher,
    PreprocessRenderRequest,
)
from .preprocess_service import PreprocessCommandService
from .query_state_service import QueryStateCommandService
from .resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
    TrainingResourcePreviewContext,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from .results import ChangedState, CommandResult, ErrorType
from .saliency_coverage import SaliencyCoverageProjector
from .saliency_render import (
    SaliencyCrossFoldIdentity,
    SaliencyRenderPublication,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from .saliency_render_work import SaliencyRenderWorkController
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
from .training_resource_preview_coordinator import (
    TrainingResourcePreviewCoordinator,
    TrainingResourcePreviewTicket,
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
    model_signal_context_snapshot as build_model_signal_context_snapshot,
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
_CONTEXT_READ_LOCK_WAIT_SECONDS = 0.1


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

    def begin_interpretation_discovery(
        self,
        command: (
            ScanSourceCommand
            | ReviewInterpretationCommand
            | PreviewInterpretationCommand
            | ValidateInterpretationCommand
        ),
        *,
        application_boundary: ApplicationDiscoveryBoundary,
    ) -> InterpretationDiscoveryPlan:
        return self._service().begin_interpretation_discovery(
            command,
            application_boundary=application_boundary,
        )

    def prepare_interpretation_discovery(
        self,
        plan: InterpretationDiscoveryPlan,
    ) -> PreparedInterpretationDiscovery:
        return self._service().prepare_interpretation_discovery(plan)

    def commit_prepared_interpretation_discovery(
        self,
        prepared: PreparedInterpretationDiscovery,
    ) -> HandlerResult:
        return self._service().commit_prepared_interpretation_discovery(prepared)

    def discovery_plan_is_current(
        self,
        plan: InterpretationDiscoveryPlan,
    ) -> bool:
        return self._service().discovery_plan_is_current(plan)

    def handle_preview_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_preview_interpretation(command)

    def handle_validate_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_validate_interpretation(command)

    def handle_apply_interpretation(self, command: Command) -> HandlerResult:
        return self._service().handle_apply_interpretation(command)

    def begin_apply_interpretation(
        self,
        command: ApplyInterpretationCommand,
        *,
        application_boundary: ApplicationApplyBoundary,
    ) -> InterpretationApplyPlan:
        return self._service().begin_apply_interpretation(
            command,
            application_boundary=application_boundary,
        )

    def prepare_apply_interpretation(
        self,
        plan: InterpretationApplyPlan,
    ) -> PreparedInterpretationApply:
        return self._service().prepare_apply_interpretation(plan)

    def verify_prepared_apply_content(
        self,
        prepared: PreparedInterpretationApply,
    ) -> PreparedInterpretationApply:
        return self._service().verify_prepared_apply_content(prepared)

    def commit_prepared_apply_interpretation(
        self,
        prepared: PreparedInterpretationApply,
    ) -> HandlerResult:
        return self._service().commit_prepared_apply_interpretation(prepared)

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
        self._resource_refinement_provider: Callable[
            [ConfigureTrainingCommand], tuple[Any, ...]
        ] = lambda _command: ()
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .training_service import TrainingCommandService  # noqa: PLC0415

            self._service_instance = TrainingCommandService(
                training=self.training,
                training_runtime=self.training_runtime,
                get_state=self._get_state,
                recommendation=self._recommendation,
                resource_refinement_provider=self._resource_refinement_provider,
            )
        return self._service_instance

    def set_resource_refinement_provider(
        self,
        provider: Callable[[ConfigureTrainingCommand], tuple[Any, ...]],
    ) -> None:
        """Bind application-owned preview provenance before lazy construction."""
        if self._service_instance is not None:
            raise RuntimeError(
                "Training refinement provider must be bound before first use."
            )
        self._resource_refinement_provider = provider

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

    def get_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
        context: TrainingResourcePreviewContext,
    ) -> TrainingResourcePreviewResult:
        return self._service().get_resource_preview(request, context)

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

    def prepare_evaluate(
        self,
        command: Command,
    ) -> tuple[
        tuple[str, dict[str, Any]],
        EvaluationModelSummaryPreparation | None,
    ]:
        return self._service().prepare_evaluate(command)

    def build_prepared_model_summary(
        self,
        preparation: EvaluationModelSummaryPreparation,
    ) -> EvaluationModelSummary:
        return self._service().build_prepared_model_summary(preparation)

    def complete_prepared_evaluate(
        self,
        result: tuple[str, dict[str, Any]],
        command: EvaluateCommand,
        model_summary: EvaluationModelSummary,
    ) -> tuple[str, dict[str, Any]]:
        return self._service().complete_prepared_evaluate(
            result,
            command,
            model_summary,
        )

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
        self.owned_work = OwnedWorkRegistry()
        self._training_operation_lock = Lock()
        self._training_operation_threads: dict[str, Thread] = {}
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
            pipeline_transaction=self.pipeline_transaction,
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
        self.training_resource_preview = TrainingResourcePreviewCoordinator(
            estimate=self.training_commands.get_resource_preview,
            generation_is_current=(self._training_preview_generation_is_current),
            registry=self.owned_work,
        )
        self.training_commands.set_resource_refinement_provider(
            self.training_resource_preview.refinements_for_configuration
        )
        self.saliency_coverage_projector = SaliencyCoverageProjector()
        self.bids_montage_preparation = BidsMontagePreparationCoordinator(
            commit_publication=self._commit_bids_montage_publication,
        )
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
            montage_snapshot_provider=self.bids_montage_preparation.snapshot,
            effective_montage_provider=(
                self.bids_montage_preparation.effective_montage
            ),
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
            effective_montage_provider=(
                self.bids_montage_preparation.effective_montage
            ),
        )
        self.saliency_render_work = SaliencyRenderWorkController(
            registry=self.owned_work,
            publish=self.saliency_render.publish,
        )
        self.evaluation_render = EvaluationRenderPublisher(
            training_runtime=self.training_runtime,
            get_publication=self._committed_view_publication,
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
        )
        self.evaluation_work = EvaluationWorkController(
            registry=self.owned_work,
            render=self.evaluation_render.publish,
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

        self.training_resource_preview.begin_close()
        if not self.training_resource_preview.close(timeout=2.0):
            logger.warning(
                "Training resource preview did not quiesce within the close timeout."
            )
            return
        if not begin_application_service_close(
            self.study,
            self,
            self.shutdown_lifecycle.begin_close,
        ):
            return
        self.shutdown_lifecycle.cancel_close_automation()
        if not self.bids_montage_preparation.close(timeout=2.0):
            logger.warning(
                "BIDS montage preparation did not quiesce within the close timeout."
            )
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

    def _handle_train_with_saved_split(self, command: Command) -> HandlerResult:
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
            had_montage_candidate = self.bids_montage_preparation.has_pending_promotion
            if had_montage_candidate:
                self.bids_montage_preparation.retry_promotion(
                    refresh_candidate=self._refresh_training_publication_strict,
                )
            if not self.bids_montage_preparation.has_pending_promotion:
                publication = self._committed_view_publication()
                if not publication.usable:
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

    def begin_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> OwnedOperationSnapshot:
        """Reserve unified ownership for one native saliency render."""
        self._ensure_open()
        return self.saliency_render_work.begin(request)

    def prepare_saliency_render(
        self,
        operation_id: str,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Prepare detached data while retaining ownership through canvas commit."""
        self._ensure_open()
        return self.saliency_render_work.prepare(operation_id, request)

    def prepare_saliency_render_variants(
        self,
        operation_id: str,
        request: SaliencyRenderRequest,
        *,
        include_normalized: bool,
    ) -> tuple[SaliencyRenderPublication, SaliencyRenderPublication | None]:
        """Prepare raw/normalized render DTOs in the same owned operation."""
        self._ensure_open()
        return self.saliency_render_work.prepare_variants(
            operation_id,
            request,
            include_normalized=include_normalized,
        )

    def finish_saliency_render(
        self,
        operation_id: str,
        phase: str,
        *,
        message: str = "",
    ) -> None:
        """Finish the exact native render operation."""
        self.saliency_render_work.finish(operation_id, phase, message=message)

    def enter_saliency_render_commit(self, operation_id: str) -> bool:
        """Atomically admit the exact native canvas publication."""
        return self.saliency_render_work.enter_commit(operation_id)

    def get_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Return detached Evaluation data guarded by publication/training identity."""
        self._ensure_open()
        return self.evaluation_render.publish(request)

    def begin_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> OwnedOperationSnapshot:
        """Reserve a request-bound Evaluation operation without the command lock."""
        self._ensure_open()
        return self.evaluation_work.begin(request)

    def run_evaluation_render(
        self,
        operation_id: str,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Run an Evaluation publication under unified backend ownership."""
        self._ensure_open()
        return self.evaluation_work.run(operation_id, request)

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
        # Background publication commits hold this lock only while promoting a
        # verified snapshot. Absorb that brief hand-off so a user click does not
        # spuriously report the epoch dialog as busy immediately after a command.
        acquired = self._command_lock.acquire(
            timeout=_CONTEXT_READ_LOCK_WAIT_SECONDS,
        )
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

    def get_training_model_signal_context(self) -> dict[str, Any] | None:
        """Return detached epoch metadata used to admit model selections."""
        acquired = self._command_lock.acquire(
            timeout=_CONTEXT_READ_LOCK_WAIT_SECONDS,
        )
        if not acquired:
            return None
        try:
            self._ensure_open()
            if self._mutation_in_progress:
                return None
            return build_model_signal_context_snapshot(self.training)
        except (AttributeError, TypeError, ValueError):
            logger.error("Failed to read model signal context.", exc_info=True)
            return None
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

    def get_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewResult:
        """Return a generation-bound advisory estimate for unsaved draft settings."""
        return self.begin_training_resource_preview(request).result()

    def begin_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewTicket:
        """Submit a draft estimate and return its backend-owned completion ticket."""
        if not isinstance(request, TrainingResourcePreviewRequest):
            raise TypeError("request must be a TrainingResourcePreviewRequest")
        with self._command_lock, self._command_admission_lock:
            if (
                self.shutdown_lifecycle.is_closing
                or self.shutdown_lifecycle.is_closed
                or self.shutdown_lifecycle.is_shutdown_fenced
            ):
                raise PreconditionError(
                    "Training resource preview is unavailable while XBrainLab "
                    "is closing."
                )
            if self._mutation_in_progress:
                raise PreconditionError("Training context is changing. Wait and retry.")
            publication = self._committed_view_publication()
            if publication.generation != request.publication_generation:
                raise PreconditionError(
                    "Training context changed. Review the settings again."
                )
            if not publication.usable:
                raise PreconditionError(
                    publication.public_unavailable_reason
                    or "Training resource preview is unavailable."
                )
            epoch = publication.state.epoch
            n_channels = epoch.n_channels
            n_times = epoch.n_times
            epoch_count = epoch.epoch_count
            sampling_frequency = epoch.sfreq
            if any(
                value is None
                for value in (
                    n_channels,
                    n_times,
                    epoch_count,
                    sampling_frequency,
                )
            ):
                raise PreconditionError(
                    "Training resource preview requires prepared EEG epochs."
                )
            event_ids = epoch.event_ids if isinstance(epoch.event_ids, dict) else {}
            context = TrainingResourcePreviewContext(
                input_shape=(
                    int(cast(int, n_channels)),
                    int(cast(int, n_times)),
                ),
                sample_count=int(cast(int, epoch_count)),
                class_count=max(len(event_ids), len(epoch.event_names), 1),
                sampling_frequency=float(cast(float, sampling_frequency)),
            )
            return self.training_resource_preview.submit(request, context)

    def training_resource_preview_background_work_snapshot(
        self,
    ) -> dict[str, int | bool]:
        """Expose exact backend preview ownership without taking the command lock."""
        return self.training_resource_preview.background_work_snapshot()

    def begin_training_resource_preview_shutdown(self) -> None:
        """Fence new preview work and cancel work that has not started."""
        self.training_resource_preview.begin_close()

    def cancel_training_resource_preview_shutdown(self) -> bool:
        """Reopen preview admission after a cancelled desktop close attempt."""
        return self.training_resource_preview.cancel_close()

    def _training_preview_generation_is_current(self, generation: int) -> bool:
        """Revalidate application identity after native estimate completion."""
        with self._command_lock:
            admission = self.shutdown_lifecycle.snapshot()
            publication = self._committed_view_publication()
            return bool(
                not admission.closing
                and not admission.closed
                and not admission.fenced
                and publication.generation == generation
                and (publication.usable or self._mutation_in_progress)
            )

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

        if not self.owned_work.wait_for_idle(
            timeout=remaining(),
            excluding_operation_id=current_owned_operation_id(),
        ):
            return False

        if not self._wait_for_owned_operation_monitors(timeout=remaining()):
            return False

        if not self.bids_montage_preparation.wait_for_idle(timeout=remaining()):
            return False

        if not self.training_resource_preview.wait_for_idle(timeout=remaining()):
            return False

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
        shutdown = self.shutdown_lifecycle.snapshot()
        if shutdown.fenced or shutdown.closing or shutdown.closed:
            return terminal_reconciled or (
                self.publication_lifecycle.publish_training_terminal_state()
            )
        if not self.training_runtime.wait_for_saliency_delivery(timeout=remaining()):
            return False
        if not self.training_publications.wait_for_saliency_delivery(
            timeout=remaining()
        ):
            return False
        return terminal_reconciled or (
            self.publication_lifecycle.publish_training_terminal_state()
        )

    def _wait_for_owned_operation_monitors(self, *, timeout: float | None) -> bool:
        """Join terminal monitor threads before reporting application idleness."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        caller = current_thread()
        while True:
            with self._training_operation_lock:
                monitors = tuple(self._training_operation_threads.items())
            if not monitors:
                return True
            for operation_id, monitor in monitors:
                if monitor is caller:
                    return False
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                monitor.join(timeout=remaining)
                if monitor.is_alive():
                    return False
                with self._training_operation_lock:
                    if self._training_operation_threads.get(operation_id) is monitor:
                        self._training_operation_threads.pop(operation_id, None)

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

    def query_published_data_summary(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Return the detached dataset summary without waiting on mutable state."""
        command = QueryStateCommand(query="data_summary")
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed
        publication = self._committed_view_publication()
        if expected_publication_generation is not None:
            rejection = self._expected_publication_rejection_for_publication(
                command,
                expected_publication_generation,
                publication,
            )
            if rejection is not None:
                return rejection
        if not publication.usable:
            message = publication.unavailable_reason or (
                "Dataset summary is temporarily unavailable. Retry shortly."
            )
            return CommandResult.failure_result(
                command_name=CommandName.QUERY_STATE.value,
                message=message,
                state=publication.state,
                changed_state=ChangedState(state_unknown=True),
                error_type=ErrorType.PRECONDITION,
                recoverable=True,
                error_message=message,
                diagnostics={
                    "query": command.query,
                    "publication_generation": publication.generation,
                    "publication_revision": publication.revision,
                    "view_verified": publication.verified,
                    "view_stale": publication.stale,
                },
            )
        return CommandResult.success_result(
            command_name=CommandName.QUERY_STATE.value,
            message="Dataset summary ready.",
            state=publication.state,
            changed_state=ChangedState(),
            diagnostics=self.state_snapshot.data_summary_from_published_state(
                publication.state,
            ),
        )

    def execute(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None = None,
        reviewed_preprocess_boundary: ApplicationPreprocessBoundary | None = None,
        operation_id: str | None = None,
    ) -> CommandResult:
        """Execute one command inside the typed notification boundary."""
        if operation_id is not None:
            return self._execute_owned_operation(
                command,
                operation_id=operation_id,
                expected_publication_generation=expected_publication_generation,
                reviewed_preprocess_boundary=reviewed_preprocess_boundary,
            )
        return self._execute_command(
            command,
            expected_publication_generation=expected_publication_generation,
            reviewed_preprocess_boundary=reviewed_preprocess_boundary,
        )

    def _execute_owned_operation(
        self,
        command: Command | Any,
        *,
        operation_id: str,
        expected_publication_generation: int | None,
        reviewed_preprocess_boundary: ApplicationPreprocessBoundary | None,
    ) -> CommandResult:
        """Bind one scheduled operation to command execution and its receipt."""
        try:
            self.owned_work.claim_start(
                operation_id,
                kind=self._owned_work_kind(command),
                command_identity=self._owned_work_command_identity(command),
            )
        except OwnedOperationClaimError as exc:
            return self._owned_operation_claim_rejected_result(command, exc)
        with self.owned_work.bind(operation_id):
            try:
                owned_work_checkpoint("Waiting for product command admission")
                result = self._execute_command(
                    command,
                    expected_publication_generation=(expected_publication_generation),
                    reviewed_preprocess_boundary=reviewed_preprocess_boundary,
                )
            except OwnedOperationCancelledError:
                snapshot = self.owned_work.finish_cancelled(operation_id)
                return self._owned_operation_cancelled_result(command, snapshot)
            except BaseException as exc:
                self.owned_work.fail(
                    operation_id,
                    message=public_exception_message(exc),
                )
                raise

            if result.error_type is ErrorType.CANCELLED:
                snapshot = self.owned_work.finish_cancelled(operation_id)
            elif (
                result.ok
                and isinstance(command, TrainCommand)
                and command.interactive
                and result.diagnostics.get("training_trainer_identity")
            ):
                snapshot = self._continue_interactive_training_operation(
                    operation_id,
                    command,
                    result,
                )
            elif (
                result.ok
                and isinstance(command, SaliencyCommand)
                and result.diagnostics.get("action") == "schedule"
            ):
                snapshot = self._continue_scheduled_saliency_operation(
                    operation_id,
                    result,
                )
            elif result.ok:
                snapshot = self.owned_work.complete(operation_id)
                if snapshot.phase is OwnedWorkPhase.CANCELLED:
                    return self._owned_operation_cancelled_result(command, snapshot)
            else:
                snapshot = self.owned_work.fail(
                    operation_id,
                    message=result.message,
                )
            return replace(
                result,
                diagnostics={
                    **result.diagnostics,
                    **owned_operation_diagnostics(snapshot),
                },
            )

    def _execute_command(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None = None,
        reviewed_preprocess_boundary: ApplicationPreprocessBoundary | None = None,
    ) -> CommandResult:
        """Execute one command after any async operation ownership is bound."""
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed
        if isinstance(command, StopTrainingCommand):
            return self._execute_stop_training_control(command)
        if isinstance(command, QueryStateCommand):
            result, completion_release = self._execute_at_command_boundary(
                command,
                expected_publication_generation=expected_publication_generation,
                reviewed_preprocess_boundary=reviewed_preprocess_boundary,
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
        explicit_saliency_target = self._explicit_saliency_target(command)
        saliency_target_boundary = (
            post_training_saliency_target(explicit_saliency_target)
            if explicit_saliency_target is not None
            else nullcontext()
        )
        try:
            with (
                self.training_publications.capture_saliency_notifications(),
                visualization_notifications,
                manager_notifications,
                saliency_target_boundary,
            ):
                if isinstance(command, SaliencyCommand):
                    visualization_batch_generation = (
                        self.publication_lifecycle.visualization_batch_generation()
                    )
                result, completion_release = self._execute_at_command_boundary(
                    command,
                    expected_publication_generation=expected_publication_generation,
                    reviewed_preprocess_boundary=reviewed_preprocess_boundary,
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

    def begin_owned_operation(
        self,
        command: Command | Any,
    ) -> OwnedOperationSnapshot:
        """Allocate lock-independent identity before scheduling product work."""
        return self.owned_work.begin(
            self._owned_work_kind(command),
            cancellable=self._owned_work_cancellable(command),
            command_identity=self._owned_work_command_identity(command),
        )

    def cancel_owned_operation(self, operation_id: str) -> bool:
        """Request cooperative cancellation without acquiring the command lock."""
        cancelled = self.owned_work.cancel(operation_id)
        if cancelled:
            snapshot = self.owned_work.snapshot(operation_id)
            if snapshot.kind is OwnedWorkKind.TRAINING:
                try:
                    self.training_runtime.stop_training(wait_timeout=0.0)
                except Exception:
                    logger.warning(
                        "Could not forward owned training cancellation.",
                        exc_info=True,
                    )
            elif snapshot.kind is OwnedWorkKind.SALIENCY:
                try:
                    self.training_runtime.cancel_saliency_job()
                except Exception:
                    logger.warning(
                        "Could not forward owned saliency cancellation.",
                        exc_info=True,
                    )
        return cancelled

    def get_owned_operation(self, operation_id: str) -> OwnedOperationSnapshot:
        """Return immutable operation truth without acquiring the command lock."""
        return self.owned_work.snapshot(operation_id)

    def get_active_owned_operation(
        self,
        kind: OwnedWorkKind,
    ) -> OwnedOperationSnapshot | None:
        """Return the oldest active operation of one product work kind."""
        return self.owned_work.first_active(kind)

    def fail_owned_operation(
        self,
        operation_id: str,
        *,
        message: str,
    ) -> OwnedOperationSnapshot:
        """Terminate work that could not be scheduled by its UI owner."""
        return self.owned_work.fail(operation_id, message=message)

    def cancel_all_owned_operations(self) -> tuple[str, ...]:
        """Cancel every cooperative operation without taking the command lock."""
        return self.owned_work.cancel_all()

    def _execute_stop_training_control(
        self,
        command: StopTrainingCommand,
    ) -> CommandResult:
        """Request training cancellation without queueing behind product work."""
        # Stop is a lock-independent control acknowledgement.  Its result must
        # not rebuild mutable product state or clear another command's error
        # while that command owns the shared lock.  Terminal training truth is
        # published by the normal lifecycle observer after the worker reacts.
        before = self._committed_view_publication().state
        try:
            # The emergency control path must remain cold-start safe: resolving
            # the lazy TrainingCommandService imports torch and can take seconds
            # before a stop intent reaches the active worker.
            stopped = self.training_runtime.stop_training(
                wait_timeout=command.wait_timeout,
            )
            outcome = self.training_runtime.terminal_outcome()
            message = "Training stopped." if stopped else "Training stop requested."
            diagnostics = {
                "stopped": bool(stopped),
                "wait_timeout": command.wait_timeout,
                "terminal_outcome": outcome.state.value,
                "training_run": (
                    outcome.run.to_dict() if outcome.run is not None else None
                ),
            }
        except Exception as exc:
            app_error = map_exception(exc)
            return CommandResult.failure_result(
                command_name=CommandName.STOP_TRAINING.value,
                message=str(app_error),
                state=before,
                changed_state=ChangedState(),
                error_type=app_error.error_type,
                recoverable=app_error.recoverable,
                error_message=str(app_error),
                diagnostics={
                    **app_error.diagnostics,
                    "control_path": "lock_independent",
                    "exception_type": safe_exception_type_name(exc),
                    "state_preserved": True,
                },
            )

        return CommandResult.success_result(
            command_name=CommandName.STOP_TRAINING.value,
            message=message,
            state=before,
            changed_state=ChangedState(),
            diagnostics={
                **diagnostics,
                "control_path": "lock_independent",
                "state_publication_deferred": True,
            },
        )

    def _explicit_saliency_target(
        self,
        command: Command | Any,
    ) -> PostTrainingSaliencyTarget | None:
        """Bind an explicit compute command to the exact completed run set."""
        if (
            not isinstance(command, SaliencyCommand)
            or not (command.method or command.params)
            or current_post_training_saliency_target() is not None
        ):
            return None
        publication = self._committed_view_publication()
        if not publication.usable:
            return None
        saliency_status = self.training_runtime.saliency_status()
        if saliency_status.phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }:
            # Reconfiguration while an older job is active owns that job's
            # cancellation boundary.  Do not silently replace it with a new
            # scheduled generation; the existing manager path performs the
            # cancellation and preserves terminal-publication ordering.
            return None
        outcome = self.training_runtime.terminal_outcome()
        if outcome.state is not TrainingOutcomeState.COMPLETED or outcome.run is None:
            return None
        try:
            current_state = self.get_state()
        except Exception:
            current_state = publication.state
        finished_runs = current_state.evaluation.finished_runs
        if finished_runs <= 0:
            return None
        selection = command.target
        selected_members = (
            self._saliency_target_members(selection)
            if isinstance(
                selection,
                (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
            )
            else None
        )
        return PostTrainingSaliencyTarget(
            run=outcome.run,
            finished_runs_before=0,
            finished_runs_after=finished_runs,
            append=False,
            explicit=True,
            selected_members=selected_members,
        )

    @staticmethod
    def _saliency_target_members(
        target: SaliencyRunIdentity | SaliencyCrossFoldIdentity,
    ) -> tuple[tuple[int, int], ...]:
        runs = (
            target.members
            if isinstance(target, SaliencyCrossFoldIdentity)
            else (target,)
        )
        return tuple((run.plan.plan_index, run.run_index) for run in runs)

    def _require_saliency_target_admitted(
        self,
        target: object,
        state: ApplicationStateSnapshot,
    ) -> None:
        """Validate one UI-selected run or Fold Set against current backend truth."""
        if not isinstance(target, (SaliencyRunIdentity, SaliencyCrossFoldIdentity)):
            raise TypeError(
                "SaliencyCommand.target must be a saliency run or Fold Set identity."
            )
        status = self.training_runtime.saliency_status()
        if status.phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }:
            raise PreconditionError(
                "Saliency computation is already running. Wait for it to finish "
                "or cancel it before starting another selection.",
                diagnostics={
                    "saliency_compute_active": True,
                    "retryable": True,
                },
            )
        holders = tuple(self.training_runtime.training_plan_holders())
        members = self._saliency_target_members(target)
        if isinstance(target, SaliencyRunIdentity):
            plan_index, run_index = members[0]
            admitted_runs = {
                (coverage.plan_index, coverage.run_index)
                for coverage in state.visualization.saliency_coverage
            }
            if (plan_index, run_index) in admitted_runs and plan_index < len(holders):
                records = tuple(holders[plan_index].get_plans())
                if run_index < len(records) and records[run_index].is_finished():
                    return
        else:
            admitted_members = {
                tuple(
                    (member.plan.plan_index, member.run_index)
                    for member in choice.identity.members
                )
                for choice in build_evaluation_cross_fold_choices(holders)
            }
            if members in admitted_members:
                return
        raise PreconditionError(
            "Visualization results or the selected Fold changed. "
            "Refresh Visualization and review Saliency Settings again.",
            diagnostics={
                "stale_saliency_target": True,
                "retryable": True,
            },
        )

    def _continue_scheduled_saliency_operation(
        self,
        operation_id: str,
        result: CommandResult,
    ) -> OwnedOperationSnapshot:
        """Keep explicit saliency owned until generation-bound publication ends."""
        schedule = result.diagnostics.get("post_training_saliency_schedule")
        status = schedule.get("status") if isinstance(schedule, dict) else None
        generation = status.get("generation") if isinstance(status, dict) else None
        self.owned_work.update(
            operation_id,
            stage="Computing saliency",
            message=f"Saliency generation {generation}",
        )
        thread = Thread(
            target=self._monitor_owned_saliency,
            args=(operation_id, generation),
            name=f"xbrainlab-owned-saliency-{operation_id[:8]}",
            daemon=True,
        )
        with self._training_operation_lock:
            self._training_operation_threads[operation_id] = thread
        try:
            thread.start()
        except BaseException as exc:
            with self._training_operation_lock:
                self._training_operation_threads.pop(operation_id, None)
            return self.owned_work.fail(
                operation_id,
                message=public_exception_message(exc),
            )
        return self.owned_work.snapshot(operation_id)

    def _monitor_owned_saliency(
        self,
        operation_id: str,
        generation: object,
    ) -> None:
        """Track explicit saliency progress and terminal status without Qt."""
        terminal_phase = OwnedWorkPhase.FAILED
        terminal_message = "Saliency computation failed."
        try:
            if (
                isinstance(generation, bool)
                or not isinstance(generation, int)
                or generation < 0
            ):
                terminal_message = "Saliency generation identity could not be verified."
            else:
                generation_matches = True
                while not self.training_runtime.wait_for_saliency_job(timeout=0.25):
                    status = self.training_runtime.saliency_status()
                    if status.generation != generation:
                        generation_matches = False
                        break
                    phase = status.phase
                    self.owned_work.update(
                        operation_id,
                        stage=(
                            "Cancelling saliency"
                            if self.owned_work.snapshot(operation_id).cancel_requested
                            else "Computing saliency"
                            if phase is PostTrainingSaliencyPhase.RUNNING
                            else "Preparing saliency"
                        ),
                        message=f"Saliency generation {generation}",
                    )
                if generation_matches:
                    while True:
                        shutdown = self.shutdown_lifecycle.snapshot()
                        if shutdown.fenced or shutdown.closing or shutdown.closed:
                            break
                        if self.training_runtime.wait_for_saliency_delivery(
                            timeout=0.25
                        ):
                            break
                    status = self.training_runtime.saliency_status()
                    generation_matches = status.generation == generation
                if not generation_matches:
                    terminal_message = (
                        "Saliency generation identity could not be verified."
                    )
                elif status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                    terminal_phase = OwnedWorkPhase.COMPLETED
                    terminal_message = ""
                elif status.phase is PostTrainingSaliencyPhase.CANCELLED:
                    terminal_phase = OwnedWorkPhase.CANCELLED
                    terminal_message = ""
                else:
                    terminal_message = status.message or "Saliency computation failed."
        except BaseException as exc:
            terminal_phase = OwnedWorkPhase.FAILED
            terminal_message = public_exception_message(exc)
        self._publish_monitored_owned_terminal(
            operation_id,
            phase=terminal_phase,
            message=terminal_message,
        )

    def _continue_interactive_training_operation(
        self,
        operation_id: str,
        command: TrainCommand,
        result: CommandResult,
    ) -> OwnedOperationSnapshot:
        """Keep interactive Train owned until its exact terminal run publishes."""
        trainer_identity = str(result.diagnostics["training_trainer_identity"])
        handoff_generation = result.diagnostics.get("training_handoff_generation")
        self.owned_work.update(
            operation_id,
            stage="Training model",
            message=f"Training handoff {handoff_generation}",
        )
        thread = Thread(
            target=self._monitor_owned_training,
            args=(operation_id, trainer_identity, command.append),
            name=f"xbrainlab-owned-training-{operation_id[:8]}",
            daemon=True,
        )
        with self._training_operation_lock:
            self._training_operation_threads[operation_id] = thread
        try:
            thread.start()
        except BaseException as exc:
            with self._training_operation_lock:
                self._training_operation_threads.pop(operation_id, None)
            return self.owned_work.fail(
                operation_id,
                message=public_exception_message(exc),
            )
        return self.owned_work.snapshot(operation_id)

    def _monitor_owned_training(
        self,
        operation_id: str,
        trainer_identity: str,
        append: bool,
    ) -> None:
        """Publish terminal owned-work truth for one admitted trainer identity."""
        terminal_phase = OwnedWorkPhase.FAILED
        terminal_message = "Training did not complete successfully."
        try:
            self.training_runtime.wait_for_training_completion(
                expected_trainer_identity=trainer_identity,
                timeout=None,
            )
            outcome = self.training_runtime.terminal_outcome()
            run = outcome.run
            if run is None or run.trainer_id != trainer_identity:
                terminal_message = "Training terminal identity could not be verified."
            elif outcome.state is TrainingOutcomeState.COMPLETED:
                terminal_phase = OwnedWorkPhase.COMPLETED
                terminal_message = ""
            elif outcome.state is TrainingOutcomeState.CANCELLED:
                terminal_phase = OwnedWorkPhase.CANCELLED
                terminal_message = ""
            else:
                terminal_message = (
                    outcome.detail or "Training did not complete successfully."
                )
        except BaseException as exc:
            terminal_phase = OwnedWorkPhase.FAILED
            terminal_message = public_exception_message(exc)
        finally:
            del append
        self._publish_monitored_owned_terminal(
            operation_id,
            phase=terminal_phase,
            message=terminal_message,
        )

    def _publish_monitored_owned_terminal(
        self,
        operation_id: str,
        *,
        phase: OwnedWorkPhase,
        message: str,
    ) -> OwnedOperationSnapshot:
        """Publish terminal truth only after its physical monitor is unowned."""
        if phase is OwnedWorkPhase.COMPLETED:
            return self.owned_work.complete(operation_id)
        if phase is OwnedWorkPhase.CANCELLED:
            return self.owned_work.finish_cancelled(operation_id)
        return self.owned_work.fail(operation_id, message=message)

    def _owned_operation_cancelled_result(
        self,
        command: Command | Any,
        snapshot: OwnedOperationSnapshot,
    ) -> CommandResult:
        name = self._owned_work_command_identity(command)
        publication = self._committed_view_publication()
        return CommandResult.failure_result(
            command_name=name,
            message="The operation was cancelled.",
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.CANCELLED,
            recoverable=True,
            diagnostics={
                **owned_operation_diagnostics(snapshot),
                "operation_cancelled": True,
                "state_preserved": True,
            },
        )

    def _owned_operation_claim_rejected_result(
        self,
        command: Command | Any,
        error: OwnedOperationClaimError,
    ) -> CommandResult:
        publication = self._committed_view_publication()
        diagnostics: dict[str, object] = {
            "operation_id": error.operation_id,
            "operation_claim_rejected": True,
            "operation_claim_reason": error.reason,
            "state_preserved": True,
        }
        if error.snapshot is not None:
            diagnostics.update(owned_operation_diagnostics(error.snapshot))
        message = "The scheduled operation could not be admitted."
        return CommandResult.failure_result(
            command_name=self._owned_work_command_identity(command),
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _owned_work_command_identity(command: Command | Any) -> str:
        try:
            return command_name(command).value
        except Exception:
            return _UNRECOGNIZED_COMMAND_NAME

    @staticmethod
    def _owned_work_kind(command: Command | Any) -> OwnedWorkKind:
        if isinstance(
            command,
            (
                ScanSourceCommand,
                ReviewInterpretationCommand,
                PreviewInterpretationCommand,
                ValidateInterpretationCommand,
            ),
        ):
            return OwnedWorkKind.IMPORT_REVIEW
        if isinstance(command, ApplyInterpretationCommand):
            return OwnedWorkKind.IMPORT_APPLY
        if isinstance(command, PreprocessCommand):
            return OwnedWorkKind.PREPROCESS
        if isinstance(command, CreateEpochCommand):
            return OwnedWorkKind.EPOCH
        if isinstance(command, (TrainCommand, StopTrainingCommand)):
            return OwnedWorkKind.TRAINING
        if isinstance(command, EvaluateCommand):
            return OwnedWorkKind.EVALUATION
        if isinstance(command, SaliencyCommand):
            return OwnedWorkKind.SALIENCY
        if isinstance(command, VisualizeCommand):
            return OwnedWorkKind.RENDER
        return OwnedWorkKind.COMMAND

    @staticmethod
    def _owned_work_cancellable(command: Command | Any) -> bool:
        return isinstance(
            command,
            (
                ScanSourceCommand,
                ReviewInterpretationCommand,
                PreviewInterpretationCommand,
                ValidateInterpretationCommand,
                ApplyInterpretationCommand,
                PreprocessCommand,
                CreateEpochCommand,
                TrainCommand,
                EvaluateCommand,
                SaliencyCommand,
                VisualizeCommand,
            ),
        )

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
        reviewed_preprocess_boundary: ApplicationPreprocessBoundary | None = None,
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
        if self._uses_prepared_preprocess(command):
            return (
                self._execute_preprocess_two_phase(
                    cast(PreprocessCommand | CreateEpochCommand, command),
                    expected_publication_generation=(expected_publication_generation),
                    reviewed_preprocess_boundary=reviewed_preprocess_boundary,
                ),
                None,
            )
        if self._is_published_data_summary_query(command):
            return (
                self.query_published_data_summary(
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
        if isinstance(
            command,
            (
                ScanSourceCommand,
                ReviewInterpretationCommand,
                PreviewInterpretationCommand,
                ValidateInterpretationCommand,
            ),
        ):
            return (
                self._execute_interpretation_discovery_two_phase(
                    command,
                    expected_publication_generation=(expected_publication_generation),
                ),
                None,
            )
        if isinstance(command, ApplyInterpretationCommand):
            return (
                self._execute_apply_interpretation_two_phase(
                    command,
                    expected_publication_generation=(expected_publication_generation),
                ),
                None,
            )
        if (
            isinstance(command, EvaluateCommand)
            and command.summary_identity is not None
        ):
            return (
                self._execute_evaluation_summary_two_phase(
                    command,
                    expected_publication_generation=(expected_publication_generation),
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

    def _execute_evaluation_summary_two_phase(
        self,
        command: EvaluateCommand,
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Capture a summary target, inspect its model unlocked, then verify."""
        name = CommandName.EVALUATE
        with self._command_lock:
            owned_work_checkpoint("Admitting Evaluation model summary")
            self._publication_delivery_fence_depth += 1
            try:
                admission = self.shutdown_lifecycle.snapshot()
                if admission.closed:
                    return self._closed_command_result(command)
                if admission.fenced:
                    return self._shutdown_fence_rejection(command)
                before_publication = self._committed_view_publication()
                if expected_publication_generation is not None:
                    rejection = self._expected_publication_rejection_for_publication(
                        command,
                        expected_publication_generation,
                        before_publication,
                    )
                    if rejection is not None:
                        return rejection
                try:
                    before = self._state_before_command(command)
                except Exception as exc:
                    return self._state_read_failure_result(name.value, exc)
                try:
                    self._ensure_command_allowed(command, before)
                    training_boundary = (
                        self.state_snapshot.capture_training_read_boundary()
                    )
                    if not training_boundary.stable:
                        return self._handler_failure_result(
                            name,
                            before,
                            before_publication,
                            self._training_read_changed_error(
                                training_boundary,
                                None,
                            ),
                            read_only=True,
                        )
                    prepared_result, preparation = self.analysis.prepare_evaluate(
                        command
                    )
                    if preparation is None:
                        return self._handler_failure_result(
                            name,
                            before,
                            before_publication,
                            RuntimeError(
                                "Evaluation model summary preparation was unavailable"
                            ),
                            read_only=True,
                        )
                    after_boundary = (
                        self.state_snapshot.capture_training_read_boundary()
                    )
                    if after_boundary != training_boundary or not after_boundary.stable:
                        return self._handler_failure_result(
                            name,
                            before,
                            before_publication,
                            self._training_read_changed_error(
                                training_boundary,
                                after_boundary,
                            ),
                            read_only=True,
                        )
                except Exception as exc:
                    return self._handler_failure_result(
                        name,
                        before,
                        before_publication,
                        exc,
                        read_only=True,
                    )
            finally:
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )

        summary: EvaluationModelSummary | None = None
        summary_error: Exception | None = None
        try:
            owned_work_checkpoint("Preparing Evaluation model summary")
            summary = self.analysis.build_prepared_model_summary(preparation)
            owned_work_checkpoint("Evaluation model summary prepared")
        except OwnedOperationCancelledError:
            raise
        except Exception as exc:
            summary_error = exc

        owned_work_checkpoint("Admitting Evaluation model summary publication")
        with self._command_lock:
            self._publication_delivery_fence_depth += 1
            try:
                admission = self.shutdown_lifecycle.snapshot()
                if admission.closed:
                    return self._closed_command_result(command)
                if admission.fenced:
                    return self._shutdown_fence_rejection(command)
                current_publication = self._committed_view_publication()
                try:
                    current_boundary = (
                        self.state_snapshot.capture_training_read_boundary()
                    )
                except Exception as exc:
                    return self._handler_failure_result(
                        name,
                        current_publication.state,
                        current_publication,
                        exc,
                        read_only=True,
                    )
                if (
                    not current_publication.usable
                    or current_publication.generation != before_publication.generation
                    or current_publication.revision != before_publication.revision
                    or current_boundary != training_boundary
                    or not current_boundary.stable
                ):
                    return self._stale_evaluation_summary_result(
                        before_publication=before_publication,
                        current_publication=current_publication,
                        before_boundary=training_boundary,
                        current_boundary=current_boundary,
                    )
                if summary_error is not None:
                    return self._handler_failure_result(
                        name,
                        before,
                        before_publication,
                        summary_error,
                        read_only=True,
                    )
                if summary is None:
                    return self._handler_failure_result(
                        name,
                        before,
                        before_publication,
                        RuntimeError("Evaluation model summary result was unavailable"),
                        read_only=True,
                    )
                message, diagnostics = self.analysis.complete_prepared_evaluate(
                    prepared_result,
                    command,
                    summary,
                )
                return CommandResult.success_result(
                    command_name=name.value,
                    message=message,
                    state=before,
                    changed_state=ChangedState(),
                    diagnostics={
                        **diagnostics,
                        "training_read_verified": True,
                        "training_read_generation": current_boundary.token.generation,
                        "training_read_trainer_identity": (
                            current_boundary.trainer_identity
                        ),
                        "evaluation_publication_generation": (
                            current_publication.generation
                        ),
                        "evaluation_publication_revision": (
                            current_publication.revision
                        ),
                    },
                )
            finally:
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )

    @staticmethod
    def _stale_evaluation_summary_result(
        *,
        before_publication: ApplicationViewPublication,
        current_publication: ApplicationViewPublication,
        before_boundary: TrainingReadBoundary,
        current_boundary: TrainingReadBoundary,
    ) -> CommandResult:
        """Reject detached model text after its application identity changed."""
        message = (
            "Evaluation results changed while the model summary was prepared. "
            "Refresh Evaluation and try again."
        )
        return CommandResult.failure_result(
            command_name=CommandName.EVALUATE.value,
            message=message,
            state=current_publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={
                "stale_evaluation_summary": True,
                "state_preserved": True,
                "retryable": True,
                "expected_publication_generation": before_publication.generation,
                "current_publication_generation": current_publication.generation,
                "expected_publication_revision": before_publication.revision,
                "current_publication_revision": current_publication.revision,
                "publication_usable": current_publication.usable,
                "training_state_changed": (
                    current_boundary != before_boundary or not current_boundary.stable
                ),
                "training_generation_before": before_boundary.token.generation,
                "training_generation_after": current_boundary.token.generation,
                "trainer_identity_changed": (
                    before_boundary.trainer_identity
                    != current_boundary.trainer_identity
                ),
            },
        )

    def _execute_interpretation_discovery_two_phase(
        self,
        command: (
            ScanSourceCommand
            | ReviewInterpretationCommand
            | PreviewInterpretationCommand
            | ValidateInterpretationCommand
        ),
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Run source discovery outside the shared lock and publish if current."""
        name = command_name(command)
        with self._command_lock:
            owned_work_checkpoint("Preparing selected EEG data")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            publication = self._committed_view_publication()
            if expected_publication_generation is not None:
                rejection = self._expected_publication_rejection_for_publication(
                    command,
                    expected_publication_generation,
                    publication,
                )
                if rejection is not None:
                    return rejection
            try:
                before = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            if not publication.usable or publication.state != before:
                return self._stale_prepared_interpretation_discovery_result(
                    name=name,
                    publication=publication,
                    expected_generation=publication.generation,
                    expected_revision=publication.revision,
                    message=(
                        "Application state changed before Data Import discovery "
                        "could start. Review the current workflow and retry."
                    ),
                )
            try:
                self._ensure_command_allowed(command, before)
                plan = self.interpretation.begin_interpretation_discovery(
                    command,
                    application_boundary=ApplicationDiscoveryBoundary(
                        publication_generation=publication.generation,
                        publication_revision=publication.revision,
                        state=before,
                    ),
                )
            except Exception as exc:
                return self._handler_failure_result(
                    name,
                    before,
                    publication,
                    exc,
                )

        try:
            prepared = self.interpretation.prepare_interpretation_discovery(plan)
        except Exception as exc:
            with self._command_lock:
                try:
                    current_state = self.get_state()
                except Exception as state_error:
                    return self._state_read_failure_result(name.value, state_error)
                current_publication = self._committed_view_publication()
                if not self._interpretation_discovery_boundary_matches(
                    plan,
                    current_state=current_state,
                    publication=current_publication,
                ):
                    return self._detached_interpretation_discovery_failure_result(
                        command=command,
                        error=exc,
                        publication=current_publication,
                    )
                return self._handler_failure_result(
                    name,
                    current_state,
                    current_publication,
                    exc,
                )

        with self._command_lock:
            owned_work_checkpoint("Checking selected EEG data")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            try:
                current_state = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            current_publication = self._committed_view_publication()
            if not self._interpretation_discovery_boundary_matches(
                plan,
                current_state=current_state,
                publication=current_publication,
            ):
                return self._stale_prepared_interpretation_discovery_result(
                    name=name,
                    publication=current_publication,
                    expected_generation=plan.application.publication_generation,
                    expected_revision=plan.application.publication_revision,
                )

            if self._is_read_only_command(command, name):
                try:
                    self._ensure_command_allowed(command, current_state)
                    handler_result = (
                        self.interpretation.commit_prepared_interpretation_discovery(
                            prepared
                        )
                    )
                    message, diagnostics = self._normalize_handler_result(
                        handler_result
                    )
                except Exception as exc:
                    return self._handler_failure_result(
                        name,
                        current_state,
                        current_publication,
                        exc,
                        read_only=True,
                    )
                return CommandResult.success_result(
                    command_name=name.value,
                    message=message,
                    state=current_state,
                    changed_state=ChangedState(),
                    diagnostics=diagnostics,
                )

            self._publication_delivery_fence_depth += 1
            self._view_coordinator.mark_stale(
                "Application state is changing while Data Import discovery commits.",
            )
            self._mutation_in_progress = True
            try:
                try:
                    self._ensure_command_allowed(command, current_state)
                    handler_result = (
                        self.interpretation.commit_prepared_interpretation_discovery(
                            prepared
                        )
                    )
                    message, diagnostics = self._normalize_handler_result(
                        handler_result
                    )
                except Exception as exc:
                    self._mutation_in_progress = False
                    return self._handler_failure_result(
                        name,
                        current_state,
                        current_publication,
                        exc,
                    )
                self._last_error = None
                self._mutation_in_progress = False
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
                    changed_state=self._changed_state(current_state, after),
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )

    def _interpretation_discovery_boundary_matches(
        self,
        plan: InterpretationDiscoveryPlan,
        *,
        current_state: ApplicationStateSnapshot,
        publication: ApplicationViewPublication,
    ) -> bool:
        return bool(
            publication.usable
            and publication.state == current_state
            and self.interpretation.discovery_plan_is_current(plan)
        )

    def _detached_interpretation_discovery_failure_result(
        self,
        *,
        command: (
            ScanSourceCommand
            | ReviewInterpretationCommand
            | PreviewInterpretationCommand
            | ValidateInterpretationCommand
        ),
        error: Exception,
        publication: ApplicationViewPublication,
    ) -> CommandResult:
        """Bind a detached scan failure to current concurrently committed truth."""
        app_error = map_exception(error)
        message = str(app_error)
        diagnostics = {
            **app_error.diagnostics,
            "exception_type": safe_exception_type_name(error),
            "handler_error_type": app_error.error_type.value,
            "handler_error_message": message,
            "handler_error_recoverable": app_error.recoverable,
            "detached_prepare_failed_after_concurrent_change": True,
            "state_preserved": True,
            "publication_generation": publication.generation,
            "publication_revision": publication.revision,
        }
        if app_error.error_type is ErrorType.CANCELLED:
            diagnostics["control_flow_outcome"] = True
        return CommandResult.failure_result(
            command_name=command_name(command).value,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=app_error.error_type,
            recoverable=app_error.recoverable,
            error_message=message,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _stale_prepared_interpretation_discovery_result(
        *,
        name: CommandName,
        publication: ApplicationViewPublication,
        expected_generation: int,
        expected_revision: int,
        message: str | None = None,
    ) -> CommandResult:
        public_message = message or (
            "Application state changed while Data Import discovery was prepared. "
            "Review the current workflow and retry."
        )
        return CommandResult.failure_result(
            command_name=name.value,
            message=public_message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=public_message,
            diagnostics={
                "stale_prepared_interpretation_discovery": True,
                "state_preserved": True,
                "expected_publication_generation": expected_generation,
                "current_publication_generation": publication.generation,
                "expected_publication_revision": expected_revision,
                "current_publication_revision": publication.revision,
                "publication_usable": publication.usable,
            },
        )

    def _execute_apply_interpretation_two_phase(
        self,
        command: ApplyInterpretationCommand,
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Prepare Raw data outside the command lock, then commit a guarded payload."""
        name = CommandName.APPLY_INTERPRETATION
        with self._command_lock:
            owned_work_checkpoint("Preparing reviewed EEG import")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            publication = self._committed_view_publication()
            if expected_publication_generation is not None:
                rejection = self._expected_publication_rejection_for_publication(
                    command,
                    expected_publication_generation,
                    publication,
                )
                if rejection is not None:
                    return rejection
            try:
                before = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            if not publication.usable or publication.state != before:
                message = (
                    "Application state changed before Data Import could start. "
                    "Review the current interpretation and retry."
                )
                return CommandResult.failure_result(
                    command_name=name.value,
                    message=message,
                    state=publication.state,
                    changed_state=ChangedState(),
                    error_type=ErrorType.PRECONDITION,
                    recoverable=True,
                    error_message=message,
                    diagnostics={
                        "stale_prepared_interpretation_apply": True,
                        "state_preserved": True,
                    },
                )
            try:
                self._ensure_command_allowed(command, before)
                plan = self.interpretation.begin_apply_interpretation(
                    command,
                    application_boundary=ApplicationApplyBoundary(
                        publication_generation=publication.generation,
                        publication_revision=publication.revision,
                        state=before,
                    ),
                )
            except Exception as exc:
                return self._handler_failure_result(
                    name,
                    before,
                    publication,
                    exc,
                )

        try:
            prepared = self.interpretation.prepare_apply_interpretation(plan)
            prepared = self.interpretation.verify_prepared_apply_content(prepared)
        except Exception as exc:
            with self._command_lock:
                try:
                    current_state = self.get_state()
                except Exception as state_error:
                    return self._state_read_failure_result(name.value, state_error)
                current_publication = self._committed_view_publication()
                if (
                    current_publication.generation
                    != plan.application.publication_generation
                    or current_publication.revision
                    != plan.application.publication_revision
                    or current_publication.state != plan.application.state
                    or current_state != current_publication.state
                ):
                    return self._detached_apply_prepare_failure_result(
                        command=command,
                        error=exc,
                        publication=current_publication,
                    )
                return self._handler_failure_result(
                    name,
                    current_state,
                    current_publication,
                    exc,
                )

        with self._command_lock:
            owned_work_checkpoint("Admitting prepared interpretation apply")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            try:
                current_state = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            current_publication = self._committed_view_publication()
            if (
                not current_publication.usable
                or current_publication.generation
                != plan.application.publication_generation
                or current_publication.revision != plan.application.publication_revision
                or current_publication.state != plan.application.state
                or current_state != plan.application.state
            ):
                return self._stale_prepared_interpretation_apply_result(
                    plan,
                    current_publication,
                )

            self._publication_delivery_fence_depth += 1
            self._view_coordinator.mark_stale(
                "Application state is changing while prepared data commits.",
            )
            self._mutation_in_progress = True
            try:
                try:
                    self._ensure_command_allowed(command, current_state)
                    handler_result = (
                        self.interpretation.commit_prepared_apply_interpretation(
                            prepared
                        )
                    )
                    message, diagnostics = self._normalize_handler_result(
                        handler_result
                    )
                    diagnostics = self._update_montage_preparation_after_command(
                        command=command,
                        name=name,
                        diagnostics=diagnostics,
                    )
                except Exception as exc:
                    self._mutation_in_progress = False
                    return self._handler_failure_result(
                        name,
                        current_state,
                        current_publication,
                        exc,
                    )
                self._last_error = None
                # Publication delivery remains fenced until the verified result
                # returns, but state capture must commit the new read model.
                self._mutation_in_progress = False
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
                    changed_state=self._changed_state(current_state, after),
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )

    @staticmethod
    def _uses_prepared_preprocess(command: Command | Any) -> bool:
        """Return whether a command has a detached preprocess implementation."""
        if isinstance(command, CreateEpochCommand):
            return True
        if not isinstance(command, PreprocessCommand):
            return False
        try:
            operation = PreprocessOperation(command.operation)
        except ValueError:
            return False
        return operation not in {
            PreprocessOperation.SET_MONTAGE,
        }

    def _execute_preprocess_two_phase(
        self,
        command: PreprocessCommand | CreateEpochCommand,
        *,
        expected_publication_generation: int | None,
        reviewed_preprocess_boundary: ApplicationPreprocessBoundary | None,
    ) -> CommandResult:
        """Prepare EEG transforms outside the lock, then commit if still current."""
        name = command_name(command)
        with self._command_lock:
            owned_work_checkpoint("Admitting EEG preprocessing")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            publication = self._committed_view_publication()
            if expected_publication_generation is not None:
                rejection = self._expected_publication_rejection_for_publication(
                    command,
                    expected_publication_generation,
                    publication,
                )
                if rejection is not None and not (
                    self._reviewed_channel_selection_boundary_matches(
                        command,
                        expected_generation=expected_publication_generation,
                        reviewed_boundary=reviewed_preprocess_boundary,
                        publication=publication,
                    )
                ):
                    return rejection
            try:
                before = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            if not publication.usable or publication.state != before:
                return self._stale_prepared_preprocess_result(
                    name=name,
                    publication=publication,
                    expected_generation=publication.generation,
                    expected_revision=publication.revision,
                    message=(
                        "Application state changed before EEG preprocessing could "
                        "start. Review the current data and retry."
                    ),
                )
            try:
                self._ensure_command_allowed(command, before)
                plan = self.preprocess_commands.begin_prepared_command(
                    command,
                    application_boundary=ApplicationPreprocessBoundary(
                        publication_generation=publication.generation,
                        publication_revision=publication.revision,
                        state=before,
                    ),
                )
            except Exception as exc:
                return self._handler_failure_result(
                    name,
                    before,
                    publication,
                    exc,
                )

        try:
            prepared = self.preprocess_commands.prepare_command(plan)
        except Exception as exc:
            with self._command_lock:
                try:
                    current_state = self.get_state()
                except Exception as state_error:
                    return self._state_read_failure_result(name.value, state_error)
                current_publication = self._committed_view_publication()
                if not self._preprocess_application_boundary_matches(
                    plan,
                    current_state=current_state,
                    publication=current_publication,
                ):
                    return self._detached_preprocess_prepare_failure_result(
                        command=command,
                        error=exc,
                        publication=current_publication,
                    )
                return self._handler_failure_result(
                    name,
                    current_state,
                    current_publication,
                    exc,
                )

        with self._command_lock:
            owned_work_checkpoint("Admitting prepared EEG preprocessing")
            admission = self.shutdown_lifecycle.snapshot()
            if admission.closed:
                return self._closed_command_result(command)
            if admission.fenced:
                return self._shutdown_fence_rejection(command)
            try:
                current_state = self.get_state()
            except Exception as exc:
                return self._state_read_failure_result(name.value, exc)
            current_publication = self._committed_view_publication()
            if not self._preprocess_application_boundary_matches(
                plan,
                current_state=current_state,
                publication=current_publication,
            ):
                return self._stale_prepared_preprocess_result(
                    name=name,
                    publication=current_publication,
                    expected_generation=plan.application.publication_generation,
                    expected_revision=plan.application.publication_revision,
                )

            self._publication_delivery_fence_depth += 1
            self._view_coordinator.mark_stale(
                "Application state is changing while prepared EEG data commits.",
            )
            self._mutation_in_progress = True
            try:
                try:
                    self._ensure_command_allowed(command, current_state)
                    handler_result = self.preprocess_commands.commit_prepared_command(
                        prepared
                    )
                    message, diagnostics = self._normalize_handler_result(
                        handler_result
                    )
                except Exception as exc:
                    self._mutation_in_progress = False
                    return self._handler_failure_result(
                        name,
                        current_state,
                        current_publication,
                        exc,
                    )
                self._last_error = None
                self._mutation_in_progress = False
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
                    changed_state=self._changed_state(current_state, after),
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._publication_delivery_fence_depth -= 1
                if self._publication_delivery_fence_depth < 0:
                    self._publication_delivery_fence_depth = 0
                    raise RuntimeError(
                        "Application publication delivery fence became unbalanced."
                    )

    @staticmethod
    def _reviewed_channel_selection_boundary_matches(
        command: PreprocessCommand | CreateEpochCommand,
        *,
        expected_generation: int,
        reviewed_boundary: ApplicationPreprocessBoundary | None,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Allow only advisory montage drift from one reviewed channel dialog."""
        if reviewed_boundary is None or not isinstance(command, PreprocessCommand):
            return False
        try:
            operation = PreprocessOperation(command.operation)
        except ValueError:
            return False
        if operation is not PreprocessOperation.SELECT_CHANNELS:
            return False
        if (
            reviewed_boundary.publication_generation != expected_generation
            or not reviewed_boundary.state.state_reliable
            or not publication.usable
            or not publication.state.state_reliable
        ):
            return False
        reviewed_capability = build_capability_policy(
            reviewed_boundary.state,
        ).get(CommandName.PREPROCESS)
        current_capability = publication.effective_capabilities.get(
            CommandName.PREPROCESS,
        )
        if not reviewed_capability.enabled or not current_capability.enabled:
            return False
        return ApplicationService._only_montage_preparation_status_changed(
            reviewed_boundary.state,
            publication.state,
        )

    @staticmethod
    def _preprocess_application_boundary_matches(
        plan: PreprocessMutationPlan,
        *,
        current_state: ApplicationStateSnapshot,
        publication: ApplicationViewPublication,
    ) -> bool:
        boundary = plan.application
        if not publication.usable or publication.state != current_state:
            return False
        if (
            publication.generation == boundary.publication_generation
            and publication.revision == boundary.publication_revision
            and current_state == boundary.state
        ):
            return True
        return ApplicationService._only_montage_preparation_status_changed(
            boundary.state,
            current_state,
        )

    @staticmethod
    def _only_montage_preparation_status_changed(
        expected: ApplicationStateSnapshot,
        current: ApplicationStateSnapshot,
    ) -> bool:
        """Allow advisory BIDS geometry progress without staling EEG work."""
        expected_visualization = expected.visualization
        current_visualization = current.visualization
        progress_changed = (
            expected_visualization.montage_preparation_state
            != current_visualization.montage_preparation_state
            or expected_visualization.montage_preparation_reason
            != current_visualization.montage_preparation_reason
        )
        if not progress_changed:
            return False
        normalized_expected = replace(
            expected,
            visualization=replace(
                expected_visualization,
                montage_preparation_state=(
                    current_visualization.montage_preparation_state
                ),
                montage_preparation_reason=(
                    current_visualization.montage_preparation_reason
                ),
            ),
        )
        return normalized_expected == current

    def _detached_preprocess_prepare_failure_result(
        self,
        *,
        command: PreprocessCommand | CreateEpochCommand,
        error: Exception,
        publication: ApplicationViewPublication,
    ) -> CommandResult:
        """Bind detached prepare failure to current concurrently committed truth."""
        app_error = map_exception(error)
        message = str(app_error)
        diagnostics = {
            **app_error.diagnostics,
            "exception_type": safe_exception_type_name(error),
            "handler_error_type": app_error.error_type.value,
            "handler_error_message": message,
            "handler_error_recoverable": app_error.recoverable,
            "detached_prepare_failed_after_concurrent_change": True,
            "state_preserved": True,
            "publication_generation": publication.generation,
            "publication_revision": publication.revision,
        }
        if app_error.error_type is ErrorType.CANCELLED:
            diagnostics["control_flow_outcome"] = True
        return CommandResult.failure_result(
            command_name=command_name(command).value,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=app_error.error_type,
            recoverable=app_error.recoverable,
            error_message=message,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _stale_prepared_preprocess_result(
        *,
        name: CommandName,
        publication: ApplicationViewPublication,
        expected_generation: int,
        expected_revision: int,
        message: str | None = None,
    ) -> CommandResult:
        public_message = message or (
            "Application state changed while EEG preprocessing was prepared. "
            "Review the current data and retry."
        )
        return CommandResult.failure_result(
            command_name=name.value,
            message=public_message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=public_message,
            diagnostics={
                "stale_prepared_preprocess": True,
                "state_preserved": True,
                "expected_publication_generation": expected_generation,
                "current_publication_generation": publication.generation,
                "expected_publication_revision": expected_revision,
                "current_publication_revision": publication.revision,
                "publication_usable": publication.usable,
            },
        )

    def _detached_apply_prepare_failure_result(
        self,
        *,
        command: ApplyInterpretationCommand,
        error: Exception,
        publication: ApplicationViewPublication,
    ) -> CommandResult:
        """Bind a detached failure to current truth after another command won."""
        app_error = map_exception(error)
        message = str(app_error)
        diagnostics = {
            **app_error.diagnostics,
            "exception_type": safe_exception_type_name(error),
            "handler_error_type": app_error.error_type.value,
            "handler_error_message": message,
            "handler_error_recoverable": app_error.recoverable,
            "detached_prepare_failed_after_concurrent_change": True,
            "state_preserved": True,
            "publication_generation": publication.generation,
            "publication_revision": publication.revision,
        }
        if app_error.error_type is ErrorType.CANCELLED:
            diagnostics["control_flow_outcome"] = True
        return CommandResult.failure_result(
            command_name=self._owned_work_command_identity(command),
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=app_error.error_type,
            recoverable=app_error.recoverable,
            error_message=message,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _stale_prepared_interpretation_apply_result(
        plan: InterpretationApplyPlan,
        publication: ApplicationViewPublication,
    ) -> CommandResult:
        message = (
            "Application state changed while EEG recordings were prepared. "
            "Review the current Data Import choices and retry."
        )
        return CommandResult.failure_result(
            command_name=CommandName.APPLY_INTERPRETATION.value,
            message=message,
            state=publication.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=message,
            diagnostics={
                "stale_prepared_interpretation_apply": True,
                "state_preserved": True,
                "expected_publication_generation": (
                    plan.application.publication_generation
                ),
                "current_publication_generation": publication.generation,
                "expected_publication_revision": plan.application.publication_revision,
                "current_publication_revision": publication.revision,
                "publication_usable": publication.usable,
            },
        )

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
            owned_work_checkpoint("Product command admitted")
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

    @staticmethod
    def _is_published_data_summary_query(command: Command | Any) -> bool:
        """Whether a dataset summary is already detached in the publication."""
        return isinstance(command, QueryStateCommand) and (
            str(command.query or "").lower() == "data_summary"
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
        self.training_resource_preview.begin_close()
        self.cancel_all_owned_operations()

    def release_shutdown_fence(self) -> bool:
        """Reopen admission and reconcile state hidden by the shutdown fence."""
        released = self.shutdown_lifecycle.release_fence()
        if released:
            self.training_resource_preview.cancel_close()
        return released

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
        if isinstance(command, SaliencyCommand) and command.target is not None:
            self._require_saliency_target_admitted(command.target, before)
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
                diagnostics = self._update_montage_preparation_after_command(
                    command=command,
                    name=name,
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

    def _update_montage_preparation_after_command(
        self,
        *,
        command: Command,
        name: CommandName,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """Advance advisory BIDS geometry without changing command success."""
        try:
            snapshot = None
            if name is CommandName.APPLY_INTERPRETATION:
                applied = diagnostics.get("applied_interpretation")
                source_kind = (
                    str(applied.get("source_kind") or "")
                    if isinstance(applied, dict)
                    else ""
                )
                snapshot = (
                    self.bids_montage_preparation.synchronize_loaded_recordings(
                        self.dataset.get_loaded_data_list() or ()
                    )
                    if source_kind == "bids"
                    else self.bids_montage_preparation.reset()
                )
            elif name is CommandName.APPLY_MONTAGE and isinstance(
                command,
                ApplyMontageCommand,
            ):
                snapshot = self.bids_montage_preparation.select_manual_values(
                    name=command.montage_name or "Manual montage",
                    channel_names=command.channels,
                    positions=command.positions,
                )
            elif name in {
                CommandName.LOAD_DATA,
                CommandName.REMOVE_FILES,
                CommandName.RESET_PREPROCESS,
            }:
                snapshot = self.bids_montage_preparation.synchronize_loaded_recordings(
                    self.dataset.get_loaded_data_list() or ()
                )
            elif name in {CommandName.RESET_SESSION, CommandName.NEW_SESSION}:
                snapshot = self.bids_montage_preparation.reset()
            if snapshot is None:
                return diagnostics
            else:
                return {
                    **diagnostics,
                    "montage_preparation": {
                        "state": snapshot.state,
                        "generation": snapshot.generation,
                        "reason": snapshot.reason,
                        "import_blocking": False,
                    },
                }
        except Exception as exc:
            logger.exception("Could not schedule optional BIDS montage preparation")
            return {
                **diagnostics,
                "montage_preparation": {
                    "state": "failed",
                    "reason": public_exception_message(exc),
                    "import_blocking": False,
                },
            }

    def _commit_bids_montage_publication(
        self,
        work: MontagePreparationWork,
        snapshot: MontagePreparationSnapshot,
    ) -> None:
        """Commit optional geometry atomically with its application publication."""
        with self._command_lock:
            if self.shutdown_lifecycle.snapshot().closing:
                return
            promoted = self.bids_montage_preparation.promote_result(
                work,
                snapshot,
                refresh_candidate=self._refresh_training_publication_strict,
            )
            if not promoted:
                return
            publication = self._committed_view_publication()
        self._publish_view_changed(publication)

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
            or app_error.error_type is ErrorType.CANCELLED
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
            CommandName.TRAIN: self._handle_train_with_saved_split,
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
