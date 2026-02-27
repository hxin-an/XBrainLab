"""Base class definition for LLM-callable tools.

All tools exposed to the LLM agent must inherit from :class:`BaseTool`
and implement its abstract interface.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all LLM tools.

    Subclasses must provide concrete implementations for :pyattr:`name`,
    :pyattr:`description`, :pyattr:`parameters`, and :meth:`execute`.
    Optionally override :meth:`is_valid` to restrict tool availability
    based on the current ``Study`` state.
    """

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

    @property
    def requires_confirmation(self) -> bool:
        """Whether this tool requires explicit user confirmation before execution.

        Dangerous or irreversible actions (e.g., clearing data, starting
        long-running training) should return ``True`` so the controller
        can present a confirmation dialog to the user.

        Returns:
            ``False`` by default.  Override in subclasses to mark
            dangerous operations.

        """
        return False

    def is_valid(self, study: Any) -> bool:
        """Check whether the tool is valid in the current application state.

        Override in subclasses to enforce preconditions (e.g., data must
        be loaded before preprocessing tools become available).

        Args:
            study: The global ``Study`` instance representing the
                current application state.

        Returns:
            ``True`` if the tool may be invoked; ``False`` otherwise.
                Defaults to ``True``.

        """
        return True

    @abstractmethod
    def execute(self, study: Any, **kwargs) -> str:
        """Executes the tool action.

        Args:
            study: The global Study instance.
            **kwargs: Parameters passed by the LLM.

        Returns:
            str: A message describing the result of the execution.

        """
