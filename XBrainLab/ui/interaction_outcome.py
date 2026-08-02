"""UI-neutral outcomes for product interactions and dialog handoffs."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any

from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.public_diagnostics import (
    DiagnosticTextLayout,
    public_diagnostic_text,
)


class InteractionStatus(str, Enum):
    """Completion state of one user-triggered UI interaction."""

    COMPLETED = "completed"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class InteractionOutcome:
    """Explicit result returned by UI actions without coupling to any host.

    ``ACCEPTED`` means a dialog was accepted or an asynchronous command was
    successfully scheduled. It must not be treated as proof that the command
    completed. Only ``COMPLETED`` records a synchronously observed success.
    """

    status: InteractionStatus
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message",
            public_diagnostic_text(
                self.message,
                layout=DiagnosticTextLayout.SINGLE_LINE,
            ),
        )

    @property
    def is_completed(self) -> bool:
        return self.status is InteractionStatus.COMPLETED

    @classmethod
    def completed(cls, message: str = "") -> InteractionOutcome:
        return cls(InteractionStatus.COMPLETED, message)

    @classmethod
    def accepted(cls, message: str = "") -> InteractionOutcome:
        return cls(InteractionStatus.ACCEPTED, message)

    @classmethod
    def cancelled(cls, message: str = "") -> InteractionOutcome:
        return cls(InteractionStatus.CANCELLED, message)

    @classmethod
    def blocked(cls, message: str = "") -> InteractionOutcome:
        return cls(InteractionStatus.BLOCKED, message)

    @classmethod
    def failed(cls, message: str = "") -> InteractionOutcome:
        return cls(InteractionStatus.FAILED, message)


class InteractionCompletionStatus(str, Enum):
    """Terminal status reported by one asynchronous product UI command."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class InteractionCompletionEvent:
    """Request-correlated terminal callback from a product UI command."""

    request_id: str
    command_name: str
    status: InteractionCompletionStatus
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, InteractionCompletionStatus):
            raise TypeError("Interaction completion status must be typed.")
        for field_name in ("request_id", "command_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Interaction completion {field_name} cannot be empty."
                )
            object.__setattr__(self, field_name, value.strip())
        object.__setattr__(
            self,
            "message",
            public_diagnostic_text(
                self.message or "",
                layout=DiagnosticTextLayout.SINGLE_LINE,
            ),
        )


InteractionCompletionCallback = Callable[[InteractionCompletionEvent], None]


