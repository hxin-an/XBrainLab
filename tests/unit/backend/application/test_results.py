"""Tests for JSON-safe application command envelopes."""

from __future__ import annotations

import json
import math
from dataclasses import fields
from inspect import signature

from XBrainLab.backend.application.commands import QueryStateCommand, VisualizeCommand
from XBrainLab.backend.application.errors import map_exception
from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.exceptions import SaliencyCancellationTimeoutError
from XBrainLab.llm.tools.application_surface import ToolCommandResult


class _MutableDomainObject:
    pass


def test_command_result_physically_removes_process_local_compatibility_fields() -> None:
    result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state={"pipeline_stage": "empty"},
        changed_state=ChangedState(),
    )

    assert "runtime" not in {field.name for field in fields(CommandResult)}
    assert "runtime" not in signature(CommandResult.success_result).parameters
    assert "runtime" not in signature(CommandResult.failure_result).parameters
    assert not hasattr(result, "runtime")
    assert not hasattr(result, "local_payload")


def test_command_result_drops_mutable_domain_objects_instead_of_retaining_them() -> (
    None
):
    runtime_data = _MutableDomainObject()
    result = CommandResult.success_result(
        command_name="query_state",
        message="Data list query ready.",
        state={"pipeline_stage": "data_loaded"},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "data_lists",
            "raw_count": 1,
            "loaded_data_list": [runtime_data],
        },
    )

    public_payload = result.to_dict()
    agent_payload = ToolCommandResult.from_command_result(
        "query_state",
        result,
    ).to_payload()

    assert public_payload["diagnostics"] == {
        "payload_type": "data_lists",
        "raw_count": 1,
    }
    assert "runtime" not in public_payload
    assert agent_payload["diagnostics"] == public_payload["diagnostics"]
    assert agent_payload["raw_result"] == public_payload
    assert "loaded_data_list" not in agent_payload["diagnostics"]
    assert "runtime" not in agent_payload["raw_result"]
    json.dumps({"public": public_payload, "agent": agent_payload})


def test_object_selection_flags_are_physically_removed_from_read_commands() -> None:
    assert "include_objects" not in {field.name for field in fields(QueryStateCommand)}
    assert "include_objects" not in {field.name for field in fields(VisualizeCommand)}
    assert "include_averaged_records" not in {
        field.name for field in fields(VisualizeCommand)
    }


def test_command_result_default_serializer_is_public_and_internal_path_is_explicit() -> (
    None
):
    private_path = "/srv/clinical/subject-17/events.tsv"
    result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state={"source_path": private_path},
        changed_state=ChangedState(),
        diagnostics={"source_path": private_path},
    )

    public_payload = result.to_dict()
    explicit_public_payload = result.to_public_dict()
    internal_payload = result.to_internal_dict()

    assert public_payload == explicit_public_payload
    assert private_path not in json.dumps(public_payload)
    assert private_path in json.dumps(internal_payload)
    assert "[REDACTED_PATH]" in json.dumps(public_payload)


def test_command_result_rejects_hostile_diagnostics_and_state_protocols() -> None:
    class HostileDiagnostics(dict[str, object]):
        def __bool__(self) -> bool:
            raise AssertionError("diagnostic truth protocol must not execute")

        def items(self):
            raise AssertionError("diagnostic mapping protocol must not execute")

    class HostileState:
        def __deepcopy__(self, memo):
            raise AssertionError("state deepcopy protocol must not execute")

        @property
        def to_dict(self):
            raise AssertionError("state serializer property must not execute")

    result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state=HostileState(),
        changed_state=ChangedState(),
        diagnostics=HostileDiagnostics({"detail": "private"}),
    )

    assert result.state == {}
    assert result.diagnostics == {}
    assert result.to_public_dict()["state"] == {}


def test_command_result_state_does_not_alias_backend_snapshot_input() -> None:
    state = {"raw": {"files": []}}

    result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state=state,
        changed_state=ChangedState(),
    )
    state["raw"]["files"].append("tampered.gdf")

    assert result.state == {"raw": {"files": []}}


def test_command_result_rejects_non_finite_numbers_from_json_contract() -> None:
    result = CommandResult.success_result(
        command_name="evaluate",
        message="ready",
        state={
            "finite": 1.0,
            "not_a_number": math.nan,
            "positive_infinity": math.inf,
        },
        changed_state=ChangedState(),
        diagnostics={
            "finite": 2.0,
            "not_a_number": math.nan,
            "negative_infinity": -math.inf,
        },
    )

    assert result.state == {}
    assert result.diagnostics == {"finite": 2.0}
    json.dumps(result.to_internal_dict(), allow_nan=False)
    json.dumps(result.to_public_dict(), allow_nan=False)


