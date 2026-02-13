import json
import os
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.utils.logger import logger


@dataclass
class DebugToolCall:
    tool: str
    params: dict[str, Any]


class ToolDebugMode:
    """
    Manages the execution of a pre-defined tool call script for debugging.
    Allows step-by-step execution by pressing Enter in the chat UI.
    """

    def __init__(self, script_path: str):
        self.script_path = script_path
        self.calls: list[dict] = []
        self.index = 0
        self._load_script()

    def _load_script(self):
        if not os.path.exists(self.script_path):
            logger.error(f"Debug script not found: {self.script_path}")
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
            logger.error(f"Failed to load debug script: {e}")

    def next_call(self) -> DebugToolCall | None:
        """Returns the next tool call in the sequence, or None if finished."""
        if self.index >= len(self.calls):
            return None

        call_data = self.calls[self.index]
        self.index += 1

        return DebugToolCall(tool=call_data["tool"], params=call_data.get("params", {}))

    @property
    def is_complete(self) -> bool:
        return self.index >= len(self.calls)
