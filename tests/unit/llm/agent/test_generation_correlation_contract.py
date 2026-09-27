"""Strict generation-correlation guards for the desktop assistant runtime."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtCore import QObject

from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
)
from XBrainLab.llm.agent.turn_orchestrator import AssistantTurnOrchestrator
from XBrainLab.llm.agent.worker import AgentWorker


def test_worker_exposes_only_correlated_generation_signals() -> None:
    assert "finished" not in AgentWorker.__dict__
    assert "chunk_received" not in AgentWorker.__dict__
    assert "generation_finished" in AgentWorker.__dict__
    assert "generation_chunk_received" in AgentWorker.__dict__
    assert "generation_error" in AgentWorker.__dict__
    assert "generation_dispatch_acknowledged" in AgentWorker.__dict__


def test_generation_dispatch_acknowledgement_is_typed_and_correlated() -> None:
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    assert accepted.generation_id == started.generation_id
    assert accepted.phase is AssistantGenerationDispatchPhase.ACCEPTED
    assert started.phase is AssistantGenerationDispatchPhase.STARTED


def test_host_turn_delivery_acknowledgement_is_typed_and_correlated() -> None:
    correlation = AssistantTurnCorrelation(generation=7, turn_id=13)

    accepted = AssistantTurnDeliveryAcknowledgement(
        correlation=correlation,
        phase=AssistantTurnDeliveryPhase.ACCEPTED,
    )
    failed = AssistantTurnDeliveryAcknowledgement(
        correlation=correlation,
        phase=AssistantTurnDeliveryPhase.ERROR,
        message="controller setup failed",
    )

    assert accepted.correlation == failed.correlation
    assert accepted.phase is AssistantTurnDeliveryPhase.ACCEPTED
    assert failed.phase is AssistantTurnDeliveryPhase.ERROR
    assert failed.message == "controller setup failed"


def test_host_turn_delivery_error_redacts_private_exception_context() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"

    failed = AssistantTurnDeliveryAcknowledgement(
        correlation=AssistantTurnCorrelation(generation=7, turn_id=13),
        phase=AssistantTurnDeliveryPhase.ERROR,
        message=f"Controller failed for {private_path}; subject_id=Alice-Smith.",
    )

    assert private_path not in failed.message
    assert "subject-17" not in failed.message
    assert "Alice-Smith" not in failed.message
    assert "events.tsv" in failed.message
    assert "[REDACTED_PATH]" in failed.message
    assert "[SUBJECT_REF:" in failed.message


def test_controller_has_a_distinct_worker_dispatch_acknowledgement_handler() -> None:
    parameters = list(
        inspect.signature(
            LLMController._on_generation_dispatch_acknowledged
        ).parameters.values()
    )
    assert [parameter.name for parameter in parameters] == ["self", "payload"]
    assert parameters[1].default is inspect.Parameter.empty


def test_dispatch_acknowledgements_are_ordered_exactly_once_and_correlated() -> None:
    controller = LLMController.__new__(LLMController)
    QObject.__init__(controller)
    controller._turn_orchestrator = AssistantTurnOrchestrator()
    controller._turn_orchestrator.active_generation_id = 41
    controller._turn_orchestrator.dispatch_phase = None
    controller._turn_orchestrator.cancelled = False
    controller._closing = False
    controller._closed = False
    controller.generation_event = MagicMock()
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=41,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)
    controller._on_generation_dispatch_acknowledged(started)

    assert (
        controller._turn_orchestrator.dispatch_phase
        is AssistantGenerationDispatchPhase.STARTED
    )
    controller.generation_event.emit.assert_called_once_with(
        AssistantGenerationEvent(
            generation_id=41,
            phase=AssistantGenerationEventPhase.STARTED,
        )
    )

    controller._turn_orchestrator.active_generation_id = 42
    controller._turn_orchestrator.dispatch_phase = None
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)

    assert controller._turn_orchestrator.dispatch_phase is None
    assert controller.generation_event.emit.call_count == 1


def test_cancelled_or_closing_turn_ignores_late_dispatch_acknowledgements() -> None:
    controller = LLMController.__new__(LLMController)
    QObject.__init__(controller)
    controller._turn_orchestrator = AssistantTurnOrchestrator()
    controller._turn_orchestrator.active_generation_id = 51
    controller._turn_orchestrator.dispatch_phase = None
    controller._turn_orchestrator.cancelled = True
    controller._closing = False
    controller._closed = False
    controller.generation_event = MagicMock()
    accepted = AssistantGenerationDispatchAcknowledgement(
        generation_id=51,
        phase=AssistantGenerationDispatchPhase.ACCEPTED,
    )
    started = AssistantGenerationDispatchAcknowledgement(
        generation_id=51,
        phase=AssistantGenerationDispatchPhase.STARTED,
    )

    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)
    controller._turn_orchestrator.cancelled = False
    controller._closing = True
    controller._on_generation_dispatch_acknowledged(accepted)
    controller._on_generation_dispatch_acknowledged(started)

    assert controller._turn_orchestrator.dispatch_phase is None
    controller.generation_event.emit.assert_not_called()


def test_generation_stop_channel_is_typed_and_requires_a_request() -> None:
    worker_source = inspect.getsource(AgentWorker)
    assert "generation_stop_finished = pyqtSignal(object)" in worker_source
    assert "generation_stop_finished = pyqtSignal(bool)" not in worker_source

    parameters = list(
        inspect.signature(AgentWorker.cancel_generation).parameters.values()
    )
    assert [parameter.name for parameter in parameters] == ["self", "payload"]
    assert parameters[1].default is inspect.Parameter.empty


def test_controller_generation_callbacks_require_explicit_correlation() -> None:
    for callback_name in (
        "_on_chunk_received",
        "_on_generation_finished",
        "_on_generation_error",
    ):
        parameters = list(
            inspect.signature(getattr(LLMController, callback_name)).parameters.values()
        )[1:]
        assert parameters
        assert all(
            parameter.default is inspect.Parameter.empty for parameter in parameters
        )


def test_runtime_and_generation_errors_have_distinct_handlers() -> None:
    assert hasattr(LLMController, "_on_runtime_error")
    assert hasattr(LLMController, "_on_generation_error")
    assert not hasattr(LLMController, "_on_uncorrelated_worker_error")
    assert not hasattr(LLMController, "_on_worker_error")


def test_product_walkthrough_scripts_avoid_legacy_generation_channels() -> None:
    forbidden = (
        "agent_controller.worker",
        "controller.worker",
        "_active_generation_id",
        "generation_started = pyqtSignal",
        "generation_started.emit(",
        "generation_started.connect(",
    )
    violations: list[str] = []
    for path in Path("scripts/dev").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        violations.extend(f"{path}: {token}" for token in forbidden if token in source)

    assert violations == []
