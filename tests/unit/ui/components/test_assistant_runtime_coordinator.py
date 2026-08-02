"""Tests for the single assistant runtime presentation owner."""

from dataclasses import dataclass

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.assistant_runtime_coordinator import (
    AssistantRuntimeCoordinator,
)

TEST_ACTIVE_MODEL_ID = "test/runtime-active"
TEST_TARGET_MODEL_ID = "test/runtime-target"


@dataclass(frozen=True)
class _ActivationTransition(AssistantRuntimeSnapshot):
    activation_id: int = 0


def _launch_spec(model_id: str) -> AssistantRuntimeLaunchSpec:
    config = LLMConfig(model_name=model_id)
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id=AssistantRuntimeBackend.LOCAL.value,
        requested_model_id=model_id,
        model_id=model_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Test runtime ready.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )


def test_runtime_coordinator_serializes_preflight_and_worker_transitions():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    spec = _launch_spec(TEST_ACTIVE_MODEL_ID)

    coordinator.begin_loading(spec)
    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=spec.model_id,
        )
    )

    assert [snapshot.phase for snapshot in published] == [
        AssistantRuntimePhase.LOADING,
        AssistantRuntimePhase.READY,
    ]
    assert coordinator.current is published[-1]


def test_runtime_coordinator_preserves_explicit_execution_device() -> None:
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    original = _launch_spec(TEST_ACTIVE_MODEL_ID)
    spec = AssistantRuntimeLaunchSpec(
        backend=original.backend,
        requested_backend_id=original.requested_backend_id,
        requested_model_id=original.requested_model_id,
        model_id=original.model_id,
        outcome=original.outcome,
        selection_detail="Local runtime ready on CPU.",
        settings=original.settings,
        device_fallback_reason="CUDA is not available",
    )

    coordinator.begin_loading(spec, activation_id=17)
    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode=spec.backend_mode,
            model_id=spec.model_id,
            activation_id=17,
        )
    )

    assert coordinator.current.execution_device == spec.execution_device
    assert coordinator.current.device_fallback_reason == "CUDA is not available"


def test_runtime_coordinator_owns_preflight_failure_copy():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)

    coordinator.mark_unavailable("  missing   model cache ")

    assert coordinator.current.phase is AssistantRuntimePhase.FAILED
    assert coordinator.current.error == "missing model cache"
    assert coordinator.current.initialized is False


def test_runtime_coordinator_rejects_untyped_payload_without_losing_truth():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    trusted = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        model_id="trusted-model",
    )
    assert coordinator.accept_worker_snapshot(trusted) is True

    accepted = coordinator.accept_worker_snapshot(object())

    assert accepted is False
    assert coordinator.current is trusted
    assert published == [trusted]


def test_runtime_coordinator_rejects_inconsistent_typed_snapshot():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    invalid_ready = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=False,
        backend_mode="local",
        model_id="model",
    )

    accepted = coordinator.accept_worker_snapshot(invalid_ready)

    assert accepted is False
    assert coordinator.current.phase is AssistantRuntimePhase.IDLE
    assert published == []


def test_runtime_coordinator_rejects_ready_snapshot_from_previous_model_request():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    stale_model = TEST_ACTIVE_MODEL_ID
    target_model = TEST_TARGET_MODEL_ID
    assert stale_model != target_model
    target_spec = _launch_spec(target_model)

    coordinator.begin_loading(target_spec)
    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=stale_model,
        )
    )

    assert coordinator.current.phase is AssistantRuntimePhase.LOADING
    assert coordinator.current.model_id == target_model
    assert len(published) == 1

    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=target_model,
        )
    )

    assert coordinator.current.phase is AssistantRuntimePhase.READY
    assert coordinator.current.model_id == target_model
    assert coordinator.current.requested_model_id == target_model
    assert coordinator.current.selection_outcome is target_spec.outcome


def test_runtime_coordinator_rejects_stale_same_model_activation_outcome() -> None:
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    spec = _launch_spec(TEST_ACTIVE_MODEL_ID)

    coordinator.begin_loading(spec, activation_id=41)
    coordinator.begin_loading(spec, activation_id=42)
    coordinator.accept_worker_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode=spec.backend_mode,
            model_id=spec.model_id,
            activation_id=41,
        )
    )

    assert coordinator.current.phase is AssistantRuntimePhase.LOADING
    assert coordinator.current.activation_id == 42
    assert coordinator.expected_activation_id == 42

    accepted_terminal = coordinator.accept_worker_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode=spec.backend_mode,
            model_id=spec.model_id,
            activation_id=42,
        )
    )

    assert accepted_terminal is True
    assert coordinator.current.phase is AssistantRuntimePhase.READY
    assert coordinator.expected_activation_id is None


def test_failed_switch_retains_the_last_ready_runtime_identity() -> None:
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    active = _launch_spec(TEST_ACTIVE_MODEL_ID)
    target = _launch_spec(TEST_TARGET_MODEL_ID)
    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode=active.backend_mode,
            model_id=active.model_id,
        )
    )

    coordinator.begin_loading(target, activation_id=73)
    accepted = coordinator.accept_worker_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            backend_mode=target.backend_mode,
            model_id=target.model_id,
            error="model switch failed",
            activation_id=73,
        )
    )

    assert accepted is True
    assert coordinator.current.phase is AssistantRuntimePhase.FAILED
    assert coordinator.current.initialized is True
    assert coordinator.current.backend_mode == active.backend_mode
    assert coordinator.current.model_id == active.model_id
    assert coordinator.current.requested_model_id == target.requested_model_id
    assert coordinator.current.selection_outcome is target.outcome
    assert coordinator.current.selection_detail == target.selection_detail
    assert coordinator.current.activation_id == 73
    assert coordinator.current.error == "model switch failed"
    assert coordinator.expected_activation_id is None


def test_runtime_coordinator_rejects_untagged_terminal_during_tagged_activation() -> (
    None
):
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    spec = _launch_spec(TEST_ACTIVE_MODEL_ID)

    coordinator.begin_loading(spec, activation_id=42)
    accepted = coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode=spec.backend_mode,
            model_id=spec.model_id,
        )
    )

    assert accepted is False
    assert coordinator.current.phase is AssistantRuntimePhase.LOADING
    assert coordinator.expected_activation_id == 42


def test_runtime_coordinator_timeout_cannot_fail_a_newer_activation() -> None:
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    first = _launch_spec(TEST_ACTIVE_MODEL_ID)
    second = _launch_spec(TEST_TARGET_MODEL_ID)

    coordinator.begin_loading(first, activation_id=7)
    coordinator.begin_loading(second, activation_id=8)

    assert coordinator.fail_activation(7, "activation timed out") is False
    assert coordinator.current.phase is AssistantRuntimePhase.LOADING
    assert coordinator.current.model_id == second.model_id

    assert coordinator.fail_activation(8, "activation timed out") is True
    assert coordinator.current.phase is AssistantRuntimePhase.FAILED
    assert coordinator.current.error == "activation timed out"
    assert coordinator.expected_activation_id is None
