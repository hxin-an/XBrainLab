"""Execution boundary for one verified assistant tool command."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
)
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    TOOL_TO_COMMAND,
    ApplicationToolRuntime,
    ToolAvailabilityContext,
    ToolCommandResult,
    execute_application_tool_command,
    normalize_tool_result,
)
from XBrainLab.llm.tools.result_contract import (
    SafeUnexpectedFailure,
    UiRequest,
    recover_authoritative_failure_state,
    redact_public_text,
    safe_unexpected_failure,
)
from XBrainLab.llm.tools.tool_registry import ToolRegistry

from .metrics import AgentMetricsTracker
from .tool_feedback import summarize_tool_result

logger = logging.getLogger(__name__)
_PUBLIC_TOOL_NAME_MAX_BYTES = 1024


def _public_tool_name(value: object) -> str:
    if type(value) is not str:
        return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER
    rendered = public_diagnostic_text(
        value,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    encoded = rendered.encode("utf-8")
    if len(encoded) <= _PUBLIC_TOOL_NAME_MAX_BYTES:
        return rendered
    marker = PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER.encode("utf-8")
    prefix = encoded[: _PUBLIC_TOOL_NAME_MAX_BYTES - len(marker)].decode(
        "utf-8", errors="ignore"
    )
    return f"{prefix}{PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}"


def _raise_invalid_application_result(message: str) -> NoReturn:
    raise TypeError(message)


@dataclass(frozen=True)
class ToolExecutionOutcome:
    """One typed tool execution result returned to the turn coordinator."""

    success: bool
    result: ToolCommandResult | UiRequest


class _ExpectedPublicationApplicationRuntime:
    """Immutable tool runtime binding execution to one reviewed publication."""

    def __init__(self, service: Any, generation: int) -> None:
        self._service = service
        self._generation = generation

    def get_view_publication(self) -> Any:
        return self._service.get_view_publication()

    def execute(self, command: Any) -> Any:
        return self._service.execute(
            command,
            expected_publication_generation=self._generation,
        )


class ToolBlockPolicy(Protocol):
    """Policy surface required when execution sees a stale capability block."""

    def blocked_result(
        self,
        command_name: str,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult: ...


class ToolExecutionCoordinator:
    """Execute one already-verified command and normalize its result envelope."""

    def __init__(
        self,
        study: Any,
        registry: ToolRegistry,
        metrics: AgentMetricsTracker,
        *,
        block_policy: ToolBlockPolicy,
        emit_status: Callable[[str], None],
        emit_application_command_started: Callable[[], None],
        emit_application_command_completed: Callable[[ToolCommandResult], None],
    ) -> None:
        self.study = study
        self.registry = registry
        self.metrics = metrics
        self.block_policy = block_policy
        self._emit_status = emit_status
        self._emit_application_command_started = emit_application_command_started
        self._emit_application_command_completed = emit_application_command_completed

    def execute(
        self,
        command_name: str,
        params: dict[str, Any],
        *,
        context: ToolAvailabilityContext,
        expected_publication_generation: int | None = None,
    ) -> ToolExecutionOutcome:
        command_name = _public_tool_name(command_name)
        runtime = (
            _ExpectedPublicationApplicationRuntime(
                get_application_service(self.study), expected_publication_generation
            )
            if expected_publication_generation is not None
            else None
        )
        tool = self.registry.get_tool(command_name)
        if tool is None:
            self._record(command_name, False, 0, "unknown tool")
            self._emit_status(f"Unknown tool: {command_name}")
            return ToolExecutionOutcome(
                False,
                ToolCommandResult.failure(
                    command_name,
                    "The requested assistant tool is unavailable.",
                    error_type="input",
                ),
            )

        contract = AGENT_ACTION_CONTRACTS.contract_for(command_name)
        if contract is None:
            message = (
                f"Assistant tool '{command_name}' is not classified by the "
                "canonical action registry."
            )
            self._record(command_name, False, 0, message)
            self._emit_status(message)
            return ToolExecutionOutcome(
                False,
                ToolCommandResult.failure(
                    command_name,
                    message,
                    error_type="contract",
                    recoverable=False,
                    diagnostics={"boundary": "agent_action_contract"},
                ),
            )

        availability = context.availability
        if not availability.enabled:
            blocked_result = self.block_policy.blocked_result(command_name, context)
            logger.warning(redact_public_text(blocked_result.message))
            self._record(command_name, False, 0, blocked_result.message)
            self._emit_status(
                summarize_tool_result(command_name, False, blocked_result)
            )
            return ToolExecutionOutcome(False, blocked_result)

        started_at = time.monotonic()
        is_application_command = command_name in APPLICATION_COMMAND_TOOLS
        if is_application_command:
            self._emit_application_command_started()
        terminal_result: ToolCommandResult | None = None
        try:
            raw_result = execute_application_tool_command(
                self.study,
                command_name,
                params,
                availability=availability,
                state=context.state,
                runtime=runtime,
            )
            if raw_result is None:
                if is_application_command:
                    _raise_invalid_application_result(
                        "Mapped application command returned no result"
                    )
                if contract.execution_kind is not AgentExecutionKind.UI_REQUEST:
                    _raise_invalid_application_result(
                        "Tool execution kind cannot use direct execution"
                    )
                raw_result = tool.execute(self.study, **params)

            execution_result: ToolCommandResult | UiRequest
            if type(raw_result) is UiRequest:
                if is_application_command:
                    _raise_invalid_application_result(
                        "Application command returned an unexpected UI request"
                    )
                execution_result = raw_result
                success = True
            else:
                normalized = normalize_tool_result(
                    self.study,
                    command_name,
                    raw_result,
                    availability=availability,
                    state=context.state,
                    runtime=runtime,
                )
                execution_result = normalized
                success = (
                    normalized.ok if type(normalized) is ToolCommandResult else True
                )
                if is_application_command:
                    if type(normalized) is not ToolCommandResult:
                        _raise_invalid_application_result(
                            "Application command did not produce a tool result"
                        )
                    terminal_result = normalized

            elapsed = (time.monotonic() - started_at) * 1000
            self._record(
                command_name,
                success,
                elapsed,
                None
                if success
                else execution_result.error_code
                if type(execution_result) is ToolCommandResult
                else "tool_request_failed",
            )
            if not success:
                self._emit_status(
                    summarize_tool_result(command_name, success, execution_result)
                )
            return ToolExecutionOutcome(success, execution_result)
        except Exception as exc:
            elapsed = (time.monotonic() - started_at) * 1000
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="tool_execution_coordinator",
                operation=command_name,
            )
            result = self._unexpected_failure_result(
                command_name,
                failure=failure,
                context=context,
                is_application_command=is_application_command,
                runtime=runtime,
            )
            if is_application_command:
                terminal_result = result
            self._record(command_name, False, elapsed, failure.error_code)
            self._emit_status(failure.message)
            return ToolExecutionOutcome(False, result)
        finally:
            if is_application_command:
                if terminal_result is None:
                    missing_result = RuntimeError(
                        "Application command ended without a terminal result"
                    )
                    failure = safe_unexpected_failure(
                        logger,
                        missing_result,
                        boundary="tool_execution_coordinator",
                        operation=command_name,
                    )
                    terminal_result = self._unexpected_failure_result(
                        command_name,
                        failure=failure,
                        context=context,
                        is_application_command=True,
                        runtime=runtime,
                    )
                self._emit_application_command_completed(terminal_result)

    @staticmethod
    def _unexpected_failure_result(
        command_name: str,
        *,
        failure: SafeUnexpectedFailure,
        context: ToolAvailabilityContext,
        is_application_command: bool,
        runtime: ApplicationToolRuntime | None,
    ) -> ToolCommandResult:
        if is_application_command:
            recovery = recover_authoritative_failure_state(
                runtime,
                logger,
                operation=command_name,
                boundary="tool_execution_state_recovery",
            )
            state = recovery.state
            capability = None
            changed_state = recovery.changed_state
            diagnostics = {
                **failure.diagnostics,
                **recovery.diagnostics,
            }
        else:
            state = context.state
            capability = context.availability.to_dict()
            changed_state = {}
            diagnostics = {
                **failure.diagnostics,
                "state_source": "pre_execution",
                "refresh_required": False,
            }

        return ToolCommandResult.failure(
            command_name,
            failure.message,
            command_name=(
                TOOL_TO_COMMAND[command_name].value if is_application_command else None
            ),
            state=state,
            capability=capability,
            error_type=failure.error_type,
            error_code=failure.error_code,
            recovery_action=failure.recovery_action,
            recoverable=failure.recoverable,
            diagnostics=diagnostics,
            changed_state=changed_state,
        )

    def _record(
        self,
        command_name: str,
        success: bool,
        elapsed_ms: float,
        error: str | None,
    ) -> None:
        current_turn = self.metrics.current_turn
        if current_turn:
            current_turn.record_tool(command_name, success, elapsed_ms, error)
