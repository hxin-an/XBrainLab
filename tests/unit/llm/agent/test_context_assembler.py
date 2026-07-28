import json
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application import Command, CommandResult
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.decision_context import build_workflow_decision_context
from XBrainLab.llm.agent.turn import AssistantResponseContract, AssistantTurnScope
from XBrainLab.llm.pipeline_state import STAGE_CONFIG, PipelineStage
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.tool_registry import ToolRegistry


def test_generation_request_marks_concept_question_as_natural_language():
    assembler = ContextAssembler(ToolRegistry(), Study())

    request = assembler.get_generation_request(
        [{"role": "user", "content": "What is an EEG epoch?"}]
    )

    assert request.response_contract is AssistantResponseContract.NATURAL_LANGUAGE
    system_prompt = " ".join(request.to_model_messages()[0]["content"].split())
    assert "Do not output JSON" in system_prompt


def test_blocked_explanation_uses_publication_but_publishes_no_actions() -> None:
    state = _state(
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(loaded=True, count=1),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )
    publication = ApplicationViewPublication(
        generation=81,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication)
    registry = ToolRegistry()
    registry.register(_NamedTool("epoch_data"))
    registry.register(_NamedTool("scan_source"))
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=runtime,
    )

    request = assembler.get_generation_request(
        [{"role": "user", "content": "Why can't I create epochs?"}]
    )
    prompt = request.to_model_messages()[0]["content"]
    blockers = prompt.split("Relevant Blockers:", maxsplit=1)[1]

    assert request.response_contract is AssistantResponseContract.NATURAL_LANGUAGE
    assert runtime.publication_reads == 1
    assert assembler.latest_tool_publication.tool_names == frozenset()
    assert "- create_epoch: Preprocess data before creating epochs." in blockers
    assert "- train:" not in blockers
    assert "unique description for epoch_data" not in prompt
    assert "unique description for scan_source" not in prompt


def test_blocked_explanation_rag_scope_never_reads_or_exposes_tools() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("start_training"))
    runtime = MagicMock()
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=runtime,
    )

    allowed = assembler.rag_allowed_tool_names("為什麼現在不能訓練?")

    assert allowed == frozenset()
    runtime.get_view_publication.assert_not_called()


def test_generation_request_marks_workflow_action_as_structured():
    assembler = ContextAssembler(ToolRegistry(), Study())

    request = assembler.get_generation_request(
        [{"role": "user", "content": "Scan /data for EEG files."}]
    )

    assert request.response_contract is AssistantResponseContract.STRUCTURED_ACTION
    assert "exactly one" in request.to_model_messages()[0]["content"]


def test_rag_examples_are_scoped_to_the_requested_workflow_action():
    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    registry.register(_NamedTool("list_files"))
    assembler = ContextAssembler(registry, Study())

    allowed = assembler.rag_allowed_tool_names(
        "Use the EEG recording at /data/eeg to prepare the data."
    )

    assert allowed == frozenset({"scan_source"})


def test_prompt_action_contracts_are_one_json_array():
    assembler = ContextAssembler(ToolRegistry(), Study())

    contracts = json.loads(assembler._format_tools([]))

    assert isinstance(contracts, list)
    assert [contract["name"] for contract in contracts] == ["respond_to_user"]


# Mock Tools
class ValidTool(BaseTool):
    @property
    def name(self):
        return "valid_tool"

    @property
    def description(self):
        return "Valid description"

    @property
    def parameters(self):
        return {"p": "v"}

    def is_valid(self, study):
        return True

    def execute(self, study, **kwargs):
        return ""


class InvalidTool(BaseTool):
    @property
    def name(self):
        return "invalid_tool"

    @property
    def description(self):
        return "Invalid description"

    @property
    def parameters(self):
        return {}

    def is_valid(self, study):
        return False

    def execute(self, study, **kwargs):
        return ""


class _NamedTool(BaseTool):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return f"unique description for {self._name}"

    @property
    def parameters(self):
        return {}

    def execute(self, study, **kwargs):
        return ""


class _ApplicationServiceStub:
    def __init__(self, state: ApplicationStateSnapshot) -> None:
        self._state = state

    def get_view_publication(self) -> ApplicationViewPublication:
        return ApplicationViewPublication(
            generation=1,
            state=self._state,
            capabilities=build_capability_policy(self._state),
        )


