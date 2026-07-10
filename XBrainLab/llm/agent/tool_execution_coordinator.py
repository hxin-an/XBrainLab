"""Execution boundary for one verified assistant tool command."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from XBrainLab.llm.tools.application_surface import (
    READ_ONLY_TOOLS,
    TOOL_TO_COMMAND,
    ToolAvailability,
    ToolCommandResult,
    execute_application_tool_command,
    normalize_tool_result,
)

logger = logging.getLogger(__name__)


class ToolExecutionHost(Protocol):
    study: Any
    registry: Any
    metrics: Any
    status_update: Any
    application_command_started: Any
    application_command_completed: Any

    def _check_tool_availability(
        self,
        command_name: str,
    ) -> ToolAvailability | str | None: ...

    def _tool_block_result(
        self,
        command_name: str,
        availability: ToolAvailability | str,
    ) -> ToolCommandResult: ...

    def _application_state_payload(self) -> dict[str, Any] | None: ...

    def _summarize_tool_result(
        self,
        command_name: str,
        success: bool,
        result: Any,
    ) -> str: ...


class ToolExecutionCoordinator:
    """Execute one already-verified command and normalize its result envelope."""

    def __init__(self, host: ToolExecutionHost) -> None:
        self.host = host

    def execute(self, command_name: str, params: dict[str, Any]) -> tuple[bool, Any]:
        tool = self.host.registry.get_tool(command_name)
        if tool is None:
            self._record(command_name, False, 0, "unknown tool")
            self.host.status_update.emit(f"Unknown tool: {command_name}")
            return False, f"Error: Unknown tool '{command_name}'"

        availability = self.host._check_tool_availability(command_name)
        if availability is not None:
            result = self.host._tool_block_result(command_name, availability)
            logger.warning(result.message)
            self._record(command_name, False, 0, result.message)
            self.host.status_update.emit(
                self.host._summarize_tool_result(command_name, False, result)
            )
            return False, result

        started_at = time.monotonic()
        is_application_command = command_name in TOOL_TO_COMMAND
        if is_application_command:
            self.host.application_command_started.emit()
        try:
            raw_result = execute_application_tool_command(
                self.host.study,
                command_name,
                params,
            )
            if raw_result is None:
                raw_result = tool.execute(self.host.study, **params)
        except Exception as exc:
            elapsed = (time.monotonic() - started_at) * 1000
            error_message = f"Tool execution failed: {exc}"
            result: Any
            if is_application_command:
                result = ToolCommandResult.failure(
                    command_name,
                    error_message,
                    command_name=TOOL_TO_COMMAND[command_name].value,
                    state=self.host._application_state_payload(),
                    raw_result=str(exc),
                )
            else:
                result = error_message
            self._record(command_name, False, elapsed, str(exc))
            self.host.status_update.emit(error_message)
            if is_application_command and isinstance(result, ToolCommandResult):
                self.host.application_command_completed.emit(result)
            return False, result

        elapsed = (time.monotonic() - started_at) * 1000
        result = raw_result
        success = True
        if command_name in TOOL_TO_COMMAND or command_name in READ_ONLY_TOOLS:
            result = normalize_tool_result(
                self.host.study,
                command_name,
                raw_result,
            )
            success = result.ok
            if is_application_command:
                self.host.application_command_completed.emit(result)
        self._record(
            command_name,
            success,
            elapsed,
            None if success else str(result),
        )
        if not success:
            self.host.status_update.emit(
                self.host._summarize_tool_result(command_name, success, result)
            )
        return success, result

    def _record(
        self,
        command_name: str,
        success: bool,
        elapsed_ms: float,
        error: str | None,
    ) -> None:
        current_turn = self.host.metrics.current_turn
        if current_turn:
            current_turn.record_tool(command_name, success, elapsed_ms, error)
