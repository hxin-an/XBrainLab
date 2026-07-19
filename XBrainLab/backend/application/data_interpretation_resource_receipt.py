"""One-shot resource receipts for Data Interpretation preview/review/reload."""

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

INTERPRETATION_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
INTERPRETATION_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT

_InterpretationPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


class DataInterpretationResourceReceiptAuthority:
    """Authorize one exact preview/review/reload resource attempt."""

    def __init__(self, *, command_name: str) -> None:
        self.command_name = command_name
        self._authority = ResourceReceiptAuthority[ResourcePreflightResult](
            command_name=command_name,
            ttl_seconds=INTERPRETATION_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=INTERPRETATION_PREFLIGHT_RECEIPT_LIMIT,
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
        candidate_id: str | None = None,
    ) -> bool:
        """Consume one matching receipt or raise a fresh typed challenge."""
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
                candidate_id=candidate_id,
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
                    candidate_id=candidate_id,
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
                            candidate_id=candidate_id,
                        )
                    )
                # Consume before parser/materialization/state side effects. A later
                # failure still spends this consent and requires a fresh challenge.
                return True

            if token:
                self._authority.discard(token)
            receipt = None
            if not confirmed:
                receipt = self._authority.pending(
                    scope_fingerprint=scope_fingerprint,
                    candidate_id=candidate_id,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                )
            if receipt is None:
                receipt = self._issue(
                    preflight=preflight,
                    scope_fingerprint=scope_fingerprint,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                    candidate_id=candidate_id,
                )
            raise self._confirmation_error(receipt)

    def clear(self) -> None:
        """Discard all pending challenges for this command."""
        self._authority.clear()

    def _issue(
        self,
        *,
        preflight: ResourcePreflightResult,
        scope_fingerprint: str,
        configuration_fingerprint: str,
        preflight_fingerprint: str,
        candidate_id: str | None,
    ) -> _InterpretationPreflightReceipt:
        challenge = self._authority.issue(
            payload=preflight,
            scope_fingerprint=scope_fingerprint,
            candidate_id=candidate_id,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        receipt = self._authority.peek(
            challenge.challenge_id,
            scope_fingerprint=scope_fingerprint,
            candidate_id=candidate_id,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        )
        if receipt is None:  # pragma: no cover - issue and lookup share one lock
            raise RuntimeError(
                "Issued interpretation resource challenge was not stored."
            )
        return receipt

    @staticmethod
    def _confirmation_error(
        receipt: _InterpretationPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )
