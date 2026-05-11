"""Focused tests for the Data Interpretation command coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    LabelImportPlan,
    PreviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.data_interpretation_service import (
    DataInterpretationCommandService,
    HandlerResult,
)


class _LoadedData:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.subject = ""
        self.session = ""
        self.runtime_details: dict[str, dict[str, str]] = {}

    def get_filepath(self) -> str:
        return self.filepath

    def get_filename(self) -> str:
        return Path(self.filepath).name

    def set_subject_name(self, subject: str) -> None:
        self.subject = subject

    def set_session_name(self, session: str) -> None:
        self.session = session

    def set_runtime_detail(self, name: str, detail: dict[str, str]) -> None:
        self.runtime_details[name] = detail


class _DatasetController:
    def __init__(self) -> None:
        self.loaded: list[_LoadedData] = []
        self.imported_paths: list[str] = []
        self.notifications: list[str] = []

    def import_files(self, paths: list[str]) -> tuple[int, list[str]]:
        self.imported_paths = list(paths)
        self.loaded = [_LoadedData(path) for path in paths]
        return len(paths), []

    def get_loaded_data_list(self) -> list[_LoadedData]:
        return list(self.loaded)

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)

    def apply_labels_batch(
        self,
        _target_files: list[Any],
        _label_map: dict[str, Any],
        _file_mapping: dict[str, str],
        _mapping: Any,
        _selected_event_names: set[str] | None,
    ) -> int:
        return 1

    def apply_labels_legacy(
        self,
        _target_files: list[Any],
        _labels: Any,
        _mapping: Any,
        _selected_event_names: set[str] | None,
        *,
        force_import: bool = False,
    ) -> int:
        return 1


def _data_filename(data: Any) -> str:
    get_filename = getattr(data, "get_filename", None)
    if callable(get_filename):
        return str(get_filename())
    return Path(_data_filepath(data)).name


def _data_filepath(data: Any) -> str:
    get_filepath = getattr(data, "get_filepath", None)
    if callable(get_filepath):
        return str(get_filepath())
    return str(getattr(data, "filepath", ""))


def _service() -> tuple[DataInterpretationCommandService, _DatasetController]:
    dataset = _DatasetController()
    return (
        DataInterpretationCommandService(
            dataset,
            data_filename=_data_filename,
            data_filepath=_data_filepath,
        ),
        dataset,
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_scan_preview_validate_and_clear_are_owned_by_interpretation_service(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    events_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service, _dataset = _service()

    _scan_message, scan_payload = _expect_payload(
        service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir))),
    )
    _preview_message, preview_payload = _expect_payload(
        service.handle_preview_interpretation(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(events_path): {
                            "label_field": "trial_type",
                            "anchor": "onset",
                            "time_model": "seconds",
                            "granularity": "trial",
                        },
                    },
                    "class_map": {"left": "left hand"},
                },
            ),
        ),
    )
    _validation_message, validation_payload = _expect_payload(
        service.handle_validate_interpretation(ValidateInterpretationCommand()),
    )
    snapshot = service.snapshot()

    assert scan_payload["payload_type"] == "scan_result"
    assert scan_payload["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert scan_payload["scan_result"]["label_carriers"] == [str(events_path)]
    assert preview_payload["payload_type"] == "interpretation_preview"
    assert preview_payload["preview"]["label_carrier_count"] == 1
    assert validation_payload["payload_type"] == "validation_decision"
    assert validation_payload["validation_decision"]["decision"] == (
        "needs_confirmation"
    )
    assert snapshot.has_scan_result is True
    assert snapshot.has_candidate is True
    assert snapshot.has_preview is True
    assert snapshot.has_validation_decision is True
    assert snapshot.pending_confirmation is True
    assert snapshot.class_map == {"left": "left hand"}

    service.clear()

    cleared = service.snapshot()
    assert cleared.has_scan_result is False
    assert cleared.has_candidate is False
    assert cleared.has_preview is False
    assert cleared.has_validation_decision is False


def test_apply_metadata_and_label_import_recipe_state_stay_together(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "metadata_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    label_path = tmp_path / "subject01_run1_events.tsv"
    recipe_path = tmp_path / "recipe.json"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    service, dataset = _service()

    service.handle_scan_source(ScanSourceCommand(source_path=str(source_dir)))
    service.handle_preview_interpretation(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    eeg_path.name: {
                        "subject": "S01",
                        "session": "session-01",
                        "task": "motor-imagery",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.handle_validate_interpretation(ValidateInterpretationCommand())
    _apply_message, apply_payload = _expect_payload(
        service.handle_apply_interpretation(ApplyInterpretationCommand(confirmed=True)),
    )
    service.handle_save_interpretation_recipe(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    loaded = dataset.loaded[0]
    plan = LabelImportPlan(
        target_indices=[0],
        label_map={str(label_path): [{"onset": 0.0, "label": "left"}]},
        mapping={"left": "left hand"},
        file_mapping={str(eeg_path): str(label_path)},
        mode="timestamp",
    )
    record = service.record_label_import_for_recipe(
        plan=plan,
        mode="timestamp",
        target_files=[loaded],
        file_mapping={str(eeg_path): str(label_path)},
        selected_event_names=None,
        success_count=1,
    )
    snapshot = service.snapshot()

    assert apply_payload["metadata_apply"] == [
        {
            "file": eeg_path.name,
            "subject": "S01",
            "session": "session-01",
            "task": "motor-imagery",
            "run": "1",
        }
    ]
    assert loaded.subject == "S01"
    assert loaded.session == "session-01"
    assert loaded.runtime_details["data_interpretation_metadata"]["task"] == (
        "motor-imagery"
    )
    assert "data_changed" in dataset.notifications
    assert record is not None
    assert record["mode"] == "timestamp"
    assert snapshot.has_applied_interpretation is True
    assert snapshot.has_recipe is True
    assert snapshot.label_import_count == 1
    assert snapshot.label_imports[0]["class_map"] == {"left": "left hand"}
