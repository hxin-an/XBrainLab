"""Tests for the single assistant runtime presentation owner."""

from dataclasses import dataclass

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
)
from XBrainLab.ui.components.assistant_runtime_coordinator import (
    AssistantRuntimeCoordinator,
)


@dataclass(frozen=True)
class _ActivationTransition(AssistantRuntimeSnapshot):
    activation_id: int = 0


def _launch_spec(model_id: str) -> AssistantRuntimeLaunchSpec:
    config = LLMConfig(model_name=model_id)
    config.local_backend_ready = lambda candidate=None: (  # type: ignore[method-assign]
        candidate == model_id
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: "Local runtime ready."
    )
    resolution = AssistantRuntimeLaunchResolver().resolve(config)
    assert resolution.launch_spec is not None
    return resolution.launch_spec


def test_runtime_coordinator_serializes_preflight_and_worker_transitions():
    published: list[AssistantRuntimeSnapshot] = []
    coordinator = AssistantRuntimeCoordinator(published.append)
    spec = _launch_spec(LLMConfig.default_local_model_id())

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
    stale_model = LLMConfig.default_local_model_id()
    target_model = LLMConfig.fallback_local_model_id()
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
    spec = _launch_spec(LLMConfig.default_local_model_id())

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
    active = _launch_spec(LLMConfig.default_local_model_id())
    target = _launch_spec(LLMConfig.fallback_local_model_id())
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
    spec = _launch_spec(LLMConfig.default_local_model_id())

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
    first = _launch_spec(LLMConfig.default_local_model_id())
    second = _launch_spec(LLMConfig.fallback_local_model_id())

    coordinator.begin_loading(first, activation_id=7)
    coordinator.begin_loading(second, activation_id=8)

    assert coordinator.fail_activation(7, "activation timed out") is False
    assert coordinator.current.phase is AssistantRuntimePhase.LOADING
    assert coordinator.current.model_id == second.model_id

    assert coordinator.fail_activation(8, "activation timed out") is True
    assert coordinator.current.phase is AssistantRuntimePhase.FAILED
    assert coordinator.current.error == "activation timed out"
    assert coordinator.expected_activation_id is None
