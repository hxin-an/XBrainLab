"""Strict product boundary for model-proposed request updates."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from .decision_contract import (
    MAX_NAME_LENGTH,
    MAX_QUOTE_LENGTH,
    MAX_SOURCE_TURN_LENGTH,
    REQUEST_MODE_TO_INTERNAL,
)

_REQUEST_MODE_TO_WIRE = {
    internal: wire for wire, internal in REQUEST_MODE_TO_INTERNAL.items()
}

ToolCommand: TypeAlias = tuple[str, dict[str, Any]]


class ToolEnvelopeStatus(str, Enum):
    """Classification before request admission or product execution."""

    NO_TOOL = "no_tool"
    VALID = "valid"
    MULTIPLE_OBJECTS = "multiple_objects"
    FORMAT_ERROR = "format_error"


@dataclass(frozen=True)
class ParameterChange:
    """A proposed value and its unverified user-source reference."""

    value: Any
    source_turn: str
    quote: str


@dataclass(frozen=True)
class RequestUpdate:
    """One request update; omitted parameters are not deletions."""

    mode: str
    action: str | None
    changes: tuple[tuple[str, ParameterChange], ...] = ()


@dataclass(frozen=True)
class ToolEnvelopeParseResult:
    """Only well-formed proposals expose a request; validity is not admission."""

    status: ToolEnvelopeStatus
    error: str = ""
    message: str = ""
    decision: str = ""
    request: RequestUpdate | None = None

    def proposal_dict(self) -> dict[str, Any] | None:
        """Serialize a valid proposal without inventing executable parameters."""
        if self.status not in (ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL):
            return None
        request = self.request
        return {
            "decision": self.decision,
            "mode": _REQUEST_MODE_TO_WIRE[request.mode]
            if request is not None
            else None,
            "action": request.action if request is not None else None,
            "changes": {
                name: {
                    "value": change.value,
                    "source_turn": change.source_turn,
                    "quote": change.quote,
                }
                for name, change in request.changes
            }
            if request is not None
            else {},
            "message": self.message if self.decision != "execute" else None,
        }

    @classmethod
    def multiple_objects(cls) -> ToolEnvelopeParseResult:
        return cls(
            ToolEnvelopeStatus.MULTIPLE_OBJECTS,
            error="A response contained multiple complete top-level JSON objects.",
        )

    @classmethod
    def format_error(cls, message: str) -> ToolEnvelopeParseResult:
        return cls(ToolEnvelopeStatus.FORMAT_ERROR, error=message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}.")
        result[key] = value
    return result


def _reject_non_standard_json(value: str) -> None:
    raise ValueError(f"Non-standard JSON value: {value}.")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON numbers must be finite.")
    return parsed


def _bounded_text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _name(value: Any) -> bool:
    return _bounded_text(value, MAX_NAME_LENGTH) and value == value.strip()


class CommandParser:
    """Parse one strict proposal, without inferring intent or repairing values."""

    @staticmethod
    def parse_product(text: str) -> ToolEnvelopeParseResult:
        """Accept one JSON object, optionally in one whole-response JSON fence."""
        stripped = text.strip()
        fence = re.fullmatch(
            r"```(?:json)?[ \t]*\r?\n(.*)\r?\n```", stripped, re.DOTALL
        )
        if fence is not None:
            stripped = fence.group(1).strip()
        decoder = json.JSONDecoder(
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_standard_json,
            parse_float=_finite_float,
        )
        try:
            decoded = decoder.decode(stripped)
        except json.JSONDecodeError:
            if CommandParser._has_multiple_adjacent_objects(stripped, decoder):
                return ToolEnvelopeParseResult.multiple_objects()
            return ToolEnvelopeParseResult.format_error(
                "Return one complete JSON object occupying the entire response.",
            )
        except (ValueError, RecursionError) as exc:
            return ToolEnvelopeParseResult.format_error(str(exc))
        try:
            return CommandParser._parse_proposal(decoded)
        except ValueError as exc:
            return ToolEnvelopeParseResult.format_error(str(exc))

    @staticmethod
    def _has_multiple_adjacent_objects(text: str, decoder: json.JSONDecoder) -> bool:
        cursor = 0
        objects = 0
        try:
            while cursor < len(text):
                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
                if cursor == len(text):
                    break
                decoded, cursor = decoder.raw_decode(text, cursor)
                if not isinstance(decoded, dict):
                    return False
                objects += 1
        except (ValueError, RecursionError):
            return False
        return objects >= 2

    @staticmethod
    def _parse_proposal(value: Any) -> ToolEnvelopeParseResult:
        if not isinstance(value, dict) or set(value) != {
            "decision",
            "mode",
            "action",
            "changes",
            "message",
        }:
            raise ValueError(
                "A proposal must contain exactly decision, mode, action, "
                "changes and message."
            )
        decision = value["decision"]
        if decision not in ("reply", "clarify", "execute"):
            raise ValueError("decision must be reply, clarify or execute.")
        message = value["message"]
        if decision == "execute":
            if message is not None or value["mode"] is None:
                raise ValueError("execute requires a non-null mode and a null message.")
        elif not isinstance(message, str) or not message.strip():
            raise ValueError("reply and clarify require a non-empty message.")
        request = CommandParser._parse_request(
            value["mode"], value["action"], value["changes"], decision
        )
        return ToolEnvelopeParseResult(
            ToolEnvelopeStatus.VALID
            if decision == "execute"
            else ToolEnvelopeStatus.NO_TOOL,
            message=message.strip() if message is not None else "",
            decision=decision,
            request=request,
        )

    @staticmethod
    def _parse_request(
        mode: Any, action: Any, changes: Any, decision: str
    ) -> RequestUpdate | None:
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object.")
        if mode is None:
            if action is not None or changes:
                raise ValueError(
                    "A null mode requires a null action and empty changes."
                )
            return None
        if not isinstance(mode, str) or mode not in REQUEST_MODE_TO_INTERNAL:
            raise ValueError(
                "mode must be null, update_pending, new_request or cancel_pending."
            )
        mode = REQUEST_MODE_TO_INTERNAL[mode]
        if mode == "cancel":
            if decision == "execute" or action is not None or changes:
                raise ValueError(
                    "cancel_pending requires no execution, "
                    "a null action and empty changes."
                )
        elif action is None:
            if decision != "clarify" or changes:
                raise ValueError(
                    "An unresolved action requires clarify and empty changes."
                )
        elif not _name(action):
            raise ValueError("action must be a bounded non-empty action name.")
        parsed = []
        for name, change in changes.items():
            if not _name(name):
                raise ValueError("Parameter names must be bounded non-empty names.")
            if not isinstance(change, dict) or set(change) != {
                "value",
                "source_turn",
                "quote",
            }:
                raise ValueError(
                    "Each change requires exactly value, source_turn and quote."
                )
            if not _bounded_text(change["source_turn"], MAX_SOURCE_TURN_LENGTH):
                raise ValueError("source_turn must be a bounded non-empty string.")
            if not _bounded_text(change["quote"], MAX_QUOTE_LENGTH):
                raise ValueError("quote must be a bounded non-empty string.")
            parsed.append((name, ParameterChange(**change)))
        return RequestUpdate(mode, action, tuple(parsed))
