"""Route assistant decisions to the product's existing EEG workflow surfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XBrainLab.backend.utils.logger import logger

_Route = tuple[str, str, str | None, str | None]

_WORKFLOW_ROUTES: dict[str, _Route] = {
    "scan_source": ("dataset", "dataset_panel", "action_handler", "import_data"),
    "review_interpretation": ("dataset", "dataset_panel", None, None),
    "preview_interpretation": ("dataset", "dataset_panel", None, None),
    "validate_interpretation": ("dataset", "dataset_panel", None, None),
    "apply_interpretation": ("dataset", "dataset_panel", None, None),
    "create_epoch": ("preprocess", "preprocess_panel", "sidebar", "open_epoching"),
    "generate_dataset": ("training", "training_panel", "sidebar", "split_data"),
    "configure_training": (
        "training",
        "training_panel",
        "sidebar",
        "training_setting",
    ),
    "saliency": (
        "visualization",
        "visualization_panel",
        "sidebar",
        "set_saliency",
    ),
}


class WorkflowSurfaceRouter:
    """Open an existing product panel or dialog for an assistant decision."""

    def __init__(
        self,
        main_window: Any,
        switch_panel: Callable[[dict[str, str]], None],
    ) -> None:
        self._main_window = main_window
        self._switch_panel = switch_panel

    def open(self, command_name: str) -> bool:
        normalized = str(command_name or "").strip().lower()
        route = _WORKFLOW_ROUTES.get(normalized)
        if route is None:
            return False

        panel_name, panel_attr, owner_attr, method_name = route
        self._switch_panel({"panel": panel_name})
        if method_name is None:
            return True

        panel = getattr(self._main_window, panel_attr, None)
        owner = getattr(panel, owner_attr, None) if owner_attr else panel
        open_surface = getattr(owner, method_name, None)
        if not callable(open_surface):
            logger.warning(
                "Assistant could not open existing UI surface for %s",
                normalized,
            )
            return False
        open_surface()
        return True
