"""Focused UI workflow owner for Data Interpretation imports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    CommandName,
    LoadDataCommand,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.errors import ApplicationError, PreconditionError
from XBrainLab.backend.application.resource_preflight import (
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    CommandReviewContext,
    ControllerCompatibilityUnavailableError,
    application_ui_runtime,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
    get_application_view_publication,
    get_command_capability,
    get_command_review_context,
    has_real_application_context,
    is_stale_publication_result,
)
from XBrainLab.ui.async_command_runner import qt_object_deleted
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import (
    InteractionOutcome,
    reserve_interaction_continuation,
)
from XBrainLab.ui.panels.dataset.data_interpretation_recipe_reload_coordinator import (
    DataInterpretationRecipeReloadCoordinator,
)
from XBrainLab.ui.panels.dataset.data_interpretation_ui_payload import (
    decision_reason,
    diagnostic_payload,
    merge_interpretation_choices,
    optional_payload_id,
)

_DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE = (
    "Data interpretation availability is unavailable right now."
)


@dataclass(frozen=True)
class _InterpretationReviewState:
    scan: dict[str, Any]
    preview: dict[str, Any]
    candidate: dict[str, Any]
    candidate_id: str | None
    decision: dict[str, Any]
    publication_generation: int | None = None


@dataclass(frozen=True)
class _PublishedInterpretationReview:
    payload: dict[str, Any]
    identity: InterpretationReviewIdentity


@dataclass(frozen=True, slots=True)
class DataInterpretationActionBindings:
    """Replaceable UI/application ports resolved by the composition root."""

    message_box: Callable[[], Any]
    file_dialog: Callable[[], Any]
    single_shot: Callable[..., Any]
    application_ui_runtime: Callable[..., Any]
    blocked_reason: Callable[..., str]
    execute_application_command: Callable[..., Any]
    execute_application_command_async: Callable[..., Any]
    get_application_view_publication: Callable[..., Any]
    get_command_capability: Callable[..., Any]
    get_command_review_context: Callable[..., Any]
    has_real_application_context: Callable[..., bool]
    is_stale_publication_result: Callable[[Any], bool]
    present_unexpected_error: Callable[..., Any]
    qt_object_deleted: Callable[[Any], bool]
    reserve_interaction_continuation: Callable[[], Any]


def default_data_interpretation_action_bindings() -> DataInterpretationActionBindings:
    """Build production bindings for direct coordinator use."""
    return DataInterpretationActionBindings(
        message_box=lambda: QMessageBox,
        file_dialog=lambda: QFileDialog,
        single_shot=QTimer.singleShot,
        application_ui_runtime=application_ui_runtime,
        blocked_reason=blocked_reason,
        execute_application_command=execute_application_command,
        execute_application_command_async=execute_application_command_async,
        get_application_view_publication=get_application_view_publication,
        get_command_capability=get_command_capability,
        get_command_review_context=get_command_review_context,
        has_real_application_context=has_real_application_context,
        is_stale_publication_result=is_stale_publication_result,
        present_unexpected_error=present_unexpected_error,
        qt_object_deleted=qt_object_deleted,
        reserve_interaction_continuation=reserve_interaction_continuation,
    )


class DataInterpretationActionHost(Protocol):
    """Narrow adapter contract retained by DatasetActionHandler."""

    panel: Any

    @property
    def controller(self) -> Any: ...

    def _show_status(self, message: str) -> None: ...

    def _compatibility_controller_value(
        self,
        blocked_title: str,
        fallback: Callable[[], Any],
        *,
        warn_when_unavailable: bool = True,
    ) -> tuple[bool, Any]: ...


class DataInterpretationActionCoordinator:
    """Own scan, review, preview, validate, apply, and recipe UI flow."""

    def __init__(
        self,
        host: DataInterpretationActionHost,
        *,
        preview_dialog_class: Callable[[], type[Any]],
        bindings: DataInterpretationActionBindings | None = None,
    ) -> None:
        self._host = host
        self.panel = host.panel
        self._preview_dialog_class = preview_dialog_class
        self._bindings = bindings or default_data_interpretation_action_bindings()
        self._recipe_reload = DataInterpretationRecipeReloadCoordinator(
            self,
            preview_dialog_class=self._preview_dialog_class,
            bindings=self._bindings,
        )

    @property
    def controller(self) -> Any:
        return self._host.controller

    def _show_status(self, message: str) -> None:
        self._host._show_status(message)

    def _compatibility_controller_value(
        self,
        blocked_title: str,
        fallback: Callable[[], Any],
        *,
        warn_when_unavailable: bool = True,
    ) -> tuple[bool, Any]:
        return self._host._compatibility_controller_value(
            blocked_title,
            fallback,
            warn_when_unavailable=warn_when_unavailable,
        )

    def _compatibility_locked_preflight_blocked(
        self,
        controller: Any,
        *,
        blocked_title: str,
        locked_message: str,
    ) -> bool:
        available, is_locked = self._compatibility_controller_value(
            blocked_title,
            lambda: bool(controller.is_locked()),
        )
        if not available:
            return True
        if is_locked:
            self._bindings.message_box().warning(
                self.panel, blocked_title, locked_message
            )
            return True
        return False

    def import_data(self) -> InteractionOutcome:
        """Scan, preview, validate, and apply an EEG data interpretation."""
        scan_capability = self._bindings.get_command_capability(
            self.panel, CommandName.SCAN_SOURCE
        )
        if scan_capability is not None and not scan_capability.enabled:
            message = self._bindings.blocked_reason(
                scan_capability,
                "Data interpretation is not available right now.",
            )
            self._bindings.message_box().warning(
                self.panel,
                "Interpretation Blocked",
                message,
            )
            return InteractionOutcome.blocked(message)
        if scan_capability is None and self._bindings.has_real_application_context(
            self.panel
        ):
            self._bindings.message_box().warning(
                self.panel,
                "Interpretation Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            return InteractionOutcome.blocked(
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE
            )

        controller = self.controller
        if scan_capability is None:
            if controller is None:
                message = "Dataset controller unavailable."
                self._bindings.message_box().critical(
                    self.panel,
                    "Import failed",
                    message,
                )
                return InteractionOutcome.failed(message)
            if self._compatibility_locked_preflight_blocked(
                controller,
                blocked_title="Interpretation Blocked",
                locked_message=(
                    "Dataset is locked. Please clear or reset before importing."
                ),
            ):
                return InteractionOutcome.blocked(
                    "Dataset is locked or its import state could not be verified."
                )

        filter_str = (
            "All files (*);;"
            "EEG files (*.set *.SET *.gdf *.GDF *.fif *.FIF *.edf *.EDF "
            "*.bdf *.BDF *.cnt *.CNT *.vhdr *.VHDR);;"
            "EEGLAB (*.set *.SET);;GDF (*.gdf *.GDF);;"
            "FIF (*.fif *.FIF);;EDF/BDF (*.edf *.EDF *.bdf *.BDF);;"
            "Neuroscan CNT (*.cnt *.CNT);;BrainVision (*.vhdr *.VHDR)"
        )
        filepaths, _ = self._bindings.file_dialog().getOpenFileNames(
            self.panel,
            "Choose EEG Source for Interpretation",
            "",
            filter_str,
            options=self._bindings.file_dialog().Option.DontUseNativeDialog,
        )
        if not filepaths:
            return InteractionOutcome.cancelled("No EEG source was selected.")

        try:
            outcome = self._run_data_interpretation_import(
                list(filepaths),
                source_hint="file",
            )
            if outcome is not None:
                return outcome
            if scan_capability is not None:
                message = "Data Interpretation command service is unavailable."
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation unavailable",
                    message,
                )
                return InteractionOutcome.failed(message)
            if self._bindings.has_real_application_context(self.panel):
                self._bindings.message_box().warning(
                    self.panel,
                    "Interpretation Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            result = self._bindings.execute_application_command(
                self.panel,
                LoadDataCommand(
                    paths=list(filepaths),
                ),
            )
            if result is not None and result.failed:
                self._bindings.message_box().critical(
                    self.panel,
                    "Import failed",
                    result.message,
                )
                return self._interaction_failure_outcome(result, result.message)
            if result is None:
                self._bindings.message_box().warning(
                    self.panel,
                    "Interpretation Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return InteractionOutcome.blocked(
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
            self._show_status(result.message)
            return InteractionOutcome.completed(result.message)
        except Exception:
            message = self._bindings.present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=self._bindings.message_box(),
            )
            return InteractionOutcome.failed(message)

    def review_current_import(
        self,
        *,
        initial_step: str = "Review and Import",
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> InteractionOutcome:
        """Reopen the exact backend-published review without rescanning files."""
        if expected_identity is not None and not isinstance(
            expected_identity,
            InterpretationReviewIdentity,
        ):
            raise TypeError("Expected interpretation review identity must be typed.")
        try:
            published_review = self._read_interpretation_review(expected_identity)
        except (ApplicationError, ControllerCompatibilityUnavailableError) as exc:
            message = str(exc)
            self._bindings.message_box().warning(
                self.panel,
                "Import review unavailable",
                message,
            )
            return InteractionOutcome.blocked(message)

        try:
            publication = published_review.payload
            scan = dict(publication["scan_result"])
            candidate = dict(publication["candidate"])
            preview = dict(publication["preview"])
            decision = dict(publication["validation_decision"])
            choices = dict(publication.get("choices") or {})
            label_sources = [
                str(item)
                for item in publication.get("label_sources", [])
                if str(item).strip()
            ]
            source_path = str(publication["source_path"])
            source_hint = str(publication.get("source_hint") or "auto")
        except (KeyError, TypeError, ValueError):
            message = self._bindings.present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT_REVIEW,
                message_box=self._bindings.message_box(),
            )
            return InteractionOutcome.failed(message)

        review_state = _InterpretationReviewState(
            scan=scan,
            preview=preview,
            candidate=candidate,
            candidate_id=self._optional_payload_id(candidate, "candidate_id"),
            decision=decision,
            publication_generation=published_review.identity.publication_generation,
        )
        return self._continue_data_interpretation_import(
            source_path=source_path,
            source_hint=source_hint,
            choices=choices,
            label_sources=label_sources,
            review_state=review_state,
            initial_step=initial_step,
        )

    def _read_interpretation_review(
        self,
        expected_identity: InterpretationReviewIdentity | None,
    ) -> _PublishedInterpretationReview:
        runtime = self._bindings.application_ui_runtime(self.panel)
        if runtime is None:
            raise ControllerCompatibilityUnavailableError(
                "The Data Import review runtime is unavailable."
            )

        publication_before = runtime.get_view_publication()
        if expected_identity is None:
            expected_identity = self._identity_from_publication(publication_before)
        self._require_interpretation_identity(
            publication_before,
            expected_identity,
        )
        review = runtime.get_interpretation_review(
            expected_identity=expected_identity,
        )
        self._require_review_payload_identity(review, expected_identity)
        publication_after = runtime.get_view_publication()
        self._require_interpretation_identity(
            publication_after,
            expected_identity,
        )
        return _PublishedInterpretationReview(
            payload=dict(review),
            identity=expected_identity,
        )

    @staticmethod
    def _identity_from_publication(
        publication: object,
    ) -> InterpretationReviewIdentity:
        if isinstance(publication, ApplicationViewPublication) and publication.usable:
            interpretation = publication.state.interpretation
            if (
                isinstance(interpretation.latest_scan_id, str)
                and interpretation.latest_scan_id.strip()
                and isinstance(interpretation.latest_candidate_id, str)
                and interpretation.latest_candidate_id.strip()
            ):
                return InterpretationReviewIdentity(
                    publication_generation=publication.generation,
                    scan_id=interpretation.latest_scan_id,
                    candidate_id=interpretation.latest_candidate_id,
                )
        raise PreconditionError(
            "The Data Import review identity could not be verified. Refresh the "
            "review and try again.",
            diagnostics={"stale_interpretation_review": True},
        )

    @staticmethod
    def _require_interpretation_identity(
        publication: object,
        expected_identity: InterpretationReviewIdentity,
    ) -> None:
        if isinstance(publication, ApplicationViewPublication):
            interpretation = publication.state.interpretation
            matches = (
                publication.usable
                and publication.generation == expected_identity.publication_generation
                and interpretation.latest_scan_id == expected_identity.scan_id
                and interpretation.latest_candidate_id == expected_identity.candidate_id
            )
            if matches:
                return
        raise PreconditionError(
            "The Data Import review changed before it could be opened. Open the "
            "current review and try again.",
            diagnostics={"stale_interpretation_review": True},
        )

    @staticmethod
    def _require_review_payload_identity(
        review: object,
        expected_identity: InterpretationReviewIdentity,
    ) -> None:
        if not isinstance(review, dict):
            raise PreconditionError(
                "The Data Import review identity could not be verified.",
                diagnostics={"stale_interpretation_review": True},
            )
        scan = review.get("scan_result")
        candidate = review.get("candidate")
        scan_id = scan.get("scan_id") if isinstance(scan, dict) else None
        candidate_id = (
            candidate.get("candidate_id") if isinstance(candidate, dict) else None
        )
        if (
            scan_id == expected_identity.scan_id
            and candidate_id == expected_identity.candidate_id
        ):
            return
        raise PreconditionError(
            "The Data Import review identity could not be verified.",
            diagnostics={
                "stale_interpretation_review": True,
                "review_payload_mismatch": True,
            },
        )

    def import_folder_source(self):
        """Interpret a folder or BIDS root through the Data Interpretation flow."""
        if not self._can_start_interpretation():
            return
        source_path = self._bindings.file_dialog().getExistingDirectory(
            self.panel,
            "Choose Folder or BIDS Root for Interpretation",
            "",
            options=(
                self._bindings.file_dialog().Option.ShowDirsOnly
                | self._bindings.file_dialog().Option.DontUseNativeDialog
            ),
        )
        if not source_path:
            return
        try:
            handled = self._run_data_interpretation_import([source_path])
            if not handled:
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation unavailable",
                    "Data Interpretation command service is unavailable.",
                )
        except Exception:
            self._bindings.present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=self._bindings.message_box(),
            )

    def import_bids_source(self):
        """Interpret a BIDS EEG folder through the Data Interpretation flow."""
        if not self._can_start_interpretation():
            return
        source_path = self._bindings.file_dialog().getExistingDirectory(
            self.panel,
            "Choose BIDS Folder for Import",
            "",
            options=(
                self._bindings.file_dialog().Option.ShowDirsOnly
                | self._bindings.file_dialog().Option.DontUseNativeDialog
            ),
        )
        if not source_path:
            return
        try:
            handled = self._run_data_interpretation_import(
                [source_path],
                source_hint="bids",
            )
            if not handled:
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation unavailable",
                    "Data Interpretation command service is unavailable.",
                )
        except Exception:
            self._bindings.present_unexpected_error(
                self.panel,
                UnexpectedErrorContext.DATA_IMPORT,
                message_box=self._bindings.message_box(),
            )

    def reload_interpretation_recipe(self):
        """Delegate recipe reload to its focused workflow owner."""
        return self._recipe_reload.reload_interpretation_recipe()

    def _can_start_interpretation(
        self,
        command_name: CommandName = CommandName.SCAN_SOURCE,
        *,
        blocked_title: str = "Interpretation Blocked",
        fallback_reason: str = "Data interpretation is not available right now.",
    ) -> bool:
        """Return whether the UI can start a Data Interpretation source flow."""
        capability = self._bindings.get_command_capability(self.panel, command_name)
        if capability is not None and not capability.enabled:
            self._bindings.message_box().warning(
                self.panel,
                blocked_title,
                self._bindings.blocked_reason(
                    capability,
                    fallback_reason,
                ),
            )
            return False

        if capability is None:
            controller = self.controller
            if controller is None:
                self._bindings.message_box().critical(
                    self.panel,
                    "Import failed",
                    "Dataset controller unavailable.",
                )
                return False
            return not self._compatibility_locked_preflight_blocked(
                controller,
                blocked_title=blocked_title,
                locked_message=(
                    "Dataset is locked. Please clear or reset before importing."
                ),
            )
        return True

    def _run_data_interpretation_import(
        self,
        filepaths: list[str],
        *,
        source_hint: str = "auto",
    ) -> InteractionOutcome | None:
        """Run the Data Interpretation command sequence for selected files."""
        source_path, choices = self._interpretation_source_and_choices(filepaths)
        return self._start_interpretation_review_async(
            source_path,
            source_hint,
            choices,
            [],
        )

    def _continue_data_interpretation_import(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        review_state: _InterpretationReviewState,
        initial_step: str = "",
    ) -> InteractionOutcome:
        dialog_kwargs: dict[str, Any] = {
            "scan_result": review_state.scan,
            "preview": review_state.preview,
            "validation_decision": review_state.decision,
            "choices": dict(choices),
        }
        if initial_step:
            dialog_kwargs["initial_step"] = initial_step
        dialog_class = self._preview_dialog_class()
        dialog = dialog_class(self.panel, **dialog_kwargs)
        if not dialog.exec():
            return InteractionOutcome.cancelled(
                "Data interpretation review was cancelled."
            )

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
        updated_choices = self._merge_interpretation_choices(
            choices,
            dialog_choices,
        )
        next_label_sources = self._dialog_label_sources(
            dialog_result,
            label_sources,
        )
        if next_label_sources != label_sources:
            updated_choices = self._choices_after_label_source_change(updated_choices)
            return self._start_interpretation_review_async(
                source_path,
                source_hint,
                updated_choices,
                next_label_sources,
                initial_step=str(dialog_result.get("resume_step") or ""),
            ) or InteractionOutcome.blocked(
                "Data interpretation review could not be started."
            )

        if (
            str(review_state.decision.get("decision")) == "blocked"
            and updated_choices == choices
        ):
            return InteractionOutcome.blocked(
                self._decision_reason(review_state.decision)
            )

        if updated_choices != choices:
            resume_step = str(dialog_result.get("resume_step") or "").strip()
            if resume_step == "Match Labels":
                return self._repreview_interpretation_async(
                    source_path=source_path,
                    source_hint=source_hint,
                    choices=updated_choices,
                    label_sources=label_sources,
                    review_state=review_state,
                    initial_step=resume_step,
                ) or InteractionOutcome.blocked(
                    "Data interpretation preview could not be refreshed."
                )
            return self._review_interpretation_for_apply_async(
                choices=updated_choices,
                review_state=review_state,
                dialog_result=dialog_result,
            ) or InteractionOutcome.blocked(
                "Data interpretation review could not be refreshed."
            )
        return self._apply_interpretation_async(review_state, dialog_result)

    def _execute_interpretation_command_async(
        self,
        command,
        *,
        on_result: Callable[[Any], InteractionOutcome | None],
        error_title: str,
        expected_publication_generation: int | None = None,
        blocked_title: str = "Interpretation Blocked",
        unexpected_error_context: UnexpectedErrorContext = (
            UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
        ),
    ) -> InteractionOutcome | None:
        """Dispatch one wizard command and continue from its Qt result callback."""

        def _handle_error(error: tuple) -> None:
            self._bindings.present_unexpected_error(
                self.panel,
                unexpected_error_context,
                error_info=error,
                message_box=self._bindings.message_box(),
                title=error_title,
            )

        def _deliver_result(result) -> InteractionOutcome | None:
            return on_result(result)

        if self._bindings.execute_application_command_async(
            self.panel,
            command,
            on_result=_deliver_result,
            on_error=_handle_error,
            busy_target=self.panel,
            expected_publication_generation=expected_publication_generation,
        ):
            return InteractionOutcome.accepted(
                "Data interpretation command was scheduled."
            )
        if self._bindings.has_real_application_context(self.panel):
            self._bindings.message_box().warning(
                self.panel,
                blocked_title,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return InteractionOutcome.blocked(
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
        if expected_publication_generation is None:
            result = self._bindings.execute_application_command(
                self.panel,
                command,
            )
        else:
            result = self._bindings.execute_application_command(
                self.panel,
                command,
                expected_publication_generation=expected_publication_generation,
            )
        if result is None:
            return None
        callback_outcome = on_result(result)
        if callback_outcome is not None:
            return callback_outcome
        if result.failed:
            return self._interaction_failure_outcome(result, result.message)
        return InteractionOutcome.completed(result.message)

    def _start_interpretation_review_async(
        self,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        *,
        initial_step: str = "",
    ) -> InteractionOutcome | None:
        """Run scan/preview/validate off the Qt thread for real Study-backed UI."""

        def _handle_review_result(review_result) -> InteractionOutcome:
            resource_outcome = self._preview_resource_preflight_outcome(
                review_result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            if self._result_failed(
                review_result,
                "Interpretation review failed",
            ):
                return self._interaction_failure_outcome(
                    review_result,
                    review_result.message,
                )
            try:
                review_state = self._review_state_from_review_result(review_result)
            except (
                ApplicationError,
                ControllerCompatibilityUnavailableError,
            ) as exc:
                self._bindings.message_box().warning(
                    self.panel,
                    "Import review changed",
                    str(exc),
                )
                return InteractionOutcome.blocked(str(exc))
            self._show_status("Import review ready.")
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=review_state,
                initial_step=initial_step,
            )

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            self._show_status("Preparing import review...")
            return self._execute_interpretation_command_async(
                ReviewInterpretationCommand(
                    source_path=source_path,
                    source_hint=source_hint,
                    label_sources=label_sources,
                    choices=choices,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_review_result,
                error_title="Interpretation failed",
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
                ),
            )

        return _dispatch()

    def _preview_and_validate_interpretation_async(
        self,
        *,
        choices: dict[str, Any],
        review_state: _InterpretationReviewState,
        on_validated: Callable[
            [_InterpretationReviewState],
            InteractionOutcome,
        ],
        error_title: str,
    ) -> InteractionOutcome | None:
        """Rebuild choices from the admitted scan, then validate the candidate."""
        scan = dict(review_state.scan)
        scan_id = self._optional_payload_id(scan, "scan_id")
        if scan_id is None:
            message = (
                "The Data Import scan identity is unavailable. Reopen the source "
                "and try again."
            )
            self._bindings.message_box().warning(
                self.panel, "Import review changed", message
            )
            return InteractionOutcome.blocked(message)

        def _handle_validation(
            validation_result,
            *,
            preview: dict[str, Any],
            candidate: dict[str, Any],
        ) -> InteractionOutcome:
            if self._result_failed(
                validation_result,
                "Interpretation validation failed",
            ):
                return self._interaction_failure_outcome(
                    validation_result,
                    validation_result.message,
                )
            decision = self._diagnostic_payload(
                validation_result,
                "validation_decision",
            )
            try:
                validated_state = self._review_state_from_parts(
                    scan=scan,
                    preview=preview,
                    candidate=candidate,
                    decision=decision,
                )
            except (
                ApplicationError,
                ControllerCompatibilityUnavailableError,
            ) as exc:
                self._bindings.message_box().warning(
                    self.panel,
                    "Import review changed",
                    str(exc),
                )
                return InteractionOutcome.blocked(str(exc))
            return on_validated(validated_state)

        def _handle_preview_result(preview_result) -> InteractionOutcome:
            resource_outcome = self._preview_resource_preflight_outcome(
                preview_result,
                retry=lambda token: _dispatch_preview(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                return resource_outcome
            if self._result_failed(preview_result, error_title):
                return self._interaction_failure_outcome(
                    preview_result,
                    preview_result.message,
                )
            preview = self._diagnostic_payload(preview_result, "preview")
            candidate = self._diagnostic_payload(preview_result, "candidate")
            candidate_id = self._optional_payload_id(candidate, "candidate_id")
            try:
                preview_state = self._review_state_from_parts(
                    scan=scan,
                    preview=preview,
                    candidate=candidate,
                    decision={},
                )
            except (
                ApplicationError,
                ControllerCompatibilityUnavailableError,
            ) as exc:
                self._bindings.message_box().warning(
                    self.panel,
                    "Import review changed",
                    str(exc),
                )
                return InteractionOutcome.blocked(str(exc))
            started = self._execute_interpretation_command_async(
                ValidateInterpretationCommand(candidate_id=candidate_id),
                on_result=lambda result: _handle_validation(
                    result,
                    preview=preview,
                    candidate=candidate,
                ),
                error_title="Interpretation validation failed",
                expected_publication_generation=(preview_state.publication_generation),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_VALIDATION
                ),
            )
            if started is not None:
                return started
            message = "Data Interpretation validation service is unavailable."
            self._bindings.message_box().critical(
                self.panel,
                "Interpretation validation unavailable",
                message,
            )
            return InteractionOutcome.blocked(message)

        def _dispatch_preview(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            return self._execute_interpretation_command_async(
                PreviewInterpretationCommand(
                    scan_id=scan_id,
                    choices=choices,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_preview_result,
                error_title=error_title,
                expected_publication_generation=(review_state.publication_generation),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_PREVIEW
                ),
            )

        return _dispatch_preview()

    def _repreview_interpretation_async(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        label_sources: list[str],
        review_state: _InterpretationReviewState,
        initial_step: str,
    ) -> InteractionOutcome | None:
        """Reopen edited choices without rediscovering the admitted source."""

        def _open_validated_review(
            validated_state: _InterpretationReviewState,
        ) -> InteractionOutcome:
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=validated_state,
                initial_step=initial_step,
            )

        return self._preview_and_validate_interpretation_async(
            choices=choices,
            review_state=review_state,
            on_validated=_open_validated_review,
            error_title="Interpretation preview failed",
        )

    def _review_interpretation_for_apply_async(
        self,
        *,
        choices: dict[str, Any],
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome | None:
        """Validate edited choices from the existing scan, then apply."""

        def _apply_validated_review(
            validated_state: _InterpretationReviewState,
        ) -> InteractionOutcome:
            if str(validated_state.decision.get("decision")) == "blocked":
                return InteractionOutcome.blocked(
                    self._decision_reason(validated_state.decision)
                )
            return self._apply_interpretation_async(
                validated_state,
                dialog_result,
            )

        return self._preview_and_validate_interpretation_async(
            choices=choices,
            review_state=review_state,
            on_validated=_apply_validated_review,
            error_title="Interpretation preview failed",
        )

    def _apply_interpretation_async(
        self,
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome:
        """Apply one reviewed candidate and continue to optional recipe saving."""
        candidate_id = (
            self._optional_payload_id(review_state.decision, "candidate_id")
            or review_state.candidate_id
        )

        def _handle_apply_result(apply_result) -> InteractionOutcome:
            resource_preflight = self._resource_preflight_view(apply_result)
            if apply_result.failed and resource_preflight:
                risk_level = resource_preflight.risk_level
                error_type = getattr(
                    getattr(apply_result, "error_type", None),
                    "value",
                    getattr(apply_result, "error_type", None),
                )
                if (
                    error_type == ErrorType.CONFIRMATION_REQUIRED.value
                    and risk_level in {"warning", "unknown"}
                ):
                    challenge = resource_preflight.challenge
                    if challenge is None:
                        message = (
                            "The resource check could not be confirmed safely. "
                            "Retry the import to run a fresh check."
                        )
                        self._bindings.message_box().critical(
                            self.panel,
                            "Dataset Resource Check",
                            message,
                        )
                        return InteractionOutcome.blocked(message)
                    reply = self._bindings.message_box().question(
                        self.panel,
                        "Dataset Resource Check",
                        (resource_preflight.message or apply_result.message)
                        + "\n\nContinue importing this dataset?",
                        self._bindings.message_box().StandardButton.Yes
                        | self._bindings.message_box().StandardButton.No,
                        self._bindings.message_box().StandardButton.No,
                    )
                    if reply != self._bindings.message_box().StandardButton.Yes:
                        return InteractionOutcome.cancelled(
                            "Dataset import was cancelled during the resource check."
                        )

                    continuation = self._bindings.reserve_interaction_continuation()

                    def _resume_confirmed_apply() -> None:
                        if self._bindings.qt_object_deleted(self.panel):
                            if continuation is not None:
                                continuation.fail(
                                    "The dataset surface closed before the confirmed "
                                    "import retry could start."
                                )
                            return

                        def _start_confirmed_apply() -> InteractionOutcome:
                            return _dispatch_apply(
                                resource_preflight_confirmed=True,
                                resource_preflight_token=challenge.challenge_id,
                            )

                        if continuation is not None:
                            continuation.start(_start_confirmed_apply)
                        else:
                            _start_confirmed_apply()

                    try:
                        self._bindings.single_shot(0, _resume_confirmed_apply)
                    except Exception:
                        logger.exception("Could not schedule confirmed dataset import")
                        message = (
                            "The confirmed dataset import retry could not be started."
                        )
                        if continuation is not None:
                            continuation.fail(message)
                        return InteractionOutcome.failed(message)
                    return InteractionOutcome.accepted(
                        "Confirmed dataset import was scheduled."
                    )
                if risk_level == "blocking":
                    self._bindings.message_box().critical(
                        self.panel,
                        "Dataset Resource Check",
                        resource_preflight.message or apply_result.message,
                    )
                    return InteractionOutcome.blocked(apply_result.message)
            if self._result_failed(apply_result, "Interpretation apply failed"):
                return self._interaction_failure_outcome(
                    apply_result,
                    apply_result.message,
                )

            def _finish(recipe_message: str = "") -> None:
                del recipe_message

            if bool(dialog_result.get("save_recipe", False)):
                if not self._save_interpretation_recipe(on_complete=_finish):
                    _finish()
                return InteractionOutcome.completed(apply_result.message)
            _finish()
            return InteractionOutcome.completed(apply_result.message)

        def _dispatch_apply(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome:
            self._show_status("Loading EEG data...")
            apply_command = ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=dialog_result.get("confirmed") is True,
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
            )
            return self._execute_interpretation_command_async(
                apply_command,
                on_result=_handle_apply_result,
                error_title="Interpretation apply failed",
                expected_publication_generation=(review_state.publication_generation),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_APPLY
                ),
            ) or InteractionOutcome.blocked(
                "Data interpretation apply could not be started."
            )

        return _dispatch_apply()

    @staticmethod
    def _resource_preflight_view(result: Any) -> ResourcePreflightView | None:
        """Read resource diagnostics through the shared typed contract."""
        diagnostics = getattr(result, "diagnostics", {})
        try:
            return ResourcePreflightView.from_diagnostics(diagnostics)
        except ResourcePreflightContractError:
            return None

    def _preview_resource_preflight_outcome(
        self,
        result: Any,
        *,
        retry: Callable[[str], Any],
    ) -> InteractionOutcome | None:
        """Handle preview RAM warnings before label payloads are materialized."""
        if not getattr(result, "failed", False):
            return None
        preflight = self._resource_preflight_view(result)
        if not preflight:
            return None
        risk_level = preflight.risk_level
        if risk_level == "blocking":
            message = preflight.message or result.message
            self._bindings.message_box().critical(
                self.panel, "Dataset Resource Check", message
            )
            return InteractionOutcome.blocked(message)
        error_type = getattr(
            getattr(result, "error_type", None),
            "value",
            getattr(result, "error_type", None),
        )
        if error_type != ErrorType.CONFIRMATION_REQUIRED.value or risk_level not in {
            "warning",
            "unknown",
        }:
            return None
        challenge = preflight.challenge
        if challenge is None:
            message = (
                "The resource check could not be confirmed safely. "
                "Retry the import to run a fresh check."
            )
            self._bindings.message_box().critical(
                self.panel, "Dataset Resource Check", message
            )
            return InteractionOutcome.blocked(message)
        result_command = str(getattr(result, "command_name", "") or "").strip().lower()
        if challenge.command_name.strip().lower() != result_command:
            message = (
                "The resource confirmation did not match this import action. "
                "Retry the import to run a fresh check."
            )
            self._bindings.message_box().critical(
                self.panel, "Dataset Resource Check", message
            )
            return InteractionOutcome.blocked(message)
        reply = self._bindings.message_box().question(
            self.panel,
            "Dataset Resource Check",
            (preflight.message or result.message)
            + "\n\nContinue building the import preview?",
            self._bindings.message_box().StandardButton.Yes
            | self._bindings.message_box().StandardButton.No,
            self._bindings.message_box().StandardButton.No,
        )
        if reply != self._bindings.message_box().StandardButton.Yes:
            return InteractionOutcome.cancelled(
                "Dataset import preview was cancelled during the resource check."
            )
        retry_outcome = retry(challenge.challenge_id)
        if isinstance(
            retry_outcome, InteractionOutcome
        ) and retry_outcome.status.value in {"blocked", "failed"}:
            return retry_outcome
        return InteractionOutcome.accepted("Confirmed dataset preview was scheduled.")

    def _review_state_from_review_result(
        self,
        review_result,
    ) -> _InterpretationReviewState:
        candidate = self._diagnostic_payload(review_result, "candidate")
        return self._review_state_from_parts(
            scan=self._diagnostic_payload(review_result, "scan_result"),
            preview=self._diagnostic_payload(review_result, "preview"),
            candidate=candidate,
            decision=self._diagnostic_payload(review_result, "validation_decision"),
        )

    def _review_state_from_parts(
        self,
        *,
        scan: dict[str, Any],
        preview: dict[str, Any],
        candidate: dict[str, Any],
        decision: dict[str, Any],
    ) -> _InterpretationReviewState:
        scan_id = self._optional_payload_id(scan, "scan_id")
        candidate_id = self._optional_payload_id(candidate, "candidate_id")
        if scan_id is None or candidate_id is None:
            raise PreconditionError(
                "The Data Import review identity could not be verified. Refresh the "
                "review and try again.",
                diagnostics={"stale_interpretation_review": True},
            )
        publication = self._bindings.get_application_view_publication(self.panel)
        if publication is None:
            raise ControllerCompatibilityUnavailableError(
                "The Data Import review runtime is unavailable."
            )
        identity = InterpretationReviewIdentity(
            publication_generation=publication.generation,
            scan_id=scan_id,
            candidate_id=candidate_id,
        )
        self._require_interpretation_identity(publication, identity)
        return _InterpretationReviewState(
            scan=scan,
            preview=preview,
            candidate=candidate,
            candidate_id=candidate_id,
            decision=decision,
            publication_generation=identity.publication_generation,
        )

    def _result_failed(self, result, title: str) -> bool:
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

    @staticmethod
    def _interaction_failure_outcome(result, message: str) -> InteractionOutcome:
        if bool(getattr(result, "recoverable", False)):
            return InteractionOutcome.blocked(message)
        return InteractionOutcome.failed(message)

    @staticmethod
    def _dialog_label_sources(
        dialog_result: dict[str, Any],
        current_sources: list[str],
    ) -> list[str]:
        if not bool(dialog_result.get("label_sources_changed")):
            return list(current_sources)
        raw_sources = dialog_result.get("label_sources")
        if not isinstance(raw_sources, list):
            return list(current_sources)
        result: list[str] = []
        for source in raw_sources:
            text = str(source).strip()
            if text and text not in result:
                result.append(text)
        return result

    def _save_interpretation_recipe(
        self,
        *,
        on_complete: Callable[[str], None] | None = None,
        review_context: CommandReviewContext | None = None,
        review_context_resolved: bool = False,
    ) -> bool:
        """Persist the current recipe and report completion asynchronously."""
        complete = on_complete or (lambda _message: None)
        if not review_context_resolved:
            review_context = self._bindings.get_command_review_context(
                self.panel,
                CommandName.SAVE_INTERPRETATION_RECIPE,
            )
        if review_context is None and self._bindings.has_real_application_context(
            self.panel
        ):
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Save Blocked",
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            complete("")
            return True
        save_capability = (
            getattr(review_context, "capability", None)
            if review_context is not None
            else None
        )
        if review_context is not None and save_capability is None:
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Save Blocked",
                _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
            )
            complete("")
            return True
        recipe_block_reason = (
            self._bindings.blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
            if save_capability is not None and not save_capability.enabled
            else self._recipe_save_block_reason()
            if review_context is None
            else None
        )
        if recipe_block_reason is not None:
            self._bindings.message_box().warning(
                self.panel,
                "Recipe Save Blocked",
                recipe_block_reason,
            )
            complete("")
            return True

        recipe_path, _ = self._bindings.file_dialog().getSaveFileName(
            self.panel,
            "Save Interpretation Recipe",
            "import_recipe.json",
            "JSON (*.json)",
        )

        def _handle_result(result) -> None:
            if result.failed:
                title = (
                    "Review Recipe Save Again"
                    if self._bindings.is_stale_publication_result(result)
                    else "Recipe not saved"
                )
                self._bindings.message_box().warning(self.panel, title, result.message)
                complete("")
                return
            complete("Recipe saved." if recipe_path else "Recipe kept in this session.")

        outcome = self._execute_interpretation_command_async(
            SaveInterpretationRecipeCommand(recipe_path=recipe_path or None),
            on_result=_handle_result,
            error_title="Recipe save failed",
            expected_publication_generation=(
                review_context.publication_generation
                if review_context is not None
                else None
            ),
            unexpected_error_context=UnexpectedErrorContext.DATA_IMPORT_RECIPE_SAVE,
        )
        return outcome is not None

    def _recipe_save_block_reason(self) -> str | None:
        save_capability = self._bindings.get_command_capability(
            self.panel,
            CommandName.SAVE_INTERPRETATION_RECIPE,
        )
        if save_capability is not None and not save_capability.enabled:
            return self._bindings.blocked_reason(
                save_capability,
                "Apply an interpretation before saving a recipe.",
            )
        return None

    @staticmethod
    def _interpretation_source_and_choices(
        filepaths: list[str],
    ) -> tuple[str, dict[str, Any]]:
        if len(filepaths) == 1:
            return filepaths[0], {}

        parents = [str(Path(path).expanduser().parent) for path in filepaths]
        unique_parents = sorted(set(parents))
        source_path = unique_parents[0] if len(unique_parents) == 1 else filepaths[0]
        return source_path, {"selected_eeg_files": list(filepaths)}

    @staticmethod
    def _merge_interpretation_choices(
        base: dict[str, Any],
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        return merge_interpretation_choices(base, updates)

    @staticmethod
    def _choices_after_label_source_change(
        choices: dict[str, Any],
    ) -> dict[str, Any]:
        """Invalidate decisions derived from the previous label-carrier set."""
        result = dict(choices)
        for key in (
            "skip_labels",
            "label_carrier",
            "label_sources",
            "required_label_carriers",
            "label_carrier_choices",
            "label_carrier_remap",
            "internal_event_selection",
            "run_event_mappings",
            "class_map",
            "event_roles",
        ):
            result.pop(key, None)
        return result

    @staticmethod
    def _diagnostic_payload(result, key: str) -> dict:
        return diagnostic_payload(result, key)

    @staticmethod
    def _optional_payload_id(payload: dict, key: str) -> str | None:
        return optional_payload_id(payload, key)

    @staticmethod
    def _decision_reason(decision: dict) -> str:
        return decision_reason(decision)