class _ApplicationRuntimeFake:
    def __init__(self, publication: ApplicationViewPublication) -> None:
        self._publication = publication
        self.publication_reads = 0

    def get_view_publication(self) -> ApplicationViewPublication:
        self.publication_reads += 1
        if self.publication_reads > 1:
            raise AssertionError("system prompt attempted a second publication read")
        return self._publication

    def execute(self, command: Command) -> CommandResult:
        del command
        raise AssertionError("prompt assembly must not execute commands")


def test_workflow_decision_context_reads_one_atomic_publication():
    state = _state()
    publication = ApplicationViewPublication(
        generation=7,
        state=state,
        capabilities=build_capability_policy(state),
    )
    service = MagicMock()
    service.get_view_publication.return_value = publication

    with patch(
        "XBrainLab.llm.agent.decision_context.get_application_service",
        return_value=service,
    ):
        context = build_workflow_decision_context(object())

    service.get_view_publication.assert_called_once_with()
    service.get_state.assert_not_called()
    service.get_capabilities.assert_not_called()
    assert context.workflow_stage == "No data loaded"


def test_system_prompt_uses_exactly_one_publication_for_all_workflow_sections():
    study = Study()
    state = _state()
    publication = ApplicationViewPublication(
        generation=8,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication)
    assembler = ContextAssembler(
        ToolRegistry(),
        study,
        application_runtime=runtime,
    )

    prompt = assembler.build_system_prompt("What can I do next?")

    assert runtime.publication_reads == 1
    assert "- workflow_stage: No data loaded" in prompt
    assert "recommended_next_step" not in prompt
    assert "STRICT RESPONSE CONTRACT - DECISION ORDER" in prompt
    assert "Operation policy" not in prompt
    assert '"unavailable_operations"' not in prompt
    assert "No executable workflow actions are available" in prompt


def test_preprocessed_publication_aligns_model_and_decision_context() -> None:
    state = _state(
        pipeline_stage="preprocessed",
        raw=RawStateSnapshot(loaded=True, count=1),
        preprocessed=PreprocessedStateSnapshot(available=True, count=1),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )
    publication = ApplicationViewPublication(
        generation=9,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication)
    registry = ToolRegistry()
    registry.register(_NamedTool("epoch_data"))

    prompt = ContextAssembler(
        registry,
        Study(),
        application_runtime=runtime,
    ).build_system_prompt("Create epochs")

    assert runtime.publication_reads == 1
    assert "## Current Stage: Preprocessed" in prompt
    assert "Ready for epoching" in prompt
    assert "recommended_next_step" not in prompt
    assert '"name": "epoch_data"' in prompt
    assert "unique description for epoch_data" in prompt


@pytest.mark.parametrize("text", ("Reset preprocessing.", "重設前處理"))
def test_reset_preprocess_prompt_exposes_only_narrow_reset_tool(text: str) -> None:
    state = _state(
        pipeline_stage="preprocessed",
        raw=RawStateSnapshot(loaded=True, count=1),
        preprocessed=PreprocessedStateSnapshot(
            available=True,
            count=1,
            operations=["bandpass"],
        ),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )
    publication = ApplicationViewPublication(
        generation=91,
        state=state,
        capabilities=build_capability_policy(state),
    )
    registry = ToolRegistry()
    registry.register(_NamedTool("reset_preprocess"))
    registry.register(_NamedTool("clear_dataset"))
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=_ApplicationRuntimeFake(publication),
    )

    prompt = assembler.build_system_prompt(text)

    assert assembler.latest_tool_publication.tool_names == frozenset(
        {"reset_preprocess"}
    )
    assert "unique description for reset_preprocess" in prompt
    assert "unique description for clear_dataset" not in prompt


@pytest.mark.parametrize("text", ("Stop training.", "停止訓練"))
def test_active_training_prompt_exposes_stop_not_start_tool(text: str) -> None:
    state = _state(
        pipeline_stage="training",
        training=TrainingStateSnapshot(
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            is_running=True,
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=True,
            has_training_option=True,
            has_trainer=True,
            is_running=True,
        ),
    )
    publication = ApplicationViewPublication(
        generation=92,
        state=state,
        capabilities=build_capability_policy(state),
    )
    registry = ToolRegistry()
    registry.register(_NamedTool("stop_training"))
    registry.register(_NamedTool("start_training"))
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=_ApplicationRuntimeFake(publication),
    )

    prompt = assembler.build_system_prompt(text)

    assert assembler.latest_tool_publication.tool_names == frozenset({"stop_training"})
    assert "unique description for stop_training" in prompt
    assert "unique description for start_training" not in prompt