class InteractionCommandCallbacks:
    """Callbacks for one command captured by an interaction completion session."""

    def __init__(
        self,
        *,
        session: InteractionCompletionSession | None,
        result_command_name: str,
        context: object,
        on_result: Callable[[CommandResult], InteractionOutcome | None],
        on_error: Callable[[tuple], None] | None,
    ) -> None:
        self._session = session
        self._result_command_name = result_command_name
        self._context = context
        self._on_result = on_result
        self._on_error = on_error
        self._started = False
        self._settled = False

    @property
    def on_result(self) -> Callable[[CommandResult], None]:
        return self._handle_result

    @property
    def on_error(self) -> Callable[[tuple], None] | None:
        if self._on_error is None and self._session is None:
            return None
        return self._handle_error

    @property
    def on_finished(self) -> Callable[[], None]:
        """Return the worker-finished callback that closes missing outcomes."""
        return self._handle_finished

    def mark_started(self, started: bool) -> None:
        """Record ownership only after the async runner accepted the command."""
        if not started or self._session is None or self._started:
            return
        self._started = True
        self._session._command_started(self._context)

    def _handle_result(self, result: CommandResult) -> None:
        if self._session is None:
            self._on_result(result)
            return
        if self._settled or self._session.is_terminal:
            self._settled = True
            return
        if not isinstance(result, CommandResult):
            self._settle(
                InteractionCompletionStatus.FAILED,
                "The asynchronous UI command returned an invalid result.",
            )
            return
        if str(result.command_name or "").strip().lower() != self._result_command_name:
            logger.warning(
                "Rejected mismatched async UI result %s while waiting for %s",
                result.command_name,
                self._result_command_name,
            )
            self._settle(
                InteractionCompletionStatus.FAILED,
                "The asynchronous UI command result did not match the scheduled "
                "command.",
            )
            return
        try:
            with bind_interaction_completion(self._session):
                callback_outcome = self._on_result(result)
        except Exception:
            logger.exception("Asynchronous UI command callback failed")
            self._settle(
                InteractionCompletionStatus.FAILED,
                "The asynchronous UI command callback failed.",
            )
            return
        if callback_outcome is not None:
            self._settle_callback_outcome(callback_outcome)
            return
        self._settle(
            (
                InteractionCompletionStatus.FAILED
                if result.failed
                else InteractionCompletionStatus.COMPLETED
            ),
            result.message,
        )

    def _settle_callback_outcome(self, outcome: object) -> None:
        """Apply the callback's typed ownership decision to this command."""
        if not isinstance(outcome, InteractionOutcome):
            self._settle(
                InteractionCompletionStatus.FAILED,
                "The asynchronous UI callback returned an invalid outcome.",
            )
            return
        if outcome.status is InteractionStatus.ACCEPTED:
            self._handoff()
            return
        if outcome.status is InteractionStatus.CANCELLED:
            self._settle(InteractionCompletionStatus.CANCELLED, outcome.message)
            return
        if outcome.status is InteractionStatus.COMPLETED:
            self._settle(InteractionCompletionStatus.COMPLETED, outcome.message)
            return
        self._settle(InteractionCompletionStatus.FAILED, outcome.message)

    def _handle_error(self, error: tuple) -> None:
        if self._session is None:
            if self._on_error is not None:
                self._on_error(error)
            return
        if self._settled or self._session.is_terminal:
            self._settled = True
            return
        try:
            if self._on_error is not None:
                with bind_interaction_completion(self._session):
                    self._on_error(error)
        except Exception:
            logger.exception("Asynchronous UI error callback failed")
        self._settle(
            InteractionCompletionStatus.FAILED,
            "The asynchronous UI command failed.",
        )

    def _handle_finished(self) -> None:
        """Fail a started command that produced no deliverable result or error."""
        if self._session is None or self._settled:
            return
        if self._session.is_terminal:
            self._settled = True
            return
        self._settle(
            InteractionCompletionStatus.FAILED,
            "The asynchronous UI command finished without returning a result.",
        )

    def _settle(
        self,
        status: InteractionCompletionStatus,
        message: str,
    ) -> None:
        if self._settled:
            return
        self._settled = True
        if self._started and self._session is not None:
            self._session._command_finished(status, message)

    def _handoff(self) -> None:
        if self._settled:
            return
        self._settled = True
        if self._started and self._session is not None:
            self._session._command_handed_off()


