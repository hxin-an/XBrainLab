"""Focused tests for loaded-data table command handlers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from XBrainLab.backend.application.commands import (
    ApplySmartParseCommand,
    MetadataUpdate,
    RemoveFilesCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.application.data_table_service import (
    DataTableCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import PreconditionError


class _DatasetController:
    def __init__(self) -> None:
        self.loaded_data: list[Any] = []
        self.metadata_updates: list[tuple[int, str | None, str | None]] = []
        self.smart_parse_payload: dict[str, tuple[str, str]] | None = None
        self.removed_indices: list[int] = []

    def get_loaded_data_list(self) -> list[Any]:
        return self.loaded_data

    def update_metadata(
        self,
        index: int,
        *,
        subject: str | None,
        session: str | None,
    ) -> None:
        self.metadata_updates.append((index, subject, session))

    def apply_smart_parse(self, payload: dict[str, tuple[str, str]]) -> int:
        self.smart_parse_payload = payload
        return len(payload)

    def remove_files(self, indices: list[int]) -> None:
        self.removed_indices = indices
        self.loaded_data = [
            item for idx, item in enumerate(self.loaded_data) if idx not in indices
        ]


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[DataTableCommandService, _DatasetController]:
    dataset = _DatasetController()
    return DataTableCommandService(dataset=dataset), dataset


def test_data_table_service_updates_metadata_and_reports_skipped_rows() -> None:
    service, dataset = _service()
    dataset.loaded_data = [object(), object()]

    message, payload = _expect_payload(
        service.handle_update_metadata(
            UpdateMetadataCommand(
                updates=[
                    MetadataUpdate(index=0, subject="S01"),
                    MetadataUpdate(index=5, session="session-02"),
                ],
            ),
        ),
    )

    assert message == "Updated metadata for 1 file(s)."
    assert payload == {"success_count": 1, "skipped_indices": [5]}
    assert dataset.metadata_updates == [(0, "S01", None)]


def test_data_table_service_normalizes_smart_parse_results() -> None:
    service, dataset = _service()

    message, payload = _expect_payload(
        service.handle_apply_smart_parse(
            ApplySmartParseCommand(
                results={
                    "/data/a.fif": ("S01", "run-01"),
                    "/data/b.fif": ["S02", "run-02"],
                },
            ),
        ),
    )

    assert message == "Smart parse updated 2 file(s)."
    assert payload == {"success_count": 2}
    assert dataset.smart_parse_payload == {
        "/data/a.fif": ("S01", "run-01"),
        "/data/b.fif": ("S02", "run-02"),
    }


def test_data_table_service_remove_files_uses_observed_count_delta() -> None:
    service, dataset = _service()
    keep = object()
    dataset.loaded_data = [object(), keep, object()]

    message, payload = _expect_payload(
        service.handle_remove_files(RemoveFilesCommand(indices=[0, 2])),
    )

    assert message == "Removed 2 file(s)."
    assert payload == {"success_count": 2, "requested_indices": [0, 2]}
    assert dataset.loaded_data == [keep]
    assert dataset.removed_indices == [0, 2]


def test_data_table_service_rejects_empty_or_invalid_metadata_updates() -> None:
    service, dataset = _service()
    dataset.loaded_data = [object()]

    with pytest.raises(PreconditionError, match="subject or session is required"):
        service.handle_update_metadata(UpdateMetadataCommand(index=0))

    with pytest.raises(PreconditionError, match="No valid metadata rows"):
        service.handle_update_metadata(UpdateMetadataCommand(index=9, subject="S09"))
