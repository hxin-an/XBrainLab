"""Ownership boundary for the in-app assistant runtime lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from itertools import count
from typing import Any, Protocol, cast

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal, pyqtSlot

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.utils.logger import logger
from XBrainLab.chat_contract import (
    MAX_CHAT_MESSAGE_CONTENT_LENGTH,
    bounded_chat_string,
)
from XBrainLab.llm.agent.confirmation import AgentConfirmationResolution
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnScope,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.turn_scope import resolve_assistant_turn_scope
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffResolution
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchResolution,
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionFailure,
)
from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)
from XBrainLab.ui.components.assistant_command_dispatcher import (
    AssistantCommandDispatcher,
)
from XBrainLab.ui.components.assistant_runtime_coordinator import (
    AssistantRuntimeCoordinator,
)


class _RuntimeDispatcher(Protocol):
    """Command dispatcher contract owned by the runtime lifecycle."""

    def bind(self, controller: object) -> None: ...

    def initialize(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool: ...

    def submit(self, request: AssistantTurnRequest) -> bool: ...

    def stop(self) -> bool: ...

    def set_model(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool: ...

    def reset(self) -> bool: ...

    def confirm(self, resolution: AgentConfirmationResolution) -> bool: ...

    def resolve_ui_handoff(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool: ...

    def debug(self, request: AssistantDebugToolRequest) -> bool: ...

    def close(self) -> bool: ...


class RuntimeSetupAction(str, Enum):
    """Next UI action after a local-runtime first-run choice."""

    CONTINUE = "continue"
    OPEN_SETTINGS = "open_settings"
    STOP = "stop"


@dataclass(frozen=True)
class RuntimeSetupOutcome:
    """Result of applying one persisted first-run runtime choice."""

    action: RuntimeSetupAction
    message: str = ""


class RuntimeActivationStatus(str, Enum):
    """Result of reconciling saved settings with the active runtime."""

    STARTED = "started"
    ALREADY_READY = "already_ready"
    SWITCHING = "switching"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class AssistantRuntimeLifecycleState(str, Enum):
    """Admission and cleanup state for the assistant runtime owner."""

    OPEN = "open"
    DEACTIVATING = "deactivating"
    CLOSING = "closing"
    CLEANUP_PENDING = "cleanup_pending"
    CLOSED = "closed"


class RuntimeCommandAdmissionStatus(str, Enum):
    """Whether one runtime command entered the owned dispatcher."""

    ACCEPTED = "accepted"
    BUSY = "busy"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RuntimeCommandAdmissionResult:
    """Typed command-admission result consumed by the UI adapter."""

    command_name: str
    status: RuntimeCommandAdmissionStatus
    message: str = ""
    turn_id: int | None = None
    generation: int | None = None
    scope: AssistantTurnScope | None = None
    terminal_command: str | None = None
    excluded_commands: tuple[CommandName, ...] = ()

    def __post_init__(self) -> None:
        if self.scope is not None and not isinstance(self.scope, AssistantTurnScope):
            raise TypeError("Runtime admission scope must be typed.")
        if self.terminal_command is not None and not isinstance(
            self.terminal_command,
            str,
        ):
            raise TypeError("Runtime admission terminal command must be a string.")
        if not isinstance(self.excluded_commands, tuple) or any(
            not isinstance(command, CommandName) for command in self.excluded_commands
        ):
            raise TypeError("Runtime admission excluded commands must be typed.")

    @property
    def accepted(self) -> bool:
        return self.status is RuntimeCommandAdmissionStatus.ACCEPTED

    @property
    def correlation(self) -> AssistantTurnCorrelation | None:
        if self.turn_id is None or self.generation is None:
            return None
        return AssistantTurnCorrelation(
            generation=self.generation,
            turn_id=self.turn_id,
        )


@dataclass(frozen=True)
class AssistantRuntimeActivationRequest(AssistantRuntimeLaunchSpec):
    """Launch spec tagged with the lifecycle request allowed to finish it."""

    activation_id: int

    @classmethod
    def from_launch_spec(
        cls,
        launch_spec: AssistantRuntimeLaunchSpec,
        *,
        activation_id: int,
    ) -> AssistantRuntimeActivationRequest:
        return cls(
            backend=launch_spec.backend,
            requested_backend_id=launch_spec.requested_backend_id,
            requested_model_id=launch_spec.requested_model_id,
            model_id=launch_spec.model_id,
            outcome=launch_spec.outcome,
            selection_detail=launch_spec.selection_detail,
            settings=launch_spec.settings,
            device_fallback_reason=launch_spec.device_fallback_reason,
            activation_id=activation_id,
        )


@dataclass(frozen=True)
class RuntimeActivationResult:
    """Observable activation result for the UI adapter."""

    status: RuntimeActivationStatus
    message: str = ""
    model_id: str = ""
    launch_spec: AssistantRuntimeLaunchSpec | None = None
    failure: AssistantRuntimeSelectionFailure | None = None
    activation_id: int | None = None

    def __post_init__(self) -> None:
        if self.launch_spec is None:
            return
        if self.model_id and self.model_id != self.launch_spec.model_id:
            raise ValueError("Activation model must match its immutable launch spec.")
        object.__setattr__(self, "model_id", self.launch_spec.model_id)
        request_id = getattr(self.launch_spec, "activation_id", None)
        if request_id is not None:
            object.__setattr__(self, "activation_id", int(request_id))

    @property
    def available(self) -> bool:
        return self.status not in {
            RuntimeActivationStatus.BUSY,
            RuntimeActivationStatus.UNAVAILABLE,
        }

    @property
    def fallback_used(self) -> bool:
        return bool(self.launch_spec and self.launch_spec.fallback_used)


class AssistantRuntimeLifecycle(QObject):
    """Own config readiness, controller startup, dispatch, state, and shutdown.

    The object deliberately has no knowledge of chat bubbles, dock widgets, or
    application panels. ``AgentManager`` owns those UI concerns and connects to
    ``controller_created`` and ``runtime_snapshot_changed`` exactly once.
    """

    controller_created = pyqtSignal(object)
    runtime_snapshot_changed = pyqtSignal(object)
    turn_finished = pyqtSignal(object)
    cleanup_finished = pyqtSignal(bool, str)
    deactivation_finished = pyqtSignal(bool, str)
    _terminal_handoff_delivery_failed = pyqtSignal(object)
    _CLOSED_MESSAGE = "Assistant runtime is closed. Restart XBrainLab to use it."
    _START_FAILURE_MESSAGE = (
        "The local assistant could not start. Open assistant settings to check "
        "the installed model and runtime."
    )
    _ACTIVATION_TIMEOUT_MESSAGE = (
        "Local assistant activation timed out. Retry the model or check the local "
        "runtime settings."
    )
    _SHUTTING_DOWN_MESSAGE = "Assistant runtime is shutting down."
    _DEACTIVATING_MESSAGE = "Assistant runtime is being disabled."
    _CLEANUP_PENDING_MESSAGE = (
        "Assistant shutdown is still finishing. Restart XBrainLab before using "
        "the assistant again."
    )
    _LOADING_MESSAGE = (
        "Assistant runtime is loading and cannot accept requests yet. Wait until "
        "the assistant is ready."
    )
    _IDLE_MESSAGE = (
        "Assistant runtime is not ready. Open assistant settings and start the "
        "local runtime before sending a request."
    )
    _BUSY_MESSAGE = (
        "The assistant is still processing the previous request. Use Stop or "
        "wait for the current response before sending again."
    )
    _DELIVERY_FAILURE_MESSAGE = (
        "The assistant could not accept this request. Restart the assistant "
        "runtime and try again."
    )
    DEFAULT_ACTIVATION_TIMEOUT_MS = 180_000
    DEFAULT_TURN_DELIVERY_TIMEOUT_MS = 5_000

    def __init__(
        self,
        study: object,
        *,
        controller_factory: Callable[[object], object],
        dispatcher: _RuntimeDispatcher | None = None,
        dispatcher_factory: Callable[[], _RuntimeDispatcher] | None = None,
        config_loader: Callable[[], LLMConfig] | None = None,
        resolver: AssistantRuntimeLaunchResolver | None = None,
        activation_timeout_ms: int = DEFAULT_ACTIVATION_TIMEOUT_MS,
        turn_delivery_timeout_ms: int = DEFAULT_TURN_DELIVERY_TIMEOUT_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._study = study
        self._controller_factory = controller_factory
        self._dispatcher_factory = dispatcher_factory
        self._dispatcher_cleanup_signal: Any | None = None
        self._dispatcher_delivery_signal: Any | None = None
        self._dispatcher: _RuntimeDispatcher
        if dispatcher is None:
            self._dispatcher_factory = dispatcher_factory or (
                lambda: AssistantCommandDispatcher(self)
            )
            self._dispatcher = self._dispatcher_factory()
        else:
            self._dispatcher = dispatcher
        self._connect_dispatcher_cleanup_signal()
        self._connect_dispatcher_delivery_signal()
        self._config_loader = config_loader or self._default_config_loader
        self._resolver = resolver or AssistantRuntimeLaunchResolver()
        self._coordinator = AssistantRuntimeCoordinator(
            self.runtime_snapshot_changed.emit,
        )
        self._controller: object | None = None
        self._initialized = False
        self._state = AssistantRuntimeLifecycleState.OPEN
        self._startup_cleanup_via_dispatcher: bool | None = None
        self._activation_ids = count(1)
        self._turn_ids = count(1)
        self._standalone_ui_generations = count(1)
        self._activation_timeout_ms = max(1, int(activation_timeout_ms))
        self._activation_watchdog: QTimer | None = None
        self._watchdog_activation_id: int | None = None
        self._turn_delivery_timeout_ms = max(1, int(turn_delivery_timeout_ms))
        self._turn_delivery_watchdog: QTimer | None = None
        self._delivery_watchdog_correlation: AssistantTurnCorrelation | None = None
        self._last_activation_request: AssistantRuntimeActivationRequest | None = None
        self._active_turn: AssistantTurnCorrelation | None = None
        self._last_released_turn: AssistantTurnCorrelation | None = None
        self._stop_requested_for: AssistantTurnCorrelation | None = None
        self._delivery_timeout_for: AssistantTurnCorrelation | None = None
        self._close_requested = False
        self._deactivation_requested = False
        self._deactivation_config: LLMConfig | None = None
        self._controller_lifecycle_connections: tuple[tuple[Any, Any], ...] = ()
        self._terminal_handoff_fallback_bound = False

    @property
    def controller(self) -> object | None:
        return self._controller

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def state(self) -> AssistantRuntimeLifecycleState:
        return self._state

    @property
    def accepts_commands(self) -> bool:
        """Return the single product-level command readiness decision."""
        return bool(
            self._lifecycle_is_open
            and self._controller is not None
            and self._initialized
            and self.current.phase is AssistantRuntimePhase.READY
            and self.current.initialized
        )

    @property
    def turn_in_flight(self) -> bool:
        """Return whether this owner has admitted a non-terminal user turn."""
        return self._active_turn is not None

    @property
    def _lifecycle_is_open(self) -> bool:
        return self._state is AssistantRuntimeLifecycleState.OPEN

    @property
    def _owns_command_transport(self) -> bool:
        return bool(
            self._lifecycle_is_open
            and self._controller is not None
            and self._initialized
        )

    @property
    def current(self) -> AssistantRuntimeSnapshot:
        return self._coordinator.current

    @property
    def expected_activation_id(self) -> int | None:
        return self._coordinator.expected_activation_id

    @property
    def dispatcher(self) -> AssistantCommandDispatcher:
        """Expose diagnostics without transferring dispatcher ownership."""
        return cast(AssistantCommandDispatcher, self._dispatcher)

    @staticmethod
    def _default_config_loader() -> LLMConfig:
        return LLMConfig.load_from_file() or LLMConfig()

    def _connect_dispatcher_cleanup_signal(self) -> None:
        """Observe optional asynchronous cleanup without widening test doubles."""
        signal = getattr(self._dispatcher, "cleanup_finished", None)
        if signal is None or not callable(getattr(signal, "connect", None)):
            self._dispatcher_cleanup_signal = None
            return
        signal.connect(self._on_dispatcher_cleanup_finished)
        self._dispatcher_cleanup_signal = signal

    def _connect_dispatcher_delivery_signal(self) -> None:
        """Observe typed completion of optionally queued turn delivery."""
        signal = getattr(self._dispatcher, "turn_delivery_acknowledged", None)
        if signal is None or not callable(getattr(signal, "connect", None)):
            self._dispatcher_delivery_signal = None
            return
        signal.connect(self._on_turn_delivery_acknowledged)
        self._dispatcher_delivery_signal = signal

    def _replace_dispatcher(self, dispatcher: _RuntimeDispatcher) -> None:
        cleanup_signal = self._dispatcher_cleanup_signal
        if cleanup_signal is not None:
            with suppress(RuntimeError, TypeError):
                cleanup_signal.disconnect(self._on_dispatcher_cleanup_finished)
        delivery_signal = self._dispatcher_delivery_signal
        if delivery_signal is not None:
            with suppress(RuntimeError, TypeError):
                delivery_signal.disconnect(self._on_turn_delivery_acknowledged)
        self._dispatcher = dispatcher
        self._connect_dispatcher_cleanup_signal()
        self._connect_dispatcher_delivery_signal()

    @pyqtSlot(bool, str)
    def _on_dispatcher_cleanup_finished(self, ok: bool, message: str) -> None:
        """Resolve asynchronous ownership for shutdown or startup rollback."""
        if self._state is AssistantRuntimeLifecycleState.CLOSED:
            return
        detail = str(message or "")
        if not ok:
            controller = self._controller
            if self._deactivation_requested:
                self._deactivation_requested = False
                self._deactivation_config = None
                self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
                self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
                self.deactivation_finished.emit(
                    False,
                    detail or "Assistant could not be disabled safely.",
                )
                return
            if self._close_requested and bool(
                getattr(controller, "shutdown_in_progress", False)
            ):
                self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
                self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
                return
            self.cleanup_finished.emit(False, detail)
            return

        if self._close_requested:
            self._complete_close()
        elif self._deactivation_requested:
            self._complete_deactivation()
        elif (
            self._state is AssistantRuntimeLifecycleState.CLEANUP_PENDING
            and self._startup_cleanup_via_dispatcher is True
        ):
            self._controller = None
            self._startup_cleanup_via_dispatcher = None
            self._state = AssistantRuntimeLifecycleState.OPEN
            if self._dispatcher_factory is not None:
                self._replace_dispatcher(self._dispatcher_factory())
            self._coordinator.clear_active_runtime(self._START_FAILURE_MESSAGE)
        self.cleanup_finished.emit(True, detail)

    def load_config(self) -> LLMConfig:
        """Load the persisted runtime configuration through one owner."""
        return self._config_loader()

    @staticmethod
    def needs_first_run(config: LLMConfig) -> bool:
        """Return whether local-runtime consent is required before startup."""
        if not hasattr(config, "model_name"):
            return False
        return (
            str(getattr(config, "inference_mode", "")).strip().lower() == "local"
            and bool(getattr(config, "local_model_enabled", True))
            and not bool(
                getattr(config, "local_runtime_notice_acknowledged", False),
            )
        )

    @staticmethod
    def _application_model_override() -> str | None:
        """Read the transient CLI model override at the resolver-owner boundary."""
        app = QCoreApplication.instance()
        if app is None:
            return None
        value = app.property("model_override")
        normalized = str(value or "").strip()
        return normalized or None

    def _resolve_launch(
        self,
        config: LLMConfig,
        *,
        requested_model_id: str | None = None,
    ) -> AssistantRuntimeLaunchResolution:
        model_id = requested_model_id
        if model_id is None:
            model_id = self._application_model_override()
        return self._resolver.resolve(
            config,
            requested_model_id=model_id,
        )

    @staticmethod
    def _unavailable_result(
        failure: AssistantRuntimeSelectionFailure,
    ) -> RuntimeActivationResult:
        return RuntimeActivationResult(
            RuntimeActivationStatus.UNAVAILABLE,
            message=failure.message,
            failure=failure,
        )

    @staticmethod
    def apply_first_run_choice(
        config: LLMConfig,
        choice: str,
    ) -> RuntimeSetupOutcome:
        """Persist one first-run choice and return the required UI action."""
        normalized = str(choice or "").strip()
        if normalized in {"enable", "use_existing_cache"}:
            config.local_model_enabled = True
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            return RuntimeSetupOutcome(RuntimeSetupAction.CONTINUE)

        if normalized == "download":
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            return RuntimeSetupOutcome(RuntimeSetupAction.OPEN_SETTINGS)

        if normalized == "disable":
            config.local_model_enabled = False
            config.local_runtime_notice_acknowledged = True
            config.save_to_file()
            return RuntimeSetupOutcome(
                RuntimeSetupAction.STOP,
                "Assistant is disabled. Open assistant settings when you want "
                "to enable it.",
            )

        return RuntimeSetupOutcome(
            RuntimeSetupAction.STOP,
            "Assistant setup was deferred. Open assistant settings when you are "
            "ready to continue.",
        )

    def activate(
        self,
        config: LLMConfig,
    ) -> RuntimeActivationResult:
        """Start or reconcile the active controller with persisted settings."""
        if not self._lifecycle_is_open:
            message = self._admission_failure_message()
            self.mark_unavailable(message)
            return RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message=message,
            )
        resolution = self._resolve_launch(config)
        if resolution.failure is not None:
            failure = resolution.failure
            self._stop_activation_watchdog()
            self._coordinator.mark_unavailable(
                redact_public_text(failure.message),
                request_context=AssistantRuntimeSnapshot(
                    phase=AssistantRuntimePhase.FAILED,
                    initialized=False,
                    backend_mode=failure.requested_backend_id,
                    requested_model_id=failure.requested_model_id,
                    selection_detail=failure.message,
                ),
            )
            return self._unavailable_result(failure)
        launch_spec = resolution.launch_spec
        if launch_spec is None:  # pragma: no cover - resolution invariant
            raise RuntimeError("Assistant runtime resolution returned no outcome.")

        if not self._initialized or self._controller is None:
            if not self.start(launch_spec=launch_spec):
                message = self.current.error or self._START_FAILURE_MESSAGE
                return RuntimeActivationResult(
                    RuntimeActivationStatus.UNAVAILABLE,
                    message=message,
                    launch_spec=self._last_activation_request,
                )
            activation_request = self._last_activation_request
            if activation_request is None:  # pragma: no cover - start invariant
                raise RuntimeError("Assistant startup did not register activation.")
            return RuntimeActivationResult(
                RuntimeActivationStatus.STARTED,
                message=activation_request.selection_detail,
                launch_spec=activation_request,
            )

        if (
            self.current.initialized
            and self.current.backend_mode == launch_spec.backend_mode
            and self.current.model_id == launch_spec.model_id
        ):
            self._coordinator.restore_active_runtime()
            return RuntimeActivationResult(
                RuntimeActivationStatus.ALREADY_READY,
                message=launch_spec.selection_detail,
                launch_spec=launch_spec,
            )

        if self.turn_in_flight:
            return self._busy_activation_result()
        return self._queue_model_switch(launch_spec)

    def activate_persisted(self) -> RuntimeActivationResult:
        return self.activate(self.load_config())

    @staticmethod
    def _require_delivery(delivered: object, command_name: str) -> None:
        """Raise when a startup command did not report explicit delivery."""
        if delivered is not True:
            raise RuntimeError(
                f"Assistant {command_name} command delivery was rejected."
            )

    def start(
        self,
        *,
        launch_spec: AssistantRuntimeLaunchSpec | None = None,
    ) -> bool:
        """Create, publish, bind, and initialize the controller exactly once."""
        if self._initialized:
            return True
        if not self._lifecycle_is_open:
            self.mark_unavailable(self._admission_failure_message())
            return False
        if self._startup_cleanup_via_dispatcher is not None:
            self.mark_unavailable(
                "The previous assistant startup did not finish shutting down. "
                "Restart XBrainLab before trying to start the assistant again."
            )
            return False

        if launch_spec is None:
            resolution = self._resolve_launch(self.load_config())
            if resolution.failure is not None:
                self.mark_unavailable(resolution.failure.message)
                return False
            launch_spec = resolution.launch_spec
        if launch_spec is None:  # pragma: no cover - resolution invariant
            raise RuntimeError("Assistant runtime resolution returned no launch spec.")

        activation_request = self._new_activation_request(launch_spec)
        self._begin_activation(activation_request)
        controller: object | None = None
        dispatcher_bound = False
        try:
            controller = self._controller_factory(self._study)
            self._bind_controller_lifecycle_signals(controller)

            self._dispatcher.bind(controller)
            dispatcher_bound = True
            self._require_delivery(
                self._dispatcher.initialize(activation_request),
                "initialization",
            )
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="start",
            )
            self._rollback_failed_start(
                controller,
                dispatcher_bound=dispatcher_bound,
            )
            return False

        self._controller = controller
        self._initialized = True
        self.controller_created.emit(controller)
        return True

    def _bind_controller_lifecycle_signals(self, controller: object) -> None:
        """Bind the required runtime-state and turn-terminal signal contract."""
        bindings = (
            ("runtime_state_changed", self.accept_runtime_snapshot),
            ("turn_finished", self._release_turn),
        )
        resolved: list[tuple[Any, Any]] = []
        for signal_name, slot in bindings:
            signal = getattr(controller, signal_name, None)
            if signal is None or not callable(getattr(signal, "connect", None)):
                raise TypeError(
                    "Assistant controller is missing required lifecycle signal "
                    f"'{signal_name}'."
                )
            resolved.append((signal, slot))
        shutdown_signal = getattr(controller, "shutdown_finished", None)
        if shutdown_signal is not None and callable(
            getattr(shutdown_signal, "connect", None)
        ):
            resolved.append((shutdown_signal, self._on_controller_shutdown_finished))
        terminal_handler = getattr(
            controller,
            "on_workflow_ui_handoff_resolved",
            None,
        )
        if callable(terminal_handler):
            resolved.append((self._terminal_handoff_delivery_failed, terminal_handler))

        connected: list[tuple[Any, Any]] = []
        try:
            for signal, slot in resolved:
                signal.connect(slot)
                connected.append((signal, slot))
        except Exception:
            for signal, slot in connected:
                with suppress(RuntimeError, TypeError):
                    signal.disconnect(slot)
            raise
        self._controller_lifecycle_connections = tuple(connected)
        self._terminal_handoff_fallback_bound = callable(terminal_handler)

    @pyqtSlot(bool, str)
    def _on_controller_shutdown_finished(self, ok: bool, message: str) -> None:
        """Resume transport cleanup after controller workers become terminal."""
        if (
            not self._close_requested
            or self._state is AssistantRuntimeLifecycleState.CLOSED
        ):
            return
        detail = redact_public_text(message or "")
        if not ok:
            self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
            self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
            self.cleanup_finished.emit(False, detail)
            return
        try:
            closed = bool(self._dispatcher.close())
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="dispatcher_cleanup_after_controller_shutdown",
            )
            self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
            self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
            self.cleanup_finished.emit(
                False,
                "Assistant transport cleanup did not finish.",
            )
            return
        if closed:
            self._complete_close()
            self.cleanup_finished.emit(True, detail)

    def _disconnect_controller_lifecycle_signals(self) -> None:
        for signal, slot in self._controller_lifecycle_connections:
            with suppress(RuntimeError, TypeError):
                signal.disconnect(slot)
        self._controller_lifecycle_connections = ()
        self._terminal_handoff_fallback_bound = False

    def _release_turn(self, payload: object) -> None:
        """Release only the turn named by a typed terminal acknowledgement."""
        if not isinstance(payload, AssistantTurnTerminal):
            logger.error(
                "Ignored untyped assistant turn terminal: %s",
                redact_public_text(payload),
            )
            return
        if payload.correlation != self._active_turn:
            logger.warning(
                "Ignored stale assistant terminal for %s; active turn is %s",
                redact_public_text(payload.correlation),
                self._active_turn,
            )
            return
        terminal = payload
        if (
            self._delivery_timeout_for == payload.correlation
            and payload.outcome == "cancelled"
        ):
            terminal = AssistantTurnTerminal(
                correlation=payload.correlation,
                outcome="delivery_timeout",
            )
        self._stop_turn_delivery_watchdog(payload.correlation)
        self._last_released_turn = payload.correlation
        self._active_turn = None
        self._stop_requested_for = None
        self._delivery_timeout_for = None
        self.turn_finished.emit(terminal)

    @pyqtSlot(object)
    def _on_turn_delivery_acknowledged(self, payload: object) -> None:
        """Terminate only the active lease when queued controller delivery fails."""
        if not isinstance(payload, AssistantTurnDeliveryAcknowledgement):
            logger.error("Ignored untyped assistant turn delivery acknowledgement.")
            return
        if payload.correlation != self._active_turn:
            if payload.correlation == self._last_released_turn:
                return
            logger.warning(
                "Ignored stale assistant turn delivery for %s; active turn is %s",
                redact_public_text(payload.correlation),
                self._active_turn,
            )
            return
        self._stop_turn_delivery_watchdog(payload.correlation)
        if payload.phase is AssistantTurnDeliveryPhase.ACCEPTED:
            return
        if payload.message:
            logger.error(
                "Assistant turn %s delivery %s: %s",
                redact_public_text(payload.correlation.turn_id),
                redact_public_text(payload.phase.value),
                redact_public_text(payload.message),
            )
        self._release_turn(
            AssistantTurnTerminal(
                correlation=payload.correlation,
                outcome=f"delivery_{payload.phase.value}",
            )
        )

    def _arm_turn_delivery_watchdog(
        self,
        correlation: AssistantTurnCorrelation,
    ) -> None:
        """Bound queued delivery to a terminal acknowledgement deadline."""
        if self._dispatcher_delivery_signal is None:
            return
        self._stop_turn_delivery_watchdog()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(self._turn_delivery_timeout_ms)
        timer.timeout.connect(
            lambda owned=correlation: self._on_turn_delivery_timeout(owned)
        )
        self._turn_delivery_watchdog = timer
        self._delivery_watchdog_correlation = correlation
        timer.start()

    def _stop_turn_delivery_watchdog(
        self,
        correlation: AssistantTurnCorrelation | None = None,
    ) -> None:
        """Cancel only the watchdog that owns the named turn."""
        owned = self._delivery_watchdog_correlation
        if correlation is not None and owned != correlation:
            return
        timer = self._turn_delivery_watchdog
        self._turn_delivery_watchdog = None
        self._delivery_watchdog_correlation = None
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _on_turn_delivery_timeout(
        self,
        correlation: AssistantTurnCorrelation,
    ) -> None:
        """Fence retries until the unacknowledged turn reaches a typed terminal."""
        if (
            correlation != self._active_turn
            or correlation != self._delivery_watchdog_correlation
        ):
            return
        self._stop_turn_delivery_watchdog(correlation)
        logger.error(
            "Assistant turn %s delivery acknowledgement timed out",
            correlation.turn_id,
        )
        self._delivery_timeout_for = correlation
        try:
            admission = self.stop_generation()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="stop_after_delivery_timeout",
            )
        else:
            if not admission.accepted:
                logger.error(
                    "Assistant controller did not accept stop after delivery timeout "
                    "for turn %s",
                    correlation.turn_id,
                )

    def _clear_active_turn(
        self,
        correlation: AssistantTurnCorrelation | None = None,
    ) -> None:
        """Release an owner-side lease when transport never admitted the request."""
        if correlation is None or correlation == self._active_turn:
            self._stop_turn_delivery_watchdog(correlation)
            self._active_turn = None
            self._stop_requested_for = None
            self._delivery_timeout_for = None

    def _new_activation_request(
        self,
        launch_spec: AssistantRuntimeLaunchSpec,
    ) -> AssistantRuntimeActivationRequest:
        request = AssistantRuntimeActivationRequest.from_launch_spec(
            launch_spec,
            activation_id=next(self._activation_ids),
        )
        self._last_activation_request = request
        return request

    def _begin_activation(
        self,
        request: AssistantRuntimeActivationRequest,
    ) -> None:
        """Register one expected activation before dispatching worker work."""
        self._coordinator.begin_loading(
            request,
            activation_id=request.activation_id,
        )
        self._arm_activation_watchdog(request.activation_id)

    def _arm_activation_watchdog(self, activation_id: int) -> None:
        self._stop_activation_watchdog()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda request_id=activation_id: self._on_activation_timeout(request_id)
        )
        self._activation_watchdog = timer
        self._watchdog_activation_id = activation_id
        timer.start(self._activation_timeout_ms)

    def _stop_activation_watchdog(self) -> None:
        timer = self._activation_watchdog
        self._activation_watchdog = None
        self._watchdog_activation_id = None
        if timer is None:
            return
        timer.stop()
        with suppress(TypeError, RuntimeError):
            timer.timeout.disconnect()
        timer.deleteLater()

    def _on_activation_timeout(self, activation_id: int) -> None:
        if not self._coordinator.fail_activation(
            activation_id,
            self._ACTIVATION_TIMEOUT_MESSAGE,
            keep_expected=True,
        ):
            return
        if self._watchdog_activation_id == activation_id:
            self._stop_activation_watchdog()

    def _rollback_failed_start(
        self,
        controller: object | None,
        *,
        dispatcher_bound: bool,
    ) -> None:
        """Remove partial startup state and leave a retryable failed runtime."""
        self._disconnect_controller_lifecycle_signals()
        self._clear_active_turn()

        cleanup_complete = True
        if dispatcher_bound:
            try:
                cleanup_complete = bool(self._dispatcher.close())
            except Exception as exc:
                cleanup_complete = False
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="assistant_runtime_lifecycle",
                    operation="rollback_close_dispatcher",
                )
        elif controller is not None:
            close = getattr(controller, "close", None)
            if callable(close):
                try:
                    cleanup_complete = bool(close())
                except Exception as exc:
                    cleanup_complete = False
                    safe_unexpected_failure(
                        logger,
                        exc,
                        boundary="assistant_runtime_lifecycle",
                        operation="rollback_close_controller",
                    )

        self._initialized = False
        if cleanup_complete:
            self._controller = None
            self._startup_cleanup_via_dispatcher = None
        else:
            self._controller = controller
            self._startup_cleanup_via_dispatcher = dispatcher_bound
            self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
            logger.error(
                "Assistant startup rollback retained controller ownership for "
                "a later shutdown retry"
            )
        if cleanup_complete and self._dispatcher_factory is not None:
            self._replace_dispatcher(self._dispatcher_factory())
        self._stop_activation_watchdog()
        self._coordinator.clear_active_runtime(self._START_FAILURE_MESSAGE)

    @pyqtSlot(object)
    def accept_runtime_snapshot(self, payload: object) -> None:
        if not self._lifecycle_is_open:
            logger.warning(
                "Ignoring assistant runtime snapshot while lifecycle is %s",
                self._state.value,
            )
            return
        if self._coordinator.accept_worker_snapshot(payload):
            self._stop_activation_watchdog()

    def replay_runtime_snapshot(self) -> None:
        self._coordinator.replay()

    def mark_unavailable(self, message: str) -> None:
        self._stop_activation_watchdog()
        self._coordinator.mark_unavailable(redact_public_text(message))

    def switch_model(self, model_name: str) -> RuntimeActivationResult:
        """Resolve once and queue one exact immutable model-switch request."""
        if not self._lifecycle_is_open:
            message = self._admission_failure_message()
            self.mark_unavailable(message)
            return RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message=message,
            )
        if self.turn_in_flight:
            return self._busy_activation_result()
        resolution = self._resolve_launch(
            self.load_config(),
            requested_model_id=str(model_name or "").strip(),
        )
        if resolution.failure is not None:
            return self._unavailable_result(resolution.failure)
        launch_spec = resolution.launch_spec
        if launch_spec is None:  # pragma: no cover - resolution invariant
            raise RuntimeError("Assistant runtime resolution returned no launch spec.")
        if self._controller is None:
            return RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Assistant runtime is not initialized.",
                launch_spec=launch_spec,
            )
        if (
            self.current.initialized
            and self.current.backend_mode == launch_spec.backend_mode
            and self.current.model_id == launch_spec.model_id
        ):
            self._coordinator.restore_active_runtime()
            return RuntimeActivationResult(
                RuntimeActivationStatus.ALREADY_READY,
                message=launch_spec.selection_detail,
                launch_spec=launch_spec,
            )
        return self._queue_model_switch(launch_spec)

    def _queue_model_switch(
        self,
        launch_spec: AssistantRuntimeLaunchSpec,
    ) -> RuntimeActivationResult:
        """Dispatch a pre-resolved spec without applying selection policy again."""
        if self.turn_in_flight:
            return self._busy_activation_result()
        activation_request = self._new_activation_request(launch_spec)
        self._begin_activation(activation_request)
        try:
            delivered = self._dispatcher.set_model(activation_request)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="dispatch_model_switch",
            )
            delivered = False
        if delivered is not True:
            logger.error(
                "Assistant model switch command delivery was rejected for "
                "activation %s",
                activation_request.activation_id,
            )
            self._stop_activation_watchdog()
            self._coordinator.fail_activation(
                activation_request.activation_id,
                self._DELIVERY_FAILURE_MESSAGE,
            )
            return RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message=self.current.error,
                launch_spec=activation_request,
            )
        return RuntimeActivationResult(
            RuntimeActivationStatus.SWITCHING,
            message=activation_request.selection_detail,
            launch_spec=activation_request,
        )

    def active_local_runtime_blocks_model_deletion(self) -> bool:
        """Return whether deleting a local model could invalidate the runtime."""
        return bool(
            self._controller is not None and self._coordinator.owns_local_runtime
        )

    def submit(
        self,
        text: str,
        *,
        generation: int | None = None,
    ) -> RuntimeCommandAdmissionResult:
        """Atomically reserve and dispatch one user turn through the runtime."""
        try:
            normalized = bounded_chat_string(
                text,
                field_name="Assistant request",
                maximum_length=MAX_CHAT_MESSAGE_CONTENT_LENGTH,
            ).strip()
        except (TypeError, ValueError):
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=(
                    "Assistant requests may contain at most "
                    f"{MAX_CHAT_MESSAGE_CONTENT_LENGTH} characters."
                ),
            )
        if not normalized:
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Enter a request before sending it to the assistant.",
            )
        if not self.accepts_commands:
            return self._dispatch_if_open("submit", normalized)
        if self.turn_in_flight:
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message=self._BUSY_MESSAGE,
            )

        if generation is None:
            generation = next(self._standalone_ui_generations)
        correlation = AssistantTurnCorrelation(
            generation=generation,
            turn_id=next(self._turn_ids),
        )
        scope = resolve_assistant_turn_scope(normalized)
        request = AssistantTurnRequest(
            correlation=correlation,
            text=normalized,
            scope=scope.scope,
            terminal_command=scope.terminal_command,
            excluded_commands=scope.excluded_commands,
        )
        self._active_turn = correlation
        self._arm_turn_delivery_watchdog(correlation)
        admission = self._dispatch_if_open("submit", request)
        if not admission.accepted:
            self._clear_active_turn(correlation)
            return admission
        return RuntimeCommandAdmissionResult(
            command_name=admission.command_name,
            status=admission.status,
            message=admission.message,
            turn_id=request.turn_id,
            generation=request.generation,
            scope=request.scope,
            terminal_command=request.terminal_command,
            excluded_commands=request.excluded_commands,
        )

    def stop_generation(self) -> RuntimeCommandAdmissionResult:
        # Stop is a control-plane command for an already-admitted turn. It must
        # remain available when a runtime transition has made new submits unsafe.
        active = self._active_turn
        if active is None:
            return RuntimeCommandAdmissionResult(
                command_name="stop",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="There is no active assistant request to stop.",
            )
        if self._stop_requested_for == active:
            return RuntimeCommandAdmissionResult(
                command_name="stop",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=active.turn_id,
                generation=active.generation,
            )
        admission = self._dispatch_if_open("stop", require_ready=False)
        if not admission.accepted:
            return admission
        if self._active_turn == active:
            self._stop_requested_for = active
        return RuntimeCommandAdmissionResult(
            command_name="stop",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
            message=admission.message,
            turn_id=active.turn_id,
            generation=active.generation,
        )

    def reset_conversation(self) -> RuntimeCommandAdmissionResult:
        if self.turn_in_flight:
            return RuntimeCommandAdmissionResult(
                command_name="reset",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message=self._BUSY_MESSAGE,
            )
        return self._dispatch_if_open("reset", require_ready=False)

    def _busy_activation_result(self) -> RuntimeActivationResult:
        """Reject runtime replacement while a correlated turn owns work."""
        return RuntimeActivationResult(
            RuntimeActivationStatus.BUSY,
            message=self._BUSY_MESSAGE,
            model_id=self.current.model_id,
        )

    def confirm(
        self,
        resolution: AgentConfirmationResolution,
    ) -> RuntimeCommandAdmissionResult:
        if not isinstance(resolution, AgentConfirmationResolution):
            raise TypeError("Assistant confirmation resolution must be typed.")
        return self._dispatch_if_open(
            "confirm",
            resolution,
            require_ready=False,
        )

    def resolve_ui_handoff(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> RuntimeCommandAdmissionResult:
        if not isinstance(resolution, WorkflowUiHandoffResolution):
            raise TypeError("Workflow UI handoff resolution must be typed.")
        admission = self._dispatch_if_open(
            "resolve_ui_handoff",
            resolution,
            require_ready=False,
        )
        if (
            admission.accepted
            or not resolution.status.is_terminal
            or not self.turn_in_flight
            or not self._owns_command_transport
            or not self._terminal_handoff_fallback_bound
        ):
            return admission
        failed = resolution.delivery_failed(
            "The completed XBrainLab settings step could not be delivered to "
            "the assistant runtime. The turn was stopped safely."
        )
        active = self._active_turn
        self._terminal_handoff_delivery_failed.emit(failed)
        return RuntimeCommandAdmissionResult(
            command_name="resolve_ui_handoff",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
            message=failed.message,
            turn_id=active.turn_id if active is not None else None,
            generation=active.generation if active is not None else None,
        )

    def debug(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        generation: int | None = None,
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> RuntimeCommandAdmissionResult:
        if not self.accepts_commands:
            return self._dispatch_if_open("debug", object())
        if self.turn_in_flight:
            return RuntimeCommandAdmissionResult(
                command_name="debug",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message=self._BUSY_MESSAGE,
            )
        if generation is None:
            generation = next(self._standalone_ui_generations)
        correlation = AssistantTurnCorrelation(
            generation=generation,
            turn_id=next(self._turn_ids),
        )
        try:
            request = AssistantDebugToolRequest.from_params(
                correlation=correlation,
                tool_name=tool_name,
                params=params,
                confirmed=confirmed,
                authorization_text=authorization_text,
            )
        except (TypeError, ValueError) as exc:
            return RuntimeCommandAdmissionResult(
                command_name="debug",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=redact_public_text(exc),
            )
        self._active_turn = correlation
        self._arm_turn_delivery_watchdog(correlation)
        admission = self._dispatch_if_open("debug", request)
        if not admission.accepted:
            self._clear_active_turn(correlation)
            return admission
        return RuntimeCommandAdmissionResult(
            command_name=admission.command_name,
            status=admission.status,
            message=admission.message,
            turn_id=request.turn_id,
            generation=request.generation,
        )

    def _dispatch_if_open(
        self,
        method_name: str,
        *args: Any,
        require_ready: bool = True,
    ) -> RuntimeCommandAdmissionResult:
        can_dispatch = (
            self.accepts_commands if require_ready else self._owns_command_transport
        )
        if not can_dispatch:
            logger.warning(
                "Assistant runtime command '%s' rejected while lifecycle is %s",
                method_name,
                self._state.value,
            )
            return RuntimeCommandAdmissionResult(
                command_name=method_name,
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=self._admission_failure_message(),
            )
        method = getattr(self._dispatcher, method_name)
        try:
            dispatched = method(*args)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation=f"dispatch_{method_name}",
            )
            return RuntimeCommandAdmissionResult(
                command_name=method_name,
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=self._DELIVERY_FAILURE_MESSAGE,
            )
        if dispatched is not True:
            logger.error(
                "Assistant runtime command '%s' delivery was rejected: %s",
                method_name,
                redact_public_text(dispatched),
            )
            return RuntimeCommandAdmissionResult(
                command_name=method_name,
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=self._DELIVERY_FAILURE_MESSAGE,
            )
        return RuntimeCommandAdmissionResult(
            command_name=method_name,
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
        )

    def _admission_failure_message(self) -> str:
        if self._state is AssistantRuntimeLifecycleState.CLOSED:
            return self._CLOSED_MESSAGE
        if self._state is AssistantRuntimeLifecycleState.CLEANUP_PENDING:
            return self._CLEANUP_PENDING_MESSAGE
        if self._state is AssistantRuntimeLifecycleState.CLOSING:
            return self._SHUTTING_DOWN_MESSAGE
        if self._state is AssistantRuntimeLifecycleState.DEACTIVATING:
            return self._DEACTIVATING_MESSAGE
        if self.current.phase is AssistantRuntimePhase.LOADING:
            return self._LOADING_MESSAGE
        if self.current.phase is AssistantRuntimePhase.FAILED:
            detail = " ".join(redact_public_text(self.current.error or "").split())
            suffix = f" {detail}" if detail else ""
            return "Assistant runtime failed and cannot accept requests." + suffix
        return self._IDLE_MESSAGE

    def request_deactivation(
        self,
        config: LLMConfig,
    ) -> RuntimeCommandAdmissionResult:
        """Unload and persist disabled state without terminally closing the app."""
        if self.turn_in_flight:
            return RuntimeCommandAdmissionResult(
                command_name="deactivate",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message=(
                    "The assistant is still processing a request. Press Stop and "
                    "wait for it to finish before disabling Assistant."
                ),
            )
        if not self._lifecycle_is_open:
            return RuntimeCommandAdmissionResult(
                command_name="deactivate",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=self._admission_failure_message(),
            )
        if self._dispatcher_factory is None:
            return RuntimeCommandAdmissionResult(
                command_name="deactivate",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Assistant cannot be restarted safely in this session.",
            )

        self._deactivation_requested = True
        self._deactivation_config = config
        self._state = AssistantRuntimeLifecycleState.DEACTIVATING
        self._initialized = False
        self._stop_activation_watchdog()
        self._stop_turn_delivery_watchdog()
        self._coordinator.mark_unavailable(self._DEACTIVATING_MESSAGE)
        try:
            closed = bool(self._dispatcher.close())
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="deactivate",
            )
            self._deactivation_requested = False
            self._deactivation_config = None
            self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
            self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
            message = "Assistant could not be disabled safely."
            self.deactivation_finished.emit(False, message)
            return RuntimeCommandAdmissionResult(
                command_name="deactivate",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message=message,
            )
        if closed:
            self._complete_deactivation()
        return RuntimeCommandAdmissionResult(
            command_name="deactivate",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
        )

    def _complete_deactivation(self) -> None:
        """Release runtime ownership, persist disabled, and reopen transport."""
        config = self._deactivation_config
        factory = self._dispatcher_factory
        if not self._deactivation_requested or config is None or factory is None:
            return
        self._deactivation_requested = False
        self._deactivation_config = None
        self._disconnect_controller_lifecycle_signals()
        self._controller = None
        self._startup_cleanup_via_dispatcher = None
        self._replace_dispatcher(factory())
        previous_enabled = bool(config.local_model_enabled)
        previous_acknowledged = bool(config.local_runtime_notice_acknowledged)
        config.local_model_enabled = False
        config.local_runtime_notice_acknowledged = True
        if not config.save_to_file():
            config.local_model_enabled = previous_enabled
            config.local_runtime_notice_acknowledged = previous_acknowledged
            self._state = AssistantRuntimeLifecycleState.OPEN
            message = "Assistant could not save the disabled setting."
            self._coordinator.clear_active_runtime(message)
            self.deactivation_finished.emit(False, message)
            return
        self._state = AssistantRuntimeLifecycleState.OPEN
        self._coordinator.clear_active_runtime("Assistant is disabled.")
        self.deactivation_finished.emit(True, "Assistant disabled.")

    def close(self) -> bool:
        """Close command admission now and retain ownership until cleanup ends."""
        if self._state is AssistantRuntimeLifecycleState.CLOSED:
            return True
        if self._state is AssistantRuntimeLifecycleState.CLOSING:
            return False
        if self._state is AssistantRuntimeLifecycleState.DEACTIVATING:
            self._close_requested = True
            self._deactivation_requested = False
            self._deactivation_config = None
            self._state = AssistantRuntimeLifecycleState.CLOSING
            self._coordinator.mark_unavailable(self._SHUTTING_DOWN_MESSAGE)
            self.deactivation_finished.emit(
                False,
                "Application shutdown replaced the disable request.",
            )
            return False
        self._close_requested = True
        self._state = AssistantRuntimeLifecycleState.CLOSING
        self._initialized = False
        self._stop_activation_watchdog()
        self._stop_turn_delivery_watchdog()
        self._coordinator.mark_unavailable(self._SHUTTING_DOWN_MESSAGE)
        try:
            if self._startup_cleanup_via_dispatcher is False:
                close = getattr(self._controller, "close", None)
                closed = bool(close()) if callable(close) else True
            else:
                closed = bool(self._dispatcher.close())
        except Exception as exc:
            closed = False
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_runtime_lifecycle",
                operation="close",
            )
        if closed:
            self._complete_close()
        else:
            self._state = AssistantRuntimeLifecycleState.CLEANUP_PENDING
            self._coordinator.mark_unavailable(self._CLEANUP_PENDING_MESSAGE)
        return closed

    def _complete_close(self) -> None:
        """Publish the terminal lifecycle state after all owned threads stop."""
        if self._state is AssistantRuntimeLifecycleState.CLOSED:
            return
        active = self._active_turn
        if active is not None:
            self._release_turn(
                AssistantTurnTerminal(
                    correlation=active,
                    outcome="shutdown_cancelled",
                )
            )
        self._disconnect_controller_lifecycle_signals()
        self._state = AssistantRuntimeLifecycleState.CLOSED
        self._controller = None
        self._startup_cleanup_via_dispatcher = None
        self._deactivation_requested = False
        self._deactivation_config = None
        self._coordinator.clear_active_runtime(self._CLOSED_MESSAGE)
