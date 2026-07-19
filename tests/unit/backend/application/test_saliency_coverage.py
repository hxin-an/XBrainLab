"""Focused tests for application-owned saliency coverage projection."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from XBrainLab.backend.application.saliency_coverage import (
    SaliencyCoverageProjector,
    saliency_coverage_for_eval_record,
    saliency_label_items_from_epoch,
    saliency_method_coverage,
)
from XBrainLab.backend.application.state_service import (
    saliency_coverage_for_eval_record as compatibility_coverage_for_eval_record,
)
from XBrainLab.backend.application.state_service import (
    saliency_label_items_from_epoch as compatibility_label_items_from_epoch,
)
from XBrainLab.backend.application.state_service import (
    saliency_method_coverage as compatibility_method_coverage,
)
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.saliency_provenance import (
    SaliencyArtifactContext,
    SaliencyProducerIdentity,
)


def _saliency_context() -> SaliencyArtifactContext:
    producer = SaliencyProducerIdentity.from_components(
        dataset={"identity": "dataset"},
        split={"identity": "test"},
        run={"identity": "run-1"},
        model={"identity": "model-1"},
    )
    return SaliencyArtifactContext(
        class_map=((769, "Left hand"), (770, "Right hand")),
        channel_names=("C3", "C4"),
        sampling_frequency_hz=100.0,
        epoch_start_seconds=0.0,
        epoch_end_seconds=0.01,
        epoch_sample_count=2,
        montage_fingerprint=None,
        epoch_data_fingerprint=producer.dataset_fingerprint,
        producer_identity=producer,
    )


def _eval_record(
    *,
    gradient: dict[int, np.ndarray] | None = None,
) -> EvalRecord:
    return EvalRecord(
        label=np.array([0, 1]),
        output=np.array([[0.9, 0.1], [0.1, 0.9]]),
        gradient=gradient
        if gradient is not None
        else {
            0: np.ones((1, 2, 2), dtype=np.float32),
            1: np.full((1, 2, 2), 2.0, dtype=np.float32),
        },
        gradient_input={},
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
        saliency_context=_saliency_context(),
    )


def test_projector_preserves_method_class_and_run_coverage_contract() -> None:
    projector = SaliencyCoverageProjector()
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((769, "Left hand"), (770, "Right hand")),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={
            0: np.ones((1, 2, 2), dtype=np.float32),
            1: np.empty((0, 2, 2), dtype=np.float32),
        },
        gradient_input={
            0: np.full((1, 2, 2), 0.5, dtype=np.float32),
            1: np.full((1, 2, 2), 0.25, dtype=np.float32),
        },
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
    )

    coverage = projector.project_run(
        eval_record,
        plan_index=2,
        run_index=3,
    )

    assert (coverage.plan_index, coverage.run_index) == (2, 3)
    methods = {item.method: item for item in coverage.methods}
    assert [item.display_name for item in methods["Gradient"].classes] == [
        "Left hand",
        "Right hand",
    ]
    assert [item.available for item in methods["Gradient"].classes] == [True, False]
    assert methods["Gradient"].available is True
    assert methods["Gradient"].complete is False
    assert methods["Gradient * Input"].complete is True
    assert methods["Gradient"].classes[0].event_code == 769
    assert methods["Gradient"].classes[0].store_key == 0
    assert "Recompute" in str(methods["Gradient"].classes[1].reason)


def test_projector_does_not_guess_partial_normalized_class_keys() -> None:
    projector = SaliencyCoverageProjector()
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((769, "Left hand"), (770, "Right hand")),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={0: np.ones((1, 2, 2), dtype=np.float32)},
    )

    coverage = projector.project_method(eval_record, "Gradient")

    assert coverage.available is False
    assert [item.available for item in coverage.classes] == [False, False]
    assert [item.store_key for item in coverage.classes] == [None, None]


def test_projector_matches_partial_explicit_event_code_and_class_name() -> None:
    projector = SaliencyCoverageProjector()
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((769, "Left hand"), (770, "Right hand")),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={
            769: np.ones((1, 2, 2), dtype=np.float32),
            "Right hand": np.full((1, 2, 2), 2.0, dtype=np.float32),
        },
    )

    coverage = projector.project_method(eval_record, "Gradient")

    assert coverage.complete is True
    assert [item.store_key for item in coverage.classes] == [769, "Right hand"]


def test_epoch_label_projection_and_compatibility_helpers_preserve_behavior() -> None:
    epoch = SimpleNamespace(event_id={"Left": 7, "Right": 8})
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((7, "Left"), (8, "Right")),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={
            7: np.ones((1, 2, 2), dtype=np.float32),
            8: np.full((1, 2, 2), 2.0, dtype=np.float32),
        },
    )

    label_items = saliency_label_items_from_epoch(epoch)
    methods = saliency_coverage_for_eval_record(
        eval_record,
        label_items=label_items,
    )
    gradient = saliency_method_coverage(
        eval_record,
        "Gradient",
        label_items=label_items,
    )

    assert label_items == [(7, "Left"), (8, "Right")]
    assert gradient == methods[0]
    assert [item.display_name for item in gradient.classes] == ["Left", "Right"]
    assert gradient.complete is True


def test_projector_fails_closed_for_incompatible_context_with_arrays() -> None:
    record = _eval_record()
    record.mark_saliency_context_incompatible(
        "Saliency identity context failed its integrity check.",
    )

    gradient = SaliencyCoverageProjector().project_method(record, "Gradient")

    assert record.gradient
    assert gradient.available is False
    assert gradient.complete is False
    assert all(item.available is False for item in gradient.classes)
    assert all("integrity" in str(item.reason).lower() for item in gradient.classes)


def test_projector_rejects_explicit_integrity_failure_with_arrays() -> None:
    record = SimpleNamespace(
        saliency_context=_saliency_context(),
        saliency_context_status="verified",
        saliency_integrity_reason="manifest_tampered",
        gradient={
            0: np.ones((1, 2, 2), dtype=np.float32),
            1: np.full((1, 2, 2), 2.0, dtype=np.float32),
        },
        gradient_input={},
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
    )

    gradient = SaliencyCoverageProjector().project_method(record, "Gradient")

    assert gradient.available is False
    assert gradient.complete is False
    assert all(item.available is False for item in gradient.classes)
    assert all("integrity" in str(item.reason).lower() for item in gradient.classes)


@pytest.mark.parametrize(
    ("gradient", "reason_fragment"),
    [
        (
            {
                0: np.array([[[np.nan, 1.0], [1.0, 1.0]]], dtype=np.float32),
                1: np.ones((1, 2, 2), dtype=np.float32),
            },
            "finite",
        ),
        (
            {
                0: np.ones((2, 2), dtype=np.float32),
                1: np.ones((1, 2, 2), dtype=np.float32),
            },
            "shape",
        ),
        (
            {
                0: np.ones((1, 2, 3), dtype=np.float32),
                1: np.ones((1, 2, 2), dtype=np.float32),
            },
            "sample",
        ),
        (
            {
                0: np.ones((1, 3, 2), dtype=np.float32),
                1: np.ones((1, 2, 2), dtype=np.float32),
            },
            "channel",
        ),
    ],
)
def test_projector_fails_closed_for_invalid_saliency_payload_contract(
    gradient: dict[int, np.ndarray],
    reason_fragment: str,
) -> None:
    record = SimpleNamespace(
        saliency_context=_saliency_context(),
        saliency_context_status="verified",
        gradient=gradient,
        gradient_input={},
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
    )

    coverage = SaliencyCoverageProjector().project_method(record, "Gradient")

    assert coverage.available is False
    assert coverage.complete is False
    assert all(item.available is False for item in coverage.classes)
    assert all(reason_fragment in str(item.reason).lower() for item in coverage.classes)


def test_state_service_compatibility_exports_point_to_projector_owner() -> None:
    assert compatibility_coverage_for_eval_record is saliency_coverage_for_eval_record
    assert compatibility_label_items_from_epoch is saliency_label_items_from_epoch
    assert compatibility_method_coverage is saliency_method_coverage


def test_saliency_coverage_module_has_no_cold_matplotlib_import() -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import XBrainLab.backend.application.saliency_coverage; "
                "import XBrainLab.backend.application.query_state_service; "
                "import XBrainLab.backend.application.state_service; "
                "assert not any(name == 'matplotlib' or "
                "name.startswith('matplotlib.') for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
