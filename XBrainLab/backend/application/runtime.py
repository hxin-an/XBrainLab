"""Runtime access to the shared ApplicationService command spine."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import TYPE_CHECKING, TypeVar

from XBrainLab.backend.study import Study

if TYPE_CHECKING:
    from .service import ApplicationService

_SERVICE_LOCK_INITIALIZATION_LOCK = RLock()
_ServiceT = TypeVar("_ServiceT")


def _service_lifecycle_lock(study: Study) -> RLock:
    """Return the lock that owns one Study's service-cache lifecycle."""
    lock = getattr(study, "_application_service_lock", None)
    if lock is not None:
        return lock
    with _SERVICE_LOCK_INITIALIZATION_LOCK:
        lock = getattr(study, "_application_service_lock", None)
        if lock is None:
            lock = RLock()
            study._application_service_lock = lock
        return lock


def resolve_application_service(
    study: Study,
    service_type: type[_ServiceT],
    factory: Callable[[], _ServiceT],
) -> _ServiceT:
    """Return or atomically publish one open service for a Study."""
    with _service_lifecycle_lock(study):
        cached_service = getattr(study, "_application_service", None)
        if isinstance(cached_service, service_type) and not getattr(
            cached_service,
            "_closed",
            True,
        ):
            return cached_service
        service = factory()
        study._application_service = service
        return service


def application_service_initialized(study: Study) -> bool:
    """Return whether the runtime cache owns a fully initialized service."""
    with _service_lifecycle_lock(study):
        service = getattr(study, "_application_service", None)
        return service is not None and not getattr(service, "_closed", True)


def get_application_service(study: Study | None = None) -> ApplicationService:
    """Return the cached ApplicationService for a Study, creating it if needed."""
    from .service import ApplicationService  # noqa: PLC0415

    target_study = study if study is not None else Study()
    return resolve_application_service(
        target_study,
        ApplicationService,
        lambda: ApplicationService(target_study),
    )


def begin_application_service_close(
    study: Study,
    service: ApplicationService,
    begin_close: Callable[[], bool],
) -> bool:
    """Atomically mark one service closing and release only its cache ownership.

    The runtime lock is always acquired before the service admission lock used by
    ``begin_close``. Runtime lookup never acquires that service lock independently,
    which keeps this ordering deadlock-free.
    """
    with _service_lifecycle_lock(study):
        if not begin_close():
            return False
        if getattr(study, "_application_service", None) is service:
            study._application_service = None
        return True
