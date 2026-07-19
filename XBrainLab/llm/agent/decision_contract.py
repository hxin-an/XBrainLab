"""Model-owned response envelope that never reaches backend execution."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

MODEL_RESPONSE_TOOL_NAME = "respond_to_user"
ToolDecision: TypeAlias = Literal["tool"]
ModelResponseDecision: TypeAlias = Literal["blocked", "missing_input", "answer"]
ModelDecision: TypeAlias = ToolDecision | ModelResponseDecision

MODEL_RESPONSE_DECISIONS: frozenset[str] = frozenset(
    {"blocked", "missing_input", "answer"}
)
MODEL_RESPONSE_BRANCH_FIELDS: dict[ModelResponseDecision, tuple[str, ...]] = {
    "blocked": ("decision", "message"),
    "missing_input": ("decision", "missing_inputs", "message"),
    "answer": ("decision", "message"),
}


def _message_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": r"\S"}


def _response_branch_schema(
    decision: ModelResponseDecision,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "decision": {"const": decision},
        "message": _message_schema(),
    }
    if decision == "missing_input":
        properties["missing_inputs"] = {
            "type": "array",
            "items": {"type": "string", "pattern": r"\S"},
            "minItems": 1,
            "uniqueItems": True,
        }
    return {
        "title": decision,
        "type": "object",
        "properties": properties,
        "required": list(MODEL_RESPONSE_BRANCH_FIELDS[decision]),
        "additionalProperties": False,
    }


def model_response_tool_contract() -> dict[str, Any]:
    """Return the prompt-facing schema for a structured no-tool decision."""
    return {
        "name": MODEL_RESPONSE_TOOL_NAME,
        "description": (
            "Return a user-facing response without executing any workflow tool. "
            "Use blocked when the exact requested action is unavailable, "
            "missing_input when that action is enabled but lacks a required "
            "user value, and answer for an informational request. Never select "
            "an enabled prerequisite or substitute action."
        ),
        "taxonomy": "Assistant Decision",
        "parameters": {
            "type": "object",
            "oneOf": [
                _response_branch_schema("blocked"),
                _response_branch_schema("missing_input"),
                _response_branch_schema("answer"),
            ],
        },
        "requires_confirmation": False,
        "decision_boundary": None,
    }