class InteractionCompletionSession:
    """Own callback correlation across one possibly chained async UI action."""

    def __init__(
        self,
        *,
        request_id: str,
        command_name: str,
        on_terminal: InteractionCompletionCallback,
    ) -> None:
        normalized_request_id = str(request_id or "").strip()
        normalized_command_name = str(command_name or "").strip().lower()
        if not normalized_request_id or not normalized_command_name:
            raise ValueError("Interaction completion identity cannot be empty.")
        if not callable(on_terminal):
            raise TypeError("Interaction completion callback must be callable.")
        self.request_id = normalized_request_id
        self.command_name = normalized_command_name
        self._on_terminal = on_terminal
        self._active_commands = 0
        self._scheduled_commands = 0
        self._pending_continuations = 0
        self._deferred_completion_message = ""
        self._terminal_event: InteractionCompletionEvent | None = None
        self._watched_context_ids: set[int] = set()
        self._lock = RLock()

    @property
    def has_scheduled_command(self) -> bool:
        with self._lock:
            return self._scheduled_commands > 0

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._terminal_event is not None

    @property
    def terminal_event(self) -> InteractionCompletionEvent | None:
        with self._lock:
            return self._terminal_event

    def prepare_command(
        self,
        *,
        context: object,
        on_result: Callable[[CommandResult], InteractionOutcome | None],
        on_error: Callable[[tuple], None] | None,
        result_command_name: str | None = None,
    ) -> InteractionCommandCallbacks:
        """Wrap one real async command callback with this request identity."""
        if not callable(on_result):
            raise TypeError("Async interaction result callback must be callable.")
        if on_error is not None and not callable(on_error):
            raise TypeError("Async interaction error callback must be callable.")
        normalized_result_command = (
            str(result_command_name or self.command_name).strip().lower()
        )
        if not normalized_result_command:
            raise ValueError("Async interaction result command cannot be empty.")
        return InteractionCommandCallbacks(
            session=self,
            result_command_name=normalized_result_command,
            context=context,
            on_result=on_result,
            on_error=on_error,
        )

    def reserve_continuation(self) -> InteractionContinuationLease | None:
        """Reserve ownership for a follow-up dispatched after this callback returns."""
        with self._lock:
            if self._terminal_event is not None or self._active_commands == 0:
                return None
            self._pending_continuations += 1
        return InteractionContinuationLease(self)

    def cancel(self, message: str, *, notify: bool = True) -> None:
        """Cancel or abandon the session so late callbacks become harmless."""
        self._finish(
            InteractionCompletionStatus.CANCELLED,
            message,
            notify=notify,
        )

    def _command_started(self, context: object) -> None:
        with self._lock:
            if self._terminal_event is not None:
                return
            self._active_commands += 1
            self._scheduled_commands += 1
        self._watch_context(context)

    def _command_finished(
        self,
        status: InteractionCompletionStatus,
        message: str,
    ) -> None:
        should_finish = False
        with self._lock:
            if self._terminal_event is not None:
                return
            self._active_commands = max(0, self._active_commands - 1)
            should_finish = status is not InteractionCompletionStatus.COMPLETED or (
                self._active_commands == 0 and self._pending_continuations == 0
            )
            if (
                status is InteractionCompletionStatus.COMPLETED
                and self._active_commands == 0
                and self._pending_continuations > 0
            ):
                self._deferred_completion_message = message
        if should_finish:
            self._finish(status, message)

    def _command_handed_off(self) -> None:
        """Release one command only when another command already owns the session."""
        has_successor = False
        with self._lock:
            if self._terminal_event is not None:
                return
            self._active_commands = max(0, self._active_commands - 1)
            has_successor = self._active_commands > 0 or self._pending_continuations > 0
        if not has_successor:
            self._finish(
                InteractionCompletionStatus.FAILED,
                "The UI command did not start its reported follow-up action.",
            )

    def _can_start_continuation(self) -> bool:
        with self._lock:
            return self._terminal_event is None and self._pending_continuations > 0

    def _continuation_start_finished(
        self,
        outcome: object,
        *,
        scheduled_before: int,
    ) -> bool:
        finish: tuple[InteractionCompletionStatus, str] | None = None
        accepted = False
        with self._lock:
            if self._terminal_event is not None:
                return False
            self._pending_continuations = max(0, self._pending_continuations - 1)
            if not isinstance(outcome, InteractionOutcome):
                finish = (
                    InteractionCompletionStatus.FAILED,
                    "The confirmed UI retry returned an invalid outcome.",
                )
            elif outcome.status is InteractionStatus.ACCEPTED:
                accepted = self._scheduled_commands > scheduled_before
                if not accepted:
                    finish = (
                        InteractionCompletionStatus.FAILED,
                        "The confirmed UI retry did not start its command.",
                    )
                elif (
                    self._active_commands == 0
                    and self._pending_continuations == 0
                    and self._deferred_completion_message
                ):
                    finish = (
                        InteractionCompletionStatus.COMPLETED,
                        self._deferred_completion_message,
                    )
            elif outcome.status is InteractionStatus.COMPLETED:
                accepted = True
                finish = (InteractionCompletionStatus.COMPLETED, outcome.message)
            elif outcome.status is InteractionStatus.CANCELLED:
                finish = (InteractionCompletionStatus.CANCELLED, outcome.message)
            else:
                finish = (
                    InteractionCompletionStatus.FAILED,
                    outcome.message or "The confirmed UI retry could not be started.",
                )
        if finish is not None:
            self._finish(*finish)
        return accepted and (
            finish is None or finish[0] is InteractionCompletionStatus.COMPLETED
        )

    def _continuation_failed(self, message: str) -> bool:
        with self._lock:
            if self._terminal_event is not None:
                return False
            self._pending_continuations = max(0, self._pending_continuations - 1)
        self._finish(
            InteractionCompletionStatus.FAILED,
            message or "The confirmed UI retry could not be started.",
        )
        return True

    def _scheduled_command_count(self) -> int:
        with self._lock:
            return self._scheduled_commands

    def _watch_context(self, context: object) -> None:
        context_id = id(context)
        with self._lock:
            if context_id in self._watched_context_ids:
                return
            self._watched_context_ids.add(context_id)
        destroyed = getattr(context, "destroyed", None)
        connect = getattr(destroyed, "connect", None)
        if not callable(connect):
            return

        def _context_destroyed(*_args: Any) -> None:
            self._finish(
                InteractionCompletionStatus.FAILED,
                "The settings surface closed before its command callback completed.",
            )

        try:
            connect(_context_destroyed)
        except (RuntimeError, TypeError):
            self._finish(
                InteractionCompletionStatus.FAILED,
                "The settings surface was unavailable for command completion.",
            )

    def _finish(
        self,
        status: InteractionCompletionStatus,
        message: str,
        *,
        notify: bool = True,
    ) -> None:
        event = InteractionCompletionEvent(
            request_id=self.request_id,
            command_name=self.command_name,
            status=status,
            message=message,
        )
        with self._lock:
            if self._terminal_event is not None:
                return
            self._terminal_event = event
            self._active_commands = 0
            self._pending_continuations = 0
        if not notify:
            return
        try:
            self._on_terminal(event)
        except Exception:
            logger.exception("Interaction completion delivery callback failed")


