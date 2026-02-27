"""Tests for the pipeline state machine.

Covers :func:`compute_pipeline_stage`, :data:`STAGE_CONFIG` integrity,
and the ``Study.pipeline_stage`` computed property.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
    compute_pipeline_stage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_study(**overrides):
    """Create a minimal Study-like mock with sensible defaults."""
    study = MagicMock()
    study.loaded_data_list = overrides.get("loaded_data_list", [])
    study.epoch_data = overrides.get("epoch_data")
    study.datasets = overrides.get("datasets", [])
    study.trainer = overrides.get("trainer")
    return study


def _running_trainer():
    trainer = MagicMock()
    trainer.is_running.return_value = True
    return trainer


def _finished_trainer():
    trainer = MagicMock()
    trainer.is_running.return_value = False
    return trainer


# ---------------------------------------------------------------------------
# compute_pipeline_stage
# ---------------------------------------------------------------------------


class TestComputePipelineStage:
    def test_empty(self):
        study = _make_study()
        assert compute_pipeline_stage(study) == PipelineStage.EMPTY

    def test_data_loaded(self):
        study = _make_study(loaded_data_list=["raw1"])
        assert compute_pipeline_stage(study) == PipelineStage.DATA_LOADED

    def test_preprocessed(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
        )
        assert compute_pipeline_stage(study) == PipelineStage.PREPROCESSED

    def test_dataset_ready(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
            datasets=["ds1"],
        )
        assert compute_pipeline_stage(study) == PipelineStage.DATASET_READY

    def test_training(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
            datasets=["ds1"],
            trainer=_running_trainer(),
        )
        assert compute_pipeline_stage(study) == PipelineStage.TRAINING

    def test_trained(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
            datasets=["ds1"],
            trainer=_finished_trainer(),
        )
        assert compute_pipeline_stage(study) == PipelineStage.TRAINED

    def test_training_takes_priority_over_trained(self):
        """If trainer is running, stage is TRAINING regardless of datasets."""
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
            datasets=["ds1"],
            trainer=_running_trainer(),
        )
        assert compute_pipeline_stage(study) == PipelineStage.TRAINING

    def test_trainer_without_is_running_attr(self):
        """Trainer that lacks is_running (edge case) → TRAINED."""
        trainer = MagicMock(spec=[])  # no attributes
        study = _make_study(trainer=trainer)
        assert compute_pipeline_stage(study) == PipelineStage.TRAINED


# ---------------------------------------------------------------------------
# STAGE_CONFIG integrity
# ---------------------------------------------------------------------------


class TestStageConfig:
    def test_all_stages_have_config(self):
        for stage in PipelineStage:
            assert stage in STAGE_CONFIG, f"Missing config for {stage}"

    def test_every_config_has_tools_and_guidance(self):
        for stage, config in STAGE_CONFIG.items():
            assert "tools" in config, f"{stage}: missing 'tools'"
            assert "guidance" in config, f"{stage}: missing 'guidance'"
            assert isinstance(config["tools"], list)
            assert isinstance(config["guidance"], str)
            assert len(config["guidance"]) > 0

    def test_switch_panel_available_in_all_stages(self):
        for stage, config in STAGE_CONFIG.items():
            assert "switch_panel" in config["tools"], (
                f"{stage}: switch_panel must always be available"
            )

    def test_empty_has_minimal_tools(self):
        tools = STAGE_CONFIG[PipelineStage.EMPTY]["tools"]
        assert "list_files" in tools
        assert "load_data" in tools
        # No preprocess/training tools in EMPTY
        assert "apply_bandpass_filter" not in tools
        assert "start_training" not in tools

    def test_data_loaded_has_preprocess_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "apply_standard_preprocess" in tools
        assert "apply_bandpass_filter" in tools
        assert "attach_labels" in tools

    def test_data_loaded_has_no_training_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "set_model" not in tools
        assert "start_training" not in tools

    def test_preprocessed_has_generate_dataset(self):
        tools = STAGE_CONFIG[PipelineStage.PREPROCESSED]["tools"]
        assert "generate_dataset" in tools
        assert "attach_labels" in tools
        # Can still re-preprocess
        assert "apply_standard_preprocess" in tools

    def test_dataset_ready_has_training_but_no_preprocess(self):
        tools = STAGE_CONFIG[PipelineStage.DATASET_READY]["tools"]
        assert "set_model" in tools
        assert "configure_training" in tools
        assert "start_training" in tools
        assert "clear_dataset" in tools
        # No preprocess tools
        assert "apply_bandpass_filter" not in tools
        assert "apply_standard_preprocess" not in tools

    def test_training_is_locked(self):
        tools = STAGE_CONFIG[PipelineStage.TRAINING]["tools"]
        assert tools == ["switch_panel"]

    def test_trained_same_tools_as_dataset_ready(self):
        trained = set(STAGE_CONFIG[PipelineStage.TRAINED]["tools"])
        ready = set(STAGE_CONFIG[PipelineStage.DATASET_READY]["tools"])
        assert trained == ready


# ---------------------------------------------------------------------------
# PipelineStage.label
# ---------------------------------------------------------------------------


class TestPipelineStageLabel:
    def test_every_stage_has_label(self):
        for stage in PipelineStage:
            assert isinstance(stage.label, str)
            assert len(stage.label) > 0

    def test_label_is_human_friendly(self):
        assert PipelineStage.EMPTY.label == "Empty (No Data)"
        assert PipelineStage.DATA_LOADED.label == "Data Loaded"
        assert PipelineStage.TRAINING.label == "Training In Progress"


# ---------------------------------------------------------------------------
# Study.pipeline_stage property
# ---------------------------------------------------------------------------


class TestStudyPipelineStage:
    def test_property_delegates_to_compute(self):
        from XBrainLab.backend.study import Study

        study = Study.__new__(Study)
        study.data_manager = MagicMock()
        study.training_manager = MagicMock()
        study.data_manager.loaded_data_list = []
        study.data_manager.epoch_data = None
        study.data_manager.datasets = []
        study.training_manager.trainer = None

        assert study.pipeline_stage == PipelineStage.EMPTY

    def test_property_reflects_loaded_data(self):
        from XBrainLab.backend.study import Study

        study = Study.__new__(Study)
        study.data_manager = MagicMock()
        study.training_manager = MagicMock()
        study.data_manager.loaded_data_list = ["raw1"]
        study.data_manager.epoch_data = None
        study.data_manager.datasets = []
        study.training_manager.trainer = None

        assert study.pipeline_stage == PipelineStage.DATA_LOADED
