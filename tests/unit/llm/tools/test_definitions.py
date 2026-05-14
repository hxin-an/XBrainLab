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
    BaseQueryStateTool,
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
        BaseQueryStateTool,
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


EXPECTED_TOOL_CONTRACTS = {
    BaseListFilesTool: {
        "name": "list_files",
        "description_markers": ("List all files", "directory"),
        "properties": ("directory", "pattern"),
        "required": ("directory",),
    },
    BaseScanSourceTool: {
        "name": "scan_source",
        "description_markers": ("Scan an EEG file", "import recipe"),
        "properties": ("source_path", "source_hint", "label_sources"),
        "required": ("source_path",),
    },
    BasePreviewInterpretationTool: {
        "name": "preview_interpretation",
        "description_markers": ("Preview file", "metadata choices"),
        "properties": ("scan_id", "choices"),
        "required": (),
    },
    BaseValidateInterpretationTool: {
        "name": "validate_interpretation",
        "description_markers": ("Validate", "safe"),
        "properties": ("candidate_id",),
        "required": (),
    },
    BaseApplyInterpretationTool: {
        "name": "apply_interpretation",
        "description_markers": ("Apply", "validated data interpretation"),
        "properties": ("candidate_id", "confirmed"),
        "required": (),
    },
    BaseSaveInterpretationRecipeTool: {
        "name": "save_interpretation_recipe",
        "description_markers": ("Save", "import recipe"),
        "properties": ("recipe_path",),
        "required": (),
    },
    BaseReloadInterpretationRecipeTool: {
        "name": "reload_interpretation_recipe",
        "description_markers": ("Reload", "preview"),
        "properties": ("recipe_path",),
        "required": ("recipe_path",),
    },
    BaseLoadDataTool: {
        "name": "load_data",
        "description_markers": ("Legacy compatibility", "Data Interpretation"),
        "properties": ("paths",),
        "required": ("paths",),
    },
    BaseAttachLabelsTool: {
        "name": "attach_labels",
        "description_markers": ("Legacy compatibility", "labels/events"),
        "properties": ("mapping", "label_format"),
        "required": ("mapping",),
    },
    BaseClearDatasetTool: {
        "name": "clear_dataset",
        "description_markers": ("Clear all loaded data", "Study state"),
        "properties": (),
        "required": (),
    },
    BaseQueryStateTool: {
        "name": "query_state",
        "description_markers": ("typed workflow state", "ApplicationService"),
        "properties": ("query",),
        "required": (),
    },
    BaseGetDatasetInfoTool: {
        "name": "get_dataset_info",
        "description_markers": ("summary info", "loaded dataset"),
        "properties": (),
        "required": (),
    },
    BaseGenerateDatasetTool: {
        "name": "generate_dataset",
        "description_markers": ("Generate training dataset", "epochs"),
        "properties": (
            "test_ratio",
            "val_ratio",
            "split_strategy",
            "training_mode",
        ),
        "required": ("split_strategy", "training_mode"),
    },
    BaseEvaluateTool: {
        "name": "evaluate",
        "description_markers": ("evaluation metrics", "training summaries"),
        "properties": ("target",),
        "required": (),
    },
    BaseVisualizeTool: {
        "name": "visualize",
        "description_markers": ("visualization views", "workflow state"),
        "properties": ("view",),
        "required": (),
    },
    BaseSaliencyTool: {
        "name": "saliency",
        "description_markers": ("saliency readiness", "trained EEG models"),
        "properties": ("method", "params"),
        "required": (),
    },
    BaseStandardPreprocessTool: {
        "name": "apply_standard_preprocess",
        "description_markers": ("standard EEG preprocessing", "Bandpass"),
        "properties": (
            "l_freq",
            "h_freq",
            "notch_freq",
            "rereference",
            "resample_rate",
            "normalize_method",
        ),
        "required": (),
    },
    BaseBandPassFilterTool: {
        "name": "apply_bandpass_filter",
        "description_markers": ("single bandpass filter",),
        "properties": ("low_freq", "high_freq"),
        "required": ("low_freq", "high_freq"),
    },
    BaseNotchFilterTool: {
        "name": "apply_notch_filter",
        "description_markers": ("notch filter", "power line noise"),
        "properties": ("freq",),
        "required": ("freq",),
    },
    BaseResampleTool: {
        "name": "resample_data",
        "description_markers": ("Resample data", "sampling rate"),
        "properties": ("rate",),
        "required": ("rate",),
    },
    BaseNormalizeTool: {
        "name": "normalize_data",
        "description_markers": ("Normalize data", "Z-Score"),
        "properties": ("method",),
        "required": ("method",),
    },
    BaseRereferenceTool: {
        "name": "set_reference",
        "description_markers": ("Set EEG reference",),
        "properties": ("method",),
        "required": ("method",),
    },
    BaseChannelSelectionTool: {
        "name": "select_channels",
        "description_markers": ("Select specific channels",),
        "properties": ("channels",),
        "required": ("channels",),
    },
    BaseSetMontageTool: {
        "name": "set_montage",
        "description_markers": ("standard EEG montage", "visualization"),
        "properties": ("montage_name",),
        "required": ("montage_name",),
    },
    BaseEpochDataTool: {
        "name": "epoch_data",
        "description_markers": ("Epoch continuous data", "events"),
        "properties": ("t_min", "t_max", "event_id", "baseline"),
        "required": ("t_min", "t_max"),
    },
    BaseSetModelTool: {
        "name": "set_model",
        "description_markers": ("deep learning model architecture",),
        "properties": ("model_name",),
        "required": ("model_name",),
    },
    BaseConfigureTrainingTool: {
        "name": "configure_training",
        "description_markers": ("training hyperparameters",),
        "properties": (
            "epoch",
            "batch_size",
            "learning_rate",
            "repeat",
            "device",
            "optimizer",
            "save_checkpoints_every",
            "output_dir",
        ),
        "required": ("epoch", "batch_size", "learning_rate"),
    },
    BaseStartTrainingTool: {
        "name": "start_training",
        "description_markers": ("Start the training process",),
        "properties": (),
        "required": (),
    },
    BaseSwitchPanelTool: {
        "name": "switch_panel",
        "description_markers": ("Switch the main window view", "panel"),
        "properties": ("panel_name", "view_mode"),
        "required": ("panel_name",),
    },
}


