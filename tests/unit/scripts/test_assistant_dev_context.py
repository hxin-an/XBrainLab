"""Research-only nuisance control must not replace host publication truth."""

import json
from dataclasses import replace

from scripts.dev.assistant_dev_context import DevContextAssembler
from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import TrainingStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.tools.tool_registry import ToolRegistry


class PublicationRuntime:
    def __init__(self, publication):
        self.publication = publication

    def get_view_publication(self):
        return self.publication


def test_nuisance_control_changes_model_card_not_host_freshness():
    study = Study()
    service = get_application_service(study)
    try:
        original = service.get_view_publication()
        runtime = PublicationRuntime(replace(original, generation=81))
        assembler = DevContextAssembler(
            ToolRegistry(), study, application_runtime=runtime
        )
        first = assembler.get_messages([{"role": "user", "content": "Open import."}])
        assert assembler.latest_tool_publication.backend_generation == 81
        runtime.publication = replace(original, generation=143)
        second = assembler.get_messages([{"role": "user", "content": "Open import."}])
        assert first == second
        assert assembler.latest_tool_publication.backend_generation == 143
        context = json.loads(second[1]["content"])
        assert "backend_generation" not in context["items"][0]["data"]
        assert context["trust"] == "untrusted"
        assert runtime.publication.generation == 143
        normal = ContextAssembler(ToolRegistry(), study, application_runtime=runtime)
        normal_card = json.loads(normal.get_messages([])[1]["content"])["items"][0][
            "data"
        ]
        assert normal_card["backend_generation"] == 143
    finally:
        service.close()


def test_anonymous_progress_aliases_preserve_distinctions_and_task_values():
    study = Study()
    service = get_application_service(study)
    try:
        state = replace(
            service.get_state(),
            pipeline_stage="training",
            training=TrainingStateSnapshot(
                is_running=True,
                model_name="EEGNet",
                progress_message="subject [SUBJECT_REF:aaaaaaaaaaaa] epoch 2/10",
            ),
        )
        publication = ApplicationViewPublication(
            generation=12, state=state, capabilities=build_capability_policy(state)
        )
        args = {
            "workflow_stage": "training",
            "backend_generation": 12,
            "state_reliable": True,
        }
        first = DevContextAssembler._state_card_payload(publication, **args)
        second_state = replace(
            state,
            training=replace(
                state.training,
                progress_message="subject [SUBJECT_REF:bbbbbbbbbbbb] epoch 2/10",
            ),
        )
        second = DevContextAssembler._state_card_payload(
            replace(publication, state=second_state), **args
        )
        assert first == second
        assert first["running"] is True
        assert first["model"] == "EEGNet"
        assert "epoch 2/10" in first["progress"]
        assert "aaaaaaaaaaaa" in state.training.progress_message
        assert "backend_generation" not in first
        third = DevContextAssembler._state_card_payload(
            replace(
                publication,
                state=replace(
                    state,
                    training=replace(
                        state.training,
                        progress_message="subject [SUBJECT_REF:aaaaaaaaaaaa] epoch 3/10",
                    ),
                ),
            ),
            **args,
        )
        assert first != third  # Never freeze genuine progress to a fabricated value.
        repeated = replace(
            state,
            training=replace(
                state.training,
                progress_message="[SUBJECT_REF:aaaaaaaaaaaa] [SUBJECT_REF:bbbbbbbbbbbb] [SUBJECT_REF:aaaaaaaaaaaa]",
            ),
        )
        card = DevContextAssembler._state_card_payload(
            replace(publication, state=repeated), **args
        )
        assert (
            card["progress"]
            == "[SUBJECT_REF:000000000001] [SUBJECT_REF:000000000002] [SUBJECT_REF:000000000001]"
        )
    finally:
        service.close()


def test_unavailable_publication_stays_unavailable():
    assert DevContextAssembler._state_card_payload(
        None, workflow_stage="empty", backend_generation=None, state_reliable=False
    ) == {"workflow_stage": "unavailable", "state_reliable": False}
