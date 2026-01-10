
import json
import re
from typing import Optional, Tuple, Dict, Any
from XBrainLab.backend.utils.logger import logger

class CommandParser:
    """Parses LLM output to extract commands."""

    @staticmethod
    def parse(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Extracts a JSON command block from the text.
        Expected format:
        ```json
        {
            "command": "tool_name",
            "parameters": { ... }
        }
        ```
        or just the JSON object.
        """
        try:
            # 1. Try to find JSON code block
            match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                # 2. Try to find raw JSON object if no code block
                # This is a simple heuristic: find first { and last }
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_str = text[start:end+1]
                else:
                    return None

            data = json.loads(json_str)
            
            if "command" in data and "parameters" in data:
                return data["command"], data["parameters"]
            
            return None

        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM output")
            return None
        except Exception as e:
            logger.error(f"Error parsing command: {e}")
            return None
