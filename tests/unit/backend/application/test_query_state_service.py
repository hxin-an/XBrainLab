"""Focused ownership tests for the query-state command service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from XBrainLab.backend.application.commands import QueryStateCommand
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.query_state_service import (
    QueryStateCommandService,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.state_service import (
    QueryStateCommandService as CompatibilityQueryStateCommandService,
)


class _StateQueries:
    def data_summary_from_state(
        self,
        state: ApplicationStateSnapshot,
    ) -> dict[str, object]:
        return {"count": state.raw.count}

    def smart_filter_suggestions(self, params: dict[str, object]) -> list[int]:
        return [int(params["target_index"])]

    def training_history(self):
        return [
            {
                "identity": {"plan_index": 0, "run_index": 0},
                "group_name": "group-1",
            }
        ]


class _DatasetQueries:
    def __init__(self) -> None:
        self.loaded = object()
        self.preprocessed = object()

    def get_loaded_data_rows(self) -> list[dict[str, object]]:
        return [
            {
                "filepath": "/data/sample.fif",
                "filename": "sample.fif",
                "subject": "S01",
                "session": "session-01",
                "n_channels": 4,
                "sampling_frequency": 128.0,
                "epochs_length": 1,
                "is_raw": True,
                "labels_imported": False,
                "channels": ["Fz", "Cz"],
                "event": {
                    "available": False,
                    "count": 0,
                    "labels": [],
                    "source": "none",
                    "scanned": True,
                },
            }
        ]

    def get_preprocessed_data_rows(self) -> list[dict[str, object]]:
        return []

    def get_label_import_target_rows(
        self,
        target_indices: list[int],
        *,
        target_count: int,
    ) -> list[dict[str, object]]:
        assert target_indices == [0]
        assert target_count == 288
        return [
            {
                "index": 0,
                "filepath": "/data/sample.fif",
                "filename": "sample.fif",
                "is_raw": True,
                "event_names": ["768", "769"],
                "suggested_event_names": ["769"],
                "event_read_error": None,
            }
        ]


def _query_service() -> QueryStateCommandService:
    state = ApplicationStateSnapshot.empty()
    study = SimpleNamespace(
        loaded_data_list=[object()],
        preprocessed_data_list=[],
        epoch_data=None,
        dataset_generator=None,
        datasets=[],
    )
    return QueryStateCommandService(
        study=study,
        dataset=_DatasetQueries(),
        state_builder=_StateQueries(),
        get_state=lambda: state,
    )


def test_query_state_service_is_owned_by_dedicated_module() -> None:
    assert CompatibilityQueryStateCommandService is QueryStateCommandService
    assert QueryStateCommandService.__module__.endswith(".query_state_service")


def test_query_state_service_preserves_read_only_query_contract() -> None:
    service = _query_service()

    message, payload = service.handle_query_state(
        QueryStateCommand(query="training_history"),
    )

    assert message == "Training history query ready."
    assert payload["payload_type"] == "training_history"
    assert payload["row_count"] == 1
    assert payload["rows"][0] == {
        "identity": {"plan_index": 0, "run_index": 0},
        "group_name": "group-1",
    }


def test_data_list_query_returns_detached_rows() -> None:
    service = _query_service()

    message, payload = service.handle_query_state(
        QueryStateCommand(query="data_lists"),
    )

    assert message == "Data list query ready."
    assert payload["raw_count"] == 1
    assert payload["preprocessed_count"] == 0
    assert payload["raw_rows"] == [
        {
            "filepath": "/data/sample.fif",
            "filename": "sample.fif",
            "subject": "S01",
            "session": "session-01",
            "n_channels": 4,
            "sampling_frequency": 128.0,
            "epochs_length": 1,
            "is_raw": True,
            "labels_imported": False,
            "channels": ["Fz", "Cz"],
            "event": {
                "available": False,
                "count": 0,
                "labels": [],
                "source": "none",
                "scanned": True,
            },
        }
    ]
    assert payload["preprocessed_rows"] == []
    assert "loaded_data_list" not in payload
    assert "preprocessed_data_list" not in payload


def test_query_state_service_keeps_state_query_on_publication_route() -> None:
    with pytest.raises(PreconditionError, match="publication routing"):
        _query_service().handle_query_state(QueryStateCommand(query="state"))


def test_label_import_target_query_returns_detached_event_review_rows() -> None:
    service = _query_service()

    message, payload = service.handle_query_state(
        QueryStateCommand(
            query="label_import_targets",
            params={"target_indices": [0], "target_count": 288},
        ),
    )

    assert message == "Label import targets ready."
    assert payload == {
        "payload_type": "label_import_targets",
        "target_count": 1,
        "targets": [
            {
                "index": 0,
                "filepath": "/data/sample.fif",
                "filename": "sample.fif",
                "is_raw": True,
                "event_names": ["768", "769"],
                "suggested_event_names": ["769"],
                "event_read_error": None,
            }
        ],
    }


def test_query_state_service_rejects_retired_live_dataset_generation_context() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown query_state request: dataset_generation_context",
    ):
        _query_service().handle_query_state(
            QueryStateCommand(query="dataset_generation_context"),
        )