def test_explanatory_no_tool_turn_publishes_no_workflow_tools() -> None:
    state = _state(
        pipeline_stage="preprocessed",
        raw=RawStateSnapshot(loaded=True, count=1),
        preprocessed=PreprocessedStateSnapshot(available=True, count=1),
        active_dataset=ActiveDatasetSnapshot(
            has_raw_data=True,
            has_preprocessed_data=True,
        ),
    )
    publication = ApplicationViewPublication(
        generation=10,
        state=state,
        capabilities=build_capability_policy(state),
    )
    registry = ToolRegistry()
    registry.register(_NamedTool("epoch_data"))
    runtime = _ApplicationRuntimeFake(publication)
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=runtime,
    )

    prompt = assembler.build_system_prompt(
        "Explain what EEG preprocessing prepares for."
    )

    assert "informational EEG or BCI question" in prompt
    assert "Answer directly and concisely for the user" in prompt
    assert '"tool_name"' not in prompt
    assert "unique description for epoch_data" not in prompt
    assert assembler.latest_tool_publication.tool_names == frozenset()
    assert runtime.publication_reads == 0


def test_standalone_explanation_does_not_inherit_prior_workflow_exchange() -> None:
    assembler = ContextAssembler(ToolRegistry(), Study())
    latest_question = (
        "Explain in one short sentence what EEG preprocessing prepares data for."
    )

    messages = assembler.get_messages(
        [
            {
                "role": "user",
                "content": "Check what is ready in the current workflow.",
            },
            {
                "role": "assistant",
                "content": "No data loaded. Next: Scan data source.",
            },
            {"role": "user", "content": latest_question},
        ]
    )

    assert messages[1:] == [{"role": "user", "content": latest_question}]
    assert "current workflow" not in str(messages[1:]).lower()


def test_referential_explanation_keeps_immediate_conversation_context() -> None:
    assembler = ContextAssembler(ToolRegistry(), Study())
    history = [
        {
            "role": "user",
            "content": "Explain what EEG preprocessing prepares data for.",
        },
        {
            "role": "assistant",
            "content": "It prepares EEG signals for reliable downstream analysis.",
        },
        {"role": "user", "content": "Why is that useful?"},
    ]

    messages = assembler.get_messages(history)

    assert messages[1:] == history


def test_real_service_prompt_reads_one_committed_publication_generation():
    from XBrainLab.backend.application import get_application_service

    study = Study()
    service = get_application_service(study)
    empty = ApplicationStateSnapshot.empty()
    loaded = replace(
        empty,
        pipeline_stage="data_loaded",
        raw=replace(
            empty.raw,
            loaded=True,
            count=1,
            files=["subject.gdf"],
        ),
        active_dataset=replace(
            empty.active_dataset,
            has_raw_data=True,
        ),
    )
    service.state_snapshot.build = MagicMock(side_effect=[empty, loaded])
    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    registry.register(_NamedTool("apply_bandpass_filter"))

    prompt = ContextAssembler(registry, study).build_system_prompt(
        "Help me import EEG data."
    )

    assert service.state_snapshot.build.call_count == 0
    assert "## Current Stage: Empty (No Data)" in prompt
    assert "- workflow_stage: No data loaded" in prompt
    assert "recommended_next_step" not in prompt
    assert "unique description for scan_source" in prompt
    assert "unique description for apply_bandpass_filter" not in prompt
    assert "- preprocess: Load raw data before preprocessing." not in prompt


def test_stale_publication_prompt_redacts_relevant_scan_source_blocker():
    study = Study()
    state = _state()
    publication = ApplicationViewPublication(
        generation=9,
        state=state,
        capabilities=build_capability_policy(state),
        stale=True,
        refresh_error="Traceback: /private/runtime.py SECRET_TOKEN_123",
    )
    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    registry.register(_NamedTool("query_state"))
    registry.register(_NamedTool("clear_dataset"))
    runtime = _ApplicationRuntimeFake(publication)
    assembler = ContextAssembler(
        registry,
        study,
        application_runtime=runtime,
    )

    prompt = assembler.build_system_prompt("Import EEG data from a source")

    assert "Workflow status unavailable" in prompt
    assert "Traceback" not in prompt
    assert "/private/runtime.py" not in prompt
    assert "SECRET_TOKEN_123" not in prompt
    assert "Workflow state is temporarily unavailable." in prompt
    assert "- scan_source: Workflow state is temporarily unavailable." in prompt
    assert "## Workflow Status Unavailable" in prompt
    assert "## Current Stage: Empty (No Data)" not in prompt
    assert "unique description for query_state" not in prompt
    assert "unique description for clear_dataset" not in prompt
    assert "unique description for scan_source" not in prompt


