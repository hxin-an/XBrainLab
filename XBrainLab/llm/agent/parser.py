"""Strict product boundary for model-proposed tool calls."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from XBrainLab.backend.application.pipeline_stage import PipelineStage
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.tools.result_contract import (
    safe_unexpected_failure,
)

from .decision_contract import MODEL_RESPONSE_TOOL_NAME, ModelDecision

ToolCommand: TypeAlias = tuple[str, dict[str, Any]]

_BARE_COMMANDS = frozenset(
    {
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "save_interpretation_recipe",
        "reload_interpretation_recipe",
        "load_data",
        "attach_labels",
        "apply_standard_preprocess",
        "apply_bandpass_filter",
        "epoch_data",
        "create_epoch",
        "configure_dataset_split",
        "configure_training",
        "start_training",
        "train",
        "evaluate",
        "visualize",
        "saliency",
        "query_state",
        "get_dataset_info",
    }
)
_NO_TOOL_SENTINELS = frozenset(
    {"ask_clarification", "clarify", "none", "no_tool", "null"}
)
_TOOL_MARKER = re.compile(
    r'["\']?(?:decision|tool_name|tool_call|tool_calls|command)'
    r'["\']?\s*:',
)
_STRICT_TOOL_FIELDS = frozenset({"workflow_stage", "tool_name", "parameters"})
_WORKFLOW_STAGES = frozenset(stage.value for stage in PipelineStage) | {"unavailable"}


class ToolEnvelopeStatus(str, Enum):
    """Classification of one complete model response at the product boundary."""

    NO_TOOL = "no_tool"
    VALID = "valid"
    FORMAT_ERROR = "format_error"


@dataclass(frozen=True)
class ToolEnvelopeParseResult:
    """Typed parse result used before any product tool execution can begin."""

    status: ToolEnvelopeStatus
    commands: tuple[ToolCommand, ...] = ()
    error: str = ""
    workflow_stage: str | None = None
    decision: ModelDecision | None = None
    intent: str = ""
    pending_action: str = ""
    missing_inputs: tuple[str, ...] = ()
    message: str = ""

    @classmethod
    def no_tool(
        cls,
        *,
        workflow_stage: str | None = None,
        intent: str = "",
        missing_inputs: tuple[str, ...] = (),
        pending_action: str = "",
        message: str = "",
    ) -> ToolEnvelopeParseResult:
        return cls(
            ToolEnvelopeStatus.NO_TOOL,
            workflow_stage=workflow_stage,
            intent=intent,
            pending_action=pending_action,
            missing_inputs=missing_inputs,
            message=message,
        )

    @classmethod
    def valid(
        cls,
        command: ToolCommand,
        *,
        workflow_stage: str,
        intent: str = "",
    ) -> ToolEnvelopeParseResult:
        return cls(
            ToolEnvelopeStatus.VALID,
            (command,),
            workflow_stage=workflow_stage,
            decision="tool",
            intent=intent,
        )

    @classmethod
    def format_error(cls, message: str) -> ToolEnvelopeParseResult:
        return cls(ToolEnvelopeStatus.FORMAT_ERROR, error=message)


class _DuplicateKeyError(ValueError):
    pass


class _NonStandardJsonValueError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_standard_json(value: str) -> None:
    raise _NonStandardJsonValueError(f"non-standard JSON value: {value}")


class CommandParser:
    """Parse strict product envelopes and explicitly tolerant diagnostics."""

    @staticmethod
    def parse_product(text: str) -> ToolEnvelopeParseResult:
        """Classify a complete model response without recovering malformed calls.

        A product action is exactly one top-level JSON object with
        ``workflow_stage``, ``tool_name`` and ``parameters``. Wrappers, prose,
        code fences, aliases, arrays, duplicate keys, partial JSON and multiple
        calls are contract failures and never reach execution.
        """

        stripped = text.strip()
        if not stripped:
            return ToolEnvelopeParseResult.no_tool()

        try:
            decoded = json.loads(
                stripped,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_non_standard_json,
            )
        except _DuplicateKeyError:
            return ToolEnvelopeParseResult.format_error(
                "A tool proposal must not contain duplicate JSON keys.",
            )
        except _NonStandardJsonValueError:
            return ToolEnvelopeParseResult.format_error(
                "A tool proposal must not contain non-standard JSON values.",
            )
        except json.JSONDecodeError as exc:
            if not CommandParser._looks_like_tool_attempt(stripped):
                return ToolEnvelopeParseResult.format_error(
                    "A structured assistant response must be one JSON object.",
                )
            if stripped.startswith("```") or not stripped.startswith(("{", "[")):
                message = (
                    "A tool proposal must occupy the entire response as one JSON "
                    "object with no prose or code fence."
                )
            elif stripped.startswith("["):
                message = "A tool proposal must be one top-level object, not an array."
            else:
                message = f"A tool proposal must be complete JSON: {exc.msg}."
            return ToolEnvelopeParseResult.format_error(message)

        if not isinstance(decoded, dict):
            return ToolEnvelopeParseResult.format_error(
                "A tool proposal must be one top-level object.",
            )

        keys = frozenset(decoded)
        if keys != _STRICT_TOOL_FIELDS:
            return ToolEnvelopeParseResult.format_error(
                "An assistant action must be exactly workflow_stage, tool_name, "
                "and parameters.",
            )

        workflow_stage = decoded["workflow_stage"]
        tool_name = decoded["tool_name"]
        parameters = decoded["parameters"]
        if (
            not isinstance(workflow_stage, str)
            or workflow_stage not in _WORKFLOW_STAGES
        ):
            return ToolEnvelopeParseResult.format_error(
                "workflow_stage must be an exact backend stage value.",
            )
        if not isinstance(tool_name, str) or not tool_name.strip():
            return ToolEnvelopeParseResult.format_error(
                "tool_name must be a non-empty string.",
            )
        if tool_name.strip().lower() in _NO_TOOL_SENTINELS:
            return ToolEnvelopeParseResult.format_error(
                "Use normal text instead of a no-tool sentinel envelope.",
            )
        if not isinstance(parameters, dict):
            return ToolEnvelopeParseResult.format_error(
                "parameters must be a JSON object.",
            )
        if tool_name.strip() == MODEL_RESPONSE_TOOL_NAME:
            return CommandParser._parse_model_response(
                parameters,
                workflow_stage=workflow_stage,
            )

        return ToolEnvelopeParseResult.valid(
            (tool_name, parameters),
            workflow_stage=workflow_stage,
        )

    @staticmethod
    def _parse_model_response(
        parameters: dict[str, Any],
        *,
        workflow_stage: str,
    ) -> ToolEnvelopeParseResult:
        """Validate the reserved no-execution response envelope."""
        parameter_keys = frozenset(parameters)
        if parameter_keys == {"message"}:
            pending_action = ""
            missing_inputs: tuple[str, ...] = ()
        elif parameter_keys == {"message", "pending_action", "missing_inputs"}:
            pending_action_value = parameters["pending_action"]
            missing_value = parameters["missing_inputs"]
            if (
                not isinstance(pending_action_value, str)
                or not pending_action_value.strip()
            ):
                return ToolEnvelopeParseResult.format_error(
                    "pending_action must be a non-empty string.",
                )
            if (
                not isinstance(missing_value, list)
                or not 1 <= len(missing_value) <= 2
                or any(
                    not isinstance(name, str) or not name.strip()
                    for name in missing_value
                )
                or len({name.strip() for name in missing_value}) != len(missing_value)
            ):
                return ToolEnvelopeParseResult.format_error(
                    "missing_inputs must be one or two unique non-empty field names.",
                )
            pending_action = pending_action_value.strip()
            missing_inputs = tuple(name.strip() for name in missing_value)
        else:
            return ToolEnvelopeParseResult.format_error(
                "respond_to_user parameters must be message only or a typed "
                "clarification.",
            )

        message = parameters["message"]
        if not isinstance(message, str):
            return ToolEnvelopeParseResult.format_error(
                "message must be a string.",
            )
        if not message.strip():
            return ToolEnvelopeParseResult.format_error(
                "A non-tool decision requires a user-facing message.",
            )

        return ToolEnvelopeParseResult.no_tool(
            workflow_stage=workflow_stage,
            intent="no_tool",
            pending_action=pending_action,
            missing_inputs=missing_inputs,
            message=message.strip(),
        )

    @staticmethod
    def parse(text: str) -> list[ToolCommand] | None:
        """Return a product command only when the strict envelope is valid."""

        result = CommandParser.parse_product(text)
        if result.status is not ToolEnvelopeStatus.VALID:
            return None
        return list(result.commands)

    @staticmethod
    def parse_diagnostic(text: str) -> list[ToolCommand] | None:
        """Recover legacy model output for offline migration/diagnostics only.

        Product execution and strict evaluation must never call this method.
        """

        decoder = json.JSONDecoder()
        cursor = 0
        found_commands: list[ToolCommand] = []
        try:
            while True:
                start_idx = text.find("{", cursor)
                if start_idx == -1:
                    break
                try:
                    data, end_idx = decoder.raw_decode(text[start_idx:])
                except json.JSONDecodeError:
                    cursor = start_idx + 1
                    continue
                found_commands.extend(CommandParser._extract_diagnostic_commands(data))
                cursor = start_idx + end_idx
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="diagnostic_command_parser",
                operation="parse_compatibility_output",
            )
            return None

        if found_commands:
            return found_commands
        partial_command = CommandParser._extract_partial_json_command(text)
        if partial_command is not None:
            return [partial_command]
        bare_command = CommandParser._extract_bare_command(text)
        if bare_command is not None:
            return [bare_command]
        return None

    @staticmethod
    def _looks_like_tool_attempt(text: str) -> bool:
        if text.startswith(("{", "[", "```")) or _TOOL_MARKER.search(text):
            return True
        command = re.split(r"[\s:]+", text, maxsplit=1)[0]
        return command in _BARE_COMMANDS

    @staticmethod
    def _extract_diagnostic_commands(data: Any) -> list[ToolCommand]:
        if isinstance(data, list):
            commands: list[ToolCommand] = []
            for item in data:
                commands.extend(CommandParser._extract_diagnostic_commands(item))
            return commands
        if not isinstance(data, dict):
            return []

        function_call = data.get("function")
        if isinstance(function_call, dict):
            return CommandParser._extract_diagnostic_single(function_call)
        tool_call = data.get("tool_call")
        if isinstance(tool_call, dict):
            return CommandParser._extract_diagnostic_commands(tool_call)
        tool_calls = data.get("tool_calls")
        if isinstance(tool_calls, list):
            return CommandParser._extract_diagnostic_commands(tool_calls)
        return CommandParser._extract_diagnostic_single(data)

    @staticmethod
    def _extract_diagnostic_single(data: dict[str, Any]) -> list[ToolCommand]:
        command = (
            data.get("tool_name")
            or data.get("command")
            or data.get("name")
            or data.get("tool")
        )
        parameters = data.get("parameters")
        if parameters is None:
            parameters = data.get("arguments")
        if parameters is None and any(
            key in data
            for key in (
                "reason",
                "reasons",
                "blocked_reason",
                "requires_confirmation",
                "decision_boundary",
            )
        ):
            parameters = {}
        if isinstance(parameters, str):
            try:
                decoded_parameters = json.loads(parameters)
            except json.JSONDecodeError:
                decoded_parameters = None
            if isinstance(decoded_parameters, dict):
                parameters = decoded_parameters
        if isinstance(command, str) and command.strip().lower() in _NO_TOOL_SENTINELS:
            return []
        if isinstance(command, str) and isinstance(parameters, dict):
            return [(command, parameters)]
        return []

    @staticmethod
    def _extract_bare_command(text: str) -> ToolCommand | None:
        stripped = text.strip()
        if not stripped:
            return None
        command = re.split(r"[\s:]+", stripped, maxsplit=1)[0]
        rest = stripped[len(command) :]
        if command in _BARE_COMMANDS and (
            not rest or rest.startswith(("\n", "\r", ":", "(", "{"))
        ):
            return command, {}
        return None

    @staticmethod
    def _extract_partial_json_command(text: str) -> ToolCommand | None:
        match = re.search(
            r'"(?:tool_name|name)"\s*:\s*"([A-Za-z0-9_]+)"',
            text,
        )
        if not match:
            return None
        command = match.group(1)
        if command in _BARE_COMMANDS:
            return command, {}
        return None
