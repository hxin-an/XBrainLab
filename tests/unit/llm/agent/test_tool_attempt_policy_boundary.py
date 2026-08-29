"""Behavior tests for the assistant tool-attempt policy boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from XBrainLab.llm.agent.assembler import PromptToolPublication
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ResourcePreflightReceipt,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.turn import AssistantToolInputReceipt
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
    tool_input_receipt: AssistantToolInputReceipt | None = None,
    single_proposal: bool = True,
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
        tool_input_receipt=tool_input_receipt,
        single_proposal=single_proposal,
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
    assert verifier.calls == [(("resample_data", {"rate": 128}), 0.9)]


@pytest.mark.parametrize(
    ("tool_name", "params", "text"),
    (
        (
            "apply_bandpass_filter",
            {"low_freq": 1, "high_freq": 40},
            "Apply a bandpass filter.",
        ),
        ("apply_notch_filter", {"freq": 50}, "Apply a notch filter."),
        ("resample_data", {"rate": 128}, "Resample the EEG data."),
        ("set_reference", {"method": "average"}, "Set the EEG reference."),
        ("normalize_data", {"method": "z-score"}, "Normalize the EEG data."),
    ),
)
def test_invented_direct_parameter_creates_typed_followup_receipt(
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
    assert decision.tool_input_receipt is not None
    assert decision.tool_input_receipt.command_name == tool_name
    assert decision.tool_input_receipt.missing_inputs == tuple(params)
    assert decision.tool_input_receipt.verified_parameters == ()
    assert decision.result is None
    assert decision.context == _context(tool_name, command_name="preprocess")
    assert source.reads == [tool_name]
    assert verifier.calls == [((tool_name, params), 0.9)]


@pytest.mark.parametrize(
    "text",
    (
        "Can you apply a notch filter?",
        "Could you please apply a notch filter?",
        "Please apply a notch filter.",
    ),
)
def test_affirmative_direct_request_variants_create_receipt(text: str) -> None:
    coordinator, _source, _verifier = _coordinator(
        _context("apply_notch_filter", command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": ["freq"]}),
    )

    decision = coordinator.evaluate(
        _request("apply_notch_filter", params={"freq": 50}, text=text)
    )

    assert decision.action is ToolAttemptAction.RESPOND
    assert decision.tool_input_receipt is not None


def test_informational_text_cannot_admit_or_complete_resample_receipt() -> None:
    coordinator, source, verifier = _coordinator(
        _context("resample_data", command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": ["rate"]}),
    )
    receipt = coordinator.admit_typed_clarification(
        command_name="resample_data",
        missing_inputs=("rate",),
        question="What resampling rate should I use?",
        original_user_text="What is resampling?",
        publication=PromptToolPublication(
            tool_names=frozenset({"resample_data"}),
            backend_generation=21,
        ),
    )

    decision = coordinator.evaluate(
        _request(
            "resample_data",
            params={"rate": 128},
            text="128 Hz",
            tool_input_receipt=receipt,
        )
    )

    assert receipt is None
    assert decision.action is ToolAttemptAction.RESPOND
    assert decision.action not in {
        ToolAttemptAction.EXECUTE,
        ToolAttemptAction.CONFIRMATION_REQUIRED,
    }
    assert decision.tool_input_receipt is None
    assert source.reads == ["resample_data"]
    assert verifier.calls == [(("resample_data", {"rate": 128}), 0.9)]


def test_partial_bandpass_keeps_only_user_proven_cutoff_in_receipt() -> None:
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
            text="Apply a 1 to 38 Hz bandpass filter.",
        )
    )

    assert decision.action is ToolAttemptAction.RESPOND
    assert (
        decision.message
        == "What high cutoff frequency should I use for the bandpass filter?"
    )
    assert decision.tool_input_receipt is not None
    assert decision.tool_input_receipt.verified_parameters == (("low_freq", 1),)


def test_word_number_frequency_creates_no_verified_value_in_the_receipt() -> None:
    coordinator, _source, _verifier = _coordinator(
        _context("apply_notch_filter", command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": ["freq"]}),
    )

    first = coordinator.evaluate(
        _request(
            "apply_notch_filter",
            params={"freq": 50},
            text="Apply a notch filter at fifty hertz.",
        )
    )

    assert first.action is ToolAttemptAction.RESPOND
    assert first.tool_input_receipt is not None
    assert first.tool_input_receipt.verified_parameters == ()


@pytest.mark.parametrize(
    ("tool_name", "params", "text", "single_proposal"),
    (
        ("resample_data", {"rate": 128}, "Do not resample the EEG data.", True),
        ("resample_data", {"rate": 128}, "What is resampling?", True),
        ("normalize_data", {"method": "z-score"}, "What is normalization?", True),
        ("set_reference", {"method": "average"}, "What reference should I use?", True),
        ("resample_data", {"rate": 128}, "Apply a notch filter.", True),
        ("resample_data", {"rate": 128}, "Open the visualization panel.", True),
        ("resample_data", {"rate": 128}, "Resample the EEG data.", False),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Tell me how to apply a notch filter.",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Never apply a notch filter.",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Would you use a notch filter?",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Avoid applying a notch filter.",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Do you recommend applying a notch filter?",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Skip applying a notch filter.",
            True,
        ),
        (
            "apply_notch_filter",
            {"freq": 50},
            "Please apply a notch filter without changing the reference.",
            True,
        ),
    ),
)
def test_untrusted_direct_parameter_proposal_never_creates_receipt(
    tool_name: str,
    params: dict[str, Any],
    text: str,
    single_proposal: bool,
) -> None:
    coordinator, _source, _verifier = _coordinator(
        _context(tool_name, command_name="preprocess"),
        tool=_Tool(parameters={"type": "object", "required": list(params)}),
    )

    decision = coordinator.evaluate(
        _request(
            tool_name,
            params=params,
            text=text,
            single_proposal=single_proposal,
        )
    )

    assert decision.action is ToolAttemptAction.RESPOND
    assert decision.tool_input_receipt is None
    assert decision.action not in {
        ToolAttemptAction.EXECUTE,
        ToolAttemptAction.CONFIRMATION_REQUIRED,
    }


def test_unavailable_direct_parameter_proposal_never_creates_receipt() -> None:
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

    assert decision.action is ToolAttemptAction.RESPOND
    assert decision.tool_input_receipt is None


@pytest.mark.parametrize(
    "text",
    (
        "What does importing an EEG dataset do?",
        "Do not import the EEG dataset.",
        "Cancel the EEG data import.",
        "Browse the EEG files.",
        "/tmp/recording.gdf",
        "Import an EEG dataset and create epochs.",
        "Import EEG data and stop.",
        "Load EEG data then switch panels.",
        "Open the epochs.",
        "Load the training model.",
    ),
)
def test_import_eeg_data_requires_a_narrow_positive_origin(text: str) -> None:
    coordinator, source, verifier = _coordinator(
        _context("import_eeg_data", command_name="scan_source")
    )

    decision = coordinator.evaluate(_request("import_eeg_data", text=text))

    assert decision.action is ToolAttemptAction.INTENT_BLOCKED
    assert decision.result is not None
    assert decision.result.error_type == "intent_mismatch"
    assert source.reads == ["import_eeg_data"]
    assert verifier.calls == []


@pytest.mark.parametrize(
    "text",
    (
        "Import an EEG dataset.",
        "Load EEG data.",
        "Open the EEG file.",
        "Select an EEG folder.",
        "Choose the EEG data file.",
        "Can you import EEG data?",
    ),
)
def test_import_eeg_data_allows_only_a_direct_positive_request(text: str) -> None:
    coordinator, source, verifier = _coordinator(
        _context("import_eeg_data", command_name="scan_source")
    )

    decision = coordinator.evaluate(_request("import_eeg_data", text=text))

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == ["import_eeg_data"]
    assert verifier.calls == [(("import_eeg_data", {}), 0.9)]


def test_complete_receipt_rebuilds_required_values_but_rejects_unknown_model_fields() -> (
    None
):
    coordinator, source, verifier = _coordinator(
        _context("resample_data", command_name="preprocess")
    )
    receipt = AssistantToolInputReceipt(
        command_name="resample_data",
        original_user_text="Resample the EEG data.",
        question="What resampling rate should I use?",
        publication_generation=21,
        missing_inputs=("rate",),
        verified_parameters=(("rate", 128),),
    )

    rebuilt = coordinator.evaluate(
        replace(
            _request(
                "resample_data",
                params={"rate": 128},
                text="128 Hz",
                tool_input_receipt=receipt,
            ),
            supplied_parameters={"rate": 512},
        )
    )
    unknown = coordinator.evaluate(
        replace(
            _request(
                "resample_data",
                params={"rate": 128},
                text="128 Hz",
                tool_input_receipt=receipt,
            ),
            supplied_parameters={"rate": 512, "invented": "value"},
        )
    )

    assert rebuilt.action is ToolAttemptAction.EXECUTE
    assert rebuilt.params == {"rate": 128}
    assert unknown.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert unknown.result is not None
    assert "Unknown parameter" in unknown.result.message
    assert source.reads == ["resample_data", "resample_data"]
    assert verifier.calls == [
        (("resample_data", {"rate": 128}), 0.9),
    ]


@pytest.mark.parametrize(
    ("tool_name", "params", "reply"),
    (
        (
            "apply_bandpass_filter",
            {"low_freq": 1, "high_freq": 40},
            "1\u201340 Hz",
        ),
        ("apply_notch_filter", {"freq": 50}, "50 Hz"),
        ("resample_data", {"rate": 128}, "128 赫茲"),
        ("set_reference", {"method": "average"}, "average"),
        ("normalize_data", {"method": "z-score"}, "z-score"),
    ),
)
def test_same_tool_clarification_reply_reaches_execution_boundary(
    tool_name: str,
    params: dict[str, Any],
    reply: str,
) -> None:
    coordinator, source, verifier = _coordinator(
        _context(tool_name, command_name="preprocess")
    )
    receipt = AssistantToolInputReceipt(
        command_name=tool_name,
        original_user_text="Run this preprocessing action.",
        question="Which required value should I use?",
        publication_generation=21,
        missing_inputs=tuple(params),
        verified_parameters=tuple(params.items()),
    )

    decision = coordinator.evaluate(
        _request(
            tool_name,
            params=params,
            text=reply,
            tool_input_receipt=receipt,
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE
    assert source.reads == [tool_name]
    assert verifier.calls == [((tool_name, params), 0.9)]


@pytest.mark.parametrize(
    ("reply", "receipt_tool", "receipt_generation"),
    (
        ("This recording has 128 channels.", "resample_data", 21),
        ("算了\uff0c不要 128 Hz", "resample_data", 21),
        ("128 Hz", "apply_notch_filter", 21),
        ("128 Hz", "resample_data", 20),
    ),
)
def test_clarification_receipt_cannot_authorize_unrelated_or_stale_reply(
    reply: str,
    receipt_tool: str,
    receipt_generation: int,
) -> None:
    coordinator, _source, _verifier = _coordinator(
        _context("resample_data", command_name="preprocess")
    )
    receipt = AssistantToolInputReceipt(
        command_name=receipt_tool,
        original_user_text="Resample the EEG data.",
        question="What resampling rate should I use?",
        publication_generation=receipt_generation,
        missing_inputs=("rate",),
    )

    decision = coordinator.evaluate(
        _request(
            "resample_data",
            params={"rate": 128},
            text=reply,
            tool_input_receipt=receipt,
        )
    )

    assert decision.action is ToolAttemptAction.RESPOND


def test_clarification_reply_still_passes_schema_verification_first() -> None:
    coordinator, _source, verifier = _coordinator(
        _context("resample_data", command_name="preprocess"),
        verifier=_Verifier(valid=False),
    )
    receipt = AssistantToolInputReceipt(
        command_name="resample_data",
        original_user_text="Resample the EEG data.",
        question="What resampling rate should I use?",
        publication_generation=21,
        missing_inputs=("rate",),
        verified_parameters=(("rate", 128),),
    )

    decision = coordinator.evaluate(
        _request(
            "resample_data",
            params={"rate": 128},
            text="128 Hz",
            tool_input_receipt=receipt,
        )
    )

    assert decision.action is ToolAttemptAction.VERIFICATION_BLOCKED
    assert verifier.calls == [(("resample_data", {"rate": 128}), 0.9)]


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
