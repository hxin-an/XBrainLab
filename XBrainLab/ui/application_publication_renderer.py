"""Always-on desktop acknowledgement for application view publications."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import ObserverDeliveryStatus
from XBrainLab.ui.core.observer_bridge import QtObserverBridge

if TYPE_CHECKING:
    from XBrainLab.backend.application.service import ApplicationService

PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS = 3
PANEL_PUBLICATION_RENDER_RETRY_INTERVAL_MS = 25
PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS = 500
DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS = PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS + 5


class ApplicationPublicationRenderLedger(QObject):
    """Coalesce panel publications and commit revisions only after rendering."""

    def __init__(
        self,
        *,
        panel_name: str,
        render_publication: Callable[[ApplicationViewPublication], None],
        commit_publication: Callable[[ApplicationViewPublication], None],
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._panel_name = panel_name
        self._render_publication = render_publication
        self._commit_publication = commit_publication
        self._last_rendered_revision = 0
        self._pending_publication: ApplicationViewPublication | None = None
        self._attempts = 0
        self._render_in_progress = False
        self._disposed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._attempt_render)

    @property
    def timer(self) -> QTimer:
        return self._timer

    @property
    def last_rendered_revision(self) -> int:
        return self._last_rendered_revision

    @property
    def pending_publication(self) -> ApplicationViewPublication | None:
        return self._pending_publication

    @property
    def render_in_progress(self) -> bool:
        return self._render_in_progress

    def queue(self, publication: ApplicationViewPublication) -> bool:
        """Queue a newer publication and re-arm only within its retry budget."""
        if self._disposed:
            return False
        revision = publication.revision
        if revision <= self._last_rendered_revision:
            return True

        pending = self._pending_publication
        if pending is not None and revision < pending.revision:
            return True
        if pending is not None and revision == pending.revision:
            if not self._timer.isActive():
                interval = self._retry_interval()
                self._timer.start(interval)
            return True

        self._pending_publication = publication
        self._attempts = 0
        self._timer.start(0)
        return True

    def record_rendered(self, publication: ApplicationViewPublication) -> bool:
        """Commit one successful direct or queued panel render."""
        if self._disposed:
            return False
        if publication.revision < self._last_rendered_revision:
            return True
        try:
            self._commit_publication(publication)
        except Exception:
            logger.exception(
                "%s application publication commit failed for revision %s",
                self._panel_name,
                publication.revision,
            )
            return False

        self._last_rendered_revision = publication.revision
        pending = self._pending_publication
        if pending is not None and pending.revision <= publication.revision:
            self._pending_publication = None
            self._attempts = 0
            self._timer.stop()
        elif pending is not None and not self._timer.isActive():
            self._timer.start(0)
        return True

    def _attempt_render(self) -> None:
        if self._disposed:
            return
        publication = self._pending_publication
        if publication is None:
            return
        if publication.revision <= self._last_rendered_revision:
            self._pending_publication = None
            self._attempts = 0
            return

        self._render_in_progress = True
        try:
            self._render_publication(publication)
        except Exception:
            self._record_failed_attempt(publication, render_exception=True)
        else:
            if not self.record_rendered(publication):
                self._record_failed_attempt(publication, render_exception=False)
        finally:
            self._render_in_progress = False

    def _record_failed_attempt(
        self,
        publication: ApplicationViewPublication,
        *,
        render_exception: bool,
    ) -> None:
        current = self._pending_publication
        if current is not None and current.revision == publication.revision:
            self._attempts += 1
            if self._should_log_failed_attempt():
                log_failure = logger.exception if render_exception else logger.error
                log_failure(
                    "%s application publication render failed for revision %s "
                    "(attempt %s; low-frequency recovery begins after %s)",
                    self._panel_name,
                    publication.revision,
                    self._attempts,
                    PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS,
                )
            self._timer.start(self._retry_interval())
        elif current is not None:
            self._attempts = 0
            self._timer.start(0)

    def _retry_interval(self) -> int:
        return (
            PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS
            if self._attempts >= PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS
            else PANEL_PUBLICATION_RENDER_RETRY_INTERVAL_MS
        )

    def _should_log_failed_attempt(self) -> bool:
        """Keep persistent render recovery observable without flooding logs."""
        return (
            self._attempts <= PANEL_PUBLICATION_RENDER_MAX_ATTEMPTS
            or self._attempts % 120 == 0
        )

    def cleanup(self) -> None:
        """Cancel queued and retry work without rendering during teardown."""
        self._disposed = True
        self._timer.stop()
        self._pending_publication = None
        self._attempts = 0


class DesktopApplicationPublicationRenderer(QObject):
    """Own the desktop's publication render acknowledgement independently."""

    def __init__(
        self,
        *,
        service: ApplicationService,
        render_publication: Callable[[ApplicationViewPublication], bool],
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._render_publication = render_publication
        self._pending_publication: ApplicationViewPublication | None = None
        self._render_attempts = 0
        self._paused_for_shutdown = False
        self._disposed = False
        self._delivery_owner = object()
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._attempt_pending_render)
        self._bridge = QtObserverBridge(
            service,
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self,
            require_slot_acknowledgement=True,
        )
        self._bridge.connect_to(self._render_and_acknowledge)
        service.require_visible_view_publication_acknowledgement(
            self._delivery_owner,
        )

    @property
    def pending_publication(self) -> ApplicationViewPublication | None:
        """Return the newest desktop publication awaiting visible render."""
        return self._pending_publication

    @property
    def service(self) -> ApplicationService:
        """Return the canonical publication port owned by this renderer."""
        return self._service

    @property
    def retry_timer(self) -> QTimer:
        """Expose the owned timer for lifecycle diagnostics and tests."""
        return self._retry_timer

    def _render_and_acknowledge(
        self,
        publication: ApplicationViewPublication,
    ) -> bool | ObserverDeliveryStatus:
        if self._disposed:
            return False
        if not isinstance(publication, ApplicationViewPublication):
            logger.error("Desktop received an invalid application publication.")
            return False
        pending = self._pending_publication
        if pending is None or publication.revision > pending.revision:
            self._pending_publication = publication
            self._render_attempts = 0
        if self._paused_for_shutdown:
            return ObserverDeliveryStatus.DEFERRED
        if self._attempt_pending_render():
            return True
        return ObserverDeliveryStatus.DEFERRED

    def render_initial_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        """Render and acknowledge the initial snapshot through the owned protocol."""
        return self._render_and_acknowledge(publication) is True

    def _attempt_pending_render(self) -> bool:
        """Acknowledge only after every materialized desktop surface rendered."""
        if self._disposed or self._paused_for_shutdown:
            return False
        publication = self._pending_publication
        if publication is None:
            return True
        try:
            rendered = self._render_publication(publication)
        except Exception:
            self._schedule_retry()
            logger.exception(
                "Desktop application publication render failed for revision %s",
                publication.revision,
            )
            return False
        if rendered is not True:
            self._schedule_retry()
            if self._render_attempts == DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS:
                logger.error(
                    "Desktop application publication was not rendered after %s "
                    "attempts for revision %s; continuing low-frequency recovery",
                    self._render_attempts,
                    publication.revision,
                )
            return False
        try:
            pending = self._pending_publication
            if pending is None or pending.revision <= publication.revision:
                self._pending_publication = None
            acknowledged = self._service.acknowledge_view_publication_delivery(
                publication.revision,
                owner=self._delivery_owner,
            )
        except Exception:
            logger.exception(
                "Desktop application publication acknowledgement failed for "
                "revision %s",
                publication.revision,
            )
            self._retain_publication_for_retry(publication)
            return False
        if acknowledged is not True:
            self._retain_publication_for_retry(publication)
            return False

        pending = self._pending_publication
        if pending is not None and pending.revision > publication.revision:
            if not self._retry_timer.isActive():
                self._retry_timer.start(0)
            return True
        self._pending_publication = None
        self._render_attempts = 0
        self._retry_timer.stop()
        return True

    def _retain_publication_for_retry(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        """Retain a failed delivery without replacing a newer revision."""
        if self._disposed:
            return
        pending = self._pending_publication
        if pending is not None and pending.revision > publication.revision:
            if not self._paused_for_shutdown and not self._retry_timer.isActive():
                self._retry_timer.start(0)
            return
        self._pending_publication = publication
        if not self._paused_for_shutdown:
            self._schedule_retry()

    def _schedule_retry(self) -> None:
        self._render_attempts += 1
        interval = (
            PANEL_PUBLICATION_RENDER_RECOVERY_INTERVAL_MS
            if self._render_attempts >= DESKTOP_PUBLICATION_RENDER_MAX_ATTEMPTS
            else PANEL_PUBLICATION_RENDER_RETRY_INTERVAL_MS
        )
        self._retry_timer.start(interval)

    def pause_for_shutdown(self) -> None:
        """Retain the newest revision without rendering into quiescing widgets."""
        if self._disposed:
            return
        self._paused_for_shutdown = True
        self._retry_timer.stop()

    def resume_after_cancelled_shutdown(self) -> None:
        """Resume the retained visible-render obligation after close is cancelled."""
        if self._disposed or not self._paused_for_shutdown:
            return
        self._paused_for_shutdown = False
        if self._pending_publication is not None:
            self._attempt_pending_render()

    def cleanup(self) -> None:
        """Detach the always-on publication bridge."""
        if self._disposed:
            return
        self._disposed = True
        self._paused_for_shutdown = True
        self._retry_timer.stop()
        self._pending_publication = None
        self._render_attempts = 0
        self._bridge.cleanup()
