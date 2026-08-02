"""Retryable delivery for committed application view publications."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from enum import Enum
from threading import Lock, get_ident

from XBrainLab.backend.utils.observer import ObserverDeliveryStatus

from .view_publication import ApplicationViewPublication


class UnobservedDeliveryPolicy(str, Enum):
    """Explicit handling for publications with no render subscribers."""

    REQUIRE_ACKNOWLEDGEMENT = "require_acknowledgement"
    ACKNOWLEDGE_WITHOUT_RENDER = "acknowledge_without_render"


class ApplicationViewEventPublisher:
    """Deliver the newest committed publication revision after acknowledgement.

    ``generation`` identifies domain state for command preconditions. ``revision``
    also advances for publication-health transitions such as stale and recovered.
    This publisher therefore de-duplicates and retries by revision, not generation.
    Reentrant publications coalesce to the newest unseen revision so consumers
    converge without recursively delivering intermediate snapshots.
    """

    def __init__(
        self,
        *,
        initial_revision: int,
        deliver: Callable[
            [ApplicationViewPublication],
            bool | ObserverDeliveryStatus,
        ],
        unobserved_delivery_policy: UnobservedDeliveryPolicy = (
            UnobservedDeliveryPolicy.REQUIRE_ACKNOWLEDGEMENT
        ),
    ) -> None:
        if (
            isinstance(initial_revision, bool)
            or not isinstance(initial_revision, int)
            or initial_revision < 1
        ):
            raise ValueError("Initial application view revision must be positive.")
        if not callable(deliver):
            raise TypeError("Application view delivery callback must be callable.")
        if not isinstance(unobserved_delivery_policy, UnobservedDeliveryPolicy):
            raise TypeError(
                "Application view unobserved delivery policy must be explicit."
            )
        self._deliver = deliver
        self._unobserved_delivery_policy = unobserved_delivery_policy
        self._state_lock = Lock()
        self._delivery_lock = Lock()
        self._delivery_owner: int | None = None
        # The initial snapshot exists before a visible consumer is attached.  It
        # becomes delivered only after that consumer renders and acknowledges it.
        self._delivered_revision = initial_revision - 1
        self._pending: ApplicationViewPublication | None = None
        self._awaiting_ack_revision: int | None = None
        self._acknowledgement_owner: object | None = None

    def publish(self, publication: ApplicationViewPublication) -> bool:
        """Deliver the newest unseen revision, retaining failed work for retry."""
        if not isinstance(publication, ApplicationViewPublication):
            raise TypeError(
                "Application publication events require ApplicationViewPublication."
            )
        caller = get_ident()
        with self._state_lock:
            if publication.revision <= self._delivered_revision:
                return True
            if self._pending is None or publication.revision >= self._pending.revision:
                self._pending = deepcopy(publication)
            if self._delivery_owner == caller:
                return True
            if self._awaiting_ack_revision == self._pending.revision:
                return False

        with self._delivery_lock:
            with self._state_lock:
                self._delivery_owner = caller
            try:
                while True:
                    with self._state_lock:
                        target = deepcopy(self._pending)
                        if target is None:
                            return True
                        if target.revision <= self._delivered_revision:
                            self._pending = None
                            return True
                        if self._awaiting_ack_revision == target.revision:
                            return False
                        self._awaiting_ack_revision = target.revision

                    delivery = self._deliver(deepcopy(target))
                    if delivery is ObserverDeliveryStatus.DEFERRED:
                        with self._state_lock:
                            pending = self._pending
                            if (
                                pending is not None
                                and pending.revision > target.revision
                            ):
                                continue
                            return self._delivered_revision >= target.revision
                    if (
                        delivery is ObserverDeliveryStatus.NO_SUBSCRIBERS
                        and self._allows_delivery_without_render()
                    ):
                        self.acknowledge(target.revision)
                        continue
                    if not (
                        delivery is True or delivery is ObserverDeliveryStatus.DELIVERED
                    ):
                        with self._state_lock:
                            if self._awaiting_ack_revision == target.revision:
                                self._awaiting_ack_revision = None
                        return False

                    with self._state_lock:
                        if self._acknowledgement_owner is not None:
                            if self._delivered_revision >= target.revision:
                                continue
                            return False
                    self.acknowledge(target.revision)
            finally:
                with self._state_lock:
                    if self._delivery_owner == caller:
                        self._delivery_owner = None

    def require_acknowledging_subscriber(self, owner: object) -> None:
        """Claim sole acknowledgement ownership for the visible renderer."""
        if owner is None:
            raise TypeError("Application view acknowledgement owner is required.")
        with self._state_lock:
            current_owner = self._acknowledgement_owner
            if current_owner is not None and current_owner is not owner:
                raise RuntimeError(
                    "Application view acknowledgement already has a visible owner."
                )
            self._acknowledgement_owner = owner
            self._unobserved_delivery_policy = (
                UnobservedDeliveryPolicy.REQUIRE_ACKNOWLEDGEMENT
            )

    def _allows_delivery_without_render(self) -> bool:
        with self._state_lock:
            return (
                self._unobserved_delivery_policy
                is UnobservedDeliveryPolicy.ACKNOWLEDGE_WITHOUT_RENDER
            )

    def acknowledge(self, revision: int, *, owner: object | None = None) -> bool:
        """Commit one UI-delivered revision after the consumer rendered it."""
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError(
                "Application view acknowledgement revision must be positive."
            )
        with self._state_lock:
            if (
                self._acknowledgement_owner is not None
                and owner is not self._acknowledgement_owner
            ):
                return False
            self._delivered_revision = max(self._delivered_revision, revision)
            pending = self._pending
            if pending is not None and pending.revision <= self._delivered_revision:
                self._pending = None
            if (
                self._awaiting_ack_revision is not None
                and self._awaiting_ack_revision <= self._delivered_revision
            ):
                self._awaiting_ack_revision = None
        return True

    def has_delivered_revision(self, revision: int) -> bool:
        """Return whether a visible consumer acknowledged this revision."""
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("Application view revision must be positive.")
        with self._state_lock:
            return self._delivered_revision >= revision

    def reject(
        self,
        publication: ApplicationViewPublication,
        *,
        owner: object | None = None,
    ) -> bool:
        """Release a deferred revision after its visible consumer failed to render."""
        if not isinstance(publication, ApplicationViewPublication):
            raise TypeError(
                "Application view rejection requires ApplicationViewPublication."
            )
        with self._state_lock:
            if (
                self._acknowledgement_owner is not None
                and owner is not self._acknowledgement_owner
            ):
                return False
            if publication.revision <= self._delivered_revision:
                return True
            pending = self._pending
            if pending is None or publication.revision >= pending.revision:
                self._pending = deepcopy(publication)
            if self._awaiting_ack_revision == publication.revision:
                self._awaiting_ack_revision = None
        return True
