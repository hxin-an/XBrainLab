"""Runtime access to the shared ApplicationService command spine."""

from __future__ import annotations

from threading import RLock

from XBrainLab.backend.study import Study

from .service import ApplicationService

_SERVICE_CREATION_LOCK = RLock()


def get_application_service(study: Study | None = None) -> ApplicationService:
    """Return the cached ApplicationService for a Study, creating it if needed."""
    if study is None:
        return ApplicationService(Study())

    with _SERVICE_CREATION_LOCK:
        cached_service = getattr(study, "_application_service", None)
        if isinstance(cached_service, ApplicationService):
            return cached_service
        return ApplicationService(study)
