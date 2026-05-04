"""Context assembler for constructing LLM prompts.

Assembles system prompts with dynamic tool definitions, RAG context,
and conversation history for the AI agent.  Tools and system-prompt text
are selected based on the current :class:`PipelineStage`.
"""

import json
from typing import Any

from ..pipeline_state import STAGE_CONFIG, PipelineStage, compute_pipeline_stage
from ..tools.application_surface import (
    READ_ONLY_TOOLS,
    TOOL_TO_COMMAND,
    blocked_tool_reasons,
    enabled_tool_names,
)
from ..tools.schema_contract import tool_contract_for_llm
from ..tools.tool_registry import ToolRegistry


class ContextAssembler:
    """Assembles the full context for the AI agent.

    Constructs the system prompt by combining ReAct-style instructions,
    **stage-filtered** tool definitions, pipeline system prompt, optional RAG
    context, and conversation history into a message list suitable for
    LLM inference.

    Attributes:
        registry: Tool registry containing all available tools.
        study_state: Current application state used for tool filtering.
        context_notes: Temporary context strings (e.g. from RAG) appended
            to the system prompt.

    """

    _TOOL_BLOCK_TEMPLATE = """
Available Tools:
{tools_str}

Blocked Commands:
{blocked_str}

To use a tool, output exactly one compact JSON object in this format:
{{"tool_name":"tool_name","parameters":{{"param_name":"value"}}}}

Rules:
1. If you need to use a tool, output ONLY the JSON object.
2. Do NOT output any introductory text (like 'Sure', 'I will') before the JSON.
3. Do NOT output the JSON block if you are not using a tool.
4. If no tool is needed, just reply normally.
5. You can ONLY use the tools listed above. Do NOT attempt to call unlisted tools.
6. Never invent placeholder paths, recipe paths, ids, labels, or file names.
   If a required value is missing, ask for it in one concise sentence.
7. If the user asks for a blocked workflow command, do not call a different tool
   to prepare or substitute for it. Explain the blocked reason in user-facing
   language.
8. The latest user message is the next requested action. Earlier messages are
   context; do not repeat an earlier tool step unless the latest message asks
   for it.
9. Use at most one tool call per assistant turn.
10. If the user asks a concept question, asks why a step is blocked, asks what
    a term means, or is only discussing the workflow, do not call a mutating
    tool. Answer in user-facing language.

Workflow tool choices:
- The current application state is authoritative. If the state already has a
  scan, preview, validation, or applied interpretation, continue from that
  state instead of repeating an earlier scan/load step from the chat history.
- Data Interpretation is the primary data entry workflow. Prefer
  scan_source -> preview_interpretation -> validate_interpretation ->
  apply_interpretation for new file, folder, BIDS, recipe, and label/event
  imports. Direct-load and label-attach paths are legacy compatibility only.
- Use apply_standard_preprocess for "standard preprocessing" or general
  preprocess requests, even when the user includes bandpass frequencies. Use
  the single bandpass filter tool only when it is listed and the user asks for a
  bandpass-only operation.
- For generate_dataset, split_strategy must be trial, session, or subject.
  individual and group are training_mode values, not split_strategy values.
"""

    def __init__(self, tool_registry: ToolRegistry, study_state: Any):
        """Initializes the ContextAssembler.

        Args:
            tool_registry: Registry containing all available tools.
            study_state: The current application state (Study object) used
                to determine which tools are active.

        """
        self.registry = tool_registry
        self.study_state = study_state
        self.context_notes: list[str] = []

    def _get_stage_config(self) -> tuple[PipelineStage, dict[str, Any]]:
        """Return the current pipeline stage and its configuration.

        Returns:
            A ``(stage, config)`` tuple where *config* contains
            ``"tools"`` and ``"system_prompt"`` keys.

        """
        stage = compute_pipeline_stage(self.study_state)
        config = STAGE_CONFIG.get(stage, STAGE_CONFIG[PipelineStage.EMPTY])
        return stage, config

    def _format_tools(self, allowed_names: list[str]) -> str:
        """Format only the tools whose names are in *allowed_names*.

        Args:
            allowed_names: Tool name strings permitted by the current
                pipeline stage.

        Returns:
            A newline-joined string of JSON-formatted tool definitions,
            or a fallback message if no tools are currently available.

        """
        allowed_set = set(allowed_names)
        active_tools = [
            t for t in self.registry.get_all_tools() if t.name in allowed_set
        ]

        tool_descs = []
        for tool in active_tools:
            tool_def = tool_contract_for_llm(tool)
            tool_descs.append(json.dumps(tool_def, indent=2))

        if not tool_descs:
            return "No tools currently available."

        return "\n".join(tool_descs)

    def _application_allowed_tools(self, fallback: list[str]) -> list[str]:
        """Return tool names allowed by ApplicationService capability policy."""
        registered_names = {tool.name for tool in self.registry.get_all_tools()}
        stage_names = set(fallback)
        try:
            app_allowed = set(enabled_tool_names(self.study_state))
        except Exception:
            return fallback
        policy_allowed = {
            name
            for name in app_allowed
            if name in stage_names and name in registered_names
        }
        non_policy_stage_tools = {
            name
            for name in fallback
            if name in registered_names
            and name not in TOOL_TO_COMMAND
            and name not in READ_ONLY_TOOLS
        }
        return sorted(policy_allowed | non_policy_stage_tools)

    def _format_blocked_tools(self) -> str:
        """Format blocked tools and reasons from the ApplicationService policy."""
        try:
            blocked = blocked_tool_reasons(self.study_state)
        except Exception:
            return "Unavailable: backend capability policy could not be read."

        lines = [
            f"- {tool_name}: {reason}"
            for tool_name, reason in sorted(blocked.items())
            if reason
        ]
        return "\n".join(lines) if lines else "None."

    def build_system_prompt(self) -> str:
        """Constructs the full system prompt with stage-filtered tools.

        Each pipeline stage has its own dedicated system prompt that
        defines the assistant's persona, goals, and constraints.  The
        tool block and RAG context are appended after the stage prompt.

        Returns:
            The assembled system prompt string including the stage-specific
            prompt, tool definitions, and any additional RAG context.

        """
        _stage, config = self._get_stage_config()
        allowed_tools = self._application_allowed_tools(config["tools"])
        tools_str = self._format_tools(allowed_tools)
        blocked_str = self._format_blocked_tools()

        prompt = config["system_prompt"]
        prompt += self._TOOL_BLOCK_TEMPLATE.format(
            tools_str=tools_str,
            blocked_str=blocked_str,
        )

        if self.context_notes:
            prompt += "\nAdditional Context:\n" + "\n".join(self.context_notes)

        return prompt

    def add_context(self, text: str):
        """Adds temporary context to the system prompt.

        Args:
            text: Context string (e.g. RAG-retrieved examples) to append.

        """
        self.context_notes.append(text)

    def clear_context(self):
        """Clears added context."""
        self.context_notes = []

    def get_messages(self, history: list) -> list:
        """Combines the system prompt and history into a message list.

        The sliding window over history is managed externally by the
        controller; this method simply concatenates system and history.

        Args:
            history: List of message dicts with ``role`` and ``content`` keys.

        Returns:
            Complete message list starting with the system prompt followed
            by the conversation history.

        """
        messages = [{"role": "system", "content": self.build_system_prompt()}]

        # Sliding Window is managed by Controller
        messages.extend(history)

        return messages
