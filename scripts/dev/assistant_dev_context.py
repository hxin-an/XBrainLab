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
1. Information or explanation requests and prohibitions are not permission to
   act. Choose respond_to_user to answer or acknowledge them. Polite requests
   to perform an action, even when phrased as questions, are action requests:
   continue with steps 2-4.
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
    # R2 presentation; required-value guidance now lives beside action fields.
    "ibm-granite/granite-4.0-micro": "",
    "ibm-granite/granite-3.3-2b-instruct": (
        "Action parameters contain only that action's listed arguments. They "
        "never contain message, a description or the user's request. An action "
        "with no arguments has an empty parameters object. A message belongs "
        "only to respond_to_user, which displays a reply and executes no action. "
        "Choose that reply for missing required values, prohibitions, information "
        "or explanation requests, and unavailable actions. Do not fill missing "
        "values to make an action possible. Output ONLY one complete JSON object "
        "with tool_name and parameters. Put any explanation inside the reply's "
        "message, never before or after the object. No reasoning, headings, "
        "comments or second object."
    ),
    "microsoft/Phi-4-mini-instruct": (
        "The catalog's name identifies a tool; your output field is tool_name, "
        "never name. Output a complete JSON object, not a tool name alone. "
        "This also applies to respond_to_user: include parameters with message. "
        "Do not copy schema fields such as description, type or properties."
    ),
    "meta-llama/Llama-3.2-3B-Instruct": (
        "Decide whether an action is appropriate before filling parameters. "
        "For information or explanation requests, prohibitions, unavailable actions "
        "or missing required values, use respond_to_user. Do not invent tools or fill missing values "
        "with null. Every response has tool_name and parameters. For an action "
        'with no arguments, write the field "parameters": {}. The empty object '
        "is that field's value, not a quoted string or a standalone response."
    ),
    "google/gemma-3-4b-it": (
        "Identify the one operation requested in current_user.text. Check only "
        "that operation's callable contract and required parameters. A blocker "
        "for another operation does not block this one. A callable zero-parameter "
        "tool is complete: use {} without asking for dialog form values. Optional "
        "parameters may be omitted. For required parameters, use values supplied in this request; "
        "another request's missing values or examples do not change completeness. "
        "Use the requested action when complete, not a promise or a second "
        "confirmation. Information, prohibitions, unavailable actions and missing "
        "required values still need respond_to_user with parameters.message. "
        "Return one complete JSON object, not a bare message."
    ),
}
DEV_PROMPT_MODEL_IDS = tuple(_MODEL_EMPHASIS)
_ROUND2_PRESENTATION_MODELS = frozenset(
    {"ibm-granite/granite-4.0-micro", "meta-llama/Llama-3.2-3B-Instruct"}
)
_ILLUSTRATED_MODELS = frozenset(
    {
        "microsoft/Phi-4-mini-instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
    }
)
_ROUND3_EMPHASIS_MODELS = frozenset(
    {"microsoft/Phi-4-mini-instruct", "meta-llama/Llama-3.2-3B-Instruct"}
)

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


