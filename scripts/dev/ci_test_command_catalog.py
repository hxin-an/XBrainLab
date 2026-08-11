"""Dependency-free logical command IDs used to expand CI test matrices."""

from __future__ import annotations

from typing import Final

LINUX_CI_COMMANDS: Final = (
    "linux-unit-backend",
    "linux-unit-llm-agent",
    "linux-unit-scripts",
    "linux-unit-ui",
    "linux-unit-rest",
    "linux-integration-agent-timing",
    "linux-integration-ui",
    "linux-integration-rest",
)

PLATFORM_CI_COMMANDS: Final = (
    "platform-core-contracts",
    "platform-product-lifecycle",
)
