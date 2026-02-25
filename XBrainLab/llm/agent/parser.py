"""Command parser for extracting tool-call JSON from LLM output.

Parses raw LLM response text to identify and extract structured JSON
tool commands embedded within free-form text or code blocks.
"""

import json
from typing import Any

from XBrainLab.backend.utils.logger import logger


class CommandParser:
    """Parses LLM output to extract structured tool commands.

    Scans response text for JSON objects containing ``tool_name`` (or
    ``command``) and ``parameters`` keys, handling both raw JSON and
    fenced code blocks.
    """

    @staticmethod
    def parse(
        text: str,
    ) -> list[tuple[str, dict[str, Any]]] | tuple[str, dict[str, Any]] | None:
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

                    if isinstance(data, dict):
                        # Check if it's a valid tool command
                        cmd = data.get("tool_name") or data.get("command")
                        params = data.get("parameters")

                        if cmd and params is not None:
                            found_commands.append((cmd, params))

                    elif isinstance(data, list):
                        # Handle JSON list of objects
                        # (if finding '[' logic was used, but here we find '{')
                        # If we parse a list, append its contents
                        for item in data:
                            if isinstance(item, dict):
                                cmd = item.get("tool_name") or item.get("command")
                                params = item.get("parameters")
                                if cmd and params is not None:
                                    found_commands.append((cmd, params))

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
        return None
