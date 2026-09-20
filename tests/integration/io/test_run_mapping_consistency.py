"""Reviewed per-recording meanings must survive real import and recipe replay."""

from __future__ import annotations

import shutil
from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)


def _write_runs(root: Path, *, same_name: bool = False) -> list[Path]:
    paths = []
    for index, run in enumerate(("04", "08")):
        folder = root / f"sub-{index + 1}"
        folder.mkdir(parents=True)
        path = folder / ("recording_raw.fif" if same_name else f"S001R{run}_raw.fif")
        raw = mne.io.RawArray(
            np.random.default_rng(index).normal(0, 1e-6, (2, 1400)),
            mne.create_info(["C3", "C4"], 100.0, ch_types="eeg"),
            verbose=False,
        )
        raw.set_annotations(
            mne.Annotations(np.arange(1, 11), [0.0] * 10, ["T1", "T2"] * 5)
        )
        raw.save(path, overwrite=True, verbose=False)
        paths.append(path)
    return paths


def test_selected_recording_does_not_include_same_named_sibling_metadata(
    tmp_path: Path,
) -> None:
    paths = _write_runs(tmp_path / "source", same_name=True)
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(
                source_path=str(tmp_path / "source"), source_hint="folder"
            )
        ).ok
        preview = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(paths[0])],
                    "skip_labels": True,
                }
            )
        )
        assert preview.ok, preview.message
        assert len(preview.state.interpretation.metadata_preview) == 1
        assert (
            preview.state.interpretation.metadata_preview[0]["subject"]["value"] == "1"
        )
        assert service.execute(ValidateInterpretationCommand()).ok
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        assert [
            str(item.get_filepath()) for item in service.study.preprocessed_data_list
        ] == [str(paths[0])]
    finally:
        service.close()


@pytest.mark.parametrize(
    "mapping_key",
    [
        "path",
        "basename",
        "run",
        "run-prefix",
        "metadata-run",
        "path-remap",
        "partial-path-remap",
    ],
)
def test_reviewed_run_mapping_survives_apply_recipe_and_epoch(
    tmp_path: Path, mapping_key: str
) -> None:
    root = tmp_path / "source"
    paths = _write_runs(
        root, same_name=mapping_key in {"metadata-run", "partial-path-remap"}
    )
    original = {path: path.read_bytes() for path in paths}
    expected = [
        {"T1": "left fist", "T2": "right fist"},
        {"T1": "both fists", "T2": "both feet"},
    ]
    keys = {
        "path": [str(path) for path in paths],
        "basename": [path.name for path in paths],
        "run": ["04", "08"],
        "run-prefix": ["run-04", "run-08"],
        "metadata-run": ["run-alpha", "run-beta"],
        "path-remap": [str(path) for path in paths],
        "partial-path-remap": [str(path) for path in paths],
    }[mapping_key]
    choices = {
        "selected_eeg_files": [str(path) for path in paths],
        "label_carrier": "embedded_events",
        "internal_event_selection": {"label_event_codes": ["T1", "T2"]},
        "run_event_mappings": dict(zip(keys, expected, strict=True)),
    }
    if mapping_key == "metadata-run":
        choices["metadata_overrides"] = {
            str(path): {"run": run}
            for path, run in zip(paths, ["alpha", "beta"], strict=True)
        }
    recipe = tmp_path / "recipe.json"
    for replay in (False, True):
        service = ApplicationService()
        try:
            if replay:
                if mapping_key in {"path-remap", "partial-path-remap"}:
                    moved = [path.with_name(f"renamed_{path.name}") for path in paths]
                    if mapping_key == "partial-path-remap":
                        moved[0] = paths[0]
                    for source, destination in zip(paths, moved, strict=True):
                        if source != destination:
                            shutil.copy2(source, destination)
                loaded = service.execute(ReloadInterpretationRecipeCommand(str(recipe)))
                assert loaded.ok, loaded.message
                if mapping_key in {"path-remap", "partial-path-remap"}:
                    remapped = service.execute(
                        PreviewInterpretationCommand(
                            choices={
                                **choices,
                                "eeg_file_remap": {
                                    str(source): str(destination)
                                    for source, destination in zip(
                                        paths, moved, strict=True
                                    )
                                    if source != destination
                                },
                            }
                        )
                    )
                    assert remapped.ok, remapped.message
                    paths = moved
            else:
                scan = service.execute(
                    ScanSourceCommand(source_path=str(root), source_hint="folder")
                )
                assert scan.ok, scan.message
                preview = service.execute(PreviewInterpretationCommand(choices=choices))
                assert preview.ok, preview.message
                review = preview.diagnostics["preview"]["internal_event_preview"][
                    "run_event_mapping_review"
                ]
                assert review["status"] == "safe"
                assert [row["events"] for row in review["files"]] == expected
            validation = service.execute(ValidateInterpretationCommand())
            assert validation.ok, validation.message
            applied = service.execute(ApplyInterpretationCommand(confirmed=True))
            assert applied.ok, applied.message
            data = service.study.preprocessed_data_list
            hints = {
                str(item.get_filepath()): item.get_runtime_detail(
                    "data_interpretation_epoch_hint"
                )["class_map"]
                for item in data
            }
            assert hints == dict(
                zip([str(path) for path in paths], expected, strict=True)
            )
            for item in data:
                source = mne.io.read_raw_fif(item.get_filepath(), verbose=False)
                np.testing.assert_array_equal(
                    item.get_mne().get_data(), source.get_data()
                )
                np.testing.assert_array_equal(
                    item.get_mne().annotations.onset, source.annotations.onset
                )
            if not replay:
                saved = service.execute(SaveInterpretationRecipeCommand(str(recipe)))
                assert saved.ok, saved.message
            epoch = service.execute(CreateEpochCommand(t_min=0.0, t_max=0.25))
            assert epoch.ok, epoch.message
            assert set(epoch.state.epoch.event_ids) == {
                label for mapping in expected for label in mapping.values()
            }
        finally:
            service.close()
    assert {path: path.read_bytes() for path in original} == original


