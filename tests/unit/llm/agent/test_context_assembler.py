from unittest.mock import MagicMock, patch

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
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.decision_context import build_workflow_decision_context
from XBrainLab.llm.pipeline_state import PipelineStage
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.tool_registry import ToolRegistry


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


class _ApplicationServiceStub:
    def __init__(self, state: ApplicationStateSnapshot) -> None:
        self._state = state

    def get_state(self) -> ApplicationStateSnapshot:
        return self._state

    def get_capabilities(self):
        return build_capability_policy(self._state)


def _state(
    *,
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
        pipeline_stage="empty",
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


def test_assembler_filtering():
    """Test that Assembler includes only tools allowed by the stage config."""

    # 1. Setup Registry
    registry = ToolRegistry()
    registry.register(ValidTool())
    registry.register(InvalidTool())

    # 2. Setup Mock Study
    mock_study = MagicMock(spec=Study)

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
        assembler = ContextAssembler(registry, mock_study)
        system_prompt = assembler.build_system_prompt()

    # 4. Verify Content
    assert "valid_tool" in system_prompt
    assert "Valid description" in system_prompt
    assert "invalid_tool" not in system_prompt
    assert "Invalid description" not in system_prompt


def test_assembler_context_and_history():
    """Test standard features: RAG context and History assembly."""
    registry = ToolRegistry()
    mock_study = MagicMock(spec=Study)

    with patch(
        "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
        return_value=PipelineStage.EMPTY,
    ):
        assembler = ContextAssembler(registry, mock_study)

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
    assert context.existing_ui_surface == "Data Import wizard"


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
    assert context.existing_ui_surface == "Data Import wizard"
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
    assert "open_existing_ui_surface" in context.allowed_actions


def test_applied_import_context_moves_to_preprocess():
    """After import is applied, the agent should continue from loaded raw data."""
    state = _state(
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
        assembler.execution_mode = "continue_until_decision"
        messages = assembler.get_messages(history)

    assert "Workflow Decision Context:" in messages[0]["content"]
    assert "mode: continue_until_decision" in messages[0]["content"]
    assert "recommended_next_step: scan_source" in messages[0]["content"]
    assert len(messages) <= 5
    assert not any(
        "Tool Output:" in str(message.get("content", "")) for message in messages[1:]
    )
    assert messages[-1] == {
        "role": "user",
        "content": "Please continue until training is ready.",
    }
