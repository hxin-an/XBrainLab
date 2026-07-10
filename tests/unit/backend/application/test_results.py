"""Tests for JSON-safe application command envelopes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from XBrainLab.backend.application.results import ChangedState, CommandResult


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
    assert payload["diagnostics"]["array"] == [1.0, 2.0]
    assert payload["diagnostics"]["runtime_object"] == {
        "object_type": "_OpaqueRuntimeObject",
        "repr": "<opaque-runtime-object>",
    }
