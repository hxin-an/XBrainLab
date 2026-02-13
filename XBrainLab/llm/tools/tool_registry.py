from typing import Any

from .base import BaseTool


class ToolRegistry:
    """
    Registry for managing available LLM tools.
    Supports dynamic filtering based on system state.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool instance."""
        if tool.name in self._tools:
            # logger.warning(f"Overwriting tool {tool.name}")
            pass
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a specific tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_active_tools(self, study: Any) -> list[BaseTool]:
        """
        Return the list of tools that are valid for the current state.
        """
        return [tool for tool in self._tools.values() if tool.is_valid(study)]
