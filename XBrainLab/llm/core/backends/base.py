from abc import ABC, abstractmethod


class BaseBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def load(self):
        """Initializes the backend resources."""

    @abstractmethod
    def generate_stream(self, messages: list):
        """Yields text chunks from the LLM."""
