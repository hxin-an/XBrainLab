"""Owned subprocess boundary for local model loading and generation."""

from __future__ import annotations

import contextlib
import multiprocessing
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.generation import GenerationProfile

DEFAULT_PROCESS_STARTUP_TIMEOUT_SECONDS = 180.0
DEFAULT_PROCESS_TERMINATION_TIMEOUT_SECONDS = 0.25
DEFAULT_PROCESS_CLOSE_GRACE_SECONDS = 0.75
_EVENT_POLL_SECONDS = 0.05


class LocalRuntimeRestartRequiredError(RuntimeError):
    """The owned model process is gone and must be explicitly recreated."""


class LocalRuntimeTurnBusyError(RuntimeError):
    """A second generation was rejected while the process owns one turn."""


class LocalRuntimeLoadError(RuntimeError):
    """A redacted recoverable failure returned by the owned model process."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        recoverable: bool,
    ) -> None:
        super().__init__(message)
        self.error_code = str(error_code)
        self.recoverable = bool(recoverable)


class _LocalEngine(Protocol):
    config: LLMConfig

    def load_model(self) -> None: ...

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        profile: GenerationProfile,
    ) -> Iterator[str]: ...

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool: ...

    def close(self) -> bool: ...


EngineFactory = Callable[[LLMConfig], _LocalEngine]


@dataclass(frozen=True)
class _RuntimeCommand:
    kind: str
    generation_id: int = 0
    messages: tuple[dict[str, Any], ...] = ()
    profile: GenerationProfile | None = None
    live_settings: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class _RuntimeEvent:
    kind: str
    generation_id: int = 0
    payload: str = ""
    error_code: str = ""
    recoverable: bool = False


def _default_engine_factory(config: LLMConfig) -> _LocalEngine:
    return LLMEngine(config)


def _exception_label(exc: BaseException) -> str:
    """Return a non-sensitive child-process failure label."""
    return type(exc).__name__


def _runtime_load_failure_event(exc: BaseException) -> _RuntimeEvent:
    """Serialize only public-safe recovery guidance from expected load failures."""
    if isinstance(exc, ApplicationError) and exc.recoverable:
        return _RuntimeEvent(
            "load_error",
            payload=str(exc),
            error_code=exc.error_type.value,
            recoverable=True,
        )
    return _RuntimeEvent(
        "load_error",
        payload=f"Local model load failed ({_exception_label(exc)}).",
    )


def _monitor_generation_cancel(
    engine: _LocalEngine,
    cancel_connection: Any,
    generation_id: int,
    cancel_requested: threading.Event,
    monitor_finished: threading.Event,
) -> None:
    """Translate the process-shared stop flag to backend cooperative cancel."""
    while not monitor_finished.wait(0.01):
        if cancel_requested.is_set():
            with contextlib.suppress(BaseException):
                engine.cancel_generation(wait_timeout=0.05)
            return
        try:
            requested = cancel_connection.poll(0.01)
        except (EOFError, OSError):
            return
        if not requested:
            continue
        try:
            requested_generation_id = cancel_connection.recv()
        except (EOFError, OSError):
            return
        if requested_generation_id != generation_id:
            continue
        cancel_requested.set()


def _run_generation_command(
    engine: _LocalEngine,
    command: _RuntimeCommand,
    event_connection: Any,
    cancel_connection: Any,
) -> None:
    generation_id = command.generation_id
    if command.profile is None:
        event_connection.send(
            _RuntimeEvent(
                "generation_error",
                generation_id,
                "Local model generation received no decoding profile.",
            )
        )
        return
    for field_name, value in command.live_settings:
        setattr(engine.config, field_name, value)

    cancel_requested = threading.Event()
    with contextlib.suppress(EOFError, OSError):
        while cancel_connection.poll():
            if cancel_connection.recv() == generation_id:
                cancel_requested.set()
    monitor_finished = threading.Event()
    cancel_monitor = threading.Thread(
        target=_monitor_generation_cancel,
        args=(
            engine,
            cancel_connection,
            generation_id,
            cancel_requested,
            monitor_finished,
        ),
        daemon=True,
        name="LocalRuntimeCancelMonitor",
    )
    cancel_monitor.start()
    try:
        for chunk in engine.generate_stream(
            list(command.messages),
            profile=command.profile,
        ):
            if cancel_requested.is_set():
                break
            event_connection.send(_RuntimeEvent("chunk", generation_id, str(chunk)))
        terminal_kind = "cancelled" if cancel_requested.is_set() else "finished"
        event_connection.send(_RuntimeEvent(terminal_kind, generation_id))
    except BaseException as exc:
        with contextlib.suppress(EOFError, OSError):
            event_connection.send(
                _RuntimeEvent(
                    "generation_error",
                    generation_id,
                    f"Local model generation failed ({_exception_label(exc)}).",
                )
            )
    finally:
        monitor_finished.set()
        cancel_monitor.join(timeout=0.1)


def _local_runtime_process_main(
    config: LLMConfig,
    command_connection: Any,
    event_connection: Any,
    cancel_connection: Any,
    engine_factory: EngineFactory,
) -> None:
    """Load and serve one local engine entirely inside the owned process."""
    engine: _LocalEngine | None = None
    try:
        engine = engine_factory(config)
        engine.load_model()
    except BaseException as exc:
        event_connection.send(_runtime_load_failure_event(exc))
        if engine is not None:
            with contextlib.suppress(BaseException):
                engine.close()
        return

    event_connection.send(_RuntimeEvent("loaded"))
    while True:
        try:
            command = command_connection.recv()
        except (EOFError, OSError):
            break
        if not isinstance(command, _RuntimeCommand):
            continue
        if command.kind == "generate":
            _run_generation_command(
                engine,
                command,
                event_connection,
                cancel_connection,
            )
            continue
        if command.kind != "close":
            continue
        try:
            closed = engine.close()
        except BaseException as exc:
            event_connection.send(
                _RuntimeEvent(
                    "close_error",
                    payload=f"Local model close failed ({_exception_label(exc)}).",
                )
            )
            return
        event_connection.send(
            _RuntimeEvent("closed" if closed is not False else "close_error")
        )
        return


class LocalRuntimeProcessOwner:
    """Supervise one spawn-based local model process and its turn lease.

    Cooperative cancellation receives the caller-provided grace. If generation
    is still live when that grace expires, only this owner's process handle is
    terminated. The owner is then fenced and cannot generate again; an explicit
    runtime Retry must construct a fresh owner.
    """

    uses_owned_process = True
    _LIVE_SETTING_FIELDS = (
        "temperature",
        "top_p",
        "max_new_tokens",
        "do_sample",
    )

    def __init__(
        self,
        config: LLMConfig,
        *,
        engine_factory: EngineFactory = _default_engine_factory,
        startup_timeout: float = DEFAULT_PROCESS_STARTUP_TIMEOUT_SECONDS,
        termination_timeout: float = DEFAULT_PROCESS_TERMINATION_TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self._engine_factory = engine_factory
        self._startup_timeout = max(0.01, float(startup_timeout))
        self._termination_timeout = max(0.01, float(termination_timeout))
        self._context = multiprocessing.get_context("spawn")
        self._process: Any | None = None
        self._command_connection: Any | None = None
        self._event_connection: Any | None = None
        self._cancel_connection: Any | None = None
        self._state_lock = threading.Lock()
        self._generation_active = threading.Event()
        self._generation_done = threading.Event()
        self._loading = threading.Event()
        self._transport_ready = threading.Event()
        self._close_requested = threading.Event()
        self._active_generation_id: int | None = None
        self._generation_sequence = 0
        self._initialized = False
        self._closed = False
        self._restart_required = False
        self._last_terminated_pid: int | None = None

    @property
    def active_backend(self) -> LocalRuntimeProcessOwner | None:
        """Compatibility readiness marker used by the worker switch path."""
        return self if self._initialized and self.is_alive else None

    @property
    def restart_required(self) -> bool:
        return self._restart_required

    @property
    def is_alive(self) -> bool:
        process = self._process
        return bool(
            self._transport_ready.is_set()
            and process is not None
            and process.is_alive()
        )

    @property
    def pid(self) -> int | None:
        process = self._process
        return None if process is None else process.pid

    @property
    def last_terminated_pid(self) -> int | None:
        return self._last_terminated_pid

    def wait_until_generation_active(self, timeout: float) -> bool:
        """Wait for the parent-side turn lease; intended for lifecycle tests."""
        return self._generation_active.wait(max(0.0, float(timeout)))

    def wait_until_process_started(self, timeout: float) -> bool:
        """Wait for the owned transport to start; intended for lifecycle tests."""
        return self._transport_ready.wait(max(0.0, float(timeout)))

    def load_model(self) -> None:
        if self._restart_required:
            raise LocalRuntimeRestartRequiredError(
                "The local model process must be recreated."
            )
        if self._initialized and self.is_alive:
            return
        self._closed = False
        self._close_requested.clear()
        self._loading.set()
        try:
            self._create_transport()
            event = self._wait_for_runtime_event(
                deadline=time.monotonic() + self._startup_timeout,
            )
            if event is not None and event.kind == "loaded":
                self._initialized = True
                return
            if self._close_requested.is_set():
                raise RuntimeError("Local model process closed during startup.")
            self._terminate_owned_process(restart_required=True)
            if event is None:
                raise TimeoutError("Local model process startup timed out.")
            if event.recoverable:
                raise LocalRuntimeLoadError(
                    event.payload,
                    error_code=event.error_code,
                    recoverable=True,
                )
            raise RuntimeError(event.payload or "Local model process failed to start.")
        finally:
            self._loading.clear()

    def switch_backend(self, mode: str) -> None:
        """Replace the process after the worker updates this owner's config."""
        del mode
        if not self.close(wait_timeout=DEFAULT_PROCESS_CLOSE_GRACE_SECONDS):
            raise RuntimeError("The previous local model process did not close.")
        self._restart_required = False
        self._closed = False
        self.load_model()

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        profile: GenerationProfile,
    ) -> Iterator[str]:
        generation_id = self._begin_generation()
        command_connection = self._require_command_connection()
        command_connection.send(
            _RuntimeCommand(
                kind="generate",
                generation_id=generation_id,
                messages=tuple(dict(message) for message in messages),
                profile=profile,
                live_settings=tuple(
                    (field_name, getattr(self.config, field_name))
                    for field_name in self._LIVE_SETTING_FIELDS
                ),
            )
        )
        try:
            while True:
                event = self._next_generation_event(generation_id)
                if event.kind == "chunk":
                    yield event.payload
                    continue
                if event.kind in {"finished", "cancelled"}:
                    return
                if event.kind == "generation_error":
                    raise RuntimeError(
                        event.payload or "Local model generation failed."
                    )
        finally:
            self._finish_generation(generation_id)

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        """Cooperate briefly, then terminate only this owner's live process."""
        with self._state_lock:
            generation_id = self._active_generation_id
        if generation_id is None:
            return not self._restart_required
        cancel_connection = self._cancel_connection
        if cancel_connection is not None:
            with contextlib.suppress(BrokenPipeError, EOFError, OSError):
                cancel_connection.send(generation_id)
        if self._generation_done.wait(max(0.0, float(wait_timeout))):
            return True
        with self._state_lock:
            if self._active_generation_id != generation_id:
                return True
        self._terminate_owned_process(restart_required=True)
        return not self.is_alive

    def close(
        self,
        wait_timeout: float = DEFAULT_PROCESS_CLOSE_GRACE_SECONDS,
    ) -> bool:
        """Release or terminate the owned process within a fixed bound."""
        if self._closed and not self.is_alive:
            return True
        grace = max(0.0, float(wait_timeout))
        self._close_requested.set()
        if self._process is not None and not self._transport_ready.wait(grace):
            return False
        if self._active_generation_id is not None:
            self.cancel_generation(wait_timeout=grace)
        process = self._process
        if process is None or not process.is_alive():
            self._initialized = False
            self._closed = True
            self._dispose_connections()
            return True

        command_connection = self._command_connection
        if command_connection is not None:
            with contextlib.suppress(BrokenPipeError, EOFError, OSError):
                command_connection.send(_RuntimeCommand(kind="close"))
        if self._loading.is_set() or self._active_generation_id is not None:
            process.join(timeout=grace)
            if process.is_alive():
                self._terminate_owned_process(restart_required=False)
            self._initialized = False
            self._closed = True
            self._dispose_connections()
            return not self.is_alive
        deadline = time.monotonic() + grace
        event = self._wait_for_runtime_event(deadline=deadline)
        clean = event is not None and event.kind == "closed"
        remaining = max(0.0, deadline - time.monotonic())
        process.join(timeout=remaining)
        clean_exit_without_event = bool(
            event is None
            and not process.is_alive()
            and getattr(process, "exitcode", None) == 0
        )
        if process.is_alive():
            self._terminate_owned_process(restart_required=False)
        self._initialized = False
        self._closed = True
        self._dispose_connections()
        return not self.is_alive and (
            clean or clean_exit_without_event or self._last_terminated_pid is not None
        )

    def _create_transport(self) -> None:
        self._dispose_connections()
        self._transport_ready.clear()
        child_command, self._command_connection = self._context.Pipe(duplex=False)
        self._event_connection, child_event = self._context.Pipe(duplex=False)
        child_cancel, self._cancel_connection = self._context.Pipe(duplex=False)
        self._process = self._context.Process(
            target=_local_runtime_process_main,
            args=(
                self.config,
                child_command,
                child_event,
                child_cancel,
                self._engine_factory,
            ),
            name="XBrainLabLocalModel",
            daemon=True,
        )
        self._process.start()
        child_command.close()
        child_event.close()
        child_cancel.close()
        self._transport_ready.set()
        if self._close_requested.is_set():
            self._terminate_owned_process(restart_required=False)

    def _begin_generation(self) -> int:
        with self._state_lock:
            if self._restart_required:
                raise LocalRuntimeRestartRequiredError(
                    "The local model process must be recreated."
                )
            if not self._initialized or not self.is_alive:
                self._restart_required = True
                raise LocalRuntimeRestartRequiredError(
                    "The local model process is unavailable."
                )
            if self._active_generation_id is not None:
                raise LocalRuntimeTurnBusyError(
                    "The local model process already owns a generation."
                )
            self._generation_sequence += 1
            generation_id = self._generation_sequence
            self._active_generation_id = generation_id
            self._generation_done.clear()
            self._generation_active.set()
            return generation_id

    def _finish_generation(self, generation_id: int) -> None:
        with self._state_lock:
            if self._active_generation_id != generation_id:
                return
            self._active_generation_id = None
            self._generation_active.clear()
            self._generation_done.set()

    def _next_generation_event(self, generation_id: int) -> _RuntimeEvent:
        while True:
            event = self._wait_for_runtime_event(
                deadline=time.monotonic() + _EVENT_POLL_SECONDS,
            )
            if event is not None:
                if event.generation_id in {0, generation_id}:
                    return event
                continue
            if self._restart_required or not self.is_alive:
                self._restart_required = True
                raise LocalRuntimeRestartRequiredError(
                    "The local model process stopped and must be recreated."
                )

    def _wait_for_runtime_event(self, *, deadline: float) -> _RuntimeEvent | None:
        event_connection = self._event_connection
        if event_connection is None:
            return None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                available = event_connection.poll(min(_EVENT_POLL_SECONDS, remaining))
                if not available:
                    # On Windows the process handle can become non-live before
                    # its final pipe payload becomes observable. Keep draining
                    # until the caller's existing deadline instead of losing a
                    # clean terminal event and treating shutdown as forced.
                    continue
                event = event_connection.recv()
            except (EOFError, OSError):
                return None
            if isinstance(event, _RuntimeEvent):
                return event

    def _require_command_connection(self) -> Any:
        command_connection = self._command_connection
        if command_connection is None:
            raise LocalRuntimeRestartRequiredError(
                "The local model process command channel is unavailable."
            )
        return command_connection

    def _terminate_owned_process(self, *, restart_required: bool) -> None:
        """Terminate through this owner's process handle, never by PID search."""
        process = self._process
        if restart_required:
            self._restart_required = True
        self._initialized = False
        if process is None:
            self._generation_done.set()
            return
        pid = process.pid
        if process.is_alive():
            self._last_terminated_pid = pid
            with contextlib.suppress(BaseException):
                process.terminate()
            process.join(timeout=self._termination_timeout)
        if process.is_alive():
            self._last_terminated_pid = pid
            kill = getattr(process, "kill", None)
            if callable(kill):
                with contextlib.suppress(BaseException):
                    kill()
            process.join(timeout=self._termination_timeout)
        self._generation_done.set()

    def _dispose_connections(self) -> None:
        for channel in (
            self._command_connection,
            self._event_connection,
            self._cancel_connection,
        ):
            if channel is None:
                continue
            with contextlib.suppress(BaseException):
                channel.close()
        self._command_connection = None
        self._event_connection = None
        self._cancel_connection = None
