"""Application service coordinating backend commands, policy, and state."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from threading import Lock, RLock
from time import monotonic
from typing import Any

from XBrainLab.backend.controller.training_controller import TrainingLifecycleEvent
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger

from .application_publication_lifecycle import ApplicationPublicationLifecycle
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
    EvaluateCommand,
    GenerateDatasetCommand,
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
    PreconditionError,
    map_exception,
)
from .lifecycle_service import LifecycleCommandService
from .pipeline_stage import pipeline_stage_readiness_summary
from .pipeline_transaction import PipelineStateTransaction
from .post_training_saliency import (
    PostTrainingSaliencyAutomation,
    SaliencyTerminalNotification,
)
from .preprocess_service import PreprocessCommandService
from .query_state_service import QueryStateCommandService
from .resource_guard import ResourcePreflightResult
from .results import ChangedState, CommandResult, CommandStatus, ErrorType
from .saliency_coverage import SaliencyCoverageProjector
from .saliency_render import (
    SaliencyRenderPublication,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
)
from .state import ApplicationStateSnapshot, ErrorSnapshot
from .state_read_models import EvaluationStateReadModel, TrainingStateReadModel
from .state_service import StateSnapshotService
from .training_configuration_reset import TrainingConfigurationResetService
from .training_publication_lifecycle import (
    SaliencyTerminalDeliveryPlan,
)
from .training_runtime import StudyTrainingRuntime, TrainingRuntimePort
from .training_snapshot import (
    model_name as snapshot_model_name,
)
from .training_snapshot import (
    model_params_snapshot as build_model_params_snapshot,
)
from .training_snapshot import (
    training_option_snapshot as build_training_option_snapshot,
)
from .view_publication import (
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
_TRAINING_RESTART_SAFETY_WAIT_SECONDS = 2.0


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
        dataset: Any,
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
        dataset: Any,
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
    ) -> None:
        self.study = study
        self.training = training
        self.has_trainer = has_trainer
        self.pipeline_transaction = pipeline_transaction
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
            )
        return self._service_instance

    def dataset_split_summary(self, datasets: list[Any]) -> dict[str, Any]:
        if not datasets:
            return {}
        return self._service().dataset_split_summary(datasets)

    def handle_generate_dataset(self, command: Command) -> HandlerResult:
        return self._service().handle_generate_dataset(command)

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
    ) -> None:
        self.training = training
        self.training_runtime = training_runtime
        self._get_state = get_state
        self._configuration_reset = configuration_reset
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .training_service import TrainingCommandService  # noqa: PLC0415

            self._service_instance = TrainingCommandService(
                training=self.training,
                training_runtime=self.training_runtime,
                get_state=self._get_state,
            )
        return self._service_instance

    def clear_configuration(self) -> None:
        self._configuration_reset.clear()

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

    def complete_synchronous_training(self) -> tuple[str, dict[str, Any]]:
        return self._service().complete_synchronous_training()

    def handle_stop_training(self, command: Command) -> HandlerResult:
        return self._service().handle_stop_training(command)

    def handle_clear_training_history(self, command: Command) -> HandlerResult:
        return self._service().handle_clear_training_history(command)


class _LazyAnalysisCommandService:
    """Defer NumPy/visualization analysis service until analysis commands run."""

    def __init__(
        self,
        *,
        evaluation: Any,
        visualization: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.evaluation = evaluation
        self.visualization = visualization
        self._get_state = get_state
        self._service_instance: Any | None = None

    def _service(self) -> Any:
        if self._service_instance is None:
            from .analysis_service import AnalysisCommandService  # noqa: PLC0415

            self._service_instance = AnalysisCommandService(
                evaluation=self.evaluation,
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


class ApplicationService:
    """Command-oriented application layer over the existing backend controllers."""

    def __init__(self, study: Study | None = None) -> None:
        target_study = study if study is not None else Study()
        command_lock = getattr(target_study, "_application_command_lock", RLock())
        self._initialize_components(target_study, command_lock)

    def _initialize_components(self, study: Study, command_lock: RLock) -> None:
        self.study = study
        self._command_lock = command_lock
        self.training_runtime = StudyTrainingRuntime(self.study)
        self.dataset = DatasetControllerAdapter(self.study)
        self.preprocess = PreprocessControllerAdapter(self.study)
        self.training = TrainingControllerAdapter(self.study)
        self.evaluation = EvaluationControllerAdapter(self.study)
        self.visualization = VisualizationControllerAdapter(self.study)
        self.training_state = TrainingStateReadModel(self.training_runtime)
        self.evaluation_state = EvaluationStateReadModel(self.training_runtime)
        self._last_error: ErrorSnapshot | None = None
        self._command_admission_lock = Lock()
        self._synchronous_training_lifecycle_lock = Lock()
        self._shutdown_fenced = False
        self._shutdown_fence_generation = 0
        self._closing = False
        self._closed = False
        self._mutation_in_progress = False
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
        self.data_table = DataTableCommandService(dataset=self.dataset)
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
        )
        self.training_configuration_reset = TrainingConfigurationResetService(
            training=self.training,
            training_runtime=self.training_runtime,
        )
        self.training_commands = _LazyTrainingCommandService(
            training=self.training,
            training_runtime=self.training_runtime,
            get_state=self.get_state,
            configuration_reset=self.training_configuration_reset,
        )
        self.saliency_coverage_projector = SaliencyCoverageProjector()
        self.state_snapshot = StateSnapshotService(
            study=self.study,
            dataset=self.dataset,
            preprocess=self.preprocess,
            training=self.training,
            training_runtime=self.training_runtime,
            training_state=self.training_state,
            evaluation=self.evaluation,
            evaluation_state=self.evaluation_state,
            visualization=self.visualization,
            dataset_generation=self.dataset_generation,
            training_commands=self.training_commands,
            interpretation=self.interpretation,
            saliency_coverage_projector=self.saliency_coverage_projector,
        )
        initial_training_boundary = self.state_snapshot.capture_training_read_boundary()
        initial_state = self.state_snapshot.build(last_error=self._last_error)
        final_initial_training_boundary = (
            self.state_snapshot.capture_training_read_boundary()
        )
        self._view_coordinator = ApplicationViewCoordinator(
            initial_state,
            initial_training_boundary=final_initial_training_boundary,
            build_state=lambda: self.state_snapshot.build(last_error=self._last_error),
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
        )
        if (
            initial_training_boundary != final_initial_training_boundary
            or not final_initial_training_boundary.stable
        ):
            self._view_coordinator.mark_stale(
                "Training state changed during application initialization."
            )
        self.publication_lifecycle = ApplicationPublicationLifecycle(
            training=self.training,
            training_runtime=self.training_runtime,
            visualization=self.visualization,
            state_snapshot=self.state_snapshot,
            command_lock=self._command_lock,
            command_admission_lock=self._command_admission_lock,
            is_closed=lambda: self._closed,
            is_mutation_in_progress=lambda: self._mutation_in_progress,
            is_shutdown_fenced=lambda: self._shutdown_fenced,
            refresh_training_publication=self._refresh_training_publication_strict,
            committed_view_publication=self._committed_view_publication,
        )
        self.training_publications = self.publication_lifecycle.coordinator
        self.saliency_render = SaliencyRenderPublisher(
            training_runtime=self.training_runtime,
            get_publication=self._committed_view_publication,
            capture_training_boundary=(
                self.state_snapshot.capture_training_read_boundary
            ),
        )
        self.query_state_commands = QueryStateCommandService(
            study=self.study,
            dataset=self.dataset,
            state_builder=self.state_snapshot,
            get_state=self.get_state,
        )
        self.analysis = _LazyAnalysisCommandService(
            evaluation=self.evaluation,
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
        self._command_handlers = self._build_command_handlers()

    @property
    def _observer_finalizer(self) -> Callable[[], Any]:
        """Compatibility view of publication observer cleanup ownership."""
        return self.publication_lifecycle.observer_finalizer

    @_observer_finalizer.setter
    def _observer_finalizer(self, cleanup: Callable[[], Any]) -> None:
        self.publication_lifecycle.observer_finalizer = cleanup

    @property
    def _saliency_notification_boundary(self) -> Any:
        """Compatibility view of the coordinator-owned delivery boundary."""
        return self.publication_lifecycle.saliency_notification_boundary

    def close(self) -> None:
        """Idempotently detach lifecycle observers and release runtime ownership."""
        from .runtime import begin_application_service_close  # noqa: PLC0415

        if not begin_application_service_close(
            self.study,
            self,
            self._begin_close,
        ):
            return
        try:
            self.post_training_saliency.cancel()
        except Exception:
            logger.debug(
                "Could not cancel post-training saliency automation during close",
                exc_info=True,
            )
        self.publication_lifecycle.close()

    def _begin_close(self) -> bool:
        """Linearize close after active commands without waiting on callbacks."""
        with self._command_admission_lock:
            if self._closed or self._closing:
                return False
            self._closing = True
            self._shutdown_fenced = True
            self._shutdown_fence_generation += 1
        try:
            self.training.cancel_terminal_notification_waits(
                "Application service is closing."
            )
        except Exception:
            logger.debug(
                "Could not cancel training terminal handoff waits during close",
                exc_info=True,
            )
        with (
            self._synchronous_training_lifecycle_lock,
            self._command_lock,
            self._command_admission_lock,
        ):
            if self._closed:
                return False
            self._closed = True
            self._closing = False
            return True

    def _closed_command_result(self, command: Command | Any) -> CommandResult:
        """Return a stable rejection without rebuilding closed backend state."""
        publication = self._committed_view_publication()
        try:
            name = command_name(command).value
        except Exception:
            name = command.__class__.__name__
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
            },
        )

    def _closed_command_result_if_any(
        self,
        command: Command | Any,
    ) -> CommandResult | None:
        """Check command admission against the service lifetime boundary."""
        with self._command_admission_lock:
            if not self._closed:
                return None
            return self._closed_command_result(command)

    def _ensure_open(self) -> None:
        """Reject direct API reads after this service released ownership."""
        with self._command_admission_lock:
            if self._closed:
                raise RuntimeError(_CLOSED_SERVICE_MESSAGE)

    def _discard_pending_saliency_terminal(self) -> None:
        """Explicitly abandon terminal UI delivery during permanent close."""
        self.publication_lifecycle.coordinator.discard_pending()

    def dispose(self) -> None:
        """Compatibility alias for explicit ApplicationService cleanup."""
        self.close()

    def _publish_training_live_state(self, *_args: Any, **_kwargs: Any) -> None:
        """Compatibility delegate for focused lifecycle tests."""
        self.publication_lifecycle.publish_training_live_state(*_args, **_kwargs)

    def _publish_training_terminal_state(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> bool:
        """Compatibility delegate for headless waits and focused tests."""
        return self.publication_lifecycle.publish_training_terminal_state(
            *_args,
            **_kwargs,
        )

    def _deliver_training_terminal_publication(
        self,
        lifecycle_event: TrainingLifecycleEvent,
    ) -> bool:
        """Compatibility delegate for terminal acknowledgement tests."""
        return self.publication_lifecycle.deliver_training_terminal_publication(
            lifecycle_event
        )

    def _terminal_training_publication_event(
        self,
        state: ApplicationStateSnapshot,
    ) -> TrainingLifecycleEvent | None:
        """Compatibility delegate for exact terminal generation tests."""
        return self.publication_lifecycle.terminal_training_publication_event(state)

    def _publish_post_training_saliency_terminal_state(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Compatibility delegate for terminal saliency observer tests."""
        return self.publication_lifecycle.publish_post_training_saliency_terminal_state(
            status
        )

    def _commit_post_training_saliency_terminal_state(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Compatibility delegate for command-boundary saliency delivery."""
        return self.publication_lifecycle.commit_post_training_saliency_terminal_state(
            status
        )

    def _remember_pending_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Compatibility delegate for shutdown reconciliation call sites."""
        self.publication_lifecycle.remember_pending_saliency_terminal(status)

    def _pending_saliency_terminal(self) -> PostTrainingSaliencyStatus | None:
        """Return coordinator-owned terminal identity awaiting delivery."""
        return self.publication_lifecycle.pending_saliency_terminal()

    def _clear_pending_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Discard one exact coordinator-owned delivery obligation."""
        self.publication_lifecycle.clear_pending_saliency_terminal(status)

    def _reconcile_pending_saliency_terminal(
        self,
        *,
        allow_shutdown_fenced: bool = False,
        blocking: bool = True,
    ) -> bool:
        """Compatibility delegate for retained terminal saliency work."""
        return self.publication_lifecycle.reconcile_pending_saliency_terminal(
            allow_shutdown_fenced=allow_shutdown_fenced,
            blocking=blocking,
        )

    def _plan_saliency_terminal_delivery(
        self,
        notification: SaliencyTerminalNotification,
    ) -> SaliencyTerminalDeliveryPlan:
        """Compatibility delegate for delivery policy tests."""
        return self.publication_lifecycle.plan_saliency_terminal_delivery(notification)

    def _notify_saliency_publication_changed(
        self,
        notification: SaliencyTerminalNotification | None = None,
    ) -> bool:
        """Compatibility delegate for visualization notification tests."""
        return self.publication_lifecycle.notify_saliency_publication_changed(
            notification
        )

    def _visualization_batch_generation(self) -> int | None:
        """Compatibility delegate for command-batch diagnostics."""
        return self.publication_lifecycle.visualization_batch_generation()

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
        """Arm post-training work only for a training command that can start."""
        append = command.append if isinstance(command, TrainCommand) else True
        self.post_training_saliency.arm(append=append)
        try:
            return self.training_commands.handle_train(
                command,
                defer_synchronous_completion=bool(
                    isinstance(command, TrainCommand) and not command.interactive
                ),
            )
        except Exception:
            self.post_training_saliency.cancel()
            raise

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
                self._reconcile_pending_saliency_terminal()
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
            return self._refresh_training_publication_opportunistic()
        finally:
            self._command_lock.release()

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Return one detached render DTO guarded by publication/training identity."""
        self._ensure_open()
        return self.saliency_render.publish(request)

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
        terminal_reconciled = self._publish_training_terminal_state()
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
        return terminal_reconciled or self._publish_training_terminal_state()

    def _committed_view_publication(self) -> ApplicationViewPublication:
        """Copy the internal publication without exposing mutable nested values."""
        return self._view_coordinator.committed()

    def query_published_state(self) -> CommandResult:
        """Return a safe UI read model without waiting for an active mutation."""
        closed = self._closed_command_result_if_any(QueryStateCommand(query="state"))
        if closed is not None:
            return closed
        publication = self._committed_view_publication()
        if not publication.usable and self._pending_saliency_terminal() is not None:
            self._reconcile_pending_saliency_terminal(blocking=False)
            publication = self._committed_view_publication()
        diagnostics = {
            "state": publication.state.to_dict(),
            "capabilities": publication.effective_capabilities.to_dict(),
            "publication_generation": publication.generation,
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
            return self._execute_at_command_boundary(
                command,
                expected_publication_generation=expected_publication_generation,
            )
        visualization_notifications = (
            self.visualization.batch_notifications()
            if isinstance(command, SaliencyCommand)
            else nullcontext()
        )
        manager_notifications = self.training_runtime.defer_saliency_terminal(
            self._commit_post_training_saliency_terminal_state
        )
        visualization_batch_generation: int | None = None
        with (
            self.training_publications.capture_saliency_notifications(),
            visualization_notifications,
            manager_notifications,
        ):
            if isinstance(command, SaliencyCommand):
                visualization_batch_generation = self._visualization_batch_generation()
            result = self._execute_at_command_boundary(
                command,
                expected_publication_generation=expected_publication_generation,
            )
        return self._retry_failed_manual_saliency_delivery(
            command,
            result,
            visualization_batch_generation,
        )

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
    ) -> CommandResult:
        """Execute a command and return a result envelope."""
        closed = self._closed_command_result_if_any(command)
        if closed is not None:
            return closed
        if self._is_published_state_query(command):
            return self.query_published_state()
        if isinstance(command, QueryStateCommand):
            return self._execute_query_without_wait(command)

        train_command = command if isinstance(command, TrainCommand) else None
        synchronous_train = train_command is not None and not train_command.interactive
        lifecycle_boundary = (
            self._synchronous_training_lifecycle_lock
            if train_command is not None
            else nullcontext()
        )
        with lifecycle_boundary:
            if (
                train_command is not None
                and not self.training.is_training()
                and not self.training.wait_until_restart_safe(
                    timeout=_TRAINING_RESTART_SAFETY_WAIT_SECONDS,
                )
            ):
                return self._training_restart_pending_result()
            result = self._execute_with_command_lock(
                command,
                expected_publication_generation=expected_publication_generation,
            )
            if (
                synchronous_train
                and result.ok
                and result.diagnostics.get("synchronous_completion_deferred") is True
            ):
                result = self._complete_deferred_synchronous_training(result)

            if not self._closed:
                try:
                    self.training_publications.retry_training_terminal_delivery()
                except Exception:
                    logger.exception(
                        "Could not retry retained terminal training publication"
                    )
            if synchronous_train and result.ok:
                generation = self._training_handoff_generation(result)
                if generation is None:
                    return self._background_delivery_failure(
                        result,
                        reason=(
                            "Training completed, but its terminal handoff identity "
                            "was unavailable."
                        ),
                        invalid_handoff=True,
                    )
                if not self.wait_for_background_tasks(
                    training_handoff_generation=generation
                ):
                    return self._background_delivery_failure(
                        result,
                        reason=(
                            "Training completed, but its final application updates "
                            "could not be delivered. Retry after the application "
                            "becomes idle."
                        ),
                    )
            return result

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

    @staticmethod
    def _training_handoff_generation(result: CommandResult) -> int | None:
        """Read one exact controller handoff identity from a command result."""
        generation = result.diagnostics.get("training_handoff_generation")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            return None
        return generation

    @staticmethod
    def _background_delivery_failure(
        result: CommandResult,
        *,
        reason: str,
        invalid_handoff: bool = False,
    ) -> CommandResult:
        """Turn an unverified synchronous terminal handoff into a safe failure."""
        diagnostics = dict(result.diagnostics)
        diagnostics["background_delivery_incomplete"] = True
        if invalid_handoff:
            diagnostics["training_handoff_generation_invalid"] = True
        return replace(
            result,
            status=CommandStatus.FAILED,
            message=reason,
            error_type=ErrorType.INTERNAL,
            recoverable=True,
            error_message=reason,
            diagnostics=diagnostics,
        )

    def _execute_with_command_lock(
        self,
        command: Command | Any,
        *,
        expected_publication_generation: int | None,
    ) -> CommandResult:
        """Serialize command admission and its immediate backend mutation."""
        with self._command_lock:
            with self._command_admission_lock:
                closed = self._closed
                rejected_by_shutdown = self._shutdown_fenced and not isinstance(
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
        return result

    def _complete_deferred_synchronous_training(
        self,
        started: CommandResult,
    ) -> CommandResult:
        """Wait outside the command lock, then verify one terminal run under it."""
        completion_error: Exception | None = None
        try:
            if not self.training_runtime.wait_for_training_completion():
                completion_error = ApplicationError(
                    message="Training completion could not be verified.",
                    error_type=ErrorType.TRAINING,
                    recoverable=True,
                    diagnostics={"training_failed": True},
                )
        except Exception as exc:
            completion_error = exc

        with self._command_lock:
            before_publication = self._committed_view_publication()
            try:
                self._raise_completion_error(completion_error)
                message, completion_diagnostics = (
                    self.training_commands.complete_synchronous_training()
                )
                self._last_error = None
                after, refresh_error = self._state_after_command()
                if refresh_error is not None or not after.state_reliable:
                    verification_error = refresh_error or RuntimeError(
                        "; ".join(after.read_errors)
                        or "updated application state is unreliable",
                    )
                    completed = self._post_state_verification_failure_result(
                        name=CommandName.TRAIN,
                        state=after,
                        diagnostics=completion_diagnostics,
                        error=verification_error,
                    )
                else:
                    completed = CommandResult.success_result(
                        command_name=CommandName.TRAIN.value,
                        message=message,
                        state=after,
                        changed_state=self._changed_state(started.state, after),
                        diagnostics=completion_diagnostics,
                    )
            except Exception as exc:
                completed = self._handler_failure_result(
                    CommandName.TRAIN,
                    started.state,
                    before_publication,
                    exc,
                )

        diagnostics = dict(started.diagnostics)
        diagnostics.pop("synchronous_completion_deferred", None)
        return replace(
            completed,
            changed_state=self._merge_changed_state(
                started.changed_state,
                completed.changed_state,
            ),
            diagnostics={**diagnostics, **completed.diagnostics},
        )

    @staticmethod
    def _raise_completion_error(error: Exception | None) -> None:
        """Re-enter the normal command failure mapping after an unlocked wait."""
        if error is not None:
            raise error

    @staticmethod
    def _merge_changed_state(
        first: ChangedState,
        second: ChangedState,
    ) -> ChangedState:
        """Union state deltas produced by start and terminal publication phases."""
        return ChangedState(
            raw_changed=first.raw_changed or second.raw_changed,
            preprocessed_changed=(
                first.preprocessed_changed or second.preprocessed_changed
            ),
            epoch_changed=first.epoch_changed or second.epoch_changed,
            datasets_changed=first.datasets_changed or second.datasets_changed,
            training_changed=first.training_changed or second.training_changed,
            evaluation_changed=first.evaluation_changed or second.evaluation_changed,
            visualization_changed=(
                first.visualization_changed or second.visualization_changed
            ),
            interpretation_changed=(
                first.interpretation_changed or second.interpretation_changed
            ),
            error_changed=first.error_changed or second.error_changed,
            state_unknown=first.state_unknown or second.state_unknown,
        )

    def _expected_publication_rejection(
        self,
        command: Command | Any,
        expected_generation: int,
    ) -> CommandResult | None:
        """Reject a generation-bound mutation against any other committed view."""
        if (
            isinstance(expected_generation, bool)
            or not isinstance(expected_generation, int)
            or expected_generation < 0
        ):
            raise ValueError(
                "Expected publication generation must be a non-negative integer."
            )
        publication = self._committed_view_publication()
        if publication.usable and publication.generation == expected_generation:
            return None
        try:
            name = command_name(command).value
        except Exception:
            name = command.__class__.__name__
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

    def _execute_query_without_wait(self, command: QueryStateCommand) -> CommandResult:
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
                },
            )
        try:
            with self._command_admission_lock:
                if self._closed:
                    return self._closed_command_result(command)
            return self._execute_serialized(command)
        finally:
            self._command_lock.release()

    def request_shutdown_fence(self) -> None:
        """Atomically reject new mutations without waiting for command execution."""
        with (
            self.training_publications.capture_saliency_notifications(),
            self.training_runtime.defer_saliency_terminal(),
        ):
            with self._command_admission_lock:
                self._shutdown_fenced = True
                self._shutdown_fence_generation += 1
            try:
                self.post_training_saliency.cancel()
                self.training_runtime.cancel_saliency_job()
            except Exception:
                logger.exception("Could not cancel background saliency during shutdown")

    def release_shutdown_fence(self) -> bool:
        """Reopen admission and reconcile state hidden by the shutdown fence."""
        publication_changed = False
        terminal_status: PostTrainingSaliencyStatus | None = None
        release_generation = -1
        try:
            with self._command_lock, self._command_admission_lock:
                if self._closed or self._closing:
                    return False
                if not self._shutdown_fenced:
                    return True
                release_generation = self._shutdown_fence_generation
                before = self._committed_view_publication()
                refreshed_state = self._refresh_training_publication_strict()
                after = self._committed_view_publication()
                if (
                    not refreshed_state.state_reliable
                    or not after.usable
                    or after.refresh_error is not None
                    or after.state != refreshed_state
                ):
                    return False
                before_visualization = before.state.visualization
                after_visualization = after.state.visualization
                publication_changed = (
                    before_visualization.post_training_saliency
                    != after_visualization.post_training_saliency
                    or before_visualization.saliency_coverage
                    != after_visualization.saliency_coverage
                )
                if publication_changed:
                    status = after.state.visualization.post_training_saliency
                    if status.phase.terminal:
                        terminal_status = status
        except Exception:
            logger.exception(
                "Could not reconcile application state after shutdown was cancelled"
            )
            terminal_status = self._terminal_saliency_release_obligation()
            if terminal_status is not None:
                self._remember_pending_saliency_terminal(terminal_status)
            return False
        terminal_status = (
            self._terminal_saliency_release_obligation() or terminal_status
        )
        try:
            with self.training_publications.capture_saliency_notifications():
                if terminal_status is not None:
                    self._remember_pending_saliency_terminal(terminal_status)
                self._reconcile_pending_saliency_terminal(
                    allow_shutdown_fenced=True,
                )
        except Exception:
            logger.exception(
                "Could not queue terminal saliency while releasing shutdown fence"
            )
            return False
        if self._pending_saliency_terminal() is not None:
            return False
        if (
            publication_changed
            and terminal_status is None
            and not self._notify_saliency_publication_changed()
        ):
            return False
        publication = self._committed_view_publication()
        if (
            not publication.usable
            or publication.refresh_error is not None
            or not self._runtime_saliency_terminal_delivery_committed()
        ):
            return False
        return self._complete_shutdown_fence_release(release_generation)

    def _terminal_saliency_release_obligation(
        self,
    ) -> PostTrainingSaliencyStatus | None:
        """Return current manager truth that still lacks public acknowledgement."""
        status = self.training_runtime.saliency_status()
        if not status.phase.terminal:
            return None
        visualization_state = self._committed_view_publication().state.visualization
        publication_status = visualization_state.post_training_saliency
        if publication_status.generation > status.generation:
            return None
        if self.training_publications.has_delivered_saliency_generation(
            status.generation
        ):
            return None
        return status

    def _runtime_saliency_terminal_delivery_committed(self) -> bool:
        """Require runtime queue acknowledgement before reopening admission."""
        delivery = self.training_runtime.saliency_delivery_state()
        if (
            delivery.pending_generations
            and delivery.active_generation is None
            and not delivery.retry_owner_active
        ):
            self.training_runtime.retry_saliency_delivery()
            delivery = self.training_runtime.saliency_delivery_state()
        if delivery.pending_generations or delivery.active_generation is not None:
            return False
        status = self.training_runtime.saliency_status()
        if not status.phase.terminal:
            return True
        if delivery.delivered_generation < status.generation:
            return False
        return self.training_publications.has_delivered_saliency_generation(
            status.generation
        )

    def _complete_shutdown_fence_release(self, expected_generation: int) -> bool:
        """Clear only the exact fence whose reconciliation just committed."""
        with self._command_admission_lock:
            if self._closed or self._closing:
                return False
            if not self._shutdown_fenced:
                return True
            if self._shutdown_fence_generation != expected_generation:
                return False
            self._shutdown_fenced = False
            return True

    def _shutdown_fence_rejection(self, command: Command | Any) -> CommandResult:
        """Return a structured rejection for commands denied at admission time."""
        try:
            name = command_name(command).value
        except Exception:
            name = command.__class__.__name__
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
    ) -> CommandResult:
        """Map one handler failure and fail closed when post-state is uncertain."""
        app_error = map_exception(exc)
        failure_diagnostics = {
            **app_error.diagnostics,
            "exception_type": exc.__class__.__name__,
            "handler_error_type": app_error.error_type.value,
            "handler_error_message": app_error.message,
            "handler_error_recoverable": app_error.recoverable,
        }
        if name is CommandName.QUERY_STATE:
            return CommandResult.failure_result(
                command_name=name.value,
                message=app_error.message,
                state=before,
                changed_state=ChangedState(),
                error_type=app_error.error_type,
                recoverable=app_error.recoverable,
                error_message=app_error.message,
                diagnostics={
                    **failure_diagnostics,
                    "read_only_query": True,
                    "publication_generation": before_publication.generation,
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
                    message=app_error.message,
                    state=after,
                    changed_state=ChangedState(),
                    error_type=app_error.error_type,
                    recoverable=app_error.recoverable,
                    error_message=app_error.message,
                    diagnostics={
                        **failure_diagnostics,
                        "control_flow_outcome": True,
                        "state_preserved": True,
                        "publication_generation": before_publication.generation,
                    },
                )
        self._last_error = ErrorSnapshot(
            error_type=app_error.error_type.value,
            message=app_error.message,
            recoverable=app_error.recoverable,
        )
        after, refresh_error = self._state_after_command()
        if refresh_error is not None:
            failure_diagnostics.update(
                {
                    "state_refresh_error": str(refresh_error),
                    "state_refresh_exception_type": refresh_error.__class__.__name__,
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
            if app_error.message not in read_errors:
                read_errors.append(app_error.message)
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
            message=app_error.message,
            state=after,
            changed_state=changed_state,
            error_type=app_error.error_type,
            recoverable=app_error.recoverable,
            error_message=app_error.message,
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
                "state_refresh_error": str(error),
                "state_refresh_exception_type": error.__class__.__name__,
                "command_effect_may_have_applied": True,
            },
        )

    def _state_fallback(self, exc: Exception) -> ApplicationStateSnapshot:
        message = f"state snapshot unavailable: {exc}"
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
            changed_state=ChangedState(error_changed=True, state_unknown=True),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            error_message=message,
            diagnostics={
                "exception_type": exc.__class__.__name__,
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
        message = app_error.message or (
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
                "publication_usable": publication.usable,
                "exception_type": exc.__class__.__name__,
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
            CommandName.GENERATE_DATASET: (
                self.dataset_generation.handle_generate_dataset
            ),
            CommandName.CLEAR_DATASETS: self.dataset_generation.handle_clear_datasets,
            CommandName.CONFIGURE_TRAINING: (
                self.training_commands.handle_configure_training
            ),
            CommandName.TRAIN: self._handle_train_with_automation,
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

    def attach_labels(self, mapping: dict[str, str]) -> CommandResult:
        """Execute an attach-labels command."""
        return self.execute(
            AttachLabelsCommand(
                mapping=mapping,
                label_paths=list(dict.fromkeys(mapping.values())),
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
        with self._command_admission_lock:
            shutdown_fenced = self._shutdown_fenced
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
            message=str(exc),
            recoverable=True,
        )
        after, refresh_error = self._state_after_command()
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
