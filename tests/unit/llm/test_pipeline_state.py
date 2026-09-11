"""Tests for the stage-specific Assistant tool configuration."""

from __future__ import annotations

from XBrainLab.backend.application.pipeline_stage import derive_pipeline_stage
from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
)

EXPECTED_STAGE_LABELS = {
    PipelineStage.EMPTY: "Empty (No Data)",
    PipelineStage.DATA_LOADED: "Data Loaded",
    PipelineStage.PREPROCESSED: "Preprocessed",
    PipelineStage.EPOCH_READY: "EEG epochs ready",
    PipelineStage.DATASET_READY: "Dataset Ready",
    PipelineStage.TRAINING: "Training In Progress",
    PipelineStage.TRAINED: "Trained",
}

EXPECTED_TARGET_TOOLS = {
    PipelineStage.EMPTY: {"import_eeg_data", "switch_panel"},
    PipelineStage.DATA_LOADED: {
        "select_channels",
        "set_montage",
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
        "create_epochs",
        "switch_panel",
    },
    PipelineStage.PREPROCESSED: {
        "set_montage",
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
        "create_epochs",
        "reset_preprocessing",
        "switch_panel",
    },
    PipelineStage.EPOCH_READY: {
        "configure_dataset_split",
        "select_model",
        "configure_training",
        "start_training",
        "reset_preprocessing",
        "switch_panel",
    },
    PipelineStage.DATASET_READY: {
        "configure_dataset_split",
        "select_model",
        "configure_training",
        "start_training",
        "reset_preprocessing",
        "switch_panel",
    },
    PipelineStage.TRAINING: {"stop_training", "switch_panel"},
    PipelineStage.TRAINED: {
        "configure_dataset_split",
        "select_model",
        "configure_training",
        "start_training",
        "reset_preprocessing",
        "clear_training_history",
        "compute_saliency",
        "switch_panel",
    },
}


def test_compute_saliency_is_published_only_after_completed_training() -> None:
    stages = {
        stage: tuple(config["tools"])
        for stage, config in STAGE_CONFIG.items()
        if "compute_saliency" in config["tools"]
    }

    assert stages == {
        PipelineStage.TRAINED: tuple(STAGE_CONFIG[PipelineStage.TRAINED]["tools"])
    }


def test_active_retraining_hides_compute_saliency_even_with_finished_history() -> None:
    stage = derive_pipeline_stage(is_training=True, finished_run_count=1)

    assert stage is PipelineStage.TRAINING
    assert "compute_saliency" not in STAGE_CONFIG[stage]["tools"]


def test_stage_config_matches_the_approved_target_ledger() -> None:
    assert {
        stage: set(config["tools"]) for stage, config in STAGE_CONFIG.items()
    } == EXPECTED_TARGET_TOOLS


# ---------------------------------------------------------------------------
# STAGE_CONFIG integrity
# ---------------------------------------------------------------------------


class TestStageConfig:
    def test_all_stages_have_config(self):
        for stage in PipelineStage:
            assert stage in STAGE_CONFIG, f"Missing config for {stage}"

    def test_every_config_has_tools(self):
        for stage, config in STAGE_CONFIG.items():
            assert "tools" in config, f"{stage}: missing 'tools'"
            assert isinstance(config["tools"], list)

    def test_switch_panel_available_in_all_stages(self):
        for stage, config in STAGE_CONFIG.items():
            assert "switch_panel" in config["tools"], (
                f"{stage}: switch_panel must always be available"
            )

    def test_empty_has_minimal_tools(self):
        tools = STAGE_CONFIG[PipelineStage.EMPTY]["tools"]
        assert tools == ["import_eeg_data", "switch_panel"]
        # No preprocess/training tools in EMPTY
        assert "apply_bandpass_filter" not in tools
        assert "start_training" not in tools

    def test_data_loaded_has_preprocess_and_epoch_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "select_channels" in tools
        assert "set_montage" in tools
        assert "apply_bandpass_filter" in tools
        assert "create_epochs" in tools
        assert "apply_standard_preprocess" not in tools

    def test_data_loaded_has_no_training_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "select_model" not in tools
        assert "start_training" not in tools

    def test_preprocessed_has_epoching_but_not_dataset_generation(self):
        tools = STAGE_CONFIG[PipelineStage.PREPROCESSED]["tools"]
        assert "select_channels" not in tools
        assert "set_montage" in tools
        assert "create_epochs" in tools
        assert "configure_dataset_split" not in tools
        assert "validate_interpretation" not in tools
        assert "apply_bandpass_filter" in tools

    def test_epoch_ready_has_configure_dataset_split(self):
        tools = STAGE_CONFIG[PipelineStage.EPOCH_READY]["tools"]
        assert "select_channels" not in tools
        assert "set_montage" not in tools
        assert "configure_dataset_split" in tools
        assert "create_epochs" not in tools
        assert "select_model" in tools

    def test_dataset_ready_has_training_but_no_preprocess(self):
        tools = STAGE_CONFIG[PipelineStage.DATASET_READY]["tools"]
        assert "select_channels" not in tools
        assert "set_montage" not in tools
        assert "select_model" in tools
        assert "configure_training" in tools
        assert "start_training" in tools
        assert "clear_dataset" not in tools
        # No preprocess tools
        assert "apply_bandpass_filter" not in tools
        assert "apply_standard_preprocess" not in tools

    def test_training_only_allows_stop_and_navigation(self):
        tools = STAGE_CONFIG[PipelineStage.TRAINING]["tools"]
        assert tools == ["stop_training", "switch_panel"]

    def test_trained_adds_completed_run_actions_to_dataset_ready(self):
        trained = set(STAGE_CONFIG[PipelineStage.TRAINED]["tools"])
        ready = set(STAGE_CONFIG[PipelineStage.DATASET_READY]["tools"])
        assert trained == ready | {"clear_training_history", "compute_saliency"}

    def test_channel_and_montage_are_published_only_before_epochs(self):
        published = {
            tool_name: {
                stage
                for stage, config in STAGE_CONFIG.items()
                if tool_name in config["tools"]
            }
            for tool_name in ("select_channels", "set_montage")
        }

        assert published == {
            "select_channels": {
                PipelineStage.DATA_LOADED,
            },
            "set_montage": {
                PipelineStage.DATA_LOADED,
                PipelineStage.PREPROCESSED,
            },
        }


# ---------------------------------------------------------------------------
# PipelineStage.label
# ---------------------------------------------------------------------------


class TestPipelineStageLabel:
    def test_every_stage_label_matches_display_contract(self):
        assert {stage: stage.label for stage in PipelineStage} == EXPECTED_STAGE_LABELS
