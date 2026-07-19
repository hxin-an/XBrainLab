import pytest

from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.core.generation import GenerationProfile


def test_structured_action_request_uses_deterministic_generation():
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "Scan /data"}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    )

    assert request.generation_profile is GenerationProfile.STRUCTURED_DECISION
    assert request.to_model_messages() == [{"role": "user", "content": "Scan /data"}]


def test_natural_language_request_preserves_configured_generation():
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "What is an epoch?"}],
        response_contract=AssistantResponseContract.NATURAL_LANGUAGE,
    )

    assert request.generation_profile is GenerationProfile.INFORMATIONAL_TEXT


def test_generation_request_copies_mutable_input_messages():
    messages = [{"role": "user", "content": "Explain EEGNet"}]
    request = AssistantGenerationRequest.from_messages(
        messages,
        response_contract=AssistantResponseContract.NATURAL_LANGUAGE,
    )

    messages[0]["content"] = "mutated"

    assert request.to_model_messages()[0]["content"] == "Explain EEGNet"


def test_generation_request_requires_positive_id_when_correlated() -> None:
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "Explain EEGNet"}],
        response_contract=AssistantResponseContract.NATURAL_LANGUAGE,
    )

    with pytest.raises(ValueError, match="positive"):
        request.correlated(0)


@pytest.mark.parametrize(
    "contract_type",
    [AssistantGenerationStopRequest, AssistantGenerationStopAcknowledgement],
)
@pytest.mark.parametrize("generation_id", [0, -1, True])
def test_generation_stop_contracts_require_positive_id(
    contract_type,
    generation_id,
) -> None:
    kwargs = {"generation_id": generation_id}
    if contract_type is AssistantGenerationStopAcknowledgement:
        kwargs["stopped"] = True

    with pytest.raises(ValueError, match="positive"):
        contract_type(**kwargs)


def test_generation_stop_acknowledgement_is_exact_and_typed() -> None:
    request = AssistantGenerationStopRequest(generation_id=41)
    acknowledgement = AssistantGenerationStopAcknowledgement(
        generation_id=request.generation_id,
        stopped=True,
    )

    assert acknowledgement.generation_id == 41
    assert acknowledgement.stopped is True


@pytest.mark.parametrize("generation_id", [0, -1, True])
def test_generation_event_rejects_invalid_correlation_id(generation_id) -> None:
    with pytest.raises(ValueError, match="positive"):
        AssistantGenerationEvent(
            generation_id=generation_id,
            phase=AssistantGenerationEventPhase.STARTED,
        )


def test_generation_event_payload_matches_phase() -> None:
    with pytest.raises(ValueError, match="requires text"):
        AssistantGenerationEvent(
            generation_id=1,
            phase=AssistantGenerationEventPhase.CHUNK,
        )
    with pytest.raises(ValueError, match="cannot include text"):
        AssistantGenerationEvent(
            generation_id=1,
            phase=AssistantGenerationEventPhase.FINISHED,
            text="late output",
        )
    with pytest.raises(ValueError, match="cannot include text"):
        AssistantGenerationEvent(
            generation_id=1,
            phase=AssistantGenerationEventPhase.CANCELLED,
            text="stopped",
        )
