from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all LLM tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool (e.g., 'load_data')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of what the tool does."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON schema describing the parameters."""

    @abstractmethod
    def execute(self, study: Any, **kwargs) -> str:
        """
        Executes the tool action.

        Args:
            study: The global Study instance.
            **kwargs: Parameters passed by the LLM.

        Returns:
            str: A message describing the result of the execution.
        """
