"""Research-only nuisance control must not replace host publication truth."""

import json
from dataclasses import replace

import pytest

from scripts.dev.assistant_dev_context import DEV_PROMPT_MODEL_IDS, DevContextAssembler
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
            ToolRegistry(),
            study,
            model_id="ibm-granite/granite-4.0-micro",
            application_runtime=runtime,
        )
        history = [{"role": "user", "content": "Open import."}]
        first = assembler.get_messages(history)
        assert assembler.latest_tool_publication.backend_generation == 81
        runtime.publication = replace(original, generation=143)
        second = assembler.get_messages(history)
        assert first == second
        assert assembler.latest_tool_publication.backend_generation == 143
        context = json.loads(second[-1]["content"])
        assert set(context) == {"application_state", "current_user"}
        assert "backend_generation" not in context["application_state"]
        assert context["current_user"] == {"text": "Open import."}
        assert runtime.publication.generation == 143
        normal = ContextAssembler(ToolRegistry(), study, application_runtime=runtime)
        normal_context = json.loads(normal.get_messages(history)[-1]["content"])
        assert normal_context["current_user"] == context["current_user"]
        assert normal_context["application_state"] == {
            **context["application_state"],
            "backend_generation": 143,
        }
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


def real_registry():
    from XBrainLab.llm.tools import get_all_tools

    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    return registry


@pytest.mark.parametrize(
    "model_id",
    [
        "ibm-granite/granite-4.0-micro",
        "ibm-granite/granite-3.3-2b-instruct",
        "microsoft/Phi-4-mini-instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "google/gemma-3-4b-it",
    ],
)
def test_readable_real_tool_contracts_preserve_arguments_and_blockers(model_id):
    registry = real_registry()
    assembler = DevContextAssembler(registry, None, model_id=model_id)
    names = [tool.name for tool in registry.get_all_tools()]
    catalog = assembler._format_tools(
        names, unavailable_actions={"unavailable_action": "No data"}
    )
    for name in names:
        assert f"Action: {name}\n" in catalog
    assert '"name":' not in catalog
    assert "low_freq: required number; unit: Hz" in catalog
    assert "high_freq: required number; unit: Hz" in catalog
    assert "panel_name: required string" in catalog
    assert "view_mode: optional string" in catalog
    assert 'allowed values: "z-score", "min-max"' in catalog
    assert (
        "message: required string; must contain a non-whitespace character" in catalog
    )
    for name in (
        "configure_training",
        "start_training",
        "stop_training",
        "compute_saliency",
    ):
        action = catalog.split(f"Action: {name}\n")[1].split("\n\n")[0]
        assert "parameters must be {}" in action
    assert "Unavailable (not callable):\n- unavailable_action: No data" in catalog
    assert "Action: unavailable_action" not in catalog


@pytest.mark.parametrize("model_id", [None, "granite4", "unknown/model"])
def test_research_prompt_never_falls_back_for_missing_or_unknown_model(model_id):
    with pytest.raises(ValueError, match="DEV prompt model"):
        DevContextAssembler(ToolRegistry(), None, model_id=model_id)


def test_new_schema_constraints_cannot_silently_disappear_from_readable_catalog(
    monkeypatch,
):
    from XBrainLab.llm.tools.definitions.preprocess_def import BaseResampleTool

    monkeypatch.setattr(
        BaseResampleTool,
        "parameters",
        property(
            lambda _: {
                "type": "object",
                "properties": {"rate": {"type": "integer", "minimum": 1}},
                "required": ["rate"],
            }
        ),
    )
    assembler = DevContextAssembler(
        real_registry(), None, model_id="google/gemma-3-4b-it"
    )
    with pytest.raises(ValueError, match=r"Unsupported.*minimum"):
        assembler._format_tools(["resample_data"])


@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
def test_complete_messages_preserve_backend_rag_retry_and_current_request(model_id):
    from XBrainLab.chat_contract import MAX_CHAT_MODEL_REQUEST_UTF8_BYTES
    from XBrainLab.llm.agent.context_encoding import (
        UntrustedContextItem,
        UntrustedContextSource,
        encode_untrusted_context,
    )
    from XBrainLab.llm.agent.prompt_policy import STRICT_TOOL_RESPONSE_PROMPT_POLICY

    study = Study()
    service = get_application_service(study)
    try:
        registry = real_registry()
        runtime = PublicationRuntime(service.get_view_publication())
        normal = ContextAssembler(registry, study, application_runtime=runtime)
        research = DevContextAssembler(
            registry, study, model_id=model_id, application_runtime=runtime
        )
        examples = [
            UntrustedContextItem(
                item_type="rag_example",
                source=UntrustedContextSource(
                    kind="xbrainlab_bundled_gold_set", id=f"reference-{index}"
                ),
                data={
                    "input": f"Explain EEG preprocessing {index}.",
                    "expected_proposal": {
                        "tool_name": "respond_to_user",
                        "parameters": {"message": f"Explanation {index}."},
                    },
                },
            )
            for index in range(3)
        ]
        reference = encode_untrusted_context(examples)
        normal.add_context(reference)
        research.add_context(reference)
        current = {"role": "user", "content": "Open Import EEG Data."}
        history = [{"role": "user", "content": "HIDDEN OLD REQUEST"}, current]
        baseline = normal.get_generation_request(history).to_model_messages()
        actual = research.get_generation_request(history).to_model_messages()
        assert len(actual) == len(baseline) == 3
        assert (
            actual[1] == baseline[1]
        )  # All references, order, bytes and trust boundary.
        assert research.latest_tool_publication == normal.latest_tool_publication
        expected_request = json.loads(baseline[-1]["content"])
        expected_request["application_state"].pop("backend_generation")
        assert json.loads(actual[-1]["content"]) == expected_request
        assert "HIDDEN OLD REQUEST" not in json.dumps(actual)
        assert research.get_messages([current]) == actual
        assert "Action: import_eeg_data\n" in actual[0]["content"]
        assert "Action: apply_bandpass_filter\n" not in actual[0]["content"]
        assert "- apply_bandpass_filter:" in actual[0]["content"]
        assert '"tool_name"' in actual[0]["content"]
        policy = " ".join(actual[0]["content"].split())
        assert "Information or explanation requests and prohibitions" in policy
        assert "Polite requests to perform an action" in policy
        assert "even when phrased as questions, are action requests" in policy
        assert "A question, explanation request or prohibition" not in policy
        assert "Use it for questions," not in policy
        assert "For questions, prohibitions," not in policy
        assert (
            research._serialized_utf8_size(actual) <= MAX_CHAT_MODEL_REQUEST_UTF8_BYTES
        )
        repaired = research.get_messages(history, format_recovery=True)
        assert repaired[1:] == actual[1:]
        assert (
            repaired[0]["content"]
            == actual[0]["content"]
            + "\n"
            + STRICT_TOOL_RESPONSE_PROMPT_POLICY.recovery_instructions()
        )
        assert STRICT_TOOL_RESPONSE_PROMPT_POLICY.max_format_recovery_attempts == 1
        # The product default hook still emits its exact existing policy text.
        assert (
            normal._decision_instructions()
            == STRICT_TOOL_RESPONSE_PROMPT_POLICY.decision_instructions()
        )
    finally:
        service.close()
