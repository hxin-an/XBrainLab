from __future__ import annotations

from dataclasses import dataclass

import pytest

from XBrainLab.backend.application.serialization import serialize_json_value
from XBrainLab.backend.application.state import TrainingStateSnapshot
from XBrainLab.backend.application.training_recommendation import (
    SAFE_UNKNOWN_VRAM_BATCH_SIZE,
    TrainingRecommendationContext,
    TrainingRecommendationField,
    TrainingRecommendationService,
    TrainingSettingProvenance,
)


@dataclass
class _Option:
    epoch: int
    bs: int
    lr: float
    optim: str
    evaluation_option: str
    use_cpu: bool = False
    gpu_idx: int | None = 0
    repeat_num: int = 1


def _context(
    *,
    model_name: str = "braindecode.eegnet",
    sample_count: int = 8_000,
    validation_sample_count: int = 1_000,
    n_channels: int = 22,
    n_times: int = 1_000,
    device: str = "cpu",
) -> TrainingRecommendationContext:
    return TrainingRecommendationContext(
        model_name=model_name,
        model_params={},
        epoch_count=sample_count,
        n_channels=n_channels,
        n_times=n_times,
        dataset_count=5,
        training_sample_count=sample_count,
        validation_sample_count=validation_sample_count,
        device=device,
    )


@pytest.mark.parametrize(
    ("model_name", "epochs", "batch_size", "learning_rate", "optimizer"),
    [
        ("braindecode.eegnet", 50, 32, 0.001, "Adam"),
        ("braindecode.deep4net", 60, 32, 0.0005, "AdamW"),
        ("braindecode.eegconformer", 75, 16, 0.0003, "AdamW"),
        ("custom.unrecognized", 40, 16, 0.0005, "Adam"),
    ],
)
def test_model_family_profiles_are_deterministic_starting_points(
    model_name,
    epochs,
    batch_size,
    learning_rate,
    optimizer,
):
    service = TrainingRecommendationService()

    first = service.recommend(_context(model_name=model_name))
    second = service.recommend(_context(model_name=model_name))

    assert first is second
    assert first.recommended_values.epochs == epochs
    assert first.recommended_values.batch_size == batch_size
    assert first.recommended_values.learning_rate == learning_rate
    assert first.recommended_values.optimizer == optimizer
    assert first.recommended_values.evaluation_strategy == "Best validation loss"
    assert first.is_starting_point is True
    assert any("not a claim of best parameters" in item for item in first.warnings)


def test_dataset_count_and_epoch_shape_apply_conservative_batch_caps():
    service = TrainingRecommendationService()

    small = service.recommend(_context(sample_count=96))
    large = service.recommend(_context())
    high_dimensional = service.recommend(
        _context(n_channels=128, n_times=1_024),
    )

    assert small.recommended_values.epochs == 30
    assert small.recommended_values.batch_size == 8
    assert large.recommended_values.epochs == 50
    assert large.recommended_values.batch_size == 32
    assert high_dimensional.recommended_values.batch_size == 8
    assert any(
        "epoch shape" in item.message.lower() for item in high_dimensional.reasons
    )


def test_gpu_uses_fixed_metadata_cap_without_resource_query_claim():
    recommendation = TrainingRecommendationService().recommend(
        _context(device="cuda:0")
    )

    assert recommendation.recommended_values.batch_size == SAFE_UNKNOWN_VRAM_BATCH_SIZE
    assert any("intentionally not queried" in item for item in recommendation.warnings)
    assert any(
        "metadata-only device cap" in item.message for item in recommendation.reasons
    )
    assert any(
        "final resource preflight" in item.lower() for item in recommendation.warnings
    )


def test_cpu_profile_uses_metadata_cap_without_vram_warning():
    recommendation = TrainingRecommendationService().recommend(_context(device="cpu"))

    assert recommendation.recommended_values.batch_size == 32
    assert not any("GPU memory" in item for item in recommendation.warnings)


def test_auto_device_uses_safe_unknown_cap_without_hardware_query_claim():
    recommendation = TrainingRecommendationService().recommend(_context(device="auto"))

    assert recommendation.recommended_values.batch_size == (
        SAFE_UNKNOWN_VRAM_BATCH_SIZE
    )
    assert any("intentionally not queried" in item for item in recommendation.warnings)


def test_no_validation_split_uses_last_epoch_with_warning():
    recommendation = TrainingRecommendationService().recommend(
        _context(validation_sample_count=0)
    )

    assert recommendation.recommended_values.evaluation_strategy == "Last Epoch"
    assert any("validation split" in item.lower() for item in recommendation.warnings)


