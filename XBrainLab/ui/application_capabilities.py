"""UI helpers for reading backend ApplicationService capabilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from PyQt6.QtCore import QCoreApplication, QThread

from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.commands import Command, CommandName
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.async_command_runner import (
    QtApplicationCommandRunner,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    prepare_interaction_command_callbacks,
)
from XBrainLab.ui.refresh_coordinator import (
    refresh_after_command,
    suppress_observer_refresh_during_command,
)

if TYPE_CHECKING:
    from XBrainLab.backend.application.epoch_context import EpochDialogContext
    from XBrainLab.backend.application.resource_guard import ResourcePreflightResult
    from XBrainLab.backend.application.saliency_render import (
        SaliencyRenderPublication,
        SaliencyRenderRequest,
    )
    from XBrainLab.backend.application.view_publication import (
        ApplicationViewPublication,
        InterpretationReviewIdentity,
    )

_FallbackResult = TypeVar("_FallbackResult")
CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE = (
    "XBrainLab could not safely complete this action from the current window "
    "state. Refresh the workflow and try again."
)


class ControllerCompatibilityUnavailableError(RuntimeError):
    """Raised when product runtime attempts a controller compatibility mutation."""


@dataclass(frozen=True)
class CommandReviewContext:
    """One command capability and the publication generation it came from."""

    capability: CommandCapability
    publication_generation: int


class ApplicationUiRuntime(Protocol):
    """Application command boundary used by UI capability helpers."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        """Execute one command through ApplicationService."""
        ...

    def get_interpretation_review(
        self,
        *,
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> dict[str, Any]:
        """Return the exact pending Data Import review payload."""
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


@dataclass(frozen=True)
class _StudyApplicationUiRuntime:
    """Production adapter from a genuine Study to ApplicationService."""

    study: Study

    def _service(self):
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

    def get_saliency_render(
        self,
        request: SaliencyRenderRequest,
    ) -> SaliencyRenderPublication:
        return self._service().get_saliency_render(request)

    def get_training_resource_preflight(self) -> ResourcePreflightResult | None:
        return self._service().get_training_resource_preflight()

    def request_shutdown_fence(self) -> None:
        self._service().request_shutdown_fence()

    def release_shutdown_fence(self) -> bool:
        return self._service().release_shutdown_fence()

    def wait_for_background_tasks(self, timeout: float | None = None) -> bool:
        return self._service().wait_for_background_tasks(timeout=timeout)


def find_study(context: Any) -> Any | None:
    """Find the nearest Study object from a widget/panel/manager context."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))

        study = getattr(current, "study", None)
        if study is not None:
            return study

        main_window = getattr(current, "main_window", None)
        study = getattr(main_window, "study", None)
        if study is not None:
            return study

        controller = getattr(current, "controller", None)
        study = getattr(controller, "study", None)
        if study is not None:
            return study

        current_attrs = getattr(current, "__dict__", {})
        for attr_name, maybe_controller in current_attrs.items():
            if attr_name == "controller" or not attr_name.endswith("_controller"):
                continue
            study = getattr(maybe_controller, "study", None)
            if study is not None:
                return study

        parent = getattr(current, "parent", None)
        current = parent() if callable(parent) else None

    return None


def application_ui_runtime(context: Any) -> ApplicationUiRuntime | None:
    """Resolve the production UI runtime from a genuine Study context."""
    study = find_study(context)
    if not issubclass(type(study), Study):
        return None
    return _StudyApplicationUiRuntime(cast(Study, study))


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
    return application_runtime.get_view_publication()


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
    """Read one typed epoch-dialog context from one application publication."""
    from XBrainLab.backend.application.epoch_context import (  # noqa: PLC0415
        EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE,
        EpochDialogContext,
        validated_epoch_handoff,
    )
    from XBrainLab.backend.application.state import (  # noqa: PLC0415
        ApplicationStateSnapshot,
        InterpretationStateSnapshot,
    )
    from XBrainLab.backend.application.view_publication import (  # noqa: PLC0415
        ApplicationViewPublication,
    )

    application_runtime = _resolve_application_ui_runtime(context, runtime)
    if application_runtime is None:
        return EpochDialogContext.unavailable()
    try:
        publication = application_runtime.get_view_publication()
    except Exception:
        logger.error("Failed to read epoch dialog publication.", exc_info=True)
        return EpochDialogContext.unavailable()

    if not isinstance(publication, ApplicationViewPublication):
        return EpochDialogContext.unavailable()
    generation = publication.generation
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        return EpochDialogContext.unavailable()
    if (
        not isinstance(publication.verified, bool)
        or not isinstance(publication.stale, bool)
        or not (
            publication.refresh_error is None
            or isinstance(publication.refresh_error, str)
        )
    ):
        return EpochDialogContext.unavailable(publication_generation=generation)

    try:
        capability = publication.effective_capabilities.get(CommandName.CREATE_EPOCH)
    except Exception:
        logger.error("Failed to read epoch capability publication.", exc_info=True)
        return EpochDialogContext.unavailable(publication_generation=generation)
    if not isinstance(capability, CommandCapability):
        return EpochDialogContext.unavailable(publication_generation=generation)

    state = publication.state
    state_read_errors_valid = isinstance(state, ApplicationStateSnapshot) and (
        isinstance(state.read_errors, list)
        and all(isinstance(error, str) for error in state.read_errors)
    )
    publication_usable = (
        publication.usable
        and publication.refresh_error is None
        and isinstance(state, ApplicationStateSnapshot)
        and state_read_errors_valid
        and state.state_reliable is True
        and not state.read_errors
        and isinstance(state.interpretation, InterpretationStateSnapshot)
    )
    if not publication_usable:
        return EpochDialogContext.unavailable(
            reason=(
                publication.public_unavailable_reason
                or EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE
            ),
            capability=capability,
            publication_generation=generation,
        )

    try:
        handoff = validated_epoch_handoff(state.interpretation.epoch_handoff)
    except (TypeError, ValueError):
        logger.error("Published epoch handoff payload is invalid.", exc_info=True)
        return EpochDialogContext.unavailable(
            capability=capability,
            publication_generation=generation,
        )
    return EpochDialogContext(
        capability=capability,
        epoch_handoff=handoff,
        publication_generation=generation,
        usable=True,
        unavailable_reason=None,
    )


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
    with suppress_observer_refresh_during_command(context):
        result = _execute_runtime_command(
            application_runtime,
            command,
            expected_publication_generation=expected_publication_generation,
        )
    if refresh:
        refresh_after_command(context, result)
    return result


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
    """Execute an ApplicationService command through QThreadPool for UI flows.

    The backend command still runs through the same ApplicationService contract,
    but expensive work is offloaded from the GUI thread. Result handling and UI
    refresh are delivered through Qt signals on the receiver thread.

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
        refresh=refresh,
        busy_target=busy_target,
        allow_during_shutdown=allow_during_shutdown,
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

    Product MainWindow wiring injects controllers into panels. This helper keeps
    older tests and standalone contexts working without allowing real Study UI
    components to walk back through the controller tree.
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


def local_result_payload(result) -> dict:
    """Return serializable diagnostics plus process-local UI references."""
    diagnostics = dict(getattr(result, "diagnostics", {}) or {})
    runtime = getattr(result, "runtime", {}) or {}
    if isinstance(runtime, dict):
        diagnostics.update(runtime)
    return diagnostics
