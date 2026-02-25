"""Factory module for dispatching raw data loading by file extension."""

import os
from collections.abc import Callable
from typing import ClassVar

from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.utils.logger import logger


class RawDataLoaderFactory:
    """Factory for creating Raw data loaders based on file extension.

    Maintains a registry of loader functions keyed by file extension.
    New formats can be supported by calling :meth:`register_loader`.

    Attributes:
        _loaders: Class-level registry mapping lowercase file extensions
            to loader callables.
    """

    _loaders: ClassVar[dict[str, Callable[[str], Raw | None]]] = {}

    @classmethod
    def register_loader(
        cls, extension: str, loader_func: Callable[[str], Raw | None]
    ) -> None:
        """Register a loader function for a specific file extension.

        Args:
            extension: File extension (including dot, e.g., '.gdf').
            loader_func: Function that takes a filepath and returns a Raw
                object or None.
        """
        cls._loaders[extension.lower()] = loader_func

    @classmethod
    def get_loader(cls, filepath: str) -> Callable[[str], Raw | None]:
        """Get the loader function for the given filepath.

        Args:
            filepath: Path to the file.

        Returns:
            Loader function.

        Raises:
            UnsupportedFormatError: If no loader is registered for the file extension.
        """
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        if ext not in cls._loaders:
            raise UnsupportedFormatError(ext)

        return cls._loaders[ext]

    @classmethod
    def load(cls, filepath: str) -> Raw | None:
        """Load raw data from file using the appropriate loader.

        Args:
            filepath: Path to the file.

        Returns:
            Raw object if successful, None otherwise.

        Raises:
            UnsupportedFormatError: If format is not supported.
            FileCorruptedError: If file loading fails due to corruption/IO error.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        loader = cls.get_loader(filepath)

        try:
            return loader(filepath)
        except Exception as e:
            # If the loader itself didn't handle the exception, wrap it
            # Note: Loaders in raw_data_loader.py currently catch exceptions and
            # return None. We might want to change that behavior to propagate
            # errors for better UI feedback.
            # For now, we assume loaders might log and return None, or raise
            # specific errors.
            logger.error("Error loading file %s: %s", filepath, e, exc_info=True)
            raise FileCorruptedError(filepath, str(e)) from e
