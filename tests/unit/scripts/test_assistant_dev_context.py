"""Research-only nuisance control must not replace host publication truth."""

import hashlib
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

ROUND1_MODELS = (
    "microsoft/Phi-4-mini-instruct",
    "google/gemma-3-4b-it",
    "ibm-granite/granite-3.3-2b-instruct",
)
ROUND2_MODELS = (
    "ibm-granite/granite-4.0-micro",
    "meta-llama/Llama-3.2-3B-Instruct",
)
ILLUSTRATED_MODELS = (
    "microsoft/Phi-4-mini-instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "ibm-granite/granite-3.3-2b-instruct",
)


class PublicationRuntime:
    def __init__(self, publication):
        self.publication = publication

    def get_view_publication(self):
        return self.publication


@pytest.mark.parametrize(
    ("model_id", "expected_sha256"),
    [
        # Full initial-state messages from the selected historical assemblers:
        # G4 d2e679c2, Llama e6d10a9f, Gemma 78110571, Phi/G33 51dd709b.
        (
            "ibm-granite/granite-4.0-micro",
            "76bcdb364340eaa2c2a2d356d9cf53025c7b45e98bb012f03c169d287e55802f",  # pragma: allowlist secret
        ),
        (
            "meta-llama/Llama-3.2-3B-Instruct",
            "922287d0361bdf7da107892e45ec3aef97495b5b7d0222854cb8604a4da0cd42",  # pragma: allowlist secret
        ),
        (
            "google/gemma-3-4b-it",
            "ac431597bda3833572737ca82cab9f53b91d53378dc5f65eaf0e751d61d69ef8",  # pragma: allowlist secret
        ),
        (
            "microsoft/Phi-4-mini-instruct",
            "d86f23255cee1085963e560928456df8f6ad7101a9633ff0f7f9270abb4784e4",  # pragma: allowlist secret
        ),
        (
            "ibm-granite/granite-3.3-2b-instruct",
            "8c183a0640eda382c10b12e6bd20e71776accdee3fb7cc72b11d2f2a21092e27",  # pragma: allowlist secret
        ),
    ],
)
def test_selected_profiles_freeze_historical_complete_input(model_id, expected_sha256):
    """A profile change requires a new research freeze, not silent retuning."""
    study = Study()
    service = get_application_service(study)
    try:
        assembler = DevContextAssembler(
            real_registry(), study, model_id=model_id, application_runtime=service
        )
        messages = assembler.get_messages(
            [{"role": "user", "content": "Open Import EEG Data."}]
        )
        serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
        assert hashlib.sha256(serialized).hexdigest() == expected_sha256
    finally:
        service.close()


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


def test_catalog_ablation_preserves_rag_state_publication_and_illustrations():
    """More definitions must never publish more executable actions."""
    study = Study()
    service = get_application_service(study)
    try:
        assemblers = [
            DevContextAssembler(
                real_registry(),
                study,
                model_id="microsoft/Phi-4-mini-instruct",
                application_runtime=service,
                tool_filter_enabled=enabled,
            )
            for enabled in (True, False)
        ]
        request = [{"role": "user", "content": "Open Import EEG Data."}]
        baseline, expanded = [item.get_messages(request) for item in assemblers]
        assert baseline[1:] == expanded[1:]
        assert (
            assemblers[0].latest_tool_publication
            == assemblers[1].latest_tool_publication
        )
        assert (
            assemblers[0].rag_allowed_tool_names()
            == assemblers[1].rag_allowed_tool_names()
        )
        assert (
            "apply_bandpass_filter"
            not in assemblers[1].latest_tool_publication.tool_names
        )
        assert assemblers[1].latest_tool_publication.blocked_reason(
            "apply_bandpass_filter"
        )
        assert '"name": "apply_bandpass_filter"' not in baseline[0]["content"]
        assert '"name": "apply_bandpass_filter"' in expanded[0]["content"]
        assert (
            baseline[0]["content"]
            .split("Complete output illustrations:")[1]
            .split("Only the listed workflow actions")[0]
            == expanded[0]["content"]
            .split("Complete output illustrations:")[1]
            .split("Catalog definitions do not grant")[0]
        )
        assert "Callable action contract:" not in expanded[0]["content"]
        assert "Only the listed workflow actions" not in expanded[0]["content"]
        assert (
            assemblers[0]._decision_instructions()
            == assemblers[1]._decision_instructions()
        )
    finally:
        service.close()


@pytest.mark.parametrize("names", [[], ["apply_bandpass_filter"], ["compute_saliency"]])
def test_catalog_ablation_keeps_state_selected_illustrations(names):
    baseline = DevContextAssembler(
        real_registry(), None, model_id="microsoft/Phi-4-mini-instruct"
    )
    expanded = DevContextAssembler(
        real_registry(),
        None,
        model_id="microsoft/Phi-4-mini-instruct",
        tool_filter_enabled=False,
    )
    marker = "Complete output illustrations:"
    assert (
        baseline._format_tools(names).split(marker)[1]
        == expanded._format_tools(names).split(marker)[1]
    )


