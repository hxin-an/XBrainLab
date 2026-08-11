"""Typed risk contracts for assistant confirmation requests."""

from __future__ import annotations

from typing import Any

from XBrainLab.llm.agent.confirmation import AgentConfirmationRisk
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptDecision,
)
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.result_contract import ToolExecutionResult


class _Tool(BaseTool):
    @property
    def name(self) -> str:
        return "confirmation_probe"

    @property
    def description(self) -> str:
        return "Run the requested action."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, study: Any, **kwargs: Any) -> ToolExecutionResult:
        del study, kwargs
        raise AssertionError("Confirmation request tests do not execute tools.")


def _request_for(
    tool_name: str,
    availability: ToolAvailability,
    *,
    confirmation_kind: str | None = None,
):
    context = ToolAvailabilityContext(
        availability=availability,
        state={"state_reliable": True},
        generation=17,
    )
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=tool_name,
        params={},
        context=context,
        tool=_Tool(),
        confirmation_kind=confirmation_kind,
    )
    return LLMController._build_confirmation_request(None, decision)  # type: ignore[arg-type]


def test_start_training_confirmation_preserves_policy_risk_and_impact() -> None:
    request = _request_for(
        "start_training",
        ToolAvailability(
            tool_name="start_training",
            enabled=True,
            command_name="train",
            confirmation_required=True,
            long_running=True,
            can_auto_execute=False,
            requires_confirmation=True,
            decision_boundary="long_running",
            continue_allowed_after_success=False,
            retry_limit=0,
            stop_after_success=True,
        ),
    )

    assert request.risk == AgentConfirmationRisk(
        destructive=False,
        high_impact=False,
        long_running=True,
        decision_boundary="long_running",
        impact_text=(
            "Starts a potentially long GPU or CPU job using the configured "
            "resources. You can stop it after it starts."
        ),
    )
    assert request.long_running is True
    assert request.destructive is False


def test_setting_confirmation_has_typed_high_impact_decision_boundary() -> None:
    request = _request_for(
        "configure_training",
        ToolAvailability(
            tool_name="configure_training",
            enabled=True,
            command_name="configure_training",
        ),
        confirmation_kind="setting_change",
    )

    assert request.risk.high_impact is True
    assert request.risk.decision_boundary == "high_impact_setting_change"
    assert request.risk.impact_text is not None


def test_backend_high_impact_boundary_survives_without_confirmation_kind() -> None:
    request = _request_for(
        "set_model",
        ToolAvailability(
            tool_name="set_model",
            enabled=True,
            command_name="configure_training",
            confirmation_required=True,
            can_auto_execute=False,
            requires_confirmation=True,
            decision_boundary="high_impact_setting_change",
        ),
    )

    assert request.risk.high_impact is True
    assert request.risk.decision_boundary == "high_impact_setting_change"


def test_destructive_risk_is_not_collapsed_into_generic_confirmation() -> None:
    request = _request_for(
        "clear_dataset",
        ToolAvailability(
            tool_name="clear_dataset",
            enabled=True,
            command_name="reset_session",
            confirmation_required=True,
            destructive=True,
            can_auto_execute=False,
            requires_confirmation=True,
            decision_boundary="destructive",
        ),
    )

    assert request.risk.destructive is True
    assert request.risk.decision_boundary == "destructive"
