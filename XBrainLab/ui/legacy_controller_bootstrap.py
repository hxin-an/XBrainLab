"""Legacy controller bootstrap boundary for workflow panel construction."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegacyWorkflowControllers:
    """Controller bundle kept only for current panel constructor compatibility."""

    dataset: Any | None
    preprocess: Any | None
    training: Any | None
    evaluation: Any | None
    visualization: Any | None


def get_legacy_workflow_controllers_for_panel_bootstrap(
    study: Any,
) -> LegacyWorkflowControllers:
    """Return temporary workflow controllers for panel bootstrap compatibility.

    Product action, readiness, and refresh truth must come from ApplicationService
    commands, snapshots, and refresh coordinators. This helper is the named UI
    quarantine for panel constructors that still accept controllers as observer or
    legacy adapters.
    """
    get_controller = getattr(study, "get_controller", None)
    if not callable(get_controller):
        return LegacyWorkflowControllers(
            dataset=None,
            preprocess=None,
            training=None,
            evaluation=None,
            visualization=None,
        )

    return LegacyWorkflowControllers(
        dataset=get_controller("dataset"),
        preprocess=get_controller("preprocess"),
        training=get_controller("training"),
        evaluation=get_controller("evaluation"),
        visualization=get_controller("visualization"),
    )
