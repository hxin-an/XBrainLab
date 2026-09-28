"""Real schema/provenance checks for a single cumulative user request."""

import json

import pytest

from XBrainLab.llm.agent.assembler import ContextAssembler, PromptToolPublication
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ParameterChange,
    RequestUpdate,
    ToolEnvelopeStatus,
)
from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator
from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptCoordinator
from XBrainLab.llm.agent.verifier import VerificationLayer
from XBrainLab.llm.tools.definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseNotchFilterTool,
)
from XBrainLab.llm.tools.tool_registry import ToolRegistry


@pytest.fixture
def coordinator():
    registry = ToolRegistry()
    registry.register(BaseBandPassFilterTool())
    registry.register(BaseNotchFilterTool())
    return ToolAttemptCoordinator(
        registry=registry,
        verifier=VerificationLayer(),
        context_source=None,  # No domain execution is involved in preparing a draft.
    )


def prepare(
    coordinator,
    *,
    pending=None,
    mode="replace",
    action="apply_bandpass_filter",
    changes=(),
    turn="U1",
    text="Lower cutoff 7 Hz.",
    generation=4,
):
    return coordinator.prepare_request_update(
        RequestUpdate(mode=mode, action=action, changes=changes),
        pending=pending,
        user_turn_id=turn,
        user_text=text,
        question="Which cutoff?",
        publication=PromptToolPublication(
            tool_names=frozenset({"apply_bandpass_filter", "apply_notch_filter"}),
            workflow_stage="preprocessed",
            backend_generation=generation,
        ),
    )


def lower(coordinator):
    return prepare(
        coordinator,
        changes=(("low_freq", ParameterChange(7, "U1", "Lower cutoff 7 Hz.")),),
    )


def test_retrieval_uses_bounded_user_evidence_without_changing_required_sources(
    coordinator,
):
    pending = lower(coordinator)
    original_sources = pending.sources
    query = ContextAssembler.retrieval_query(
        "Upper cutoff 30 Hz.", pending_request=pending
    )
    assert query == "Lower cutoff 7 Hz.\nUpper cutoff 30 Hz."
    assert "apply_bandpass_filter" not in query
    assert "Which cutoff?" not in query
    assert (
        len(ContextAssembler.retrieval_query("x" * 16_384, pending_request=pending))
        <= 1024
    )
    assert pending.sources == original_sources
    owner = PendingInteractionCoordinator()
    owner.set_request(pending)
    owner.invalidate_request()
    assert (
        ContextAssembler.retrieval_query("New question.", pending_request=owner.request)
        == "New question."
    )


def test_initial_value_survives_followup_and_explicit_correction(coordinator):
    pending = lower(coordinator)
    corrected = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        turn="U2",
        text="Change lower cutoff to 8 Hz.",
        changes=(("low_freq", ParameterChange(8, "U2", "lower cutoff to 8 Hz")),),
    )
    complete = prepare(
        coordinator,
        pending=corrected,
        mode="continue",
        turn="U3",
        text="30 Hz.",
        changes=(("high_freq", ParameterChange(30, "U3", "30 Hz")),),
    )
    assert pending.parameter_values() == {"low_freq": 7}
    assert complete.parameter_values() == {"low_freq": 8, "high_freq": 30}
    assert dict(complete.parameters)["low_freq"].source_turn == "U2"


@pytest.mark.parametrize(
    "wire_mode,expected",
    [
        ("update_pending", {"low_freq": 8, "high_freq": 30}),
        ("new_request", {"low_freq": 8}),
    ],
)
def test_flat_mode_preserves_or_discards_other_values_without_guessing(
    coordinator, wire_mode, expected
):
    pending = prepare(
        coordinator,
        text="Bandpass from 7 to 30 Hz.",
        changes=(
            ("low_freq", ParameterChange(7, "U1", "7 to 30 Hz")),
            ("high_freq", ParameterChange(30, "U1", "7 to 30 Hz")),
        ),
    )
    text = "Lower cutoff 8 Hz."
    proposal = CommandParser.parse_product(
        json.dumps(
            {
                "decision": "clarify",
                "mode": wire_mode,
                "action": "apply_bandpass_filter",
                "changes": {
                    "low_freq": {"value": 8, "source_turn": "U2", "quote": text}
                },
                "message": "Which cutoff?",
            }
        )
    )
    assert proposal.status is ToolEnvelopeStatus.NO_TOOL
    updated = prepare(
        coordinator,
        pending=pending,
        mode=proposal.request.mode,
        changes=proposal.request.changes,
        turn="U2",
        text=text,
    )
    assert updated.parameter_values() == expected
    assert pending.parameter_values() == {"low_freq": 7, "high_freq": 30}
    assert dict(updated.parameters)["low_freq"].source_turn == "U2"
    if wire_mode == "update_pending":
        assert dict(updated.parameters)["high_freq"].source_turn == "U1"