def real_registry():
    from XBrainLab.llm.tools import get_all_tools

    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    return registry


@pytest.mark.parametrize(
    "model_id",
    ROUND2_MODELS,
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


@pytest.mark.parametrize("model_id", ROUND1_MODELS)
def test_round1_models_reuse_original_policy_and_lossless_json_catalog(model_id):
    registry = real_registry()
    baseline = ContextAssembler(registry, None)
    candidate = DevContextAssembler(registry, None, model_id=model_id)
    names = [tool.name for tool in registry.get_all_tools()]
    blockers = {"unavailable_action": "No data"}
    assert candidate._decision_instructions().startswith(
        baseline._decision_instructions()
    )
    assert candidate._TOOL_BLOCK_TEMPLATE == baseline._TOOL_BLOCK_TEMPLATE
    catalog = candidate._format_tools(names, unavailable_actions=blockers)
    assert catalog.split("\n\nComplete output illustrations:")[0].split(
        "\n\nOutput decision:\n"
    )[0] == (baseline._format_tools(names, unavailable_actions=blockers))


@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
@pytest.mark.parametrize(
    "names",
    [
        [],
        ["import_eeg_data"],
        ["switch_panel"],
        ["start_training", "switch_panel"],
        ["apply_bandpass_filter"],
        ["apply_bandpass_filter", "select_channels", "switch_panel"],
        ["create_epochs", "switch_panel"],
        ["compute_saliency"],
        None,  # Every registered contract; exercises all argument examples.
    ],
)
def test_output_illustrations_are_complete_legal_and_only_callable(model_id, names):
    from XBrainLab.llm.agent.parser import CommandParser
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator

    registry = real_registry()
    if names is None:
        names = [tool.name for tool in registry.get_all_tools()]
    assembler = DevContextAssembler(registry, None, model_id=model_id)
    catalog = assembler._format_tools(names)
    if model_id not in ILLUSTRATED_MODELS:
        assert "Complete output illustrations:" not in catalog
        assert "Which operation would you like help with?" not in catalog
        return
    examples = catalog.split("Complete output illustrations:\n", 1)[1]
    proposals = [
        json.loads(line) for line in examples.splitlines() if line.startswith("{")
    ]
    assert 1 <= len(proposals) <= 5
    assert any(proposal["tool_name"] == "respond_to_user" for proposal in proposals)
    validator = ToolSchemaValidator(
        {tool.name: tool.parameters for tool in registry.get_all_tools()}
    )
    for proposal in proposals:
        assert (
            CommandParser.parse_product(json.dumps(proposal)).proposal_dict()
            == proposal
        )
        if proposal["tool_name"] == "respond_to_user":
            assert set(proposal["parameters"]) == {"message"}
        else:
            assert proposal["tool_name"] in names
            assert validator.validate(
                proposal["tool_name"], proposal["parameters"]
            ).is_valid
            assert "message" not in proposal["parameters"]
    assert "not values or permission for this request" in examples


@pytest.mark.parametrize("model_id", DEV_PROMPT_MODEL_IDS)
def test_model_emphasis_uses_selected_round_baseline_without_duplication(model_id):
    from scripts.dev.assistant_dev_context import _MODEL_EMPHASIS

    assembler = DevContextAssembler(real_registry(), None, model_id=model_id)
    messages = assembler.get_messages(
        [{"role": "user", "content": "Explain EEG preprocessing."}]
    )
    system = messages[0]["content"]
    emphasis = _MODEL_EMPHASIS[model_id]
    catalog = assembler._format_tools(assembler.latest_tool_publication.tool_names)
    if model_id in (
        "ibm-granite/granite-4.0-micro",
        "microsoft/Phi-4-mini-instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
    ):
        assert system.count(emphasis) == 1
        assert assembler._decision_instructions().endswith(
            "Remember: " + emphasis + "\n"
        )
        assert emphasis not in catalog
    else:
        assert emphasis not in assembler._decision_instructions()
        assert system.count(emphasis) == 1
        assert catalog.rstrip().endswith("Output decision:\n" + emphasis)
    assert catalog in system
    assert "DEV-" not in system and "candidate4" not in system


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
        real_registry(), None, model_id="ibm-granite/granite-4.0-micro"
    )
    with pytest.raises(ValueError, match=r"Unsupported.*minimum"):
        assembler._format_tools(["resample_data"])


