"""Tests for shared ApplicationService runtime access."""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Barrier, Event

import pytest

from XBrainLab.backend.application import ApplicationService, get_application_service
from XBrainLab.backend.application.runtime import (
    application_service_initialized,
    get_initialized_application_service,
)
from XBrainLab.backend.study import Study


def test_get_application_service_caches_service_on_study():
    study = Study()

    first = get_application_service(study)
    second = get_application_service(study)

    assert first is second
    assert first.study is study
    assert study._application_service is first
    assert application_service_initialized(study) is True


def test_get_initialized_application_service_never_constructs_runtime():
    study = Study()

    assert get_initialized_application_service(study) is None
    assert study._application_service is None

    service = get_application_service(study)

    assert get_initialized_application_service(study) is service


def test_direct_construction_is_initialization_only_and_not_cached():
    study = Study()

    first = ApplicationService(study)
    second = ApplicationService(study)

    assert first is not second
    assert first.study is study
    assert second.study is study
    assert study._application_service is None
    assert application_service_initialized(study) is False
    first.close()
    second.close()


def test_direct_construction_does_not_replace_runtime_cached_service():
    study = Study()
    cached = get_application_service(study)

    explicit = ApplicationService(study)

    assert explicit is not cached
    assert get_application_service(study) is cached
    assert study._application_service is cached
    explicit.close()


def test_get_application_service_without_study_creates_service():
    service = get_application_service()

    assert isinstance(service, ApplicationService)
    assert isinstance(service.study, Study)
    assert service.study._application_service is service


def test_get_application_service_is_atomic_per_study(monkeypatch):
    study = Study()
    barrier = Barrier(2)
    initialization_started = Event()
    allow_initialization = Event()
    original_init = ApplicationService.__init__

    def synchronized_init(self, current_study=None):
        initialization_started.set()
        assert allow_initialization.wait(timeout=2.0)
        original_init(self, current_study)

    monkeypatch.setattr(ApplicationService, "__init__", synchronized_init)

    def acquire_service(_index):
        barrier.wait(timeout=2)
        return get_application_service(study)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(acquire_service, index) for index in range(2)]
        assert initialization_started.wait(timeout=2.0)
        allow_initialization.set()
        services = [future.result(timeout=2.0) for future in futures]

    assert services[0] is services[1]


def test_direct_construction_does_not_publish_into_runtime_cache(monkeypatch):
    study = Study()
    constructed = ApplicationService(study)
    resolved = get_application_service(study)

    assert resolved is not constructed
    assert resolved.study is study
    assert constructed.study is study
    assert study._application_service is resolved
    constructed.close()


def test_failed_runtime_initialization_is_not_cached_and_can_retry(monkeypatch):
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
        get_application_service(study)

    assert study._application_service is None
    assert application_service_initialized(study) is False
    service = get_application_service(study)
    assert service.study is study
    assert get_application_service(study) is service
    assert application_service_initialized(study) is True


def test_close_and_concurrent_lookup_publish_one_open_replacement() -> None:
    study = Study()
    closing = get_application_service(study)
    cleanup_started = Event()
    release_cleanup = Event()
    original_finalizer = closing.publication_lifecycle.observer_finalizer

    def blocked_finalizer() -> None:
        cleanup_started.set()
        assert release_cleanup.wait(timeout=2.0)
        original_finalizer()

    closing.publication_lifecycle.observer_finalizer = blocked_finalizer

    with (
        ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="service-close",
        ) as close_executor,
        ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="service-lookup",
        ) as lookup_executor,
    ):
        close_future = close_executor.submit(closing.close)
        assert cleanup_started.wait(timeout=2.0)
        assert application_service_initialized(study) is False
        lookup_barrier = Barrier(2)

        def lookup() -> ApplicationService:
            lookup_barrier.wait(timeout=2.0)
            return get_application_service(study)

        lookup_futures = [lookup_executor.submit(lookup) for _index in range(2)]
        replacements = [future.result(timeout=2.0) for future in lookup_futures]
        release_cleanup.set()
        close_future.result(timeout=2.0)

    replacement = replacements[0]
    assert replacement is replacements[1]
    assert replacement is not closing
    assert replacement.is_closed is False
    assert study._application_service is replacement
    assert application_service_initialized(study) is True
    assert get_application_service(study) is replacement
    replacement.close()


def test_closing_one_study_does_not_block_service_creation_for_another(
    monkeypatch,
) -> None:
    closing_study = Study()
    independent_study = Study()
    closing = get_application_service(closing_study)
    close_started = Event()
    release_close = Event()
    original_begin_close = closing.shutdown_lifecycle.begin_close

    def blocked_begin_close() -> bool:
        close_started.set()
        assert release_close.wait(timeout=2.0)
        return original_begin_close()

    monkeypatch.setattr(closing.shutdown_lifecycle, "begin_close", blocked_begin_close)

    with (
        ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="blocked-study-close",
        ) as close_executor,
        ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="independent-study-create",
        ) as create_executor,
    ):
        close_future = close_executor.submit(closing.close)
        assert close_started.wait(timeout=2.0)
        create_future = create_executor.submit(
            get_application_service,
            independent_study,
        )
        try:
            independent = create_future.result(timeout=0.25)
        except FutureTimeoutError:
            pytest.fail(
                "Closing one Study held the runtime lock needed to create another "
                "Study's ApplicationService."
            )
        finally:
            release_close.set()
            close_future.result(timeout=2.0)

    assert independent.study is independent_study
    assert independent_study._application_service is independent
    independent.close()
