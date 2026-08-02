"""State-lifecycle regressions for legacy raw-data compatibility commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    PreviewInterpretationCommand,
    RemoveFilesCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


def _raw(path: Path) -> Raw:
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    mne_raw = mne.io.RawArray(
        np.zeros((1, 200), dtype=np.float64),
        info,
        verbose="ERROR",
    )
    raw = Raw(str(path), mne_raw)
    raw.set_event(np.asarray([[50, 0, 1]], dtype=int), {"cue": 1})
    return raw


def _service_with_applied_interpretation(
    tmp_path: Path,
    *,
    file_count: int = 1,
) -> tuple[ApplicationService, list[Raw]]:
    source = tmp_path / "source"
    source.mkdir()
    paths = [source / f"subject-{index + 1:02d}.fif" for index in range(file_count)]
    for path in paths:
        path.write_bytes(b"scan-only fixture")
    raws = [_raw(path) for path in paths]
    raws_by_path = {raw.get_filepath(): raw for raw in raws}
    study = Study()
    service = ApplicationService(study)

    def import_files(selected_paths: list[str]) -> tuple[int, list[str]]:
        selected = [raws_by_path[path] for path in selected_paths]
        study.set_loaded_data_list(selected, force_update=True)
        return len(selected), []

    service.dataset.import_files = MagicMock(side_effect=import_files)
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    assert service.execute(PreviewInterpretationCommand()).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(tmp_path / "recipe.json"))
    )
    assert saved.ok
    assert saved.state.interpretation.has_applied_interpretation
    assert saved.state.interpretation.has_recipe
    assert saved.state.interpretation.epoch_handoff
    return service, raws


@pytest.mark.parametrize(
    "mutation",
    [
        "append",
        "replace",
        "remove",
        "metadata",
        "smart_parse",
        "attach_labels",
    ],
)
def test_legacy_raw_mutation_invalidates_interpretation_recipe_and_epoch_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    service, raws = _service_with_applied_interpretation(
        tmp_path,
        file_count=2 if mutation == "remove" else 1,
    )
    original = raws[0]

    if mutation in {"append", "replace"}:
        new_path = tmp_path / f"{mutation}.fif"
        new_path.write_bytes(b"load-only fixture")
        new_raw = _raw(new_path)

        def import_new(_paths: list[str]) -> tuple[int, list[str]]:
            active = (
                [] if mutation == "replace" else list(service.study.loaded_data_list)
            )
            service.study.set_loaded_data_list([*active, new_raw], force_update=True)
            return 1, []

        service.dataset.import_files = MagicMock(side_effect=import_new)
        command: Any = LoadDataCommand(
            paths=[str(new_path)],
            allow_append=mutation == "append",
        )
    elif mutation == "remove":
        command = RemoveFilesCommand(indices=[0])
    elif mutation == "metadata":
        command = UpdateMetadataCommand(index=0, subject="changed-subject")
    elif mutation == "smart_parse":
        command = ApplySmartParseCommand(
            results={original.get_filepath(): ("parsed-subject", "parsed-session")}
        )
    else:
        label_path = tmp_path / "labels.txt"
        label_path.write_text("1\n", encoding="utf-8")
        command = AttachLabelsCommand(
            mapping={original.get_filepath(): str(label_path)},
            label_paths=[str(label_path)],
            selected_event_names=["cue"],
        )

    result = service.execute(command)

    assert result.ok, result.message
    assert result.diagnostics["interpretation_lifecycle"] == {
        "invalidated": True,
        "reason": "legacy_raw_mutation",
    }
    interpretation = result.state.interpretation
    assert interpretation.has_scan_result is False
    assert interpretation.has_candidate is False
    assert interpretation.has_preview is False
    assert interpretation.has_validation_decision is False
    assert interpretation.has_applied_interpretation is False
    assert interpretation.has_recipe is False
    assert interpretation.latest_interpretation_id is None
    assert interpretation.latest_recipe_id is None
    assert interpretation.recipe_path is None
    assert interpretation.epoch_handoff == {}


def test_sequence_label_batch_failure_rolls_back_and_does_not_update_recipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, raws = _service_with_applied_interpretation(tmp_path, file_count=2)

    def fail_second_target(
        target: Raw,
        _labels: list[int],
        _mapping: dict[int, str],
        _selected_event_names: set[str] | None = None,
    ) -> None:
        target.set_event(np.asarray([[75, 0, 9]], dtype=int), {"changed": 9})
        target.set_labels_imported(True)
        if target.get_filepath() == raws[1].get_filepath():
            raise RuntimeError("second target failed")

    monkeypatch.setattr(
        service.dataset.label_service,
        "apply_labels_to_single_file",
        fail_second_target,
    )
    first_labels = tmp_path / "first.txt"
    second_labels = tmp_path / "second.txt"
    first_labels.write_text("1\n", encoding="utf-8")
    second_labels.write_text("2\n", encoding="utf-8")
    result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0, 1],
                label_paths=[str(first_labels), str(second_labels)],
                file_mapping={
                    raws[0].get_filepath(): str(first_labels),
                    raws[1].get_filepath(): str(second_labels),
                },
                mapping={1: "left", 2: "right"},
                mode="sequence",
            )
        )
    )

    assert result.failed
    assert result.diagnostics["success_count"] == 0
    assert result.diagnostics["expected_count"] == 2
    assert result.diagnostics["rolled_back"] is True
    assert result.state.interpretation.has_applied_interpretation is True
    assert result.state.interpretation.label_import_count == 0
    for raw in raws:
        assert raw.is_labels_imported() is False
        events, event_id = raw.get_event_list()
        np.testing.assert_array_equal(events, np.asarray([[50, 0, 1]], dtype=int))
        assert event_id == {"cue": 1}

    saved = service.execute(
        SaveInterpretationRecipeCommand(
            recipe_path=str(tmp_path / "recipe-after-failure.json")
        )
    )
    assert saved.ok
    assert saved.diagnostics["recipe"]["label_imports"] == []


def test_legacy_raw_noop_preserves_applied_interpretation(tmp_path: Path) -> None:
    service, raws = _service_with_applied_interpretation(tmp_path)

    result = service.execute(
        LoadDataCommand(paths=[raws[0].get_filepath()], allow_append=True)
    )

    assert result.ok
    assert result.diagnostics["success_count"] == 0
    assert "interpretation_lifecycle" not in result.diagnostics
    assert result.state.interpretation.has_applied_interpretation is True
    assert result.state.interpretation.has_recipe is True
    assert result.state.interpretation.epoch_handoff


def test_legacy_raw_handler_failure_invalidates_interpretation_fail_closed(
    tmp_path: Path,
) -> None:
    service, _raws = _service_with_applied_interpretation(tmp_path)
    service.dataset_state.update_metadata_batch = MagicMock(
        side_effect=RuntimeError("metadata outcome is unknown")
    )

    result = service.execute(UpdateMetadataCommand(index=0, subject="changed"))

    assert result.failed
    assert result.state.interpretation.has_applied_interpretation is False
    assert result.state.interpretation.has_recipe is False
    assert result.state.interpretation.epoch_handoff == {}


def test_legacy_raw_precondition_failure_preserves_interpretation(
    tmp_path: Path,
) -> None:
    service, _raws = _service_with_applied_interpretation(tmp_path)

    result = service.execute(RemoveFilesCommand(indices=[99]))

    assert result.failed
    assert result.state.interpretation.has_applied_interpretation is True
    assert result.state.interpretation.has_recipe is True
    assert result.state.interpretation.epoch_handoff