def test_context_refresh_preserves_explicit_edits_even_at_recommended_value():
    service = TrainingRecommendationService()
    initial = service.recommend(_context())
    submitted = _Option(
        epoch=99,
        bs=initial.values.batch_size,
        lr=initial.values.learning_rate,
        optim="SGD",
        evaluation_option=initial.values.evaluation_strategy,
    )
    service.note_configuration_submitted(
        {
            TrainingRecommendationField.EPOCHS,
            TrainingRecommendationField.OPTIMIZER,
        }
    )

    manual = service.recommend(_context(), current_option=submitted)

    assert manual.manual_fields == (
        TrainingRecommendationField.EPOCHS,
        TrainingRecommendationField.OPTIMIZER,
    )

    changed_context = _context(model_name="braindecode.eegconformer")
    refreshed = service.recommend(changed_context, current_option=submitted)

    assert refreshed.values.epochs == 99
    assert refreshed.values.optimizer == "SGD"
    assert refreshed.values.batch_size == 16
    assert refreshed.values.learning_rate == 0.0003
    assert refreshed.context_fingerprint != initial.context_fingerprint

    reverted = _Option(
        epoch=refreshed.recommended_values.epochs,
        bs=refreshed.values.batch_size,
        lr=refreshed.values.learning_rate,
        optim="SGD",
        evaluation_option=refreshed.values.evaluation_strategy,
    )
    service.note_configuration_submitted({TrainingRecommendationField.EPOCHS})
    after_revert = service.recommend(changed_context, current_option=reverted)

    assert after_revert.values.epochs == refreshed.recommended_values.epochs
    assert after_revert.provenance[TrainingRecommendationField.EPOCHS] is (
        TrainingSettingProvenance.MANUAL
    )
    assert after_revert.provenance[TrainingRecommendationField.OPTIMIZER] is (
        TrainingSettingProvenance.MANUAL
    )

    next_context = _context(model_name="braindecode.deep4net")
    after_refresh = service.recommend(next_context, current_option=reverted)

    assert after_refresh.recommended_values.epochs == 60
    assert after_refresh.values.epochs == refreshed.recommended_values.epochs
    assert after_refresh.provenance[TrainingRecommendationField.EPOCHS] is (
        TrainingSettingProvenance.MANUAL
    )


def test_legacy_saved_option_does_not_claim_manual_provenance_on_first_read():
    service = TrainingRecommendationService()
    saved = _Option(
        epoch=120,
        bs=12,
        lr=0.002,
        optim="SGD",
        evaluation_option="Last Epoch",
    )

    recommendation = service.recommend(_context(), current_option=saved)

    assert recommendation.values == recommendation.recommended_values
    assert recommendation.manual_fields == ()


def test_submission_publishes_complete_saved_values_with_coherent_provenance():
    service = TrainingRecommendationService()
    baseline = service.recommend(_context())
    saved = _Option(
        epoch=91,
        bs=4,
        lr=0.02,
        optim="SGD",
        evaluation_option="Last Epoch",
    )

    service.note_configuration_submitted({TrainingRecommendationField.LEARNING_RATE})
    updated = service.recommend(_context(), current_option=saved)

    assert updated.values.epochs == baseline.recommended_values.epochs
    assert updated.values.batch_size == baseline.recommended_values.batch_size
    assert updated.values.learning_rate == saved.lr
    assert updated.values.optimizer == baseline.recommended_values.optimizer
    assert updated.values.evaluation_strategy == (
        baseline.recommended_values.evaluation_strategy
    )
    assert updated.recommended_values == baseline.recommended_values
    assert updated.manual_fields == (TrainingRecommendationField.LEARNING_RATE,)


def test_training_state_snapshot_publishes_typed_recommendation_as_json():
    recommendation = TrainingRecommendationService().recommend(_context())

    payload = serialize_json_value(TrainingStateSnapshot(recommendation=recommendation))

    assert payload["recommendation"]["context_fingerprint"] == (
        recommendation.context_fingerprint
    )
    assert payload["recommendation"]["values"] == {
        "epochs": 50,
        "batch_size": 32,
        "learning_rate": 0.001,
        "optimizer": "Adam",
        "evaluation_strategy": "Best validation loss",
    }
    assert payload["recommendation"]["provenance"] == {
        "epochs": "recommended",
        "batch_size": "recommended",
        "learning_rate": "recommended",
        "optimizer": "recommended",
        "evaluation_strategy": "recommended",
    }


def test_service_has_no_resource_checker_or_resource_cache_state():
    service = TrainingRecommendationService()

    first = service.recommend(_context(device="cuda:0"))
    second = service.recommend(_context(device="cuda:0"))

    assert first is second
    assert first.values.batch_size == SAFE_UNKNOWN_VRAM_BATCH_SIZE
    assert not hasattr(service, "_resource_checker")
    assert not hasattr(service, "_resource_evaluated")
