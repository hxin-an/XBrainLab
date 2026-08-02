"""Read-only query command handling for the application command spine."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from XBrainLab.backend.services.dataset_state_service import DatasetDetachedReadPort

from .commands import Command, QueryStateCommand
from .errors import PreconditionError
from .state import ApplicationStateSnapshot

if TYPE_CHECKING:
    from .state_service import StateSnapshotService

HandlerResult = str | tuple[str, dict[str, Any]]


class QueryStateCommandService:
    """Handle read-only query_state commands through the command spine."""

    def __init__(
        self,
        *,
        study: Any,
        dataset: DatasetDetachedReadPort,
        state_builder: StateSnapshotService,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.study = study
        self.dataset = dataset
        self.state_builder = state_builder
        self.get_state = get_state

    def handle_query_state(
        self,
        command: Command,
        *,
        state: ApplicationStateSnapshot | None = None,
    ) -> HandlerResult:
        if not isinstance(command, QueryStateCommand):
            raise TypeError("Invalid command for query_state")

        query = str(command.query or "state").lower()
        if query == "state":
            raise PreconditionError(
                "State queries must use ApplicationService publication routing.",
            )
        if query == "data_lists":
            loaded_rows = self.dataset.get_loaded_data_rows()
            preprocessed_rows = self.dataset.get_preprocessed_data_rows()
            diagnostics: dict[str, Any] = {
                "raw_count": len(loaded_rows),
                "preprocessed_count": len(preprocessed_rows),
                "raw_files": [str(row.get("filepath", "")) for row in loaded_rows],
                "preprocessed_files": [
                    str(row.get("filepath", "")) for row in preprocessed_rows
                ],
                "raw_rows": loaded_rows,
                "preprocessed_rows": preprocessed_rows,
            }
            return "Data list query ready.", diagnostics
        if query == "label_import_targets":
            target_indices = command.params.get("target_indices")
            target_count = command.params.get("target_count", 0)
            if not isinstance(target_indices, list):
                raise PreconditionError("target_indices must be a list.")
            if (
                isinstance(target_count, bool)
                or not isinstance(target_count, int)
                or target_count < 0
            ):
                raise PreconditionError(
                    "target_count must be a non-negative integer.",
                )
            rows = self.dataset.get_label_import_target_rows(
                target_indices,
                target_count=target_count,
            )
            return (
                "Label import targets ready.",
                {
                    "payload_type": "label_import_targets",
                    "target_count": len(rows),
                    "targets": rows,
                },
            )
        if query == "data_summary":
            state = state if state is not None else self.get_state()
            return "Dataset summary ready.", self.state_builder.data_summary_from_state(
                state,
            )
        if query == "preprocess_diagnostics":
            state = state if state is not None else self.get_state()
            return (
                "Preprocess diagnostics ready.",
                dict(state.preprocessed.diagnostics),
            )
        if query == "smart_filter_suggestions":
            suggestions = self.state_builder.smart_filter_suggestions(command.params)
            return (
                "Smart filter suggestions ready.",
                {"suggestions": suggestions},
            )
        if query == "training_history":
            rows = self.state_builder.training_history()
            return (
                "Training history query ready.",
                {
                    "payload_type": "training_history",
                    "row_count": len(rows),
                    "rows": rows,
                },
            )
        raise ValueError(f"Unknown query_state request: {command.query}")


__all__ = ["HandlerResult", "QueryStateCommandService"]
