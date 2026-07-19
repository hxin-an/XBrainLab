"""Route assistant decisions to explicitly registered product UI surfaces."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from XBrainLab.backend.utils.logger import logger


class WorkflowPanel(str, Enum):
    """Stable panel targets understood by the host UI adapter."""

    DATASET = "dataset"
    PREPROCESS = "preprocess"
    TRAINING = "training"
    EVALUATION = "evaluation"
    VISUALIZATION = "visualization"


class WorkflowSurfaceStatus(str, Enum):
    """Observable outcome after routing to an existing product surface."""

    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CLOSED_WITHOUT_CHANGE = "closed_without_change"
    NAVIGATED = "navigated"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


_DEFAULT_MESSAGES: dict[WorkflowSurfaceStatus, str] = {
    WorkflowSurfaceStatus.ACCEPTED: (
        "The settings dialog was accepted, but workflow completion has not "
        "been verified."
    ),
    WorkflowSurfaceStatus.COMPLETED: (
        "The settings dialog completed the requested workflow change."
    ),
    WorkflowSurfaceStatus.CANCELLED: "The settings dialog was cancelled.",
    WorkflowSurfaceStatus.CLOSED_WITHOUT_CHANGE: (
        "The settings dialog closed without applying a workflow change."
    ),
    WorkflowSurfaceStatus.NAVIGATED: "The relevant XBrainLab panel is open.",
    WorkflowSurfaceStatus.BLOCKED: (
        "The existing settings surface is currently blocked by workflow state."
    ),
    WorkflowSurfaceStatus.UNAVAILABLE: (
        "No existing XBrainLab settings surface is available for this step."
    ),
    WorkflowSurfaceStatus.FAILED: (
        "XBrainLab could not open the requested workflow surface."
    ),
}


@dataclass(frozen=True)
class WorkflowSurfaceResult:
    """Result returned by one host-owned panel or dialog adapter.

    ``ACCEPTED`` records a dialog-level acceptance only. The adapter must return
    ``COMPLETED`` only after the requested workflow mutation has actually
    completed and its product result is known.
    """

    status: WorkflowSurfaceStatus
    message: str = ""


@dataclass(frozen=True)
class WorkflowSurfaceRequest:
    """Normalized decision context passed to one existing product surface."""

    command_name: str
    decision_fields: tuple[str, ...] = ()
    suggested_values: tuple[tuple[str, str], ...] = ()
    request_id: str = ""

    @property
    def suggestions(self) -> dict[str, str]:
        return dict(self.suggested_values)


WorkflowSurfaceCallback = Callable[[WorkflowSurfaceRequest], WorkflowSurfaceResult]
WorkflowPanelNavigator = Callable[[WorkflowPanel], None]


@dataclass(frozen=True)
class WorkflowSurfaceRoute:
    """Typed route injected by the host instead of reflected attribute names."""

    panel: WorkflowPanel
    open_surface: WorkflowSurfaceCallback | None = None


@dataclass(frozen=True)
class WorkflowSurfaceOutcome:
    """Typed handoff outcome consumed by the assistant host."""

    status: WorkflowSurfaceStatus
    command_name: str
    message: str
    request_id: str = ""

    @property
    def routed(self) -> bool:
        """Whether navigation reached a real product surface."""
        return self.status not in {
            WorkflowSurfaceStatus.UNAVAILABLE,
            WorkflowSurfaceStatus.FAILED,
        }

    @property
    def is_verified_completion(self) -> bool:
        """Whether the product surface verified the requested state change."""
        return self.status is WorkflowSurfaceStatus.COMPLETED


class WorkflowSurfaceRouter:
    """Navigate and invoke host-injected workflow surface adapters.

    The router never inspects ``MainWindow`` attributes and never infers dialog
    completion from a global state generation. Each route callback owns the
    concrete UI integration and must return an explicit
    :class:`WorkflowSurfaceResult`.
    """

    def __init__(
        self,
        navigate: WorkflowPanelNavigator,
        routes: Mapping[str, WorkflowSurfaceRoute],
    ) -> None:
        self._navigate = navigate
        self._routes = self._normalize_routes(routes)

    def open(
        self,
        command_name: str,
        *,
        request_id: str = "",
        decision_fields: Iterable[str] = (),
        suggested_values: Mapping[str, object] | None = None,
    ) -> WorkflowSurfaceOutcome:
        """Open the registered panel or dialog for ``command_name``."""
        normalized = self._normalize_command_name(command_name)
        route = self._routes.get(normalized)
        if route is None:
            return self._outcome(
                WorkflowSurfaceStatus.UNAVAILABLE,
                normalized,
                request_id=request_id,
            )

        try:
            self._navigate(route.panel)
        except Exception:
            logger.exception("Assistant could not navigate to %s", normalized)
            return self._outcome(
                WorkflowSurfaceStatus.FAILED,
                normalized,
                request_id=request_id,
            )

        if route.open_surface is None:
            return self._outcome(
                WorkflowSurfaceStatus.NAVIGATED,
                normalized,
                request_id=request_id,
            )

        suggestions = {
            str(key): " ".join(str(value).split())
            for key, value in (suggested_values or {}).items()
            if str(key).strip() and str(value).strip()
        }
        fields = tuple(
            dict.fromkeys(
                field
                for value in decision_fields
                if (field := str(value or "").strip())
            )
        )
        request = WorkflowSurfaceRequest(
            command_name=normalized,
            decision_fields=fields,
            suggested_values=tuple(suggestions.items()),
            request_id=str(request_id or "").strip(),
        )
        try:
            result = route.open_surface(request)
        except Exception:
            logger.exception("Existing UI surface failed for %s", normalized)
            return self._outcome(
                WorkflowSurfaceStatus.FAILED,
                normalized,
                "The XBrainLab settings dialog closed because of an error.",
                request_id=request_id,
            )

        if not isinstance(result, WorkflowSurfaceResult):
            logger.error(
                "Workflow surface adapter for %s returned %s instead of "
                "WorkflowSurfaceResult",
                normalized,
                type(result).__name__,
            )
            return self._outcome(
                WorkflowSurfaceStatus.FAILED,
                normalized,
                "The settings surface did not return a valid outcome.",
                request_id=request_id,
            )

        return self._outcome(
            result.status,
            normalized,
            result.message,
            request_id=request_id,
        )

    def route_for(self, command_name: str) -> WorkflowSurfaceRoute | None:
        """Return the registered typed route for host presentation context."""
        return self._routes.get(self._normalize_command_name(command_name))

    @classmethod
    def _normalize_routes(
        cls,
        routes: Mapping[str, WorkflowSurfaceRoute],
    ) -> dict[str, WorkflowSurfaceRoute]:
        normalized_routes: dict[str, WorkflowSurfaceRoute] = {}
        for command_name, route in routes.items():
            normalized = cls._normalize_command_name(command_name)
            if not normalized:
                raise ValueError("Workflow route command names cannot be empty.")
            if normalized in normalized_routes:
                raise ValueError(f"Duplicate workflow route: {normalized}")
            normalized_routes[normalized] = route
        return normalized_routes

    @staticmethod
    def _normalize_command_name(command_name: str) -> str:
        return str(command_name or "").strip().lower()

    @staticmethod
    def _outcome(
        status: WorkflowSurfaceStatus,
        command_name: str,
        message: str = "",
        *,
        request_id: str = "",
    ) -> WorkflowSurfaceOutcome:
        return WorkflowSurfaceOutcome(
            status=status,
            command_name=command_name,
            message=message.strip() or _DEFAULT_MESSAGES[status],
            request_id=str(request_id or "").strip(),
        )