def test_saliency_cancel_timeout_maps_to_retryable_precondition() -> None:
    error = map_exception(SaliencyCancellationTimeoutError())

    assert error.error_type is ErrorType.PRECONDITION
    assert error.recoverable is True
    assert error.diagnostics == {
        "retryable": True,
        "operation": "saliency_cancellation",
        "state_preserved": True,
    }


def test_command_failure_public_fields_and_serialization_redact_private_context() -> (
    None
):
    private_path = "/srv/clinical/subject-17/events.tsv"
    private_subject = "Alice-Smith"
    message = (
        f"Could not read {private_path}\r\nRetry after checking "
        f"subject_id={private_subject}."
    )
    diagnostics = {
        "source_path": private_path,
        "subject_id": private_subject,
        "retryable": True,
    }

    result = CommandResult.failure_result(
        command_name="scan_source",
        message=message,
        state={"last_error": {"message": message}},
        changed_state=ChangedState(error_changed=True),
        error_type=ErrorType.FILE_CORRUPTED,
        recoverable=True,
        diagnostics=diagnostics,
    )
    payload = result.to_public_dict()

    assert private_path not in result.message
    assert private_subject not in result.message
    assert "\r" not in result.message
    assert "\x00" not in result.message
    assert "events.tsv" in result.message
    assert "Retry after checking" in result.message
    assert result.diagnostics == diagnostics
    serialized = json.dumps(payload)
    assert private_path not in serialized
    assert private_subject not in serialized
    assert "[REDACTED_PATH]" in serialized
    assert "[SUBJECT_REF:" in serialized
    assert payload["diagnostics"]["retryable"] is True


def test_command_public_projection_redacts_realistic_structured_private_context() -> (
    None
):
    result = CommandResult.failure_result(
        command_name="scan_source",
        message="Import needs review.",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.VALIDATION,
        recoverable=True,
        diagnostics={
            "source_path": "relative/private/Mary Example/session.edf",
            "participants": [
                {
                    "participant_id": "sub-control",
                    "display_name": "Mary Example",
                    "age": 42,
                }
            ],
            "authorization": "Basic dXNlcjpwYXNz",
            "password": "correct horse battery staple",
        },
    )

    serialized = json.dumps(result.to_public_dict())

    for private_value in (
        "relative/private",
        "Mary Example",
        "sub-control",
        "dXNlcjpwYXNz",
        "correct horse battery staple",
    ):
        assert private_value not in serialized
    assert "[REDACTED_PATH]" in serialized
    assert "[SUBJECT_REF:" in serialized
    assert serialized.count("[REDACTED_SECRET]") == 2


def test_exception_mapping_preserves_recovery_guidance_without_private_values() -> None:
    private_path = r"C:\Users\Alice\EEG\sub-P001\recording.edf"

    mapped = map_exception(
        ValueError(
            f"Required EEG file {private_path} is unavailable; choose another source."
        )
    )

    public_message = str(mapped)
    assert private_path in mapped.message
    assert private_path not in public_message
    assert "sub-P001" not in public_message
    assert ".edf" in public_message
    assert "choose another source" in public_message
    assert mapped.error_type is ErrorType.VALIDATION


def test_application_error_keeps_internal_message_but_public_string_is_redacted() -> (
    None
):
    private_path = "/srv/clinical/sub-P001/events.tsv"

    mapped = map_exception(ValueError(f"Required file {private_path} is unavailable"))

    assert private_path in mapped.message
    assert private_path not in str(mapped)
    assert "events.tsv" in str(mapped)
    assert "[REDACTED_PATH]" in str(mapped)


def test_generic_xbrainlab_error_mapping_keeps_internal_message() -> None:
    from XBrainLab.backend.exceptions import XBrainLabError

    private_path = "/srv/clinical/sub-P001/events.tsv"
    mapped = map_exception(XBrainLabError(f"Could not read {private_path}"))

    assert private_path in mapped.message
    assert private_path not in str(mapped)
    assert "[REDACTED_PATH]" in str(mapped)


def test_exception_mapping_rejects_hostile_message_properties_and_string_protocols() -> (
    None
):
    class HostileError(Exception):
        @property
        def message(self) -> str:
            raise AssertionError("exception message property must not execute")

        def __str__(self) -> str:
            raise AssertionError("exception string protocol must not execute")

    mapped = map_exception(HostileError("/srv/clinical/sub-P001/events.tsv"))

    assert mapped.error_type is ErrorType.INTERNAL
    assert mapped.recoverable is False
    assert mapped.message == "An unexpected application error occurred."
