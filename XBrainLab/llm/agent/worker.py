"""Background worker for LLM inference.

Provides a Qt-based worker that runs LLM generation in a separate
thread, with streaming output, timeout handling, and hot-swap model
switching.
"""

import contextlib

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_process import (
    LocalRuntimeLoadError,
)
from XBrainLab.llm.core.runtime_process import (
    LocalRuntimeProcessOwner as LLMEngine,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchSpec
from XBrainLab.llm.tools.result_contract import (
    SAFE_UNEXPECTED_FAILURE_MESSAGE,
    redact_public_text,
    safe_unexpected_failure,
)

from .runtime_state import AssistantRuntimePhase, AssistantRuntimeSnapshot
from .turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
)

# Cooperative model cancellation gets this short grace before the owned process
# is terminated and the runtime becomes restart-required.
GENERATION_THREAD_SHUTDOWN_WAIT_MS = 750
GENERATION_THREAD_EXIT_WAIT_MS = 250
RUNTIME_RESTART_REQUIRED_MESSAGE = (
    "The local model process stopped responding and was terminated. "
    "Retry the local assistant to restart it."
)
LIVE_GENERATION_SETTING_FIELDS = (
    "temperature",
    "top_p",
    "max_new_tokens",
)


def _runtime_load_failure_message(error: Exception) -> str:
    """Keep expected recoverable load guidance while redacting unknown failures."""
    if isinstance(error, LocalRuntimeLoadError) and error.recoverable:
        logger.warning("Local runtime load stopped with a recoverable error.")
        return redact_public_text(str(error))
    return safe_unexpected_failure(
        logger,
        error,
        boundary="assistant_worker",
        operation="initialize_agent",
    ).message


class AssistantGenerationAdmissionError(RuntimeError):
    """Expected, user-actionable rejection before model generation starts."""

    def __init__(self, message: object) -> None:
        public_message = (
            message
            if type(message) is str
            else "The assistant request could not start."
        )
        self.public_message = public_message
        super().__init__(public_message)


class GenerationThread(QThread):
    """QThread for running LLM generation without blocking the UI.

    Attributes:
        chunk_received: Signal emitted for each text chunk generated.
        finished_generation: Signal emitted when generation completes.
        error_occurred: Signal emitted with an error message on failure.
        engine: The LLM engine performing inference.
        messages: The message list to generate from.

    """

    chunk_received = pyqtSignal(str)
    finished_generation = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, engine, request: AssistantGenerationRequest):
        """Initializes the GenerationThread.

        Args:
            engine: The ``LLMEngine`` instance to use for generation.
            request: Typed request containing messages and decoding policy.

        """
        super().__init__()
        self.engine = engine
        self.request = request

    def run(self):
        """Executes streaming generation, emitting chunks until done."""
        try:
            for chunk in self.engine.generate_stream(
                self.request.to_model_messages(),
                profile=self.request.generation_profile,
            ):
                if self.isInterruptionRequested():
                    logger.info("Generation interrupted by user request.")
                    break
                self.chunk_received.emit(chunk)
            self.finished_generation.emit()
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_generation_thread",
                operation="generate_stream",
            )
            self.error_occurred.emit(failure.message)


class RuntimeLoadThread(QThread):
    """Load one process-owned runtime without blocking worker control slots."""

    load_succeeded = pyqtSignal(object)
    load_failed = pyqtSignal(object, object)

    def __init__(self, engine: LLMEngine):
        super().__init__()
        self.engine = engine

    def run(self) -> None:
        try:
            self.engine.load_model()
        except Exception as exc:
            self.load_failed.emit(self, exc)
            return
        self.load_succeeded.emit(self)


ACTIVE_GENERATION_THREADS: set[GenerationThread] = set()
ACTIVE_RUNTIME_LOAD_THREADS: set[RuntimeLoadThread] = set()


