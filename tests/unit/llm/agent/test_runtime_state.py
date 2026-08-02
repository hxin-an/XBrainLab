"""Assistant runtime snapshot serialization regressions."""

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeSelectionOutcome


def test_runtime_snapshot_round_trip_preserves_effective_device() -> None:
    snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        model_id="ibm-granite/granite-3.3-2b-instruct",
        requested_model_id="ibm-granite/granite-3.3-2b-instruct",
        selection_outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Local runtime ready on CPU.",
        execution_device="cpu",
        device_fallback_reason="CUDA is not available.",
        activation_id=7,
    )

    restored = AssistantRuntimeSnapshot.from_payload(snapshot.to_dict())

    assert restored == snapshot
    assert restored.device_fallback_used is True


def test_legacy_runtime_snapshot_defaults_new_device_fields() -> None:
    restored = AssistantRuntimeSnapshot.from_payload(
        {
            "phase": "ready",
            "initialized": True,
            "backend_mode": "local",
            "model_id": "legacy-cached-model",
            "selection_outcome": "exact",
        }
    )

    assert restored.execution_device == ""
    assert restored.device_fallback_reason == ""
    assert restored.device_fallback_used is False
