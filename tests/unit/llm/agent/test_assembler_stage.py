"""Tests for ContextAssembler policy and stage-filtered tool behaviour."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import patch

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
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


def _prompt_policy_read(
    stage: PipelineStage,
    *,
    published_tools: frozenset[str] = frozenset(),
) -> PromptPolicyReadResult:
    snapshot = replace(ApplicationStateSnapshot.empty(), pipeline_stage=stage.value)
    return PromptPolicyReadResult(
        publication=ApplicationViewPublication(
            generation=1,
            state=snapshot,
            capabilities=build_capability_policy(snapshot),
        ),
        published_tools=published_tools,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStageBasedFiltering:
    """ContextAssembler only includes tools allowed by the current stage."""

    def _build(self, stage: PipelineStage, tool_names: list[str]):
        registry = ToolRegistry()
        for n in tool_names:
            registry.register(_FakeTool(n))

        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(
                stage,
                published_tools=frozenset(tool_names),
            ),
        ):
            assembler = ContextAssembler(registry, Study())
            return assembler.build_system_prompt()

    def test_empty_stage_only_shows_allowed_tools(self):
        prompt = self._build(
            PipelineStage.EMPTY,
            [
                "import_eeg_data",
                "switch_panel",
                "apply_bandpass_filter",
            ],
        )
        assert '"name": "import_eeg_data"' in prompt
        assert '"name": "switch_panel"' in prompt
        assert '"name": "apply_bandpass_filter"' not in prompt

    def test_data_loaded_shows_preprocess_not_training(self):
        prompt = self._build(
            PipelineStage.DATA_LOADED,
            ["select_channels", "apply_bandpass_filter", "start_training"],
        )
        assert '"name": "select_channels"' in prompt
        assert '"name": "apply_bandpass_filter"' in prompt
        assert '"name": "start_training"' not in prompt

    def test_dataset_ready_shows_training_not_preprocess(self):
        prompt = self._build(
            PipelineStage.DATASET_READY,
            [
                "select_model",
                "configure_training",
                "start_training",
                "apply_bandpass_filter",
            ],
        )
        assert '"name": "select_model"' in prompt
        assert '"name": "start_training"' in prompt
        assert '"name": "apply_bandpass_filter"' not in prompt

    def test_training_only_switch_panel(self):
        prompt = self._build(
            PipelineStage.TRAINING,
            ["switch_panel", "select_model", "stop_training"],
        )
        assert '"name": "switch_panel"' in prompt
        assert '"name": "stop_training"' in prompt
        assert '"name": "select_model"' not in prompt

    def test_trained_allows_retraining(self):
        prompt = self._build(
            PipelineStage.TRAINED,
            [
                "select_model",
                "configure_training",
                "start_training",
                "clear_training_history",
                "switch_panel",
            ],
        )
        assert '"name": "select_model"' in prompt
        assert '"name": "start_training"' in prompt
        assert '"name": "clear_training_history"' in prompt

    def test_no_tools_registered_shows_fallback(self):
        prompt = self._build(PipelineStage.EMPTY, [])
        assert "No executable workflow actions are available" in prompt

    def test_prompt_composes_the_canonical_decision_policy(self):
        prompt = self._build(
            PipelineStage.EMPTY,
            ["import_eeg_data", "switch_panel", "select_model"],
        )

        assert (
            STRICT_TOOL_RESPONSE_PROMPT_POLICY.decision_instructions("empty") in prompt
        )
        assert "backend-stage-published action contracts" in prompt
        assert "Workflow Decision Context" not in prompt
        assert 'schema "xbrainlab.untrusted_context.v1"' in prompt
        assert "Only the listed workflow actions are available" in prompt

    def test_stage_filter_keeps_retired_tools_out_of_primary_prompt(self):
        prompt = self._build(
            PipelineStage.DATA_LOADED,
            [
                "scan_source",
                "preview_interpretation",
                "select_channels",
                "apply_bandpass_filter",
            ],
        )
        assert '"name": "select_channels"' in prompt
        assert '"name": "apply_bandpass_filter"' in prompt
        assert "scan_source" not in prompt
        assert "preview_interpretation" not in prompt

    def test_backend_policy_cannot_reintroduce_unpublished_model_tools(self):
        retired = {
            "load_data",
            "attach_labels",
            "get_dataset_info",
            "scan_source",
            "query_state",
        }
        registry = ToolRegistry()
        for name in (*retired, "import_eeg_data", "switch_panel"):
            registry.register(_FakeTool(name))
        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(
                PipelineStage.EMPTY,
                published_tools=frozenset(
                    retired | {"import_eeg_data", "switch_panel"}
                ),
            ),
        ):
            prompt = ContextAssembler(registry, Study()).build_system_prompt()

        assert '"name": "import_eeg_data"' in prompt
        assert '"name": "switch_panel"' in prompt
        for tool_name in retired:
            assert tool_name not in prompt


class TestPromptContent:
    """System prompt remains policy-only while context is separately encoded."""

    def test_stage_name_is_not_in_system_policy(self):
        registry = ToolRegistry()
        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(PipelineStage.PREPROCESSED),
        ):
            assembler = ContextAssembler(registry, Study())
            prompt = assembler.build_system_prompt()

        assert "Preprocessed" not in prompt
        assert "EEG workflow guide" in prompt

    def test_stage_guidance_is_not_in_system_policy(self):
        registry = ToolRegistry()
        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(PipelineStage.EMPTY),
        ):
            assembler = ContextAssembler(registry, Study())
            prompt = assembler.build_system_prompt()

        assert "no data is loaded" not in prompt.lower()
        assert "runtime context" in prompt.lower()

    def test_rag_context_is_in_separate_untrusted_message(self):
        registry = ToolRegistry()
        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(PipelineStage.EMPTY),
        ):
            assembler = ContextAssembler(registry, Study())
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

    def test_each_stage_acknowledges_its_exact_backend_value(self):
        """Workflow state changes only the required stage acknowledgement."""
        prompts = {}
        for stage in PipelineStage:
            registry = ToolRegistry()
            with patch(
                "XBrainLab.llm.agent.assembler.read_prompt_policy",
                return_value=_prompt_policy_read(stage),
            ):
                assembler = ContextAssembler(registry, Study())
                prompt = assembler.build_system_prompt()
            prompts[stage] = prompt
        assert len(set(prompts.values())) == len(PipelineStage)
        for stage, prompt in prompts.items():
            assert f'"workflow_stage":"{stage.value}"' in prompt

    def test_rule_6_only_listed_tools(self):
        """Prompt instructs LLM not to call unlisted tools."""
        registry = ToolRegistry()
        with patch(
            "XBrainLab.llm.agent.assembler.read_prompt_policy",
            return_value=_prompt_policy_read(PipelineStage.EMPTY),
        ):
            assembler = ContextAssembler(registry, Study())
            prompt = assembler.build_system_prompt()

        assert "backend-stage-published action contracts" in prompt
        assert "Use only an action contract listed for this exact stage" in prompt
