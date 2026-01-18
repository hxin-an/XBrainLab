import json


class PromptManager:
    """
    Manages the construction of prompts for the LLM Agent.
    Handles System Prompt, Tool Definitions, Context Injection, and History Management.
    """

    def __init__(self, tools: list):
        self.tools = tools
        self.system_template = """You are XBrainLab Assistant.
You have access to the XBrainLab software and can control it to perform tasks.

Available Tools:
{tools_str}

To use a tool, you MUST output a JSON object in the following format:
```json
{{
    "command": "tool_name",
    "parameters": {{
        "param_name": "value"
    }}
}}
```

If no tool is needed, just reply normally.
"""
        self.context_notes: list[str] = []

    def _format_tools(self) -> str:
        """Formats the list of tool objects into a JSON string description."""
        tool_descs = []
        for tool in self.tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            tool_descs.append(json.dumps(tool_def, indent=2))
        return "\n".join(tool_descs)

    def get_system_message(self) -> str:
        """Constructs the full system prompt with tools and context."""
        tools_str = self._format_tools()
        prompt = self.system_template.format(tools_str=tools_str)

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
        messages = [{"role": "system", "content": self.get_system_message()}]

        # Sliding Window: Keep only the last 10 messages
        # Ideally this should be token-based, but count-based is safe for now.
        recent_history = history[-10:]
        messages.extend(recent_history)

        return messages
