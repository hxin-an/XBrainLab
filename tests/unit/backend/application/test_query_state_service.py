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

    def training_history(self, *, include_objects: bool = False):
        row = {"group_name": "group-1"}
        if include_objects:
            row["record"] = object()
        return [row]


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
        dataset=object(),
        state_builder=_StateQueries(),
        get_state=lambda: state,
    )


def test_query_state_service_is_owned_by_dedicated_module() -> None:
    assert CompatibilityQueryStateCommandService is QueryStateCommandService
    assert QueryStateCommandService.__module__.endswith(".query_state_service")


def test_query_state_service_preserves_read_only_query_contract() -> None:
    service = _query_service()

    message, payload = service.handle_query_state(
        QueryStateCommand(query="training_history", include_objects=True),
    )

    assert message == "Training history query ready."
    assert payload["payload_type"] == "training_history"
    assert payload["row_count"] == 1
    assert "record" in payload["rows"][0]


def test_query_state_service_keeps_state_query_on_publication_route() -> None:
    with pytest.raises(PreconditionError, match="publication routing"):
        _query_service().handle_query_state(QueryStateCommand(query="state"))