@pytest.mark.parametrize("alias", ["basename", "run", "basename-remap"])
def test_ambiguous_alias_cannot_fill_an_unmapped_recording(
    tmp_path: Path, alias: str
) -> None:
    root = tmp_path / "source"
    paths = _write_runs(root, same_name=alias.startswith("basename"))
    remap = {}
    if alias == "basename-remap":
        destination = paths[1].with_name("renamed_raw.fif")
        shutil.copy2(paths[1], destination)
        remap[str(paths[1])] = str(destination)
    reviewed = {"T1": "left fist", "T2": "right fist"}
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(source_path=str(root), source_hint="folder")
        ).ok
        preview = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(path) for path in paths],
                    "eeg_file_remap": remap,
                    "label_carrier": "embedded_events",
                    "internal_event_selection": {"label_event_codes": ["T1", "T2"]},
                    "run_event_mappings": {
                        **({str(paths[0]): reviewed} if not remap else {}),
                        (paths[0].name if alias.startswith("basename") else "run-04"): {
                            "T1": "wrong left",
                            "T2": "wrong right",
                        },
                    },
                    "metadata_overrides": {str(path): {"run": "04"} for path in paths},
                }
            )
        )
        assert preview.ok, preview.message
        review = preview.diagnostics["preview"]["internal_event_preview"][
            "run_event_mapping_review"
        ]
        assert review["status"] == "needs_confirmation"
        assert review["files"][1]["missing_event_codes"] == ["T1", "T2"]
        if remap:
            assert review["files"][0]["missing_event_codes"] == ["T1", "T2"]
        assert service.execute(ValidateInterpretationCommand()).ok
        unconfirmed = service.execute(ApplyInterpretationCommand(confirmed=False))
        assert not unconfirmed.ok
        assert service.study.preprocessed_data_list == []
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))
        assert applied.ok, applied.message
        data = service.study.preprocessed_data_list
        assert len(data) == 2
        if remap:
            for item in data:
                assert item.get_runtime_detail("data_interpretation_epoch_hint") is None
                assert set(item.get_mne().annotations.description) == {"T1", "T2"}
        else:
            hints = {
                str(item.get_filepath()): item.get_runtime_detail(
                    "data_interpretation_epoch_hint"
                )["class_map"]
                for item in data
            }
            assert hints[str(paths[0])] == reviewed
            assert hints[str(paths[1])] == {"T1": "T1", "T2": "T2"}
        epoch = service.execute(CreateEpochCommand(t_min=0.0, t_max=0.25))
        assert not epoch.ok
        assert not epoch.state.epoch.exists
    finally:
        service.close()
