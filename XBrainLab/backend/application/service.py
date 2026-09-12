"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from functools import cached_property
from threading import Lock, RLock
from time import monotonic
from typing import TYPE_CHECKING, Any, cast

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
    Command,
    CommandName,
    CreateEpochCommand,
    DiscardTrainingPreparationCommand,
    EvaluateCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    RemoveFilesCommand,
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
from .data_interpretation_apply_preparation import (
    ApplicationApplyBoundary,
    InterpretationApplyPlan,
)
from .data_interpretation_discovery_preparation import (
    ApplicationDiscoveryBoundary,
    InterpretationDiscoveryPlan,
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
)
from .errors import (
    ApplicationError,
    PreconditionError,
    map_exception,
)
from .evaluation_render import (
    EvaluationModelSummary,
    EvaluationRenderPublication,
    EvaluationRenderPublisher,
    EvaluationRenderRequest,
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
    SaliencyRenderPublication,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
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
from .training_operation_monitor import TrainingOperationMonitor
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
)
from .training_snapshot import (
    model_signal_context_snapshot as build_model_signal_context_snapshot,
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

if TYPE_CHECKING:
    from .analysis_service import AnalysisCommandService
    from .data_interpretation_service import DataInterpretationCommandService
    from .dataset_generation_service import DatasetGenerationCommandService
    from .training_service import TrainingCommandService

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
        UpdateMetadataCommand,
        ApplySmartParseCommand,
        RemoveFilesCommand,
    )

    def __init__(self, get_interpretation: Callable[[], Any | None]) -> None:
        self._get_interpretation = get_interpretation

    def _invalidate(self) -> bool:
        interpretation = self._get_interpretation()
        return bool(
            interpretation is not None
            and interpretation.invalidate_for_legacy_raw_mutation()
        )

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
            self._invalidate()
            raise RuntimeError(
                "Legacy raw mutation handlers must report an integer success_count."
            )
        if success_count < 0:
            self._invalidate()
            raise RuntimeError(
                "Legacy raw mutation handlers cannot report a negative success_count."
            )
        if success_count == 0:
            return diagnostics
        invalidated = self._invalidate()
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
        self._invalidate()


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
        self._synchronous_training_lifecycle_lock = (
            self.study._synchronous_training_lifecycle_lock
        )
        self._mutation_in_progress = False
        self._publication_delivery_fence_depth = 0
        self.pipeline_transaction = PipelineStateTransaction(
            self.study,
            training_runtime=self.training_runtime,
        )
        self.legacy_raw_mutation_lifecycle = _LegacyRawMutationLifecycleCoordinator(
            lambda: vars(self).get("interpretation"),
        )
        self.data_table = DataTableCommandService(dataset=self.dataset_state)
        self.preprocess_commands = PreprocessCommandService(
            preprocess=self.preprocess,
            dataset=self.dataset,
            pipeline_transaction=self.pipeline_transaction,
        )
        self.training_recommendation = TrainingRecommendationService()
        self.training_configuration_reset = TrainingConfigurationResetService(
            training=self.training,
            training_runtime=self.training_runtime,
            recommendation=self.training_recommendation,
        )
        self.training_resource_preview = TrainingResourcePreviewCoordinator(
            estimate=lambda request,
            context: self.training_commands.get_resource_preview(request, context),
            generation_is_current=self._training_preview_generation_is_current,
            registry=self.owned_work,
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
            dataset_split_state=self._dataset_split_state,
            interpretation_snapshot=lambda: (
                self.interpretation.snapshot()
                if "interpretation" in vars(self)
                else InterpretationStateSnapshot()
            ),
            saliency_coverage_projector=self.saliency_coverage_projector,
            training_recommendation=self.training_recommendation,
            montage_snapshot_provider=self.bids_montage_preparation.snapshot,
            effective_montage_provider=(
                self.bids_montage_preparation.effective_montage
            ),
            bids_restore_available_provider=(
                self.bids_montage_preparation.can_restore_bids
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
            tuple(self.dataset_state.get_active_data_rows())
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
            build_data_summary_rows=self.dataset_state.get_active_data_rows,
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
            config_factory=self._dataset_config_from_payload,
        )
        self.query_state_commands = QueryStateCommandService(
            dataset=self.dataset_state,
            state_builder=self.state_snapshot,
            get_state=self.get_state,
        )
        self.lifecycle = LifecycleCommandService(
            dataset=self.dataset,
            clear_training_configuration=lambda: (
                self.training_configuration_reset.clear()
            ),
            clear_interpretation=lambda: (
                self.interpretation.clear() if "interpretation" in vars(self) else None
            ),
            get_state=self.get_state,
            pipeline_transaction=self.pipeline_transaction,
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
            publication_lifecycle=self.publication_lifecycle,
            refresh_training_publication=self._refresh_training_publication_strict,
            committed_view_publication=self._committed_view_publication,
            wait_for_synchronous_training_quiescence=(
                self._wait_for_synchronous_training_quiescence
            ),
        )
        self.training_operation_monitor = TrainingOperationMonitor(
            training_runtime=self.training_runtime,
            registry=self.owned_work,
            shutdown_snapshot=self.shutdown_lifecycle.snapshot,
        )
        self.synchronous_training_lifecycle = SynchronousTrainingLifecycleCoordinator(
            training_runtime=self.training_runtime,
            terminal_notifications=self.training,
            retry_terminal_delivery=(
                self._retry_synchronous_training_terminal_delivery
            ),
            command_lock=self._command_lock,
            complete_training=lambda identity: (
                self.training_commands.complete_synchronous_training(identity)
            ),
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

    @cached_property
    def interpretation(self) -> DataInterpretationCommandService:
        """Construct the real interpretation owner only when a workflow needs it."""
        from .data_interpretation_service import (  # noqa: PLC0415
            DataInterpretationCommandService,
        )

        return DataInterpretationCommandService(
            self.dataset,
            data_filepath=StateSnapshotService.data_filepath,
            pipeline_transaction=self.pipeline_transaction,
        )

    @cached_property
    def dataset_generation(self) -> DatasetGenerationCommandService:
        """Construct the split owner on first command, not on state reads."""
        from .dataset_generation_service import (  # noqa: PLC0415
            DatasetGenerationCommandService,
        )

        return DatasetGenerationCommandService(
            study=self.study,
            training=self.training,
            has_trainer=self.training_runtime.has_trainer,
            pipeline_transaction=self.pipeline_transaction,
            get_publication_generation=lambda: (
                self._committed_view_publication().generation
            ),
        )

    @cached_property
    def training_commands(self) -> TrainingCommandService:
        """Construct the real training owner after its dependencies are composed."""
        from .training_service import TrainingCommandService  # noqa: PLC0415

        return TrainingCommandService(
            training=self.training,
            training_runtime=self.training_runtime,
            get_state=self.get_state,
            recommendation=self.training_recommendation,
            resource_refinement_provider=self.training_resource_preview.refinements_for_configuration,
        )

    def _dataset_split_state(self, datasets: list[Any]) -> dict[str, Any]:
        service = vars(self).get("dataset_generation")
        if service is not None:
            return service.dataset_split_state(datasets)
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

    @staticmethod
    def _dataset_config_from_payload(payload: dict[str, Any]) -> Any:
        """Parse preview input without constructing mutable split lifecycle state."""
        from .dataset_generation_service import (  # noqa: PLC0415
            DatasetGenerationCommandService,
        )

        return DatasetGenerationCommandService.config_from_payload(payload)

    @cached_property
    def analysis(self) -> AnalysisCommandService:
        """Create the real analysis owner only when an analysis route is used."""
        from .analysis_service import AnalysisCommandService  # noqa: PLC0415

        return AnalysisCommandService(
            training_runtime=self.training_runtime,
            visualization=self.visualization,
            get_state=self.get_state,
        )

    def _wait_for_synchronous_training_quiescence(self, timeout: float) -> bool:
        return self.synchronous_training_lifecycle.wait_until_quiescent(timeout=timeout)

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
            handoff, setup = self.preprocess_commands.build_epoch_setup(
                state,
                source_data=self.dataset_state.get_preprocessed_data_list(),
            )
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

        if not self.training_operation_monitor.wait_until_idle(timeout=remaining()):
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
                snapshot = self.training_operation_monitor.start_training(
                    operation_id,
                    str(result.diagnostics["training_trainer_identity"]),
                    result.diagnostics.get("training_handoff_generation"),
                )
            elif (
                result.ok
                and isinstance(command, SaliencyCommand)
                and result.diagnostics.get("action") == "schedule"
            ):
                schedule = result.diagnostics.get("post_training_saliency_schedule")
                status = schedule.get("status") if isinstance(schedule, dict) else None
                generation = (
                    status.get("generation") if isinstance(status, dict) else None
                )
                snapshot = self.training_operation_monitor.start_saliency(
                    operation_id,
                    generation,
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
        return PostTrainingSaliencyTarget(
            run=outcome.run,
            finished_runs_before=0,
            finished_runs_after=finished_runs,
            append=False,
            explicit=True,
        )

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

    def _release_publication_delivery_fence(self) -> None:
        """Release one command-owned publication delivery fence."""
        self._publication_delivery_fence_depth -= 1
        if self._publication_delivery_fence_depth < 0:
            self._publication_delivery_fence_depth = 0
            raise RuntimeError(
                "Application publication delivery fence became unbalanced."
            )

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
                    identity = preparation.identity
                    selected_plan = self.training_runtime.training_plan_holders()[
                        identity.plan.plan_index
                    ]
                    selected_run = (
                        selected_plan.get_plans()[identity.run.run_index]
                        if identity.run is not None
                        else None
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
                self._release_publication_delivery_fence()

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
                    or current_boundary.trainer_identity
                    != training_boundary.trainer_identity
                    or not current_boundary.stable
                ):
                    return self._stale_evaluation_summary_result(
                        before_publication=before_publication,
                        current_publication=current_publication,
                        before_boundary=training_boundary,
                        current_boundary=current_boundary,
                    )
                try:
                    current_plans = self.training_runtime.training_plan_holders()
                    current_plan = current_plans[identity.plan.plan_index]
                    current_run = (
                        current_plan.get_plans()[identity.run.run_index]
                        if identity.run is not None
                        else None
                    )
                    prepared_result, current_preparation = (
                        self.analysis.prepare_evaluate(command)
                    )
                    target_unchanged = (
                        current_plan is selected_plan
                        and current_run is selected_run
                        and current_preparation is not None
                        and current_preparation.dataset is preparation.dataset
                        and current_preparation.model_instance
                        is preparation.model_instance
                        and current_preparation.model_holder is preparation.model_holder
                        and current_preparation.terminal == preparation.terminal
                    )
                except (IndexError, PreconditionError):
                    target_unchanged = False
                if not target_unchanged:
                    return self._stale_evaluation_summary_result(
                        before_publication=before_publication,
                        current_publication=current_publication,
                        before_boundary=training_boundary,
                        current_boundary=current_boundary,
                    )
                if summary_error is not None:
                    return self._handler_failure_result(
                        name,
                        current_publication.state,
                        current_publication,
                        summary_error,
                        read_only=True,
                    )
                if summary is None:
                    return self._handler_failure_result(
                        name,
                        current_publication.state,
                        current_publication,
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
                    state=current_publication.state,
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
                self._release_publication_delivery_fence()

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
                    return self._detached_prepare_failure_result(
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
                return self._result_after_mutation(
                    name=name,
                    before=current_state,
                    message=message,
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._release_publication_delivery_fence()

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

    def _detached_prepare_failure_result(
        self,
        *,
        command: Command,
        error: Exception,
        publication: ApplicationViewPublication,
    ) -> CommandResult:
        """Bind a detached prepare failure to current committed truth."""
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
                    return self._detached_prepare_failure_result(
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
                return self._result_after_mutation(
                    name=name,
                    before=current_state,
                    message=message,
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._release_publication_delivery_fence()

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
                    return self._detached_prepare_failure_result(
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
                    if name is CommandName.CREATE_EPOCH:
                        self._project_effective_montage_to_epoch()
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
                return self._result_after_mutation(
                    name=name,
                    before=current_state,
                    message=message,
                    diagnostics=diagnostics,
                )
            finally:
                self._mutation_in_progress = False
                self._release_publication_delivery_fence()

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
            electrode_layout=current.electrode_layout,
        )
        return normalized_expected == current

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
                self._release_publication_delivery_fence()
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
        if name in {CommandName.EVALUATE, CommandName.VISUALIZE}:
            publication = self._committed_view_publication()
            publication_key = (
                "evaluation_publication_generation"
                if name is CommandName.EVALUATE
                else "visualization_publication_generation"
            )
            diagnostics = {
                **diagnostics,
                publication_key: publication.generation,
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
        return self._result_after_mutation(
            name=name,
            before=before,
            message=message,
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
            elif name in {
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
            self._project_effective_montage_to_epoch()
            publication = self._committed_view_publication()
        self._publish_view_changed(publication)

    def _handle_apply_montage(
        self,
        command: Command,
    ) -> HandlerResult:
        """Commit a reviewed layout under the command lock, without preprocessing."""
        if not isinstance(command, ApplyMontageCommand):
            raise TypeError("Invalid command for apply_montage")
        epoch_data = self.study.epoch_data
        if epoch_data is not None:
            epoch_names = epoch_data.get_channel_names()
            get_data = getattr(epoch_data, "get_data", None)
            channel_axis_matches = True
            if callable(get_data):
                epoch_array = get_data()
                shape = getattr(epoch_array, "shape", None)
                channel_axis_matches = (
                    isinstance(shape, tuple)
                    and len(shape) == 3
                    and shape[1] == len(epoch_names)
                )
            if len(set(epoch_names)) != len(epoch_names) or not channel_axis_matches:
                raise RuntimeError("Epoch channel identity is inconsistent.")
        current_channels = (
            tuple(epoch_data.get_channel_names())
            if epoch_data is not None
            else tuple(self.get_state().raw.channels)
        )
        if command.restore_bids:
            if (
                command.channels
                or command.positions
                or command.montage_name is not None
                or command.electrode_names is not None
            ):
                raise ValueError(
                    "Restoring BIDS electrode layout cannot include a manual layout."
                )
            if self.training_runtime.has_trainer():
                raise ValueError(
                    "Clear training before replacing an electrode layout used "
                    "by model inputs."
                )
            snapshot = self.bids_montage_preparation.restore_bids(current_channels)
            self._project_effective_montage_to_epoch()
            effective = self.bids_montage_preparation.effective_montage()
            if effective is None:
                raise RuntimeError(
                    "Restored BIDS electrode layout was not available for projection."
                )
            return "Restored the BIDS electrode layout.", {
                "channel_count": len(effective.channel_names),
                "montage_preparation": {
                    "state": snapshot.state,
                    "generation": snapshot.generation,
                    "reason": snapshot.reason,
                    "import_blocking": False,
                },
            }
        manual_override = self.bids_montage_preparation.build_manual_override(
            name=command.montage_name or "Manual montage",
            selected_channel_names=current_channels,
            channel_names=command.channels,
            positions=command.positions,
            electrode_names=command.electrode_names,
        )
        channels = manual_override.channel_names
        electrodes = manual_override.electrode_names
        positions = manual_override.positions_m
        if self.training_runtime.has_trainer():
            existing = self.bids_montage_preparation.effective_montage()
            requested = (
                channels,
                electrodes,
                positions,
            )
            current = (
                (
                    tuple(existing.channel_names),
                    tuple(existing.electrode_names),
                    tuple(existing.positions_m),
                )
                if existing is not None
                else None
            )
            if current is not None and current != requested:
                raise ValueError(
                    "Clear training before replacing an electrode layout used "
                    "by model inputs."
                )
            if current == requested:
                return (
                    "Electrode layout is already applied.",
                    {"channel_count": len(channels), "layout_noop": True},
                )
        snapshot = self.bids_montage_preparation.select_manual(manual_override)
        self._project_effective_montage_to_epoch()
        message = (
            f"Applied electrode layout '{command.montage_name}' to "
            f"{len(channels)} channel(s)."
            if command.montage_name
            else f"Applied electrode layout to {len(channels)} channel(s)."
        )
        return message, {
            "channel_count": len(channels),
            "montage_preparation": {
                "state": snapshot.state,
                "generation": snapshot.generation,
                "reason": snapshot.reason,
                "import_blocking": False,
            },
        }

    def _project_effective_montage_to_epoch(self) -> None:
        """Project coordinator geometry without modifying Epoch identity."""
        epoch_data = self.study.epoch_data
        effective = self.bids_montage_preparation.effective_montage()
        if epoch_data is None or effective is None:
            return
        set_channel_positions = getattr(epoch_data, "set_channel_positions", None)
        if not callable(set_channel_positions):
            return
        positions_by_channel = {
            channel: position
            for channel, position in zip(
                effective.channel_names,
                effective.positions_m,
                strict=True,
            )
            if channel in epoch_data.get_channel_names()
        }
        set_channel_positions(positions_by_channel)

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

    def _result_after_mutation(
        self,
        *,
        name: CommandName,
        before: ApplicationStateSnapshot,
        message: str,
        diagnostics: dict[str, Any],
    ) -> CommandResult:
        """Verify a committed mutation before reporting success on any command route.

        The caller retains admission and publication fencing, and ends mutation
        capture before entering here so the new read model can be verified.
        """
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
        """Bind serialized command handlers not handled by a detached route."""
        handlers: dict[CommandName, Callable[[Command], HandlerResult]] = {
            CommandName.SAVE_INTERPRETATION_RECIPE: (
                lambda command: self.interpretation.handle_save_interpretation_recipe(
                    command
                )
            ),
            CommandName.RELOAD_INTERPRETATION_RECIPE: (
                lambda command: self.interpretation.handle_reload_interpretation_recipe(
                    command
                )
            ),
            CommandName.UPDATE_METADATA: self.data_table.handle_update_metadata,
            CommandName.APPLY_SMART_PARSE: self.data_table.handle_apply_smart_parse,
            CommandName.REMOVE_FILES: self.data_table.handle_remove_files,
            CommandName.PREPROCESS: self.preprocess_commands.handle_preprocess,
            CommandName.CONFIGURE_DATASET_SPLIT: (
                lambda command: self.dataset_generation.handle_save_dataset_split(
                    command
                )
            ),
            CommandName.CLEAR_DATASETS: (
                lambda command: self.dataset_generation.handle_clear_datasets(command)
            ),
            CommandName.CONFIGURE_TRAINING: (
                lambda command: self.training_commands.handle_configure_training(
                    command
                )
            ),
            CommandName.TRAIN: self._handle_train_with_saved_split,
            CommandName.DISCARD_TRAINING_PREPARATION: (
                self._handle_discard_training_preparation
            ),
            CommandName.STOP_TRAINING: (
                lambda command: self.training_commands.handle_stop_training(command)
            ),
            CommandName.CLEAR_TRAINING_HISTORY: (
                lambda command: self.training_commands.handle_clear_training_history(
                    command
                )
            ),
            CommandName.EVALUATE: lambda command: self.analysis.handle_evaluate(
                command
            ),
            CommandName.VISUALIZE: lambda command: self.analysis.handle_visualize(
                command
            ),
            CommandName.SALIENCY: lambda command: self.analysis.handle_saliency(
                command
            ),
            CommandName.APPLY_MONTAGE: self._handle_apply_montage,
            CommandName.RESET_PREPROCESS: self.lifecycle.handle_reset_preprocess,
            CommandName.RESET_SESSION: self.lifecycle.handle_reset_session,
            CommandName.NEW_SESSION: self.lifecycle.handle_new_session,
        }
        return handlers

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
