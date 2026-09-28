"""The single-turn model response schema; backend schemas own tool parameters."""

from typing import Any

MODEL_RESPONSE_TOOL_NAME = "respond_to_user"
MAX_NAME_LENGTH = 128


def model_proposal_schema() -> dict[str, Any]:
    """Describe one tool call or a non-executable answer."""
    return {
        "type": "object",
        "required": ["tool_name", "parameters"],
        "additionalProperties": False,
        "properties": {
            "tool_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_NAME_LENGTH,
            },
            "parameters": {"type": "object"},
        },
        "allOf": [
            {
                "if": {
                    "properties": {"tool_name": {"const": MODEL_RESPONSE_TOOL_NAME}}
                },
                "then": {
                    "properties": {
                        "parameters": {
                            "type": "object",
                            "required": ["message"],
                            "additionalProperties": False,
                            "properties": {
                                "message": {"type": "string", "pattern": r"\S"}
                            },
                        }
                    }
                },
            }
        ],
    }