def _state(
    *,
    pipeline_stage: str = "empty",
    raw: RawStateSnapshot | None = None,
    preprocessed: PreprocessedStateSnapshot | None = None,
    epoch: EpochStateSnapshot | None = None,
    dataset: DatasetStateSnapshot | None = None,
    training: TrainingStateSnapshot | None = None,
    evaluation: EvaluationStateSnapshot | None = None,
    visualization: VisualizationStateSnapshot | None = None,
    interpretation: InterpretationStateSnapshot | None = None,
    active_dataset: ActiveDatasetSnapshot | None = None,
    active_training: ActiveTrainingSnapshot | None = None,
) -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        pipeline_stage=pipeline_stage,
        raw=raw or RawStateSnapshot(),
        preprocessed=preprocessed or PreprocessedStateSnapshot(),
        epoch=epoch or EpochStateSnapshot(),
        dataset=dataset or DatasetStateSnapshot(),
        training=training or TrainingStateSnapshot(),
        evaluation=evaluation or EvaluationStateSnapshot(),
        visualization=visualization or VisualizationStateSnapshot(),
        interpretation=interpretation or InterpretationStateSnapshot(),
        active_dataset=active_dataset or ActiveDatasetSnapshot(),
        active_training=active_training or ActiveTrainingSnapshot(),
    )


def _usable_epoch_state() -> EpochStateSnapshot:
    return EpochStateSnapshot(
        available=True,
        exists=True,
        epoch_count=288,
        event_names=["Left hand", "Right hand"],
        event_ids={"Left hand": 769, "Right hand": 770},
    )


def test_assembler_filtering():
    """Test that Assembler includes only tools allowed by the stage config."""

    # 1. Setup Registry
    registry = ToolRegistry()
    registry.register(ValidTool())
    registry.register(InvalidTool())

    # 2. Use an explicit non-product context with no application runtime.
    compatibility_context = object()

    # 3. Patch pipeline stage to a config that allows only valid_tool
    with (
        patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ),
        patch(
            "XBrainLab.llm.agent.assembler.STAGE_CONFIG",
            {
                PipelineStage.EMPTY: {
                    "tools": ["valid_tool"],
                    "system_prompt": "You are XBrainLab Assistant.\ntest stage prompt",
                }
            },
        ),
    ):
        assembler = ContextAssembler(registry, compatibility_context)
        system_prompt = assembler.build_system_prompt()

    # 4. Verify Content
    assert "valid_tool" in system_prompt
    assert "Valid description" in system_prompt
    assert "invalid_tool" not in system_prompt
    assert "Invalid description" not in system_prompt


def test_assembler_context_and_history():
    """Test standard features: RAG context and History assembly."""
    registry = ToolRegistry()
    compatibility_context = object()

    with patch(
        "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
        return_value=PipelineStage.EMPTY,
    ):
        assembler = ContextAssembler(registry, compatibility_context)

        # Add RAG context
        assembler.add_context("Important RAG Info")

        # Get Messages with History
        history = [{"role": "user", "content": "Hello"}]
        messages = assembler.get_messages(history)

    # Verify System Message index 0
    sys_msg = messages[0]["content"]
    assert "Important RAG Info" in sys_msg
    assert "You are XBrainLab Assistant" in sys_msg  # Standard header

    # Verify History
    assert messages[1] == {"role": "user", "content": "Hello"}


def test_workflow_decision_context_uses_backend_state_for_next_step():
    """The LLM should receive a compact workflow decision, not infer from chat."""
    context = build_workflow_decision_context(
        Study(),
        latest_user_text="Help me prepare this dataset for training",
        mode="continue_until_decision",
    )

    assert context.workflow_stage == "No data loaded"
    assert context.recommended_next_step == "scan_source"
    assert context.recommended_label == "Scan data source"
    assert context.mode == "continue_until_decision"
    assert "scan_source" in context.allowed_actions
    assert context.decision_needed == ["source_path"]
    assert "open_existing_ui_surface" not in context.allowed_actions


