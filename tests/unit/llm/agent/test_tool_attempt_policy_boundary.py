"""Behavior tests for the assistant tool-attempt policy boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from XBrainLab.backend.application.resource_preflight import (
    ResourceConfirmationChallenge,
)
from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.verifier import VerificationResult
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.result_contract import ToolCommandResult


@dataclass(frozen=True)
class _Tool:
    requires_confirmation: bool = False
    description: str = "Test tool"
    parameters: dict[str, Any] | None = None


class _Registry:
    def __init__(self, tool: _Tool | None = None) -> None:
        self.tool = tool or _Tool()

    def get_tool(self, name: str) -> Any:
        del name
        return self.tool


class _Verifier:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict[str, Any]],
    ) -> VerificationResult:
        self.calls.append(tool_call)
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


def test_unavailable_reference_reason_blocks_before_any_execution_boundary() -> None:
    coordinator, source, verifier = _coordinator(_context("create_epochs"))
    publication = PromptToolPublication(
        tool_names=frozenset({"import_eeg_data", "switch_panel"}),
        backend_generation=48,
        blocked_reasons=(
            ("create_epochs", "Load raw data before creating EEG epochs."),
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "create_epochs",
            text="Create epochs now.",
            publication=publication,
        )
    )

    assert decision.action is ToolAttemptAction.PUBLICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "precondition"
    assert decision.result.blocked_reason == (
        "Load raw data before creating EEG epochs."
    )
    assert decision.result.diagnostics == {
        "publication_generation": 48,
        "published_tool_count": 2,
    }
    assert source.reads == []
    assert verifier.calls == []


def test_unpublished_unregistered_tool_is_rejected_before_verification() -> None:
    coordinator, source, verifier = _coordinator(_context("unregistered_tool"))
    publication = PromptToolPublication(
        tool_names=frozenset({"scan_source", "preview_interpretation"}),
        backend_generation=47,
    )

    decision = coordinator.evaluate(
        _request(
            "unregistered_tool",
            params={},
            text="Run this command",
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
        _context("select_model", command_name="configure_training")
    )

    decision = coordinator.evaluate(_request("select_model", text="Start training"))

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["select_model"]
    assert verifier.calls == [("select_model", {})]


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
    assert verifier.calls == [("preview_interpretation", {})]


def test_explicit_direct_parameter_value_reaches_execution_boundary() -> None:
    coordinator, source, verifier = _coordinator(
        _context("resample_data", command_name="preprocess")
    )

    decision = coordinator.evaluate(
        _request(
            "resample_data",
            params={"rate": 128},
            text="Resample the EEG data to 128 Hz.",
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["resample_data"]
    assert verifier.calls == [("resample_data", {"rate": 128})]


@pytest.mark.parametrize(
    ("tool_name", "params", "text"),
    (
        ("set_reference", {"method": "average"}, "Set the EEG reference."),
        ("normalize_data", {"method": "z-score"}, "Normalize the EEG data."),
    ),
)
def test_unprovided_direct_method_is_rejected_without_execution(
    tool_name: str,
    params: dict[str, Any],
    text: str,
) -> None:
    coordinator, source, verifier = _coordinator(
        _context(tool_name, command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": list(params)}),
    )

    decision = coordinator.evaluate(
        _request(
            tool_name,
            params=params,
            text=text,
        )
    )

    assert decision.action is ToolAttemptAction.RESPOND
    assert decision.message
    assert decision.params == params
    assert decision.result is None
    assert decision.context == _context(tool_name, command_name="preprocess")
    assert source.reads == [tool_name]
    assert verifier.calls == [(tool_name, params)]


def test_host_admission_does_not_grade_numeric_proposal_against_user_text() -> None:
    coordinator, _source, _verifier = _coordinator(
        _context("apply_bandpass_filter", command_name="preprocess"),
        tool=_Tool(
            parameters={"type": "object", "required": ["low_freq", "high_freq"]}
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "apply_bandpass_filter",
            params={"low_freq": 1, "high_freq": 40},
            text="low 1 Hz, high 38 Hz",
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert decision.params == {"low_freq": 1, "high_freq": 40}


def test_incomplete_direct_proposal_cannot_bypass_full_schema_validation() -> None:
    verifier = _Verifier(valid=False)
    coordinator, _source, observed_verifier = _coordinator(
        _context("apply_bandpass_filter", command_name="preprocess"),
        verifier=verifier,
        tool=_Tool(
            parameters={"type": "object", "required": ["low_freq", "high_freq"]}
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "apply_bandpass_filter",
            params={"high_freq": 20},
            text="20 Hz",
        )
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert decision.result is not None
    assert decision.result.message == "schema mismatch"
    assert observed_verifier.calls == [("apply_bandpass_filter", {"high_freq": 20})]


def test_inadmissible_partial_bandpass_keeps_schema_rejection() -> None:
    verifier = _Verifier(valid=False)
    coordinator, _source, observed_verifier = _coordinator(
        _context("apply_bandpass_filter", command_name="preprocess"),
        verifier=verifier,
        tool=_Tool(
            parameters={"type": "object", "required": ["low_freq", "high_freq"]}
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "apply_bandpass_filter",
            params={"high_freq": 20, "unexpected": 1},
            text="20 Hz",
        )
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert observed_verifier.calls == [
        ("apply_bandpass_filter", {"high_freq": 20, "unexpected": 1})
    ]


def test_model_mapped_reversed_bandpass_reaches_schema_validation() -> None:
    verifier = _Verifier(valid=False)
    coordinator, _source, observed_verifier = _coordinator(
        _context("apply_bandpass_filter", command_name="preprocess"),
        verifier=verifier,
        tool=_Tool(
            parameters={"type": "object", "required": ["low_freq", "high_freq"]}
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "apply_bandpass_filter",
            params={"low_freq": 40, "high_freq": 10},
            text="10 Hz 40 Hz",
        )
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert observed_verifier.calls == [
        ("apply_bandpass_filter", {"low_freq": 40, "high_freq": 10})
    ]


def test_numeric_proposal_still_requires_backend_capability() -> None:
    coordinator, _source, _verifier = _coordinator(
        _context("resample_data", enabled=False, command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": ["rate"]}),
    )

    decision = coordinator.evaluate(
        _request(
            "resample_data",
            params={"rate": 128},
            text="Resample the EEG data.",
        )
    )

    assert decision.action is ToolAttemptAction.CAPABILITY_BLOCKED
    assert decision.result is not None
    assert decision.result.blocked_reason == "Dataset is not ready."


def test_import_eeg_data_proposal_is_not_blocked_by_host_english_intent_gate() -> None:
    coordinator, source, verifier = _coordinator(
        _context("import_eeg_data", command_name="scan_source")
    )

    decision = coordinator.evaluate(
        _request("import_eeg_data", text="I want to import data.")
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["import_eeg_data"]
    assert verifier.calls == [("import_eeg_data", {})]


@pytest.mark.parametrize(
    ("tool_name", "params", "reply"),
    (
        ("set_reference", {"method": "average"}, "average"),
        ("normalize_data", {"method": "z-score"}, "z-score"),
    ),
)
def test_current_turn_direct_methods_reach_execution_boundary(
    tool_name: str,
    params: dict[str, Any],
    reply: str,
) -> None:
    coordinator, source, verifier = _coordinator(
        _context(tool_name, command_name="preprocess")
    )

    decision = coordinator.evaluate(
        _request(
            tool_name,
            params=params,
            text=reply,
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == [tool_name]
    assert verifier.calls == [(tool_name, params)]


def test_current_turn_values_still_require_full_schema_verification() -> None:
    coordinator, _source, verifier = _coordinator(
        _context("resample_data", command_name="preprocess"),
        verifier=_Verifier(valid=False),
    )

    decision = coordinator.evaluate(
        _request("resample_data", params={"rate": 128}, text="Resample to 128 Hz.")
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert verifier.calls == [("resample_data", {"rate": 128})]


def test_published_command_is_admitted_for_continue_wording() -> None:
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
    assert verifier.calls == [("apply_interpretation", {})]


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
    params = {"append": True}
    assert coordinator.confirmed_params(
        "start_training",
        params,
        confirmation_kind="resource_preflight",
        resource_preflight_receipt=ResourceConfirmationChallenge(
            challenge_id="receipt-1",
            command_name="start_training",
            configuration_fingerprint="configuration-1",
            preflight_fingerprint="preflight-1",
            scope_fingerprint="scope-1",
            ttl_seconds=120.0,
        ),
    ) == {
        "append": True,
        "confirmed": True,
        "resource_preflight_confirmed": True,
        "resource_preflight_token": "receipt-1",
    }
    assert params == {"append": True}


def test_resource_warning_becomes_training_bound_typed_confirmation() -> None:
    coordinator, source, verifier = _coordinator(
        _context("start_training", command_name="train", long_running=True)
    )
    initial = coordinator.evaluate(
        _request(
            "start_training",
            params={"append": True},
            text="Start training",
        )
    )
    assert initial.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    warning = ToolCommandResult.failure(
        "start_training",
        "Training may exceed available GPU memory.",
        command_name="train",
        error_type="confirmation_required",
        diagnostics={
            "resource_preflight": {
                "requires_confirmation": True,
                "confirmation_token": "receipt-1",
                "confirmation_command": "start_training",
                "configuration_fingerprint": "configuration-1",
                "preflight_fingerprint": "preflight-1",
                "scope_fingerprint": "scope-1",
                "confirmation_ttl_seconds": 120.0,
            },
        },
    )

    confirmation = coordinator.resource_confirmation(initial, warning)

    assert confirmation is not None
    assert confirmation.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert confirmation.confirmation_kind == "resource_preflight"
    assert confirmation.resource_preflight_receipt == ResourceConfirmationChallenge(
        challenge_id="receipt-1",
        command_name="start_training",
        configuration_fingerprint="configuration-1",
        preflight_fingerprint="preflight-1",
        scope_fingerprint="scope-1",
        ttl_seconds=120.0,
    )
    assert confirmation.command_name == "start_training"
    assert confirmation.params == initial.params == {"append": True}
    assert confirmation.context is initial.context
    assert confirmation.context is not None
    assert confirmation.context.generation == 21
    assert confirmation.message == warning.message
    assert source.reads == ["start_training"]
    assert verifier.calls == [("start_training", {"append": True})]


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
