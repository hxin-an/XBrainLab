"""Loaded-data table command handlers for the application command spine."""

from __future__ import annotations

from typing import Any

from .commands import (
    ApplySmartParseCommand,
    Command,
    MetadataUpdate,
    RemoveFilesCommand,
    UpdateMetadataCommand,
)
from .errors import PreconditionError

HandlerResult = str | tuple[str, dict[str, Any]]


class DataTableCommandService:
    """Handle metadata, smart-parse, and row-removal commands for loaded data."""

    def __init__(
        self,
        *,
        dataset: Any,
    ) -> None:
        self.dataset = dataset

    def handle_update_metadata(self, command: Command) -> HandlerResult:
        if not isinstance(command, UpdateMetadataCommand):
            raise TypeError("Invalid command for update_metadata")

        updates = self._metadata_updates(command)
        if not updates:
            raise PreconditionError("At least one metadata update is required.")
        if all(update.subject is None and update.session is None for update in updates):
            raise PreconditionError("subject or session is required.")

        loaded_count = len(self.dataset.get_loaded_data_list())
        updated = 0
        skipped: list[int] = []
        for update in updates:
            if 0 <= update.index < loaded_count:
                self.dataset.update_metadata(
                    update.index,
                    subject=update.subject,
                    session=update.session,
                )
                updated += 1
            else:
                skipped.append(update.index)

        if updated == 0:
            raise PreconditionError("No valid metadata rows were selected.")
        return (
            f"Updated metadata for {updated} file(s).",
            {"success_count": updated, "skipped_indices": skipped},
        )

    def handle_apply_smart_parse(self, command: Command) -> HandlerResult:
        if not isinstance(command, ApplySmartParseCommand):
            raise TypeError("Invalid command for apply_smart_parse")
        if not command.results:
            raise PreconditionError("smart parse results cannot be empty.")
        normalized = self._normalize_smart_parse_results(command.results)
        count = self.dataset.apply_smart_parse(normalized)
        return (
            f"Smart parse updated {count} file(s).",
            {"success_count": count},
        )

    def handle_remove_files(self, command: Command) -> HandlerResult:
        if not isinstance(command, RemoveFilesCommand):
            raise TypeError("Invalid command for remove_files")
        if not command.indices:
            raise PreconditionError("indices list cannot be empty.")
        before = len(self.dataset.get_loaded_data_list())
        self.dataset.remove_files([int(index) for index in command.indices])
        after = len(self.dataset.get_loaded_data_list())
        removed = before - after
        if removed <= 0:
            raise PreconditionError("No valid files were selected for removal.")
        return (
            f"Removed {removed} file(s).",
            {"success_count": removed, "requested_indices": command.indices},
        )

    @staticmethod
    def _metadata_updates(command: UpdateMetadataCommand) -> list[MetadataUpdate]:
        if command.updates:
            return command.updates
        if command.index is None:
            return []
        return [
            MetadataUpdate(
                index=command.index,
                subject=command.subject,
                session=command.session,
            ),
        ]

    @staticmethod
    def _normalize_smart_parse_results(
        results: dict[str, tuple[str, str] | list[str] | Any],
    ) -> dict[str, tuple[str, str]]:
        normalized: dict[str, tuple[str, str]] = {}
        for path, value in results.items():
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                normalized[str(path)] = (str(value[0]), str(value[1]))
            else:
                raise ValueError(
                    "Smart parse results must map paths to (subject, session).",
                )
        return normalized
