"""Debug tool call script loader and step-by-step executor.

This module provides classes to load a JSON-based debug script containing
pre-defined tool calls and replay them one at a time, enabling
interactive step-through debugging via the chat UI.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.tools.result_contract import safe_unexpected_failure


@dataclass(frozen=True)
class DebugToolCall:
    """Immutable representation of a single debug tool invocation.

    Attributes:
        tool: The name of the tool to execute (must match a key in
            ``ToolExecutor.TOOL_MAP``).
        params: Keyword arguments forwarded to the tool's ``execute`` method.

    """

    tool: str
    params: dict[str, Any]
    confirmed: bool = False
    authorization_text: str = ""


class ToolDebugMode:
    """Manages the execution of a pre-defined tool call script for debugging.

    Loads a JSON debug script and yields one ``DebugToolCall`` at a time,
    allowing step-by-step execution triggered by pressing Enter in the
    chat UI.

    Attributes:
        script_path: Absolute or relative path to the JSON debug script.
        calls: Ordered list of raw call dictionaries loaded from the script.
        index: Zero-based position of the next call to return.

    """

    def __init__(self, script_path: str):
        """Initialise the debug mode and load the script.

        Args:
            script_path: Path to a JSON file containing a ``calls`` array.
                Each element must have a ``"tool"`` key and an optional
                ``"params"`` dictionary.

        """
        self.script_path = script_path
        self.calls: list[dict] = []
        self.index = 0
        self._load_script()

    def _load_script(self) -> None:
        """Load and parse the JSON debug script into ``self.calls``.

        If the file does not exist or cannot be parsed, an error is logged
        and ``self.calls`` remains empty.
        """
        if not os.path.exists(self.script_path):
            logger.error("Debug script was not found.")
            return

        try:
            with open(self.script_path, encoding="utf-8") as f:
                data = json.load(f)
                self.calls = data.get("calls", [])
                logger.info("Loaded debug script with %d calls.", len(self.calls))
        except Exception as error:
            safe_unexpected_failure(
                logger,
                error,
                boundary="tool_debug_script_loader",
                operation="load_script",
            )

    def next_call(self) -> DebugToolCall | None:
        """Return the next tool call in the sequence.

        Advances the internal index by one each time it is called.

        Returns:
            A ``DebugToolCall`` containing the tool name and parameters,
            or ``None`` if all calls have been consumed.

        """
        if self.index >= len(self.calls):
            return None

        call_data = self.calls[self.index]
        self.index += 1

        if not isinstance(call_data, dict) or not isinstance(
            call_data.get("tool"),
            str,
        ):
            logger.error(
                "Invalid debug call entry at index %d.",
                self.index - 1,
            )
            return None
        params = call_data.get("params", {})
        confirmed = call_data.get("confirmed", False)
        authorization_text = call_data.get("authorization_text", "")
        if (
            not isinstance(params, dict)
            or type(confirmed) is not bool
            or not isinstance(authorization_text, str)
        ):
            logger.error(
                "Invalid debug call contract at index %d.",
                self.index - 1,
            )
            return None
        return DebugToolCall(
            tool=call_data["tool"],
            params=dict(params),
            confirmed=confirmed,
            authorization_text=authorization_text,
        )

    @property
    def is_complete(self) -> bool:
        """Whether all calls in the debug script have been consumed.

        Returns:
            ``True`` if the internal index has reached or exceeded the
            total number of calls; ``False`` otherwise.

        """
        return self.index >= len(self.calls)
