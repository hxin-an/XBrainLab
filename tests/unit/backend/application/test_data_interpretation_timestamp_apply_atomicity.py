"""Failure contracts for reviewed timestamp-label application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.data_interpretation_apply import (
    DataInterpretationApplyService,
    TimestampLabelStateUnknownError,
)
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.label_resource_admission import (
    LabelResourceAdmissionService,
    LabelResourceSpec,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.services.label_import_service import (
    AtomicLabelApplyError,
    AtomicLabelRollbackFailure,
    AtomicLabelStateUnknownError,
    LabelImportService,
)


class _Dataset:
    def __init__(self, loaded: list[Any]) -> None:
        self.loaded = loaded
        self.batch_calls = 0

    def get_loaded_data_list(self) -> list[Any]:
        return self.loaded

    def apply_labels_batch(self, *_args: Any, **_kwargs: Any) -> int:
        self.batch_calls += 1
        return 1


class _UnsupportedTimestampTarget:
    pass


def _service(dataset: _Dataset) -> DataInterpretationApplyService:
    return DataInterpretationApplyService(
        dataset,
        data_filename=lambda item: item.get_filename(),
        data_filepath=lambda item: item.get_filepath(),
        record_label_import=lambda **_kwargs: None,
    )


def _raw(path: str) -> Raw:
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = Raw(
        path,
        mne.io.RawArray(np.zeros((1, 200)), info, verbose=False),
    )
    raw.set_event(np.array([[25, 0, 1]]), {"original": 1})
    return raw


def test_timestamp_commit_with_incomplete_rollback_marks_state_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [_raw("/data/first.fif"), _raw("/data/second.fif")]
    service = _service(_Dataset(targets))

    def stage_labels(
        _label_service: LabelImportService,
        staged: Raw,
        *_args: Any,
    ) -> None:
        staged.set_event(np.array([[75, 0, 9]]), {"changed": 9})
        staged.set_labels_imported(True)

    monkeypatch.setattr(
        LabelImportService,
        "apply_labels_to_single_file",
        stage_labels,
    )
    original_replace = LabelImportService._replace_raw_label_state
    replace_calls = 0

    def fail_commit_then_rollback(target: Raw, source: Raw) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise RuntimeError("second target commit failed")
        if replace_calls == 3:
            raise RuntimeError("first target rollback failed")
        original_replace(target, source)

    monkeypatch.setattr(
        LabelImportService,
        "_replace_raw_label_state",
        staticmethod(fail_commit_then_rollback),
    )
    prepared = [
        (
            target,
            target.get_filepath(),
            f"/labels/{index}.csv",
            {"left": "Left hand"},
            [{"onset": 0.75, "duration": 0.0, "label": "left"}],
        )
        for index, target in enumerate(targets)
    ]

    with pytest.raises(AtomicLabelStateUnknownError) as error:
        service._apply_timestamp_targets_atomically(prepared)

    assert error.value.state_unknown is True
    assert error.value.recoverable is False
    assert "second target commit failed" in str(error.value)
    assert "first target rollback failed" in str(error.value)
    assert replace_calls == 4
    assert targets[0].is_labels_imported() is True


def test_timestamp_apply_rejects_runtime_without_atomic_staging() -> None:
    target = _UnsupportedTimestampTarget()
    dataset = _Dataset([target])
    service = _service(dataset)
    prepared = [
        (
            target,
            "/data/unsupported.eeg",
            "/labels/unsupported.csv",
            {"left": "Left hand"},
            [{"onset": 0.75, "duration": 0.0, "label": "left"}],
        )
    ]

    with pytest.raises(TypeError, match="Raw"):
        service._apply_timestamp_targets_atomically(prepared)

    assert dataset.batch_calls == 0


def test_timestamp_internal_preparation_error_is_not_exposed_to_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _raw("/data/subject.fif")

    def fail_preparation(
        _label_service: LabelImportService,
        _target: Raw,
        *_args: Any,
    ) -> None:
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(
        LabelImportService,
        "apply_labels_to_single_file",
        fail_preparation,
    )

    with pytest.raises(AtomicLabelApplyError) as error:
        LabelImportService().apply_timestamp_labels_atomically(
            [
                (
                    target,
                    [{"onset": 0.75, "duration": 0.0, "label": "left"}],
                    {"left": "Left hand"},
                )
            ]
        )

    assert error.value.error_code == "label_application_failed"
    assert error.value.phase == "preparation"
    assert error.value.user_message == (
        "Reviewed labels could not be applied safely; no labels were changed."
    )
    assert "private implementation detail" not in error.value.user_message
    assert target.is_labels_imported() is False


def test_public_timestamp_apply_preserves_nonrecoverable_state_unknown_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_labels.csv"
    label_path.write_text("onset,label\n0.75,left\n", encoding="utf-8")
    plan = {
        "path": str(label_path),
        "name": label_path.name,
        "format": "CSV",
        "selected_target_file": str(eeg_path),
        "selected_label_field": "label",
        "selected_anchor": "onset",
        "selected_duration_field": "",
        "time_model": "seconds",
        "placement_method": "time_field",
        "granularity": "event",
        "placement_review": {"status": "ready"},
        "value_decisions": {
            "left": {
                "decision": "resolved",
                "keep_event": True,
                "role": "stimulus",
                "use_as_class": True,
                "class_name": "Left hand",
            }
        },
        "run_class_map": {"left": "Left hand"},
    }
    candidate = InterpretationCandidate(
        candidate_id="candidate-atomicity",
        scan_id="scan-atomicity",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(eeg_path)],
        label_carriers=[str(label_path)],
        label_carrier_plan=[plan],
        class_map={"left": "Left hand"},
    )
    target = _raw(str(eeg_path))
    service = _service(_Dataset([target]))
    resources = LabelResourceAdmissionService(
        command_name="test_timestamp_atomicity"
    ).admit(
        [
            LabelResourceSpec(
                path=str(label_path),
                label_field="label",
                anchor="onset",
            )
        ],
        confirmed=False,
        token=None,
    )
    atomic_error = AtomicLabelStateUnknownError(
        operation_name="reviewed timestamp label batch",
        commit_error=RuntimeError("second target commit failed"),
        rollback_failures=[
            AtomicLabelRollbackFailure(
                target_path=str(eeg_path),
                exception_type="RuntimeError",
                message="first target rollback failed",
            )
        ],
    )

    def fail_atomic_apply(
        _label_service: LabelImportService,
        _operations: Any,
        *,
        operation_name: str = "reviewed timestamp label batch",
    ) -> int:
        assert operation_name == "reviewed timestamp label batch"
        raise atomic_error

    monkeypatch.setattr(
        LabelImportService,
        "apply_timestamp_labels_atomically",
        fail_atomic_apply,
    )

    with pytest.raises(TimestampLabelStateUnknownError) as error:
        service.apply_label_carriers(candidate, resources)

    assert error.value.recoverable is False
    assert error.value.diagnostics["state_unknown"] is True
    assert error.value.diagnostics["retryable"] is False
    assert error.value.diagnostics["command_effect_may_have_applied"] is True
    assert error.value.diagnostics["rollback_failures"] == [
        {
            "target_path": str(eeg_path),
            "exception_type": "RuntimeError",
            "message": "first target rollback failed",
        }
    ]
