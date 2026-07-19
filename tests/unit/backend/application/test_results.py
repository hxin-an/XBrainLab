"""Tests for JSON-safe application command envelopes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from XBrainLab.backend.application.errors import map_exception
from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.exceptions import SaliencyCancellationTimeoutError
from XBrainLab.llm.tools.application_surface import ToolCommandResult


class _OpaqueRuntimeObject:
    def __repr__(self) -> str:
        return "<opaque-runtime-object>"


def test_command_result_to_dict_is_json_serializable_with_runtime_objects() -> None:
    result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state={"pipeline_stage": "empty"},
        changed_state=ChangedState(),
        diagnostics={
            "path": Path("example.edf"),
            "array": np.asarray([1.0, 2.0], dtype=np.float32),
            "runtime_object": _OpaqueRuntimeObject(),
        },
    )

    payload = result.to_dict()

    json.dumps(payload)
    assert payload["diagnostics"]["path"] == "example.edf"
    assert "array" not in payload["diagnostics"]
    assert "runtime_object" not in payload["diagnostics"]
    assert "runtime" not in payload
    assert result.runtime["array"].tolist() == [1.0, 2.0]
    assert isinstance(result.runtime["runtime_object"], _OpaqueRuntimeObject)
    assert result.local_payload["runtime_object"] is result.runtime["runtime_object"]
    json.dumps(result.diagnostics)


def test_public_and_agent_query_payloads_never_expose_runtime_objects() -> None:
    runtime_data = _OpaqueRuntimeObject()
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

    assert result.runtime["loaded_data_list"] == [runtime_data]
    assert public_payload["diagnostics"] == {
        "payload_type": "data_lists",
        "raw_count": 1,
    }
    assert "runtime" not in public_payload
    assert agent_payload["diagnostics"] == public_payload["diagnostics"]
    assert agent_payload["raw_result"] == public_payload
    assert "loaded_data_list" not in agent_payload["diagnostics"]
    assert "runtime" not in agent_payload["raw_result"]
    assert "opaque-runtime-object" not in json.dumps(
        {"public": public_payload, "agent": agent_payload},
    )


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


def test_saliency_cancel_timeout_maps_to_retryable_precondition() -> None:
    error = map_exception(SaliencyCancellationTimeoutError())

    assert error.error_type is ErrorType.PRECONDITION
    assert error.recoverable is True
    assert error.diagnostics == {
        "retryable": True,
        "operation": "saliency_cancellation",
        "state_preserved": True,
    }
