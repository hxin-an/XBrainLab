"""Real Command regressions for event metadata and explicit carrier identity."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from tests.integration.io.test_bids_timestamp_label_field import (
    _choices,
    _write_brainvision_bids_with_generic_flash_codes,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root, eeg, events = _write_brainvision_bids_with_generic_flash_codes(
        tmp_path.resolve()
    )
    eeg.with_suffix(".eeg").write_bytes(
        np.arange(2_000, dtype="<f4").reshape(1_000, 2).tobytes()
    )
    return root, eeg, events


def _assert_applied_labels(service: ApplicationService) -> None:
    validation = service.execute(ValidateInterpretationCommand())
    assert validation.ok, validation.message
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok, applied.message
    assert len(service.study.loaded_data_list) == 1
    raw = service.study.loaded_data_list[0]
    events, event_id = raw.get_event_list()
    actual = {
        label: events[events[:, 2] == event_id[label], 0].tolist()
        for label in ("Target 0", "Target 1")
    }
    assert actual == {"Target 0": [100], "Target 1": [300]}
    np.testing.assert_array_equal(
        raw.get_mne().get_data(),
        np.arange(2_000, dtype="<f4").reshape(1_000, 2).T.astype(float) * 1e-6,
    )


@pytest.mark.parametrize(
    ("local_field", "expected_names"),
    [
        (None, {"0": "Root A", "1": "Root B"}),
        ({"Description": "Local definition without names."}, {}),
        ({"Levels": {}}, {}),
        ({"Levels": {"0": "Local A"}}, {"0": "Local A"}),
    ],
)
def test_bids_preview_uses_overriding_field_definition_for_level_suggestions(
    tmp_path: Path, local_field: dict | None, expected_names: dict[str, str]
) -> None:
    root, eeg, events = _fixture(tmp_path)
    (root / "task-cvep_events.json").write_text(
        json.dumps({"trial_id": {"Levels": {"0": "Root A", "1": "Root B"}}}),
        encoding="utf-8",
    )
    local_metadata = {"duration": {"Description": "Unrelated local field."}}
    if local_field is not None:
        local_metadata["trial_id"] = local_field
    events.with_suffix(".json").write_text(json.dumps(local_metadata), encoding="utf-8")
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        plan = preview.diagnostics["candidate"]["label_carrier_plan"][0]
        assert plan["selected_label_field_levels_available"] is bool(expected_names)
        for code in ("0", "1"):
            assert plan["value_decisions"][code][
                "suggested_name"
            ] == expected_names.get(code, code)
        assert preview.state.interpretation.class_map == {
            "0": "Target 0",
            "1": "Target 1",
        }
        _assert_applied_labels(service)
    finally:
        service.close()


def _write_level_names(path: Path, prefix: str) -> None:
    path.write_text(
        json.dumps({"trial_id": {"Levels": {"0": f"{prefix} A", "1": f"{prefix} B"}}}),
        encoding="utf-8",
    )


def _entity_subset_fixture(tmp_path: Path, variant: str):
    root, eeg, events = _fixture(tmp_path)
    old = "sub-01_task-cvep"
    new = old + ("_acq-hi_run-1" if variant == "acquisition" else "_run-1")
    events.with_suffix(".json").unlink()
    for path in list(eeg.parent.iterdir()):
        if path.suffix in {".vhdr", ".vmrk"}:
            path.write_text(
                path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
            )
        path.rename(path.with_name(path.name.replace(old, new)))
    eeg = eeg.with_name(eeg.name.replace(old, new))
    events = events.with_name(events.name.replace(old, new))
    metadata = root / "task-cvep_events.json"
    _write_level_names(metadata, "Root")
    prefix = "Root"
    if variant == "subject":
        metadata = root / "sub-01" / "sub-01_task-cvep_events.json"
        prefix = "Subject"
        _write_level_names(metadata, prefix)
    return root, eeg, events, metadata, prefix


def _assert_no_publication(service: ApplicationService, applied) -> None:
    assert not applied.ok, applied.message
    assert not applied.changed_state.raw_changed
    assert not applied.changed_state.preprocessed_changed
    summary = service.execute(QueryStateCommand(query="data_summary"))
    assert summary.ok, summary.message
    assert summary.diagnostics["count"] == 0


@pytest.mark.parametrize("variant", ["subject", "acquisition"])
def test_entity_subset_json_suggestions_preserve_explicit_classes_and_signal(
    tmp_path: Path, variant: str
) -> None:
    root, eeg, events, _metadata, prefix = _entity_subset_fixture(tmp_path, variant)
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        plan = preview.diagnostics["candidate"]["label_carrier_plan"][0]
        assert {
            code: plan["value_decisions"][code]["suggested_name"] for code in ("0", "1")
        } == {"0": f"{prefix} A", "1": f"{prefix} B"}
        assert preview.state.interpretation.class_map == {
            "0": "Target 0",
            "1": "Target 1",
        }
        _assert_applied_labels(service)
    finally:
        service.close()


@pytest.mark.parametrize("variant", ["subject", "acquisition", "recognized_control"])
def test_entity_subset_json_mutation_after_validation_refuses_publication(
    tmp_path: Path, variant: str
) -> None:
    root, eeg, events, metadata, _prefix = _entity_subset_fixture(tmp_path, variant)
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        validated = service.execute(ValidateInterpretationCommand())
        assert validated.ok, validated.message
        assert not validated.state.interpretation.blocked_reasons
        directory_mtime = metadata.parent.stat().st_mtime_ns
        _write_level_names(metadata, "Modified")
        assert metadata.parent.stat().st_mtime_ns == directory_mtime
        _assert_no_publication(
            service, service.execute(ApplyInterpretationCommand(confirmed=True))
        )
    finally:
        service.close()


@pytest.mark.parametrize("variant", ["subject", "acquisition"])
def test_new_applicable_json_after_validation_refuses_publication(
    tmp_path: Path, variant: str
) -> None:
    root, eeg, events, metadata, _prefix = _entity_subset_fixture(tmp_path, variant)
    metadata.unlink()
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        validated = service.execute(ValidateInterpretationCommand())
        assert validated.ok, validated.message
        assert not validated.state.interpretation.blocked_reasons
        _write_level_names(metadata, "New")
        _assert_no_publication(
            service, service.execute(ApplyInterpretationCommand(confirmed=True))
        )
    finally:
        service.close()


def test_same_level_applicable_json_ambiguity_cannot_publish(tmp_path: Path) -> None:
    root, eeg, events, _metadata, _prefix = _entity_subset_fixture(
        tmp_path, "recognized_control"
    )
    _write_level_names(root / "events.json", "Generic")
    service = ApplicationService()
    try:
        catalog = service.execute(
            ScanSourceCommand(str(root), source_hint="bids", catalog_only=True)
        )
        assert catalog.ok, catalog.message
        scan = service.execute(ScanSourceCommand(str(root), source_hint="bids"))
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        validated = service.execute(ValidateInterpretationCommand())
        assert (
            not scan.ok
            or not preview.ok
            or not validated.ok
            or validated.state.interpretation.blocked_reasons
        ), "Two applicable JSON sidecars at one directory level must not validate"
        failures = " ".join(
            f"{result.message} {result.diagnostics} "
            f"{result.state.interpretation.blocked_reasons}"
            for result in (scan, preview, validated)
        )
        assert "ambiguous" in failures.lower()
        _assert_no_publication(
            service, service.execute(ApplyInterpretationCommand(confirmed=True))
        )
    finally:
        service.close()


@pytest.mark.parametrize(
    "seam", ["prepare_apply_interpretation", "verify_prepared_apply_content"]
)
def test_new_json_during_detached_prepare_cannot_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seam: str
) -> None:
    from XBrainLab.backend.application.data_interpretation_service import (
        DataInterpretationCommandService,
    )

    root, eeg, events, _metadata, _prefix = _entity_subset_fixture(
        tmp_path, "recognized_control"
    )
    new_metadata = root / "sub-01" / "sub-01_task-cvep_events.json"
    original = getattr(DataInterpretationCommandService, seam)
    prepared_calls = []

    def prepare_then_add_json(self, plan):
        prepared = original(self, plan)
        _write_level_names(new_metadata, "New during prepare")
        prepared_calls.append(prepared)
        return prepared

    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        assert service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        ).ok
        validated = service.execute(ValidateInterpretationCommand())
        assert validated.ok and not validated.state.interpretation.blocked_reasons
        monkeypatch.setattr(
            DataInterpretationCommandService,
            seam,
            prepare_then_add_json,
        )
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert len(prepared_calls) == 1, "The real detached loader must complete"
        _assert_no_publication(service, applied)
    finally:
        service.close()


def test_unselected_subject_json_ambiguity_does_not_block_selected_run(
    tmp_path: Path,
) -> None:
    root, eeg, events, _metadata, _prefix = _entity_subset_fixture(
        tmp_path, "recognized_control"
    )
    other_directory = root / "sub-02" / "eeg"
    shutil.copytree(eeg.parent, other_directory)
    for path in list(other_directory.iterdir()):
        if path.suffix in {".vhdr", ".vmrk"}:
            path.write_text(
                path.read_text(encoding="utf-8").replace("sub-01", "sub-02"),
                encoding="utf-8",
            )
        path.rename(path.with_name(path.name.replace("sub-01", "sub-02")))
    for name in ("events.json", "task-cvep_events.json"):
        _write_level_names(other_directory / name, "Other subject")
    service = ApplicationService()
    try:
        catalog = service.execute(
            ScanSourceCommand(str(root), source_hint="bids", catalog_only=True)
        )
        assert catalog.ok, catalog.message
        scanned = service.execute(
            ScanSourceCommand(
                str(root), source_hint="bids", selected_bids_subjects=["01"]
            )
        )
        assert scanned.ok, scanned.message
        assert scanned.diagnostics["scan_result"]["eeg_files"] == [str(eeg)]
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        _assert_applied_labels(service)
    finally:
        service.close()


@pytest.mark.parametrize(
    "unrelated",
    [
        "task-other_events.json",
        "sub-02_task-cvep_events.json",
        "task-cvep_acq-lo_events.json",
        "sub-02/sub-02_task-cvep_events.json",
    ],
)
def test_unrelated_json_does_not_change_selected_review_or_block_apply(
    tmp_path: Path, unrelated: str
) -> None:
    root, eeg, events, _metadata, _prefix = _entity_subset_fixture(
        tmp_path, "recognized_control"
    )
    other = root / unrelated
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("invalid JSON must not be read", encoding="utf-8")
    service = ApplicationService()
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(
            PreviewInterpretationCommand(choices=_choices(eeg, events))
        )
        assert preview.ok, preview.message
        plan = preview.diagnostics["candidate"]["label_carrier_plan"][0]
        assert {
            code: plan["value_decisions"][code]["suggested_name"] for code in ("0", "1")
        } == {"0": "Root A", "1": "Root B"}
        assert preview.state.interpretation.class_map == {
            "0": "Target 0",
            "1": "Target 1",
        }
        validated = service.execute(ValidateInterpretationCommand())
        assert validated.ok, validated.message
        assert not validated.state.interpretation.blocked_reasons
        other.write_text("different invalid JSON, still unrelated", encoding="utf-8")
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        summary = service.execute(QueryStateCommand(query="data_summary"))
        assert summary.ok and summary.diagnostics["count"] == 1
        loaded = service.study.loaded_data_list[0]
        observed, classes = loaded.get_event_list()
        assert observed[:, 0].tolist() == [100, 300]
        assert classes == {"Target 0": 1, "Target 1": 2}
        np.testing.assert_array_equal(
            loaded.get_mne().get_data(),
            np.arange(2_000, dtype="<f4").reshape(1_000, 2).T.astype(float) * 1e-6,
        )
    finally:
        service.close()


@pytest.mark.parametrize(
    "key_kind", ["resolved_alias", "basename", "matching_aliases", "known_unselected"]
)
def test_alias_carrier_choices_preserve_reviewed_classes_and_recipe(
    tmp_path: Path, key_kind: str
) -> None:
    root, eeg, events = _fixture(tmp_path)
    (root / "alias-prefix").mkdir()
    alias = root / "alias-prefix" / ".." / events.relative_to(root)
    choices = _choices(eeg, events)
    carrier_choice = choices["label_carrier_choices"].pop(str(events))
    key = events.name if key_kind == "basename" else str(alias)
    choices["label_carrier_choices"][key] = carrier_choice
    if key_kind == "matching_aliases":
        choices["label_carrier_choices"][str(events)] = dict(carrier_choice)
    elif key_kind == "known_unselected":
        duplicate = root / "sub-01" / "ses-02" / "eeg"
        shutil.copytree(events.parent, duplicate)
        for source in duplicate.iterdir():
            renamed = source.with_name(
                source.name.replace("_task-cvep", "_task-cvep_run-2")
            )
            source.rename(renamed)
            if renamed.suffix in {".vhdr", ".vmrk"}:
                renamed.write_text(
                    renamed.read_text(encoding="utf-8").replace(
                        "_task-cvep", "_task-cvep_run-2"
                    ),
                    encoding="utf-8",
                )
        other_events = duplicate / events.name.replace("_task-cvep", "_task-cvep_run-2")
        choices["label_carrier_choices"][str(other_events)] = {
            **carrier_choice,
            "label_field": "trial_type",
        }
    service = ApplicationService()
    recipe = tmp_path / "recipe.json"
    try:
        assert service.execute(ScanSourceCommand(str(root), source_hint="bids")).ok
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        assert preview.ok, preview.message
        assert preview.state.interpretation.class_map == {
            "0": "Target 0",
            "1": "Target 1",
        }
        plan = preview.diagnostics["candidate"]["label_carrier_plan"][0]
        assert Path(plan["path"]) == events
        _assert_applied_labels(service)
        saved = service.execute(SaveInterpretationRecipeCommand(str(recipe)))
        assert saved.ok, saved.message
    finally:
        service.close()
    replay = ApplicationService()
    try:
        loaded = replay.execute(ReloadInterpretationRecipeCommand(str(recipe)))
        assert loaded.ok, loaded.message
        _assert_applied_labels(replay)
    finally:
        replay.close()


@pytest.mark.parametrize(
    "invalid_kind",
    ["outside_path", "outside_required", "conflict", "ambiguous_basename"],
)
def test_invalid_carrier_choice_identity_is_rejected_before_publication_and_can_retry(
    tmp_path: Path, invalid_kind: str
) -> None:
    root, eeg, events = _fixture(tmp_path)
    choices = _choices(eeg, events)
    valid_choices = _choices(eeg, events)
    carrier_choice = choices["label_carrier_choices"].pop(str(events))
    if invalid_kind in {"outside_path", "outside_required"}:
        outside = tmp_path / "outside" / events.name
        outside.parent.mkdir()
        outside.write_bytes(events.read_bytes())
        choices["label_carrier_choices"][str(outside)] = carrier_choice
        if invalid_kind == "outside_required":
            choices["required_label_carriers"] = [str(outside)]
    elif invalid_kind == "conflict":
        choices["label_carrier_choices"][str(events)] = carrier_choice
        choices["label_carrier_choices"][events.name] = {
            **carrier_choice,
            "label_field": "trial_type",
        }
    else:
        duplicate = root / "sub-01" / "ses-02" / "eeg"
        shutil.copytree(events.parent, duplicate)
        choices["label_carrier_choices"][events.name] = carrier_choice
    service = ApplicationService()
    try:
        scanned = service.execute(ScanSourceCommand(str(root), source_hint="bids"))
        assert scanned.ok, scanned.message
        preview = service.execute(PreviewInterpretationCommand(choices=choices))
        assert not preview.ok
        assert preview.state.interpretation == scanned.state.interpretation
        assert service.study.loaded_data_list == []
        assert preview.diagnostics["label_carrier_choices"]["code"] in {
            "unbound_choice",
            "conflicting_choices",
            "ambiguous_choice",
        }
        retry = service.execute(PreviewInterpretationCommand(choices=valid_choices))
        assert retry.ok, retry.message
        _assert_applied_labels(service)
    finally:
        service.close()
