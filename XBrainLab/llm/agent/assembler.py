"""Context assembler for constructing LLM prompts.

Assembles system prompts with dynamic tool definitions, RAG context,
and conversation history for the AI agent.  Tools and guidance text
are selected based on the current :class:`PipelineStage`.
"""

import json
from typing import Any

from ..pipeline_state import STAGE_CONFIG, PipelineStage, compute_pipeline_stage
from ..tools.tool_registry import ToolRegistry


class ContextAssembler:
    """Assembles the full context for the AI agent.

    Constructs the system prompt by combining ReAct-style instructions,
    **stage-filtered** tool definitions, pipeline guidance, optional RAG
    context, and conversation history into a message list suitable for
    LLM inference.

    Attributes:
        registry: Tool registry containing all available tools.
        study_state: Current application state used for tool filtering.
        context_notes: Temporary context strings (e.g. from RAG) appended
            to the system prompt.

    """

    SYSTEM_TEMPLATE = """You are XBrainLab Assistant.
You have access to the XBrainLab software and can control it to perform tasks.

Current Pipeline Stage: {stage_name}
{stage_guidance}

Available Tools:
{tools_str}

To use a tool, you MUST output a JSON object in the following format:
```
{{
    "tool_name": "tool_name",
    "parameters": {{
        "param_name": "value"
    }}
}}
```

Rules:
1. If you need to use a tool, output ONLY the JSON block.
2. Do NOT output any introductory text (like 'Sure', 'I will') before the JSON.
3. Do NOT output the JSON block if you are not using a tool.
4. Do NOT use the 'json' language identifier, just the code block delimiters.
5. If no tool is needed, just reply normally.
6. You can ONLY use the tools listed above. Do NOT attempt to call unlisted tools.
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
            ``"tools"`` and ``"guidance"`` keys.

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
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            tool_descs.append(json.dumps(tool_def, indent=2))

        if not tool_descs:
            return "No tools currently available."

        return "\n".join(tool_descs)

    def build_system_prompt(self) -> str:
        """Constructs the full system prompt with stage-filtered tools.

        Returns:
            The assembled system prompt string including pipeline stage,
            guidance, tool definitions, and any additional RAG context.

        """
        stage, config = self._get_stage_config()
        tools_str = self._format_tools(config["tools"])

        prompt = self.SYSTEM_TEMPLATE.format(
            stage_name=stage.label,
            stage_guidance=config["guidance"],
            tools_str=tools_str,
        )

        if self.context_notes:
            prompt += "\n\nAdditional Context:\n" + "\n".join(self.context_notes)

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
