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
    "invalid_kind", ["outside_path", "conflict", "ambiguous_basename"]
)
def test_invalid_carrier_choice_identity_is_rejected_before_publication_and_can_retry(
    tmp_path: Path, invalid_kind: str
) -> None:
    root, eeg, events = _fixture(tmp_path)
    choices = _choices(eeg, events)
    valid_choices = _choices(eeg, events)
    carrier_choice = choices["label_carrier_choices"].pop(str(events))
    if invalid_kind == "outside_path":
        outside = tmp_path / "outside" / events.name
        outside.parent.mkdir()
        outside.write_bytes(events.read_bytes())
        choices["label_carrier_choices"][str(outside)] = carrier_choice
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
