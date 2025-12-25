import re
from typing import List, Dict, Any
# We need to import command_params to validate commands.
# Assuming prompts.py is in the parent directory relative to core/
# or we can pass it in. For now, let's assume we can import it from remote.prompts
# But since this is in remote/core, we need to adjust imports.
# Ideally, command_params should be passed in or imported from a config module.
import sys
import os

# Add parent directory to path to allow importing prompts
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from prompts import command_params
except ImportError:
    # Fallback or mock if running in isolation
    command_params = {}

class CommandParser:
    """
    Command Parser.
    
    Responsible for:
    1. Extracting JSON-like commands from unstructured LLM text.
    2. Validating commands against a schema (command_params).
    """

    def __init__(self, params_schema: Dict = None):
        """
        Initialize the parser.

        Args:
            params_schema (Dict): Dictionary defining valid commands and their required parameters.
                                  If None, uses the default from prompts.py.
        """
        self.command_params = params_schema if params_schema is not None else command_params
        
        # Pre-compile regex patterns
        self.command_pattern = re.compile(r'"command":\s*"([^"]+)"')
        self.parameter_pattern = re.compile(r'"parameters":\s*(\{[^{}]+\})')
        self.text_pattern = re.compile(r'"text":\s*"([^"]+)"')

    def parse(self, output_text: str) -> List[Dict[str, Any]]:
        """
        Parse the output text and extract valid commands.

        Args:
            output_text (str): The raw text output from the LLM.

        Returns:
            List[Dict]: A list of command dictionaries or text responses.
                        e.g. [{"command": "Import Data", "parameters": {...}}, {"text": "..."}]
        """
        commands = self.command_pattern.findall(output_text)
        parameters = self.parameter_pattern.findall(output_text)
        texts = self.text_pattern.findall(output_text)

        extracted_commands = []

        for i, command in enumerate(commands):
            cmd = command.lower()
            
            # 1. Validate Command Name
            if cmd not in self.command_params:
                continue

            # 2. Parse Parameters
            param_str = parameters[i] if i < len(parameters) else '{}'
            try:
                # Using eval is risky but was in original code. 
                # Ideally we should use json.loads but the LLM might output single quotes or loose JSON.
                # For now, we keep eval but wrapped in try-except.
                params = eval(param_str)
            except Exception as e:
                print(f"[CommandParser] Error parsing parameters: {e}")
                continue

            # 3. Validate Parameters
            if not self._validate_params(cmd, params):
                continue

            extracted_commands.append({"command": cmd, "parameters": params})

        # Append text responses
        for t in texts:
            extracted_commands.append({"text": t})

        return extracted_commands

    def _validate_params(self, cmd: str, params: Dict) -> bool:
        """Check if parameters satisfy the schema requirements."""
        schema = self.command_params.get(cmd, {})
        required = schema.get("required", [])
        at_least_one = schema.get("at_least_one", [])

        # Check required
        if any(r not in params for r in required):
            return False
            
        # Check at_least_one
        if at_least_one and not any(p in params for p in at_least_one):
            return False

        return True
