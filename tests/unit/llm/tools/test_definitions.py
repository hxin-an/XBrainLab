"""Unit tests for LLM tool definitions — schema validation and contracts."""

import pytest

from XBrainLab.llm.tools.definitions.dataset_def import (
    BaseAttachLabelsTool,
    BaseClearDatasetTool,
    BaseGenerateDatasetTool,
    BaseGetDatasetInfoTool,
    BaseListFilesTool,
    BaseLoadDataTool,
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


def _get_all_def_classes():
    """Return all abstract tool definition classes."""
    return [
        BaseListFilesTool,
        BaseLoadDataTool,
        BaseAttachLabelsTool,
        BaseClearDatasetTool,
        BaseGetDatasetInfoTool,
        BaseGenerateDatasetTool,
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
        params = BaseSetModelTool.parameters.fget(None)
        model_enum = params["properties"]["model_name"]["enum"]
        assert "EEGNet" in model_enum
        assert "SCCNet" in model_enum
        assert "ShallowConvNet" in model_enum
        # DeepConvNet was removed (doesn't exist)
        assert "DeepConvNet" not in model_enum


class TestSwitchPanelEnums:
    def test_panel_enum_values(self):
        params = BaseSwitchPanelTool.parameters.fget(None)
        panel_enum = params["properties"]["panel_name"]["enum"]
        assert "dashboard" in panel_enum
        assert "dataset" in panel_enum
        assert "training" in panel_enum
        assert "visualization" in panel_enum
        assert "evaluation" in panel_enum


class TestGenerateDatasetEnums:
    def test_split_strategy(self):
        params = BaseGenerateDatasetTool.parameters.fget(None)
        strategies = params["properties"]["split_strategy"]["enum"]
        assert "trial" in strategies
        assert "session" in strategies
        assert "subject" in strategies

    def test_required_fields(self):
        params = BaseGenerateDatasetTool.parameters.fget(None)
        assert "split_strategy" in params["required"]
        assert "training_mode" in params["required"]


class TestRequiresConfirmation:
    """Verify that dangerous tools require user confirmation."""

    def test_clear_dataset_requires_confirmation(self):
        val = BaseClearDatasetTool.requires_confirmation.fget(None)
        assert val is True

    def test_start_training_requires_confirmation(self):
        val = BaseStartTrainingTool.requires_confirmation.fget(None)
        assert val is True

    @pytest.mark.parametrize(
        "tool_cls",
        [
            BaseListFilesTool,
            BaseLoadDataTool,
            BaseAttachLabelsTool,
            BaseGetDatasetInfoTool,
            BaseGenerateDatasetTool,
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

        assert BaseTool.requires_confirmation.fget(None) is False
