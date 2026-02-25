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


@dataclass
class DebugToolCall:
    """Immutable representation of a single debug tool invocation.

    Attributes:
        tool: The name of the tool to execute (must match a key in
            ``ToolExecutor.TOOL_MAP``).
        params: Keyword arguments forwarded to the tool's ``execute`` method.

    """

    tool: str
    params: dict[str, Any]


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
            logger.error("Debug script not found: %s", self.script_path)
            return

        try:
            with open(self.script_path, encoding="utf-8") as f:
                data = json.load(f)
                self.calls = data.get("calls", [])
                msg = (
                    f"Loaded debug script with {len(self.calls)} "
                    f"calls from {self.script_path}"
                )
                logger.info(msg)
        except Exception as e:
            logger.error("Failed to load debug script: %s", e)

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

        return DebugToolCall(tool=call_data["tool"], params=call_data.get("params", {}))

    @property
    def is_complete(self) -> bool:
        """Whether all calls in the debug script have been consumed.

        Returns:
            ``True`` if the internal index has reached or exceeded the
            total number of calls; ``False`` otherwise.

        """
        return self.index >= len(self.calls)
