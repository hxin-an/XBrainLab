"""Desktop publication ownership across cancellable shutdown attempts."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from PyQt6.QtCore import QObject

from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import ObserverDeliveryStatus
from XBrainLab.ui.application_publication_renderer import (
    DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS,
    PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS,
    ApplicationPublicationRenderLedger,
    DesktopApplicationPublicationRenderer,
)
from XBrainLab.ui.components.info_panel_service import InfoPanelService


def test_initial_revision_requires_visible_renderer_acknowledgement(qtbot) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    render = MagicMock(return_value=True)
    owner = QObject()

    assert (
        service._view_event_publisher.has_delivered_revision(initial.revision) is False
    )

    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )

    assert renderer.render_initial_publication(initial) is True
    assert (
        service._view_event_publisher.has_delivered_revision(initial.revision) is True
    )
    render.assert_called_once_with(initial)

    renderer.cleanup()
    service.close()


def test_panel_ledger_retries_deferred_render_without_logging_failure(
    qtbot,
    caplog,
) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    publication = replace(initial, revision=initial.revision + 1)
    render = MagicMock(side_effect=[False, True])
    commit = MagicMock()
    owner = QObject()
    ledger = ApplicationPublicationRenderLedger(
        panel_name="Dataset",
        render_publication=render,
        commit_publication=commit,
        parent=owner,
    )

    ledger.queue(publication)
    ledger.timer.stop()
    ledger._attempt_render()

    assert ledger.pending_publication == publication
    assert ledger.timer.isActive() is True
    assert "application publication render failed" not in caplog.text

    ledger.timer.stop()
    ledger._attempt_render()

    assert ledger.pending_publication is None
    assert ledger.last_rendered_revision == publication.revision
    commit.assert_called_once_with(publication)
    ledger.cleanup()
    service.close()


def test_false_acknowledgements_retain_revision_through_recovery_until_success(
    qtbot,
) -> None:
    service = ApplicationService(Study())
    publication = service.get_view_publication()
    render = MagicMock(return_value=True)
    owner = QObject()
    acknowledge = service.acknowledge_view_publication_delivery
    acknowledgement_attempts = 0

    def fail_until_recovery(revision: int, *, owner: object | None = None) -> bool:
        nonlocal acknowledgement_attempts
        acknowledgement_attempts += 1
        if acknowledgement_attempts <= DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS:
            return False
        return acknowledge(revision, owner=owner)

    service.acknowledge_view_publication_delivery = MagicMock(
        side_effect=fail_until_recovery
    )
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )

    assert renderer.render_initial_publication(publication) is False
    for _ in range(DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS - 1):
        assert renderer.pending_publication == publication
        assert renderer.retry_timer.isActive() is True
        assert renderer._attempt_pending_render() is False

    assert renderer.pending_publication == publication
    assert renderer.retry_timer.isActive() is True
    assert (
        renderer.retry_timer.interval() == PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS
    )
    assert (
        service._view_event_publisher.has_delivered_revision(publication.revision)
        is False
    )

    assert renderer._attempt_pending_render() is True
    assert renderer.pending_publication is None
    assert renderer.retry_timer.isActive() is False
    assert service._view_event_publisher.has_delivered_revision(publication.revision)
    assert render.call_count == DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS + 1

    renderer.cleanup()
    service.close()


def test_transient_render_exception_retains_revision_until_success(qtbot) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    publication = replace(initial, revision=initial.revision + 1)
    render = MagicMock(side_effect=[RuntimeError("transient"), True])
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )

    assert renderer._render_and_acknowledge(publication) is not True
    assert renderer.pending_publication == publication
    assert renderer.retry_timer.isActive() is True

    assert renderer._attempt_pending_render() is True
    assert renderer.pending_publication is None
    assert service._view_event_publisher.has_delivered_revision(publication.revision)

    renderer.cleanup()
    service.close()


def test_aggregate_render_runtime_error_does_not_acknowledge_revision(qtbot) -> None:
    class BrokenAggregatePanel(QObject):
        def update_info(self, **_kwargs) -> None:
            raise RuntimeError("aggregate renderer failed")

    study = Study()
    service = ApplicationService(study)
    info_service = InfoPanelService(study)
    panel = BrokenAggregatePanel()
    info_service._listeners.add(panel)
    initial = service.get_view_publication()
    publication = replace(initial, revision=initial.revision + 1)
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=info_service.render_publication,
        parent=owner,
    )

    try:
        result = renderer._render_and_acknowledge(publication)

        assert result is ObserverDeliveryStatus.DEFERRED
        assert renderer.pending_publication == publication
        assert renderer.retry_timer.isActive() is True
        assert (
            service._view_event_publisher.has_delivered_revision(publication.revision)
            is False
        )
    finally:
        renderer.cleanup()
        service.close()


def test_retry_budget_never_abandons_unacknowledged_revision(qtbot) -> None:
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    publication = replace(initial, revision=initial.revision + 1)
    render = MagicMock(return_value=False)
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )

    assert renderer._render_and_acknowledge(publication) is not True
    for _ in range(DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS + 2):
        assert renderer._attempt_pending_render() is False

    assert renderer.pending_publication == publication
    assert renderer.retry_timer.isActive() is True
    assert (
        service._view_event_publisher.has_delivered_revision(publication.revision)
        is False
    )

    render.return_value = True
    assert renderer._attempt_pending_render() is True
    assert (
        service._view_event_publisher.has_delivered_revision(publication.revision)
        is True
    )

    renderer.cleanup()
    service.close()


def test_shutdown_pause_retains_publication_without_render_retry_or_rejection(
    qtbot,
) -> None:
    service = ApplicationService(Study())
    render = MagicMock(return_value=True)
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )
    initial = service.get_view_publication()
    publication = replace(
        initial,
        generation=initial.generation + 1,
        revision=initial.revision + 1,
    )
    reject = MagicMock(wraps=service.reject_view_publication_delivery)
    service.reject_view_publication_delivery = reject

    renderer.pause_for_shutdown()

    assert service._publish_view_changed(publication) is False
    qtbot.wait(50)

    render.assert_not_called()
    reject.assert_not_called()
    assert renderer.pending_publication == publication
    assert renderer.retry_timer.isActive() is False

    renderer.cleanup()
    service.close()


def test_non_owner_success_cannot_acknowledge_paused_desktop_publication(
    qtbot,
) -> None:
    service = ApplicationService(Study())
    non_owner = MagicMock(return_value=True)
    service.subscribe("view_publication_changed", non_owner)
    render = MagicMock(return_value=True)
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )
    initial = service.get_view_publication()
    publication = replace(
        initial,
        generation=initial.generation + 1,
        revision=initial.revision + 1,
    )

    renderer.pause_for_shutdown()

    assert service._publish_view_changed(publication) is False
    assert (
        service._view_event_publisher.has_delivered_revision(publication.revision)
        is False
    )
    assert service.acknowledge_view_publication_delivery(publication.revision) is False
    non_owner.assert_called_once_with(publication)
    render.assert_not_called()

    renderer.cleanup()
    service.close()


def test_cancelled_shutdown_resumes_and_acknowledges_latest_publication(qtbot) -> None:
    service = ApplicationService(Study())
    render = MagicMock(return_value=True)
    owner = QObject()
    renderer = DesktopApplicationPublicationRenderer(
        service=service,
        render_publication=render,
        parent=owner,
    )
    initial = service.get_view_publication()
    first = replace(
        initial,
        generation=initial.generation + 1,
        revision=initial.revision + 1,
    )
    latest = replace(
        first,
        generation=first.generation + 1,
        revision=first.revision + 1,
    )

    renderer.pause_for_shutdown()
    assert service._publish_view_changed(first) is False
    assert service._publish_view_changed(latest) is False

    renderer.resume_after_cancelled_shutdown()

    render.assert_called_once_with(latest)
    assert service._view_event_publisher.has_delivered_revision(latest.revision)
    assert renderer.pending_publication is None

    renderer.cleanup()
    service.close()
