"""Real-model adaptive-workflow UI-handoff boundary walkthrough.

Exports are loaded lazily so stdlib-only source-identity consumers do not import
the Qt product or image stack during CI plan/receipt verification.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.dev.chatpanel_guided_boundary.dialog import (
        capture_and_cancel_workflow_dialog,
    )
    from scripts.dev.chatpanel_guided_boundary.evidence import (
        GuidedBoundaryEvidenceAssembler,
        render_guided_boundary_markdown,
    )
    from scripts.dev.chatpanel_guided_boundary.state import (
        GuidedBoundaryPhase,
        GuidedBoundaryState,
        reconcile_closed_event_loop,
    )
    from scripts.dev.chatpanel_guided_boundary.validation import (
        DEFAULT_MODEL_ID,
        EXPECTED_AUTO_CHAIN,
        build_guided_prompts,
        validate_guided_boundary_artifact_root,
        validate_guided_boundary_payload,
    )

_EXPORT_MODULES = {
    "capture_and_cancel_workflow_dialog": "dialog",
    "GuidedBoundaryEvidenceAssembler": "evidence",
    "render_guided_boundary_markdown": "evidence",
    "GuidedBoundaryPhase": "state",
    "GuidedBoundaryState": "state",
    "reconcile_closed_event_loop": "state",
    "DEFAULT_MODEL_ID": "validation",
    "EXPECTED_AUTO_CHAIN": "validation",
    "build_guided_prompts": "validation",
    "validate_guided_boundary_artifact_root": "validation",
    "validate_guided_boundary_payload": "validation",
}

__all__ = [
    "DEFAULT_MODEL_ID",
    "EXPECTED_AUTO_CHAIN",
    "GuidedBoundaryEvidenceAssembler",
    "GuidedBoundaryPhase",
    "GuidedBoundaryState",
    "build_guided_prompts",
    "capture_and_cancel_workflow_dialog",
    "reconcile_closed_event_loop",
    "render_guided_boundary_markdown",
    "validate_guided_boundary_artifact_root",
    "validate_guided_boundary_payload",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
