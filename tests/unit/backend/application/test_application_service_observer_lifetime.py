"""ApplicationService observer ownership and disposal regressions."""

from __future__ import annotations

import gc
from unittest.mock import MagicMock
from weakref import ref

import pytest

from XBrainLab.backend.application import ApplicationService, get_application_service
from XBrainLab.backend.application.commands import QueryStateCommand
from XBrainLab.backend.application.runtime import application_service_initialized
from XBrainLab.backend.study import Study

_SALIENCY_TERMINAL_EVENT = "post_training_saliency_terminal"


def _observer_count(observable, event: str) -> int:
    return len(observable._observers.get(event, ()))


def test_direct_services_share_one_lifecycle_observer_owner() -> None:
    study = Study()
    first = get_application_service(study)
    second = get_application_service(study)
    training_controller = study.get_controller("training")
    saliency_events = study.training_manager._saliency_lifecycle_events

    assert second is first
    assert _observer_count(training_controller, "training_started") == 1
    assert _observer_count(training_controller, "training_updated") == 1
    assert _observer_count(training_controller, "training_stopped") == 1
    assert _observer_count(saliency_events, _SALIENCY_TERMINAL_EVENT) == 1

    first.publication_lifecycle.publish_training_live_state = MagicMock()
    first.close()
    first.close()
    first.dispose()
    training_controller.notify("training_started")

    first.publication_lifecycle.publish_training_live_state.assert_not_called()
    assert _observer_count(training_controller, "training_started") == 0
    assert _observer_count(training_controller, "training_updated") == 0
    assert _observer_count(training_controller, "training_stopped") == 0
    assert _observer_count(saliency_events, _SALIENCY_TERMINAL_EVENT) == 0


def test_runtime_service_cache_releases_only_after_explicit_close() -> None:
    study = Study()
    training_controller = study.get_controller("training")
    saliency_events = study.training_manager._saliency_lifecycle_events
    service = get_application_service(study)
    service_ref = ref(service)

    del service
    gc.collect()

    cached = service_ref()
    assert cached is study._application_service
    assert cached is not None
    cached.close()
    del cached
    gc.collect()

    assert service_ref() is None
    assert _observer_count(training_controller, "training_started") == 0
    assert _observer_count(training_controller, "training_updated") == 0
    assert _observer_count(training_controller, "training_stopped") == 0
    assert _observer_count(saliency_events, _SALIENCY_TERMINAL_EVENT) == 0


def test_close_unsubscribes_armed_automation_and_releases_service() -> None:
    study = Study()
    training_controller = study.get_controller("training")
    saliency_events = study.training_manager._saliency_lifecycle_events
    service = ApplicationService(study)
    service.post_training_saliency.arm()
    service_ref = ref(service)

    assert _observer_count(training_controller, "training_stopped") == 2
    assert _observer_count(saliency_events, _SALIENCY_TERMINAL_EVENT) == 1

    service.close()

    assert _observer_count(training_controller, "training_started") == 0
    assert _observer_count(training_controller, "training_updated") == 0
    assert _observer_count(training_controller, "training_stopped") == 0
    assert _observer_count(saliency_events, _SALIENCY_TERMINAL_EVENT) == 0

    del service
    gc.collect()

    assert service_ref() is None
    training_controller.notify("training_stopped")
    assert service_ref() is None


def test_close_releases_runtime_cache_for_a_fresh_service() -> None:
    study = Study()
    service = get_application_service(study)

    service.close()

    assert application_service_initialized(study) is False
    replacement = get_application_service(study)
    assert replacement is not service
    assert replacement.study is study
    replacement.close()


def test_closed_service_rejects_commands_and_public_reads() -> None:
    study = Study()
    service = get_application_service(study)
    service.close()

    result = service.execute(QueryStateCommand(query="state"))

    assert result.failed is True
    assert result.diagnostics["application_service_closed"] is True
    assert "closed" in result.message.lower()
    with pytest.raises(RuntimeError, match="closed"):
        service.get_state()
    with pytest.raises(RuntimeError, match="closed"):
        service.get_view_publication()
    with pytest.raises(RuntimeError, match="closed"):
        service.get_capabilities()
