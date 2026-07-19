"""One-shot resource confirmation authority and deterministic fingerprints."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Any, Generic, TypeVar

from .resource_preflight import ResourceConfirmationChallenge

DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS = 120.0
DEFAULT_RESOURCE_RECEIPT_LIMIT = 8

_T = TypeVar("_T")
_UNSET = object()
_PREFLIGHT_FINGERPRINT_VOLATILE_KEYS = frozenset(
    {
        "allocated_bytes",
        "available_bytes",
        "available_memory_bytes",
        "available_ram_bytes",
        "available_vram_bytes",
        "confirmation_challenge",
        "confirmation_command",
        "confirmation_receipt_reused",
        "confirmation_token",
        "confirmation_ttl_seconds",
        "configuration_fingerprint",
        "free_bytes",
        "message",
        "preflight_fingerprint",
        "reserved_bytes",
        "scope_fingerprint",
        "suggestions",
        "total_bytes",
        "total_memory_bytes",
        "used_bytes",
        "used_memory_bytes",
    }
)


@dataclass(frozen=True, slots=True)
class ResourceReceiptRecord(Generic[_T]):
    """Stored challenge and its backend-only preflight payload."""

    challenge: ResourceConfirmationChallenge
    payload: _T
    created_at: float


class ResourceReceiptAuthority(Generic[_T]):
    """Thread-safe, bounded, consume-once authority for resource challenges."""

    def __init__(
        self,
        *,
        command_name: str,
        ttl_seconds: float = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS,
        max_receipts: int = DEFAULT_RESOURCE_RECEIPT_LIMIT,
        clock: Callable[[], float] | None = None,
        challenge_id_factory: Callable[[], str] | None = None,
    ) -> None:
        normalized_command = _text(command_name)
        if not normalized_command:
            raise ValueError("command_name is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_receipts <= 0:
            raise ValueError("max_receipts must be positive")
        self.command_name = normalized_command
        self.ttl_seconds = float(ttl_seconds)
        self.max_receipts = int(max_receipts)
        self._clock = clock or time.monotonic
        self._challenge_id_factory = challenge_id_factory or (
            lambda: secrets.token_urlsafe(24)
        )
        self._records: dict[str, ResourceReceiptRecord[_T]] = {}
        self._lock = RLock()

    def issue(
        self,
        *,
        scope_fingerprint: str,
        payload: _T,
        candidate_id: str | None = None,
        configuration_fingerprint: str | None = None,
        preflight_fingerprint: str | None = None,
    ) -> ResourceConfirmationChallenge:
        """Issue one bounded challenge for an exact caller-owned scope."""
        scope = _text(scope_fingerprint)
        if not scope:
            raise ValueError("scope_fingerprint is required")
        with self._lock:
            self._discard_expired_locked()
            while len(self._records) >= self.max_receipts:
                oldest = min(self._records.values(), key=lambda item: item.created_at)
                self._records.pop(oldest.challenge.challenge_id, None)
            challenge_id = _text(self._challenge_id_factory())
            if not challenge_id:
                raise ValueError("challenge_id_factory returned an empty value")
            if challenge_id in self._records:
                raise RuntimeError("Resource challenge ID collision.")
            challenge = ResourceConfirmationChallenge(
                challenge_id=challenge_id,
                command_name=self.command_name,
                scope_fingerprint=scope,
                ttl_seconds=self.ttl_seconds,
                candidate_id=_optional_text(candidate_id),
                configuration_fingerprint=_optional_text(configuration_fingerprint),
                preflight_fingerprint=_optional_text(preflight_fingerprint),
            )
            self._records[challenge.challenge_id] = ResourceReceiptRecord(
                challenge=challenge,
                payload=payload,
                created_at=self._clock(),
            )
            return challenge

    def pending(
        self,
        *,
        scope_fingerprint: str,
        candidate_id: str | None | object = _UNSET,
        configuration_fingerprint: str | None | object = _UNSET,
        preflight_fingerprint: str | None | object = _UNSET,
    ) -> ResourceReceiptRecord[_T] | None:
        """Return the newest unexpired challenge for the exact supplied scope."""
        with self._lock:
            self._discard_expired_locked()
            records = (
                record
                for record in self._records.values()
                if self._matches(
                    record.challenge,
                    scope_fingerprint=scope_fingerprint,
                    candidate_id=candidate_id,
                    configuration_fingerprint=configuration_fingerprint,
                    preflight_fingerprint=preflight_fingerprint,
                )
            )
            return max(records, key=lambda item: item.created_at, default=None)

    def peek(
        self,
        challenge_id: str | None,
        *,
        scope_fingerprint: str,
        candidate_id: str | None | object = _UNSET,
        configuration_fingerprint: str | None | object = _UNSET,
        preflight_fingerprint: str | None | object = _UNSET,
    ) -> ResourceReceiptRecord[_T] | None:
        """Validate a challenge without consuming it; mismatch invalidates it."""
        with self._lock:
            return self._resolve_locked(
                challenge_id,
                scope_fingerprint=scope_fingerprint,
                candidate_id=candidate_id,
                configuration_fingerprint=configuration_fingerprint,
                preflight_fingerprint=preflight_fingerprint,
                consume=False,
            )

    def consume(
        self,
        challenge_id: str | None,
        *,
        scope_fingerprint: str,
        candidate_id: str | None | object = _UNSET,
        configuration_fingerprint: str | None | object = _UNSET,
        preflight_fingerprint: str | None | object = _UNSET,
    ) -> ResourceReceiptRecord[_T] | None:
        """Atomically validate and consume one challenge."""
        with self._lock:
            return self._resolve_locked(
                challenge_id,
                scope_fingerprint=scope_fingerprint,
                candidate_id=candidate_id,
                configuration_fingerprint=configuration_fingerprint,
                preflight_fingerprint=preflight_fingerprint,
                consume=True,
            )

    def discard(self, challenge_id: str | None) -> None:
        normalized = _text(challenge_id)
        if not normalized:
            return
        with self._lock:
            self._records.pop(normalized, None)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def _resolve_locked(
        self,
        challenge_id: str | None,
        *,
        scope_fingerprint: str,
        candidate_id: str | None | object,
        configuration_fingerprint: str | None | object,
        preflight_fingerprint: str | None | object,
        consume: bool,
    ) -> ResourceReceiptRecord[_T] | None:
        self._discard_expired_locked()
        normalized_id = _text(challenge_id)
        if not normalized_id:
            return None
        record = self._records.get(normalized_id)
        if record is None:
            return None
        if not self._matches(
            record.challenge,
            scope_fingerprint=scope_fingerprint,
            candidate_id=candidate_id,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
        ):
            self._records.pop(normalized_id, None)
            return None
        if consume:
            self._records.pop(normalized_id, None)
        return record

    def _discard_expired_locked(self) -> None:
        now = self._clock()
        expired = [
            challenge_id
            for challenge_id, record in self._records.items()
            if now - record.created_at >= self.ttl_seconds
        ]
        for challenge_id in expired:
            self._records.pop(challenge_id, None)

    def _matches(
        self,
        challenge: ResourceConfirmationChallenge,
        *,
        scope_fingerprint: str,
        candidate_id: str | None | object,
        configuration_fingerprint: str | None | object,
        preflight_fingerprint: str | None | object,
    ) -> bool:
        if challenge.command_name != self.command_name:
            return False
        if challenge.scope_fingerprint != _text(scope_fingerprint):
            return False
        checks = (
            (candidate_id, challenge.candidate_id),
            (configuration_fingerprint, challenge.configuration_fingerprint),
            (preflight_fingerprint, challenge.preflight_fingerprint),
        )
        return all(
            supplied is _UNSET or _optional_text(supplied) == expected
            for supplied, expected in checks
        )


def fingerprint_resource_preflight(value: Any) -> str:
    """Return a stable fingerprint excluding live memory and receipt fields."""
    if hasattr(value, "to_diagnostics") and callable(value.to_diagnostics):
        value = value.to_diagnostics()
    return fingerprint_resource_scope(_stable_preflight_value(value))


def fingerprint_resource_scope(value: Any) -> str:
    """Return a deterministic SHA-256 fingerprint for caller-owned scope data."""
    payload = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_preflight_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_preflight_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _PREFLIGHT_FINGERPRINT_VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stable_preflight_value(item) for item in value]
    return _canonical_value(value)


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return repr(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    result = _text(value)
    return result or None