@pytest.mark.parametrize(
    (
        "stage",
        "active_dataset",
        "epoch",
        "active_training",
        "training",
        "evaluation",
        "expected_label",
        "expected_next_step",
    ),
    [
        (
            "empty",
            ActiveDatasetSnapshot(),
            EpochStateSnapshot(),
            ActiveTrainingSnapshot(),
            TrainingStateSnapshot(),
            EvaluationStateSnapshot(),
            "No data loaded",
            "scan_source",
        ),
        (
            "data_loaded",
            ActiveDatasetSnapshot(has_raw_data=True),
            EpochStateSnapshot(),
            ActiveTrainingSnapshot(),
            TrainingStateSnapshot(),
            EvaluationStateSnapshot(),
            "Ready for preprocessing",
            "preprocess",
        ),
        (
            "preprocessed",
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
            ),
            EpochStateSnapshot(),
            ActiveTrainingSnapshot(),
            TrainingStateSnapshot(),
            EvaluationStateSnapshot(),
            "Ready for epoching",
            "create_epoch",
        ),
        (
            "epoch_ready",
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
            ),
            _usable_epoch_state(),
            ActiveTrainingSnapshot(),
            TrainingStateSnapshot(),
            EvaluationStateSnapshot(),
            "Ready to build dataset",
            "generate_dataset",
        ),
        (
            "dataset_ready",
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=True,
            ),
            _usable_epoch_state(),
            ActiveTrainingSnapshot(),
            TrainingStateSnapshot(),
            EvaluationStateSnapshot(),
            "Dataset ready",
            "configure_training",
        ),
        (
            "training",
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=True,
            ),
            _usable_epoch_state(),
            ActiveTrainingSnapshot(has_trainer=True, is_running=True),
            TrainingStateSnapshot(has_trainer=True, is_running=True),
            EvaluationStateSnapshot(total_plans=1),
            "Training running",
            None,
        ),
        (
            "trained",
            ActiveDatasetSnapshot(
                has_raw_data=True,
                has_preprocessed_data=True,
                has_epoch_data=True,
                has_datasets=True,
            ),
            _usable_epoch_state(),
            ActiveTrainingSnapshot(has_trainer=True),
            TrainingStateSnapshot(has_trainer=True),
            EvaluationStateSnapshot(
                available=True,
                total_plans=1,
                total_runs=1,
                finished_runs=1,
                metrics_available=True,
            ),
            "Results available",
            "evaluate",
        ),
    ],
)
def test_workflow_decision_context_uses_published_stage_contract(
    stage: str,
    active_dataset: ActiveDatasetSnapshot,
    epoch: EpochStateSnapshot,
    active_training: ActiveTrainingSnapshot,
    training: TrainingStateSnapshot,
    evaluation: EvaluationStateSnapshot,
    expected_label: str,
    expected_next_step: str | None,
) -> None:
    state = _state(
        pipeline_stage=stage,
        active_dataset=active_dataset,
        epoch=epoch,
        active_training=active_training,
        training=training,
        evaluation=evaluation,
    )
    publication = ApplicationViewPublication(
        generation=3,
        state=state,
        capabilities=build_capability_policy(state),
    )

    context = build_workflow_decision_context(
        object(),
        publication=publication,
    )

    assert context.workflow_stage == expected_label
    assert context.recommended_next_step == expected_next_step


def test_workflow_decision_context_follows_data_import_lifecycle():
    """Data Import scan/preview/validate/apply state drives the next step."""
    state = _state(
        interpretation=InterpretationStateSnapshot(
            has_scan_result=True,
            latest_scan_id="scan-001",
            source_path="/data/sub01.gdf",
        ),
    )

    with patch(
        "XBrainLab.llm.agent.decision_context.get_application_service",
        return_value=_ApplicationServiceStub(state),
    ):
        context = build_workflow_decision_context(
            object(),
            latest_user_text="continue importing",
        )

    assert context.recommended_next_step == "preview_interpretation"
    assert context.evidence[0] == "A data source scan is ready for import preview."
    assert context.decision_needed == []
    assert any("scan is ready" in item for item in context.evidence)


def test_workflow_decision_context_routes_validated_import_to_apply_boundary():
    """Validated import candidates should stop at the apply confirmation boundary."""
    state = _state(
        interpretation=InterpretationStateSnapshot(
            has_scan_result=True,
            has_candidate=True,
            has_validation_decision=True,
            latest_candidate_id="candidate-001",
            validation_decision="ready",
        ),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )

    with patch(
        "XBrainLab.llm.agent.decision_context.get_application_service",
        return_value=_ApplicationServiceStub(state),
    ):
        context = build_workflow_decision_context(
            object(),
            latest_user_text="apply it",
            mode="continue_until_decision",
        )

    assert context.recommended_next_step == "apply_interpretation"
    assert context.can_auto_continue is False
    assert context.stop_reason == "semantic_apply"
    assert "apply_interpretation" in context.allowed_actions


