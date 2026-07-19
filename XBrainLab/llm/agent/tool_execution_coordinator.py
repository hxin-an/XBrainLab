"""Execution boundary for one verified assistant tool command."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.tools import bind_real_tool_execution_context
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

from .tool_feedback import summarize_tool_result

logger = logging.getLogger(__name__)


def _raise_invalid_application_result(message: str) -> NoReturn:
    raise TypeError(message)


@dataclass(frozen=True)
class ToolExecutionOutcome:
    """One typed tool execution result returned to the turn coordinator."""

    success: bool
    result: ToolCommandResult | UiRequest


class ToolExecutionHost(Protocol):
    study: Any
    registry: Any
    metrics: Any
    status_update: Any
    application_command_started: Any
    application_command_completed: Any


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
        host: ToolExecutionHost,
        *,
        block_policy: ToolBlockPolicy,
        application_runtime: ApplicationToolRuntime | None = None,
    ) -> None:
        self.host = host
        self.block_policy = block_policy
        self.application_runtime = application_runtime

    def execute(
        self,
        command_name: str,
        params: dict[str, Any],
        *,
        context: ToolAvailabilityContext,
        application_runtime: ApplicationToolRuntime | None = None,
    ) -> ToolExecutionOutcome:
        runtime = (
            application_runtime
            if application_runtime is not None
            else self.application_runtime
        )
        tool = self.host.registry.get_tool(command_name)
        if tool is None:
            self._record(command_name, False, 0, "unknown tool")
            self.host.status_update.emit(f"Unknown tool: {command_name}")
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
            self.host.status_update.emit(message)
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
            result = self.block_policy.blocked_result(command_name, context)
            logger.warning(redact_public_text(result.message))
            self._record(command_name, False, 0, result.message)
            self.host.status_update.emit(
                summarize_tool_result(command_name, False, result)
            )
            return ToolExecutionOutcome(False, result)

        started_at = time.monotonic()
        is_application_command = command_name in APPLICATION_COMMAND_TOOLS
        if is_application_command:
            self.host.application_command_started.emit()
        terminal_result: ToolCommandResult | None = None
        try:
            raw_result = execute_application_tool_command(
                self.host.study,
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
                if contract is not None and contract.execution_kind not in {
                    AgentExecutionKind.READ_ONLY,
                    AgentExecutionKind.UI_REQUEST,
                }:
                    _raise_invalid_application_result(
                        "Tool execution kind cannot use direct execution"
                    )
                direct_execution_host = self.host.study
                if (
                    contract is not None
                    and contract.execution_kind is AgentExecutionKind.READ_ONLY
                ):
                    direct_execution_host = bind_real_tool_execution_context(
                        self.host.study,
                        runtime,
                    )
                raw_result = tool.execute(direct_execution_host, **params)

            result: ToolCommandResult | UiRequest
            if isinstance(raw_result, UiRequest):
                if is_application_command:
                    _raise_invalid_application_result(
                        "Application command returned an unexpected UI request"
                    )
                result = raw_result
                success = True
            else:
                normalized = normalize_tool_result(
                    self.host.study,
                    command_name,
                    raw_result,
                    availability=availability,
                    state=context.state,
                    runtime=runtime,
                )
                result = normalized
                success = (
                    normalized.ok if isinstance(normalized, ToolCommandResult) else True
                )
                if is_application_command:
                    if not isinstance(normalized, ToolCommandResult):
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
                else result.error_code
                if isinstance(result, ToolCommandResult)
                else "tool_request_failed",
            )
            if not success:
                self.host.status_update.emit(
                    summarize_tool_result(command_name, success, result)
                )
            return ToolExecutionOutcome(success, result)
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
            self.host.status_update.emit(failure.message)
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
                self.host.application_command_completed.emit(terminal_result)

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
        current_turn = self.host.metrics.current_turn
        if current_turn:
            current_turn.record_tool(command_name, success, elapsed_ms, error)