class InteractionContinuationLease:
    """One-shot ownership for a follow-up command scheduled on a later UI turn."""

    def __init__(self, session: InteractionCompletionSession) -> None:
        self._session = session
        self._claimed = False
        self._lock = RLock()

    def start(
        self,
        callback: Callable[[], InteractionOutcome | None],
    ) -> bool:
        """Bind the session explicitly while starting exactly one continuation."""
        if not callable(callback):
            raise TypeError("Interaction continuation callback must be callable.")
        if not self._claim() or not self._session._can_start_continuation():
            return False
        scheduled_before = self._session._scheduled_command_count()
        try:
            with bind_interaction_completion(self._session):
                outcome = callback()
        except Exception:
            logger.exception("Confirmed UI retry callback failed")
            self._session._continuation_failed(
                "The confirmed UI retry callback failed.",
            )
            return False
        return self._session._continuation_start_finished(
            outcome,
            scheduled_before=scheduled_before,
        )

    def fail(self, message: str) -> bool:
        """Fail a continuation that cannot be started, exactly once."""
        if not self._claim():
            return False
        return self._session._continuation_failed(message)

    def _claim(self) -> bool:
        with self._lock:
            if self._claimed:
                return False
            self._claimed = True
            return True


_ACTIVE_INTERACTION_COMPLETION: ContextVar[InteractionCompletionSession | None] = (
    ContextVar("active_interaction_completion", default=None)
)


@contextmanager
def bind_interaction_completion(
    session: InteractionCompletionSession,
) -> Iterator[None]:
    """Bind async commands scheduled in this scope to one handoff session."""
    if not isinstance(session, InteractionCompletionSession):
        raise TypeError("Interaction completion binding requires a typed session.")
    token = _ACTIVE_INTERACTION_COMPLETION.set(session)
    try:
        yield
    finally:
        _ACTIVE_INTERACTION_COMPLETION.reset(token)


def current_interaction_completion() -> InteractionCompletionSession | None:
    """Return the request session inherited by the current UI callback scope."""
    return _ACTIVE_INTERACTION_COMPLETION.get()


def reserve_interaction_continuation() -> InteractionContinuationLease | None:
    """Reserve explicit ownership for a retry dispatched after this UI callback."""
    session = current_interaction_completion()
    if session is None:
        return None
    return session.reserve_continuation()


def prepare_interaction_command_callbacks(
    *,
    context: object,
    command_name: str,
    on_result: Callable[[CommandResult], InteractionOutcome | None],
    on_error: Callable[[tuple], None] | None,
) -> InteractionCommandCallbacks:
    """Capture current handoff correlation or return transparent callbacks."""
    session = current_interaction_completion()
    if session is not None:
        return session.prepare_command(
            context=context,
            on_result=on_result,
            on_error=on_error,
            result_command_name=command_name,
        )
    return InteractionCommandCallbacks(
        session=None,
        result_command_name=str(command_name or "").strip().lower(),
        context=context,
        on_result=on_result,
        on_error=on_error,
    )
