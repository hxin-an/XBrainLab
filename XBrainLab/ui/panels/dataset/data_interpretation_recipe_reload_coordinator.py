"""Focused UI workflow owner for reloading Data Interpretation recipes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from XBrainLab.backend.application.commands import (
    CommandName,
    PreviewInterpretationCommand,
    ReloadInterpretationRecipeCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
)
from XBrainLab.ui.components.user_error_presentation import UnexpectedErrorContext
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.panels.dataset.data_interpretation_ui_payload import (
    decision_reason,
    diagnostic_payload,
    merge_interpretation_choices,
    optional_payload_id,
)

_DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE = (
    "Data interpretation availability is unavailable right now."
)


class DataInterpretationRecipeReloadBindings(Protocol):
    """Application and Qt ports shared with the parent interpretation flow."""

    @property
    def message_box(self) -> Callable[[], Any]: ...

    @property
    def file_dialog(self) -> Callable[[], Any]: ...

    @property
    def blocked_reason(self) -> Callable[..., str]: ...

    @property
    def get_command_review_context(self) -> Callable[..., Any]: ...

    @property
    def has_real_application_context(self) -> Callable[..., bool]: ...

    @property
    def is_stale_publication_result(self) -> Callable[[Any], bool]: ...


class DataInterpretationRecipeReloadHost(Protocol):
    """Narrow continuation ports supplied by the parent import workflow."""

    panel: Any

    def _can_start_interpretation(
        self,
        command_name: CommandName,
        *,
        blocked_title: str,
        fallback_reason: str,
    ) -> bool: ...

    def _execute_interpretation_command_async(
        self,
        command: Any,
        *,
        on_result: Callable[[Any], InteractionOutcome | None],
        error_title: str,
        expected_publication_generation: int | None = None,
        blocked_title: str = "Interpretation Blocked",
        unexpected_error_context: UnexpectedErrorContext = (
            UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
        ),
    ) -> InteractionOutcome | None: ...

    def _preview_resource_preflight_outcome(
        self,
        result: Any,
        *,
        retry: Callable[[str], Any],
    ) -> InteractionOutcome | None: ...

    def _review_state_from_parts(
        self,
        *,
        scan: dict[str, Any],
        preview: dict[str, Any],
        candidate: dict[str, Any],
        decision: dict[str, Any],
    ) -> Any: ...

    def _apply_interpretation_async(
        self,
        review_state: Any,
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome: ...


class DataInterpretationRecipeReloadCoordinator:
    """Own recipe selection, review, re-preview, validation, and continuation."""

    def __init__(
        self,
        host: DataInterpretationRecipeReloadHost,
        *,
        preview_dialog_class: Callable[[], type[Any]],
        bindings: DataInterpretationRecipeReloadBindings,
    ) -> None:
        self._host = host
        self.panel = host.panel
        self._preview_dialog_class = preview_dialog_class
        self._bindings = bindings

    def reload_interpretation_recipe(self) -> None:
        """Reload a saved import recipe, preview it, and apply after review."""
        if not self._host._can_start_interpretation(
            CommandName.RELOAD_INTERPRETATION_RECIPE,
            blocked_title="Recipe Reload Blocked",
            fallback_reason="Recipe reload is not available right now.",
        ):
            return
        review_context = self._bindings.get_command_review_context(
            self.panel,
            CommandName.RELOAD_INTERPRETATION_RECIPE,
        )
        if review_context is None and self._bindings.has_real_application_context(
            self.panel
        ):
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Reload Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return
        reload_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else None
        )
        if review_context is not None and reload_capability is None:
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Reload Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return
        if reload_capability is not None and not reload_capability.enabled:
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Reload Blocked",
                self._bindings.blocked_reason(
                    reload_capability,
                    "Recipe reload is not available right now.",
                ),
            )
            return
        recipe_path, _ = self._bindings.file_dialog().getOpenFileName(
            self.panel,
            "Choose Import Recipe",
            "",
            "Import Recipe (*.json);;JSON (*.json)",
        )
        if not recipe_path:
            return

        def _handle_reload_result(result: Any) -> InteractionOutcome | None:
            resource_outcome = self._host._preview_resource_preflight_outcome(
                result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            self._continue_reloaded_interpretation_recipe(result)
            return None

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            return self._host._execute_interpretation_command_async(
                ReloadInterpretationRecipeCommand(
                    recipe_path=recipe_path,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_reload_result,
                error_title="Recipe reload failed",
                expected_publication_generation=(
                    review_context.publication_generation
                    if review_context is not None
                    else None
                ),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_IMPORT_RECIPE_RELOAD
                ),
            )

        started = _dispatch()
        if not started:
            self._bindings.message_box().critical(
                self.panel,
                "Recipe reload unavailable",
                "Data Interpretation command service is unavailable.",
            )

    def _continue_reloaded_interpretation_recipe(self, reload_result: Any) -> None:
        """Open the recipe review after its backend state is ready."""
        if self._result_failed(reload_result, "Recipe reload failed"):
            return

        scan = diagnostic_payload(reload_result, "scan_result")
        preview = diagnostic_payload(reload_result, "preview")
        candidate = diagnostic_payload(reload_result, "candidate")
        decision = diagnostic_payload(reload_result, "validation_decision")
        raw_base_choices = candidate.get("choices")
        base_choices: dict[str, Any] = (
            {str(key): value for key, value in raw_base_choices.items()}
            if isinstance(raw_base_choices, dict)
            else {}
        )
        try:
            review_state = self._host._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision=decision,
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            self._bindings.message_box().warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        dialog = self._preview_dialog_class()(
            self.panel,
            scan_result=scan,
            preview=preview,
            validation_decision=decision,
            choices=base_choices,
        )
        if not dialog.exec():
            return

        raw_dialog_result = dialog.get_result()
        dialog_result = (
            dict(raw_dialog_result) if isinstance(raw_dialog_result, dict) else {}
        )
        raw_dialog_choices = dialog_result.get("choices")
        dialog_choices: dict[str, Any] = (
            {str(key): value for key, value in raw_dialog_choices.items()}
            if isinstance(raw_dialog_choices, dict)
            else {}
        )
        dialog_choices = merge_interpretation_choices(
            base_choices,
            dialog_choices,
        )
        if (
            str(decision.get("decision")) == "blocked"
            and dialog_choices == base_choices
        ):
            self._bindings.message_box().critical(
                self.panel,
                "Interpretation blocked",
                decision_reason(decision),
            )
            return
        if dialog_choices != base_choices:

            def _handle_preview_result(result: Any) -> InteractionOutcome | None:
                resource_outcome = self._host._preview_resource_preflight_outcome(
                    result,
                    retry=lambda token: _dispatch_preview(
                        resource_preflight_confirmed=True,
                        resource_preflight_token=token,
                    ),
                )
                if resource_outcome is not None:
                    return resource_outcome
                self._continue_reloaded_recipe_preview(
                    result,
                    scan=scan,
                    dialog_result=dialog_result,
                )
                return None

            def _dispatch_preview(
                *,
                resource_preflight_confirmed: bool = False,
                resource_preflight_token: str | None = None,
            ) -> InteractionOutcome | None:
                return self._host._execute_interpretation_command_async(
                    PreviewInterpretationCommand(
                        scan_id=optional_payload_id(scan, "scan_id"),
                        choices=dialog_choices,
                        resource_preflight_confirmed=resource_preflight_confirmed,
                        resource_preflight_token=resource_preflight_token,
                    ),
                    on_result=_handle_preview_result,
                    error_title="Interpretation preview failed",
                    expected_publication_generation=(
                        review_state.publication_generation
                    ),
                    unexpected_error_context=(
                        UnexpectedErrorContext.DATA_INTERPRETATION_PREVIEW
                    ),
                )

            started = _dispatch_preview()
            if not started:
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation preview unavailable",
                    "Data Interpretation command service is unavailable.",
                )
            return

        self._host._apply_interpretation_async(review_state, dialog_result)

    def _continue_reloaded_recipe_preview(
        self,
        preview_result: Any,
        *,
        scan: dict[str, Any],
        dialog_result: dict[str, Any],
    ) -> None:
        """Validate a re-previewed recipe candidate without blocking the GUI."""
        if self._result_failed(preview_result, "Interpretation preview failed"):
            return
        preview = diagnostic_payload(preview_result, "preview")
        candidate = diagnostic_payload(preview_result, "candidate")
        candidate_id = optional_payload_id(candidate, "candidate_id")
        try:
            preview_state = self._host._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision={},
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            self._bindings.message_box().warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        started = self._host._execute_interpretation_command_async(
            ValidateInterpretationCommand(candidate_id=candidate_id),
            on_result=lambda result: self._continue_reloaded_recipe_validation(
                result,
                scan=scan,
                preview=preview,
                candidate=candidate,
                dialog_result=dialog_result,
            ),
            error_title="Interpretation validation failed",
            expected_publication_generation=preview_state.publication_generation,
            unexpected_error_context=(
                UnexpectedErrorContext.DATA_INTERPRETATION_VALIDATION
            ),
        )
        if not started:
            self._bindings.message_box().critical(
                self.panel,
                "Interpretation validation unavailable",
                "Data Interpretation command service is unavailable.",
            )

    def _continue_reloaded_recipe_validation(
        self,
        validation_result: Any,
        *,
        scan: dict[str, Any],
        preview: dict[str, Any],
        candidate: dict[str, Any],
        dialog_result: dict[str, Any],
    ) -> None:
        """Apply a validated reloaded recipe through the shared async path."""
        if self._result_failed(
            validation_result,
            "Interpretation validation failed",
        ):
            return
        decision = diagnostic_payload(validation_result, "validation_decision")
        if str(decision.get("decision")) == "blocked":
            self._bindings.message_box().critical(
                self.panel,
                "Interpretation blocked",
                decision_reason(decision),
            )
            return
        try:
            review_state = self._host._review_state_from_parts(
                scan=scan,
                preview=preview,
                candidate=candidate,
                decision=decision,
            )
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            self._bindings.message_box().warning(
                self.panel,
                "Import review changed",
                str(exc),
            )
            return
        self._host._apply_interpretation_async(review_state, dialog_result)

    def _result_failed(self, result: Any, title: str) -> bool:
        if not result.failed:
            return False
        if self._bindings.is_stale_publication_result(result):
            self._bindings.message_box().warning(
                self.panel,
                "Review Data Import Again",
                result.message,
            )
        else:
            self._bindings.message_box().critical(self.panel, title, result.message)
        return True
