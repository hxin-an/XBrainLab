"""Tests for shared ApplicationService runtime access."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from XBrainLab.backend.application import ApplicationService, get_application_service
from XBrainLab.backend.study import Study


def test_get_application_service_caches_service_on_study():
    study = Study()

    first = get_application_service(study)
    second = get_application_service(study)

    assert first is second
    assert first.study is study


def test_get_application_service_without_study_creates_service():
    service = get_application_service()

    assert isinstance(service, ApplicationService)
    assert isinstance(service.study, Study)


def test_get_application_service_is_atomic_per_study(monkeypatch):
    study = Study()
    barrier = Barrier(2)
    original_init = ApplicationService.__init__

    def synchronized_init(self, current_study=None):
        time.sleep(0.03)
        original_init(self, current_study)

    monkeypatch.setattr(ApplicationService, "__init__", synchronized_init)

    def acquire_service(_index):
        barrier.wait(timeout=2)
        return get_application_service(study)

    with ThreadPoolExecutor(max_workers=2) as executor:
        services = list(executor.map(acquire_service, range(2)))

    assert services[0] is services[1]
