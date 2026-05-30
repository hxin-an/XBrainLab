"""Controller compatibility bootstrap boundary for workflow panel construction."""

from collections.abc import Callable
from typing import Any


class CompatibilityWorkflowControllers:
    """Lazy controller bundle kept only for panel constructor compatibility."""

    def __init__(
        self,
        get_controller: Callable[[str], Any] | None,
    ) -> None:
        self._get_controller = get_controller
        self._cache: dict[str, Any | None] = {}

    def _controller(self, name: str) -> Any | None:
        if name not in self._cache:
            self._cache[name] = (
                self._get_controller(name) if self._get_controller else None
            )
        return self._cache[name]

    @property
    def dataset(self) -> Any | None:
        return self._controller("dataset")

    @property
    def preprocess(self) -> Any | None:
        return self._controller("preprocess")

    @property
    def training(self) -> Any | None:
        return self._controller("training")

    @property
    def evaluation(self) -> Any | None:
        return self._controller("evaluation")

    @property
    def visualization(self) -> Any | None:
        return self._controller("visualization")


def get_compatibility_workflow_controllers_for_panel_bootstrap(
    study: Any,
) -> CompatibilityWorkflowControllers:
    """Return temporary workflow controllers for panel bootstrap compatibility.

    Product action, readiness, and refresh truth must come from ApplicationService
    commands, snapshots, and refresh coordinators. This helper is the named UI
    quarantine for panel constructors that still accept controllers as observer or
    compatibility adapters.
    """
    get_controller = getattr(study, "get_controller", None)
    return CompatibilityWorkflowControllers(
        get_controller if callable(get_controller) else None,
    )
