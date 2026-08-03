"""Exception-safe Qt thread-pool ownership for application commands."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from threading import Lock
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThreadPool, pyqtSlot

from XBrainLab.backend.application.commands import Command
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.worker import PythonThreadWorker, Worker
from XBrainLab.ui.refresh_coordinator import (
    refresh_after_command,
    suppress_observer_refresh_during_command,
)


class AsyncCommandDelivery(QObject):
    """Deliver callbacks only while the owning Qt context remains usable."""

    def __init__(
        self,
        *,
        context: Any,
        command: Command,
        on_result: Callable[[CommandResult], None],
        on_error: Callable[[tuple], None] | None,
        refresh: bool,
        allow_during_shutdown: bool,
        parent: QObject | None,
    ) -> None:
        super().__init__(parent)
        self._context = context
        self._command = command
        self._on_result = on_result
        self._on_error = on_error
        self._refresh = refresh
        self._allow_during_shutdown = allow_during_shutdown

    @pyqtSlot(object)
    def handle_result(self, result: CommandResult) -> None:
        """Deliver one result on the receiver's GUI thread."""
        if qt_object_deleted(self._context) or (
            not self._allow_during_shutdown and context_is_closing(self._context)
        ):
            return
        if self._refresh:
            try:
                refresh_after_command(self._context, result)
            except Exception:
                logger.exception("Async command UI refresh callback failed")
        try:
            self._on_result(result)
        except Exception:
            logger.exception("Async command result callback failed")

    @pyqtSlot(tuple)
    def handle_error(self, error: tuple) -> None:
        """Log and deliver one worker error while the receiver is alive."""
        message = error[1] if len(error) > 1 else error
        formatted_traceback = error[2] if len(error) > 2 else ""
        logger.error(
            "Async application command failed: %s: %s",
            self._command.name,
            message,
        )
        if formatted_traceback:
            logger.debug(
                "Async application command traceback:\n%s",
                formatted_traceback,
            )
        if (
            self._on_error is not None
            and not qt_object_deleted(self._context)
            and (self._allow_during_shutdown or not context_is_closing(self._context))
        ):
            try:
                self._on_error(error)
            except Exception:
                logger.exception("Async command error callback failed")


