"""One-shot confirmation receipts for external label materialization."""

from __future__ import annotations

import time
from threading import RLock

from .resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
    enforce_resource_preflight,
)
from .resource_receipt import (
    DEFAULT_RESOURCE_RECEIPT_LIMIT,
    DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS,
    ResourceReceiptAuthority,
    ResourceReceiptRecord,
)

LABEL_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
LABEL_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT

_LabelPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


class LabelResourceReceiptAuthority:
    """Authorize one exact label parse before any payload is materialized."""

    def __init__(self, *, command_name: str) -> None:
        self._authority = ResourceReceiptAuthority[ResourcePreflightResult](
            command_name=command_name,
            ttl_seconds=LABEL_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=LABEL_PREFLIGHT_RECEIPT_LIMIT,
            clock=lambda: time.monotonic(),
        )
        self._lock = RLock()

    def authorize(
        self,
        *,
        confirmed: bool,
        token: str | None,
        preflight: ResourcePreflightResult,
        scope_fingerprint: str,
        configuration_fingerprint: str,
        preflight_fingerprint: str,
    ) -> bool:
        """Consume one matching challenge or fail before parser entry."""
        with self._lock:
            if preflight.blocking:
                self._authority.discard(token)
                enforce_resource_preflight(preflight, confirmed=False)

            if not preflight.requires_confirmation:
                self._authority.discard(token)
                enforce_resource_preflight(preflight, confirmed=False)
                return False

            receipt = self._authority.peek(
                token,
                scope_fingerprint=scope_fingerprint,
                configuration_fingerprint=configuration_fingerprint,
                preflight_fingerprint=preflight_fingerprint,
            )
            if receipt is not None:
                if not confirmed:
                    raise self._confirmation_error(receipt)
                enforce_resource_preflight(preflight, confirmed=True)
                consumed = self._authority.consume(
                    receipt.challenge.challenge_id,
                    scope_fingerprint=scope_fingerprint,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                )
                if consumed is None:
                    raise self._confirmation_error(
                        self._issue(
                            preflight=preflight,
                            scope_fingerprint=scope_fingerprint,
                            configuration_fingerprint=configuration_fingerprint,
                            preflight_fingerprint=preflight_fingerprint,
                        )
                    )
                # Consent is spent before the first parser call. Loader failure
                # cannot leave a reusable authorization behind.
                return True

            if token:
                self._authority.discard(token)
            receipt = None
            if not confirmed:
                receipt = self._authority.pending(
                    scope_fingerprint=scope_fingerprint,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                )
            raise self._confirmation_error(
                receipt
                or self._issue(
                    preflight=preflight,
                    scope_fingerprint=scope_fingerprint,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                )
            )

    def enforce_blocking(
        self,
        *,
        token: str | None,
        preflight: ResourcePreflightResult,
    ) -> None:
        """Reject blocking risk before identity hashing or parser setup."""
        if not preflight.blocking:
            return
        with self._lock:
            self._authority.discard(token)
            enforce_resource_preflight(preflight, confirmed=False)

    def _issue(
        self,
        *,
        preflight: ResourcePreflightResult,
        scope_fingerprint: str,
        configuration_fingerprint: str,
        preflight_fingerprint: str,
    ) -> _LabelPreflightReceipt:
        challenge = self._authority.issue(
            payload=preflight,
            scope_fingerprint=scope_fingerprint,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        receipt = self._authority.peek(
            challenge.challenge_id,
            scope_fingerprint=scope_fingerprint,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        if receipt is None:  # pragma: no cover - issue and lookup share one lock
            raise RuntimeError("Issued label resource challenge was not stored.")
        return receipt

    @staticmethod
    def _confirmation_error(
        receipt: _LabelPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )
