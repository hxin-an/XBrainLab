"""Host-owned adapters for typed assistant handoff to existing product UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Any

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.response_presentation import panel_target_for_command
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSession,
    WorkflowUiHandoffTransitionStatus,
)
from XBrainLab.ui.components.workflow_surface_router import (
    WorkflowPanel,
    WorkflowSurfaceCallback,
    WorkflowSurfaceOutcome,
    WorkflowSurfaceRequest,
    WorkflowSurfaceResult,
    WorkflowSurfaceRoute,
    WorkflowSurfaceRouter,
    WorkflowSurfaceStatus,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionEvent,
    InteractionCompletionSession,
    InteractionCompletionStatus,
    InteractionOutcome,
    InteractionStatus,
    bind_interaction_completion,
)
from XBrainLab.ui.panel_navigation import PanelPreparationFailure
from XBrainLab.ui.product_language import decision_field_labels

_PANEL_INDEX: dict[WorkflowPanel, int] = {
    WorkflowPanel.DATASET: 0,
    WorkflowPanel.PREPROCESS: 1,
    WorkflowPanel.TRAINING: 2,
    WorkflowPanel.EVALUATION: 3,
    WorkflowPanel.VISUALIZATION: 4,
}

_PANEL_LABEL: dict[WorkflowPanel, str] = {
    WorkflowPanel.DATASET: "Dataset",
    WorkflowPanel.PREPROCESS: "Preprocess",
    WorkflowPanel.TRAINING: "Training",
    WorkflowPanel.EVALUATION: "Evaluation",
    WorkflowPanel.VISUALIZATION: "Visualization",
}

_RESOLUTION_STATUS: dict[
    WorkflowSurfaceStatus,
    WorkflowUiHandoffResolutionStatus,
] = {
    WorkflowSurfaceStatus.ACCEPTED: (WorkflowUiHandoffResolutionStatus.COMMAND_PENDING),
    WorkflowSurfaceStatus.COMPLETED: WorkflowUiHandoffResolutionStatus.COMPLETED,
    WorkflowSurfaceStatus.CANCELLED: WorkflowUiHandoffResolutionStatus.CANCELLED,
    WorkflowSurfaceStatus.CLOSED_WITHOUT_CHANGE: (
        WorkflowUiHandoffResolutionStatus.CANCELLED
    ),
    WorkflowSurfaceStatus.NAVIGATED: (WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI),
    WorkflowSurfaceStatus.BLOCKED: WorkflowUiHandoffResolutionStatus.BLOCKED,
    WorkflowSurfaceStatus.UNAVAILABLE: (WorkflowUiHandoffResolutionStatus.UNAVAILABLE),
    WorkflowSurfaceStatus.FAILED: WorkflowUiHandoffResolutionStatus.FAILED,
}

_COMPLETION_STATUS: dict[
    InteractionCompletionStatus,
    WorkflowUiHandoffResolutionStatus,
] = {
    InteractionCompletionStatus.COMPLETED: (
        WorkflowUiHandoffResolutionStatus.COMPLETED
    ),
    InteractionCompletionStatus.FAILED: WorkflowUiHandoffResolutionStatus.FAILED,
    InteractionCompletionStatus.CANCELLED: (
        WorkflowUiHandoffResolutionStatus.CANCELLED
    ),
}

WorkflowUiHandoffTerminalCallback = Callable[
    [WorkflowUiHandoffResolution],
    bool | None,
]


@dataclass(slots=True)
class _ActiveWorkflowUiHandoff:
    session: WorkflowUiHandoffSession
    completion: InteractionCompletionSession
    on_terminal: WorkflowUiHandoffTerminalCallback | None


@dataclass(slots=True)
class _PendingWorkflowSurfaceOpen:
    generation: int
    panel: WorkflowPanel
    open_surface: WorkflowSurfaceCallback
    request: WorkflowSurfaceRequest
    active: _ActiveWorkflowUiHandoff


@dataclass(slots=True)
class _PendingPanelNavigationFailure:
    generation: int
    panel: WorkflowPanel
    failure: PanelPreparationFailure
    active: _ActiveWorkflowUiHandoff


class WorkflowUiHandoffHost:
    """Own typed routes from assistant decisions into product UI surfaces.

    This adapter is deliberately UI-specific. It owns the stable route table,
    main-window navigation, concrete dialog entry points, and conversion from
    dialog-local :class:`InteractionOutcome` values into the assistant-facing
    surface contract. ``AgentManager`` only wires the request and presents the
    returned outcome.
    """

    def __init__(
        self,
        main_window: Any,
        *,
        application_service: Any | None = None,
    ) -> None:
        self._main_window = main_window
        if application_service is not None:
            logger.debug(
                "WorkflowUiHandoffHost ignores the legacy ApplicationService "
                "argument; product actions resolve their typed UI runtime."
            )
        self._active: _ActiveWorkflowUiHandoff | None = None
        self._navigation_pending_panel: WorkflowPanel | None = None
        self._navigation_generation = 0
        self._pending_surface_open: _PendingWorkflowSurfaceOpen | None = None
        self._pending_navigation_failure: _PendingPanelNavigationFailure | None = None
        self._router = WorkflowSurfaceRouter(
            self._navigate,
            self._build_routes(),
        )

    def open(
        self,
        request: WorkflowUiHandoffRequest,
        *,
        on_terminal: WorkflowUiHandoffTerminalCallback | None = None,
    ) -> WorkflowUiHandoffResolution:
        """Open the product surface named by one validated typed request."""
        if not isinstance(request, WorkflowUiHandoffRequest):
            raise TypeError("Workflow UI handoff requires WorkflowUiHandoffRequest.")
        if on_terminal is not None and not callable(on_terminal):
            raise TypeError("Workflow UI handoff terminal callback must be callable.")
        if self._active is not None:
            raise RuntimeError("A workflow UI handoff session is already active.")

        completion = InteractionCompletionSession(
            request_id=request.request_id,
            command_name=request.command_name,
            on_terminal=self._on_completion_terminal,
        )
        active = _ActiveWorkflowUiHandoff(
            session=WorkflowUiHandoffSession(request),
            completion=completion,
            on_terminal=on_terminal,
        )
        self._active = active
        with bind_interaction_completion(completion):
            surface_outcome = self._router.open(
                request.command_name,
                request_id=request.request_id,
                decision_fields=request.decision_fields,
                suggested_values=request.suggestions,
            )
        if (
            surface_outcome.status is WorkflowSurfaceStatus.ACCEPTED
            and not completion.has_scheduled_command
        ):
            surface_outcome = WorkflowSurfaceOutcome(
                status=WorkflowSurfaceStatus.FAILED,
                command_name=request.command_name,
                message=(
                    "The settings dialog closed without scheduling the requested "
                    "command."
                ),
                request_id=request.request_id,
            )
        try:
            self._show_decision_status(request, surface_outcome)
        except Exception:
            logger.exception(
                "Assistant handoff status presentation failed for %s",
                request.command_name,
            )
        resolution = WorkflowUiHandoffResolution.for_request(
            request,
            status=self._initial_resolution_status(active, surface_outcome),
            message=surface_outcome.message,
        )
        transition = active.session.resolve(resolution)
        if transition is WorkflowUiHandoffTransitionStatus.TERMINATED:
            self._clear_active(active)
        elif transition not in {
            WorkflowUiHandoffTransitionStatus.ADVANCED,
            WorkflowUiHandoffTransitionStatus.DUPLICATE,
        }:
            logger.error(
                "Workflow UI handoff could not record initial status %s",
                resolution.status,
            )
            failed = WorkflowUiHandoffResolution.for_request(
                request,
                status=WorkflowUiHandoffResolutionStatus.FAILED,
                message="The settings handoff returned an invalid lifecycle status.",
            )
            active.session.resolve(failed)
            self._clear_active(active)
            return failed
        return resolution

    @property
    def active_request(self) -> WorkflowUiHandoffRequest | None:
        """Return the exact request currently waiting for a terminal callback."""
        active = self._active
        return active.session.request if active is not None else None

    def resolve_terminal(self, payload: object) -> bool:
        """Resolve the active request from one real async command callback."""
        active = self._active
        if active is None:
            logger.warning("Ignored UI handoff callback with no active session")
            return False
        request = active.session.request
        if not isinstance(payload, InteractionCompletionEvent):
            logger.error("Malformed workflow UI handoff callback: %r", payload)
            resolution = WorkflowUiHandoffResolution.for_request(
                request,
                status=WorkflowUiHandoffResolutionStatus.FAILED,
                message="The settings command returned an invalid completion callback.",
            )
            return self._finish_active(active, resolution)
        if (
            payload.request_id != request.request_id
            or payload.command_name != request.command_name
        ):
            logger.warning(
                "Ignored stale workflow UI callback for %s (%s)",
                payload.command_name,
                payload.request_id,
            )
            return False
        resolution = WorkflowUiHandoffResolution.for_request(
            request,
            status=_COMPLETION_STATUS[payload.status],
            message=payload.message,
        )
        return self._finish_active(active, resolution)

    def retry_terminal_delivery(self) -> bool:
        """Retry a terminal callback that explicitly rejected ownership."""
        active = self._active
        if active is None:
            return True
        resolution = active.session.terminal_resolution
        if resolution is None:
            return False
        return self._deliver_terminal(active, resolution)

    def _on_completion_terminal(self, event: InteractionCompletionEvent) -> None:
        """Adapt the completion observer's notification-only callback shape."""
        self.resolve_terminal(event)

    def abandon_active(self) -> None:
        """Invalidate host delivery after Stop while the controller cancels its turn."""
        self._invalidate_pending_navigation()
        active = self._active
        if active is None:
            return
        active.completion.cancel(
            "The pending settings command was cancelled.",
            notify=False,
        )
        self._active = None

    def _finish_active(
        self,
        active: _ActiveWorkflowUiHandoff,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        if self._active is not active:
            return False
        transition = active.session.resolve(resolution)
        if transition is not WorkflowUiHandoffTransitionStatus.TERMINATED:
            return False
        return self._deliver_terminal(active, resolution)

    def _deliver_terminal(
        self,
        active: _ActiveWorkflowUiHandoff,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        if self._active is not active:
            return False
        callback = active.on_terminal
        if callback is None:
            self._clear_active(active)
            return True
        try:
            accepted = callback(resolution)
        except Exception:
            logger.exception("Workflow UI handoff terminal callback failed")
            return False
        if accepted is False:
            logger.error(
                "Workflow UI handoff terminal callback rejected %s (%s)",
                resolution.command_name,
                resolution.request_id,
            )
            return False
        self._clear_active(active)
        return True

    def _clear_active(self, active: _ActiveWorkflowUiHandoff) -> None:
        if self._active is active:
            self._active = None

    def _build_routes(self) -> dict[str, WorkflowSurfaceRoute]:
        return {
            CommandName.SCAN_SOURCE.value: self._route(
                CommandName.SCAN_SOURCE, self._open_data_import
            ),
            CommandName.REVIEW_INTERPRETATION.value: self._route(
                CommandName.REVIEW_INTERPRETATION
            ),
            CommandName.PREVIEW_INTERPRETATION.value: self._route(
                CommandName.PREVIEW_INTERPRETATION
            ),
            CommandName.VALIDATE_INTERPRETATION.value: self._route(
                CommandName.VALIDATE_INTERPRETATION
            ),
            CommandName.APPLY_INTERPRETATION.value: self._route(
                CommandName.APPLY_INTERPRETATION,
                self._open_current_import_review,
            ),
            CommandName.PREPROCESS.value: self._route(CommandName.PREPROCESS),
            CommandName.CREATE_EPOCH.value: self._route(
                CommandName.CREATE_EPOCH, self._open_epoching
            ),
            CommandName.GENERATE_DATASET.value: self._route(
                CommandName.GENERATE_DATASET, self._open_data_splitting
            ),
            CommandName.CONFIGURE_TRAINING.value: self._route(
                CommandName.CONFIGURE_TRAINING, self._open_training_settings
            ),
            CommandName.TRAIN.value: self._route(CommandName.TRAIN),
            CommandName.EVALUATE.value: self._route(CommandName.EVALUATE),
            CommandName.VISUALIZE.value: self._route(CommandName.VISUALIZE),
            CommandName.SALIENCY.value: self._route(
                CommandName.SALIENCY, self._open_saliency_settings
            ),
            CommandName.APPLY_MONTAGE.value: self._route(
                CommandName.APPLY_MONTAGE, self._open_montage
            ),
        }

    def _route(
        self,
        command: CommandName,
        open_surface: WorkflowSurfaceCallback | None = None,
    ) -> WorkflowSurfaceRoute:
        target = panel_target_for_command(command.value)
        if target is None:
            raise ValueError(f"No product surface registered for {command.value}.")
        panel = WorkflowPanel(target.value)
        return WorkflowSurfaceRoute(
            panel=panel,
            open_surface=(
                None
                if open_surface is None
                else lambda request: self._open_materialized_surface(
                    panel,
                    open_surface,
                    request,
                )
            ),
        )

    def _open_materialized_surface(
        self,
        panel: WorkflowPanel,
        open_surface: WorkflowSurfaceCallback,
        request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        """Avoid touching a placeholder while its real panel is being prepared."""
        navigation_failure = self._pending_navigation_failure
        if (
            navigation_failure is not None
            and navigation_failure.generation == self._navigation_generation
            and navigation_failure.panel is panel
            and navigation_failure.active is self._active
            and navigation_failure.active.session.request.request_id
            == request.request_id
            and navigation_failure.active.session.request.command_name
            == request.command_name
        ):
            self._pending_navigation_failure = None
            return WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                navigation_failure.failure.message,
            )
        if self._navigation_pending_panel is panel:
            active = self._active
            if (
                active is None
                or active.session.request.request_id != request.request_id
                or active.session.request.command_name != request.command_name
            ):
                return WorkflowSurfaceResult(
                    WorkflowSurfaceStatus.FAILED,
                    "The pending settings surface lost its request correlation.",
                )
            self._pending_surface_open = _PendingWorkflowSurfaceOpen(
                generation=self._navigation_generation,
                panel=panel,
                open_surface=open_surface,
                request=request,
                active=active,
            )
            return WorkflowSurfaceResult(
                WorkflowSurfaceStatus.NAVIGATED,
                (
                    f"{_PANEL_LABEL[panel]} is loading. "
                    "The requested settings will open when it is ready."
                ),
            )
        return open_surface(request)

    def _initial_resolution_status(
        self,
        active: _ActiveWorkflowUiHandoff,
        outcome: WorkflowSurfaceOutcome,
    ) -> WorkflowUiHandoffResolutionStatus:
        """Keep a deferred modal non-terminal without changing panel-only routes."""
        pending = self._pending_surface_open
        if (
            outcome.status is WorkflowSurfaceStatus.NAVIGATED
            and pending is not None
            and pending.active is active
            and pending.request.request_id == active.session.request.request_id
            and pending.request.command_name == active.session.request.command_name
        ):
            return WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
        return _RESOLUTION_STATUS[outcome.status]

    def _navigate(self, panel: WorkflowPanel) -> None:
        generation = self._invalidate_pending_navigation()
        switch_page = self._main_window.switch_page
        callback_delivered = False

        def _on_ready(_materialized_panel: object) -> None:
            nonlocal callback_delivered
            if callback_delivered:
                return
            callback_delivered = True
            self._complete_pending_navigation(panel, generation)

        def _on_failed(failure: PanelPreparationFailure) -> None:
            nonlocal callback_delivered
            if callback_delivered:
                return
            callback_delivered = True
            self._fail_pending_navigation(panel, generation, failure)

        if self._accepts_ready_callback(switch_page):
            self._navigation_pending_panel = panel
            callback_kwargs: dict[str, object] = {"on_ready": _on_ready}
            if self._accepts_callback(switch_page, "on_failed"):
                callback_kwargs["on_failed"] = _on_failed
            try:
                materialized = switch_page(
                    _PANEL_INDEX[panel],
                    **callback_kwargs,
                )
            except Exception:
                if generation == self._navigation_generation:
                    self._invalidate_pending_navigation()
                raise
            if materialized is not False and not callback_delivered:
                _on_ready(None)
        else:
            materialized = switch_page(_PANEL_INDEX[panel])
            if materialized is False:
                self._navigation_pending_panel = panel
        if callback_delivered:
            return
        status_bar = self._main_window.statusBar()
        if status_bar is not None:
            status_bar.showMessage(
                f"Opening {_PANEL_LABEL[panel]}..."
                if self._navigation_pending_panel is panel
                else f"{_PANEL_LABEL[panel]} is open."
            )

    @staticmethod
    def _accepts_ready_callback(switch_page: Callable[..., object]) -> bool:
        """Identify the public callback contract without breaking legacy doubles."""
        return WorkflowUiHandoffHost._accepts_callback(switch_page, "on_ready")

    @staticmethod
    def _accepts_callback(
        switch_page: Callable[..., object],
        callback_name: str,
    ) -> bool:
        """Identify one named callback without breaking legacy test doubles."""
        try:
            parameters = signature(switch_page).parameters
        except (TypeError, ValueError):
            return False
        callback = parameters.get(callback_name)
        return callback is not None and callback.kind in {
            Parameter.KEYWORD_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        }

    def _invalidate_pending_navigation(self) -> int:
        """Invalidate stale first-open callbacks and return the new generation."""
        self._navigation_generation += 1
        self._navigation_pending_panel = None
        self._pending_surface_open = None
        self._pending_navigation_failure = None
        return self._navigation_generation

    def _fail_pending_navigation(
        self,
        panel: WorkflowPanel,
        generation: int,
        failure: PanelPreparationFailure,
    ) -> None:
        """Settle one correlated modal handoff after lazy preparation fails."""
        if (
            generation != self._navigation_generation
            or self._navigation_pending_panel is not panel
        ):
            return
        if not isinstance(failure, PanelPreparationFailure):
            logger.error(
                "Malformed panel preparation failure for %s: %r",
                _PANEL_LABEL[panel],
                failure,
            )
            failure = PanelPreparationFailure(
                panel_index=_PANEL_INDEX[panel],
                panel_name=_PANEL_LABEL[panel],
                message=f"Could not open {_PANEL_LABEL[panel]}.",
            )

        pending = self._pending_surface_open
        self._navigation_pending_panel = None
        self._pending_surface_open = None

        status_bar = self._main_window.statusBar()
        if status_bar is not None:
            status_bar.showMessage(failure.message, 6000)

        active = self._active
        if pending is None:
            route = (
                self._router.route_for(active.session.request.command_name)
                if active is not None
                else None
            )
            if (
                active is not None
                and route is not None
                and route.panel is panel
                and route.open_surface is not None
            ):
                self._pending_navigation_failure = _PendingPanelNavigationFailure(
                    generation=generation,
                    panel=panel,
                    failure=failure,
                    active=active,
                )
            return
        if (
            pending.generation != generation
            or pending.panel is not panel
            or active is not pending.active
        ):
            return
        if active is None or active.completion.is_terminal:
            return
        self._resolve_deferred_surface(
            active,
            WorkflowSurfaceResult(WorkflowSurfaceStatus.FAILED, failure.message),
        )

    def _complete_pending_navigation(
        self,
        panel: WorkflowPanel,
        generation: int,
    ) -> None:
        """Open a deferred concrete surface after its panel exists."""
        if (
            generation != self._navigation_generation
            or self._navigation_pending_panel is not panel
        ):
            return
        pending = self._pending_surface_open
        self._navigation_pending_panel = None
        self._pending_surface_open = None

        status_bar = self._main_window.statusBar()
        if status_bar is not None:
            status_bar.showMessage(f"{_PANEL_LABEL[panel]} is open.")
        if (
            pending is None
            or pending.generation != generation
            or pending.panel is not panel
        ):
            return
        active = pending.active
        if self._active is not active or active.completion.is_terminal:
            return
        try:
            with bind_interaction_completion(active.completion):
                result = pending.open_surface(pending.request)
        except Exception:
            logger.exception(
                "Deferred workflow surface failed for %s",
                pending.request.command_name,
            )
            result = WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                f"Could not open {_PANEL_LABEL[panel]} settings.",
            )
        if not isinstance(result, WorkflowSurfaceResult):
            logger.error(
                "Deferred workflow surface for %s returned %s",
                pending.request.command_name,
                type(result).__name__,
            )
            result = WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                f"Could not open {_PANEL_LABEL[panel]} settings.",
            )
        if result.message and status_bar is not None:
            status_bar.showMessage(result.message, 6000)
        self._resolve_deferred_surface(active, result)

    def _resolve_deferred_surface(
        self,
        active: _ActiveWorkflowUiHandoff,
        result: WorkflowSurfaceResult,
    ) -> None:
        """Settle a lazy modal once while preserving its original request."""
        if self._active is not active or active.completion.is_terminal:
            return
        if result.status is WorkflowSurfaceStatus.ACCEPTED:
            if active.completion.has_scheduled_command:
                return
            result = WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                "The settings dialog closed without scheduling the requested command.",
            )
        elif result.status is WorkflowSurfaceStatus.NAVIGATED:
            result = WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                "The deferred settings surface did not return a terminal outcome.",
            )

        resolution = WorkflowUiHandoffResolution.for_request(
            active.session.request,
            status=_RESOLUTION_STATUS[result.status],
            message=result.message,
        )
        self._finish_active(active, resolution)

    def _show_decision_status(
        self,
        request: WorkflowUiHandoffRequest,
        outcome: WorkflowSurfaceOutcome,
    ) -> None:
        """Name requested fields without creating a second settings surface."""
        if (
            outcome.status
            not in {
                WorkflowSurfaceStatus.ACCEPTED,
                WorkflowSurfaceStatus.NAVIGATED,
            }
            or not request.decision_fields
        ):
            return
        route = self._router.route_for(request.command_name)
        if route is None:
            return
        if self._navigation_pending_panel is route.panel:
            return
        status_bar = self._main_window.statusBar()
        if status_bar is None:
            return
        fields = ", ".join(decision_field_labels(request.decision_fields))
        status_bar.showMessage(
            f"{_PANEL_LABEL[route.panel]} is open. Review: {fields}."
        )

    def _open_data_import(
        self,
        _request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        return self._surface_result(
            self._main_window.dataset_panel.action_handler.import_data()
        )

    def _open_current_import_review(
        self,
        request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        step_by_field = {
            "eeg_source": "Choose EEG Data",
            "label_source": "Load Labels",
            "metadata_review": "Review Metadata",
            "label_matching": "Match Labels",
            "import_review": "Review and Import",
        }
        initial_step = next(
            (
                step_by_field[field]
                for field in request.decision_fields
                if field in step_by_field
            ),
            "Review and Import",
        )
        active = self._active
        identity = (
            active.session.request.interpretation_identity
            if active is not None
            else None
        )
        if not isinstance(identity, InterpretationReviewIdentity):
            return WorkflowSurfaceResult(
                WorkflowSurfaceStatus.BLOCKED,
                "The Data Import review identity is unavailable. Open the current "
                "review and try again.",
            )
        action_handler = self._main_window.dataset_panel.action_handler
        return self._surface_result(
            action_handler.review_current_import(
                initial_step=initial_step,
                expected_identity=identity,
            )
        )

    def _open_epoching(self, request: WorkflowSurfaceRequest) -> WorkflowSurfaceResult:
        suggestions = request.suggestions
        kwargs = {"suggested_values": suggestions} if suggestions else {}
        return self._surface_result(
            self._main_window.preprocess_panel.sidebar.open_epoching(**kwargs)
        )

    def _open_data_splitting(
        self,
        request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        suggestions = request.suggestions
        kwargs = {"suggested_values": suggestions} if suggestions else {}
        return self._surface_result(
            self._main_window.training_panel.sidebar.split_data(**kwargs)
        )

    def _open_training_settings(
        self,
        request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        sidebar = self._main_window.training_panel.sidebar
        suggestions = request.suggestions
        decision_fields = set(request.decision_fields)
        needs_model = "model" in decision_fields or "model" in suggestions
        option_suggestions = {
            key: value for key, value in suggestions.items() if key != "model"
        }
        needs_options = bool(
            "training_options" in decision_fields or option_suggestions
        )
        if not needs_model and not needs_options:
            needs_options = True

        if needs_model and needs_options:
            return self._surface_result(
                sidebar.configure_training(
                    suggested_model=suggestions.get("model"),
                    suggested_values=option_suggestions,
                )
            )

        if needs_model:
            return self._surface_result(
                sidebar.select_model(suggested_model=suggestions.get("model"))
            )

        if needs_options:
            return self._surface_result(
                sidebar.training_setting(suggested_values=option_suggestions)
            )
        return WorkflowSurfaceResult(WorkflowSurfaceStatus.FAILED)

    def _open_saliency_settings(
        self,
        _request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        return self._surface_result(
            self._main_window.visualization_panel.sidebar.set_saliency()
        )

    def _open_montage(
        self,
        request: WorkflowSurfaceRequest,
    ) -> WorkflowSurfaceResult:
        """Open the existing montage dialog with correlated assistant suggestions."""
        suggestions = request.suggestions
        return self._surface_result(
            self._main_window.visualization_panel.sidebar.set_montage(
                default_montage=suggestions.get("montage_name"),
                warning=suggestions.get("warning", ""),
            )
        )

    @staticmethod
    def _surface_result(outcome: object) -> WorkflowSurfaceResult:
        if not isinstance(outcome, InteractionOutcome):
            return WorkflowSurfaceResult(
                WorkflowSurfaceStatus.FAILED,
                "The settings surface did not return a valid outcome.",
            )
        status = {
            InteractionStatus.COMPLETED: WorkflowSurfaceStatus.COMPLETED,
            InteractionStatus.ACCEPTED: WorkflowSurfaceStatus.ACCEPTED,
            InteractionStatus.CANCELLED: WorkflowSurfaceStatus.CANCELLED,
            InteractionStatus.BLOCKED: WorkflowSurfaceStatus.BLOCKED,
            InteractionStatus.FAILED: WorkflowSurfaceStatus.FAILED,
        }[outcome.status]
        return WorkflowSurfaceResult(status, outcome.message)