def _parameter_lines(
    tool_name: str, schema: dict, *, mark_required_source: bool = False
) -> list[str]:
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
        if mark_required_source and name in required:
            line += (
                "; value must be specified in current_user.text. "
                "A purpose or desired effect is not a selected value."
            )
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
        if model_id not in _ROUND2_PRESENTATION_MODELS:
            self._TOOL_BLOCK_TEMPLATE = ContextAssembler._TOOL_BLOCK_TEMPLATE
        super().__init__(
            tool_registry, study_state, application_runtime=application_runtime
        )

    def _decision_instructions(self) -> str:
        baseline = (
            _DECISION_STEPS
            if self.model_id in _ROUND2_PRESENTATION_MODELS
            else super()._decision_instructions()
        )
        if self.model_id in _ROUND3_EMPHASIS_MODELS:
            return baseline + "\nRemember: " + _MODEL_EMPHASIS[self.model_id] + "\n"
        return baseline

    def _format_tools(self, allowed_names, *, unavailable_actions=None) -> str:
        formatter = (
            self._format_readable_tools
            if self.model_id in _ROUND2_PRESENTATION_MODELS
            else super()._format_tools
        )
        catalog = formatter(allowed_names, unavailable_actions=unavailable_actions)
        if self.model_id in _ILLUSTRATED_MODELS:
            catalog += "\n\n" + self._output_illustrations(allowed_names)
        emphasis = _MODEL_EMPHASIS[self.model_id]
        if emphasis and self.model_id not in _ROUND3_EMPHASIS_MODELS:
            catalog += "\n\nOutput decision:\n" + emphasis
        return catalog

    def _output_illustrations(self, allowed_names) -> str:
        """Contract-authored contrasts; no bank, oracle or request inspection."""
        lines = [
            "Complete output illustrations:",
            "These show format and effect, not values or permission for this request. "
            "Choose one response using the rules above; never copy example values.",
        ]
        active_tools = [
            tool for tool in self.registry.get_all_tools() if tool.name in allowed_names
        ]
        is_phi = self.model_id == "microsoft/Phi-4-mini-instruct"
        is_llama = self.model_id == "meta-llama/Llama-3.2-3B-Instruct"
        is_granite33 = self.model_id == "ibm-granite/granite-3.3-2b-instruct"

        def example(kind, request, tool_name, parameters):
            lines.extend(
                (
                    f"Example input ({kind}): {request}",
                    json.dumps({"tool_name": tool_name, "parameters": parameters}),
                )
            )

        # A single contract supplies both sides; numbers are independently authored,
        # never selected from the current request, DEV cases or retrieved examples.
        bandpass = next(
            (tool for tool in active_tools if tool.name == "apply_bandpass_filter"),
            None,
        )
        if bandpass is not None and (is_phi or is_granite33):
            example(
                "complete action",
                "Use a passband whose two endpoints are 11 Hz and 43 Hz.",
                bandpass.name,
                {"low_freq": 11, "high_freq": 43},
            )
            if is_granite33:
                example(
                    "prohibition",
                    "Do not use a passband whose endpoints are 11 Hz and 43 Hz.",
                    "respond_to_user",
                    {"message": "I will leave the bandpass unchanged."},
                )
                example(
                    "information only",
                    "What would a passband with endpoints at 11 Hz and 43 Hz retain?",
                    "respond_to_user",
                    {"message": "It retains frequencies between the two endpoints."},
                )
            example(
                "missing required value",
                "Use a passband starting at 11 Hz; the other endpoint is undecided.",
                "respond_to_user",
                {
                    "message": "What upper cutoff should I use? Please send the bandpass request with both endpoints."
                },
            )
            if is_granite33:
                return "\n".join(lines)

        zero_argument = next(
            (tool for tool in active_tools if not tool.parameters.get("properties")),
            None,
        )
        dialog = next(
            (
                tool
                for tool in active_tools
                if tool_contract_for_llm(tool)["taxonomy"] == "GUI Completion"
                and not tool.parameters.get("properties")
            ),
            None,
        )
        contrast_tool = dialog if is_llama else zero_argument
        if (is_llama or is_granite33) and contrast_tool is not None:
            description = tool_contract_for_llm(contrast_tool)["description"]
            example(
                "open dialog" if is_llama else "complete action",
                description,
                contrast_tool.name,
                {},
            )
            if is_granite33:
                example(
                    "prohibition",
                    "Do not perform this operation: " + description,
                    "respond_to_user",
                    {"message": "I will not perform that operation."},
                )
            example(
                "information only",
                "Explain this feature without using it: " + description,
                "respond_to_user",
                {"message": "Its documented function is: " + description},
            )
            if is_granite33:
                return "\n".join(lines)
        elif zero_argument is not None:
            lines.extend(
                (
                    "Action with no arguments: requests the named action, not a text reply.",
                    json.dumps({"tool_name": zero_argument.name, "parameters": {}}),
                )
            )
        panel_tool = next(
            (tool for tool in active_tools if tool.name == "switch_panel"), None
        )
        if panel_tool is not None and not is_phi and not is_granite33:
            panel = panel_tool.parameters["properties"]["panel_name"]["enum"][0]
            lines.extend(
                (
                    "Action with arguments: requests a panel change only when the user asks for it.",
                    json.dumps(
                        {
                            "tool_name": "switch_panel",
                            "parameters": {"panel_name": panel},
                        }
                    ),
                )
            )
        if is_llama and dialog is not None:
            return "\n".join(lines)
        if is_granite33 or is_llama:
            example(
                "information only",
                "In general, what are EEG recordings?",
                "respond_to_user",
                {
                    "message": "EEG recordings measure electrical activity using scalp electrodes."
                },
            )
            return "\n".join(lines)
        lines.extend(
            (
                "Reply: displays an answer or question; executes no action.",
                json.dumps(
                    {
                        "tool_name": "respond_to_user",
                        "parameters": {
                            "message": "Which operation would you like help with?"
                        },
                    }
                ),
            )
        )
        return "\n".join(lines)

    def _format_readable_tools(self, allowed_names, *, unavailable_actions=None) -> str:
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
                        *_parameter_lines(
                            tool.name,
                            contract["parameters"],
                            mark_required_source=(
                                self.model_id == "ibm-granite/granite-4.0-micro"
                            ),
                        ),
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