def test_applied_import_context_moves_to_preprocess():
    """After import is applied, the agent should continue from loaded raw data."""
    state = _state(
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(loaded=True, count=1),
        interpretation=InterpretationStateSnapshot(
            has_applied_interpretation=True,
            latest_interpretation_id="interpretation-001",
        ),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )

    with patch(
        "XBrainLab.llm.agent.decision_context.get_application_service",
        return_value=_ApplicationServiceStub(state),
    ):
        context = build_workflow_decision_context(object())

    assert context.recommended_next_step == "preprocess"
    assert context.recommended_label == "Preprocess data"


def test_assembler_sends_decision_context_and_short_clean_history():
    """History sent to the LLM is short and excludes prior tool payloads."""
    registry = ToolRegistry()
    mock_study = Study()
    history = [
        {"role": "user", "content": "old request 1"},
        {"role": "assistant", "content": "old response 1"},
        {"role": "user", "content": "Tool Output: " + ("x" * 2000)},
        {"role": "assistant", "content": "I scanned the old folder."},
        {"role": "user", "content": "old request 2"},
        {"role": "assistant", "content": "old response 2"},
        {"role": "user", "content": "Please continue until training is ready."},
    ]

    with patch(
        "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
        return_value=PipelineStage.EMPTY,
    ):
        assembler = ContextAssembler(registry, mock_study)
        assembler.bind_turn_scope(AssistantTurnScope.GUIDED_WORKFLOW)
        messages = assembler.get_messages(history)

    assert "Workflow Decision Context:" in messages[0]["content"]
    assert "mode: continue_until_decision" in messages[0]["content"]
    assert "continuation_candidate: scan_source" in messages[0]["content"]
    assert (
        "continuation_role: backend_advice_not_user_request" in messages[0]["content"]
    )
    assert len(messages) <= 5
    assert not any(
        "Tool Output:" in str(message.get("content", "")) for message in messages[1:]
    )
    assert messages[-1] == {
        "role": "user",
        "content": "Please continue until training is ready.",
    }


def test_assembler_does_not_replay_executed_action_envelopes_to_model() -> None:
    assembler = ContextAssembler(ToolRegistry(), Study())
    history = [
        {"role": "user", "content": "Import /data/S04.edf and continue."},
        {
            "role": "assistant",
            "content": (
                '{"tool_name":"scan_source","parameters":'
                '{"source_path":"/data/S04.edf"}}'
            ),
        },
        {"role": "user", "content": "Tool Output: scan completed"},
        {"role": "assistant", "content": "The source scan completed."},
    ]

    clean_history = assembler._history_for_llm(history)

    assert clean_history == [
        {"role": "user", "content": "Import /data/S04.edf and continue."},
        {"role": "assistant", "content": "The source scan completed."},
    ]


def test_assembler_publishes_exact_tool_names_used_in_prompt() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    registry.register(_NamedTool("start_training"))
    assembler = ContextAssembler(registry, Study())

    prompt = assembler.build_system_prompt("Import EEG data from a source")

    assert assembler.latest_tool_publication.tool_names == frozenset({"scan_source"})
    assert "unique description for scan_source" in prompt
    assert "unique description for start_training" not in prompt


def test_assembler_narrows_concrete_source_request_to_scan_tool() -> None:
    registry = ToolRegistry()
    for name in ("list_files", "scan_source", "switch_panel"):
        registry.register(_NamedTool(name))
    assembler = ContextAssembler(registry, Study())

    prompt = assembler.build_system_prompt("Load /data/S04.edf")

    assert assembler.latest_tool_publication.tool_names == frozenset({"scan_source"})
    assert "unique description for scan_source" in prompt
    assert "unique description for list_files" not in prompt
    assert "unique description for switch_panel" not in prompt


def test_assembler_publishes_browse_tool_for_explicit_file_listing() -> None:
    registry = ToolRegistry()
    for name in ("list_files", "scan_source", "switch_panel"):
        registry.register(_NamedTool(name))
    assembler = ContextAssembler(registry, Study())

    prompt = assembler.build_system_prompt("List the files in /data/eeg")

    assert assembler.latest_tool_publication.tool_names == frozenset({"list_files"})
    assert "unique description for list_files" in prompt
    assert "unique description for scan_source" not in prompt


