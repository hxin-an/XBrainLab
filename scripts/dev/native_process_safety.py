"""Platform-aware safety setup for native lifecycle subprocesses."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeProcessSafety:
    """Report whether this process can and did disable POSIX core dumps."""

    core_dump_limit_supported: bool
    core_dumps_disabled: bool


def disable_core_dumps() -> NativeProcessSafety:
    """Disable POSIX core files before loading native UI libraries."""
    if os.name != "posix":
        return NativeProcessSafety(False, False)

    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        disabled = resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
    except (AttributeError, ImportError, OSError, ValueError):
        disabled = False
    return NativeProcessSafety(True, disabled)
