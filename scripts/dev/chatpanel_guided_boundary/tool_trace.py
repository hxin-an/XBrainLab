"""Read-only runtime tracing for guided-boundary tool-call evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from functools import wraps
from typing import Any


class GuidedToolTraceRecorder:
    """Observe normalized proposals and host execution without changing outcomes."""

    def __init__(self, structured_value: Callable[[Any], Any]) -> None:
        self._structured_value = structured_value
        self._attempts: list[dict[str, Any]] = []
        self._controller: Any | None = None
        self._originals: dict[str, Any] = {}

    def attach(self, controller: Any) -> None:
        """Attach once to the concrete controller instance used by the walkthrough."""
        if self._controller is controller:
            return
        self.detach()
        self._controller = controller
        self._wrap_selection(controller)
        self._wrap_execution(controller)

    def detach(self) -> None:
        """Restore the observed instance methods when the harness is done."""
        controller = self._controller
        if controller is not None:
            for name, original in self._originals.items():
                with suppress(AttributeError, RuntimeError):
                    setattr(controller, name, original)
        self._controller = None
        self._originals.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a JSON-safe copy of every observed host attempt."""
        value = self._structured_value(self._attempts)
        return list(value) if isinstance(value, Sequence) else []

    def _wrap_selection(self, controller: Any) -> None:
        name = "_select_tool_proposal"
        original = getattr(controller, name)
        self._originals[name] = original

        @wraps(original)
        def observe_selection(command_result: Any) -> Any:
            selected = original(command_result)
            if selected is not None:
                tool_name, parameters = selected
                self._attempts.append(
                    {
                        "normalized": self._call(tool_name, parameters),
                        "actual": None,
                    }
                )
            return selected

        setattr(controller, name, observe_selection)

    def _wrap_execution(self, controller: Any) -> None:
        name = "_execute_tool_no_loop"
        original = getattr(controller, name)
        self._originals[name] = original

        @wraps(original)
        def observe_execution(
            command_name: str,
            parameters: Mapping[str, Any],
            *,
            context: Any = None,
            expected_publication_generation: int | None = None,
        ) -> Any:
            self._record_actual(command_name, parameters)
            kwargs = {"context": context}
            if expected_publication_generation is not None:
                kwargs["expected_publication_generation"] = (
                    expected_publication_generation
                )
            return original(command_name, parameters, **kwargs)

        setattr(controller, name, observe_execution)

    def _record_actual(
        self,
        tool_name: str,
        parameters: Mapping[str, Any],
    ) -> None:
        for attempt in reversed(self._attempts):
            if attempt.get("actual") is not None:
                continue
            normalized = attempt.get("normalized")
            if (
                isinstance(normalized, Mapping)
                and normalized.get("tool_name") == tool_name
            ):
                attempt["actual"] = {
                    "kind": "model_execution",
                    **self._call(tool_name, parameters),
                }
                return
        self._attempts.append(
            {
                "normalized": None,
                "actual": {
                    "kind": "host_execution",
                    **self._call(tool_name, parameters),
                },
            }
        )

    def _call(
        self,
        tool_name: str,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        structured = self._structured_value(dict(parameters))
        return {
            "tool_name": str(tool_name),
            "parameters": structured if isinstance(structured, dict) else {},
        }


def assemble_tool_attempts(
    raw_proposals: object,
    traces: object,
    canonical_calls: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Pair raw model output with observed normalized and host-boundary calls."""
    raw = _mapping_sequence(raw_proposals)
    observed = _mapping_sequence(traces)
    count = max(len(raw), len(observed), len(canonical_calls))
    attempts: list[dict[str, Any]] = []
    for index in range(count):
        trace = observed[index] if index < len(observed) else {}
        attempts.append(
            {
                "raw": raw[index] if index < len(raw) else None,
                "canonical": (
                    dict(canonical_calls[index])
                    if index < len(canonical_calls)
                    else None
                ),
                "normalized": trace.get("normalized"),
                "actual": trace.get("actual"),
            }
        )
    return attempts


def _mapping_sequence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) if isinstance(item, Mapping) else {} for item in value]
