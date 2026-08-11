"""UI helpers for reading backend ApplicationService capabilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import getattr_static
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast
from weakref import ReferenceType, ref

from PyQt6.QtCore import QCoreApplication, QThread

from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.commands import (
    Command,
    CommandName,
    QueryStateCommand,
)
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.async_command_runner import (
    QtApplicationCommandRunner,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    prepare_interaction_command_callbacks,
)

if TYPE_CHECKING:
    from XBrainLab.backend.application.dataset_split_preview import (
        DatasetSplitContext,
        DatasetSplitContextPublication,
        DatasetSplitContextRequest,
        DatasetSplitPreviewPublication,
        DatasetSplitPreviewRequest,
    )
    from XBrainLab.backend.application.epoch_context import EpochDialogContext
    from XBrainLab.backend.application.evaluation_render import (
        EvaluationRenderPublication,
        EvaluationRenderRequest,
    )
    from XBrainLab.backend.application.preprocess_render import (
        PreprocessRenderPublication,
        PreprocessRenderRequest,
    )
    from XBrainLab.backend.application.resource_guard import (
        ResourcePreflightResult,
        TrainingResourcePreviewRequest,
        TrainingResourcePreviewResult,
    )
    from XBrainLab.backend.application.saliency_render import (
        SaliencyRenderPublication,
        SaliencyRenderRequest,
    )
    from XBrainLab.backend.application.training_recommendation import (
        TrainingRecommendation,
    )
    from XBrainLab.backend.application.view_publication import (
        InterpretationReviewIdentity,
    )

_FallbackResult = TypeVar("_FallbackResult")
CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE = (
    "XBrainLab could not safely complete this action from the current window "
    "state. Refresh the workflow and try again."
)
TRAINING_PROGRESS_UPDATED_EVENT = "training_updated"
_PYTHON_OWNED_COMMAND_THREADS: dict[CommandName, str] = {
    CommandName.PREPROCESS: "XBrainLab-preprocess",
    CommandName.TRAIN: "XBrainLab-training-start",
}


class ControllerCompatibilityUnavailableError(RuntimeError):
    """Raised when product runtime attempts a controller compatibility mutation."""


class DatasetSplitQueryPort(Protocol):
    """Narrow detached read/cancellation port used by dataset splitting."""

    def get_dataset_split_context(
        self,
        request: DatasetSplitContextRequest,
    ) -> DatasetSplitContextPublication:
        """Return detached split choices for one application generation."""
        ...

    def get_dataset_split_preview(
        self,
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        """Return detached speculative split rows."""
        ...

    def cancel_dataset_split_preview(self, request_id: str) -> bool:
        """Cancel one application-owned speculative preview."""
        ...


class EvaluationQueryPort(Protocol):
    """Narrow read port used by the Evaluation panel."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def get_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Return a detached Evaluation render publication."""
        ...


class EvaluationActionPort(Protocol):
    """Narrow command port used by the Evaluation panel."""

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Execute one Evaluation query through ApplicationService."""
        ...


class PreprocessQueryPort(Protocol):
    """Narrow detached read port used by the Preprocess panel."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def get_preprocess_render(
        self,
        request: PreprocessRenderRequest,
    ) -> PreprocessRenderPublication:
        """Return one bounded detached signal publication."""
        ...


class ApplicationPublicationSubscriptionPort(Protocol):
    """Narrow subscription port for revisioned application publications."""

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Subscribe to the typed application publication event."""
        ...

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Unsubscribe from the typed application publication event."""
        ...


