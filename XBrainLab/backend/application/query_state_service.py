"""Read-only query command handling for the application command spine."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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
        dataset: Any,
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
            state = state if state is not None else self.get_state()
            loaded = list(getattr(self.study, "loaded_data_list", []) or [])
            preprocessed = list(
                getattr(self.study, "preprocessed_data_list", []) or [],
            )
            diagnostics: dict[str, Any] = {
                "raw_count": len(loaded),
                "preprocessed_count": len(preprocessed),
                "raw_files": state.raw.files,
                "preprocessed_files": state.preprocessed.files,
            }
            if command.include_objects:
                diagnostics["loaded_data_list"] = loaded
                diagnostics["preprocessed_data_list"] = preprocessed
            return "Data list query ready.", diagnostics
        if query == "dataset_generation_context":
            epoch_data = getattr(self.study, "epoch_data", None)
            dataset_generator = getattr(self.study, "dataset_generator", None)
            datasets = list(getattr(self.study, "datasets", []) or [])
            diagnostics = {
                "payload_type": "dataset_generation_context",
                "epoch_available": epoch_data is not None,
                "generator_exists": dataset_generator is not None,
                "dataset_count": len(datasets),
            }
            if command.include_objects:
                diagnostics["epoch_data"] = epoch_data
                diagnostics["dataset_generator"] = dataset_generator
                diagnostics["datasets"] = datasets
            return "Dataset generation context ready.", diagnostics
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
            rows = self.state_builder.training_history(
                include_objects=command.include_objects,
            )
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
