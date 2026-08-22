"""JSON-safe observations of backend-owned public application truth."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import ApplicationViewPublication, CommandResult

_SENSITIVE_KEY_PARTS = {
    "diagnostic",
    "diagnostics",
    "directories",
    "directory",
    "file",
    "filename",
    "filenames",
    "files",
    "metadata",
    "path",
    "paths",
    "patient",
    "prompt",
    "prompts",
    "secret",
    "secrets",
    "subject",
    "token",
    "tokens",
}


def _artifact_safe(value: Any, *, key: str = "") -> Any:
    """Remove local identifiers while preserving scoreable workflow fields."""
    key_parts = set(key.casefold().replace("-", "_").split("_"))
    if value and key_parts & _SENSITIVE_KEY_PARTS:
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(child_key): _artifact_safe(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_artifact_safe(item, key=key) for item in value]
    return value


def capture_publication(
    publication: ApplicationViewPublication, *, sequence: int
) -> dict[str, Any]:
    """Project a public publication without inferring or mutating product state."""
    capabilities = {
        name: {
            "enabled": capability.enabled,
            "requires_confirmation": capability.requires_confirmation,
            "reasons": list(capability.reasons),
        }
        for name, capability in publication.effective_capabilities.capabilities.items()
    }
    return {
        "sequence": sequence,
        "kind": "publication",
        "payload": {
            "generation": publication.generation,
            "revision": publication.revision,
            "verified": publication.verified,
            "stale": publication.stale,
            "state": _artifact_safe(publication.state.to_dict()),
            "capabilities": capabilities,
        },
    }


def capture_command_result(result: CommandResult, *, sequence: int) -> dict[str, Any]:
    """Project the public command envelope without interpreting backend policy."""
    state = result.state.to_dict() if hasattr(result.state, "to_dict") else result.state
    return {
        "sequence": sequence,
        "kind": "command_result",
        "payload": {
            "command_name": result.command_name,
            "status": result.status.value,
            "message": result.message,
            "error_type": result.error_type.value,
            "recoverable": result.recoverable,
            "state": _artifact_safe(state),
            "changed_state": result.changed_state.to_dict(),
            "diagnostics": _artifact_safe(result.diagnostics, key="diagnostics"),
        },
    }
