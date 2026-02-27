"""Tests for stage-based ContextAssembler behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.pipeline_state import PipelineStage
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.tool_registry import ToolRegistry

# ---------------------------------------------------------------------------
# Test tools
# ---------------------------------------------------------------------------


class _FakeTool(BaseTool):
    """Configurable fake tool for testing."""

    def __init__(self, tool_name: str):
        self._name = tool_name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return f"desc-{self._name}"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    def execute(self, study, **kwargs):
        return ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStageBasedFiltering:
    """ContextAssembler only includes tools allowed by the current stage."""

    def _build(self, stage: PipelineStage, tool_names: list[str]):
        registry = ToolRegistry()
        for n in tool_names:
            registry.register(_FakeTool(n))

        study = MagicMock()

        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=stage,
        ):
            assembler = ContextAssembler(registry, study)
            return assembler.build_system_prompt()

    def test_empty_stage_only_shows_allowed_tools(self):
        prompt = self._build(
            PipelineStage.EMPTY,
            ["list_files", "load_data", "switch_panel", "apply_bandpass_filter"],
        )
        assert "list_files" in prompt
        assert "load_data" in prompt
        assert "switch_panel" in prompt
        assert "apply_bandpass_filter" not in prompt

    def test_data_loaded_shows_preprocess_not_training(self):
        prompt = self._build(
            PipelineStage.DATA_LOADED,
            ["apply_standard_preprocess", "start_training", "switch_panel"],
        )
        assert "apply_standard_preprocess" in prompt
        assert "start_training" not in prompt

    def test_dataset_ready_shows_training_not_preprocess(self):
        prompt = self._build(
            PipelineStage.DATASET_READY,
            [
                "set_model",
                "configure_training",
                "start_training",
                "apply_bandpass_filter",
            ],
        )
        assert "set_model" in prompt
        assert "start_training" in prompt
        assert "apply_bandpass_filter" not in prompt

    def test_training_only_switch_panel(self):
        prompt = self._build(
            PipelineStage.TRAINING,
            ["switch_panel", "set_model", "clear_dataset", "list_files"],
        )
        assert "switch_panel" in prompt
        assert "set_model" not in prompt
        assert "clear_dataset" not in prompt

    def test_trained_allows_retraining(self):
        prompt = self._build(
            PipelineStage.TRAINED,
            ["set_model", "configure_training", "start_training", "switch_panel"],
        )
        assert "set_model" in prompt
        assert "start_training" in prompt

    def test_no_tools_registered_shows_fallback(self):
        prompt = self._build(PipelineStage.EMPTY, [])
        assert "No tools currently available" in prompt


class TestPromptContent:
    """System prompt includes stage name and guidance."""

    def test_contains_stage_name(self):
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.PREPROCESSED,
        ):
            assembler = ContextAssembler(registry, study)
            prompt = assembler.build_system_prompt()

        assert "Preprocessed" in prompt

    def test_contains_guidance(self):
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ):
            assembler = ContextAssembler(registry, study)
            prompt = assembler.build_system_prompt()

        # Per-stage prompt should contain stage-specific guidance
        assert "no data has been loaded" in prompt.lower()

    def test_rag_context_appended(self):
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ):
            assembler = ContextAssembler(registry, study)
            assembler.add_context("RAG info")
            prompt = assembler.build_system_prompt()

        assert "RAG info" in prompt
        assert "Additional Context" in prompt

    def test_each_stage_has_unique_prompt(self):
        """Every stage should produce a distinct system prompt."""
        prompts = set()
        for stage in PipelineStage:
            registry = ToolRegistry()
            study = MagicMock()
            with patch(
                "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
                return_value=stage,
            ):
                assembler = ContextAssembler(registry, study)
                prompt = assembler.build_system_prompt()
            prompts.add(prompt)
        assert len(prompts) == len(PipelineStage)

    def test_rule_6_only_listed_tools(self):
        """Prompt instructs LLM not to call unlisted tools."""
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ):
            assembler = ContextAssembler(registry, study)
            prompt = assembler.build_system_prompt()

        assert "ONLY use the tools listed above" in prompt
