"""Tests for shared ApplicationService runtime access."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

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


def test_direct_construction_never_publishes_partial_service(monkeypatch):
    study = Study()
    initialization_started = Event()
    allow_initialization = Event()
    original_init = ApplicationService.__init__

    def delayed_init(self, current_study=None):
        initialization_started.set()
        assert allow_initialization.wait(timeout=2)
        original_init(self, current_study)

    monkeypatch.setattr(ApplicationService, "__init__", delayed_init)
    with ThreadPoolExecutor(max_workers=2) as executor:
        constructing = executor.submit(ApplicationService, study)
        assert initialization_started.wait(timeout=2)
        resolving = executor.submit(get_application_service, study)
        try:
            time.sleep(0.05)
            assert resolving.done() is False
        finally:
            allow_initialization.set()
        constructed = constructing.result(timeout=2)
        resolved = resolving.result(timeout=2)

    assert resolved is constructed
    assert resolved.study is study


def test_failed_direct_initialization_releases_lock_and_can_retry(monkeypatch):
    study = Study()
    original_initialize = ApplicationService._initialize_components
    attempts = 0

    def fail_once(self, current_study, command_lock):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("initialization failed")
        original_initialize(self, current_study, command_lock)

    monkeypatch.setattr(ApplicationService, "_initialize_components", fail_once)

    with pytest.raises(RuntimeError, match="initialization failed"):
        ApplicationService(study)

    assert study._application_service is None
    service = ApplicationService(study)
    assert service.study is study
    assert get_application_service(study) is service
