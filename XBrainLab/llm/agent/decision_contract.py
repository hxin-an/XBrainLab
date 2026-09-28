"""Shared names and bounds for strict model proposals."""

# Semantic label retained for corpus eligibility and historical score categories.
MODEL_RESPONSE_TOOL_NAME = "respond_to_user"
MAX_NAME_LENGTH = 128
MAX_SOURCE_TURN_LENGTH = 64
MAX_QUOTE_LENGTH = 4096
REQUEST_MODE_TO_INTERNAL = {
    "update_pending": "continue",
    "new_request": "replace",
    "cancel_pending": "cancel",
}


def model_proposal_schema() -> dict:
    """Project flat output fields; parser and backend still enforce combinations."""
    return {
        "type": "object",
        "required": ["decision", "mode", "action", "changes", "message"],
        "additionalProperties": False,
        "properties": {
            "decision": {"enum": ["reply", "clarify", "execute"]},
            "mode": {"enum": [None, *REQUEST_MODE_TO_INTERNAL]},
            "action": {"type": ["string", "null"]},
            "changes": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "required": ["value", "source_turn", "quote"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"not": {"type": "null"}},
                        "source_turn": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                },
            },
            "message": {"type": ["string", "null"]},
        },
    }
