"""Model-owned response envelope that never reaches backend execution."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

MODEL_RESPONSE_TOOL_NAME = "respond_to_user"
ToolDecision: TypeAlias = Literal["tool"]
ModelDecision: TypeAlias = ToolDecision


def _message_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": r"\S"}


def model_response_tool_contract() -> dict[str, Any]:
    """Return the prompt-facing schema for one structured user response."""
    return {
        "name": MODEL_RESPONSE_TOOL_NAME,
        "description": (
            "Return a user-facing response without executing any workflow tool. "
            "Use it for an informational answer, a clarification question, or "
            "a specific blocked explanation. Never select an enabled prerequisite "
            "or substitute action."
        ),
        "taxonomy": "Assistant Decision",
        "parameters": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"message": _message_schema()},
                    "required": ["message"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "message": _message_schema(),
                        "pending_action": {"type": "string", "pattern": r"\S"},
                        "missing_inputs": {
                            "type": "array",
                            "items": {"type": "string", "pattern": r"\S"},
                            "minItems": 1,
                            "maxItems": 2,
                            "uniqueItems": True,
                        },
                    },
                    "required": ["message", "pending_action", "missing_inputs"],
                    "additionalProperties": False,
                },
            ]
        },
        "requires_confirmation": False,
        "decision_boundary": None,
    }
