"""Typed, correlated confirmation for assistant-proposed mutations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

_INTERNAL_CONFIRMATION_PARAMS = frozenset(
    {
        "confirmed",
        "resource_preflight_confirmed",
        "resource_preflight_token",
    }
)


class AgentConfirmationResolutionStatus(str, Enum):
    """Explicit user decision for one still-current confirmation request."""

    APPROVED = "approved"
    CANCELLED = "cancelled"


_COMMAND_IMPACT_TEXT = {
    "start_training": (
        "Starts a potentially long GPU or CPU job using the configured resources. "
        "You can stop it after it starts."
    ),
}
_HIGH_IMPACT_DECISION_BOUNDARIES = frozenset(
    {"high_impact", "high_impact_setting_change"}
)


@dataclass(frozen=True, slots=True)
class AgentConfirmationRisk:
    """Typed impact semantics copied from one verified action policy."""

    destructive: bool = False
    high_impact: bool = False
    long_running: bool = False
    decision_boundary: str | None = None
    impact_text: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.destructive, "destructive"),
            (self.high_impact, "high-impact"),
            (self.long_running, "long-running"),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"Confirmation {label} risk must be a boolean.")
        for value, label in (
            (self.decision_boundary, "decision boundary"),
            (self.impact_text, "impact text"),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"Confirmation {label} must be text or None.")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Confirmation {label} cannot be empty.")

    @classmethod
    def from_policy(
        cls,
        *,
        command_name: str,
        destructive: bool,
        high_impact: bool,
        long_running: bool,
        decision_boundary: str | None,
    ) -> AgentConfirmationRisk:
        """Copy typed policy facts without inferring them from display prose."""
        command = _require_text(command_name, "Confirmation risk command")
        typed_high_impact = bool(
            high_impact or decision_boundary in _HIGH_IMPACT_DECISION_BOUNDARIES
        )
        boundary = (
            "high_impact_setting_change"
            if typed_high_impact and not decision_boundary
            else decision_boundary
        )
        impact_text = _COMMAND_IMPACT_TEXT.get(command)
        if typed_high_impact and command in {"configure_training", "set_model"}:
            impact_text = (
                "Changes the model or training settings used by the next run. "
                "XBrainLab will validate the reviewed values before applying them."
            )
        return cls(
            destructive=destructive,
            high_impact=typed_high_impact,
            long_running=long_running,
            decision_boundary=boundary,
            impact_text=impact_text,
        )


@dataclass(frozen=True, slots=True)
class AgentConfirmationRequest:
    """One exact assistant action waiting for an explicit user decision."""

    command_name: str
    params_fingerprint: str
    action_label: str
    description: str
    risk: AgentConfirmationRisk
    publication_generation: int | None
    confirmation_kind: str | None = None
    parameter_rows: tuple[tuple[str, str], ...] = ()
    request_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        _require_text(self.request_id, "Confirmation request id")
        _require_text(self.command_name, "Confirmation command")
        _require_text(self.params_fingerprint, "Confirmation params fingerprint")
        _require_text(self.action_label, "Confirmation action label")
        _require_text(self.description, "Confirmation description")
        if not isinstance(self.risk, AgentConfirmationRisk):
            raise TypeError("Confirmation risk must use the typed risk contract.")
        _validate_generation(self.publication_generation)
        if self.confirmation_kind is not None and not isinstance(
            self.confirmation_kind,
            str,
        ):
            raise TypeError("Confirmation kind must be text or None.")
        if not isinstance(self.parameter_rows, tuple) or not all(
            isinstance(row, tuple)
            and len(row) == 2
            and all(isinstance(value, str) for value in row)
            for row in self.parameter_rows
        ):
            raise TypeError("Confirmation parameter rows must be typed text pairs.")

    @property
    def destructive(self) -> bool:
        return self.risk.destructive

    @property
    def high_impact(self) -> bool:
        return self.risk.high_impact

    @property
    def long_running(self) -> bool:
        return self.risk.long_running

    @property
    def decision_boundary(self) -> str | None:
        return self.risk.decision_boundary

    @property
    def impact_text(self) -> str | None:
        return self.risk.impact_text

    @classmethod
    def for_action(
        cls,
        *,
        command_name: str,
        params: Mapping[str, Any],
        action_label: str,
        description: str,
        destructive: bool,
        publication_generation: int | None,
        confirmation_kind: str | None = None,
        request_id: str | None = None,
        risk: AgentConfirmationRisk | None = None,
    ) -> AgentConfirmationRequest:
        """Build a request from exact params and a safe human-readable summary."""
        if not isinstance(params, Mapping):
            raise TypeError("Confirmation params must be a mapping.")
        command = _require_text(command_name, "Confirmation command")
        if not isinstance(destructive, bool):
            raise TypeError("Confirmation destructive flag must be a boolean.")
        typed_risk = risk or AgentConfirmationRisk(destructive=destructive)
        if not isinstance(typed_risk, AgentConfirmationRisk):
            raise TypeError("Confirmation risk must use the typed risk contract.")
        if typed_risk.destructive is not destructive:
            raise ValueError("Confirmation destructive flag must match its typed risk.")
        request = uuid4().hex if request_id is None else str(request_id).strip()
        return cls(
            command_name=command,
            params_fingerprint=_fingerprint_params(params),
            action_label=" ".join(str(action_label or "").split()),
            description=" ".join(str(description or "").split()),
            risk=typed_risk,
            publication_generation=publication_generation,
            confirmation_kind=(
                " ".join(confirmation_kind.split()) if confirmation_kind else None
            ),
            parameter_rows=_parameter_rows(params),
            request_id=request,
        )


@dataclass(frozen=True, slots=True)
class AgentConfirmationResolution:
    """Correlated answer that can approve only its originating request."""

    request_id: str
    command_name: str
    params_fingerprint: str
    publication_generation: int | None
    status: AgentConfirmationResolutionStatus

    def __post_init__(self) -> None:
        _require_text(self.request_id, "Confirmation resolution id")
        _require_text(self.command_name, "Confirmation resolution command")
        _require_text(
            self.params_fingerprint,
            "Confirmation resolution params fingerprint",
        )
        _validate_generation(self.publication_generation)
        if not isinstance(self.status, AgentConfirmationResolutionStatus):
            raise TypeError("Confirmation resolution status must be typed.")

    @property
    def approved(self) -> bool:
        return self.status is AgentConfirmationResolutionStatus.APPROVED

    def matches(self, request: AgentConfirmationRequest) -> bool:
        """Return whether this answer belongs to the exact still-pending action."""
        return bool(
            isinstance(request, AgentConfirmationRequest)
            and self.request_id == request.request_id
            and self.command_name == request.command_name
            and self.params_fingerprint == request.params_fingerprint
            and self.publication_generation == request.publication_generation
        )

    @classmethod
    def for_request(
        cls,
        request: AgentConfirmationRequest,
        *,
        status: AgentConfirmationResolutionStatus,
    ) -> AgentConfirmationResolution:
        if not isinstance(request, AgentConfirmationRequest):
            raise TypeError("Confirmation resolution requires a typed request.")
        if not isinstance(status, AgentConfirmationResolutionStatus):
            raise TypeError("Confirmation resolution status must be typed.")
        return cls(
            request_id=request.request_id,
            command_name=request.command_name,
            params_fingerprint=request.params_fingerprint,
            publication_generation=request.publication_generation,
            status=status,
        )


def _fingerprint_params(params: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _canonical_value(params),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parameter_rows(params: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for raw_key, value in sorted(params.items(), key=lambda item: str(item[0])):
        key = str(raw_key)
        if key in _INTERNAL_CONFIRMATION_PARAMS:
            continue
        display_value = _display_value(value)
        rows.append((key.replace("_", " ").strip().capitalize(), display_value))
    return tuple(rows)


def _display_value(value: Any) -> str:
    normalized = _canonical_value(value)
    if isinstance(normalized, str):
        return normalized
    return json.dumps(normalized, ensure_ascii=True, sort_keys=True)


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return repr(value)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    return normalized


def _validate_generation(value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Confirmation publication generation must be non-negative.")
