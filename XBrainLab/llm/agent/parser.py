"""Command parser for extracting tool-call JSON from LLM output.

Parses raw LLM response text to identify and extract structured JSON
tool commands embedded within free-form text or code blocks.
"""

import json
import re
from typing import Any

from XBrainLab.backend.utils.logger import logger

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
        "generate_dataset",
        "configure_training",
        "start_training",
        "train",
        "clear_dataset",
        "query_state",
        "get_dataset_info",
    }
)


class CommandParser:
    """Parses LLM output to extract structured tool commands.

    Scans response text for JSON objects containing ``tool_name`` (or
    ``command``) and ``parameters`` / ``arguments`` keys, handling both
    raw JSON and fenced code blocks.
    """

    @staticmethod
    def parse(
        text: str,
    ) -> list[tuple[str, dict[str, Any]]] | None:
        """Extracts JSON command blocks from LLM output text.

        Scans ``text`` for JSON objects containing a ``tool_name`` (or
        ``command``) key and a ``parameters`` key.  Multiple commands may
        be present in a single response.

        Args:
            text: Raw LLM response text, potentially containing fenced
                code blocks or inline JSON.

        Returns:
            A list of ``(tool_name, parameters)`` tuples if commands are
            found, or ``None`` if no valid commands are detected.

        """
        # Clean up the text: remove code blocks if present
        # We want to scan the "inner" text of the code block if it exists
        # but multiple code blocks might exist.
        # Simplified approach: Just scan the whole text for JSON objects.

        cleaned_text = text
        # If there are code block markers, try to extract content inside them?
        # Actually raw_decode works fine on mixed text if we start at '{'

        decoder = json.JSONDecoder()
        cursor = 0
        found_commands = []

        try:
            while True:
                # Find next '{'
                start_idx = cleaned_text.find("{", cursor)
                if start_idx == -1:
                    break

                try:
                    data, end_idx = decoder.raw_decode(cleaned_text[start_idx:])
                    # data is the JSON object, end_idx is length relative to start_idx

                    found_commands.extend(
                        CommandParser._extract_commands_from_decoded(data),
                    )

                    # Move cursor past this object
                    cursor = start_idx + end_idx

                except json.JSONDecodeError:
                    # Failed to decode from this '{', maybe it was just text
                    cursor = start_idx + 1

        except Exception as e:
            logger.error("Error parsing command: %s", e)
            return None

        if found_commands:
            # To maintain backward compatibility with single-return callers,
            # we might need to handle this carefully.
            # But simple_bench expects a tuple.
            # I should change simple_bench first or return a list and fix simple_bench.
            return found_commands  # Return List[Tuple]
        bare_command = CommandParser._extract_bare_command(cleaned_text)
        if bare_command is not None:
            return [bare_command]
        return None

    @staticmethod
    def _extract_commands_from_object(
        data: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        """Extract one or more tool calls from a decoded JSON object."""
        function_call = data.get("function")
        if isinstance(function_call, dict):
            return CommandParser._extract_single_command(function_call)

        tool_call = data.get("tool_call")
        if isinstance(tool_call, dict):
            return CommandParser._extract_commands_from_object(tool_call)

        tool_calls = data.get("tool_calls")
        if isinstance(tool_calls, list):
            commands: list[tuple[str, dict[str, Any]]] = []
            for item in tool_calls:
                if isinstance(item, dict):
                    commands.extend(CommandParser._extract_commands_from_object(item))
            return commands

        return CommandParser._extract_single_command(data)

    @staticmethod
    def _extract_commands_from_decoded(
        data: Any,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Extract commands from a decoded JSON value."""
        if isinstance(data, dict):
            return CommandParser._extract_commands_from_object(data)
        if isinstance(data, list):
            commands: list[tuple[str, dict[str, Any]]] = []
            for item in data:
                if isinstance(item, dict):
                    commands.extend(CommandParser._extract_commands_from_object(item))
            return commands
        return []

    @staticmethod
    def _extract_single_command(
        data: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        """Extract one tool call from a decoded JSON object."""
        cmd = data.get("tool_name") or data.get("command") or data.get("name")
        params = data.get("parameters")
        if params is None:
            params = data.get("arguments")
        if params is None and any(
            key in data for key in ("reason", "reasons", "blocked_reason")
        ):
            params = {}
        if isinstance(params, str):
            try:
                decoded_params = json.loads(params)
            except json.JSONDecodeError:
                decoded_params = None
            if isinstance(decoded_params, dict):
                params = decoded_params
        if isinstance(cmd, str) and isinstance(params, dict):
            return [(cmd, params)]
        return []

    @staticmethod
    def _extract_bare_command(text: str) -> tuple[str, dict[str, Any]] | None:
        """Extract a bare tool name when the model emits command syntax text."""
        stripped = text.strip()
        if not stripped:
            return None
        command = re.split(r"[\s:]+", stripped, maxsplit=1)[0]
        if command in _BARE_COMMANDS:
            return command, {}
        return None