def test_continue_mode_advances_from_completed_scan_to_preview_tool() -> None:
    state = _state(
        interpretation=InterpretationStateSnapshot(
            has_scan_result=True,
            latest_scan_id="scan-001",
            source_path="/data/S04.edf",
        ),
    )
    publication = ApplicationViewPublication(
        generation=22,
        state=state,
        capabilities=build_capability_policy(state),
    )
    registry = ToolRegistry()
    for name in ("list_files", "scan_source", "preview_interpretation"):
        registry.register(_NamedTool(name))
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=_ApplicationRuntimeFake(publication),
    )
    assembler.bind_turn_scope(AssistantTurnScope.GUIDED_WORKFLOW)
    assembler.set_turn_authorized_command(
        "preview_interpretation",
        continuation=True,
    )

    prompt = assembler.build_system_prompt(
        "Load /data/S04.edf and continue until a decision is needed."
    )

    assert assembler.latest_tool_publication.tool_names == frozenset(
        {"preview_interpretation"}
    )
    assert assembler.latest_tool_publication.recommended_command == (
        "preview_interpretation"
    )
    assert "unique description for preview_interpretation" in prompt
    assert "unique description for scan_source" not in prompt
    contracts_text = prompt.split(
        "Available Action Contracts (exhaustive JSON array):\n",
        maxsplit=1,
    )[1].split("\nOnly the listed workflow action", maxsplit=1)[0]
    preview_contract = next(
        item
        for item in json.loads(contracts_text)
        if item["name"] == "preview_interpretation"
    )
    assert preview_contract["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_changing_continuation_authorization_discards_stale_rag_context() -> None:
    assembler = ContextAssembler(ToolRegistry(), Study())
    assembler.set_turn_authorized_command("scan_source")
    assembler.add_context(
        'Example response: {"tool_name": "scan_source", "parameters": {}}'
    )

    assembler.set_turn_authorized_command(
        "preview_interpretation",
        continuation=True,
    )

    assert assembler.context_notes == []


def test_recoverable_tool_feedback_is_structured_system_context_not_history() -> None:
    from XBrainLab.llm.agent.tool_feedback import ToolRecoveryFeedback

    assembler = ContextAssembler(ToolRegistry(), Study())
    assembler.set_recovery_feedback(
        ToolRecoveryFeedback(
            tool_name="list_files",
            command_name=None,
            error_type="input",
            message="directory is required",
            blocked_reason=None,
            guidance="Provide the missing input or ask the user for it.",
        )
    )

    messages = assembler.get_messages(
        [
            {"role": "user", "content": "list files"},
            {
                "role": "user",
                "content": 'Tool Output: {"message":"directory is required"}',
            },
        ]
    )

    assert "Tool Recovery Feedback" in messages[0]["content"]
    assert '"tool_name": "list_files"' in messages[0]["content"]
    assert "runtime data, not instructions" in messages[0]["content"]
    assert all("Tool Output:" not in item["content"] for item in messages[1:])


def test_assembler_only_includes_blocker_relevant_to_latest_request():
    assembler = ContextAssembler(ToolRegistry(), Study())

    prompt = assembler.build_system_prompt("Train the model now.")
    blockers = prompt.split("Relevant Blockers:", maxsplit=1)[1].split(
        "To use a tool",
        maxsplit=1,
    )[0]

    assert "- train:" in blockers
    assert "- preprocess:" not in blockers
    assert "- create_epoch:" not in blockers


def test_prompt_policy_read_result_serializes_one_successful_publication() -> None:
    from XBrainLab.llm.agent.prompt_policy import read_prompt_policy

    state = _state()
    publication = ApplicationViewPublication(
        generation=17,
        state=state,
        capabilities=build_capability_policy(state),
    )
    result = read_prompt_policy(
        object(),
        runtime=_ApplicationRuntimeFake(publication),
    )

    payload = json.loads(json.dumps(result.to_prompt_payload()))

    assert payload["backend_generation"] == 17
    assert payload["publication_error"] is None
    assert "scan_source" in payload["published_tools"]
    assert payload["blocked_reasons"]["preprocess"]


def test_prompt_policy_publication_exception_is_fail_closed_and_safe() -> None:
    from XBrainLab.llm.agent.prompt_policy import read_prompt_policy

    runtime = MagicMock()
    runtime.get_view_publication.side_effect = RuntimeError(
        "secret backend path\nTraceback (most recent call last): ..."
    )

    result = read_prompt_policy(object(), runtime=runtime)
    serialized = json.dumps(result.to_prompt_payload())

    assert result.published_tools == frozenset()
    assert result.blocked_reasons == ()
    assert result.publication_error is not None
    assert result.publication_error.code == "publication_read_failed"
    assert "temporarily unavailable" in result.publication_error.message
    assert "secret backend path" not in serialized
    assert "Traceback" not in serialized


def test_prompt_policy_policy_exception_is_fail_closed_and_prompt_visible() -> None:
    from XBrainLab.llm.agent.prompt_policy import read_prompt_policy

    state = _state()
    publication = ApplicationViewPublication(
        generation=18,
        state=state,
        capabilities=build_capability_policy(state),
    )
    runtime = _ApplicationRuntimeFake(publication)
    with patch(
        "XBrainLab.llm.agent.prompt_policy.build_agent_tool_policy",
        side_effect=RuntimeError("internal capability implementation detail"),
    ):
        result = read_prompt_policy(object(), runtime=runtime)

    assert result.published_tools == frozenset()
    assert result.publication_error is not None
    assert result.publication_error.code == "policy_read_failed"

    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    assembler = ContextAssembler(
        registry,
        object(),
        application_runtime=_ApplicationRuntimeFake(publication),
    )
    with patch(
        "XBrainLab.llm.agent.prompt_policy.build_agent_tool_policy",
        side_effect=RuntimeError("internal capability implementation detail"),
    ):
        prompt = assembler.build_system_prompt("Import EEG data")

    assert "Backend capability policy is temporarily unavailable" in prompt
    assert "unique description for scan_source" not in prompt
    assert "internal capability implementation detail" not in prompt


def test_prompt_policy_blocked_reason_exception_is_fail_closed() -> None:
    from XBrainLab.llm.agent.prompt_policy import read_prompt_policy

    class _BrokenAvailability:
        enabled = False
        command_name = "train"
        tool_name = "start_training"

        @property
        def reason_text(self) -> str:
            raise RuntimeError("blocked reason serialization detail")

    state = _state()
    publication = ApplicationViewPublication(
        generation=19,
        state=state,
        capabilities=build_capability_policy(state),
    )
    with patch(
        "XBrainLab.llm.agent.prompt_policy.build_agent_tool_policy",
        return_value={"start_training": _BrokenAvailability()},
    ):
        result = read_prompt_policy(
            object(),
            runtime=_ApplicationRuntimeFake(publication),
        )

    serialized = json.dumps(result.to_prompt_payload())
    assert result.published_tools == frozenset()
    assert result.blocked_reasons == ()
    assert result.publication_error is not None
    assert result.publication_error.code == "blocked_reasons_failed"
    assert "blocked reason serialization detail" not in serialized


def test_prompt_policy_invalid_publication_type_is_serializable_and_fail_closed() -> (
    None
):
    from XBrainLab.llm.agent.prompt_policy import read_prompt_policy

    runtime = MagicMock()
    runtime.get_view_publication.return_value = object()

    result = read_prompt_policy(object(), runtime=runtime)
    payload = result.to_prompt_payload()

    assert result.publication is None
    assert result.published_tools == frozenset()
    assert payload["backend_generation"] is None
    assert payload["publication_error"]["code"] == "publication_read_failed"

    registry = ToolRegistry()
    registry.register(_NamedTool("scan_source"))
    prompt = ContextAssembler(
        registry,
        object(),
        application_runtime=runtime,
    ).build_system_prompt("Import data")

    assert "Backend capability policy is temporarily unavailable" in prompt
    assert "unique description for scan_source" not in prompt


def test_product_prompt_does_not_publish_unmapped_stage_tool() -> None:
    state = _state()
    publication = ApplicationViewPublication(
        generation=20,
        state=state,
        capabilities=build_capability_policy(state),
    )
    registry = ToolRegistry()
    registry.register(_NamedTool("unmapped_mutation"))
    assembler = ContextAssembler(
        registry,
        Study(),
        application_runtime=_ApplicationRuntimeFake(publication),
    )

    with patch.dict(
        STAGE_CONFIG[PipelineStage.EMPTY],
        {"tools": ["unmapped_mutation"]},
    ):
        prompt = assembler.build_system_prompt("Change the dataset")

    assert "unique description for unmapped_mutation" not in prompt
    assert assembler.latest_tool_publication.tool_names == frozenset()
