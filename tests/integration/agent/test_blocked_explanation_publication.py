"""Low-mock gate for publication-backed blocked workflow explanations."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest

from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import CommandName, get_application_service
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
    EpochStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.response_presentation import AssistantResponsePresentation
from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.worker import AgentWorker


class _NoopWorker(AgentWorker):
    """Keep the worker lifecycle real while suppressing model initialization."""

    def __init__(self) -> None:
        super().__init__()
        self.generation_requests: list[AssistantGenerationRequest] = []

    def initialize_agent(self) -> None:
        return None

    def generate_from_messages(self, request: AssistantGenerationRequest) -> None:
        self.generation_requests.append(request)

    def reinitialize_agent(self, _mode: str) -> None:
        return None

    def cancel_generation(self, request: AssistantGenerationStopRequest) -> None:
        self.generation_stop_finished.emit(
            AssistantGenerationStopAcknowledgement(
                generation_id=request.generation_id,
                stopped=True,
            )
        )

    def shutdown(self, wait_ms: int = 0) -> bool:
        del wait_ms
        self.shutdown_finished.emit(True)
        return True


def _raw_loaded_state() -> ApplicationStateSnapshot:
    return replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(
            loaded=True,
            count=1,
            files=["/data/subject.fif"],
            formats=[".fif"],
        ),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )


def _preprocessed_state() -> ApplicationStateSnapshot:
    return replace(
        _raw_loaded_state(),
        pipeline_stage="preprocessed",
        preprocessed=PreprocessedStateSnapshot(
            available=True,
            count=1,
            files=["/data/subject.fif"],
            operations=["bandpass"],
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )


def _epoch_state_without_split_or_training_config() -> ApplicationStateSnapshot:
    return replace(
        _preprocessed_state(),
        pipeline_stage="epoch_ready",
        epoch=EpochStateSnapshot(
            available=True,
            exists=True,
            epoch_count=12,
            n_channels=2,
            n_times=128,
            sfreq=128.0,
            event_names=["left", "right"],
            event_ids={"left": 1, "right": 2},
            channel_names=["C3", "C4"],
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
            has_epoch_data=True,
        ),
    )


@pytest.mark.usefixtures("qtbot")
def test_controller_explains_blocked_steps_from_real_atomic_publications(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    service = get_application_service(study)
    initial_publication = service.get_view_publication()
    view_store = ApplicationViewStore(
        initial_publication.state,
        initial_publication.training_boundary,
    )
    monkeypatch.setattr(service, "get_view_publication", view_store.read)
    with patch(
        "XBrainLab.llm.agent.controller.AgentWorker",
        _NoopWorker,
    ):
        controller = LLMController(study)
    generation_requests: list[AssistantGenerationRequest] = []
    presentations: list[AssistantResponsePresentation] = []

    worker = controller.worker
    assert isinstance(worker, _NoopWorker)

    def record_generation(request: object) -> None:
        assert isinstance(request, AssistantGenerationRequest)
        generation_requests.append(request)

    controller.sig_generate.connect(record_generation)
    controller.response_presentation_ready.connect(presentations.append)

    cases = (
        (
            _raw_loaded_state(),
            "Why can't I create epochs?",
            CommandName.CREATE_EPOCH,
            "Preprocess data before creating EEG epochs.",
        ),
        (
            _preprocessed_state(),
            "Why can't I build the training dataset?",
            CommandName.CONFIGURE_DATASET_SPLIT,
            "Create EEG epochs before building the training dataset.",
        ),
        (
            _epoch_state_without_split_or_training_config(),
            "為什麼現在不能訓練?",
            CommandName.TRAIN,
            "Save a valid data splitting specification before training.",
        ),
        (
            ApplicationStateSnapshot.empty(),
            "Why can't I evaluate the model?",
            CommandName.EVALUATE,
            "Create a training plan before evaluating results.",
        ),
        (
            ApplicationStateSnapshot.empty(),
            "為什麼不能查看顯著性?",
            CommandName.SALIENCY,
            "Create EEG epochs, build the training dataset, or select a model "
            "and training settings before querying saliency readiness.",
        ),
        (
            ApplicationStateSnapshot.empty(),
            "Why is visualization blocked?",
            CommandName.VISUALIZE,
            "Create EEG epochs, complete training, or configure saliency before "
            "opening visualization views.",
        ),
    )

    try:
        for sequence, (state, text, command, reason) in enumerate(cases, start=1):
            publication = view_store.publish(
                state,
                initial_publication.training_boundary,
            )
            capability = publication.effective_capabilities.get(command)
            assert capability.enabled is False
            assert reason in capability.reasons

            response_count = len(presentations)
            controller.handle_user_turn(
                AssistantTurnRequest.single_action(
                    correlation=AssistantTurnCorrelation(
                        generation=sequence,
                        turn_id=sequence,
                    ),
                    text=text,
                )
            )

            assert len(presentations) == response_count + 1
            assert reason in presentations[-1].text
            assert controller.is_processing is False
            assert generation_requests == []
            assert worker.generation_requests == []
            assert controller._tool_attempt_session.execution_count == 0
    finally:
        close_controller_and_wait(controller, qtbot)
