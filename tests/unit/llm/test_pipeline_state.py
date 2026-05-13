"""Tests for the pipeline state machine.

Covers :func:`compute_pipeline_stage`, :data:`STAGE_CONFIG` integrity,
and the ``Study.pipeline_stage`` computed property.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
    compute_pipeline_stage,
)

EXPECTED_STAGE_LABELS = {
    PipelineStage.EMPTY: "Empty (No Data)",
    PipelineStage.DATA_LOADED: "Data Loaded",
    PipelineStage.PREPROCESSED: "Preprocessed",
    PipelineStage.DATASET_READY: "Dataset Ready",
    PipelineStage.TRAINING: "Training In Progress",
    PipelineStage.TRAINED: "Trained",
}

EXPECTED_STAGE_PROMPT_MARKERS = {
    PipelineStage.EMPTY: (
        "## Current Stage: Empty (No Data)",
        "start the Data Interpretation workflow",
        "'scan_source'",
        "'reload_interpretation_recipe'",
        "Do NOT suggest preprocessing or training",
    ),
    PipelineStage.DATA_LOADED: (
        "## Current Stage: Data Loaded",
        "EEG preprocessing guide",
        "'apply_standard_preprocess'",
        "Data Interpretation tools",
        "Do NOT suggest training-related steps yet",
    ),
    PipelineStage.PREPROCESSED: (
        "## Current Stage: Preprocessed",
        "EEG dataset generation guide",
        "'generate_dataset'",
        "Data Interpretation preview",
        "Do NOT suggest model selection or training",
    ),
    PipelineStage.DATASET_READY: (
        "## Current Stage: Dataset Ready",
        "EEG model training guide",
        "'set_model'",
        "'configure_training'",
        "'start_training'",
        "dataset is locked",
    ),
    PipelineStage.TRAINING: (
        "## Current Stage: Training In Progress",
        "training job is currently running",
        "'switch_panel'",
        "Do NOT try to start another training run",
    ),
    PipelineStage.TRAINED: (
        "## Current Stage: Trained",
        "EEG results & iteration",
        "'evaluate'",
        "'visualize'",
        "'saliency'",
        "'clear_dataset'",
    ),
}

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

    def test_real_study_uses_application_service_snapshot(self):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study

        study = Study()
        service = get_application_service(study)
        service.get_state = MagicMock(
            return_value=SimpleNamespace(pipeline_stage="dataset_ready"),
        )

        assert compute_pipeline_stage(study) == PipelineStage.DATASET_READY

    def test_real_study_does_not_fallback_to_direct_state_when_service_fails(self):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study

        study = Study()
        study.loaded_data_list = [MagicMock()]
        service = get_application_service(study)
        service.get_state = MagicMock(side_effect=RuntimeError("snapshot failed"))

        assert compute_pipeline_stage(study) == PipelineStage.EMPTY


# ---------------------------------------------------------------------------
# STAGE_CONFIG integrity
# ---------------------------------------------------------------------------


class TestStageConfig:
    def test_all_stages_have_config(self):
        for stage in PipelineStage:
            assert stage in STAGE_CONFIG, f"Missing config for {stage}"

    def test_every_config_has_tools_and_system_prompt(self):
        for stage, config in STAGE_CONFIG.items():
            assert "tools" in config, f"{stage}: missing 'tools'"
            assert "system_prompt" in config, f"{stage}: missing 'system_prompt'"
            assert isinstance(config["tools"], list)
            assert isinstance(config["system_prompt"], str)

    def test_every_system_prompt_matches_stage_contract(self):
        for stage, markers in EXPECTED_STAGE_PROMPT_MARKERS.items():
            prompt = STAGE_CONFIG[stage]["system_prompt"]
            assert prompt.startswith("You are XBrainLab Assistant"), stage
            assert "### What you should do" in prompt, stage
            assert "### What you should NOT do" in prompt, stage
            for marker in markers:
                assert marker in prompt, f"{stage}: missing prompt marker {marker!r}"

    def test_switch_panel_available_in_all_stages(self):
        for stage, config in STAGE_CONFIG.items():
            assert "switch_panel" in config["tools"], (
                f"{stage}: switch_panel must always be available"
            )

    def test_empty_has_minimal_tools(self):
        tools = STAGE_CONFIG[PipelineStage.EMPTY]["tools"]
        assert "list_files" in tools
        assert "scan_source" in tools
        assert "preview_interpretation" in tools
        assert "load_data" not in tools
        # No preprocess/training tools in EMPTY
        assert "apply_bandpass_filter" not in tools
        assert "start_training" not in tools

    def test_data_loaded_has_preprocess_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "apply_standard_preprocess" in tools
        assert "apply_bandpass_filter" in tools
        assert "scan_source" in tools
        assert "attach_labels" not in tools

    def test_data_loaded_has_no_training_tools(self):
        tools = STAGE_CONFIG[PipelineStage.DATA_LOADED]["tools"]
        assert "set_model" not in tools
        assert "start_training" not in tools

    def test_preprocessed_has_generate_dataset(self):
        tools = STAGE_CONFIG[PipelineStage.PREPROCESSED]["tools"]
        assert "generate_dataset" in tools
        assert "validate_interpretation" in tools
        assert "attach_labels" not in tools
        # Can still re-preprocess
        assert "apply_standard_preprocess" in tools

    def test_stage_prompts_do_not_present_legacy_data_entry_as_primary(self):
        for stage in (
            PipelineStage.EMPTY,
            PipelineStage.DATA_LOADED,
            PipelineStage.PREPROCESSED,
        ):
            prompt = STAGE_CONFIG[stage]["system_prompt"]
            assert "'load_data'" not in prompt
            assert "'attach_labels'" not in prompt
            assert "Data Interpretation" in prompt

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
    def test_every_stage_label_matches_display_contract(self):
        assert {stage: stage.label for stage in PipelineStage} == EXPECTED_STAGE_LABELS


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

    def test_property_reflects_application_service_snapshot(self):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study

        study = Study()
        service = get_application_service(study)
        service.get_state = MagicMock(
            return_value=SimpleNamespace(pipeline_stage="data_loaded"),
        )

        assert study.pipeline_stage == PipelineStage.DATA_LOADED