class ApplicationViewPublicationPort(
    ApplicationPublicationSubscriptionPort,
    Protocol,
):
    """Narrow query/subscription port for committed application publications."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...


class TrainingQueryPort(Protocol):
    """Narrow detached query port used by the Training panel."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def query_training_history(
        self,
        *,
        expected_publication_generation: int,
    ) -> CommandResult:
        """Return detached Training history bound to one publication."""
        ...

    def query_training_state(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Return detached Training configuration state."""
        ...

    def get_training_recommendation(
        self,
        *,
        expected_publication_generation: int | None = None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
    ) -> TrainingRecommendation:
        """Return the backend-owned starting point for Training Setting."""
        ...

    def get_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewResult:
        """Return a detached advisory estimate for unsaved draft settings."""
        ...


class TrainingPublicationPort(ApplicationViewPublicationPort, Protocol):
    """Committed state/capability publication port used by Training."""


class TrainingActionPort(Protocol):
    """Narrow command port used by Training actions."""

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Execute one Training action through ApplicationService."""
        ...


class TrainingTransientProgressPort(Protocol):
    """Notification-only port for non-authoritative live Training progress."""

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Subscribe to the sole transient progress event."""
        ...

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Unsubscribe from the sole transient progress event."""
        ...


class VisualizationQueryPort(Protocol):
    """Narrow read port used by the Visualization panel."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Return one detached saliency render publication."""
        ...


class VisualizationPublicationPort(
    ApplicationViewPublicationPort,
    Protocol,
):
    """Narrow application publication port used by Visualization."""


class VisualizationActionPort(Protocol):
    """Narrow command port used by the Visualization panel."""

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Execute one Visualization query or action through ApplicationService."""
        ...


@dataclass(frozen=True)
class CommandReviewContext:
    """One command capability and the publication generation it came from."""

    capability: CommandCapability
    publication_generation: int


@dataclass(frozen=True)
class DatasetSplitDialogBinding:
    """Detached context and application callbacks required by the split dialog."""

    split_context: DatasetSplitContext
    publication_generation: int
    preview_provider: Callable[
        [DatasetSplitPreviewRequest],
        DatasetSplitPreviewPublication,
    ]
    preview_canceller: Callable[[str], bool]


class ApplicationUiRuntime(
    DatasetSplitQueryPort,
    EvaluationQueryPort,
    EvaluationActionPort,
    PreprocessQueryPort,
    TrainingQueryPort,
    TrainingPublicationPort,
    TrainingActionPort,
    VisualizationQueryPort,
    VisualizationPublicationPort,
    VisualizationActionPort,
    Protocol,
):
    """Application command boundary used by UI capability helpers."""

    def get_interpretation_review(
        self,
        *,
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> dict[str, Any]:
        """Return the exact pending Data Import review payload."""
        ...

    def get_epoch_dialog_context(self) -> EpochDialogContext:
        """Return one detached epoch setup bound to application truth."""
        ...

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        """Return a detached saliency render publication."""
        ...

    def request_shutdown_fence(self) -> None:
        """Close command admission before application shutdown."""
        ...

    def release_shutdown_fence(self) -> bool:
        """Reopen command admission after a cancelled shutdown."""
        ...

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        """Wait for application-owned background work at lifecycle boundaries."""
        ...

    def close(self) -> bool:
        """Release the initialized application runtime after workers are idle."""
        ...


@dataclass(frozen=True)
class _StudyApplicationUiRuntime:
    """Production adapter from a genuine Study to ApplicationService."""

    study: Study
    desktop_host_ref: ReferenceType[Any] | None = None

    def _service(self):
        host = self.desktop_host_ref() if self.desktop_host_ref is not None else None
        ensure_renderer = getattr(
            host,
            "_ensure_application_publication_renderer",
            None,
        )
        if callable(ensure_renderer):
            renderer = ensure_renderer()
            service = getattr(renderer, "service", None)
            if service is not None:
                return service
        if bool(getattr(host, "_closing_in_progress", False)):
            from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
                get_initialized_application_service,
            )

            service = get_initialized_application_service(self.study)
            if service is not None:
                return service
            raise RuntimeError(
                "Application runtime is unavailable while the desktop is closing."
            )
        from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
            get_application_service,
        )

        return get_application_service(self.study)

    def get_view_publication(self) -> ApplicationViewPublication:
        return self._service().get_view_publication()

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        return self._service().execute(
            command,
            expected_publication_generation=expected_publication_generation,
        )

    def get_interpretation_review(
        self,
        *,
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> dict[str, Any]:
        return self._service().get_interpretation_review(
            expected_identity=expected_identity,
        )

    def get_epoch_dialog_context(self) -> EpochDialogContext:
        return self._service().get_epoch_dialog_context()

    def get_dataset_split_context(
        self,
        request: DatasetSplitContextRequest,
    ) -> DatasetSplitContextPublication:
        return self._service().get_dataset_split_context(request)

    def get_dataset_split_preview(
        self,
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        return self._service().get_dataset_split_preview(request)

    def cancel_dataset_split_preview(self, request_id: str) -> bool:
        return self._service().cancel_dataset_split_preview(request_id)

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        return self._service().get_saliency_render(request)

    def get_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        return self._service().get_evaluation_render(request)

    def get_preprocess_render(
        self,
        request: PreprocessRenderRequest,
    ) -> PreprocessRenderPublication:
        return self._service().get_preprocess_render(request)

    def query_training_history(
        self,
        *,
        expected_publication_generation: int,
    ) -> CommandResult:
        return self.execute(
            QueryStateCommand(query="training_history"),
            expected_publication_generation=expected_publication_generation,
        )

    def query_training_state(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        return self.execute(
            QueryStateCommand(query="state"),
            expected_publication_generation=expected_publication_generation,
        )

    def get_training_recommendation(
        self,
        *,
        expected_publication_generation: int | None = None,
        prospective_model_name: str | None = None,
        prospective_model_params: dict[str, Any] | None = None,
    ) -> TrainingRecommendation:
        return self._service().get_training_recommendation(
            expected_publication_generation=expected_publication_generation,
            prospective_model_name=prospective_model_name,
            prospective_model_params=prospective_model_params,
        )

    def get_training_resource_preview(
        self,
        request: TrainingResourcePreviewRequest,
    ) -> TrainingResourcePreviewResult:
        return self._service().get_training_resource_preview(request)

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        from XBrainLab.backend.application.view_publication import (  # noqa: PLC0415
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        )

        if event_name != APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT:
            raise ValueError("UI runtime exposes only application publications.")
        host = self.desktop_host_ref() if self.desktop_host_ref is not None else None
        defer_subscription = getattr(
            host,
            "_defer_application_runtime_subscription",
            None,
        )
        if callable(defer_subscription) and defer_subscription(event_name, callback):
            return
        self._service().subscribe(event_name, callback)

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        from XBrainLab.backend.application.view_publication import (  # noqa: PLC0415
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        )

        if event_name != APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT:
            raise ValueError("UI runtime exposes only application publications.")
        host = self.desktop_host_ref() if self.desktop_host_ref is not None else None
        cancel_deferred = getattr(
            host,
            "_cancel_deferred_application_runtime_subscription",
            None,
        )
        if callable(cancel_deferred) and cancel_deferred(event_name, callback):
            return
        if bool(getattr(host, "_closing_in_progress", False)):
            from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
                get_initialized_application_service,
            )

            service = get_initialized_application_service(self.study)
            if service is None:
                return
            service.unsubscribe(event_name, callback)
            return
        self._service().unsubscribe(event_name, callback)

    def get_training_resource_preflight(self) -> ResourcePreflightResult | None:
        return self._service().get_training_resource_preflight()

    def request_shutdown_fence(self) -> None:
        self._service().request_shutdown_fence()

    def release_shutdown_fence(self) -> bool:
        return self._service().release_shutdown_fence()

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        host = self.desktop_host_ref() if self.desktop_host_ref is not None else None
        if bool(getattr(host, "_closing_in_progress", False)):
            from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
                get_initialized_application_service,
            )

            service = get_initialized_application_service(self.study)
            if service is None:
                return True
            return service.wait_for_background_tasks(timeout=timeout)
        return self._service().wait_for_background_tasks(timeout=timeout)

    def close(self) -> bool:
        from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
            get_initialized_application_service,
        )

        service = get_initialized_application_service(self.study)
        if service is None:
            return True
        service.close()
        return bool(service.is_closed)


@dataclass(frozen=True)
class _StudyTrainingTransientUiPort:
    """Production adapter exposing only Training's transient progress tick."""

    study: Study

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name != TRAINING_PROGRESS_UPDATED_EVENT:
            raise ValueError("Training transient port exposes only progress updates.")
        self.study.training_state_service.subscribe(event_name, callback)

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name != TRAINING_PROGRESS_UPDATED_EVENT:
            raise ValueError("Training transient port exposes only progress updates.")
        self.study.training_state_service.unsubscribe(event_name, callback)


def _declared_context_attribute(context: Any, name: str) -> Any | None:
    """Read only attributes genuinely declared by a context or its type.

    Dynamic proxies such as ``MagicMock`` manufacture arbitrary attributes and
    parent chains on access. Treating those values as product ownership can
    loop forever or silently bind the wrong runtime.
    """
    if context is None:
        return None
    try:
        getattr_static(context, name)
    except AttributeError:
        return None
    try:
        return getattr(context, name)
    except Exception:
        return None


def _declared_parent(context: Any) -> Any | None:
    parent = _declared_context_attribute(context, "parent")
    if not callable(parent):
        return None
    try:
        return parent()
    except Exception:
        return None


def find_study(context: Any) -> Any | None:
    """Find the nearest Study object from a widget/panel/manager context."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))

        study = _declared_context_attribute(current, "study")
        if study is not None:
            return study

        main_window = _declared_context_attribute(current, "main_window")
        study = _declared_context_attribute(main_window, "study")
        if study is not None:
            return study

        controller = _declared_context_attribute(current, "controller")
        study = _declared_context_attribute(controller, "study")
        if study is not None:
            return study

        current_attrs = getattr(current, "__dict__", {})
        for attr_name, maybe_controller in current_attrs.items():
            if attr_name == "controller" or not attr_name.endswith("_controller"):
                continue
            study = _declared_context_attribute(maybe_controller, "study")
            if study is not None:
                return study

        current = _declared_parent(current)

    return None


def application_ui_runtime(context: Any) -> ApplicationUiRuntime | None:
    """Resolve the production UI runtime from a genuine Study context."""
    study = find_study(context)
    if not issubclass(type(study), Study):
        return None
    desktop_host = _find_desktop_runtime_host(context)
    return _StudyApplicationUiRuntime(
        cast(Study, study),
        ref(desktop_host) if desktop_host is not None else None,
    )


def _find_desktop_runtime_host(context: Any) -> Any | None:
    """Find the MainWindow-like owner that binds visible publication delivery."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if _owns_desktop_publication_renderer(current):
            return current
        main_window = _declared_context_attribute(current, "main_window")
        if _owns_desktop_publication_renderer(main_window):
            return main_window
        current = _declared_parent(current)
    return None


def _owns_desktop_publication_renderer(candidate: Any) -> bool:
    """Reject dynamic mock attributes when locating the real desktop owner."""
    if candidate is None:
        return False
    try:
        ensure_renderer = getattr_static(
            candidate,
            "_ensure_application_publication_renderer",
        )
    except AttributeError:
        return False
    return callable(ensure_renderer)


def training_transient_ui_port(
    context: Any,
) -> TrainingTransientProgressPort | None:
    """Resolve the notification-only Training progress adapter."""
    study = find_study(context)
    if not issubclass(type(study), Study):
        return None
    return _StudyTrainingTransientUiPort(cast(Study, study))


def _resolve_application_ui_runtime(
    context: Any,
    runtime: ApplicationUiRuntime | None,
) -> ApplicationUiRuntime | None:
    return runtime if runtime is not None else application_ui_runtime(context)


def has_real_application_context(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Return whether a UI context has an explicit application runtime."""
    return _resolve_application_ui_runtime(context, runtime) is not None


def is_application_runtime_deferred(context: Any) -> bool:
    """Return whether first paint intentionally precedes command-runtime startup."""
    study = find_study(context)
    if not issubclass(type(study), Study):
        return False
    main_window = getattr(context, "main_window", None)
    host = main_window if main_window is not None else context
    return bool(
        getattr(host, "_defer_initial_application_runtime", False)
        and not application_runtime_initialized(context)
    )


def application_runtime_initialized(context: Any) -> bool:
    """Read command-runtime readiness without constructing the service."""
    study = find_study(context)
    if not issubclass(type(study), Study):
        return False
    from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
        application_service_initialized,
    )

    return application_service_initialized(cast(Study, study))


def get_application_view_publication(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> ApplicationViewPublication | None:
    """Read one full state/capability publication for an atomic UI render."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    try:
        publication = application_runtime.get_view_publication()
    except Exception:
        logger.error("Application publication is unavailable.", exc_info=True)
        return None
    if not isinstance(publication, ApplicationViewPublication):
        logger.error("Application runtime returned an invalid view publication.")
        return None
    if (
        isinstance(publication.generation, bool)
        or not isinstance(publication.generation, int)
        or publication.generation < 1
        or isinstance(publication.revision, bool)
        or not isinstance(publication.revision, int)
        or publication.revision < 1
    ):
        logger.error("Application runtime returned an invalid publication identity.")
        return None
    return publication


def get_command_capability(
    context: Any,
    command_name: CommandName | str,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> CommandCapability | None:
    """Read one command capability from the shared ApplicationService policy."""
    publication = get_application_view_publication(context, runtime=runtime)
    if publication is None:
        return None
    return publication.effective_capabilities.get(command_name)


def get_command_review_context(
    context: Any,
    command_name: CommandName | str,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> CommandReviewContext | None:
    """Bind a reviewed command capability to one immutable publication."""
    publication = get_application_view_publication(context, runtime=runtime)
    if publication is None:
        return None
    return CommandReviewContext(
        capability=publication.effective_capabilities.get(command_name),
        publication_generation=publication.generation,
    )


def get_interpretation_review(
    context: Any,
    *,
    expected_identity: InterpretationReviewIdentity | None = None,
    runtime: ApplicationUiRuntime | None = None,
) -> dict[str, Any]:
    """Return the current review through the production ApplicationService."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        raise ControllerCompatibilityUnavailableError(
            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
        )
    return application_runtime.get_interpretation_review(
        expected_identity=expected_identity,
    )


def get_epoch_dialog_context(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> EpochDialogContext:
    """Read one typed, detached epoch-dialog context through ApplicationService."""
    from XBrainLab.backend.application.epoch_context import (  # noqa: PLC0415
        EpochDialogContext,
    )

    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return EpochDialogContext.unavailable()
    try:
        dialog_context = application_runtime.get_epoch_dialog_context()
    except Exception:
        logger.error("Failed to read detached epoch dialog context.", exc_info=True)
        return EpochDialogContext.unavailable()
    if not isinstance(dialog_context, EpochDialogContext):
        logger.error("Application runtime returned an invalid epoch dialog context.")
        return EpochDialogContext.unavailable()
    return dialog_context


def get_training_resource_preflight(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> ResourcePreflightResult | None:
    """Read the current training resource preflight through ApplicationService."""
    from XBrainLab.backend.application.resource_guard import (  # noqa: PLC0415
        ResourcePreflightResult,
    )

    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    getter = getattr(application_runtime, "get_training_resource_preflight", None)
    if not callable(getter):
        return None
    try:
        result = getter()
    except Exception:
        logger.error("Training resource preflight failed.", exc_info=True)
        return None
    return result if isinstance(result, ResourcePreflightResult) else None


def get_saliency_render_publication(
    context: Any,
    request: SaliencyRenderRequest,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> SaliencyRenderPublication | None:
    """Read one detached visualization payload through ApplicationService."""
    from XBrainLab.backend.application.saliency_render import (  # noqa: PLC0415
        SaliencyRenderPublication,
        SaliencyRenderRequest,
    )

    if not isinstance(request, SaliencyRenderRequest):
        raise TypeError("request must be a SaliencyRenderRequest")
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    publication = application_runtime.get_saliency_render(request)
    if not isinstance(publication, SaliencyRenderPublication):
        raise TypeError("Application runtime returned an invalid saliency render")
    return publication


def get_evaluation_render_publication(
    context: Any,
    request: EvaluationRenderRequest,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> EvaluationRenderPublication | None:
    """Read one detached Evaluation payload through ApplicationService."""
    from XBrainLab.backend.application.evaluation_render import (  # noqa: PLC0415
        EvaluationRenderPublication,
        EvaluationRenderRequest,
    )

    if not isinstance(request, EvaluationRenderRequest):
        raise TypeError("request must be an EvaluationRenderRequest")
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    publication = application_runtime.get_evaluation_render(request)
    if not isinstance(publication, EvaluationRenderPublication):
        raise TypeError("Application runtime returned an invalid Evaluation render")
    return publication


def get_preprocess_render_publication(
    context: Any,
    request: PreprocessRenderRequest,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> PreprocessRenderPublication | None:
    """Read one bounded detached signal payload through ApplicationService."""
    from XBrainLab.backend.application.preprocess_render import (  # noqa: PLC0415
        PreprocessRenderPublication,
        PreprocessRenderRequest,
    )

    if not isinstance(request, PreprocessRenderRequest):
        raise TypeError("request must be a PreprocessRenderRequest")
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    publication = application_runtime.get_preprocess_render(request)
    if not isinstance(publication, PreprocessRenderPublication):
        raise TypeError("Application runtime returned an invalid Preprocess render")
    return publication


def get_dataset_split_dialog_binding(
    context: Any,
    *,
    publication_generation: int,
    runtime: ApplicationUiRuntime | None = None,
) -> DatasetSplitDialogBinding | None:
    """Bind detached split context and preview callbacks to one generation."""
    from XBrainLab.backend.application.dataset_split_preview import (  # noqa: PLC0415
        DatasetSplitContextPublication,
        DatasetSplitContextRequest,
    )

    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None

    request = DatasetSplitContextRequest(
        publication_generation=publication_generation,
    )
    publication = application_runtime.get_dataset_split_context(request)
    if not isinstance(publication, DatasetSplitContextPublication):
        raise TypeError("Application runtime returned an invalid dataset split context")
    if (
        publication.request != request
        or publication.generation != publication_generation
    ):
        raise ValueError("Dataset split context does not match the reviewed generation")

    return DatasetSplitDialogBinding(
        split_context=publication.context,
        publication_generation=publication.generation,
        preview_provider=application_runtime.get_dataset_split_preview,
        preview_canceller=application_runtime.cancel_dataset_split_preview,
    )


def blocked_reason(capability: CommandCapability | None, fallback: str) -> str:
    """Format a capability block reason for UI warnings/tooltips."""
    if capability is None:
        return fallback
    if capability.reasons:
        return "\n".join(capability.reasons)
    return fallback


def is_stale_publication_result(result: Any) -> bool:
    """Return whether a command was rejected before its handler for stale review."""
    diagnostics = getattr(result, "diagnostics", None)
    return (
        isinstance(diagnostics, dict) and diagnostics.get("stale_publication") is True
    )


def _execute_runtime_command(
    runtime: ApplicationUiRuntime,
    command: Command,
    *,
    expected_publication_generation: int | None,
) -> CommandResult:
    if expected_publication_generation is None:
        return runtime.execute(command)
    return runtime.execute(
        command,
        expected_publication_generation=expected_publication_generation,
    )


def execute_application_command(
    context: Any,
    command: Command,
    *,
    refresh: bool = True,
    expected_publication_generation: int | None = None,
    runtime: ApplicationUiRuntime | None = None,
) -> CommandResult | None:
    """Execute an ApplicationService command for real Study-backed UI paths.

    Returns ``None`` when the caller has no production or explicitly supplied
    application runtime. Product UI callers should treat that as blocked for
    state-changing commands; read-only compatibility adapters are separate.
    """
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return None
    # State-changing UI render is owned by the revisioned application
    # publication. Keep ``refresh`` as a compatibility call-site parameter, but
    # never turn a command result into a second product refresh truth.
    del refresh
    return _execute_runtime_command(
        application_runtime,
        command,
        expected_publication_generation=expected_publication_generation,
    )


def request_application_shutdown_fence(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Close command admission immediately without waiting for the command lock."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return False
    application_runtime.request_shutdown_fence()
    return True


def release_application_shutdown_fence(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Reopen command admission immediately after a cancelled close attempt."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return False
    released = application_runtime.release_shutdown_fence()
    return released is not False


def application_background_tasks_idle(
    context: Any,
    *,
    timeout: float | None = 0.0,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Observe application-owned worker completion without blocking the GUI."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return True
    waiter = getattr(application_runtime, "wait_for_background_tasks", None)
    if not callable(waiter):
        return True
    try:
        return bool(waiter(timeout=timeout))
    except Exception:
        logger.exception("Could not verify application background task shutdown")
        return False


def close_application_runtime(
    context: Any,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Close the existing application runtime without constructing a new one."""
    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return True
    closer = getattr(application_runtime, "close", None)
    if not callable(closer):
        return True
    try:
        return bool(closer())
    except Exception:
        logger.exception("Could not finalize the application runtime")
        return False


def execute_application_command_async(
    context: Any,
    command: Command,
    *,
    on_result: Callable[[CommandResult], InteractionOutcome | None],
    on_error: Callable[[tuple], None] | None = None,
    refresh: bool = True,
    busy_target: Any | None = None,
    allow_during_shutdown: bool = False,
    expected_publication_generation: int | None = None,
    runtime: ApplicationUiRuntime | None = None,
) -> bool:
    """Execute an ApplicationService command outside the GUI thread.

    The backend command still runs through the same ApplicationService contract,
    but expensive work is offloaded from the GUI thread. Native-heavy preprocess
    and training-admission commands use a Python-owned thread; other commands
    retain the Qt worker pool.
    Result handling and UI refresh are delivered through Qt signals on the receiver
    thread.

    Returns ``False`` when no application runtime is available so callers can show
    an explicit blocked state or use an intentional read-only compatibility adapter.
    """
    application = QCoreApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        logger.error(
            "Async UI command %s must be dispatched from the GUI thread.",
            command.name,
        )
        return False

    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return False

    completion_callbacks = prepare_interaction_command_callbacks(
        context=context,
        command_name=command.name.value,
        on_result=on_result,
        on_error=on_error,
    )
    started = QtApplicationCommandRunner(
        context=context,
        command=command,
        execute=lambda: _execute_runtime_command(
            application_runtime,
            command,
            expected_publication_generation=expected_publication_generation,
        ),
        on_result=completion_callbacks.on_result,
        on_error=completion_callbacks.on_error,
        on_finished=completion_callbacks.on_finished,
        # Application publications own state-changing render. Command results
        # are still delivered to the interaction callback for user feedback.
        refresh=False,
        busy_target=busy_target,
        allow_during_shutdown=allow_during_shutdown,
        python_thread_name=_PYTHON_OWNED_COMMAND_THREADS.get(command.name),
    ).start()
    completion_callbacks.mark_started(started)
    return started


def run_controller_compatibility_call(
    context: Any,
    fallback: Callable[[], _FallbackResult],
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> _FallbackResult:
    """Run controller fallback only when no application runtime is available."""
    if _resolve_application_ui_runtime(context, runtime) is None:
        return fallback()
    raise ControllerCompatibilityUnavailableError(
        CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    )


def get_controller_for_compatibility_context(
    context: Any,
    study: Any,
    controller_name: str,
    *,
    runtime: ApplicationUiRuntime | None = None,
) -> Any | None:
    """Return a controller only for explicit compatibility UI contexts.

    Migrated Product MainWindow wiring injects typed application ports. This
    helper keeps older tests and standalone contexts working without allowing
    real Study UI components to walk back through the controller tree.
    """
    getter = getattr(study, "get_controller", None)
    if not callable(getter):
        return None
    try:
        return run_controller_compatibility_call(
            context,
            lambda: getter(controller_name),
            runtime=runtime,
        )
    except ControllerCompatibilityUnavailableError:
        return None
