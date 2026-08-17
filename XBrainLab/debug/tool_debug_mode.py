"""Strict, model-free Assistant walkthrough profile state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

WALKTHROUGH_SCHEMA_VERSION = "xbrainlab.assistant_walkthrough.v1"
_ROOT_FIELDS = frozenset({"schema_version", "profile_id", "title", "calls"})
_CALL_FIELDS = frozenset({"id", "tool", "params", "instruction", "expected_outcomes"})


@dataclass(frozen=True, slots=True)
class DebugToolCall:
    """One immutable walkthrough action dispatched through the real tool boundary."""

    step_id: str
    tool: str
    params: dict[str, Any]
    instruction: str
    expected_outcomes: tuple[str, ...]


class ToolDebugMode:
    """Own only walkthrough sequencing; product owners still execute every action."""

    def __init__(self, script_path: str):
        self.script_path = str(script_path)
        self.profile_id = ""
        self.title = ""
        self.calls: tuple[DebugToolCall, ...] = ()
        self.index = 0
        self._pending = False
        self._failure = ""
        self._load_script()

    def _load_script(self) -> None:
        path = Path(self.script_path)
        if not path.is_file():
            raise ValueError("Assistant walkthrough profile was not found.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Assistant walkthrough profile is not valid JSON."
            ) from exc
        if not isinstance(data, dict) or set(data) != _ROOT_FIELDS:
            raise ValueError("Assistant walkthrough profile has invalid root fields.")
        if data.get("schema_version") != WALKTHROUGH_SCHEMA_VERSION:
            raise ValueError("Assistant walkthrough profile version is unsupported.")
        profile_id = data.get("profile_id")
        title = data.get("title")
        raw_calls = data.get("calls")
        if (
            not isinstance(profile_id, str)
            or not profile_id.strip()
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(raw_calls, list)
            or not raw_calls
        ):
            raise ValueError("Assistant walkthrough profile metadata is incomplete.")
        calls = tuple(
            self._parse_call(item, index) for index, item in enumerate(raw_calls)
        )
        step_ids = [call.step_id for call in calls]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Assistant walkthrough step IDs must be unique.")
        self.profile_id = profile_id.strip()
        self.title = title.strip()
        self.calls = calls

    @staticmethod
    def _parse_call(raw: object, index: int) -> DebugToolCall:
        if not isinstance(raw, dict) or set(raw) != _CALL_FIELDS:
            raise ValueError(
                f"Assistant walkthrough step {index + 1} has invalid fields."
            )
        step_id = raw.get("id")
        tool = raw.get("tool")
        params = raw.get("params")
        instruction = raw.get("instruction")
        outcomes = raw.get("expected_outcomes")
        if (
            not isinstance(step_id, str)
            or not step_id.strip()
            or not isinstance(tool, str)
            or tool not in AGENT_ACTION_CONTRACTS.tool_names()
            or not isinstance(params, dict)
            or not isinstance(instruction, str)
            or not instruction.strip()
            or not isinstance(outcomes, list)
            or not outcomes
            or any(
                not isinstance(value, str) or not value.strip() for value in outcomes
            )
        ):
            raise ValueError(f"Assistant walkthrough step {index + 1} is invalid.")
        return DebugToolCall(
            step_id=step_id.strip(),
            tool=tool,
            params=dict(params),
            instruction=instruction.strip(),
            expected_outcomes=tuple(value.strip() for value in outcomes),
        )

    @property
    def current_call(self) -> DebugToolCall | None:
        """Return the current uncommitted step without consuming it."""
        if self.index >= len(self.calls):
            return None
        return self.calls[self.index]

    def begin_call(self) -> DebugToolCall | None:
        """Mark the current step pending; only a terminal may advance it."""
        if self._pending or self._failure:
            return None
        call = self.current_call
        if call is not None:
            self._pending = True
        return call

    def reject_pending(self) -> None:
        """Release a step rejected before controller ownership was established."""
        self._pending = False

    def complete_pending(self, outcome: str) -> bool:
        """Commit exactly one pending step when its correlated terminal is accepted."""
        if not self._pending or self.current_call is None:
            return False
        expected = self.current_call.expected_outcomes
        self._pending = False
        if outcome not in expected:
            self._failure = (
                f"Step {self.current_call.step_id} ended as {outcome}; expected "
                f"{', '.join(expected)}."
            )
            return False
        self.index += 1
        return True

    @property
    def is_waiting(self) -> bool:
        return self._pending

    @property
    def can_dispatch(self) -> bool:
        return not self._pending and not self._failure and self.current_call is not None

    @property
    def failure(self) -> str:
        return self._failure

    @property
    def is_complete(self) -> bool:
        return not self._pending and not self._failure and self.index >= len(self.calls)

    @property
    def progress_text(self) -> str:
        if self._failure:
            return self._failure
        if self.is_complete:
            return f"{self.title} · Complete ({len(self.calls)}/{len(self.calls)})"
        call = self.current_call
        if call is None:
            return self.title
        state = "Waiting for completion" if self._pending else "Press Enter"
        return (
            f"{self.title} · {self.index + 1}/{len(self.calls)} · "
            f"{call.instruction} · {state}"
        )
