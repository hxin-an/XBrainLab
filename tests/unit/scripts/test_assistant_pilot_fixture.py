"""Real Study/Command checks for bounded per-case Pilot initial states."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
import torch

from scripts.dev.assistant_pilot_fixture import prepare_fixture
from XBrainLab.backend.application import StopTrainingCommand, get_application_service
from XBrainLab.backend.study import Study


def test_reviewed_auxiliary_channel_exists_and_is_not_eeg(study, tmp_path):
    fixture = _fixture("data_loaded", tool="select_channels")
    fixture["conditions"]["auxiliary_channels"] = ["EOG1"]
    prepare_fixture(study, fixture, tmp_path / "auxiliary")
    raw = study.loaded_data_list[0].get_mne()
    assert raw.ch_names == ["C3", "C4", "Cz", "Fz", "REF", "EOG1"]
    assert raw.get_channel_types() == ["eeg"] * 5 + ["eog"]


@pytest.mark.parametrize(
    "prior", [{"notch": 60}, {"bandpass": {"low_freq": 1, "high_freq": 40}}]
)
def test_reviewed_prior_filter_is_actually_applied(study, tmp_path, prior):
    fixture = _fixture("preprocessed")
    fixture["conditions"]["prior_preprocessing"] = prior
    prepare_fixture(study, fixture, tmp_path / "prior")
    original = study.loaded_data_list[0].get_mne().copy().load_data()
    actual = study.preprocessed_data_list[0].get_mne()
    if "notch" in prior:
        expected = original.notch_filter(freqs=60, verbose=False)
    else:
        expected = original.filter(l_freq=1, h_freq=40, verbose=False)
    np.testing.assert_allclose(
        actual.get_data(), expected.get_data(), rtol=1e-7, atol=1e-12
    )


def _fixture(stage, sfreq=256, tool=""):
    return {
        "conditions": {
            "stage": stage,
            "raw_sampling_hz": sfreq,
            "channels": ["C3", "C4", "Cz", "Fz", "REF"],
            "session_history": "fresh_single_turn",
            "required_callable_tool": tool,
        },
        "metadata": {
            "fixture_id": "FX-DEV-A01-01",
            "family_id": "DEV-A01-01",
            "workflow_stage": stage,
        },
    }


@pytest.fixture
def study():
    value = Study()
    yield value
    service = get_application_service(value)
    if service.get_state().training.is_running:
        service.execute(StopTrainingCommand(wait_timeout=5.0))
    assert service.wait_for_background_tasks(timeout=10.0)
    get_application_service(value).close()


@pytest.mark.parametrize(
    "stage,tool",
    [
        ("empty", "import_eeg_data"),
        ("data_loaded", "apply_bandpass_filter"),
        ("preprocessed", "reset_preprocessing"),
        ("epoch_ready", "configure_dataset_split"),
        ("dataset_ready", "start_training"),
    ],
)
def test_prepares_real_published_stage_without_training(study, tmp_path, stage, tool):
    result = prepare_fixture(study, _fixture(stage, tool=tool), tmp_path / "case")
    publication = get_application_service(study).get_view_publication()
    assert result["stage"] == stage == publication.state.pipeline_stage
    assert result["publication_generation"] == publication.generation
    assert publication.usable
    assert result["state"] == publication.state.to_dict()
    assert result["required_tool_enabled"] is True
    assert not publication.state.training.has_trainer
    assert not publication.state.training.is_running
    if stage == "empty":
        assert not result["commands"]
        assert not study.loaded_data_list
        assert result["source"] is None
        return
    raw = study.loaded_data_list[0]
    assert raw.get_sfreq() == 256
    assert raw.get_mne().ch_names == ["C3", "C4", "Cz", "Fz", "REF"]
    assert raw.get_mne().get_channel_types() == ["eeg"] * 5
    events, event_ids = raw.get_event_list()
    assert len(events) == 12
    assert set(event_ids) == {"left", "right"}
    assert result["source"]["synthetic"] is True
    assert (
        result["source"]["sha256"]
        == hashlib.sha256(
            (tmp_path / "case" / "fixture_raw.fif").read_bytes()
        ).hexdigest()
    )
    assert all(item["ok"] for item in result["commands"])
    if stage in {"epoch_ready", "dataset_ready"}:
        assert publication.state.epoch.epoch_count == 12
        assert publication.state.epoch.sfreq == 256
    if stage == "preprocessed":
        assert publication.state.preprocessed.operations
        assert not publication.state.epoch.exists
    if stage == "dataset_ready":
        assert publication.state.dataset.split_spec_saved
        assert publication.state.training.has_model
        assert publication.state.training.has_training_option
        assert publication.state.training.training_option["device"] == "cpu"
        assert not publication.state.dataset.split_materialized


@pytest.mark.parametrize("sfreq", [250, 512])
def test_respects_sampling_rate_and_reproduces_signal(tmp_path, sfreq):
    studies = [Study(), Study()]
    try:
        for number, value in enumerate(studies):
            prepare_fixture(
                value, _fixture("data_loaded", sfreq), tmp_path / str(number)
            )
            raw = value.loaded_data_list[0]
            assert raw.get_sfreq() == sfreq
            events, _ = raw.get_event_list()
            assert events[:, 0].tolist() == [
                sfreq * second for second in range(1, 24, 2)
            ]
        np.testing.assert_array_equal(
            studies[0].loaded_data_list[0].get_mne().get_data(),
            studies[1].loaded_data_list[0].get_mne().get_data(),
        )
    finally:
        for value in studies:
            get_application_service(value).close()


def test_defaults_are_reported_for_unspecified_raw_metadata(study, tmp_path):
    fixture = _fixture("epoch_ready", None)
    fixture["conditions"].pop("channels")
    result = prepare_fixture(study, fixture, tmp_path / "case")
    assert result["evidence"]["sfreq"] == 256
    assert result["evidence"]["channels"] == ["C3", "C4", "Cz", "Fz", "REF"]
    assert result["evidence"]["defaults_used"] == ["raw_sampling_hz", "channels"]


def test_existing_destination_is_never_overwritten(study, tmp_path):
    destination = tmp_path / "case"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    before = get_application_service(study).get_state().to_dict()
    with pytest.raises(FileExistsError):
        prepare_fixture(study, _fixture("data_loaded"), destination)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert get_application_service(study).get_state().to_dict() == before


def test_existing_study_is_not_reset_or_mutated(study, tmp_path):
    prepare_fixture(study, _fixture("data_loaded"), tmp_path / "first")
    before = get_application_service(study).get_state().to_dict()
    with pytest.raises(ValueError, match="fresh"):
        prepare_fixture(study, _fixture("epoch_ready"), tmp_path / "second")
    assert not (tmp_path / "second").exists()
    assert get_application_service(study).get_state().to_dict() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("stage", "trained"),
        ("stage", "training"),
        ("raw_sampling_hz", float("nan")),
        ("raw_sampling_hz", True),
        ("channels", ["C3", "C3"]),
        ("session_history", "keep_existing_history"),
    ],
)
def test_rejects_invalid_or_unsupported_fixture_before_writes(
    study, tmp_path, field, value
):
    fixture = _fixture("data_loaded")
    fixture["conditions"][field] = value
    with pytest.raises(ValueError):
        prepare_fixture(study, fixture, tmp_path / "case")
    assert not (tmp_path / "case").exists()
    assert not study.loaded_data_list


def test_required_tool_is_checked_not_injected(study, tmp_path):
    with pytest.raises(RuntimeError, match="required tool"):
        prepare_fixture(
            study, _fixture("empty", tool="start_training"), tmp_path / "case"
        )
    assert get_application_service(study).get_state().pipeline_stage == "empty"
    assert not study.datasets


def test_prompt_stage_membership_is_checked_alongside_backend_capability(
    study, tmp_path
):
    with pytest.raises(RuntimeError, match="required tool"):
        prepare_fixture(
            study, _fixture("preprocessed", tool="select_channels"), tmp_path / "case"
        )
    assert get_application_service(study).get_state().pipeline_stage == "preprocessed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("labels", "unknown event mapping"),
        ("channel_types", "mixed unknown"),
        ("channels", ["C3", " "]),
        ("channels", []),
    ],
)
def test_rejects_unimplemented_data_semantics(study, tmp_path, field, value):
    fixture = _fixture("data_loaded")
    fixture["conditions"][field] = value
    with pytest.raises(ValueError):
        prepare_fixture(study, fixture, tmp_path / "case")
    assert not (tmp_path / "case").exists()


@pytest.mark.parametrize("tool", ["clear_training_history", "compute_saliency"])
def test_real_cpu_trained_fixture_publishes_checkpoint_and_metrics(
    study, tmp_path, tool
):
    result = prepare_fixture(study, _fixture("trained", tool=tool), tmp_path / "case")
    state = get_application_service(study).get_state()
    assert state.pipeline_stage == "trained"
    assert state.training.finished_run_count == 1
    assert state.evaluation.metrics_available
    assert not state.training.is_running
    assert not state.visualization.saliency_available
    assert result["jobs"]["training"]["phase"] == "completed"
    assert result["jobs"]["training"]["configured_epochs"] == 1
    assert result["jobs"]["training"]["elapsed_seconds"] > 0
    checkpoints = list((tmp_path / "case" / "training").rglob("Epoch-1-model"))
    assert len(checkpoints) == 1
    assert torch.load(checkpoints[0], map_location="cpu", weights_only=True)


def test_renderable_fixture_uses_real_saliency_computation(study, tmp_path):
    fixture = _fixture("trained", tool="switch_panel")
    fixture["conditions"]["saliency_results"] = (
        "already computed and renderable for current selected run"
    )
    result = prepare_fixture(study, fixture, tmp_path / "case")
    state = get_application_service(study).get_state()
    assert result["jobs"]["saliency"]["phase"] == "completed"
    assert state.visualization.saliency_available
    assert state.visualization.channel_positions_available
    assert state.visualization.saliency_coverage
    assert all(
        any(method.method == "Gradient" and method.complete for method in run.methods)
        for run in state.visualization.saliency_coverage
    )


def test_running_fixture_is_actual_cancellable_cpu_job(study, tmp_path):
    result = prepare_fixture(
        study,
        _fixture("training", tool="stop_training"),
        tmp_path / "case",
        running_training_epochs=20,
    )
    service = get_application_service(study)
    assert result["stage"] == "training"
    assert result["jobs"]["training"]["configured_epochs"] == 20
    assert service.get_state().training.is_running
    operation_id = result["jobs"]["training"]["operation_id"]
    assert not service.get_owned_operation(operation_id).phase.terminal
    assert service.execute(StopTrainingCommand(wait_timeout=5.0)).ok
    assert service.wait_for_background_tasks(timeout=10.0)
    assert not service.get_state().training.is_running
    assert service.get_owned_operation(operation_id).phase.terminal


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": 121},
        {"running_training_epochs": 0},
        {"running_training_epochs": 10001},
    ],
)
def test_invalid_job_budget_rejected_before_mutation(study, tmp_path, kwargs):
    with pytest.raises(ValueError):
        prepare_fixture(study, _fixture("trained"), tmp_path / "case", **kwargs)
    assert not (tmp_path / "case").exists()


def test_preparation_timeout_does_not_leave_running_job(study, tmp_path):
    with pytest.raises(TimeoutError):
        prepare_fixture(
            study, _fixture("trained"), tmp_path / "case", timeout_seconds=0.001
        )
    assert not get_application_service(study).get_state().training.is_running


def test_post_start_requirement_failure_cancels_its_real_job(study, tmp_path):
    with pytest.raises(RuntimeError, match="required tool"):
        prepare_fixture(
            study,
            _fixture("training", tool="start_training"),
            tmp_path / "case",
            running_training_epochs=20,
        )
    service = get_application_service(study)
    assert service.wait_for_background_tasks(timeout=10.0)
    assert not service.get_state().training.is_running
