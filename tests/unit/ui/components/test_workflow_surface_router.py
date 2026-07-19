"""Contract tests for assistant handoff to existing product surfaces."""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field

import pytest

from XBrainLab.ui.components import workflow_surface_router
from XBrainLab.ui.components.workflow_surface_router import (
    WorkflowPanel,
    WorkflowSurfaceOutcome,
    WorkflowSurfaceRequest,
    WorkflowSurfaceResult,
    WorkflowSurfaceRoute,
    WorkflowSurfaceRouter,
    WorkflowSurfaceStatus,
)


@dataclass
class _PanelNavigator:
    targets: list[WorkflowPanel] = field(default_factory=list)
    error: Exception | None = None

    def __call__(self, target: WorkflowPanel) -> None:
        self.targets.append(target)
        if self.error is not None:
            raise self.error


@dataclass
class _DialogSurface:
    result: WorkflowSurfaceResult
    opened: int = 0
    error: Exception | None = None
    received_suggestions: dict[str, str] = field(default_factory=dict)
    received_decision_fields: tuple[str, ...] = ()
    received_request_id: str = ""

    def __call__(self, request: WorkflowSurfaceRequest) -> WorkflowSurfaceResult:
        self.opened += 1
        self.received_suggestions = request.suggestions
        self.received_decision_fields = request.decision_fields
        self.received_request_id = request.request_id
        if self.error is not None:
            raise self.error
        return self.result


def _router(
    surface: _DialogSurface | None,
    *,
    command_name: str = "create_epoch",
    panel: WorkflowPanel = WorkflowPanel.PREPROCESS,
) -> tuple[WorkflowSurfaceRouter, _PanelNavigator]:
    navigator = _PanelNavigator()
    router = WorkflowSurfaceRouter(
        navigator,
        {
            command_name: WorkflowSurfaceRoute(
                panel=panel,
                open_surface=surface,
            )
        },
    )
    return router, navigator


def test_completed_dialog_is_the_only_verified_workflow_completion():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(
            WorkflowSurfaceStatus.COMPLETED,
            "Epoch settings were applied.",
        )
    )
    router, navigator = _router(dialog)

    outcome = router.open("create_epoch")

    assert outcome == WorkflowSurfaceOutcome(
        WorkflowSurfaceStatus.COMPLETED,
        "create_epoch",
        "Epoch settings were applied.",
    )
    assert outcome.routed is True
    assert outcome.is_verified_completion is True
    assert navigator.targets == [WorkflowPanel.PREPROCESS]
    assert dialog.opened == 1


def test_router_passes_user_supplied_values_to_existing_surface_adapter():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(WorkflowSurfaceStatus.CANCELLED, "Cancelled.")
    )
    router, _navigator = _router(dialog)

    router.open(
        "create_epoch",
        request_id="request-1",
        decision_fields=("target_event", "epoch_window"),
        suggested_values={"target_event": "769", "t_min": "-0.2"},
    )

    assert dialog.received_suggestions == {
        "target_event": "769",
        "t_min": "-0.2",
    }
    assert dialog.received_decision_fields == ("target_event", "epoch_window")
    assert dialog.received_request_id == "request-1"


def test_scheduled_dialog_outcome_does_not_claim_verified_completion():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(
            WorkflowSurfaceStatus.ACCEPTED,
            "The dialog was accepted; completion is still awaiting verification.",
        )
    )
    router, _navigator = _router(dialog)

    outcome = router.open("create_epoch")

    assert outcome.status is WorkflowSurfaceStatus.ACCEPTED
    assert outcome.routed is True
    assert outcome.is_verified_completion is False


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (WorkflowSurfaceStatus.CANCELLED, "The user cancelled the dialog."),
        (
            WorkflowSurfaceStatus.CLOSED_WITHOUT_CHANGE,
            "The dialog closed without applying changes.",
        ),
    ],
)
def test_dialog_exit_without_completion_is_not_reported_as_completed(status, message):
    dialog = _DialogSurface(WorkflowSurfaceResult(status, message))
    router, _navigator = _router(dialog)

    outcome = router.open("create_epoch")

    assert outcome.status is status
    assert outcome.message == message
    assert outcome.routed is True
    assert outcome.is_verified_completion is False


def test_panel_only_route_reports_navigation_without_completion():
    router, navigator = _router(
        None,
        command_name="review_interpretation",
        panel=WorkflowPanel.DATASET,
    )

    outcome = router.open(" REVIEW_INTERPRETATION ")

    assert outcome.status is WorkflowSurfaceStatus.NAVIGATED
    assert outcome.command_name == "review_interpretation"
    assert outcome.routed is True
    assert outcome.is_verified_completion is False
    assert navigator.targets == [WorkflowPanel.DATASET]


def test_blocked_surface_is_explicit_and_not_reported_as_completed():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(
            WorkflowSurfaceStatus.BLOCKED,
            "Create epochs before configuring training.",
        )
    )
    router, _navigator = _router(dialog)

    outcome = router.open("create_epoch")

    assert outcome.status is WorkflowSurfaceStatus.BLOCKED
    assert outcome.is_verified_completion is False


def test_navigation_failure_does_not_open_dialog_or_leak_exception_details():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(WorkflowSurfaceStatus.COMPLETED, "Applied.")
    )
    router, navigator = _router(dialog)
    navigator.error = RuntimeError("private dataset path /tmp/subject.gdf")

    outcome = router.open("create_epoch")

    assert outcome.status is WorkflowSurfaceStatus.FAILED
    assert outcome.routed is False
    assert outcome.is_verified_completion is False
    assert "/tmp/subject.gdf" not in outcome.message
    assert dialog.opened == 0


def test_dialog_failure_is_typed_and_does_not_leak_exception_details():
    dialog = _DialogSurface(
        WorkflowSurfaceResult(WorkflowSurfaceStatus.COMPLETED, "Applied."),
        error=RuntimeError("private dataset path /tmp/subject.gdf"),
    )
    router, _navigator = _router(dialog)

    outcome = router.open("create_epoch")

    assert outcome.status is WorkflowSurfaceStatus.FAILED
    assert outcome.routed is False
    assert outcome.is_verified_completion is False
    assert "/tmp/subject.gdf" not in outcome.message
    assert dialog.opened == 1


def test_invalid_dialog_return_fails_closed_instead_of_guessing_completion():
    class _InvalidDialog:
        def __call__(self, _request):
            return True

    navigator = _PanelNavigator()
    router = WorkflowSurfaceRouter(
        navigator,
        {
            "create_epoch": WorkflowSurfaceRoute(
                WorkflowPanel.PREPROCESS,
                _InvalidDialog(),  # type: ignore[arg-type]
            )
        },
    )

    outcome = router.open("create_epoch")

    assert outcome.status is WorkflowSurfaceStatus.FAILED
    assert outcome.is_verified_completion is False
    assert "valid outcome" in outcome.message


def test_unknown_surface_is_typed_unavailable():
    router = WorkflowSurfaceRouter(_PanelNavigator(), {})

    outcome = router.open("unknown_tool")

    assert outcome.status is WorkflowSurfaceStatus.UNAVAILABLE
    assert outcome.routed is False
    assert outcome.is_verified_completion is False


def test_router_has_no_attribute_reflection_or_generation_inference():
    tree = ast.parse(inspect.getsource(workflow_surface_router))
    reflected_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "hasattr", "setattr"}
    ]
    generation_names = [
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and "generation" in node.id.lower()
    ]

    assert reflected_calls == []
    assert generation_names == []
