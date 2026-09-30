"""Research-only prompt presentation and nuisance-ID projection.

Exact model identity selects a source-versioned emphasis; the real tool schemas
and backend publication still own arguments and admission. Ordinary observers
record the actual requests, and the host retains its original generation.
"""

from __future__ import annotations

import json
import re

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.decision_contract import model_proposal_schema
from XBrainLab.llm.tools.schema_contract import tool_contract_for_llm

PROJECTION_ID = "dev-state-card-nuisance-v1"
_SUBJECT_REF = re.compile(r"\[SUBJECT_REF:[0-9a-f]{12}\]")

_DECISION_STEPS = """Choose one response for current_user.text, in this order:
1. A question, explanation request or prohibition is not permission to act.
   Choose respond_to_user to answer or acknowledge it, without an action.
2. For a requested action, check the callable list. If absent or unavailable,
   choose respond_to_user and explain why. Do not invent a tool, substitute
   another action, or perform prerequisite actions instead.
3. For an available action, check its required parameters. If any required
   value is missing or unclear in the current request, choose respond_to_user:
   name all missing values and ask for the complete request again, including
   values already supplied. Never fill gaps with null, empty values, defaults,
   state or examples.
   Optional parameters may be omitted. Zero-parameter tools need no values:
   opening a dialog does not require the values the user will enter inside it.
4. For a complete request to an available action, choose that action with only
   its defined parameters. A message promising to act does not execute it.
   The application handles any required confirmation; do not ask again first.
Each turn is independent: no draft or history supplies missing values. A bare
value or 'same as before' is not a complete request. For multiple requested
actions, or an explanation plus a requested action, ask which to do first;
never partially execute. Explaining a prohibited action is one answer: answer
the question and acknowledge the prohibition without treating it as an action.
Opening a dialog does not complete its operation. Never report completion
without a trusted tool result; starting training is not completion, and asking
to stop is not stopped. Write your own English reply, not a copy of the request;
use plain English instead of internal tool names in message.
Return exactly one JSON object with only tool_name and parameters. No prose,
Markdown or comments outside it. Only respond_to_user uses a message parameter.
"""

# Versioned with the full source. Model identity alone selects the emphasis;
# no case, oracle, score, candidate index or environment-dependent selection.
_MODEL_EMPHASIS = {
    "ibm-granite/granite-4.0-micro": (
        "Check each required value against the current request. A partly supplied "
        "operation is still incomplete: ask for the missing value, without borrowing "
        "one from a reference. When every required value is supplied, use the tool."
    ),
    "ibm-granite/granite-3.3-2b-instruct": (
        "You may choose respond_to_user instead of an action. Use it for questions, "
        "prohibitions, unavailable actions and missing values; never guess values "
        "or do prerequisites. Put any explanation only in its message string. "
        "Output one JSON object, with no introduction, trailing prose or // comments."
    ),
    "microsoft/Phi-4-mini-instruct": (
        "The two output fields are tool_name and parameters, never name. Tool "
        "descriptions are input guidance, not an answer to copy: do not output "
        "description, type or properties. A zero-parameter dialog uses {}; do not "
        "put its form fields or a question inside the parameters."
    ),
    "meta-llama/Llama-3.2-3B-Instruct": (
        "Decide whether an action is appropriate before filling parameters. "
        "For questions, prohibitions, unavailable actions or missing required "
        "values, use respond_to_user. Do not invent tools or fill missing values "
        "with null. Zero-parameter tools take {} without method, view_mode or message."
    ),
    "google/gemma-3-4b-it": (
        "For an available, fully specified action request, call the action tool. "
        "Saying you will open a dialog does not open it; use its tool with {}. "
        "Do not ask for form fields, repeat supplied values as questions, or ask "
        "whether to proceed. This does not override prohibitions, blockers or "
        "missing required values, which still need respond_to_user."
    ),
}
DEV_PROMPT_MODEL_IDS = tuple(_MODEL_EMPHASIS)

# These units are backend semantics, not fields claimed to exist in the schema:
# backend/preprocessor/filtering.py (l_freq/h_freq/notch_freqs) and resample.py (sfreq).
_PARAMETER_UNITS = {
    ("apply_bandpass_filter", "low_freq"): "Hz",
    ("apply_bandpass_filter", "high_freq"): "Hz",
    ("apply_notch_filter", "freq"): "Hz",
    ("resample_data", "rate"): "Hz",
}


