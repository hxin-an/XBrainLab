"""Focused decision-order tests for ``ToolAttemptCoordinator``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.verifier import VerificationResult
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
)


@dataclass(frozen=True)
class _Tool:
    requires_confirmation: bool = False
    description: str = "Demo tool"


class _Registry:
    def __init__(self, tool: _Tool | None = None) -> None:
        self.tool = tool or _Tool()
        self.reads = 0

    def get_tool(self, name: str) -> Any:
        del name
        self.reads += 1
        return self.tool


class _Verifier:
    def __init__(
        self,
        valid: bool = True,
        error_message: str = "schema mismatch",
    ) -> None:
        self.valid = valid
        self.error_message = error_message
        self.calls = 0

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict[str, Any]],
        *,
        confidence: float,
    ) -> VerificationResult:
        del tool_call
        assert confidence == 0.8
        self.calls += 1
        return VerificationResult(
            self.valid,
            None if self.valid else self.error_message,
        )


class _Source:
    def __init__(self, context: ToolAvailabilityContext | None) -> None:
        self.context = context
        self.reads = 0

    def get_context(self, tool_name: str) -> ToolAvailabilityContext | None:
        del tool_name
        self.reads += 1
        return self.context


def _context(
    *,
    tool_name: str = "query_state",
    enabled: bool = True,
    confirmation: bool = False,
) -> ToolAvailabilityContext:
    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=enabled,
            reasons=() if enabled else ("State is unavailable.",),
            command_name=tool_name,
            requires_confirmation=confirmation,
        ),
        state={"state_reliable": True},
        generation=17,
    )


def _request(
    *,
    tool_name: str = "query_state",
    params: dict[str, Any] | None = None,
    text: str = "Show current workflow state",
) -> ToolAttemptRequest:
    return ToolAttemptRequest(
        command_name=tool_name,
        params=params or {},
        confidence=0.8,
        publication=PromptToolPublication(
            tool_names=frozenset({tool_name}),
            backend_generation=17,
        ),
        latest_user_text=text,
    )


def _coordinator(
    context: ToolAvailabilityContext | None,
    *,
    verifier: _Verifier | None = None,
    registry: _Registry | None = None,
) -> tuple[ToolAttemptCoordinator, _Source, _Verifier, _Registry]:
    source = _Source(context)
    actual_verifier = verifier or _Verifier()
    actual_registry = registry or _Registry()
    coordinator = ToolAttemptCoordinator(
        registry=actual_registry,
        verifier=actual_verifier,
        context_source=source,
    )
    return coordinator, source, actual_verifier, actual_registry


def _training_preflight() -> dict[str, Any]:
    return {
        "payload_type": "training_resource_preflight",
        "risk_level": "warning",
        "requires_confirmation": True,
        "message": "Training may use most available memory.",
        "model_name": "EEGNet",
        "training_batch_size": 32,
        "estimated_gpu_batch_working_set_bytes": 4_096,
        "available_vram_bytes": 8_192,
        "confirmation_token": "training-receipt-1",
        "confirmation_command": "start_training",
        "configuration_fingerprint": "configuration-1",
        "preflight_fingerprint": "preflight-1",
        "scope_fingerprint": "scope-1",
        "confirmation_ttl_seconds": 120.0,
    }


def _interpretation_preflight(
    *,
    command_name: str,
    candidate_id: str,
    token: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "risk_level": "warning",
        "requires_confirmation": True,
        "message": "Import preview may use most available memory.",
        "warnings": ["Import preview may use most available memory."],
        "confirmation_challenge": {
            "schema_version": 1,
            "challenge_id": token,
            "command_name": command_name,
            "scope_fingerprint": f"{command_name}-scope-1",
            "ttl_seconds": 120.0,
            "candidate_id": candidate_id,
            "configuration_fingerprint": f"{command_name}-configuration-1",
            "preflight_fingerprint": f"{command_name}-preflight-1",
        },
    }


def test_schema_rejection_prevents_registry_and_confirmation_checks() -> None:
    coordinator, source, verifier, registry = _coordinator(
        _context(),
        verifier=_Verifier(valid=False),
    )

    decision = coordinator.evaluate(_request())

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.message == "schema mismatch"
    assert decision.result.error_type == "input"
    assert decision.result.state == {"state_reliable": True}
    assert decision.result.capability == _context().availability.to_dict()
    assert decision.result.diagnostics == {"publication_generation": 17}
    assert source.reads == 1
    assert verifier.calls == 1
    assert registry.reads == 0


def test_host_deterministic_continuation_rejects_non_allowlisted_mutation() -> None:
    coordinator, source, verifier, registry = _coordinator(
        _context(tool_name="apply_standard_preprocess"),
    )

    decision = coordinator.evaluate_host_deterministic_continuation(
        "apply_standard_preprocess",
        {},
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "contract"
    assert "not an allowlisted host continuation" in decision.result.message
    assert source.reads == 0
    assert verifier.calls == 0
    assert registry.reads == 0


def test_host_deterministic_continuation_rejects_parameterized_allowlisted_tool() -> (
    None
):
    coordinator, source, verifier, registry = _coordinator(
        _context(tool_name="preview_interpretation"),
    )

    decision = coordinator.evaluate_host_deterministic_continuation(
        "preview_interpretation",
        {"unexpected": True},
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "contract"
    assert "parameter-free" in decision.result.message
    assert source.reads == 0
    assert verifier.calls == 0
    assert registry.reads == 0


def test_capability_block_prevents_registry_lookup() -> None:
    coordinator, source, verifier, registry = _coordinator(_context(enabled=False))

    decision = coordinator.evaluate(_request())

    assert decision.action is ToolAttemptAction.CAPABILITY_BLOCKED
    assert decision.result is not None
    assert decision.result.diagnostics["publication_generation"] == 17
    assert source.reads == 1
    assert verifier.calls == 1
    assert registry.reads == 0


def test_schema_rejection_uses_requested_path_label_in_typed_result(tmp_path) -> None:
    eeg_path = tmp_path / "A01T.gdf"
    eeg_path.touch()
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="scan_source"),
        verifier=_Verifier(
            valid=False,
            error_message="Missing required parameter(s): source_path",
        ),
    )

    decision = coordinator.evaluate(
        _request(
            tool_name="scan_source",
            params={"source_path": str(eeg_path)},
            text=f"Load {eeg_path}",
        )
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.message == "Required source path is missing."


def test_tool_and_backend_confirmation_metadata_share_one_boundary() -> None:
    registry = _Registry(_Tool(requires_confirmation=True))
    coordinator, source, verifier, _registry = _coordinator(
        _context(confirmation=True),
        registry=registry,
    )

    decision = coordinator.evaluate(_request())

    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert decision.context is not None
    assert decision.context.generation == 17
    assert source.reads == 1
    assert verifier.calls == 1
    assert registry.reads == 1


def test_missing_context_fails_closed_without_controller_fallback() -> None:
    coordinator, source, verifier, registry = _coordinator(None)

    decision = coordinator.evaluate(_request())

    assert decision.action is ToolAttemptAction.CAPABILITY_BLOCKED
    assert decision.context is not None
    assert decision.context.policy_error is not None
    assert decision.result is not None
    assert decision.result.error_type == "runtime"
    assert source.reads == 1
    assert verifier.calls == 1
    assert registry.reads == 0


def test_selection_policy_keeps_only_first_normalized_proposal() -> None:
    coordinator, _source, _verifier, _registry = _coordinator(_context())
    commands = [("query_state", {}), ("evaluate", {})]

    decision = coordinator.select_proposal(
        commands,
        mode="multi",
        execution_count=0,
        workflow_tool_cap=5,
        cancelled=False,
    )

    assert decision.command == ("query_state", {})
    assert decision.reason == "execute"
    assert decision.discarded_count == 1


def test_start_training_warning_creates_command_bound_resource_receipt() -> None:
    preflight = _training_preflight()
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="start_training"),
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="start_training",
        params={"append": True},
        context=_context(tool_name="start_training"),
    )
    warning = ToolCommandResult.failure(
        "start_training",
        preflight["message"],
        command_name="train",
        error_type="confirmation_required",
        diagnostics={"resource_preflight": preflight},
    )

    pending = coordinator.resource_confirmation(initial, warning)

    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    receipt = pending.resource_preflight_receipt
    assert receipt is not None
    assert receipt.command_name == "start_training"
    assert receipt.candidate_id is None
    assert receipt.token == "training-receipt-1"  # noqa: S105
    assert receipt.configuration_fingerprint == "configuration-1"
    assert receipt.preflight_fingerprint == "preflight-1"
    assert receipt.scope_fingerprint == "scope-1"
    assert receipt.ttl_seconds == 120.0


def test_start_training_receipt_approval_injects_resource_confirmation() -> None:
    preflight = _training_preflight()
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="start_training")
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="start_training",
        params={"append": True},
        context=_context(tool_name="start_training"),
    )
    warning = ToolCommandResult.failure(
        "start_training",
        str(preflight["message"]),
        command_name="train",
        error_type="confirmation_required",
        diagnostics={"resource_preflight": preflight},
    )
    pending = coordinator.resource_confirmation(initial, warning)
    assert pending is not None

    params = coordinator.approved_params(pending)

    assert params == {
        "append": True,
        "confirmed": True,
        "resource_preflight_confirmed": True,
        "resource_preflight_token": "training-receipt-1",
    }


@pytest.mark.parametrize(
    ("command_name", "params", "candidate_id", "token", "expected"),
    [
        (
            "preview_interpretation",
            {"choices": {"skip_labels": True}},
            "scan-1",
            "preview-receipt-1",
            {
                "scan_id": "scan-1",
                "choices": {"skip_labels": True},
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "preview-receipt-1",
            },
        ),
        (
            "reload_interpretation_recipe",
            {"recipe_path": "/tmp/recipe.json"},
            "recipe-1",
            "reload-receipt-1",
            {
                "recipe_path": "/tmp/recipe.json",
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "reload-receipt-1",
            },
        ),
    ],
)
def test_data_interpretation_resource_warning_approval_injects_exact_receipt(
    command_name: str,
    params: dict[str, Any],
    candidate_id: str,
    token: str,
    expected: dict[str, Any],
) -> None:
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name=command_name),
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name=command_name,
        params=params,
        context=_context(tool_name=command_name),
    )
    warning = ToolCommandResult.failure(
        command_name,
        "Import preview may use most available memory.",
        command_name=command_name,
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": _interpretation_preflight(
                command_name=command_name,
                candidate_id=candidate_id,
                token=token,
            ),
        },
    )

    pending = coordinator.resource_confirmation(initial, warning)

    assert pending is not None
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert coordinator.approved_params(pending) == expected


def test_preview_resource_receipt_rejects_different_requested_scan() -> None:
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="preview_interpretation"),
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="preview_interpretation",
        params={"scan_id": "scan-2", "choices": {}},
        context=_context(tool_name="preview_interpretation"),
    )
    warning = ToolCommandResult.failure(
        "preview_interpretation",
        "Import preview may use most available memory.",
        command_name="preview_interpretation",
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": _interpretation_preflight(
                command_name="preview_interpretation",
                candidate_id="scan-1",
                token="preview-receipt-1",  # noqa: S106
            ),
        },
    )
    pending = coordinator.resource_confirmation(initial, warning)
    assert pending is not None

    with pytest.raises(ValueError, match="scan does not match"):
        coordinator.approved_params(pending)


def test_blocking_resource_result_never_becomes_approvable_confirmation() -> None:
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="preview_interpretation"),
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="preview_interpretation",
        params={"scan_id": "scan-1"},
        context=_context(tool_name="preview_interpretation"),
    )
    blocking = ToolCommandResult.failure(
        "preview_interpretation",
        "Dataset is too large to preview safely.",
        command_name="preview_interpretation",
        error_type="precondition",
        recoverable=True,
        diagnostics={
            "resource_preflight": {
                "schema_version": 1,
                "risk_level": "blocking",
                "requires_confirmation": False,
                "message": "Dataset is too large to preview safely.",
            },
        },
    )

    assert coordinator.resource_confirmation(initial, blocking) is None


def test_resource_receipts_are_restricted_to_explicit_command_allowlist() -> None:
    coordinator, _source, _verifier, _registry = _coordinator(
        _context(tool_name="list_files")
    )
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="list_files",
        params={"directory": "/data"},
        context=_context(tool_name="list_files"),
    )
    warning = ToolCommandResult.failure(
        "list_files",
        "Loading may use most available memory.",
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": {
                "requires_confirmation": True,
                "confirmation_token": "receipt-1",
                "candidate_id": "candidate-1",
                "scope_fingerprint": "scope-1",
            }
        },
    )

    blocked = coordinator.resource_confirmation(initial, warning)

    assert blocked is not None
    assert blocked.action is ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED
    assert blocked.result is not None
    assert blocked.result.error_type == "contract"
    assert "does not support receipt-bound" in blocked.result.message
    assert (
        blocked.result.diagnostics["resource_confirmation_contract"]
        == "unsupported_command"
    )
