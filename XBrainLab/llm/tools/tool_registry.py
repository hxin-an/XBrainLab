"""Dynamic tool registry for managing LLM-callable tools.

Provides registration, lookup, and listing of
:class:`~XBrainLab.llm.tools.base.BaseTool` instances.

Tool *filtering* (which tools are available at each pipeline stage)
is handled by :data:`~XBrainLab.llm.pipeline_state.STAGE_CONFIG`.
"""

from XBrainLab.backend.utils.logger import logger

from .base import BaseTool


class ToolRegistry:
    """Registry for managing available LLM tools.

    Supports dynamic filtering based on the current ``Study`` state so
    that only valid tools are presented to the agent at each turn.

    Attributes:
        _tools: Internal mapping from tool name to ``BaseTool`` instance.

    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool instance.

        If a tool with the same name already exists it will be
        silently overwritten.

        Args:
            tool: The ``BaseTool`` instance to register.

        """
        if tool.name in self._tools:
            logger.warning("Overwriting tool %s", tool.name)
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a specific tool by name.

        Args:
            name: The canonical tool name.

        Returns:
            The matching ``BaseTool`` instance, or ``None`` if not found.

        """
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """Return all registered tools.

        Returns:
            A list of every ``BaseTool`` instance currently registered.

        """
        return list(self._tools.values())