class AsyncCommandCleanup(QObject):
    """Serialize outcome delivery and cleanup independently from UI deletion."""

    def __init__(self, finish: Callable[[], None]) -> None:
        super().__init__()
        self._finish = finish
        self._delivery: AsyncCommandDelivery | None = None
        self._outcome_in_progress = False
        self._finish_pending = False
        self._finished = False

    def bind_delivery(self, delivery: AsyncCommandDelivery) -> None:
        """Bind the disposable screen receiver before worker signals are connected."""
        self._delivery = delivery

    @pyqtSlot(object)
    def handle_result(self, result: CommandResult) -> None:
        """Deliver a result before allowing the worker to settle cleanup."""
        self._deliver(lambda delivery: delivery.handle_result(result))

    @pyqtSlot(tuple)
    def handle_error(self, error: tuple) -> None:
        """Deliver an error before allowing the worker to settle cleanup."""
        self._deliver(lambda delivery: delivery.handle_error(error))

    @pyqtSlot()
    def handle_finished(self) -> None:
        """Release ownership after any nested outcome callback has returned."""
        if self._finished:
            return
        if self._outcome_in_progress:
            self._finish_pending = True
            return
        self._finish_now()

    def _deliver(
        self,
        callback: Callable[[AsyncCommandDelivery], None],
    ) -> None:
        if self._finished:
            return
        self._outcome_in_progress = True
        try:
            delivery = self._delivery
            if delivery is not None and not qt_object_deleted(delivery):
                callback(delivery)
        finally:
            self._outcome_in_progress = False
            if self._finish_pending:
                self._finish_now()

    def _finish_now(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._finish_pending = False
        self._delivery = None
        finish = self._finish
        self._finish = lambda: None
        try:
            finish()
        finally:
            if not qt_object_deleted(self):
                self.deleteLater()


class AsyncCommandRegistry:
    """Own active command handles independently from transient Qt widgets."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._handles: list[AsyncCommandHandle] = []

    def register(self, handle: AsyncCommandHandle) -> None:
        with self._lock:
            self._handles.append(handle)

    def release(self, handle: AsyncCommandHandle) -> None:
        with self._lock, suppress(ValueError):
            self._handles.remove(handle)

    def active_count(self, context: Any | None = None) -> int:
        """Return active command count, optionally scoped to one UI context."""
        with self._lock:
            if context is None:
                return len(self._handles)
            return sum(handle.context is context for handle in self._handles)


class AsyncBusyStateCoordinator:
    """Reference-count busy state across chained commands sharing one target."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[int, int] = {}

    def acquire(self, target: Any) -> bool:
        """Acquire one busy lease and notify the target on the first lease."""
        set_busy = getattr(target, "set_busy", None)
        if not callable(set_busy):
            return False
        target_id = id(target)
        with self._lock:
            current = self._counts.get(target_id, 0)
            if current == 0:
                set_busy(True)
            self._counts[target_id] = current + 1
        return True

    def release(self, target: Any) -> None:
        """Release one lease and clear the target only after the final command."""
        target_id = id(target)
        should_clear = False
        with self._lock:
            current = self._counts.get(target_id, 0)
            if current <= 1:
                self._counts.pop(target_id, None)
                should_clear = current == 1
            else:
                self._counts[target_id] = current - 1
        if not should_clear or qt_object_deleted(target):
            return
        set_busy = getattr(target, "set_busy", None)
        if callable(set_busy):
            set_busy(False)

    def active_count(self, target: Any) -> int:
        """Return current busy lease count for lifecycle tests and diagnostics."""
        with self._lock:
            return self._counts.get(id(target), 0)


class AsyncCommandHandle:
    """Retain one worker and its Qt receivers until terminal cleanup."""

    def __init__(
        self,
        *,
        context: Any,
        worker: Worker | PythonThreadWorker,
        registry: AsyncCommandRegistry,
    ) -> None:
        self.context = context
        self.worker = worker
        self.registry = registry
        self.finished = False
        self._registered = False
        self._receivers: list[QObject] = []

    def register(self) -> None:
        # Mark ownership before invoking an injected registry. If registration
        # appends and then raises, ``finish`` can still roll the handle back.
        self._registered = True
        try:
            self.registry.register(self)
        except Exception:
            self.registry.release(self)
            self._registered = False
            raise

    def retain(self, receiver: QObject) -> None:
        self._receivers.append(receiver)

    def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        for receiver in tuple(self._receivers):
            if not qt_object_deleted(receiver):
                with suppress(RuntimeError):
                    receiver.deleteLater()
        self._receivers.clear()
        if self._registered:
            self.registry.release(self)
            self._registered = False


_APPLICATION_COMMAND_REGISTRY = AsyncCommandRegistry()
_ASYNC_BUSY_STATE = AsyncBusyStateCoordinator()


def application_command_registry() -> AsyncCommandRegistry:
    """Return the process registry used for async command lifetime ownership."""
    return _APPLICATION_COMMAND_REGISTRY


class QtApplicationCommandRunner:
    """Own async command setup and roll back every partial setup state."""

    def __init__(
        self,
        *,
        context: Any,
        command: Command,
        execute: Callable[[], CommandResult],
        on_result: Callable[[CommandResult], None],
        on_error: Callable[[tuple], None] | None,
        on_finished: Callable[[], None] | None = None,
        refresh: bool,
        busy_target: Any | None,
        allow_during_shutdown: bool,
        delivery_factory: Callable[..., AsyncCommandDelivery] | None = None,
        cleanup_factory: Callable[[Callable[[], None]], AsyncCommandCleanup]
        | None = None,
        thread_pool_factory: Callable[[], QThreadPool | None] | None = None,
        worker_factory: Callable[[Callable[[], CommandResult]], Worker] | None = None,
        python_worker_factory: (
            Callable[[Callable[[], CommandResult], str], PythonThreadWorker] | None
        ) = None,
        python_thread_name: str | None = None,
        registry: AsyncCommandRegistry | None = None,
    ) -> None:
        self.context = context
        self.command = command
        self.execute = execute
        self.on_result = on_result
        self.on_error = on_error
        self.on_finished = on_finished
        self.refresh = refresh
        self.busy_target = busy_target if busy_target is not None else context
        self.allow_during_shutdown = allow_during_shutdown
        self.delivery_factory = delivery_factory or AsyncCommandDelivery
        self.cleanup_factory = cleanup_factory or AsyncCommandCleanup
        self.thread_pool_factory = thread_pool_factory or QThreadPool.globalInstance
        self.worker_factory = worker_factory or Worker
        self.python_worker_factory = python_worker_factory or (
            lambda execute, name: PythonThreadWorker(execute, name=name)
        )
        self.python_thread_name = python_thread_name
        self.registry = registry or application_command_registry()

    def start(self) -> bool:
        """Prepare and start one worker, rolling back all partial ownership."""
        target = self.busy_target
        suppression = None
        suppression_entered = False
        busy_acquired = False
        worker: Worker | PythonThreadWorker | None = None
        handle: AsyncCommandHandle | None = None
        worker_finished = False

        def finish_worker() -> None:
            nonlocal worker_finished
            if worker_finished:
                return
            worker_finished = True
            if suppression_entered and suppression is not None:
                with suppress(Exception):
                    suppression.__exit__(None, None, None)
            if busy_acquired:
                try:
                    _ASYNC_BUSY_STATE.release(target)
                except Exception:
                    logger.warning(
                        "Could not clear async command busy state.",
                        exc_info=True,
                    )
            if handle is not None:
                handle.finish()

        def complete_worker() -> None:
            try:
                if self.on_finished is not None:
                    self.on_finished()
            except Exception:
                logger.exception("Async command finished callback failed")
            finally:
                finish_worker()

        try:
            busy_acquired = _ASYNC_BUSY_STATE.acquire(target)

            if self.refresh:
                suppression = suppress_observer_refresh_during_command(self.context)
                suppression.__enter__()
                suppression_entered = True

            worker = (
                self.python_worker_factory(self.execute, self.python_thread_name)
                if self.python_thread_name is not None
                else self.worker_factory(self.execute)
            )
            handle = AsyncCommandHandle(
                context=self.context,
                worker=worker,
                registry=self.registry,
            )
            handle.register()

            delivery_parent = (
                self.context
                if isinstance(self.context, QObject)
                and not qt_object_deleted(self.context)
                else None
            )
            delivery_receiver = self.delivery_factory(
                context=self.context,
                command=self.command,
                on_result=self.on_result,
                on_error=self.on_error,
                refresh=self.refresh,
                allow_during_shutdown=self.allow_during_shutdown,
                parent=delivery_parent,
            )
            handle.retain(delivery_receiver)
            cleanup_receiver = self.cleanup_factory(complete_worker)
            cleanup_receiver.bind_delivery(delivery_receiver)
            handle.retain(cleanup_receiver)

            worker.signals.result.connect(cleanup_receiver.handle_result)
            worker.signals.error.connect(cleanup_receiver.handle_error)
            worker.signals.finished.connect(cleanup_receiver.handle_finished)

            if isinstance(worker, PythonThreadWorker):
                worker.start()
            else:
                thread_pool = _require_thread_pool(self.thread_pool_factory)
                thread_pool.start(worker)
        except Exception as exc:
            finish_worker()
            logger.warning(
                "Could not prepare async application command %s: %s",
                self.command.name,
                exc,
            )
            return False
        return True


def qt_object_deleted(obj: Any) -> bool:
    """Return whether a Qt wrapper was deleted before an async callback."""
    if obj is None:
        return False
    try:
        return bool(sip.isdeleted(obj))
    except (AttributeError, TypeError, RuntimeError):
        return False


def context_is_closing(context: Any) -> bool:
    """Return whether the owning window has entered its close lifecycle."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if qt_object_deleted(current):
            return True
        try:
            if bool(getattr(current, "_closing_in_progress", False)):
                return True
            main_window = getattr(current, "main_window", None)
            if main_window is not None and main_window is not current:
                current = main_window
                continue
            parent = getattr(current, "parent", None)
            current = parent() if callable(parent) else None
        except RuntimeError:
            return True
    return False


def _require_thread_pool(
    factory: Callable[[], QThreadPool | None],
) -> QThreadPool:
    thread_pool = factory()
    if thread_pool is None:
        raise RuntimeError("Qt thread pool is unavailable")
    return thread_pool