class TestToolDefinitionContracts:
    """Verify that all tool definitions expose name, description, parameters,
    and that execute() raises NotImplementedError (abstract guard)."""

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_name(self, tool_cls):
        assert (
            _property_value(tool_cls.name) == EXPECTED_TOOL_CONTRACTS[tool_cls]["name"]
        )

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_description(self, tool_cls):
        desc = _property_value(tool_cls.description)
        assert isinstance(desc, str)
        for marker in EXPECTED_TOOL_CONTRACTS[tool_cls]["description_markers"]:
            assert marker in desc

    @pytest.mark.parametrize("tool_cls", _get_all_def_classes())
    def test_has_parameters(self, tool_cls):
        params = _property_value(tool_cls.parameters)
        assert isinstance(params, dict)
        assert params["type"] == "object"
        assert (
            tuple(params.get("properties", {}).keys())
            == EXPECTED_TOOL_CONTRACTS[tool_cls]["properties"]
        )
        assert (
            tuple(params.get("required", ()))
            == EXPECTED_TOOL_CONTRACTS[tool_cls]["required"]
        )

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

    def test_scan_source_accepts_external_label_sources(self):
        params = _property_value(BaseScanSourceTool.parameters)
        label_sources = params["properties"]["label_sources"]

        assert label_sources["type"] == "array"
        assert label_sources["items"]["type"] == "string"
        assert "label/event files or folders" in label_sources["description"]

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
        assert "metadata_overrides" in choices["properties"]
        assert "label_carrier_choices" in choices["properties"]
        assert "eeg_file_remap" in choices["properties"]
        assert (
            choices["properties"]["eeg_file_remap"]["additionalProperties"]["type"]
            == "string"
        )
        assert "label_carrier_remap" in choices["properties"]
        assert (
            choices["properties"]["label_carrier_remap"]["additionalProperties"]["type"]
            == "string"
        )

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