@pytest.mark.parametrize(
    "source,quote,value",
    [
        ("RAG1", "30 Hz", 30),
        ("U2", "absent", 30),
        ("U2", "30 Hz", 99),
    ],
)
def test_fabricated_source_or_value_cannot_mutate_saved_parameters(
    coordinator, source, quote, value
):
    pending = lower(coordinator)
    with pytest.raises(ValueError):
        prepare(
            coordinator,
            pending=pending,
            mode="continue",
            turn="U2",
            text="30 Hz",
            changes=(("high_freq", ParameterChange(value, source, quote)),),
        )
    assert pending.parameter_values() == {"low_freq": 7}


def test_replace_and_cancel_do_not_inherit_parameters(coordinator):
    pending = lower(coordinator)
    replaced = prepare(
        coordinator,
        pending=pending,
        action="apply_notch_filter",
        turn="U2",
        text="Notch 50 Hz.",
        changes=(("freq", ParameterChange(50, "U2", "50 Hz")),),
    )
    assert replaced.parameter_values() == {"freq": 50}
    assert prepare(coordinator, pending=replaced, mode="cancel", action=None) is None


def test_stale_request_and_silent_action_change_are_rejected(coordinator):
    pending = lower(coordinator)
    with pytest.raises(ValueError, match="changed"):
        prepare(coordinator, pending=pending, mode="continue", generation=5)
    with pytest.raises(ValueError, match="action"):
        prepare(
            coordinator, pending=pending, mode="continue", action="apply_notch_filter"
        )


def test_unresolved_operation_preserves_original_user_evidence(coordinator):
    pending = prepare(coordinator, action=None, text="Filter with lower cutoff 7 Hz.")
    assert pending.parameter_values() == {}
    resolved = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        turn="U2",
        text="Bandpass.",
        changes=(("low_freq", ParameterChange(7, "U1", "lower cutoff 7 Hz")),),
    )
    assert resolved.parameter_values() == {"low_freq": 7}


def test_pending_owner_does_not_block_plain_text_and_clear_removes_draft(coordinator):
    owner = PendingInteractionCoordinator()
    pending = lower(coordinator)
    owner.set_request(pending)
    assert owner.request is pending
    assert not owner.has_pending
    owner.clear()
    assert owner.request is None


def test_quote_cannot_cut_a_different_numeric_value_out_of_source(coordinator):
    with pytest.raises(ValueError):
        prepare(
            coordinator,
            text="Bandpass from 17 Hz to 30 Hz.",
            changes=(
                ("low_freq", ParameterChange(7, "U1", "7 Hz")),
                ("high_freq", ParameterChange(30, "U1", "30 Hz")),
            ),
        )


def test_unresolved_value_remains_available_after_intermediate_clarification(
    coordinator,
):
    pending = prepare(coordinator, action=None, text="Filter data.")
    pending = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        action=None,
        turn="U2",
        text="7 Hz.",
    )
    pending = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        action=None,
        turn="U3",
        text="That is the lower cutoff.",
    )
    resolved = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        turn="U4",
        text="Bandpass.",
        changes=(("low_freq", ParameterChange(7, "U2", "7 Hz")),),
    )
    assert resolved.parameter_values() == {"low_freq": 7}
    assert dict(resolved.sources)["U3"] == "That is the lower cutoff."


def test_multiple_changes_are_atomic_and_superseded_value_cannot_return(coordinator):
    pending = lower(coordinator)
    with pytest.raises(ValueError):
        prepare(
            coordinator,
            pending=pending,
            mode="continue",
            turn="U2",
            text="Lower 8 Hz and upper 30 Hz.",
            changes=(
                ("low_freq", ParameterChange(8, "U2", "Lower 8 Hz")),
                ("high_freq", ParameterChange(99, "U2", "upper 30 Hz")),
            ),
        )
    assert pending.parameter_values() == {"low_freq": 7}
    corrected = prepare(
        coordinator,
        pending=pending,
        mode="continue",
        turn="U2",
        text="Lower 8 Hz.",
        changes=(("low_freq", ParameterChange(8, "U2", "Lower 8 Hz")),),
    )
    with pytest.raises(ValueError, match="superseded"):
        prepare(
            coordinator,
            pending=corrected,
            mode="continue",
            turn="U3",
            text="30 Hz.",
            changes=(("low_freq", ParameterChange(7, "U1", "Lower cutoff 7 Hz.")),),
        )
