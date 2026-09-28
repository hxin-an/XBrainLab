"""Strict product boundary for a single model-proposed command."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from .decision_contract import MAX_NAME_LENGTH, MODEL_RESPONSE_TOOL_NAME

ToolCommand: TypeAlias = tuple[str, dict[str, Any]]


class ToolEnvelopeStatus(str, Enum):
    """Classification before request admission or product execution."""

    NO_TOOL = "no_tool"
    VALID = "valid"
    MULTIPLE_OBJECTS = "multiple_objects"
    FORMAT_ERROR = "format_error"


@dataclass(frozen=True)
class ToolEnvelopeParseResult:
    """A parsed command or non-executable reply; validity is not admission."""

    status: ToolEnvelopeStatus
    error: str = ""
    message: str = ""
    command: ToolCommand | None = None

    @property
    def decision(self) -> str:
        """Semantic label for diagnostics, not a second model wire contract."""
        if self.status is ToolEnvelopeStatus.VALID:
            return "execute"
        if self.status is ToolEnvelopeStatus.NO_TOOL:
            return "reply"
        return ""

    def proposal_dict(self) -> dict[str, Any] | None:
        """Serialize only a successfully parsed two-field response."""
        if self.status is ToolEnvelopeStatus.NO_TOOL:
            return {
                "tool_name": MODEL_RESPONSE_TOOL_NAME,
                "parameters": {"message": self.message},
            }
        if self.status is ToolEnvelopeStatus.VALID and self.command is not None:
            tool_name, parameters = self.command
            return {"tool_name": tool_name, "parameters": parameters}
        return None

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
        if not isinstance(value, dict) or set(value) != {"tool_name", "parameters"}:
            raise ValueError(
                "A response must contain exactly tool_name and parameters."
            )
        tool_name = value["tool_name"]
        parameters = value["parameters"]
        if not _name(tool_name):
            raise ValueError("tool_name must be a bounded non-empty name.")
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object.")
        if tool_name == MODEL_RESPONSE_TOOL_NAME:
            if set(parameters) != {"message"}:
                raise ValueError(
                    "respond_to_user requires exactly a message parameter."
                )
            message = parameters["message"]
            if not isinstance(message, str) or not message.strip():
                raise ValueError("respond_to_user requires a non-empty message.")
            return ToolEnvelopeParseResult(ToolEnvelopeStatus.NO_TOOL, message=message)
        return ToolEnvelopeParseResult(
            ToolEnvelopeStatus.VALID, command=(tool_name, parameters)
        )
