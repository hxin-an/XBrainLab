"""Tests for the pipeline state machine.

Covers :func:`compute_pipeline_stage`, :data:`STAGE_CONFIG` integrity,
and the LLM compatibility re-export of the backend stage contract.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.pipeline_stage import (
    PipelineStage as BackendPipelineStage,
)
from XBrainLab.backend.application.pipeline_stage import (
    compute_pipeline_stage as backend_compute_pipeline_stage,
)
from XBrainLab.backend.application.pipeline_stage import derive_pipeline_stage
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
    compute_pipeline_stage,
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

EXPECTED_STAGE_PROMPT_MARKERS = {
    PipelineStage.EMPTY: (
        "## Current Stage: Empty (No Data)",
        "EEG data import guide",
        "Data Interpretation",
        "source path",
    ),
    PipelineStage.DATA_LOADED: (
        "## Current Stage: Data Loaded",
        "EEG preprocessing guide",
        "Raw EEG data is available",
        "epoching",
    ),
    PipelineStage.PREPROCESSED: (
        "## Current Stage: Preprocessed",
        "EEG epoching guide",
        "Ready for EEG epoching",
        "target event",
        "epoch window",
    ),
    PipelineStage.EPOCH_READY: (
        "## Current Stage: EEG Epochs Ready",
        "EEG dataset generation guide",
        "epoch data is available",
        "split strategy",
    ),
    PipelineStage.DATASET_READY: (
        "## Current Stage: Dataset Ready",
        "EEG model training guide",
        "training dataset is ready",
        "model and training settings",
    ),
    PipelineStage.TRAINING: (
        "## Current Stage: Training In Progress",
        "training job is currently running",
        "Do not start another run",
    ),
    PipelineStage.TRAINED: (
        "## Current Stage: Trained",
        "EEG results & iteration",
        "Completed training results",
        "retraining",
    ),
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


def test_stage_prompts_do_not_publish_a_second_tool_truth():
    tool_literals = {
        f"'{tool_name}'"
        for config in STAGE_CONFIG.values()
        for tool_name in config["tools"]
    }

    for config in STAGE_CONFIG.values():
        prompt = config["system_prompt"]
        assert not tool_literals.intersection(
            literal for literal in tool_literals if literal in prompt
        )
        assert "backend-published action contracts below are authoritative" in prompt


def test_stage_config_matches_the_approved_target_ledger() -> None:
    assert {
        stage: set(config["tools"]) for stage, config in STAGE_CONFIG.items()
    } == EXPECTED_TARGET_TOOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_study(**overrides):
    """Create a minimal Study-like mock with sensible defaults."""
    study = MagicMock()
    study.loaded_data_list = overrides.get("loaded_data_list", [])
    study.preprocessed_data_list = overrides.get("preprocessed_data_list", [])
    study.epoch_data = overrides.get("epoch_data")
    study.datasets = overrides.get("datasets", [])
    study.model_holder = overrides.get("model_holder")
    study.training_option = overrides.get("training_option")
    study.trainer = overrides.get("trainer")
    return study


def _running_trainer():
    trainer = MagicMock()
    trainer.is_running.return_value = True
    return trainer


def _finished_trainer():
    trainer = MagicMock()
    trainer.is_running.return_value = False
    run = MagicMock()
    run.is_finished.return_value = True
    holder = MagicMock()
    holder.get_plans.return_value = [run]
    trainer.get_training_plan_holders.return_value = [holder]
    return trainer


# ---------------------------------------------------------------------------
# compute_pipeline_stage
# ---------------------------------------------------------------------------


class TestComputePipelineStage:
    def test_llm_reexports_backend_stage_contract(self):
        assert PipelineStage is BackendPipelineStage
        assert compute_pipeline_stage is backend_compute_pipeline_stage

    def test_empty(self):
        study = _make_study()
        assert compute_pipeline_stage(study) == PipelineStage.EMPTY

    def test_data_loaded(self):
        study = _make_study(loaded_data_list=["raw1"])
        assert compute_pipeline_stage(study) == PipelineStage.DATA_LOADED

    def test_preprocessed(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            preprocessed_data_list=["preprocessed1"],
        )
        assert compute_pipeline_stage(study) == PipelineStage.PREPROCESSED

    def test_epoch_ready(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            preprocessed_data_list=["preprocessed1"],
            epoch_data=MagicMock(),
        )
        assert compute_pipeline_stage(study) == PipelineStage.EPOCH_READY

    def test_dataset_ready(self):
        study = _make_study(
            loaded_data_list=["raw1"],
            epoch_data=MagicMock(),
            datasets=["ds1"],
            model_holder=MagicMock(),
            training_option=MagicMock(),
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

    def test_trainer_without_completion_evidence_is_not_trained(self):
        """Trainer construction alone is not evidence of completed results."""
        trainer = MagicMock(spec=[])  # no attributes
        study = _make_study(trainer=trainer)
        assert compute_pipeline_stage(study) == PipelineStage.EMPTY

    def test_real_study_uses_explicit_application_view_publication(self):
        from XBrainLab.backend.study import Study

        study = Study()
        snapshot = replace(
            ApplicationStateSnapshot.empty(),
            pipeline_stage="dataset_ready",
        )
        publication = ApplicationViewPublication(
            generation=2,
            state=snapshot,
            capabilities=build_capability_policy(snapshot),
        )

        assert (
            compute_pipeline_stage(study, publication=publication)
            == PipelineStage.DATASET_READY
        )

    def test_real_study_without_publication_does_not_fallback_to_direct_state(self):
        from XBrainLab.backend.study import Study

        study = Study()
        study.loaded_data_list = [MagicMock()]

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
            assert (
                "backend-published action contracts below are authoritative" in prompt
            )
            for marker in markers:
                assert marker in prompt, f"{stage}: missing prompt marker {marker!r}"

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

    def test_data_loaded_prompt_allows_preprocessing_or_epoching(self):
        prompt = STAGE_CONFIG[PipelineStage.DATA_LOADED]["system_prompt"]
        assert "ready for preprocessing or EEG epoching" in prompt
        assert "must complete before EEG epoching" not in prompt

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

    def test_stage_prompts_do_not_present_legacy_data_entry_as_primary(self):
        for stage in (
            PipelineStage.EMPTY,
            PipelineStage.DATA_LOADED,
            PipelineStage.PREPROCESSED,
            PipelineStage.EPOCH_READY,
        ):
            prompt = STAGE_CONFIG[stage]["system_prompt"]
            assert "'load_data'" not in prompt
            assert "'attach_labels'" not in prompt
            assert (
                "backend-published action contracts below are authoritative" in prompt
            )

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
