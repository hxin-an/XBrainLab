"""Application boundary: interpretation admission behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.unit.backend.application.application_test_support import (
    _class_value_decisions,
    _use_test_raw_factory,
)
from tests.unit.backend.application.preprocess_test_support import (
    _minimal_raw,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ChangedState,
    CommandName,
    ErrorType,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    data_interpretation_internal_events,
)
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
)
from XBrainLab.backend.application.resource_guard import (
    ResourcePreflightResult,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study


def _apply_resource_preflight(
    risk_level: str,
    paths: list[str],
) -> ResourcePreflightResult:
    """Build a bounded import preflight response for command-path tests."""
    message = f"resource risk: {risk_level}"
    return ResourcePreflightResult(
        issues=(message,) if risk_level == "blocking" else (),
        warnings=(message,) if risk_level == "warning" else (),
        diagnostics={
            "risk_level": risk_level,
            "message": message,
            "files": [
                {
                    "path": str(Path(path).resolve()),
                    "file_bytes": Path(path).stat().st_size,
                }
                for path in paths
            ],
        },
    )


def _mutate_file_same_size(path: Path) -> None:
    with path.open("r+b") as handle:
        first_byte = handle.read(1)
        assert first_byte
        handle.seek(0)
        handle.write(bytes([first_byte[0] ^ 0x01]))


def _prepared_apply_integrity_fixture(
    tmp_path: Path,
    resource_kind: str,
) -> tuple[Path, Path]:
    if resource_kind == "selected_eeg":
        selected = tmp_path / "subject.fif"
        selected.write_bytes(b"selected EEG content")
        return selected, selected
    if resource_kind in {"brainvision_data", "brainvision_markers"}:
        fixture_root = (
            Path(__file__).resolve().parents[4]
            / "tests"
            / "fixtures"
            / "data"
            / "multiformat"
        )
        stem = "A01T-mini-real"
        for suffix in (".vhdr", ".eeg", ".vmrk"):
            source = fixture_root / f"{stem}{suffix}"
            (tmp_path / source.name).write_bytes(source.read_bytes())
        dependency = ".eeg" if resource_kind == "brainvision_data" else ".vmrk"
        return tmp_path / f"{stem}.vhdr", tmp_path / f"{stem}{dependency}"
    if resource_kind == "eeglab_fdt":
        from scipy.io import savemat

        selected = tmp_path / "subject.set"
        dependency = tmp_path / "subject-data.fdt"
        dependency.write_bytes(b"\0" * (2 * 20 * 4))
        savemat(
            selected,
            {
                "EEG": {
                    "data": dependency.name,
                    "nbchan": 2.0,
                    "pnts": 20.0,
                    "trials": 1.0,
                }
            },
            do_compression=True,
        )
        return selected, dependency
    raise AssertionError(f"Unsupported integrity fixture: {resource_kind}")


def _review_prepared_apply_candidate(
    service: ApplicationService,
    selected_eeg: Path,
    *,
    entrypoint: str,
) -> str:
    choices = {"label_carrier": "embedded_events"}
    if entrypoint == "review":
        reviewed = service.execute(
            ReviewInterpretationCommand(
                source_path=str(selected_eeg),
                choices=choices,
            )
        )
        assert reviewed.ok
        return str(reviewed.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ScanSourceCommand(source_path=str(selected_eeg))).ok
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    assert preview.ok
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    return candidate_id


def test_prepared_apply_imports_only_the_reviewed_selected_file(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "reviewed-selection"
    source_dir.mkdir()
    selected = source_dir / "selected.fif"
    sibling = source_dir / "sibling.fif"
    selected.write_bytes(b"selected EEG content")
    sibling.write_bytes(b"unselected EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(selected)],
                "skip_labels": True,
            }
        )
    )
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok

    applied = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert applied.ok
    load.assert_called_once_with(str(selected))
    assert [raw.get_filepath() for raw in service.study.loaded_data_list] == [
        str(selected)
    ]
    assert applied.diagnostics["applied_interpretation"]["loaded_files"] == [
        str(selected)
    ]


def test_prepared_apply_partial_loader_failure_preserves_active_study_data(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "partial-loader-failure"
    source_dir.mkdir()
    first = source_dir / "first.fif"
    second = source_dir / "second.fif"
    first.write_bytes(b"first reviewed EEG")
    second.write_bytes(b"second reviewed EEG")
    old_raw = _minimal_raw(tmp_path / "existing.fif")
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)

    def load(path: str) -> Raw:
        if path == str(second):
            raise RuntimeError("second recording cannot load")
        return _minimal_raw(Path(path))

    load_mock = MagicMock(side_effect=load)
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(load=load_mock)
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(first), str(second)],
                "skip_labels": True,
            }
        )
    )
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok

    failed = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert failed.failed
    assert failed.error_type is ErrorType.RUNTIME
    assert failed.diagnostics["state_preserved"] is True
    assert failed.state.interpretation.has_applied_interpretation is False
    assert study.data_manager.loaded_data_list == [old_raw]
    assert load_mock.call_args_list == [
        ((str(first),),),
        ((str(second),),),
    ]


@pytest.mark.parametrize(
    "resource_kind",
    ("selected_eeg", "brainvision_data", "brainvision_markers", "eeglab_fdt"),
)
@pytest.mark.parametrize("entrypoint", ("preview", "review"))
def test_prepared_apply_rejects_reviewed_resource_changed_before_publication(
    tmp_path: Path,
    resource_kind: str,
    entrypoint: str,
) -> None:
    selected, mutation_target = _prepared_apply_integrity_fixture(
        tmp_path,
        resource_kind,
    )
    old_raw = _minimal_raw(tmp_path / "existing.fif")
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    load = _use_test_raw_factory(service)
    candidate_id = _review_prepared_apply_candidate(
        service,
        selected,
        entrypoint=entrypoint,
    )

    _mutate_file_same_size(mutation_target)
    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert rejected.diagnostics["reason"] == "reviewed_content_or_contract_changed"
    # The two-phase path may load into a detached holder before the final
    # identity check.  The safety contract is that no changed input reaches
    # the live Study, not that the isolated loader is never entered.
    load.assert_called_once_with(str(selected))
    assert study.data_manager.loaded_data_list == [old_raw]
    assert rejected.state.interpretation.has_applied_interpretation is False


@pytest.mark.parametrize(
    "resource_kind",
    ("selected_eeg", "brainvision_data", "brainvision_markers", "eeglab_fdt"),
)
@pytest.mark.parametrize("entrypoint", ("preview", "review"))
def test_prepared_apply_rejects_reviewed_resource_changed_during_materialization(
    tmp_path: Path,
    resource_kind: str,
    entrypoint: str,
) -> None:
    selected, mutation_target = _prepared_apply_integrity_fixture(
        tmp_path,
        resource_kind,
    )
    old_raw = _minimal_raw(tmp_path / "existing.fif")
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    candidate_id = _review_prepared_apply_candidate(
        service,
        selected,
        entrypoint=entrypoint,
    )
    mutated = False

    def load(path: str) -> Raw:
        nonlocal mutated
        raw = _minimal_raw(Path(path))
        if not mutated:
            _mutate_file_same_size(mutation_target)
            mutated = True
        return raw

    load_mock = MagicMock(side_effect=load)
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(load=load_mock)

    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert rejected.diagnostics["reason"] == "reviewed_content_or_contract_changed"
    assert load_mock.call_count == 1
    assert study.data_manager.loaded_data_list == [old_raw]
    assert rejected.state.interpretation.has_applied_interpretation is False


@pytest.mark.parametrize("mutation_phase", ("before_apply", "during_detached_apply"))
def test_prepared_apply_rejects_label_content_changed_before_or_during_detached_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_phase: str,
) -> None:
    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_events.csv"
    eeg_path.write_bytes(b"reviewed EEG content")
    label_path.write_text("event_code,label\n1,left\n", encoding="utf-8")
    old_raw = _minimal_raw(tmp_path / "existing.fif")
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    _use_test_raw_factory(service)
    assert service.execute(
        ScanSourceCommand(source_path=str(eeg_path), label_sources=[str(label_path)])
    ).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "label",
                        "anchor": "event_code",
                        "placement_method": "event_code",
                        "role": "class labels",
                    }
                }
            }
        )
    )
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    if mutation_phase == "before_apply":
        _mutate_file_same_size(label_path)
    else:
        interpretation = service.interpretation
        original_detached_copy = interpretation.apply_service.detached_copy

        def detached_copy(*args: Any, **kwargs: Any) -> Any:
            detached = original_detached_copy(*args, **kwargs)
            original_apply = detached.apply_label_carriers

            def apply_then_mutate(
                *apply_args: Any,
                **apply_kwargs: Any,
            ) -> dict[str, Any]:
                result = original_apply(*apply_args, **apply_kwargs)
                _mutate_file_same_size(label_path)
                return result

            detached.apply_label_carriers = apply_then_mutate
            return detached

        monkeypatch.setattr(
            interpretation.apply_service,
            "detached_copy",
            detached_copy,
        )

    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert rejected.diagnostics["reason"] == "reviewed_content_or_contract_changed"
    assert study.data_manager.loaded_data_list == [old_raw]
    assert rejected.state.interpretation.has_applied_interpretation is False


def test_prepared_apply_warning_receipt_authorizes_one_actual_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"reviewed EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    candidate_id = _review_prepared_apply_candidate(
        service,
        eeg_path,
        entrypoint="preview",
    )
    preflight_calls = 0

    def warning_preflight(paths: list[str]) -> ResourcePreflightResult:
        nonlocal preflight_calls
        preflight_calls += 1
        return _apply_resource_preflight("warning", paths)

    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        warning_preflight,
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )

    warning = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )
    token = warning.diagnostics["resource_preflight"]["confirmation_token"]
    assert warning.failed
    assert warning.error_type is ErrorType.CONFIRMATION_REQUIRED
    load.assert_not_called()
    pending = service.execute(
        ApplyInterpretationCommand(
            candidate_id=candidate_id,
            confirmed=True,
            resource_preflight_confirmed=True,
        )
    )
    assert pending.failed
    assert pending.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert pending.diagnostics["resource_preflight"]["confirmation_token"] == token
    load.assert_not_called()
    continued = service.execute(
        ApplyInterpretationCommand(
            candidate_id=candidate_id,
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=token,
        )
    )

    assert continued.ok
    load.assert_called_once_with(str(eeg_path))
    assert continued.diagnostics["resource_preflight"]["confirmation_receipt_reused"]
    assert preflight_calls == 3


def test_prepared_apply_warning_receipt_cannot_bypass_later_blocking_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"reviewed EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    candidate_id = _review_prepared_apply_candidate(
        service,
        eeg_path,
        entrypoint="preview",
    )
    risk_level = "warning"

    def current_preflight(paths: list[str]) -> ResourcePreflightResult:
        return _apply_resource_preflight(risk_level, paths)

    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        current_preflight,
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )
    warning = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )
    token = warning.diagnostics["resource_preflight"]["confirmation_token"]
    risk_level = "blocking"

    rejected = service.execute(
        ApplyInterpretationCommand(
            candidate_id=candidate_id,
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=token,
        )
    )

    assert warning.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    load.assert_not_called()


def test_prepared_apply_warning_receipt_is_bound_to_exact_candidate_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    first = tmp_path / "first.fif"
    second = tmp_path / "second.fif"
    first.write_bytes(b"first reviewed EEG")
    second.write_bytes(b"second reviewed EEG")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    assert service.execute(ScanSourceCommand(source_path=str(tmp_path))).ok
    first_preview = service.execute(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(first)], "skip_labels": True}
        )
    )
    first_candidate_id = str(first_preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(
        ValidateInterpretationCommand(candidate_id=first_candidate_id)
    ).ok
    second_preview = service.execute(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(second)], "skip_labels": True}
        )
    )
    second_candidate_id = str(second_preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(
        ValidateInterpretationCommand(candidate_id=second_candidate_id)
    ).ok
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        lambda paths: _apply_resource_preflight("warning", paths),
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )
    warning = service.execute(
        ApplyInterpretationCommand(candidate_id=first_candidate_id, confirmed=True)
    )
    first_token = warning.diagnostics["resource_preflight"]["confirmation_token"]

    rejected = service.execute(
        ApplyInterpretationCommand(
            candidate_id=second_candidate_id,
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=first_token,
        )
    )

    assert warning.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert rejected.failed
    assert rejected.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert rejected.diagnostics["resource_preflight"]["candidate_id"] == (
        second_candidate_id
    )
    assert (
        rejected.diagnostics["resource_preflight"]["confirmation_token"] != first_token
    )
    load.assert_not_called()


def test_prepared_apply_preflight_includes_admitted_external_label_carrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    eeg_path = tmp_path / "subject.fif"
    label_path = tmp_path / "subject_events.tsv"
    eeg_path.write_bytes(b"reviewed EEG content")
    label_path.write_text("onset\ttrial_type\n0\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    assert service.execute(
        ScanSourceCommand(source_path=str(eeg_path), label_sources=[str(label_path)])
    ).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions({"left": "left"}),
                    }
                }
            }
        )
    )
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    observed_scopes: list[tuple[str, ...]] = []

    def blocking_preflight(paths: list[str]) -> ResourcePreflightResult:
        observed_scopes.append(tuple(paths))
        return _apply_resource_preflight("blocking", paths)

    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        blocking_preflight,
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )

    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert observed_scopes == [(str(eeg_path), str(label_path))]
    load.assert_not_called()


def test_prepared_apply_uses_the_target_candidates_confirmation_requirement(
    tmp_path: Path,
) -> None:
    confirmation_source = tmp_path / "needs-confirmation"
    safe_source = tmp_path / "safe"
    confirmation_source.mkdir()
    safe_source.mkdir()
    confirmation_eeg = confirmation_source / "recording_raw.fif"
    confirmation_events = confirmation_source / "recording_events.tsv"
    safe_eeg = safe_source / "sub-02_task-mi_raw.fif"
    confirmation_eeg.write_bytes(b"reviewed EEG content")
    confirmation_events.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    safe_eeg.write_bytes(b"safe reviewed EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)

    assert service.execute(ScanSourceCommand(source_path=str(confirmation_source))).ok
    confirmation_preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(confirmation_events): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions({"left": "left"}),
                    }
                }
            }
        )
    )
    confirmation_candidate_id = str(
        confirmation_preview.diagnostics["candidate"]["candidate_id"]
    )
    confirmation_validation = service.execute(
        ValidateInterpretationCommand(candidate_id=confirmation_candidate_id)
    )
    assert confirmation_validation.diagnostics["validation_decision"]["decision"] == (
        "needs_confirmation"
    )

    assert service.execute(ScanSourceCommand(source_path=str(safe_source))).ok
    safe_preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    safe_eeg.name: {
                        "subject": "02",
                        "session": "01",
                        "task": "mi",
                        "run": "1",
                    }
                }
            }
        )
    )
    safe_candidate_id = str(safe_preview.diagnostics["candidate"]["candidate_id"])
    safe_validation = service.execute(
        ValidateInterpretationCommand(candidate_id=safe_candidate_id)
    )
    assert safe_validation.diagnostics["validation_decision"]["decision"] == "safe"

    rejected = service.execute(
        ApplyInterpretationCommand(
            candidate_id=confirmation_candidate_id,
            confirmed=False,
        )
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.CONFIRMATION_REQUIRED
    load.assert_not_called()


def test_prepared_apply_confirmation_cannot_override_sequence_placement_needing_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scipy.io import savemat

    eeg_path = tmp_path / "A01T.gdf"
    label_path = tmp_path / "A01T.mat"
    eeg_path.write_bytes(b"reviewed EEG content")
    savemat(label_path, {"classlabel": [1, 2]})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {"events": {"768": {"count": 3, "description": "trial"}}},
    )
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    assert service.execute(ScanSourceCommand(source_path=str(tmp_path))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left", "2": "right"}
                        ),
                    }
                }
            }
        )
    )
    candidate_id = str(preview.diagnostics["candidate"]["candidate_id"])
    validation = service.execute(
        ValidateInterpretationCommand(candidate_id=candidate_id)
    )

    [carrier] = preview.diagnostics["candidate"]["label_carrier_plan"]
    assert carrier["placement_review"]["status"] == "needs_review"
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert "selected EEG event has no label" in rejected.message
    load.assert_not_called()


def test_prepared_apply_rejects_stale_warning_receipt_before_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"reviewed EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    candidate_id = _review_prepared_apply_candidate(
        service,
        eeg_path,
        entrypoint="preview",
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        lambda paths: _apply_resource_preflight("warning", paths),
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )
    warning = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )
    stale_token = warning.diagnostics["resource_preflight"]["confirmation_token"]
    eeg_path.write_bytes(b"reviewed EEG content changed after warning")

    rejected = service.execute(
        ApplyInterpretationCommand(
            candidate_id=candidate_id,
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=stale_token,
        )
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert (
        rejected.diagnostics["resource_preflight"]["confirmation_token"] != stale_token
    )
    load.assert_not_called()


def test_prepared_apply_blocking_preflight_never_materializes_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    eeg_path = tmp_path / "subject.fif"
    eeg_path.write_bytes(b"reviewed EEG content")
    service = ApplicationService(Study())
    load = _use_test_raw_factory(service)
    candidate_id = _review_prepared_apply_candidate(
        service,
        eeg_path,
        entrypoint="review",
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        lambda paths: _apply_resource_preflight("blocking", paths),
    )
    monkeypatch.setattr(
        data_interpretation_service,
        "_stat_change_time_is_reliable",
        lambda: False,
    )

    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    load.assert_not_called()
    assert service.study.data_manager.loaded_data_list == []


def test_apply_reuses_safe_review_preflight_and_hashes_reviewed_content_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    service = ApplicationService(Study())
    _use_test_raw_factory(service)
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok

    original_preflight = data_interpretation_service.check_import_resource_preflight
    original_identity = data_interpretation_service.DataInterpretationCommandService._reviewed_content_identity
    preflight_calls = 0
    identity_calls = 0

    def _counted_preflight(paths: list[str]) -> ResourcePreflightResult:
        nonlocal preflight_calls
        preflight_calls += 1
        return original_preflight(paths)

    def _counted_identity(candidate: Any) -> dict[str, Any]:
        nonlocal identity_calls
        identity_calls += 1
        return original_identity(candidate)

    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        _counted_preflight,
    )
    monkeypatch.setattr(
        data_interpretation_service.DataInterpretationCommandService,
        "_reviewed_content_identity",
        staticmethod(_counted_identity),
    )

    review = service.execute(
        ReviewInterpretationCommand(
            source_path=str(source_dir),
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        )
    )
    candidate_id = review.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok

    applied = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert applied.ok
    expected_preflight_calls = (
        1 if data_interpretation_service._stat_change_time_is_reliable() else 2
    )
    assert preflight_calls == expected_preflight_calls
    assert identity_calls == 1


def test_apply_invalidates_safe_review_admission_when_content_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application import data_interpretation_service

    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity a")
    study = Study()
    service = ApplicationService(study)
    _use_test_raw_factory(service)
    review = service.execute(
        ReviewInterpretationCommand(
            source_path=str(source_dir),
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        )
    )
    candidate_id = review.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    original_preflight = data_interpretation_service.check_import_resource_preflight
    preflight_calls = 0

    def _counted_preflight(paths: list[str]) -> ResourcePreflightResult:
        nonlocal preflight_calls
        preflight_calls += 1
        return original_preflight(paths)

    monkeypatch.setattr(
        data_interpretation_service,
        "check_import_resource_preflight",
        _counted_preflight,
    )
    eeg_path.write_bytes(b"reviewed EEG identity b")

    rejected = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert rejected.diagnostics["reason"] == "reviewed_content_or_contract_changed"
    assert preflight_calls == 1
    assert study.data_manager.loaded_data_list == []
    assert rejected.state.interpretation.has_applied_interpretation is False


def test_cancelled_command_fails_closed_when_rollback_state_does_not_match(
    tmp_path: Path,
) -> None:
    service = ApplicationService(Study())
    before_apply = service.get_view_publication()
    service._view_coordinator.mark_stale("ApplyInterpretation mutation in progress")
    changed_raw = _minimal_raw(tmp_path / "unreverted-cancel.fif")
    service.study.set_loaded_data_list([changed_raw], force_update=True)

    result = service._handler_failure_result(
        CommandName.APPLY_INTERPRETATION,
        before_apply.state,
        before_apply,
        OwnedOperationCancelledError(
            "operation-1",
            "Committing interpreted dataset",
        ),
    )

    assert result.failed
    assert result.error_type is ErrorType.CANCELLED
    assert "control_flow_outcome" not in result.diagnostics
    assert result.changed_state != ChangedState()
    assert result.state != before_apply.state
    assert service._last_error is not None
    assert service._last_error.error_type == ErrorType.CANCELLED.value


def test_failed_replacement_restores_raw_interpretation_and_recipe(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old_source"
    new_source = tmp_path / "new_source"
    old_source.mkdir()
    new_source.mkdir()
    old_eeg = old_source / "subject01_run1.fif"
    new_eeg = new_source / "subject02_run1.fif"
    old_eeg.write_bytes(b"old scan fixture")
    new_eeg.write_bytes(b"new scan fixture")
    recipe_path = tmp_path / "old-recipe.json"
    service = ApplicationService(Study())
    manager = service.study.data_manager

    prepared_by_path: dict[str, Raw] = {}
    for path in (old_eeg, new_eeg):
        prepared = _minimal_raw(path)
        prepared_by_path[str(path)] = prepared
    _use_test_raw_factory(service, prepared_by_path)
    service.execute(ScanSourceCommand(source_path=str(old_source)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    old_eeg.name: {
                        "subject": "subject01",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    first_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    assert first_apply.ok is True
    assert saved.ok is True
    old_raw = manager.loaded_data_list[0]
    old_interpretation_id = first_apply.state.interpretation.latest_interpretation_id
    old_recipe_id = saved.state.interpretation.latest_recipe_id

    service.execute(ScanSourceCommand(source_path=str(new_source)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    new_eeg.name: {
                        "subject": "subject02",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    interpretation = service.interpretation
    original_detached_copy = interpretation.apply_service.detached_copy

    def _failing_detached_copy(*args, **kwargs):
        detached = original_detached_copy(*args, **kwargs)
        detached.apply_candidate_metadata_to_loaded_data = MagicMock(
            side_effect=RuntimeError("replacement metadata failed"),
        )
        return detached

    interpretation.apply_service.detached_copy = _failing_detached_copy

    failed = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert failed.failed is True
    assert "replacement metadata failed" in failed.message
    assert manager.loaded_data_list == [old_raw]
    assert failed.state.interpretation.latest_interpretation_id == (
        old_interpretation_id
    )
    assert failed.state.interpretation.latest_recipe_id == old_recipe_id
    assert failed.state.interpretation.recipe_path == str(recipe_path)
    assert interpretation.state.resolve_recipe(None).recipe_id == old_recipe_id
    assert interpretation.state.resolve_recipe(None).label_imports == []
