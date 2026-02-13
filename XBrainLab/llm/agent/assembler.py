import json
from typing import Any

from ..tools.tool_registry import ToolRegistry


class ContextAssembler:
    """
    Assembles the context for the AI Agent, including:
    1. System Prompt (ReAct instructions)
    2. Tool Definitions (Filtered by State)
    3. RAG Context (Knowledge Retrieval)
    4. Conversation History
    """

    SYSTEM_TEMPLATE = """You are XBrainLab Assistant.
You have access to the XBrainLab software and can control it to perform tasks.

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
"""

    def __init__(self, tool_registry: ToolRegistry, study_state: Any):
        """
        Args:
            tool_registry: Registry containing all available tools.
            study_state: The current state of the application (Study object).
        """
        self.registry = tool_registry
        self.study_state = study_state
        self.context_notes: list[str] = []

    def _format_tools(self) -> str:
        """
        Retrieves active tools from registry and formats them into JSON descriptions.
        """
        active_tools = self.registry.get_active_tools(self.study_state)

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
        """Constructs the full system prompt with filtered tools and context."""
        tools_str = self._format_tools()
        prompt = self.SYSTEM_TEMPLATE.format(tools_str=tools_str)

        if self.context_notes:
            prompt += "\n\nAdditional Context:\n" + "\n".join(self.context_notes)

        return prompt

    def add_context(self, text: str):
        """Adds temporary context (e.g. from RAG) to the system prompt."""
        self.context_notes.append(text)

    def clear_context(self):
        """Clears added context."""
        self.context_notes = []

    def get_messages(self, history: list) -> list:
        """
        Combines system prompt and history into the final message list.
        Applies sliding window to history if needed.
        """
        messages = [{"role": "system", "content": self.build_system_prompt()}]

        # Sliding Window is managed by Controller
        messages.extend(history)

        return messages
