"""Tests for shared ApplicationService runtime access."""

from XBrainLab.backend.application import ApplicationService, get_application_service
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study


def test_get_application_service_caches_service_on_study():
    study = Study()

    first = get_application_service(study)
    second = get_application_service(study)

    assert first is second
    assert first.study is study


def test_backend_facade_uses_existing_application_service():
    study = Study()
    service = get_application_service(study)

    facade = BackendFacade(study)

    assert facade.service is service


def test_get_application_service_without_study_creates_service():
    service = get_application_service()

    assert isinstance(service, ApplicationService)
    assert isinstance(service.study, Study)
