"""Tests for ContextAssembler policy and stage-filtered tool behaviour."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.prompt_policy import (
    STRICT_TOOL_RESPONSE_PROMPT_POLICY,
    PromptPolicyReadResult,
)
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

        with (
            patch(
                "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
                return_value=stage,
            ),
            patch(
                "XBrainLab.llm.agent.assembler.read_prompt_policy",
                return_value=PromptPolicyReadResult.not_applicable(),
            ),
        ):
            assembler = ContextAssembler(registry, study)
            return assembler.build_system_prompt()

    def test_empty_stage_only_shows_allowed_tools(self):
        prompt = self._build(
            PipelineStage.EMPTY,
            [
                "list_files",
                "load_data",
                "scan_source",
                "switch_panel",
                "apply_bandpass_filter",
            ],
        )
        assert "list_files" in prompt
        assert "scan_source" in prompt
        assert "load_data" not in prompt
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
            ["switch_panel", "set_model", "retired_reset_tool", "list_files"],
        )
        assert "switch_panel" in prompt
        assert "set_model" not in prompt
        assert "retired_reset_tool" not in prompt

    def test_trained_allows_retraining(self):
        prompt = self._build(
            PipelineStage.TRAINED,
            [
                "set_model",
                "configure_training",
                "start_training",
                "evaluate",
                "visualize",
                "saliency",
                "switch_panel",
            ],
        )
        assert "set_model" in prompt
        assert "start_training" in prompt
        assert "evaluate" in prompt
        assert "visualize" in prompt
        assert "saliency" in prompt

    def test_no_tools_registered_shows_fallback(self):
        prompt = self._build(PipelineStage.EMPTY, [])
        assert "No executable workflow actions are available" in prompt

    def test_prompt_composes_the_canonical_decision_policy(self):
        prompt = self._build(
            PipelineStage.EMPTY,
            ["scan_source", "preview_interpretation", "set_model"],
        )

        assert STRICT_TOOL_RESPONSE_PROMPT_POLICY.decision_instructions() in prompt
        assert "request-scoped action contracts are" in prompt
        assert "Workflow Decision Context" not in prompt
        assert 'schema "xbrainlab.untrusted_context.v1"' in prompt
        assert "Only the listed workflow action is available" in prompt

    def test_stage_filter_keeps_legacy_tools_out_of_primary_prompt(self):
        prompt = self._build(
            PipelineStage.DATA_LOADED,
            [
                "scan_source",
                "preview_interpretation",
                "attach_labels",
                "apply_standard_preprocess",
            ],
        )
        assert "scan_source" in prompt
        assert "preview_interpretation" in prompt
        assert "apply_standard_preprocess" in prompt
        assert "attach_labels" not in prompt

    def test_backend_policy_cannot_reintroduce_stage_filtered_legacy_tool(self):
        registry = ToolRegistry()
        for name in ("load_data", "attach_labels", "scan_source", "switch_panel"):
            registry.register(_FakeTool(name))
        study = MagicMock()

        with (
            patch(
                "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
                return_value=PipelineStage.EMPTY,
            ),
            patch(
                "XBrainLab.llm.agent.assembler.read_prompt_policy",
                return_value=PromptPolicyReadResult(
                    publication=None,
                    published_tools=frozenset(
                        {
                            "load_data",
                            "attach_labels",
                            "scan_source",
                            "switch_panel",
                        }
                    ),
                    blocked_reasons=(),
                ),
            ),
        ):
            prompt = ContextAssembler(registry, study).build_system_prompt()

        assert "scan_source" in prompt
        assert "switch_panel" in prompt
        assert "load_data" not in prompt
        assert "attach_labels" not in prompt


class TestPromptContent:
    """System prompt remains policy-only while context is separately encoded."""

    def test_stage_name_is_not_in_system_policy(self):
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.PREPROCESSED,
        ):
            assembler = ContextAssembler(registry, study)
            prompt = assembler.build_system_prompt()

        assert "Preprocessed" not in prompt
        assert "EEG workflow guide" in prompt

    def test_stage_guidance_is_not_in_system_policy(self):
        registry = ToolRegistry()
        study = MagicMock()
        with patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ):
            assembler = ContextAssembler(registry, study)
            prompt = assembler.build_system_prompt()

        assert "no data is loaded" not in prompt.lower()
        assert "runtime context" in prompt.lower()

    def test_rag_context_is_in_separate_untrusted_message(self):
        registry = ToolRegistry()
        study = MagicMock()
        with (
            patch(
                "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
                return_value=PipelineStage.EMPTY,
            ),
            patch(
                "XBrainLab.llm.agent.assembler.read_prompt_policy",
                return_value=PromptPolicyReadResult.not_applicable(),
            ),
        ):
            assembler = ContextAssembler(registry, study)
            assembler.add_context("RAG info")
            messages = assembler.get_messages(
                [{"role": "user", "content": "Import EEG data."}]
            )

        assert "RAG info" not in messages[0]["content"]
        context = json.loads(messages[1]["content"])
        runtime_item = next(
            item for item in context["items"] if item["type"] == "runtime_context"
        )
        assert runtime_item["data"] == {"text": "RAG info"}
        assert runtime_item["source"] == {"kind": "assistant_runtime_context"}

    def test_each_stage_uses_the_same_policy_prompt(self):
        """Workflow state changes data, not policy prose."""
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
        assert len(prompts) == 1

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

        assert "request-scoped action contracts are" in prompt
        assert "Use only an action contract listed for this exact turn" in prompt