def validate_dev_prompt_model(model_id: str) -> None:
    """Fail before loading a model rather than silently choose another prompt."""
    if not isinstance(model_id, str) or model_id not in _MODEL_EMPHASIS:
        raise ValueError(f"Unsupported DEV prompt model: {model_id!r}")


def _parameter_lines(tool_name: str, schema: dict) -> list[str]:
    """Render the current schemas losslessly; new constraints require review."""
    unknown = set(schema) - {"type", "properties", "required", "additionalProperties"}
    if unknown:
        raise ValueError(f"Unsupported parameter schema keywords: {sorted(unknown)}")
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
    ):
        raise ValueError("Unsupported parameter object boundary")
    properties = schema["properties"]
    required = schema.get("required", [])
    if not set(required) <= set(properties):
        raise ValueError("Required parameter missing from properties")
    if not properties:
        return ["No parameters: parameters must be {}. No extra fields."]
    lines = ["Parameters (object; no extra fields):"]
    for name, definition in properties.items():
        unknown = set(definition) - {"type", "enum", "description", "pattern"}
        if unknown:
            raise ValueError(f"Unsupported {name} schema keywords: {sorted(unknown)}")
        kind = definition.get("type")
        if kind not in ("string", "number", "integer", "boolean", "null"):
            raise ValueError(f"Unsupported parameter type: {kind!r}")
        line = f"- {name}: {'required' if name in required else 'optional'} {kind}"
        if unit := _PARAMETER_UNITS.get((tool_name, name)):
            line += f"; unit: {unit}"
        if "enum" in definition:
            line += "; allowed values: " + ", ".join(
                json.dumps(value, ensure_ascii=False) for value in definition["enum"]
            )
        if "pattern" in definition:
            if definition["pattern"] != r"\S" or kind != "string":
                raise ValueError("Unsupported parameter pattern")
            line += "; must contain a non-whitespace character"
        if "description" in definition:
            line += ". " + definition["description"]
        lines.append(line)
    return lines


class DevContextAssembler(ContextAssembler):
    """Pure model-facing projection; owns no readiness or execution policy."""

    _TOOL_BLOCK_TEMPLATE = "\nAvailable choices (guidance, not output):\n{tools_str}\n{availability_note}\n"

    def __init__(
        self, tool_registry, study_state, *, model_id: str, application_runtime=None
    ):
        validate_dev_prompt_model(model_id)
        self.model_id = model_id
        super().__init__(
            tool_registry, study_state, application_runtime=application_runtime
        )

    def _decision_instructions(self) -> str:
        return _DECISION_STEPS + "\nRemember: " + _MODEL_EMPHASIS[self.model_id] + "\n"

    def _format_tools(self, allowed_names, *, unavailable_actions=None) -> str:
        reply_schema = model_proposal_schema()["allOf"][0]["then"]["properties"][
            "parameters"
        ]
        sections = [
            "\n".join(
                [
                    "Reply: respond_to_user (no action)",
                    "Answer, acknowledge a prohibition, ask for missing values or explain a blocker.",
                    *_parameter_lines("respond_to_user", reply_schema),
                ]
            )
        ]
        for tool in self.registry.get_all_tools():
            if tool.name not in allowed_names:
                continue
            contract = tool_contract_for_llm(tool)
            sections.append(
                "\n".join(
                    [
                        f"Action: {contract['name']}",
                        f"Category: {contract['taxonomy']}. {contract['description']}",
                        *_parameter_lines(tool.name, contract["parameters"]),
                    ]
                )
            )
        if len(sections) == 1:
            sections.append("No callable action is available.")
        if unavailable_actions:
            sections.append(
                "Unavailable (not callable):\n"
                + "\n".join(
                    f"- {name}: {reason}"
                    for name, reason in unavailable_actions.items()
                )
            )
        sections.append("\n".join(self._final_output_reminder()))
        return "\n\n".join(sections)

    @staticmethod
    def _state_card_payload(publication, **kwargs):
        payload = ContextAssembler._state_card_payload(publication, **kwargs)
        # This number is meaningful only to the host's original publication.
        payload.pop("backend_generation", None)
        progress = payload.get("progress")
        if isinstance(progress, str):
            aliases: dict[str, str] = {}

            def alias(match):
                original = match.group(0)
                if original not in aliases:
                    aliases[original] = f"[SUBJECT_REF:{len(aliases) + 1:012x}]"
                return aliases[original]

            payload["progress"] = _SUBJECT_REF.sub(alias, progress)
        return payload
