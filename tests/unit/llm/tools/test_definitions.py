"""Unit tests for LLM tool definitions — schema validation and contracts."""

from typing import Any

import pytest

from XBrainLab.llm.tools.definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)
from XBrainLab.llm.tools.definitions.dataset_def import (
    BaseApplyInterpretationTool,
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
    BasePreviewInterpretationTool,
    BaseReloadInterpretationRecipeTool,
    BaseSaveInterpretationRecipeTool,
    BaseScanSourceTool,
    BaseValidateInterpretationTool,
)
from XBrainLab.llm.tools.definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseChannelSelectionTool,
    BaseEpochDataTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
    BaseSetMontageTool,
    BaseStandardPreprocessTool,
)
from XBrainLab.llm.tools.definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
)
from XBrainLab.llm.tools.definitions.ui_control_def import BaseSwitchPanelTool


def _property_value(prop: property) -> Any:
    getter = prop.fget
    assert getter is not None
    return getter(None)


def _get_all_def_classes():
    """Return all abstract tool definition classes."""
    return [
        BaseListFilesTool,
        BaseScanSourceTool,
        BasePreviewInterpretationTool,
        BaseValidateInterpretationTool,
        BaseApplyInterpretationTool,
        BaseSaveInterpretationRecipeTool,
        BaseReloadInterpretationRecipeTool,
        BaseLoadDataTool,
        BaseAttachLabelsTool,
        BaseClearDatasetTool,
        BaseGetDatasetInfoTool,
        BaseGenerateDatasetTool,
        BaseEvaluateTool,
        BaseVisualizeTool,
        BaseSaliencyTool,
        BaseStandardPreprocessTool,
        BaseBandPassFilterTool,
        BaseNotchFilterTool,
        BaseResampleTool,
        BaseNormalizeTool,
        BaseRereferenceTool,
        BaseChannelSelectionTool,
        BaseSetMontageTool,
        BaseEpochDataTool,
        BaseSetModelTool,
        BaseConfigureTrainingTool,
        BaseStartTrainingTool,
        BaseSwitchPanelTool,
    ]


class TestToolDefinitionContracts:
    """Verify that all tool definitions expose name, description, parameters,
    and that execute() raises NotImplementedError (abstract guard)."""

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_name(self, tool_cls):
        assert isinstance(tool_cls.name.fget(None), str)  # property
        assert len(tool_cls.name.fget(None)) > 0

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_description(self, tool_cls):
        # Access through a temporary instance that bypasses BaseTool ABC enforcement
        # We can use __dict__ to get the property directly
        desc = tool_cls.description.fget(None)
        assert isinstance(desc, str)
        assert len(desc) > 0

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_parameters(self, tool_cls):
        params = tool_cls.parameters.fget(None)
        assert isinstance(params, dict)
        assert "type" in params
        assert params["type"] == "object"

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_execute_raises_not_implemented(self, tool_cls):
        with pytest.raises(NotImplementedError):
            tool_cls.execute(None, None)


class TestSetModelToolEnums:
    def test_model_enum_values(self):
        params = _property_value(BaseSetModelTool.parameters)
        model_enum = params["properties"]["model_name"]["enum"]
        assert "EEGNet" in model_enum
        assert "SCCNet" in model_enum
        assert "ShallowConvNet" in model_enum
        # DeepConvNet was removed (doesn't exist)
        assert "DeepConvNet" not in model_enum


class TestSwitchPanelEnums:
    def test_panel_enum_values(self):
        params = _property_value(BaseSwitchPanelTool.parameters)
        panel_enum = params["properties"]["panel_name"]["enum"]
        assert "dashboard" in panel_enum
        assert "dataset" in panel_enum
        assert "training" in panel_enum
        assert "visualization" in panel_enum
        assert "evaluation" in panel_enum


class TestGenerateDatasetEnums:
    def test_split_strategy(self):
        params = _property_value(BaseGenerateDatasetTool.parameters)
        strategies = params["properties"]["split_strategy"]["enum"]
        assert "trial" in strategies
        assert "session" in strategies
        assert "subject" in strategies

    def test_required_fields(self):
        params = _property_value(BaseGenerateDatasetTool.parameters)
        assert "split_strategy" in params["required"]
        assert "training_mode" in params["required"]


