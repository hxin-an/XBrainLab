
import json

SYSTEM_PROMPT_CHAT = """You are XBrainLab Assistant, an expert in EEG analysis and the XBrainLab software.
Your goal is to assist researchers in analyzing brainwave data.

Currently, you are in CHAT mode. You can answer questions about EEG concepts, signal processing, and machine learning.
"""

def get_system_prompt(tools: list) -> str:
    """
    Generates the system prompt with available tools.
    """
    tool_descs = []
    for tool in tools:
        tool_def = {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        }
        tool_descs.append(json.dumps(tool_def, indent=2))
    
    tools_str = "\n".join(tool_descs)

    return f"""You are XBrainLab Assistant.
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
