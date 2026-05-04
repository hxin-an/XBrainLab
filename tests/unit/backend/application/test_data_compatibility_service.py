"""Focused tests for legacy data/label compatibility command handlers."""

from __future__ import annotations

from typing import Any, cast

from XBrainLab.backend.application.commands import (
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
)
from XBrainLab.backend.application.data_compatibility_service import (
    DataCompatibilityCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.results import ErrorType


class _Raw:
    def __init__(self, filepath: str, filename: str | None = None) -> None:
        self.filepath = filepath
        self.filename = filename or filepath.rsplit("/", 1)[-1]

    def get_filepath(self) -> str:
        return self.filepath

    def get_filename(self) -> str:
        return self.filename


class _DatasetController:
    def __init__(self) -> None:
        self.import_result: tuple[int, list[str]] = (0, [])
        self.loaded_data: list[Any] = []
        self.batch_calls: list[tuple[Any, ...]] = []
        self.legacy_calls: list[tuple[Any, ...]] = []

    def import_files(self, paths: list[str]) -> tuple[int, list[str]]:
        self.import_paths = paths
        return self.import_result

    def get_loaded_data_list(self) -> list[Any]:
        return self.loaded_data

    def apply_labels_batch(self, *args: Any) -> int:
        self.batch_calls.append(args)
        return 1

    def apply_labels_legacy(self, *args: Any, **kwargs: Any) -> int:
        self.legacy_calls.append((*args, kwargs))
        return 1


class _InterpretationCommands:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_label_import_for_recipe(self, **kwargs: Any) -> dict[str, Any]:
        self.recorded.append(kwargs)
        return {
            "mode": kwargs["mode"],
            "target_files": [raw.get_filepath() for raw in kwargs["target_files"]],
            "selected_event_names": kwargs["selected_event_names"],
        }


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[
    DataCompatibilityCommandService,
    _DatasetController,
    _InterpretationCommands,
]:
    dataset = _DatasetController()
    interpretation = _InterpretationCommands()
    return (
        DataCompatibilityCommandService(dataset=dataset, interpretation=interpretation),
        dataset,
        interpretation,
    )


def test_data_compatibility_service_maps_load_failures_to_typed_error() -> None:
    service, dataset, _interpretation = _service()
    dataset.import_result = (0, ["Unsupported format: sample.xyz"])

    try:
        service.handle_load_data(LoadDataCommand(paths=["sample.xyz"]))
    except ApplicationError as error:
        assert error.error_type == ErrorType.UNSUPPORTED_FORMAT
        assert error.diagnostics == {
            "success_count": 0,
            "errors": ["Unsupported format: sample.xyz"],
        }
    else:
        raise AssertionError("Expected unsupported-format ApplicationError")


def test_data_compatibility_service_attaches_labels_with_default_event_names(
    monkeypatch: Any,
) -> None:
    service, dataset, _interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif", "sub-01_raw.fif")
    dataset.loaded_data = [raw]
    monkeypatch.setattr(
        "XBrainLab.backend.application.data_compatibility_service.load_label_file",
        lambda path: [1, 2, 1],
    )

    message, payload = _expect_payload(
        service.handle_attach_labels(
            AttachLabelsCommand(mapping={"sub-01_raw.fif": "labels.txt"}),
        ),
    )

    assert message == "Attached labels to 1 file(s)."
    assert payload == {"success_count": 1, "errors": []}
    assert dataset.batch_calls == [
        (
            [raw],
            {"labels.txt": [1, 2, 1]},
            {"/data/sub-01_raw.fif": "labels.txt"},
            {1: "1", 2: "2"},
            None,
        ),
    ]


def test_data_compatibility_service_imports_labels_and_updates_recipe() -> None:
    service, dataset, interpretation = _service()
    raw = _Raw("/data/sub-01_raw.fif")
    dataset.loaded_data = [raw]

    message, payload = _expect_payload(
        service.handle_import_labels(
            ImportLabelsCommand(
                plan=LabelImportPlan(
                    target_indices=[0],
                    label_map={"labels.tsv": [1, 2]},
                    file_mapping={"/data/sub-01_raw.fif": "labels.tsv"},
                    mapping={1: "left", 2: "right"},
                    selected_event_names=["cue"],
                ),
            ),
        ),
    )

    assert message == "Imported labels for 1 file(s)."
    assert payload["success_count"] == 1
    assert payload["mode"] == "batch"
    assert payload["recipe_updated"] is True
    assert payload["label_import"] == {
        "mode": "batch",
        "target_files": ["/data/sub-01_raw.fif"],
        "selected_event_names": ["cue"],
    }
    assert interpretation.recorded[0]["file_mapping"] == {
        "/data/sub-01_raw.fif": "labels.tsv",
    }