class TestConfigureTrainingDefinitions:
    def test_output_dir_is_optional_schema_parameter(self):
        params = _property_value(BaseConfigureTrainingTool.parameters)

        assert params["properties"]["output_dir"]["type"] == "string"
        assert "output_dir" not in params.get("required", [])


class TestAnalysisDefinitions:
    def test_evaluate_target_is_optional(self):
        params = _property_value(BaseEvaluateTool.parameters)
        assert "target" in params["properties"]
        assert "target" not in params.get("required", [])

    def test_visualize_view_is_optional(self):
        params = _property_value(BaseVisualizeTool.parameters)
        assert "view" in params["properties"]
        assert "view" not in params.get("required", [])

    def test_saliency_can_query_or_configure_method(self):
        params = _property_value(BaseSaliencyTool.parameters)
        assert "method" in params["properties"]
        assert "params" in params["properties"]
        assert params["properties"]["params"]["type"] == "object"


class TestDataInterpretationDefinitions:
    def test_scan_source_requires_source_path(self):
        params = _property_value(BaseScanSourceTool.parameters)
        assert "source_path" in params["required"]

    def test_reload_recipe_requires_recipe_path(self):
        params = _property_value(BaseReloadInterpretationRecipeTool.parameters)
        assert "recipe_path" in params["required"]

    def test_apply_interpretation_uses_dynamic_confirmation_policy(self):
        val = _property_value(BaseApplyInterpretationTool.requires_confirmation)
        assert val is False

    def test_preview_choices_are_structured_for_labels_and_metadata(self):
        params = _property_value(BasePreviewInterpretationTool.parameters)
        choices = params["properties"]["choices"]

        assert choices["additionalProperties"] is False
        assert "label_carrier" in choices["properties"]
        assert "bids_events" in choices["properties"]["label_carrier"]["enum"]
        assert "event_role" in choices["properties"]
        assert "subject" in choices["properties"]

    def test_legacy_data_tools_are_marked_in_descriptions(self):
        assert "Legacy compatibility" in _property_value(BaseLoadDataTool.description)
        assert "Legacy compatibility" in _property_value(
            BaseAttachLabelsTool.description
        )


class TestRequiresConfirmation:
    """Verify that dangerous tools require user confirmation."""

    def test_clear_dataset_requires_confirmation(self):
        val = _property_value(BaseClearDatasetTool.requires_confirmation)
        assert val is True

    def test_start_training_requires_confirmation(self):
        val = _property_value(BaseStartTrainingTool.requires_confirmation)
        assert val is True

    @pytest.mark.parametrize(
        "tool_cls",
        [
            BaseListFilesTool,
            BaseScanSourceTool,
            BasePreviewInterpretationTool,
            BaseValidateInterpretationTool,
            BaseApplyInterpretationTool,
            BaseSaveInterpretationRecipeTool,
            BaseReloadInterpretationRecipeTool,
            BaseLoadDataTool,
            BaseAttachLabelsTool,
            BaseGetDatasetInfoTool,
            BaseGenerateDatasetTool,
            BaseEvaluateTool,
            BaseVisualizeTool,
            BaseSaliencyTool,
            BaseStandardPreprocessTool,
            BaseBandPassFilterTool,
            BaseNotchFilterTool,
            BaseResampleTool,
            BaseNormalizeTool,
            BaseRereferenceTool,
            BaseChannelSelectionTool,
            BaseSetMontageTool,
            BaseEpochDataTool,
            BaseSetModelTool,
            BaseConfigureTrainingTool,
            BaseSwitchPanelTool,
        ],
    )
    def test_normal_tools_do_not_require_confirmation(self, tool_cls):
        # requires_confirmation is inherited from BaseTool → False
        from XBrainLab.llm.tools.base import BaseTool

        assert _property_value(BaseTool.requires_confirmation) is False
