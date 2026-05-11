"""Runtime access to the shared ApplicationService command spine."""

from __future__ import annotations

from XBrainLab.backend.study import Study

from .service import ApplicationService


def get_application_service(study: Study | None = None) -> ApplicationService:
    """Return the cached ApplicationService for a Study, creating it if needed."""
    if study is None:
        return ApplicationService(Study())

    cached_service = getattr(study, "_application_service", None)
    if isinstance(cached_service, ApplicationService):
        return cached_service

    service = ApplicationService(study)
    study._application_service = service
    return service