class AgentWorker(QObject):
    """Worker managing LLM initialization, generation, and model switching.

    Runs inside a dedicated ``QThread`` to keep the UI responsive.  Emits
    Qt signals for streaming chunks, completion, errors, and status logs.

    Attributes:
        error: Signal emitted for runtime/model lifecycle errors.
        log: Signal emitted with status/log messages.
        engine: The underlying ``LLMEngine`` instance (``None`` until initialized).
        generation_thread: The currently running ``GenerationThread``, if any.

    """

    error = pyqtSignal(str)
    generation_finished = pyqtSignal(int, list)
    generation_chunk_received = pyqtSignal(int, str)
    generation_error = pyqtSignal(int, str)
    generation_dispatch_acknowledged = pyqtSignal(object)
    log = pyqtSignal(str)
    generation_stop_finished = pyqtSignal(object)
    shutdown_finished = pyqtSignal(bool)
    runtime_snapshot_changed = pyqtSignal(object)

    def __init__(self):
        """Initializes the AgentWorker with no engine loaded."""
        super().__init__()
        self.engine: LLMEngine | None = None
        self.generation_thread: GenerationThread | None = None
        self.runtime_load_thread: RuntimeLoadThread | None = None
        self.timeout_timer: QTimer | None = None
        self._is_timed_out = False
        self._timed_out_generation: GenerationThread | None = None
        self._cancel_pending = False
        self._pending_stop_request: AssistantGenerationStopRequest | None = None
        self._active_generation_id: int | None = None
        self._generation_thread_id: int | None = None
        self._runtime_phase = AssistantRuntimePhase.IDLE
        self._runtime_error = ""
        self._runtime_launch_spec: AssistantRuntimeLaunchSpec | None = None
        self._runtime_activation_id = 0
        self._shutdown_requested = False

    def _reload_generation_settings(self) -> None:
        """Refresh live generation knobs without changing runtime selection."""
        if self.engine is None:
            return
        saved = LLMConfig.load_from_file()
        if saved is None:
            return
        for field_name in LIVE_GENERATION_SETTING_FIELDS:
            setattr(
                self.engine.config,
                field_name,
                getattr(saved, field_name),
            )

    def initialize_agent(self, launch_spec: AssistantRuntimeLaunchSpec):
        """Initializes the LLM engine and loads the model.

        Consumes the exact immutable selection produced by the lifecycle. If
        the engine is already initialized, this method is a no-op.

        Raises:
            Exception: Propagated via the ``error`` signal if model
                loading fails.

        """
        if not isinstance(launch_spec, AssistantRuntimeLaunchSpec):
            message = "Assistant initialization requires a runtime launch spec."
            self._publish_runtime(AssistantRuntimePhase.FAILED, error=message)
            self.error.emit(f"Model Load Error: {message}")
            return

        activation_id = self._activation_id(launch_spec)
        if self.engine:
            if activation_id > 0:
                active = self._runtime_launch_spec
                if (
                    active is not None
                    and active.backend_mode == launch_spec.backend_mode
                    and active.model_id == launch_spec.model_id
                ):
                    self._publish_runtime(
                        AssistantRuntimePhase.READY,
                        launch_spec=active,
                        activation_id=activation_id,
                    )
                else:
                    self._publish_runtime(
                        AssistantRuntimePhase.FAILED,
                        error=(
                            "Assistant runtime is already initialized with "
                            "another model."
                        ),
                        launch_spec=launch_spec,
                        activation_id=activation_id,
                    )
            return

        self._runtime_launch_spec = launch_spec
        self._runtime_activation_id = activation_id
        self._publish_runtime(
            AssistantRuntimePhase.LOADING,
            activation_id=activation_id,
        )
        config = launch_spec.build_config()
        if launch_spec.selection_detail != "Local runtime ready.":
            logger.warning(
                "Local backend will continue with resolved runtime: %s",
                redact_public_text(launch_spec.selection_detail),
            )
            self.log.emit(redact_public_text(launch_spec.selection_detail))

        candidate_engine: LLMEngine | None = None
        try:
            logger.info("Initializing LLM Engine...")
            self.log.emit("Loading AI Model...")

            candidate_engine = LLMEngine(config)
            if getattr(candidate_engine, "uses_owned_process", False) is True:
                self.engine = candidate_engine
                self._start_runtime_load(candidate_engine)
                return
            candidate_engine.load_model()
            self.engine = candidate_engine
            self._publish_runtime(
                AssistantRuntimePhase.READY,
                activation_id=activation_id,
            )

            self.log.emit(
                f"AI Model Loaded: {redact_public_text(launch_spec.model_id)}"
            )
            logger.info("Local Agent initialized successfully")
        except Exception as exc:
            failure_message = _runtime_load_failure_message(exc)
            close = getattr(candidate_engine, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
            self.engine = None
            self._publish_runtime(
                AssistantRuntimePhase.FAILED,
                error=failure_message,
                activation_id=activation_id,
            )
            self.error.emit(f"Model Load Error: {failure_message}")

    def _start_runtime_load(self, engine: LLMEngine) -> None:
        """Track one asynchronous process load while retaining close ownership."""
        thread = RuntimeLoadThread(engine)
        self.runtime_load_thread = thread
        ACTIVE_RUNTIME_LOAD_THREADS.add(thread)
        thread.load_succeeded.connect(self._on_runtime_load_succeeded)
        thread.load_failed.connect(self._on_runtime_load_failed)
        thread.finished.connect(lambda: self._release_runtime_load_thread(thread))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_runtime_load_succeeded(self, payload: object) -> None:
        if not isinstance(payload, RuntimeLoadThread):
            return
        if payload is not self.runtime_load_thread or payload.engine is not self.engine:
            return
        if self._shutdown_requested:
            self._close_engine(payload.engine)
            self.engine = None
            return
        self._publish_runtime(
            AssistantRuntimePhase.READY,
            activation_id=self._runtime_activation_id,
        )
        launch_spec = self._runtime_launch_spec
        if launch_spec is not None:
            self.log.emit(
                f"AI Model Loaded: {redact_public_text(launch_spec.model_id)}"
            )
        logger.info("Local Agent initialized successfully")

    def _on_runtime_load_failed(
        self,
        thread_payload: object,
        error_payload: object,
    ) -> None:
        if not isinstance(thread_payload, RuntimeLoadThread):
            return
        if (
            thread_payload is not self.runtime_load_thread
            or thread_payload.engine is not self.engine
        ):
            return
        if self._shutdown_requested:
            self.engine = None
            return
        error = (
            error_payload
            if isinstance(error_payload, Exception)
            else RuntimeError("Local model process failed to load.")
        )
        failure_message = _runtime_load_failure_message(error)
        self._close_engine(thread_payload.engine)
        self.engine = None
        self._publish_runtime(
            AssistantRuntimePhase.FAILED,
            error=failure_message,
            activation_id=self._runtime_activation_id,
        )
        self.error.emit(f"Model Load Error: {failure_message}")

    def _release_runtime_load_thread(self, thread: RuntimeLoadThread) -> None:
        ACTIVE_RUNTIME_LOAD_THREADS.discard(thread)
        if self.runtime_load_thread is thread:
            self.runtime_load_thread = None

    @staticmethod
    def _close_engine(engine: object, *, wait_ms: int = 0) -> bool:
        close = getattr(engine, "close", None)
        if not callable(close):
            return True
        if getattr(engine, "uses_owned_process", False) is True:
            return close(wait_timeout=max(0, int(wait_ms)) / 1000.0) is not False
        return close() is not False

    def _cleanup_runtime_load(self, *, wait_ms: int) -> bool:
        """Stop an in-flight process load through the exact owned process."""
        thread = self.runtime_load_thread
        if thread is None:
            return True
        engine = self.engine
        closed = True if engine is None else self._close_engine(engine, wait_ms=wait_ms)
        thread.requestInterruption()
        try:
            running = thread.isRunning()
        except RuntimeError:
            self._release_runtime_load_thread(thread)
            return closed
        if not running:
            self._release_runtime_load_thread(thread)
        return closed and not running

    def _track_generation_thread(self, thread: GenerationThread) -> None:
        """Keep running generation threads alive until Qt reports finished."""
        ACTIVE_GENERATION_THREADS.add(thread)
        thread.finished.connect(lambda: self._release_generation_thread(thread))
        thread.finished.connect(thread.deleteLater)

    def _release_generation_thread(self, thread: GenerationThread) -> None:
        """Release ownership only after Qt confirms the thread has finished."""
        ACTIVE_GENERATION_THREADS.discard(thread)
        if self.generation_thread is not thread:
            return
        generation_id = self._generation_thread_id or self._active_generation_id
        self.generation_thread = None
        self._generation_thread_id = None
        if self._active_generation_id == generation_id:
            self._active_generation_id = None
        if self._cancel_pending:
            request = self._pending_stop_request
            self._cancel_pending = False
            self._pending_stop_request = None
            self._timed_out_generation = None
            self._is_timed_out = False
            self._active_generation_id = None
            if request is None and generation_id is not None:
                request = AssistantGenerationStopRequest(generation_id=generation_id)
            if request is not None:
                self._acknowledge_generation_stop(request, stopped=True)
            return
        if self._timed_out_generation is thread:
            self._timed_out_generation = None
            message = "Error: Generation timed out (Local LLM is too slow)."
            if generation_id is not None and generation_id > 0:
                self.generation_error.emit(generation_id, message)
            self._active_generation_id = None

    def _generation_is_active(self) -> bool:
        """Return whether the worker still owns a running generation thread."""
        thread = self.generation_thread
        if thread is None:
            return False
        try:
            running = thread.isRunning()
        except RuntimeError:
            self._release_generation_thread(thread)
            return False
        if not running:
            self._release_generation_thread(thread)
            return False
        return True

    @staticmethod
    def _disconnect_generation_thread(thread: GenerationThread) -> None:
        """Disconnect generation callbacks if they are still connected."""
        with contextlib.suppress(TypeError, RuntimeError):
            thread.chunk_received.disconnect()
        with contextlib.suppress(TypeError, RuntimeError):
            thread.finished_generation.disconnect()
        with contextlib.suppress(TypeError, RuntimeError):
            thread.error_occurred.disconnect()

    def _cancel_backend_generation(self, *, wait_ms: int) -> bool:
        """Request backend cancellation and preserve an explicit failure."""
        cancel = getattr(self.engine, "cancel_generation", None)
        if not callable(cancel):
            return True
        try:
            return bool(
                cancel(wait_timeout=max(0, int(wait_ms)) / 1000 if wait_ms > 0 else 0.0)
            )
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_worker",
                operation="cancel_backend_generation",
            )
            return False

    def _engine_requires_restart(self) -> bool:
        return (
            self.engine is not None
            and getattr(self.engine, "restart_required", False) is True
        )

    def _retire_restart_required_engine(self) -> None:
        """Fence a terminated model process and publish retry-only readiness."""
        engine = self.engine
        if engine is None:
            return
        close = getattr(engine, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                self._close_engine(engine)
        self.engine = None
        self._publish_runtime(
            AssistantRuntimePhase.FAILED,
            error=RUNTIME_RESTART_REQUIRED_MESSAGE,
            activation_id=0,
        )

    def _cleanup_generation_thread(self, wait_ms: int = 0) -> bool:
        """Disconnect and request interruption of any running generation thread.

        Prevents double callbacks and interleaved chunks when a new
        generation is started before a previous one finishes.
        """
        thread = self.generation_thread
        if thread is None:
            if (
                self._generation_thread_id is None
                and self._active_generation_id is None
            ):
                return True
            return self._cancel_backend_generation(wait_ms=wait_ms)

        self._disconnect_generation_thread(thread)
        try:
            running = thread.isRunning()
        except RuntimeError:
            self._release_generation_thread(thread)
            return True
        wait_completed = False
        backend_stopped = True
        if running:
            backend_stopped = self._cancel_backend_generation(wait_ms=wait_ms)
            thread.requestInterruption()
            wait_for_thread = getattr(thread, "wait", None)
            if (
                backend_stopped
                and getattr(self.engine, "uses_owned_process", False) is True
                and callable(wait_for_thread)
            ):
                wait_completed = bool(wait_for_thread(GENERATION_THREAD_EXIT_WAIT_MS))
            elif (
                wait_ms > 0
                and not isinstance(thread, QThread)
                and callable(wait_for_thread)
            ):
                wait_completed = bool(wait_for_thread(max(0, int(wait_ms))))
        if self._engine_requires_restart():
            self._retire_restart_required_engine()
        stopped = backend_stopped and (not running or wait_completed)
        if running and not wait_completed:
            try:
                stopped = backend_stopped and not thread.isRunning()
            except RuntimeError:
                stopped = backend_stopped
        if stopped:
            self._release_generation_thread(thread)
        return stopped

    def cancel_generation(self, payload: object) -> None:
        """Cancel generation on the worker's owning Qt thread."""
        if not isinstance(payload, AssistantGenerationStopRequest):
            self.error.emit(
                "Assistant generation cancellation requires a typed request."
            )
            return
        if self.timeout_timer is not None:
            self.timeout_timer.stop()
        owned_generation_id = self._generation_thread_id or self._active_generation_id
        if self.generation_thread is not None and owned_generation_id is None:
            self._acknowledge_generation_stop(payload, stopped=False)
            return
        if (
            owned_generation_id is not None
            and payload.generation_id != owned_generation_id
        ):
            self._acknowledge_generation_stop(payload, stopped=False)
            return
        if self.generation_thread is None:
            stopped = self._cancel_backend_generation(
                wait_ms=GENERATION_THREAD_SHUTDOWN_WAIT_MS,
            )
            if stopped:
                self._active_generation_id = None
                self._generation_thread_id = None
                self._cancel_pending = False
                self._pending_stop_request = None
            self._acknowledge_generation_stop(payload, stopped=stopped)
            return
        self._cancel_pending = True
        self._pending_stop_request = payload
        self._timed_out_generation = None
        stopped = self._cleanup_generation_thread(
            wait_ms=GENERATION_THREAD_SHUTDOWN_WAIT_MS,
        )
        if stopped and self._cancel_pending:
            self._cancel_pending = False
            self._pending_stop_request = None
            self._active_generation_id = None
            self._generation_thread_id = None
            self._acknowledge_generation_stop(payload, stopped=True)
        elif not stopped:
            self._acknowledge_generation_stop(payload, stopped=False)

    def _acknowledge_generation_stop(
        self,
        request: AssistantGenerationStopRequest,
        *,
        stopped: bool,
    ) -> None:
        self.generation_stop_finished.emit(
            AssistantGenerationStopAcknowledgement(
                generation_id=request.generation_id,
                stopped=stopped,
            )
        )

    @staticmethod
    def _require_generation_engine(
        engine: LLMEngine | None,
    ) -> LLMEngine:
        if engine is None:
            raise AssistantGenerationAdmissionError(
                "Failed to initialize LLM engine.",
            )
        if (
            getattr(engine, "uses_owned_process", False) is True
            and engine.active_backend is None
        ):
            if engine.restart_required:
                raise AssistantGenerationAdmissionError(
                    RUNTIME_RESTART_REQUIRED_MESSAGE,
                )
            raise AssistantGenerationAdmissionError(
                "The local assistant is still loading. Please wait until it is ready.",
            )
        return engine

    @staticmethod
    def _require_generation_slot_available(stopped: bool) -> None:
        if not stopped:
            raise AssistantGenerationAdmissionError(
                "Previous generation is still stopping. Please wait and retry."
            )

    def generate_from_messages(self, request: AssistantGenerationRequest):
        """Run one typed LLM generation request.

        Reloads configuration from the settings file to capture any
        runtime changes (e.g. temperature, API key), then spawns a
        ``GenerationThread`` with a configurable timeout.

        Args:
            request: Typed messages, response grammar, and decoding profile.

        """
        if not isinstance(request, AssistantGenerationRequest):
            self.error.emit("Assistant generation requires a typed request.")
            return

        generation_id = request.generation_id
        if generation_id <= 0:
            self.error.emit("Assistant generation requires a positive correlation ID.")
            return
        try:
            self._acknowledge_generation_dispatch(
                generation_id,
                AssistantGenerationDispatchPhase.ACCEPTED,
            )
            if not self.engine:
                launch_spec = self._runtime_launch_spec
                if launch_spec is not None:
                    self.initialize_agent(launch_spec)
            engine = self._require_generation_engine(self.engine)

            self._require_generation_slot_available(self._cleanup_generation_thread())

            messages = request.to_model_messages()
            last_msg = messages[-1]
            if last_msg["role"] == "user":
                message_length = len(str(last_msg.get("content", "")))
                self.log.emit("Processing...")
                logger.info(
                    "Agent generation requested (message_chars=%s)",
                    message_length,
                )
            else:
                self.log.emit("Processing...")

            # Generation settings can update live, but backend/model selection is
            # immutable until the lifecycle dispatches a new launch spec.
            try:
                self._reload_generation_settings()
            except Exception as error:
                safe_unexpected_failure(
                    logger,
                    error,
                    boundary="assistant_worker",
                    operation="reload_generation_settings",
                )
                raise RuntimeError(SAFE_UNEXPECTED_FAILURE_MESSAGE) from None

            self._active_generation_id = generation_id
            self._generation_thread_id = generation_id
            self.generation_thread = GenerationThread(engine, request)
            self.generation_thread.chunk_received.connect(
                lambda chunk, current=generation_id: self._on_generation_chunk(
                    current,
                    chunk,
                )
            )
            self.generation_thread.finished_generation.connect(
                lambda current=generation_id: self._on_generation_finished(current)
            )
            self.generation_thread.error_occurred.connect(
                lambda message, current=generation_id: self._on_generation_error(
                    current,
                    message,
                )
            )
            self._track_generation_thread(self.generation_thread)

            # Timeout timer (thread-safe UI timer) — reuse existing or create once
            self._is_timed_out = False
            self._timed_out_generation = None

            if self.timeout_timer is None:
                self.timeout_timer = QTimer(self)
                self.timeout_timer.setSingleShot(True)
                self.timeout_timer.timeout.connect(self._on_timeout)

            # Start with config timeout or default 60s
            timeout_ms = getattr(engine.config, "timeout", 60) * 1000
            self.timeout_timer.start(timeout_ms)

            self.generation_thread.start()
        except Exception as error:
            self._finish_generation_setup_failure(generation_id, error)
            return

        self._acknowledge_generation_dispatch(
            generation_id,
            AssistantGenerationDispatchPhase.STARTED,
        )

    def _acknowledge_generation_dispatch(
        self,
        generation_id: int,
        phase: AssistantGenerationDispatchPhase,
    ) -> None:
        """Publish typed worker progress for one queued generation request."""
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=generation_id,
                phase=phase,
            )
        )

    def _finish_generation_setup_failure(
        self,
        generation_id: int,
        error: Exception,
    ) -> None:
        """Release partial setup state and emit one correlated terminal error."""
        if type(error) is AssistantGenerationAdmissionError:
            message = redact_public_text(
                object.__getattribute__(error, "public_message")
            )
            logger.warning(
                "Assistant generation %s was not admitted: %s",
                generation_id,
                redact_public_text(message),
            )
        else:
            failure = safe_unexpected_failure(
                logger,
                error,
                boundary="assistant_worker",
                operation="finish_generation_setup",
            )
            message = failure.message
        if self.timeout_timer is not None:
            with contextlib.suppress(RuntimeError):
                self.timeout_timer.stop()
        thread = self.generation_thread
        if thread is not None and self._generation_thread_id == generation_id:
            with contextlib.suppress(Exception):
                self._cleanup_generation_thread()
            if self.generation_thread is thread:
                self._release_generation_thread(thread)
        if self._active_generation_id == generation_id:
            self._active_generation_id = None
        if self._generation_thread_id == generation_id:
            self._generation_thread_id = None
        self.generation_error.emit(generation_id, message)

    def _on_timeout(self):
        """Handles generation timeout.

        Requests interruption of the generation thread and records a pending
        timeout. The error is emitted only after thread exit, while the
        timed-out flag prevents stale callbacks from further processing.
        """
        if self.generation_thread and self.generation_thread.isRunning():
            thread = self.generation_thread
            self._is_timed_out = True
            self._timed_out_generation = thread
            if self.timeout_timer is not None:
                self.timeout_timer.stop()
            logger.error("Agent generation timed out.")

            # Product runtimes get a cooperative grace followed by owned-process
            # termination. The parent generation thread is still fenced until
            # Qt confirms that this exact correlated request has exited.
            wait_ms = (
                GENERATION_THREAD_SHUTDOWN_WAIT_MS
                if getattr(self.engine, "uses_owned_process", False) is True
                else 0
            )
            self._cleanup_generation_thread(wait_ms=wait_ms)

    def _on_generation_chunk(self, generation_id: int, chunk: str) -> None:
        """Forward output only for the worker's still-active generation."""
        if generation_id != self._active_generation_id:
            return
        self.generation_chunk_received.emit(generation_id, chunk)

    def _on_generation_finished(self, generation_id: int):
        """Handles successful completion of the generation thread."""
        active_generation_id = self._active_generation_id
        if generation_id != active_generation_id:
            return
        if self._is_timed_out:
            return
        if self.timeout_timer is not None:
            self.timeout_timer.stop()
        self.generation_finished.emit(generation_id, [])
        self._active_generation_id = None
        self.log.emit("Generation completed.")

    def _on_generation_error(
        self,
        generation_id: int,
        err_msg: str,
    ):
        """Handles an error emitted by the generation thread.

        Args:
            err_msg: The error message string from the generation thread.

        """
        active_generation_id = self._active_generation_id
        if generation_id != active_generation_id or self._is_timed_out:
            return
        if self.timeout_timer is not None:
            self.timeout_timer.stop()
        self.generation_error.emit(generation_id, err_msg)
        self._active_generation_id = None
        if self._engine_requires_restart():
            self._retire_restart_required_engine()

    def reinitialize_agent(self, launch_spec: AssistantRuntimeLaunchSpec):
        """Hot-swap to one exact selection resolved by the lifecycle."""
        if not isinstance(launch_spec, AssistantRuntimeLaunchSpec):
            message = "Assistant model switch requires a runtime launch spec."
            logger.warning("Rejected untyped assistant model switch")
            self.error.emit(f"Switch Failed: {message}")
            return
        activation_id = self._activation_id(launch_spec)
        if self._generation_is_active():
            message = "Wait for the active generation to finish or stop it."
            self._publish_runtime(
                AssistantRuntimePhase.FAILED,
                error=message,
                launch_spec=launch_spec,
                activation_id=activation_id,
            )
            self.error.emit(f"Switch Failed: {message}")
            return

        logger.info(
            "Worker switching model to: %s",
            redact_public_text(launch_spec.model_id),
        )
        self.log.emit(f"Switching to {redact_public_text(launch_spec.model_id)}...")

        engine = self.engine
        if engine is None:
            config = launch_spec.build_config()
            try:
                config.save_to_file()
            except Exception as exc:
                failure = safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="assistant_worker",
                    operation="save_model_selection",
                )
                self._publish_runtime(
                    AssistantRuntimePhase.FAILED,
                    error=failure.message,
                    launch_spec=launch_spec,
                    activation_id=activation_id,
                )
                self.error.emit(f"Switch Failed: {failure.message}")
                return
            self.initialize_agent(launch_spec)
            return

        old_config = engine.config
        old_launch_spec = self._runtime_launch_spec
        new_config = launch_spec.build_config()

        try:
            self._runtime_launch_spec = launch_spec
            self._runtime_activation_id = activation_id
            self._publish_runtime(
                AssistantRuntimePhase.LOADING,
                activation_id=activation_id,
            )
            engine.config = new_config
            engine.switch_backend(launch_spec.backend_mode)
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_worker",
                operation="switch_backend",
            )
            engine.config = old_config
            if engine.active_backend is None:
                with contextlib.suppress(Exception):
                    engine.close()
                self.engine = None
            self._runtime_launch_spec = (
                launch_spec if self.engine is None else old_launch_spec
            )
            self._publish_runtime(
                AssistantRuntimePhase.FAILED,
                error=failure.message,
                launch_spec=launch_spec,
                activation_id=activation_id,
            )
            self.error.emit(f"Switch Failed: {failure.message}")
            return

        try:
            new_config.save_to_file()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_worker",
                operation="persist_switched_model",
            )
            self.error.emit(
                "Model switched for this session, but the setting could not be saved.",
            )

        if launch_spec.fallback_used:
            self.log.emit(redact_public_text(launch_spec.selection_detail))
        self.log.emit(
            f"Switched to local model: {redact_public_text(launch_spec.model_id)}"
        )
        self._publish_runtime(
            AssistantRuntimePhase.READY,
            activation_id=activation_id,
        )
        logger.info(
            "Model switch successful to local model %s",
            redact_public_text(launch_spec.model_id),
        )

    def shutdown(self, wait_ms: int = GENERATION_THREAD_SHUTDOWN_WAIT_MS) -> bool:
        """Stop generation work and release the loaded local model backend."""
        self._shutdown_requested = True
        if self.timeout_timer is not None:
            self.timeout_timer.stop()
        self._timed_out_generation = None
        if not self._cleanup_runtime_load(wait_ms=wait_ms):
            self.shutdown_finished.emit(False)
            return False
        stopped = self._cleanup_generation_thread(wait_ms=wait_ms)
        if not stopped:
            self.shutdown_finished.emit(False)
            return False
        if self.engine is not None:
            if not self._close_engine(self.engine, wait_ms=wait_ms):
                self.shutdown_finished.emit(False)
                return False
            self.engine = None
        self._runtime_launch_spec = None
        self._runtime_activation_id = 0
        self._publish_runtime(AssistantRuntimePhase.IDLE, activation_id=0)
        self.shutdown_finished.emit(True)
        return True

    def _emit_runtime_snapshot(
        self,
        *,
        launch_spec: AssistantRuntimeLaunchSpec | None = None,
        activation_id: int | None = None,
    ) -> None:
        """Publish runtime state without exposing worker-owned objects to the UI."""
        backend_mode = ""
        model_id = ""
        requested_model_id = ""
        selection_outcome = None
        selection_detail = ""
        execution_device = ""
        device_fallback_reason = ""
        launch_spec = launch_spec or self._runtime_launch_spec
        if launch_spec is not None:
            backend_mode = launch_spec.backend_mode
            model_id = redact_public_text(launch_spec.model_id)
            requested_model_id = redact_public_text(launch_spec.requested_model_id)
            selection_outcome = launch_spec.outcome
            selection_detail = redact_public_text(launch_spec.selection_detail)
            execution_device = redact_public_text(launch_spec.execution_device)
            device_fallback_reason = redact_public_text(
                launch_spec.device_fallback_reason
            )
        snapshot = AssistantRuntimeSnapshot(
            phase=self._runtime_phase,
            initialized=self.engine is not None,
            backend_mode=backend_mode,
            model_id=model_id,
            requested_model_id=requested_model_id,
            selection_outcome=selection_outcome,
            selection_detail=selection_detail,
            execution_device=execution_device,
            device_fallback_reason=device_fallback_reason,
            error=self._runtime_error,
            activation_id=(
                self._runtime_activation_id
                if activation_id is None
                else max(0, int(activation_id))
            ),
        )
        self.runtime_snapshot_changed.emit(snapshot)

    def _publish_runtime(
        self,
        phase: AssistantRuntimePhase,
        *,
        error: str = "",
        launch_spec: AssistantRuntimeLaunchSpec | None = None,
        activation_id: int | None = None,
    ) -> None:
        """Commit and publish one assistant runtime lifecycle transition."""
        self._runtime_phase = phase
        self._runtime_error = " ".join(redact_public_text(error or "").split())
        self._emit_runtime_snapshot(
            launch_spec=launch_spec,
            activation_id=activation_id,
        )

    @staticmethod
    def _activation_id(launch_spec: AssistantRuntimeLaunchSpec) -> int:
        try:
            activation_id = int(getattr(launch_spec, "activation_id", 0))
        except (TypeError, ValueError):
            return 0
        return max(0, activation_id)
