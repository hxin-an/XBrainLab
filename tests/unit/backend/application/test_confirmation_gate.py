"""Strict confirmation typing at public application boundaries."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ErrorType,
    LoadDataCommand,
    QueryStateCommand,
    ResetSessionCommand,
    TrainCommand,
    command_specs,
    execute_automation_payload,
)
from XBrainLab.backend.study import Study


def test_public_automation_confirmation_field_sweep_is_strict_boolean() -> None:
    confirmation_schemas = {
        field_name: field_schema
        for spec in command_specs()
        for field_name, field_schema in spec.input_schema["properties"].items()
        if field_name == "confirmed" or field_name.endswith("_confirmed")
    }

    assert set(confirmation_schemas) == {
        "confirmed",
        "resource_preflight_confirmed",
    }
    assert all(
        field_schema == {"type": "boolean"}
        for field_schema in confirmation_schemas.values()
    )

    create_epoch_spec = next(
        spec for spec in command_specs() if spec.name == CommandName.CREATE_EPOCH
    )
    assert create_epoch_spec.input_schema["properties"]["confirmation_receipt"] == {
        "type": "string",
        "nullable": True,
    }


@pytest.mark.parametrize("invalid_confirmation", ["false", 1])
@pytest.mark.parametrize(
    ("field_name", "valid_arguments"),
    [
        ("confirmed", {}),
        ("resource_preflight_confirmed", {"confirmed": True}),
    ],
)
def test_public_automation_rejects_non_boolean_confirmation_fields(
    field_name: str,
    valid_arguments: dict[str, Any],
    invalid_confirmation: object,
) -> None:
    service = _ready_training_service()
    arguments = {**valid_arguments, field_name: invalid_confirmation}

    execution = execute_automation_payload(
        service,
        {"command": "train", "arguments": arguments},
    )

    assert execution.accepted is False
    assert execution.command_name == "train"
    assert execution.verification["schema_valid"] is False
    assert field_name in execution.verification["error"]
    assert "must be a boolean" in execution.verification["error"]
    assert type(invalid_confirmation).__name__ in execution.verification["error"]
    assert execution.result is None
    service.training.start_training.assert_not_called()


def test_public_automation_preserves_false_as_missing_confirmation() -> None:
    service = _ready_training_service()

    execution = execute_automation_payload(
        service,
        {"command": "train", "arguments": {"confirmed": False}},
    )

    assert execution.accepted is True
    assert execution.verification["schema_valid"] is True
    assert execution.result is not None
    assert execution.result["status"] == "failed"
    assert execution.result["error_type"] == "confirmation_required"
    service.training.start_training.assert_not_called()


@pytest.mark.parametrize("invalid_confirmation", ["false", 1])
def test_command_gate_rejects_non_boolean_confirmed_before_training(
    invalid_confirmation: object,
) -> None:
    service = _ready_training_service()

    result = service.execute(
        TrainCommand(confirmed=cast(Any, invalid_confirmation)),
    )

    assert result.failed is True
    assert result.error_type is ErrorType.VALIDATION
    assert result.recoverable is True
    assert "confirmed must be a boolean" in result.message
    assert result.diagnostics["confirmation_field"] == "confirmed"
    assert result.diagnostics["expected_type"] == "boolean"
    assert result.diagnostics["received_type"] == type(invalid_confirmation).__name__
    service.training.start_training.assert_not_called()


@pytest.mark.parametrize("invalid_confirmation", ["false", 1])
def test_command_gate_rejects_non_boolean_resource_preflight_confirmation(
    invalid_confirmation: object,
    tmp_path: Path,
) -> None:
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(0, []))
    source = tmp_path / "sample.fif"
    source.write_bytes(b"placeholder")

    result = service.execute(
        LoadDataCommand(
            paths=[str(source)],
            resource_preflight_confirmed=cast(Any, invalid_confirmation),
        ),
    )

    assert result.failed is True
    assert result.error_type is ErrorType.VALIDATION
    assert result.recoverable is True
    assert "resource_preflight_confirmed must be a boolean" in result.message
    assert result.diagnostics["confirmation_field"] == "resource_preflight_confirmed"
    assert result.diagnostics["expected_type"] == "boolean"
    assert result.diagnostics["received_type"] == type(invalid_confirmation).__name__
    service.dataset.import_files.assert_not_called()


def test_expected_publication_is_checked_after_command_lock_acquisition() -> None:
    """A queued destructive command cannot execute after publication A becomes B."""
    service = ApplicationService(Study())
    publication_a = service.get_view_publication()
    changed_state = replace(
        publication_a.state,
        pipeline_stage="raw_loaded",
        raw=replace(publication_a.state.raw, loaded=True, count=1),
        active_dataset=replace(
            publication_a.state.active_dataset,
            has_raw_data=True,
        ),
    )
    service.state_snapshot.build = MagicMock(return_value=changed_state)
    handler = MagicMock(return_value="Session reset.")
    service._command_handlers[CommandName.RESET_SESSION] = handler
    started = Event()
    results = []

    def _execute_confirmed_reset() -> None:
        started.set()
        results.append(
            service.execute(
                ResetSessionCommand(confirmed=True),
                expected_publication_generation=publication_a.generation,
            )
        )

    with service._command_lock:
        thread = Thread(target=_execute_confirmed_reset, daemon=True)
        thread.start()
        assert started.wait(timeout=1.0)
        service.get_state()
        publication_b = service.get_view_publication()
        assert publication_b.generation > publication_a.generation

    thread.join(timeout=2.0)

    assert thread.is_alive() is False
    assert len(results) == 1
    result = results[0]
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.changed_state.any_changed() is False
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["expected_publication_generation"] == (
        publication_a.generation
    )
    assert result.diagnostics["current_publication_generation"] == (
        publication_b.generation
    )
    handler.assert_not_called()


def test_expected_publication_rejects_an_unusable_committed_view() -> None:
    service = ApplicationService(Study())
    publication = service.get_view_publication()
    handler = MagicMock(return_value="Session reset.")
    service._command_handlers[CommandName.RESET_SESSION] = handler
    service._view_coordinator.mark_stale("state refresh failed")

    result = service.execute(
        ResetSessionCommand(confirmed=True),
        expected_publication_generation=publication.generation,
    )

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["publication_usable"] is False
    handler.assert_not_called()


def test_state_query_rejects_a_stale_expected_publication_generation() -> None:
    service = ApplicationService(Study())
    reviewed = service.get_view_publication()
    changed_state = replace(reviewed.state, pipeline_stage="data_loaded")
    service.state_snapshot.build = MagicMock(return_value=changed_state)
    service.get_state()
    current = service.get_view_publication()

    result = service.execute(
        QueryStateCommand(query="state"),
        expected_publication_generation=reviewed.generation,
    )

    assert current.generation > reviewed.generation
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.state == current.state
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["expected_publication_generation"] == (
        reviewed.generation
    )
    assert result.diagnostics["current_publication_generation"] == (current.generation)


@pytest.mark.parametrize("query", ["data_lists", "training_history"])
def test_detached_query_rejects_stale_generation_before_domain_read(
    query: str,
) -> None:
    service = ApplicationService(Study())
    reviewed = service.get_view_publication()
    changed_state = replace(reviewed.state, pipeline_stage="data_loaded")
    service.state_snapshot.build = MagicMock(return_value=changed_state)
    service.get_state()
    current = service.get_view_publication()
    domain_read = MagicMock()
    service.query_state_commands.handle_query_state = domain_read

    result = service.execute(
        QueryStateCommand(query=query),
        expected_publication_generation=reviewed.generation,
    )

    assert current.generation > reviewed.generation
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["current_publication_generation"] == (current.generation)
    domain_read.assert_not_called()


def test_generation_bound_state_query_returns_one_atomic_publication() -> None:
    service = ApplicationService(Study())
    reviewed = service.get_view_publication()
    later = replace(
        reviewed,
        state=replace(reviewed.state, pipeline_stage="data_loaded"),
        generation=reviewed.generation + 1,
        revision=reviewed.revision + 1,
    )
    committed_read = MagicMock(side_effect=[reviewed, later])
    service._committed_view_publication = committed_read
    service._publish_committed_view = MagicMock(return_value=True)

    result = service.execute(
        QueryStateCommand(query="state"),
        expected_publication_generation=reviewed.generation,
    )

    assert result.ok is True
    assert result.state == reviewed.state
    assert result.diagnostics["state"] == reviewed.state.to_dict()
    assert result.diagnostics["publication_generation"] == reviewed.generation
    assert result.diagnostics["publication_revision"] == reviewed.revision
    assert committed_read.call_count == 1


def _ready_training_service() -> ApplicationService:
    service = ApplicationService(Study())
    state = service.get_state()
    ready_state = replace(
        state,
        pipeline_stage="dataset_ready",
        raw=replace(state.raw, loaded=True, count=1),
        dataset=replace(state.dataset, available=True, count=1),
        training=replace(
            state.training,
            has_model=True,
            has_training_option=True,
        ),
        active_dataset=replace(
            state.active_dataset,
            has_raw_data=True,
            has_datasets=True,
        ),
        active_training=replace(
            state.active_training,
            has_model=True,
            has_training_option=True,
        ),
    )
    service.state_snapshot.build = MagicMock(return_value=ready_state)
    service.training.start_training = MagicMock(return_value=1)
    return service