def test_selected_granite4_preserves_round2_reminder_and_unannotated_fields():
    registry = real_registry()
    schemas = {
        tool.name: json.dumps(tool.parameters, sort_keys=True)
        for tool in registry.get_all_tools()
    }
    assembler = DevContextAssembler(
        registry, None, model_id="ibm-granite/granite-4.0-micro"
    )
    catalog = assembler._format_tools(["apply_bandpass_filter", "switch_panel"])
    expected = (
        "Check each required value against the current request. A partly supplied "
        "operation is still incomplete: ask for the missing value, without borrowing "
        "one from a reference. When every required value is supplied, use the tool."
    )
    assert assembler._decision_instructions().endswith("Remember: " + expected + "\n")
    assert "value must be specified in current_user.text" not in catalog
    assert "A purpose or desired effect is not a selected value" not in catalog
    assert expected not in catalog
    assert "Output decision:" not in catalog
    assert schemas == {
        tool.name: json.dumps(tool.parameters, sort_keys=True)
        for tool in registry.get_all_tools()
    }


def test_selected_gemma_preserves_exact_round4_emphasis():
    assembler = DevContextAssembler(
        real_registry(), None, model_id="google/gemma-3-4b-it"
    )
    catalog = assembler._format_tools(
        ["import_eeg_data"], unavailable_actions={"start_training": "No dataset"}
    )
    emphasis = catalog.split("Output decision:\n")[1]
    assert emphasis == (
        "Select one decision, not a conversational promise. If the user requests "
        "one available action and supplies its required values, output that "
        "action's JSON object. Do not ask again for values already supplied. "
        "Dialog-opening tools always take empty parameters, even when form "
        "choices are mentioned; those choices are made in the dialog. A reply promising "
        "to open it does not execute it. For information or explanation requests, "
        "prohibitions, unavailable actions or missing required values, output "
        "respond_to_user with your reply in parameters.message instead. "
        "Return only the single complete JSON object, not a bare message."
    )
    assert "No dataset" in catalog


def test_phi_direct_examples_contrast_complete_and_missing_values():
    assembler = DevContextAssembler(
        real_registry(), None, model_id="microsoft/Phi-4-mini-instruct"
    )
    examples = assembler._output_illustrations(
        ["apply_bandpass_filter", "switch_panel", "select_channels"]
    )
    assert "Example input (complete action):" in examples
    assert "Example input (missing required value):" in examples
    proposals = [
        json.loads(line) for line in examples.splitlines() if line.startswith("{")
    ]
    assert any(p["tool_name"] == "apply_bandpass_filter" for p in proposals)
    assert not any(p["tool_name"] == "switch_panel" for p in proposals)
    assert "apply_bandpass_filter" not in assembler._output_illustrations(
        ["switch_panel"]
    )


@pytest.mark.parametrize(
    "action", ["create_epochs", "start_training", "compute_saliency"]
)
def test_selected_llama_preserves_round3_generic_output_examples(action):
    assembler = DevContextAssembler(
        real_registry(), None, model_id="meta-llama/Llama-3.2-3B-Instruct"
    )
    examples = assembler._output_illustrations([action, "switch_panel"])
    assert "Example input" not in examples
    assert "Which operation would you like help with?" in examples
    proposals = [
        json.loads(line) for line in examples.splitlines() if line.startswith("{")
    ]
    assert proposals == [
        {"tool_name": action, "parameters": {}},
        {"tool_name": "switch_panel", "parameters": {"panel_name": "dataset"}},
        {
            "tool_name": "respond_to_user",
            "parameters": {"message": "Which operation would you like help with?"},
        },
    ]


def test_granite33_examples_include_action_prohibition_information_and_missing():
    assembler = DevContextAssembler(
        real_registry(), None, model_id="ibm-granite/granite-3.3-2b-instruct"
    )
    examples = assembler._output_illustrations(["apply_bandpass_filter"])
    for kind in (
        "complete action",
        "prohibition",
        "information only",
        "missing required value",
    ):
        assert f"Example input ({kind}):" in examples
    proposals = [
        json.loads(line) for line in examples.splitlines() if line.startswith("{")
    ]
    assert len(proposals) == 4
    assert [p["tool_name"] for p in proposals] == [
        "apply_bandpass_filter",
        "respond_to_user",
        "respond_to_user",
        "respond_to_user",
    ]
    assert "apply_bandpass_filter" not in assembler._output_illustrations([])


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
        catalog = research._format_tools(
            research.latest_tool_publication.tool_names,
            unavailable_actions=dict(research.latest_tool_publication.blocked_reasons),
        )
        assert catalog in actual[0]["content"]
        assert "import_eeg_data" in research.latest_tool_publication.tool_names
        assert (
            "apply_bandpass_filter" not in research.latest_tool_publication.tool_names
        )
        assert research.latest_tool_publication.blocked_reason("apply_bandpass_filter")
        assert '"tool_name"' in actual[0]["content"]
        policy = " ".join(actual[0]["content"].split())
        if model_id in ROUND2_MODELS:
            assert "Information or explanation requests and prohibitions" in policy
            assert "Polite requests to perform an action" in policy
            assert "even when phrased as questions, are action requests" in policy
        else:
            assert normal._decision_instructions() in actual[0]["content"]
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
