"""Typed resource-preflight wire contract shared by application clients.

Resource estimators remain in :mod:`resource_guard`.  This module owns the
serialized contract shared by backend, desktop UI, and agent clients.  Receipt
storage and lifecycle enforcement live in :mod:`resource_receipt`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

RESOURCE_PREFLIGHT_SCHEMA_VERSION = 1
RESOURCE_CONFIRMATION_SCHEMA_VERSION = 1

_KNOWN_RISK_LEVELS = frozenset({"safe", "warning", "blocking", "unknown"})

_PREFLIGHT_STANDARD_KEYS = frozenset(
    {
        "schema_version",
        "risk_level",
        "requires_confirmation",
        "issues",
        "warnings",
        "unknowns",
        "message",
        "suggestions",
        "required_memory_bytes",
        "available_memory_bytes",
        "total_memory_bytes",
        "used_memory_bytes",
        "dataset_ram_risk_level",
        "vram",
        "vram_risk_level",
        "model_name",
        "training_batch_size",
        "reason",
        "confirmation_challenge",
        # Flat aliases are emitted only for compatibility with command clients
        # that still call their input field ``resource_preflight_token``.
        "confirmation_token",
        "confirmation_command",
        "confirmation_ttl_seconds",
        "candidate_id",
        "configuration_fingerprint",
        "preflight_fingerprint",
        "scope_fingerprint",
    }
)


class ResourcePreflightContractError(ValueError):
    """Raised when a resource-preflight payload violates the wire contract."""


@dataclass(frozen=True, slots=True)
class ResourceConfirmationChallenge:
    """Backend-issued proof bound to one command and one exact resource scope."""

    challenge_id: str
    command_name: str
    scope_fingerprint: str
    ttl_seconds: float
    candidate_id: str | None = None
    configuration_fingerprint: str | None = None
    preflight_fingerprint: str | None = None
    schema_version: int = RESOURCE_CONFIRMATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema_version(
            {"schema_version": self.schema_version},
            contract_name="resource confirmation",
            expected_version=RESOURCE_CONFIRMATION_SCHEMA_VERSION,
        )
        if not _text(self.challenge_id):
            raise ResourcePreflightContractError(
                "Resource confirmation challenge ID is required."
            )
        if not _text(self.command_name) or not _text(self.scope_fingerprint):
            raise ResourcePreflightContractError(
                "Resource confirmation command and scope are required."
            )
        if _positive_float(self.ttl_seconds) is None:
            raise ResourcePreflightContractError(
                "Resource confirmation TTL must be positive."
            )

    @property
    def token(self) -> str:
        """Compatibility alias for command fields that still use token naming."""
        return self.challenge_id

    def to_diagnostics(self) -> dict[str, Any]:
        """Serialize the canonical confirmation challenge."""
        return {
            "schema_version": self.schema_version,
            "challenge_id": self.challenge_id,
            "command_name": self.command_name,
            "scope_fingerprint": self.scope_fingerprint,
            "ttl_seconds": self.ttl_seconds,
            "candidate_id": self.candidate_id,
            "configuration_fingerprint": self.configuration_fingerprint,
            "preflight_fingerprint": self.preflight_fingerprint,
        }

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: Mapping[str, Any] | None,
    ) -> ResourceConfirmationChallenge | None:
        """Parse the canonical challenge, with one centralized legacy adapter."""
        if not isinstance(diagnostics, Mapping):
            return None
        payload = _preflight_payload(diagnostics)
        nested = payload.get("confirmation_challenge")
        if isinstance(nested, Mapping):
            raw = nested
            schema_version = _schema_version(
                raw,
                contract_name="resource confirmation",
                expected_version=RESOURCE_CONFIRMATION_SCHEMA_VERSION,
            )
            challenge_id = _text(raw.get("challenge_id"))
            command_name = _text(raw.get("command_name"))
            scope_fingerprint = _text(raw.get("scope_fingerprint"))
            ttl_seconds = _positive_float(raw.get("ttl_seconds"))
            candidate_id = _optional_text(raw.get("candidate_id"))
            configuration_fingerprint = _optional_text(
                raw.get("configuration_fingerprint")
            )
            preflight_fingerprint = _optional_text(raw.get("preflight_fingerprint"))
        else:
            if "confirmation_challenge" in payload and nested is not None:
                raise ResourcePreflightContractError(
                    "Resource confirmation challenge must be a mapping."
                )
            # Compatibility is intentionally confined here.  Product clients do
            # not read these flat keys themselves.
            schema_version = RESOURCE_CONFIRMATION_SCHEMA_VERSION
            challenge_id = _text(payload.get("confirmation_token"))
            command_name = _text(payload.get("confirmation_command"))
            candidate_id = _optional_text(payload.get("candidate_id"))
            if not command_name:
                payload_type = _text(payload.get("payload_type"))
                if payload_type == "training_resource_preflight":
                    command_name = "start_training"
                elif candidate_id:
                    command_name = "apply_interpretation"
            scope_fingerprint = _text(payload.get("scope_fingerprint"))
            ttl_seconds = _positive_float(payload.get("confirmation_ttl_seconds"))
            configuration_fingerprint = _optional_text(
                payload.get("configuration_fingerprint")
            )
            preflight_fingerprint = _optional_text(payload.get("preflight_fingerprint"))

        if not challenge_id:
            return None
        if not command_name or not scope_fingerprint or ttl_seconds is None:
            raise ResourcePreflightContractError(
                "Resource confirmation challenge is incomplete."
            )
        return cls(
            challenge_id=challenge_id,
            command_name=command_name,
            scope_fingerprint=scope_fingerprint,
            ttl_seconds=ttl_seconds,
            candidate_id=candidate_id,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
            schema_version=schema_version,
        )


@dataclass(frozen=True, slots=True)
class ResourceMemoryView:
    """Typed memory estimate used by UI and agent presentation code."""

    risk_level: str = "unknown"
    required_memory_bytes: int | None = None
    available_memory_bytes: int | None = None
    total_memory_bytes: int | None = None
    used_memory_bytes: int | None = None
    message: str = ""
    suggestions: tuple[str, ...] = ()
    gpu_name: str | None = None
    gpu_index: int | None = None
    reason: str | None = None

    @property
    def has_data(self) -> bool:
        return any(
            (
                self.required_memory_bytes is not None,
                self.available_memory_bytes is not None,
                self.total_memory_bytes is not None,
                bool(self.message),
                bool(self.gpu_name),
                bool(self.reason),
            )
        )

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "required_memory_bytes": self.required_memory_bytes,
            "available_memory_bytes": self.available_memory_bytes,
            "total_memory_bytes": self.total_memory_bytes,
            "used_memory_bytes": self.used_memory_bytes,
            "message": self.message,
            "suggestions": list(self.suggestions),
            "gpu_name": self.gpu_name,
            "gpu_index": self.gpu_index,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ResourcePreflightView:
    """Versioned application-client view of one resource preflight result."""

    risk_level: str
    requires_confirmation: bool
    message: str
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    dataset_ram: ResourceMemoryView = field(default_factory=ResourceMemoryView)
    vram: ResourceMemoryView = field(default_factory=ResourceMemoryView)
    model_name: str | None = None
    batch_size: int | None = None
    reason: str | None = None
    challenge: ResourceConfirmationChallenge | None = None
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = RESOURCE_PREFLIGHT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        risk_level: str,
        requires_confirmation: bool,
        message: str,
        issues: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        unknowns: tuple[str, ...] = (),
        suggestions: tuple[str, ...] = (),
        details: Mapping[str, Any] | None = None,
        challenge: ResourceConfirmationChallenge | None = None,
    ) -> ResourcePreflightView:
        """Build a typed view from backend-owned result components."""
        payload = {
            **dict(details or {}),
            "schema_version": RESOURCE_PREFLIGHT_SCHEMA_VERSION,
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "message": message,
            "issues": list(issues),
            "warnings": list(warnings),
            "unknowns": list(unknowns),
            "suggestions": list(suggestions),
        }
        if challenge is not None:
            payload["confirmation_challenge"] = challenge.to_diagnostics()
        view = cls.from_diagnostics(payload)
        if view is None:  # pragma: no cover - the payload above is always complete
            raise ResourcePreflightContractError("Resource preflight is empty.")
        return view

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: Mapping[str, Any] | None,
    ) -> ResourcePreflightView | None:
        """Parse a command result or a direct resource-preflight payload."""
        if not isinstance(diagnostics, Mapping):
            return None
        payload = _preflight_payload(diagnostics)
        if not payload or not _looks_like_preflight(payload):
            return None
        schema_version = _schema_version(
            payload,
            contract_name="resource preflight",
            expected_version=RESOURCE_PREFLIGHT_SCHEMA_VERSION,
        )
        issues = _text_tuple(payload.get("issues"))
        warnings = _text_tuple(payload.get("warnings"))
        unknowns = _text_tuple(payload.get("unknowns"))
        risk_level = _risk_level(payload.get("risk_level"), issues, warnings, unknowns)
        requires_confirmation = (
            _boolean(payload.get("requires_confirmation"))
            if "requires_confirmation" in payload
            else risk_level in {"warning", "unknown"}
        )
        message = _text(payload.get("message"))
        suggestions = _text_tuple(payload.get("suggestions"))
        challenge = ResourceConfirmationChallenge.from_diagnostics(payload)
        dataset_ram = _memory_view(
            payload,
            risk_level=payload.get("dataset_ram_risk_level", risk_level),
            required_keys=(
                "required_memory_bytes",
                "estimated_ram_working_set_bytes",
            ),
            available_keys=("available_memory_bytes", "available_ram_bytes"),
        )
        raw_vram = payload.get("vram")
        vram_payload = dict(raw_vram) if isinstance(raw_vram, Mapping) else {}
        vram = _memory_view(
            vram_payload or payload,
            risk_level=payload.get(
                "vram_risk_level",
                vram_payload.get("risk_level", "unknown"),
            ),
            required_keys=(
                "required_memory_bytes",
                "estimated_vram_bytes",
                "estimated_gpu_batch_working_set_bytes",
            ),
            available_keys=("available_memory_bytes", "available_vram_bytes"),
        )
        details = {
            str(key): value
            for key, value in payload.items()
            if str(key) not in _PREFLIGHT_STANDARD_KEYS
        }
        return cls(
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            message=message,
            issues=issues,
            warnings=warnings,
            unknowns=unknowns,
            suggestions=suggestions,
            dataset_ram=dataset_ram,
            vram=vram,
            model_name=_optional_text(payload.get("model_name")),
            batch_size=_optional_int(payload.get("training_batch_size")),
            reason=_optional_text(payload.get("reason")),
            challenge=challenge,
            details=details,
            schema_version=schema_version,
        )

    def with_challenge(
        self,
        challenge: ResourceConfirmationChallenge | None,
    ) -> ResourcePreflightView:
        """Return the same preflight presentation with a backend challenge."""
        return ResourcePreflightView(
            risk_level=self.risk_level,
            requires_confirmation=self.requires_confirmation,
            message=self.message,
            issues=self.issues,
            warnings=self.warnings,
            unknowns=self.unknowns,
            suggestions=self.suggestions,
            dataset_ram=self.dataset_ram,
            vram=self.vram,
            model_name=self.model_name,
            batch_size=self.batch_size,
            reason=self.reason,
            challenge=challenge,
            details=dict(self.details),
            schema_version=self.schema_version,
        )

    def to_diagnostics(self) -> dict[str, Any]:
        """Serialize the sole versioned resource-preflight wire representation."""
        payload = {
            **dict(self.details),
            "schema_version": self.schema_version,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "unknowns": list(self.unknowns),
            "message": self.message,
            "suggestions": list(self.suggestions),
            "required_memory_bytes": self.dataset_ram.required_memory_bytes,
            "available_memory_bytes": self.dataset_ram.available_memory_bytes,
            "total_memory_bytes": self.dataset_ram.total_memory_bytes,
            "used_memory_bytes": self.dataset_ram.used_memory_bytes,
            "dataset_ram_risk_level": self.dataset_ram.risk_level,
        }
        if self.vram.has_data:
            payload["vram"] = self.vram.to_diagnostics()
            payload["vram_risk_level"] = self.vram.risk_level
        if self.model_name is not None:
            payload["model_name"] = self.model_name
        if self.batch_size is not None:
            payload["training_batch_size"] = self.batch_size
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.challenge is not None:
            challenge = self.challenge
            payload["confirmation_challenge"] = challenge.to_diagnostics()
            # Transitional aliases are all derived from the canonical challenge.
            payload.update(
                {
                    "confirmation_token": challenge.challenge_id,
                    "confirmation_command": challenge.command_name,
                    "confirmation_ttl_seconds": challenge.ttl_seconds,
                    "candidate_id": challenge.candidate_id,
                    "configuration_fingerprint": (challenge.configuration_fingerprint),
                    "preflight_fingerprint": challenge.preflight_fingerprint,
                    "scope_fingerprint": challenge.scope_fingerprint,
                }
            )
        return payload


def _preflight_payload(diagnostics: Mapping[str, Any]) -> Mapping[str, Any]:
    if "resource_preflight" not in diagnostics:
        return diagnostics
    nested = diagnostics.get("resource_preflight")
    if not isinstance(nested, Mapping):
        raise ResourcePreflightContractError(
            "Resource preflight diagnostics must be a mapping."
        )
    return nested


def _looks_like_preflight(payload: Mapping[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "schema_version",
            "risk_level",
            "requires_confirmation",
            "issues",
            "warnings",
            "unknowns",
            "message",
            "confirmation_challenge",
            "confirmation_token",
        )
    )


def _schema_version(
    payload: Mapping[str, Any],
    *,
    contract_name: str,
    expected_version: int,
) -> int:
    raw = payload.get("schema_version")
    if raw is None:
        # Version 0 is the temporary flat-key compatibility input.  It is always
        # normalized to the current schema when serialized again.
        return expected_version
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ResourcePreflightContractError(
            f"Invalid {contract_name} schema version."
        ) from exc
    if version != expected_version:
        raise ResourcePreflightContractError(
            f"Unsupported {contract_name} schema version: {version}."
        )
    return version


def _memory_view(
    payload: Mapping[str, Any],
    *,
    risk_level: Any,
    required_keys: tuple[str, ...],
    available_keys: tuple[str, ...],
) -> ResourceMemoryView:
    return ResourceMemoryView(
        risk_level=_risk_level(risk_level, (), (), ()),
        required_memory_bytes=_first_int(payload, required_keys),
        available_memory_bytes=_first_int(payload, available_keys),
        total_memory_bytes=_optional_int(
            payload.get("total_memory_bytes", payload.get("total_bytes"))
        ),
        used_memory_bytes=_optional_int(
            payload.get("used_memory_bytes", payload.get("used_bytes"))
        ),
        message=_text(payload.get("message")),
        suggestions=_text_tuple(payload.get("suggestions")),
        gpu_name=_optional_text(payload.get("gpu_name")),
        gpu_index=_optional_int(payload.get("gpu_index")),
        reason=_optional_text(payload.get("reason")),
    )


def _risk_level(
    value: Any,
    issues: tuple[str, ...],
    warnings: tuple[str, ...],
    unknowns: tuple[str, ...],
) -> str:
    enum_value = getattr(value, "value", value)
    normalized = _text(enum_value).lower()
    if normalized in _KNOWN_RISK_LEVELS:
        return normalized
    if normalized:
        raise ResourcePreflightContractError(
            f"Unsupported resource risk level: {normalized}."
        )
    if issues:
        return "blocking"
    if warnings:
        return "warning"
    if unknowns:
        return "unknown"
    return "safe"


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ResourcePreflightContractError(
        "Resource preflight requires_confirmation must be a boolean."
    )


def _first_int(payload: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _optional_int(payload.get(key))
        if value is not None:
            return value
    return None


def _positive_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    result = _text(value)
    return result or None


def _text_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(text for item in value if (text := _text(item)))
