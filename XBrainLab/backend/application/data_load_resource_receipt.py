"""One-shot RAM-warning receipts for the legacy ``load_data`` command."""

from __future__ import annotations

import time
from pathlib import Path
from threading import RLock
from typing import Any

from .commands import CommandName, LoadDataCommand
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
    fingerprint_resource_preflight,
    fingerprint_resource_scope,
)

DATA_LOAD_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
DATA_LOAD_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT

_DataLoadPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


class DataLoadResourceReceiptAuthority:
    """Authorize one exact direct-load attempt before its import side effect."""

    def __init__(self) -> None:
        self._authority = ResourceReceiptAuthority[ResourcePreflightResult](
            command_name=CommandName.LOAD_DATA.value,
            ttl_seconds=DATA_LOAD_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=DATA_LOAD_PREFLIGHT_RECEIPT_LIMIT,
            clock=lambda: time.monotonic(),
        )
        self._lock = RLock()

    def annotate(
        self,
        command: LoadDataCommand,
        preflight: ResourcePreflightResult,
    ) -> ResourcePreflightResult:
        """Bind the estimate to command options and ordered on-disk identities."""
        configuration_fingerprint = fingerprint_resource_scope(
            {
                "command": CommandName.LOAD_DATA.value,
                "allow_append": bool(command.allow_append),
            }
        )
        path_identities = [
            _path_identity(path, index=index)
            for index, path in enumerate(command.paths)
        ]
        preflight_fingerprint = fingerprint_resource_preflight(
            {
                "risk_level": preflight.risk_level.value,
                "issue_count": len(preflight.issues),
                "warning_count": len(preflight.warnings),
                "unknown_count": len(preflight.unknowns),
                # The ratio changes whenever other processes use RAM. The backend
                # still binds consent to the aggregate risk and required estimate,
                # but does not invalidate it for harmless live-memory jitter.
                "diagnostics": {
                    key: value
                    for key, value in preflight.diagnostics.items()
                    if key != "required_to_available_ratio"
                },
            }
        )
        scope_fingerprint = fingerprint_resource_scope(
            {
                "command": CommandName.LOAD_DATA.value,
                "configuration_fingerprint": configuration_fingerprint,
                "ordered_paths": path_identities,
                "preflight_fingerprint": preflight_fingerprint,
            }
        )
        return _with_diagnostics(
            preflight,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
            scope_fingerprint=scope_fingerprint,
        )

    def authorize(
        self,
        command: LoadDataCommand,
        preflight: ResourcePreflightResult,
    ) -> ResourcePreflightResult:
        """Consume one matching receipt or raise a backend-issued challenge."""
        with self._lock:
            token = command.resource_preflight_token
            if preflight.blocking:
                self._authority.discard(token)
                enforce_resource_preflight(preflight, confirmed=False)

            if not preflight.requires_confirmation:
                self._authority.discard(token)
                enforce_resource_preflight(preflight, confirmed=False)
                return _with_diagnostics(
                    preflight,
                    confirmation_receipt_reused=False,
                )

            receipt = self._matching(token, preflight)
            if receipt is not None:
                if not command.resource_preflight_confirmed:
                    raise self._confirmation_error(receipt)
                enforce_resource_preflight(preflight, confirmed=True)
                consumed = self._authority.consume(
                    receipt.challenge.challenge_id,
                    scope_fingerprint=receipt.challenge.scope_fingerprint,
                    configuration_fingerprint=(
                        receipt.challenge.configuration_fingerprint
                    ),
                    preflight_fingerprint=receipt.challenge.preflight_fingerprint,
                )
                if consumed is None:
                    raise self._confirmation_error(self._issue(preflight))
                # Consent is spent before DatasetController.import_files. A loader
                # failure therefore cannot leave a reusable authorization behind.
                return _with_diagnostics(
                    preflight,
                    confirmation_receipt_reused=True,
                )

            if token:
                self._authority.discard(token)
            receipt = None
            if not command.resource_preflight_confirmed:
                receipt = self._pending(preflight)
            raise self._confirmation_error(receipt or self._issue(preflight))

    def _matching(
        self,
        token: str | None,
        preflight: ResourcePreflightResult,
    ) -> _DataLoadPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.peek(
            token,
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )

    def _pending(
        self,
        preflight: ResourcePreflightResult,
    ) -> _DataLoadPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.pending(
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )

    def _issue(
        self,
        preflight: ResourcePreflightResult,
    ) -> _DataLoadPreflightReceipt:
        diagnostics = preflight.diagnostics
        challenge = self._authority.issue(
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            payload=preflight,
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )
        receipt = self._authority.peek(
            challenge.challenge_id,
            scope_fingerprint=challenge.scope_fingerprint,
            configuration_fingerprint=challenge.configuration_fingerprint,
            preflight_fingerprint=challenge.preflight_fingerprint,
        )
        if receipt is None:  # pragma: no cover - issue and lookup share one lock
            raise RuntimeError("Issued data-load resource challenge was not stored.")
        return receipt

    @staticmethod
    def _confirmation_error(
        receipt: _DataLoadPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )


def _path_identity(path_value: str, *, index: int) -> dict[str, Any]:
    """Return an ordered, non-loading identity for one selected path."""
    path = Path(path_value).expanduser()
    identity: dict[str, Any] = {
        "index": index,
        "resolved_path": str(path.resolve(strict=False)),
    }
    try:
        stat = path.stat()
    except OSError as exc:
        identity.update(
            {
                "status": "unavailable",
                "error_type": exc.__class__.__name__,
            }
        )
        return identity
    identity.update(
        {
            "status": "available",
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "mode": stat.st_mode,
        }
    )
    return identity


def _with_diagnostics(
    preflight: ResourcePreflightResult,
    **updates: Any,
) -> ResourcePreflightResult:
    return ResourcePreflightResult(
        issues=preflight.issues,
        diagnostics={**preflight.diagnostics, **updates},
        warnings=preflight.warnings,
        unknowns=preflight.unknowns,
    )
