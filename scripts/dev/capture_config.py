"""Own temporary preferences for one standalone desktop capture."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from XBrainLab.platform_paths import CONFIG_DIR_ENV, SETTINGS_FILENAME

if TYPE_CHECKING:
    from XBrainLab.llm.core.config import LLMConfig


@contextmanager
def isolated_capture_config(config: LLMConfig | None = None) -> Iterator[Path]:
    """Isolate preferences through capture shutdown, preserving the selected model."""
    previous = os.environ.get(CONFIG_DIR_ENV)
    with TemporaryDirectory(prefix="xbrainlab-capture-config-") as directory:
        root = Path(directory)
        os.environ[CONFIG_DIR_ENV] = str(root)
        try:
            if config is not None and not config.save_to_file(
                str(root / SETTINGS_FILENAME)
            ):
                raise RuntimeError(
                    "Could not copy Assistant settings into capture isolation."
                )
            yield root
        finally:
            if previous is None:
                os.environ.pop(CONFIG_DIR_ENV, None)
            else:
                os.environ[CONFIG_DIR_ENV] = previous
