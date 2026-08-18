"""Behavior tests for the assistant tool-attempt policy boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ResourcePreflightReceipt,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.turn_orchestrator import AssistantToolAttemptSession
from XBrainLab.llm.agent.verifier import VerificationResult
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
)


@dataclass(frozen=True)
class _Tool:
    requires_confirmation: bool = False
    description: str = "Test tool"


class _Registry:
    def __init__(self, tool: _Tool | None = None) -> None:
        self.tool = tool or _Tool()

    def get_tool(self, name: str) -> Any:
        del name
        return self.tool


class _Verifier:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.calls: list[tuple[tuple[str, dict[str, Any]], float]] = []

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict[str, Any]],
        *,
        confidence: float,
    ) -> VerificationResult:
        self.calls.append((tool_call, confidence))
        return VerificationResult(
            self.valid,
            None if self.valid else "schema mismatch",
        )


class _ContextSource:
    def __init__(self, context: ToolAvailabilityContext | None) -> None:
        self.context = context
        self.reads: list[str] = []

    def get_context(self, tool_name: str) -> ToolAvailabilityContext | None:
        self.reads.append(tool_name)
        return self.context


def _context(
    tool_name: str,
    *,
    enabled: bool = True,
    generation: int = 21,
    **availability: Any,
) -> ToolAvailabilityContext:
    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=enabled,
            reasons=() if enabled else ("Dataset is not ready.",),
            **availability,
        ),
        state={"state_reliable": True},
        generation=generation,
    )


def _request(
    tool_name: str,
    *,
    params: dict[str, Any] | None = None,
    text: str,
    publication: PromptToolPublication | None = None,
) -> ToolAttemptRequest:
    return ToolAttemptRequest(
        command_name=tool_name,
        params=params or {},
        confidence=0.9,
        publication=publication
        or PromptToolPublication(
            tool_names=frozenset({tool_name}),
            backend_generation=21,
        ),
        latest_user_text=text,
    )


def _coordinator(
    context: ToolAvailabilityContext | None,
    *,
    verifier: _Verifier | None = None,
    tool: _Tool | None = None,
) -> tuple[ToolAttemptCoordinator, _ContextSource, _Verifier]:
    source = _ContextSource(context)
    actual_verifier = verifier or _Verifier()
    return (
        ToolAttemptCoordinator(
            registry=_Registry(tool),
            verifier=actual_verifier,
            context_source=source,
        ),
        source,
        actual_verifier,
    )


def test_unpublished_tool_is_blocked_with_prompt_generation_before_context_read() -> (
    None
):
    coordinator, source, verifier = _coordinator(_context("start_training"))
    publication = PromptToolPublication(
        tool_names=frozenset({"query_state"}),
        backend_generation=47,
    )

    decision = coordinator.evaluate(
        _request(
            "start_training",
            text="Start training",
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.PUBLICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "tool_not_published"
    assert decision.result.diagnostics == {
        "publication_generation": 47,
        "published_tool_count": 1,
    }
    assert source.reads == []
    assert verifier.calls == []


def test_unpublished_legacy_attach_labels_is_rejected_before_verification() -> None:
    coordinator, source, verifier = _coordinator(_context("attach_labels"))
    publication = PromptToolPublication(
        tool_names=frozenset({"scan_source", "preview_interpretation"}),
        backend_generation=47,
    )

    decision = coordinator.evaluate(
        _request(
            "attach_labels",
            params={"mapping": {"A01T.gdf": "A01T.mat"}},
            text="Attach these labels",
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.PUBLICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "tool_not_published"
    assert source.reads == []
    assert verifier.calls == []


def test_stale_prompt_generation_blocks_immediate_execution() -> None:
    coordinator, source, verifier = _coordinator(
        _context("validate_interpretation", generation=22)
    )
    publication = PromptToolPublication(
        tool_names=frozenset({"validate_interpretation"}),
        backend_generation=21,
    )

    decision = coordinator.evaluate(
        _request(
            "validate_interpretation",
            text="Validate the reviewed interpretation.",
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.PUBLICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "stale_publication"
    assert decision.result.diagnostics == {
        "prompt_generation": 21,
        "current_generation": 22,
    }
    assert source.reads == ["validate_interpretation"]
    assert verifier.calls == []


def test_published_tool_is_not_reclassified_from_host_text() -> None:
    coordinator, source, verifier = _coordinator(
        _context("set_model", command_name="configure_training")
    )

    decision = coordinator.evaluate(_request("set_model", text="Start training"))

    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert source.reads == ["set_model"]
    assert verifier.calls == [(("set_model", {}), 0.9)]


def test_explicit_continue_request_authorizes_current_backend_candidate() -> None:
    coordinator, source, verifier = _coordinator(
        _context(
            "preview_interpretation",
            command_name="preview_interpretation",
            generation=48,
        )
    )
    publication = PromptToolPublication(
        tool_names=frozenset({"preview_interpretation"}),
        backend_generation=48,
        recommended_command="preview_interpretation",
        authorized_command="preview_interpretation",
    )

    decision = coordinator.evaluate(
        _request(
            "preview_interpretation",
            text=("Load /data/S04.edf and continue until a decision is needed."),
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["preview_interpretation"]
    assert verifier.calls == [(("preview_interpretation", {}), 0.9)]


def test_natural_continue_request_only_authorizes_recommended_command() -> None:
    coordinator, source, verifier = _coordinator(
        _context(
            "apply_interpretation",
            command_name="apply_interpretation",
            generation=49,
        )
    )
    publication = PromptToolPublication(
        tool_names=frozenset({"scan_source", "apply_interpretation"}),
        backend_generation=49,
        recommended_command="apply_interpretation",
    )

    decision = coordinator.evaluate(
        _request(
            "apply_interpretation",
            text="Continue with the reviewed recording.",
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["apply_interpretation"]
    assert verifier.calls == [(("apply_interpretation", {}), 0.9)]


def test_explicit_dataset_info_request_authorizes_normalized_query_state() -> None:
    coordinator, source, verifier = _coordinator(
        _context(
            "query_state",
            command_name="query_state",
            read_only=True,
            can_auto_execute=True,
        )
    )

    decision = coordinator.evaluate(
        _request(
            "query_state",
            params={"query": "state"},
            text="Show dataset info.",
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["query_state"]
    assert len(verifier.calls) == 1


def test_unapproved_path_is_blocked_before_schema_verification() -> None:
    coordinator, source, verifier = _coordinator(
        _context("scan_source", command_name="scan_source")
    )

    decision = coordinator.evaluate(
        _request(
            "scan_source",
            params={"source_path": "/tmp/model-invented-path.gdf"},
            text="Import my EEG data",
        )
    )

    assert decision.action is ToolAttemptAction.PROVENANCE_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "input"
    assert decision.result.diagnostics["policy"] == "path_provenance"
    assert decision.result.diagnostics["publication_generation"] == 21
    assert source.reads == ["scan_source"]
    assert verifier.calls == []


def test_long_running_capability_requires_confirmation_from_single_context() -> None:
    coordinator, source, verifier = _coordinator(
        _context(
            "start_training",
            command_name="train",
            long_running=True,
        )
    )

    decision = coordinator.evaluate(_request("start_training", text="Start training"))

    assert decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert decision.context is not None
    assert decision.context.generation == 21
    assert source.reads == ["start_training"]
    assert len(verifier.calls) == 1


def test_disabled_capability_returns_generation_bound_block_result() -> None:
    coordinator, source, _verifier = _coordinator(
        _context(
            "start_training",
            enabled=False,
            command_name="train",
        )
    )

    decision = coordinator.evaluate(_request("start_training", text="Start training"))

    assert decision.action is ToolAttemptAction.CAPABILITY_BLOCKED
    assert decision.result is not None
    assert decision.result.blocked_reason == "Dataset is not ready."
    assert decision.result.diagnostics == {"publication_generation": 21}
    assert source.reads == ["start_training"]


def test_confirmation_fields_are_owned_by_coordinator() -> None:
    coordinator, _source, _verifier = _coordinator(_context("start_training"))
    assert coordinator.confirmed_params(
        "apply_interpretation",
        {"candidate_id": "candidate-1"},
        confirmation_kind="resource_preflight",
        resource_preflight_receipt=ResourcePreflightReceipt(
            challenge_id="receipt-1",
            command_name="apply_interpretation",
            candidate_id="candidate-1",
            scope_fingerprint="scope-1",
            ttl_seconds=120.0,
        ),
    ) == {
        "candidate_id": "candidate-1",
        "confirmed": True,
        "resource_preflight_confirmed": True,
        "resource_preflight_token": "receipt-1",
    }


def test_loop_state_resets_per_turn() -> None:
    coordinator, _source, _verifier = _coordinator(_context("query_state"))
    session = AssistantToolAttemptSession()
    request = _request("query_state", text="Show current workflow state")

    def observed() -> ToolAttemptRequest:
        return replace(
            request,
            repeated=session.record_tool_proposal(
                request.command_name,
                request.params,
            ),
        )

    first = coordinator.evaluate(observed())
    second = coordinator.evaluate(observed())
    third = coordinator.evaluate(observed())
    session.reset_for_user_turn()
    after_reset = coordinator.evaluate(observed())

    assert first.action is ToolAttemptAction.EXECUTE
    assert second.action is ToolAttemptAction.EXECUTE
    assert third.action is ToolAttemptAction.LOOP
    assert after_reset.action is ToolAttemptAction.EXECUTE


def test_loop_policy_handles_non_json_serializable_parameters_deterministically() -> (
    None
):
    coordinator, _source, _verifier = _coordinator(_context("query_state"))
    session = AssistantToolAttemptSession()
    opaque_value = object()
    request = _request(
        "query_state",
        params={"opaque": opaque_value},
        text="Show current workflow state",
    )

    def observed() -> ToolAttemptRequest:
        return replace(
            request,
            repeated=session.record_tool_proposal(
                request.command_name,
                request.params,
            ),
        )

    first = coordinator.evaluate(observed())
    second = coordinator.evaluate(observed())
    third = coordinator.evaluate(observed())

    assert first.action is ToolAttemptAction.EXECUTE
    assert second.action is ToolAttemptAction.EXECUTE
    assert third.action is ToolAttemptAction.LOOP


def test_resource_warning_becomes_candidate_bound_typed_confirmation() -> None:
    coordinator, _source, _verifier = _coordinator(_context("apply_interpretation"))
    initial = coordinator.evaluate(
        _request(
            "apply_interpretation",
            params={"candidate_id": "candidate-1"},
            text="Apply the reviewed import",
        )
    )
    warning = ToolCommandResult.failure(
        "apply_interpretation",
        "Import may exceed available RAM.",
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": {
                "requires_confirmation": True,
                "confirmation_token": "receipt-1",
                "candidate_id": "candidate-1",
                "scope_fingerprint": "scope-1",
                "confirmation_ttl_seconds": 120.0,
            },
        },
    )

    confirmation = coordinator.resource_confirmation(initial, warning)

    assert confirmation is not None
    assert confirmation.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert confirmation.confirmation_kind == "resource_preflight"
    assert confirmation.resource_preflight_receipt == ResourcePreflightReceipt(
        challenge_id="receipt-1",
        command_name="apply_interpretation",
        candidate_id="candidate-1",
        scope_fingerprint="scope-1",
        ttl_seconds=120.0,
    )
    assert confirmation.context is initial.context
    assert confirmation.message == warning.message


def test_resource_warning_without_backend_receipt_fails_closed() -> None:
    coordinator, _source, _verifier = _coordinator(_context("start_training"))
    initial = coordinator.evaluate(_request("start_training", text="Start training"))
    warning = ToolCommandResult.failure(
        "start_training",
        "Training configuration may exceed available GPU memory.",
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": {"requires_confirmation": True},
        },
    )

    blocked = coordinator.resource_confirmation(initial, warning)

    assert blocked is not None
    assert blocked.action is ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED
    assert blocked.result is not None
    assert blocked.result.error_type == "contract"
    assert blocked.resource_preflight_receipt is None
