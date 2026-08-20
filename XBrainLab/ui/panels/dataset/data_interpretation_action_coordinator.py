"""Focused UI workflow owner for Data Interpretation imports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    CommandName,
    LoadDataCommand,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
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
from XBrainLab.platform_paths import dataset_storage_layout
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    CommandReviewContext,
    ControllerCompatibilityUnavailableError,
    application_ui_runtime,
    blocked_reason,
    cancel_application_operation,
    execute_application_command,
    execute_application_command_async,
    get_application_operation,
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
from XBrainLab.ui.owned_operation_presenter import OwnedOperationPresenter
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


def _dataset_dialog_start_directory(*, prefer_bids: bool = False) -> str:
    layout = dataset_storage_layout()
    candidates = (
        (layout.bids_root, layout.datasets_root, layout.data_root)
        if prefer_bids
        else (layout.datasets_root, layout.data_root)
    )
    return next((str(path) for path in candidates if path.is_dir()), "")


def _default_loading_dialog_class() -> type[Any]:
    from XBrainLab.ui.dialogs.dataset.data_interpretation_loading_dialog import (  # noqa: PLC0415
        DataInterpretationLoadingDialog,
    )

    return DataInterpretationLoadingDialog


def _default_source_chooser_dialog_class() -> type[Any]:
    from XBrainLab.ui.dialogs.dataset.eeg_source_chooser_dialog import (  # noqa: PLC0415
        EegSourceChooserDialog,
    )

    return EegSourceChooserDialog


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
    cancel_application_operation: Callable[..., bool]
    execute_application_command: Callable[..., Any]
    execute_application_command_async: Callable[..., Any]
    get_application_operation: Callable[..., Any]
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
        cancel_application_operation=cancel_application_operation,
        execute_application_command=execute_application_command,
        execute_application_command_async=execute_application_command_async,
        get_application_operation=get_application_operation,
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

    def _show_status(self, message: str, timeout_ms: int = 7000) -> None: ...

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
        bids_subject_dialog_class: Callable[[], type[Any]],
        source_chooser_dialog_class: Callable[[], type[Any]] | None = None,
        loading_dialog_class: Callable[[], type[Any]] | None = None,
        bindings: DataInterpretationActionBindings | None = None,
    ) -> None:
        self._host = host
        self.panel = host.panel
        self._source_chooser_dialog_class = (
            source_chooser_dialog_class or _default_source_chooser_dialog_class
        )
        self._preview_dialog_class = preview_dialog_class
        self._bids_subject_dialog_class = bids_subject_dialog_class
        self._loading_dialog_class = (
            loading_dialog_class or _default_loading_dialog_class
        )
        self._active_loading_dialog: Any | None = None
        self._active_loading_token: object | None = None
        self._active_loading_operation_id: str | None = None
        self._loading_cancel_operation_id: str | None = None
        self._operation_presenter: OwnedOperationPresenter | None = None
        timer_parent = self.panel if isinstance(self.panel, QObject) else None
        self._loading_progress_timer = QTimer(timer_parent)
        self._loading_progress_timer.setInterval(250)
        self._loading_progress_timer.timeout.connect(
            self._refresh_loading_operation_status
        )
        self._busy_control_states: list[tuple[Any, bool]] = []
        self._bindings = bindings or default_data_interpretation_action_bindings()
        self._recipe_reload = DataInterpretationRecipeReloadCoordinator(
            self,
            preview_dialog_class=self._preview_dialog_class,
            bindings=self._bindings,
        )

    def _open_loading_dialog(
        self,
        *,
        initial_step: str,
        retry: Callable[[], Any],
    ) -> object:
        self._close_loading_dialog()
        token = object()
        dialog_class = self._loading_dialog_class()
        dialog = dialog_class(
            self._loading_dialog_parent(),
            initial_step=initial_step,
        )
        self._active_loading_dialog = dialog
        self._active_loading_token = token
        self._active_loading_operation_id = None
        self._loading_progress_timer.stop()
        dialog.rejected.connect(lambda: self._cancel_loading_dialog(token))
        dialog.retry_requested.connect(
            lambda: retry() if self._loading_dialog_is_active(token) else None
        )
        dialog.show()
        return token

    def _loading_dialog_parent(self) -> Any | None:
        """Keep the modal surface independent from the disabled busy panel."""
        window_getter = getattr(self.panel, "window", None)
        if not callable(window_getter):
            return None
        try:
            top_level = window_getter()
        except RuntimeError:
            return None
        return top_level if top_level is not self.panel else None

    def _loading_dialog_is_active(self, token: object) -> bool:
        dialog = self._active_loading_dialog
        return bool(
            self._active_loading_token is token
            and dialog is not None
            and not bool(getattr(dialog, "cancelled_by_user", False))
        )

    def _cancel_loading_dialog(self, token: object) -> None:
        if self._active_loading_token is not token:
            return
        operation_id = self._active_loading_operation_id
        if operation_id is not None:
            presenter = self._operation_presenter
            if presenter is not None and presenter.active_operation_id == operation_id:
                cancel_requested = presenter.request_cancel()
            else:
                cancel_requested = self._bindings.cancel_application_operation(
                    self.panel,
                    operation_id,
                )
            if cancel_requested:
                self._loading_cancel_operation_id = operation_id
        dialog = self._active_loading_dialog
        self._active_loading_token = None
        self._active_loading_dialog = None
        self._active_loading_operation_id = None
        self._loading_progress_timer.stop()
        if dialog is not None:
            dialog.deleteLater()

    def cancel_active_operation(self) -> bool:
        """Request cancellation from the visible Dataset action surface."""
        presenter = self._operation_presenter
        return presenter.request_cancel() if presenter is not None else False

    def set_busy(self, busy: bool) -> None:
        """Fence Dataset mutations without disabling the active Import cancel action.

        Async interpreter work used to mark the complete Dataset panel busy.  Qt
        then disabled ``OwnedOperationCancelButton`` as a child of the panel,
        leaving an admitted Apply impossible to cancel from its visible product
        surface.  Keep every other mutable Dataset action fenced, including
        inline table edits, while deliberately leaving the owned-operation
        control enabled for the operation presenter.
        """
        if busy:
            if self._busy_control_states:
                return
            sidebar = getattr(self.panel, "sidebar", None)
            if sidebar is None:
                set_busy = getattr(self.panel, "set_busy", None)
                if callable(set_busy):
                    set_busy(True)
                    self._busy_control_states.append((self.panel, True))
                return
            cancel_button = getattr(sidebar, "import_cancel_btn", None)
            controls = list(getattr(sidebar, "_action_buttons", ()) or ())
            table = getattr(self.panel, "table", None)
            if table is not None:
                controls.append(table)
            for control in controls:
                if control is None or control is cancel_button:
                    continue
                is_enabled = getattr(control, "isEnabled", None)
                set_enabled = getattr(control, "setEnabled", None)
                if not callable(is_enabled) or not callable(set_enabled):
                    continue
                self._busy_control_states.append((control, bool(is_enabled())))
                set_enabled(False)
            return

        control_states = self._busy_control_states
        self._busy_control_states = []
        for control, was_enabled in control_states:
            if control is self.panel:
                set_busy = getattr(control, "set_busy", None)
                if callable(set_busy):
                    set_busy(False)
                continue
            if self._bindings.qt_object_deleted(control):
                continue
            set_enabled = getattr(control, "setEnabled", None)
            if callable(set_enabled):
                set_enabled(was_enabled)

    def _ensure_operation_presenter(self) -> OwnedOperationPresenter | None:
        if self._operation_presenter is not None:
            return self._operation_presenter
        sidebar = getattr(self.panel, "sidebar", None)
        cancel_button = getattr(sidebar, "import_cancel_btn", None)
        if cancel_button is None or not isinstance(self.panel, QWidget):
            return None
        self._operation_presenter = OwnedOperationPresenter(
            self.panel,
            cancel_button=cancel_button,
            snapshot_getter=lambda operation_id: (
                self._bindings.get_application_operation(
                    self.panel,
                    operation_id,
                )
            ),
            canceller=lambda operation_id: self._bindings.cancel_application_operation(
                self.panel,
                operation_id,
            ),
        )
        self._operation_presenter.terminal.connect(
            self._handle_owned_operation_terminal
        )
        return self._operation_presenter

    def _handle_owned_operation_terminal(
        self,
        operation_id: str,
        phase: str,
    ) -> None:
        """Settle cancellation initiated from the modal import surface."""
        if operation_id != self._loading_cancel_operation_id:
            return
        self._loading_cancel_operation_id = None
        if phase == "cancelled":
            self._show_status("Dataset import cancelled")

    def _close_loading_dialog(self, token: object | None = None) -> None:
        if token is not None and self._active_loading_token is not token:
            return
        dialog = self._active_loading_dialog
        self._active_loading_token = None
        self._active_loading_dialog = None
        self._active_loading_operation_id = None
        self._loading_progress_timer.stop()
        if dialog is None:
            return
        dialog.accept()
        dialog.deleteLater()

    def _show_loading_error(
        self,
        token: object,
        message: str,
        *,
        retry_available: bool = True,
    ) -> None:
        if not self._loading_dialog_is_active(token):
            return
        dialog = self._active_loading_dialog
        if dialog is None:
            return
        dialog.show_error(
            message,
            retry_available=retry_available,
        )

    @property
    def controller(self) -> Any:
        return self._host.controller

    def _show_status(self, message: str, timeout_ms: int = 7000) -> None:
        if timeout_ms == 7000:
            self._host._show_status(message)
            return
        self._host._show_status(message, timeout_ms)

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

        chooser = self._source_chooser_dialog_class()(
            self.panel,
            start_directory=_dataset_dialog_start_directory(),
        )
        if not chooser.exec():
            return InteractionOutcome.cancelled("No EEG source was selected.")
        selection = chooser.get_result()
        if selection is None or not selection.paths:
            return InteractionOutcome.cancelled("No EEG source was selected.")

        if selection.kind != "files":
            source_path = str(selection.paths[0])
            try:
                outcome = self._start_source_classification_async(source_path)
                if outcome is not None:
                    return outcome
                message = "Data Interpretation command service is unavailable."
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation unavailable",
                    message,
                )
                return InteractionOutcome.failed(message)
            except Exception:
                message = self._bindings.present_unexpected_error(
                    self.panel,
                    UnexpectedErrorContext.DATA_IMPORT,
                    message_box=self._bindings.message_box(),
                )
                return InteractionOutcome.failed(message)

        filepaths = list(selection.paths)

        try:
            outcome = self._run_data_interpretation_import(
                filepaths,
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
                    paths=filepaths,
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

    def _start_source_classification_async(
        self,
        source_path: str,
    ) -> InteractionOutcome | None:
        """Classify one detached path, then enter the existing owned flow."""

        def _handle_classification(result) -> InteractionOutcome:
            error_type = getattr(
                getattr(result, "error_type", None),
                "value",
                getattr(result, "error_type", None),
            )
            if result.failed and error_type == ErrorType.CANCELLED.value:
                self._show_status("Dataset import cancelled")
                return InteractionOutcome.cancelled(result.message)
            if self._result_failed(result, "EEG source discovery failed"):
                return self._interaction_failure_outcome(result, result.message)
            diagnostics = getattr(result, "diagnostics", {})
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            source_kind = str(diagnostics.get("source_kind") or "").strip()
            if source_kind == "bids":
                catalog = diagnostics.get("bids_subject_catalog")
                if not isinstance(catalog, dict):
                    return InteractionOutcome.failed(
                        "BIDS subject catalog was unavailable."
                    )
                return self._present_bids_subject_catalog(source_path, catalog)
            if source_kind not in {"file", "folder"}:
                return InteractionOutcome.failed(
                    "The selected EEG source type could not be determined."
                )
            return self._run_data_interpretation_import(
                [source_path],
                source_hint=source_kind,
            ) or InteractionOutcome.blocked(
                "Data interpretation review could not be started."
            )

        self._show_status("Checking EEG source…")
        return self._execute_interpretation_command_async(
            ScanSourceCommand(
                source_path=source_path,
                source_hint="auto",
                catalog_only=True,
            ),
            on_result=_handle_classification,
            error_title="EEG source discovery failed",
            unexpected_error_context=UnexpectedErrorContext.DATA_IMPORT,
        )

    def import_folder_source(self):
        """Compatibility entry retained for non-sidebar callers."""
        if not self._can_start_interpretation():
            return
        source_path = self._bindings.file_dialog().getExistingDirectory(
            self.panel,
            "Choose Folder or BIDS Root for Interpretation",
            _dataset_dialog_start_directory(),
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
        """Compatibility entry retained for non-sidebar callers."""
        if not self._can_start_interpretation():
            return
        source_path = self._bindings.file_dialog().getExistingDirectory(
            self.panel,
            "Choose BIDS Folder for Import",
            _dataset_dialog_start_directory(prefer_bids=True),
            options=(
                self._bindings.file_dialog().Option.ShowDirsOnly
                | self._bindings.file_dialog().Option.DontUseNativeDialog
            ),
        )
        if not source_path:
            return
        try:
            handled = self._start_bids_subject_selection_async(source_path)
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

    def _start_bids_subject_selection_async(
        self,
        source_path: str,
    ) -> InteractionOutcome | None:
        """Inspect one explicit BIDS root for compatibility callers."""

        def _handle_catalog_result(result) -> InteractionOutcome:
            if self._result_failed(result, "BIDS subject discovery failed"):
                return self._interaction_failure_outcome(result, result.message)
            catalog = self._diagnostic_payload(result, "bids_subject_catalog")
            return self._present_bids_subject_catalog(source_path, catalog)

        self._show_status("Reading BIDS subject catalog...")
        return self._execute_interpretation_command_async(
            ScanSourceCommand(
                source_path=source_path,
                source_hint="bids",
                catalog_only=True,
            ),
            on_result=_handle_catalog_result,
            error_title="BIDS subject discovery failed",
            unexpected_error_context=UnexpectedErrorContext.DATA_IMPORT,
        )

    def _present_bids_subject_catalog(
        self,
        source_path: str,
        catalog: dict[str, Any],
    ) -> InteractionOutcome:
        """Reuse the bounded BIDS subject decision for a classified source."""
        if (
            not list(catalog.get("subjects") or [])
            or int(catalog.get("eeg_file_count") or 0) <= 0
        ):
            message = "No importable BIDS subjects were found in this folder."
            self._bindings.message_box().warning(
                self.panel,
                "No BIDS subjects found",
                message,
            )
            return InteractionOutcome.blocked(message)

        dialog_class = self._bids_subject_dialog_class()
        dialog = dialog_class(self.panel, catalog=catalog)
        if not dialog.exec():
            return InteractionOutcome.cancelled("BIDS subject selection was cancelled.")
        selected_subjects = [
            str(value).strip()
            for value in list(dialog.get_result() or [])
            if str(value).strip()
        ]
        if not selected_subjects:
            return InteractionOutcome.blocked(
                "Select at least one BIDS subject before continuing."
            )
        return self._run_data_interpretation_import(
            [source_path],
            source_hint="bids",
            initial_choices={"selected_bids_subjects": selected_subjects},
        ) or InteractionOutcome.blocked(
            "Data interpretation review could not be started."
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
        initial_choices: dict[str, Any] | None = None,
    ) -> InteractionOutcome | None:
        """Run the Data Interpretation command sequence for selected files."""
        source_path, choices = self._interpretation_source_and_choices(filepaths)
        if initial_choices:
            choices = self._merge_interpretation_choices(
                choices,
                dict(initial_choices),
            )
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
        loading_token: object | None = None,
        validated_choices: dict[str, Any] | None = None,
    ) -> InteractionOutcome:
        comparison_choices = (
            dict(validated_choices) if validated_choices is not None else dict(choices)
        )
        dialog_kwargs: dict[str, Any] = {
            "scan_result": review_state.scan,
            "preview": review_state.preview,
            "validation_decision": review_state.decision,
            "choices": dict(choices),
            "publication_generation": review_state.publication_generation,
        }
        if initial_step:
            dialog_kwargs["initial_step"] = initial_step
        dialog_class = self._preview_dialog_class()
        try:
            dialog = dialog_class(self.panel, **dialog_kwargs)
        except Exception:
            if loading_token is None:
                raise
            logger.exception("Could not construct the Data Import preview")
            message = "The import review could not be displayed. Try again."
            self._show_loading_error(loading_token, message)
            return InteractionOutcome.failed(message)
        if (
            self._bindings.qt_object_deleted(dialog)
            or not self._preview_context_is_available()
        ):
            if not self._bindings.qt_object_deleted(dialog):
                dialog.deleteLater()
            if loading_token is not None:
                self._close_loading_dialog(loading_token)
            return InteractionOutcome.cancelled(
                "Data interpretation preview was cancelled."
            )
        if loading_token is not None and not self._loading_dialog_is_active(
            loading_token
        ):
            dialog.deleteLater()
            return InteractionOutcome.cancelled(
                "Data interpretation preview was cancelled."
            )

        if loading_token is not None:
            # Construct the potentially heavy wizard while the existing owned
            # loading surface remains visible. Show the completed wizard before
            # releasing that surface so there is no blank transition.
            dialog.show()
            if (
                self._bindings.qt_object_deleted(dialog)
                or not self._preview_context_is_available()
                or not self._loading_dialog_is_active(loading_token)
            ):
                if not self._bindings.qt_object_deleted(dialog):
                    dialog.deleteLater()
                self._close_loading_dialog(loading_token)
                return InteractionOutcome.cancelled(
                    "Data interpretation preview was cancelled."
                )
            self._close_loading_dialog(loading_token)
        accepted = bool(dialog.exec())
        if not accepted:
            if isinstance(dialog, QObject):
                dialog.deleteLater()
            return InteractionOutcome.cancelled(
                "Data interpretation review was cancelled."
            )

        raw_dialog_result = dialog.get_result()
        dialog_result = (
            dict(raw_dialog_result) if isinstance(raw_dialog_result, dict) else {}
        )
        import_confirmed = dialog_result.get("confirmed") is True
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

        def _continue_after_review() -> InteractionOutcome:
            continuation_choices = updated_choices
            if next_label_sources != label_sources:
                continuation_choices = self._choices_after_label_source_change(
                    continuation_choices
                )
                return self._start_interpretation_review_async(
                    source_path,
                    source_hint,
                    continuation_choices,
                    next_label_sources,
                    initial_step=str(dialog_result.get("resume_step") or ""),
                ) or InteractionOutcome.blocked(
                    "Data interpretation review could not be started."
                )

            if (
                str(review_state.decision.get("decision")) == "blocked"
                and continuation_choices == comparison_choices
            ):
                if import_confirmed:
                    self._show_status(
                        "Dataset import blocked · Review the import settings"
                    )
                return InteractionOutcome.blocked(
                    self._decision_reason(review_state.decision)
                )

            if continuation_choices != comparison_choices:
                resume_step = str(dialog_result.get("resume_step") or "").strip()
                if resume_step == "Match Labels":
                    return self._repreview_interpretation_async(
                        source_path=source_path,
                        source_hint=source_hint,
                        choices=continuation_choices,
                        label_sources=label_sources,
                        review_state=review_state,
                        initial_step=resume_step,
                    ) or InteractionOutcome.blocked(
                        "Data interpretation preview could not be refreshed."
                    )
                return self._review_interpretation_for_apply_async(
                    source_path=source_path,
                    source_hint=source_hint,
                    choices=continuation_choices,
                    validated_choices=comparison_choices,
                    label_sources=label_sources,
                    review_state=review_state,
                    dialog_result=dialog_result,
                ) or InteractionOutcome.blocked(
                    "Data interpretation review could not be refreshed."
                )

            def _retry_cancelled_apply() -> InteractionOutcome:
                return self.review_current_import(
                    initial_step="Review and Import",
                    expected_identity=self._review_identity(review_state),
                )

            return self._apply_interpretation_async(
                review_state,
                dialog_result,
                retry_cancelled_apply=_retry_cancelled_apply,
            )

        # The production preview is a QDialog.  Finish destroying that modal
        # surface before opening resource confirmation or dispatching Apply;
        # otherwise WSLg/native compositors can briefly render both modal
        # lifecycles during the same call stack.  Plain injected test doubles
        # retain the synchronous fallback because they have no Qt lifecycle.
        if not isinstance(dialog, QObject):
            return _continue_after_review()

        continuation = self._bindings.reserve_interaction_continuation()
        continuation_scheduled = False

        def _start_review_continuation() -> None:
            if continuation is not None:
                continuation.start(_continue_after_review)
            else:
                _continue_after_review()

        def _review_dialog_destroyed(*_args: object) -> None:
            nonlocal continuation_scheduled
            if continuation_scheduled:
                return
            continuation_scheduled = True
            try:
                self._bindings.single_shot(0, _start_review_continuation)
            except Exception:
                logger.exception("Could not continue the accepted dataset review")
                message = "The accepted dataset review could not continue."
                self._show_status("Dataset import failed · Review the import settings")
                if continuation is not None:
                    continuation.fail(message)

        try:
            dialog.destroyed.connect(_review_dialog_destroyed)
            dialog.deleteLater()
        except Exception:
            logger.exception("Could not close the accepted dataset review")
            message = "The accepted dataset review could not be closed safely."
            if continuation is not None:
                continuation.fail(message)
            self._show_status("Dataset import failed · Review the import settings")
            return InteractionOutcome.failed(message)
        return InteractionOutcome.accepted(
            "Dataset import will continue after the review closes."
        )

    def _preview_context_is_available(self) -> bool:
        """Return whether a newly built preview may still enter its modal loop."""
        if self._bindings.qt_object_deleted(self.panel):
            return False
        window_getter = getattr(self.panel, "window", None)
        if not callable(window_getter):
            return True
        try:
            window = window_getter()
        except RuntimeError:
            return False
        return bool(
            window is None
            or (
                not self._bindings.qt_object_deleted(window)
                and getattr(window, "_closing_in_progress", False) is not True
            )
        )

    def _execute_interpretation_command_async(
        self,
        command,
        *,
        on_result: Callable[[Any], InteractionOutcome | None],
        error_title: str,
        expected_publication_generation: int | None = None,
        blocked_title: str = "Interpretation Blocked",
        on_error: Callable[[tuple], None] | None = None,
        unexpected_error_context: UnexpectedErrorContext = (
            UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
        ),
    ) -> InteractionOutcome | None:
        """Dispatch one wizard command and continue from its Qt result callback."""

        def _handle_error(error: tuple) -> None:
            if on_error is not None:
                on_error(error)
                return
            self._bindings.present_unexpected_error(
                self.panel,
                unexpected_error_context,
                error_info=error,
                message_box=self._bindings.message_box(),
                title=error_title,
            )

        def _deliver_result(result) -> InteractionOutcome | None:
            return on_result(result)

        def _bind_loading_operation(operation_id: str) -> None:
            presenter = self._ensure_operation_presenter()
            if presenter is not None:
                presenter.bind(operation_id, stage="Preparing import")
            if self._active_loading_token is not None:
                self._active_loading_operation_id = operation_id
                sidebar = getattr(self.panel, "sidebar", None)
                cancel_button = getattr(sidebar, "import_cancel_btn", None)
                if cancel_button is not None:
                    cancel_button.setVisible(False)
                dialog = self._active_loading_dialog
                progress_bar = getattr(dialog, "progress_bar", None)
                if progress_bar is not None:
                    progress_bar.setProperty("operationId", operation_id)
                    progress_bar.setProperty("operationKind", "")
                    progress_bar.setProperty("stage", "Preparing import")
                    progress_bar.setProperty("progress", "indeterminate")
                    progress_bar.setProperty("indeterminate", True)
                    progress_bar.setProperty("operationPhase", "pending")
                self._loading_progress_timer.start()

        if self._bindings.execute_application_command_async(
            self.panel,
            command,
            on_result=_deliver_result,
            on_error=_handle_error,
            # The coordinator's narrow busy surface fences every Dataset
            # mutation while keeping the visible owned-operation Cancel button
            # operable.  Passing the panel itself would disable Cancel as a Qt
            # child and make a cancellable Apply impossible to stop.
            busy_target=self,
            expected_publication_generation=expected_publication_generation,
            on_operation_started=_bind_loading_operation,
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

    def _refresh_loading_operation_status(self) -> None:
        """Project backend stage truth into the active cancellable dialog."""
        operation_id = self._active_loading_operation_id
        dialog = self._active_loading_dialog
        if operation_id is None or dialog is None:
            self._loading_progress_timer.stop()
            return
        snapshot = self._bindings.get_application_operation(
            self.panel,
            operation_id,
        )
        if snapshot is None:
            return
        phase = str(getattr(snapshot.phase, "value", snapshot.phase))
        raw_kind = getattr(snapshot, "kind", "")
        kind = str(getattr(raw_kind, "value", raw_kind) or "")
        if phase in {"completed", "cancelled", "failed"}:
            self._loading_progress_timer.stop()
        stage = str(getattr(snapshot, "stage", "") or "Working")
        completed = getattr(snapshot, "completed", None)
        total = getattr(snapshot, "total", None)
        if isinstance(completed, int) and isinstance(total, int):
            detail = f"{completed} of {total} items complete"
        elif bool(getattr(snapshot, "cancel_requested", False)):
            detail = "Cancelling safely…"
        else:
            detail = "Working…"
        set_stage = getattr(dialog, "set_stage", None)
        if callable(set_stage):
            set_stage(stage, detail)
        progress_bar = getattr(dialog, "progress_bar", None)
        if progress_bar is not None:
            progress_bar.setProperty("operationId", operation_id)
            progress_bar.setProperty("operationKind", kind)
            progress_bar.setProperty("stage", stage)
            progress_bar.setProperty(
                "progress",
                f"{completed}/{total}"
                if isinstance(completed, int) and isinstance(total, int)
                else "indeterminate",
            )
            progress_bar.setProperty(
                "indeterminate",
                not (isinstance(completed, int) and isinstance(total, int)),
            )
            progress_bar.setProperty("operationPhase", phase)

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

        loading_token: object | None = None

        def _retry_review() -> None:
            _dispatch()

        def _handle_review_result(review_result) -> InteractionOutcome:
            if loading_token is None or not self._loading_dialog_is_active(
                loading_token
            ):
                return InteractionOutcome.cancelled(
                    "Data interpretation review was cancelled."
                )
            resource_outcome = self._preview_resource_preflight_outcome(
                review_result,
                retry=lambda token: _dispatch(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                if resource_outcome.status.value == "cancelled":
                    self._close_loading_dialog(loading_token)
                elif resource_outcome.status.value in {"blocked", "failed"}:
                    self._show_loading_error(
                        loading_token,
                        resource_outcome.message,
                    )
                return resource_outcome
            if self._result_failed(
                review_result,
                "Interpretation review failed",
                present=False,
            ):
                self._show_loading_error(loading_token, review_result.message)
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
                self._show_loading_error(loading_token, str(exc))
                return InteractionOutcome.blocked(str(exc))
            self._show_status("Import review ready.")
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=review_state,
                initial_step=initial_step,
                loading_token=loading_token,
            )

        def _dispatch(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            if loading_token is not None and self._loading_dialog_is_active(
                loading_token
            ):
                dialog = self._active_loading_dialog
                if dialog is not None:
                    dialog.set_stage(
                        "Preparing import review",
                        "Scanning the selected EEG data and nearby label files.",
                    )
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
                on_error=lambda error: self._show_loading_error(
                    loading_token,
                    str(error[1]) if len(error) > 1 else "The import review failed.",
                )
                if loading_token is not None
                else None,
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_REVIEW
                ),
            )

        loading_token = self._open_loading_dialog(
            initial_step=initial_step,
            retry=_retry_review,
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
        loading_token: object | None = None,
        on_terminal: Callable[[InteractionOutcome], None] | None = None,
        on_cancelled: Callable[
            [_InterpretationReviewState | None],
            InteractionOutcome,
        ]
        | None = None,
    ) -> InteractionOutcome | None:
        """Rebuild choices from the admitted scan, then validate the candidate."""

        def _terminal(outcome: InteractionOutcome) -> InteractionOutcome:
            if on_terminal is not None and outcome.status.value in {
                "blocked",
                "cancelled",
                "failed",
            }:
                on_terminal(outcome)
            return outcome

        def _cancelled_command_outcome(
            result,
            *,
            preserved_state: _InterpretationReviewState | None = None,
        ) -> InteractionOutcome | None:
            error_type = getattr(
                getattr(result, "error_type", None),
                "value",
                getattr(result, "error_type", None),
            )
            if not result.failed or error_type != ErrorType.CANCELLED.value:
                return None
            if loading_token is not None:
                self._close_loading_dialog(loading_token)
            if on_cancelled is not None:
                return _terminal(on_cancelled(preserved_state))
            return _terminal(InteractionOutcome.cancelled(result.message))

        def _handle_async_error(error: tuple, fallback_message: str) -> None:
            message = (
                str(error[1]).strip()
                if len(error) > 1 and str(error[1]).strip()
                else fallback_message
            )
            if loading_token is not None:
                self._show_loading_error(loading_token, message)
                return
            self._bindings.message_box().warning(
                self.panel,
                error_title,
                "The import settings could not be revalidated.\n\n"
                f"{message}\n\nReopen Import EEG Data and review the current settings.",
            )
            _terminal(InteractionOutcome.failed(message))

        scan = dict(review_state.scan)
        scan_id = self._optional_payload_id(scan, "scan_id")
        if scan_id is None:
            message = (
                "The Data Import scan identity is unavailable. Reopen the source "
                "and try again."
            )
            if loading_token is not None:
                self._show_loading_error(loading_token, message)
            else:
                self._bindings.message_box().warning(
                    self.panel, "Import review changed", message
                )
            return _terminal(InteractionOutcome.blocked(message))

        def _handle_validation(
            validation_result,
            *,
            preview: dict[str, Any],
            candidate: dict[str, Any],
            preview_state: _InterpretationReviewState,
        ) -> InteractionOutcome:
            cancelled = _cancelled_command_outcome(
                validation_result,
                preserved_state=preview_state,
            )
            if cancelled is not None:
                return cancelled
            if self._result_failed(
                validation_result,
                "Interpretation validation failed",
                present=loading_token is None,
            ):
                if loading_token is not None:
                    self._show_loading_error(loading_token, validation_result.message)
                return _terminal(
                    self._interaction_failure_outcome(
                        validation_result,
                        validation_result.message,
                    )
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
                if loading_token is not None:
                    self._show_loading_error(loading_token, str(exc))
                else:
                    self._bindings.message_box().warning(
                        self.panel,
                        "Import review changed",
                        str(exc),
                    )
                return _terminal(InteractionOutcome.blocked(str(exc)))
            return on_validated(validated_state)

        def _handle_preview_result(preview_result) -> InteractionOutcome:
            cancelled = _cancelled_command_outcome(preview_result)
            if cancelled is not None:
                return cancelled
            resource_outcome = self._preview_resource_preflight_outcome(
                preview_result,
                retry=lambda token: _dispatch_preview(
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                ),
            )
            if resource_outcome is not None:
                if loading_token is not None:
                    if resource_outcome.status.value == "cancelled":
                        self._close_loading_dialog(loading_token)
                    elif resource_outcome.status.value in {"blocked", "failed"}:
                        self._show_loading_error(
                            loading_token,
                            resource_outcome.message,
                        )
                return _terminal(resource_outcome)
            if self._result_failed(
                preview_result,
                error_title,
                present=loading_token is None,
            ):
                if loading_token is not None:
                    self._show_loading_error(loading_token, preview_result.message)
                return _terminal(
                    self._interaction_failure_outcome(
                        preview_result,
                        preview_result.message,
                    )
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
                if loading_token is not None:
                    self._show_loading_error(loading_token, str(exc))
                else:
                    self._bindings.message_box().warning(
                        self.panel,
                        "Import review changed",
                        str(exc),
                    )
                return _terminal(InteractionOutcome.blocked(str(exc)))
            started = self._execute_interpretation_command_async(
                ValidateInterpretationCommand(candidate_id=candidate_id),
                on_result=lambda result: _handle_validation(
                    result,
                    preview=preview,
                    candidate=candidate,
                    preview_state=preview_state,
                ),
                error_title="Interpretation validation failed",
                expected_publication_generation=(preview_state.publication_generation),
                on_error=lambda error: _handle_async_error(
                    error,
                    "The import preview could not be validated.",
                ),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_VALIDATION
                ),
            )
            if started is not None:
                return _terminal(started)
            message = "Data Interpretation validation service is unavailable."
            self._bindings.message_box().critical(
                self.panel,
                "Interpretation validation unavailable",
                message,
            )
            return _terminal(InteractionOutcome.blocked(message))

        def _dispatch_preview(
            *,
            resource_preflight_confirmed: bool = False,
            resource_preflight_token: str | None = None,
        ) -> InteractionOutcome | None:
            started = self._execute_interpretation_command_async(
                PreviewInterpretationCommand(
                    scan_id=scan_id,
                    choices=choices,
                    resource_preflight_confirmed=resource_preflight_confirmed,
                    resource_preflight_token=resource_preflight_token,
                ),
                on_result=_handle_preview_result,
                error_title=error_title,
                expected_publication_generation=(review_state.publication_generation),
                on_error=lambda error: _handle_async_error(
                    error,
                    "The import preview could not be updated.",
                ),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_PREVIEW
                ),
            )
            return _terminal(started) if started is not None else None

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

        loading_token: object | None = None

        def _open_validated_review(
            validated_state: _InterpretationReviewState,
        ) -> InteractionOutcome:
            if loading_token is None or not self._loading_dialog_is_active(
                loading_token
            ):
                return InteractionOutcome.cancelled(
                    "Data interpretation preview was cancelled."
                )
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=validated_state,
                initial_step=initial_step,
                loading_token=loading_token,
            )

        def _dispatch_preview() -> InteractionOutcome | None:
            if loading_token is not None and self._loading_dialog_is_active(
                loading_token
            ):
                dialog = self._active_loading_dialog
                if dialog is not None:
                    dialog.set_stage(
                        "Updating label matches",
                        "Checking the selected label values and EEG events.",
                    )
            return self._preview_and_validate_interpretation_async(
                choices=choices,
                review_state=review_state,
                on_validated=_open_validated_review,
                error_title="Interpretation preview failed",
                loading_token=loading_token,
            )

        loading_token = self._open_loading_dialog(
            initial_step=initial_step,
            retry=_dispatch_preview,
        )
        return _dispatch_preview()

    def _review_interpretation_for_apply_async(
        self,
        *,
        source_path: str,
        source_hint: str,
        choices: dict[str, Any],
        validated_choices: dict[str, Any],
        label_sources: list[str],
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
    ) -> InteractionOutcome | None:
        """Validate edited choices from the existing scan, then apply."""

        def _replace_preparing_status(outcome: InteractionOutcome) -> None:
            if outcome.status.value == "cancelled":
                self._show_status("Dataset import cancelled")
            elif outcome.status.value == "blocked":
                self._show_status("Dataset import blocked · Review the import settings")
            elif outcome.status.value == "failed":
                self._show_status("Dataset import failed · Review the import settings")

        def _apply_validated_review(
            validated_state: _InterpretationReviewState,
        ) -> InteractionOutcome:
            if str(validated_state.decision.get("decision")) == "blocked":
                outcome = InteractionOutcome.blocked(
                    self._decision_reason(validated_state.decision)
                )
                _replace_preparing_status(outcome)
                return outcome

            def _retry_cancelled_apply() -> InteractionOutcome:
                return self.review_current_import(
                    initial_step="Review and Import",
                    expected_identity=self._review_identity(validated_state),
                )

            return self._apply_interpretation_async(
                validated_state,
                dialog_result,
                retry_cancelled_apply=_retry_cancelled_apply,
            )

        preserved_review_state = review_state

        def _retry_cancelled_revalidation() -> InteractionOutcome:
            return self._continue_data_interpretation_import(
                source_path=source_path,
                source_hint=source_hint,
                choices=dict(choices),
                label_sources=list(label_sources),
                review_state=preserved_review_state,
                initial_step="Review and Import",
                validated_choices=dict(validated_choices),
            )

        def _reopen_cancelled_review(
            preview_state: _InterpretationReviewState | None,
        ) -> InteractionOutcome:
            nonlocal preserved_review_state
            if preview_state is not None:
                preserved_review_state = _InterpretationReviewState(
                    scan=dict(preview_state.scan),
                    preview=dict(preview_state.preview),
                    candidate=dict(preview_state.candidate),
                    candidate_id=preview_state.candidate_id,
                    decision=dict(review_state.decision),
                    publication_generation=preview_state.publication_generation,
                )
            return self._schedule_cancelled_review_reopen(
                _retry_cancelled_revalidation,
                cancelled_message="The operation was cancelled.",
            )

        started = self._preview_and_validate_interpretation_async(
            choices=choices,
            review_state=review_state,
            on_validated=_apply_validated_review,
            error_title="Interpretation preview failed",
            on_terminal=_replace_preparing_status,
            on_cancelled=_reopen_cancelled_review,
        )
        if started is not None:
            return started
        self._show_status("Dataset import failed · Review the import settings")
        return None

    def _schedule_cancelled_review_reopen(
        self,
        retry: Callable[[], InteractionOutcome] | None,
        *,
        cancelled_message: str,
    ) -> InteractionOutcome:
        """Reopen one preserved review after the current Qt callback settles."""
        self._show_status("Dataset import cancelled · Review preserved")
        if retry is None:
            return InteractionOutcome.cancelled(cancelled_message)

        continuation = self._bindings.reserve_interaction_continuation()

        def _resume_cancelled_review() -> None:
            main_window = getattr(self._host, "main_window", None)
            if self._bindings.qt_object_deleted(self.panel) or (
                getattr(main_window, "_closing_in_progress", False) is True
            ):
                if continuation is not None:
                    continuation.fail(
                        "XBrainLab started closing before the preserved dataset "
                        "review could reopen."
                    )
                return
            if continuation is not None:
                continuation.start(retry)
            else:
                retry()

        try:
            self._bindings.single_shot(0, _resume_cancelled_review)
        except Exception:
            logger.exception("Could not reopen cancelled dataset review")
            message = "The preserved dataset review could not be reopened."
            self._show_status("Dataset import failed · Review the import settings")
            if continuation is not None:
                continuation.fail(message)
            return InteractionOutcome.failed(message)
        return InteractionOutcome.accepted(
            "Dataset import was cancelled and the preserved review will reopen."
        )

    def _apply_interpretation_async(
        self,
        review_state: _InterpretationReviewState,
        dialog_result: dict[str, Any],
        *,
        retry_cancelled_apply: Callable[[], InteractionOutcome] | None = None,
    ) -> InteractionOutcome:
        """Apply one reviewed candidate and continue to optional recipe saving."""
        candidate_id = (
            self._optional_payload_id(review_state.decision, "candidate_id")
            or review_state.candidate_id
        )

        def _handle_apply_result(apply_result) -> InteractionOutcome:
            error_type = getattr(
                getattr(apply_result, "error_type", None),
                "value",
                getattr(apply_result, "error_type", None),
            )
            if apply_result.failed and error_type == ErrorType.CANCELLED.value:
                return self._schedule_cancelled_review_reopen(
                    retry_cancelled_apply,
                    cancelled_message=apply_result.message,
                )

            resource_preflight = self._resource_preflight_view(apply_result)
            if apply_result.failed and resource_preflight:
                risk_level = resource_preflight.risk_level
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
                        self._show_status("Dataset import blocked · Retry the import")
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
                        self._show_status("Dataset import cancelled")
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
                        self._show_status(
                            "Dataset import failed · Review the import settings"
                        )
                        if continuation is not None:
                            continuation.fail(message)
                        return InteractionOutcome.failed(message)
                    return InteractionOutcome.accepted(
                        "Confirmed dataset import was scheduled."
                    )
                if risk_level == "blocking":
                    self._show_status("Dataset import blocked · Check available memory")
                    self._bindings.message_box().critical(
                        self.panel,
                        "Dataset Resource Check",
                        resource_preflight.message or apply_result.message,
                    )
                    return InteractionOutcome.blocked(apply_result.message)
            diagnostics = getattr(apply_result, "diagnostics", {})
            state_preserved = (
                isinstance(diagnostics, dict)
                and diagnostics.get("state_preserved") is True
            )
            if (
                apply_result.failed
                and state_preserved
                and not self._bindings.is_stale_publication_result(apply_result)
            ):
                self._bindings.message_box().critical(
                    self.panel,
                    "Interpretation apply failed",
                    apply_result.message + "\n\nExisting data was preserved.",
                )
                self._show_status("Dataset import failed · Existing data preserved")
                return self._interaction_failure_outcome(
                    apply_result,
                    apply_result.message,
                )
            if self._result_failed(apply_result, "Interpretation apply failed"):
                self._show_status("Dataset import failed · Review the import settings")
                return self._interaction_failure_outcome(
                    apply_result,
                    apply_result.message,
                )

            self._show_status(apply_result.message)

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
            apply_command = ApplyInterpretationCommand(
                candidate_id=candidate_id,
                confirmed=dialog_result.get("confirmed") is True,
                resource_preflight_confirmed=resource_preflight_confirmed,
                resource_preflight_token=resource_preflight_token,
            )

            def _handle_apply_error(error: tuple) -> None:
                self._show_status("Dataset import failed · Review the import settings")
                self._bindings.present_unexpected_error(
                    self.panel,
                    UnexpectedErrorContext.DATA_INTERPRETATION_APPLY,
                    error_info=error,
                    message_box=self._bindings.message_box(),
                    title="Interpretation apply failed",
                )

            started = self._execute_interpretation_command_async(
                apply_command,
                on_result=_handle_apply_result,
                error_title="Interpretation apply failed",
                on_error=_handle_apply_error,
                expected_publication_generation=(review_state.publication_generation),
                unexpected_error_context=(
                    UnexpectedErrorContext.DATA_INTERPRETATION_APPLY
                ),
            )
            if started is not None:
                return started
            self._show_status("Dataset import failed · Review the import settings")
            return InteractionOutcome.blocked(
                "Data interpretation apply could not be started."
            )

        return _dispatch_apply()

    @staticmethod
    def _review_identity(
        review_state: _InterpretationReviewState,
    ) -> InterpretationReviewIdentity:
        publication_generation = review_state.publication_generation
        scan_id = str(review_state.scan.get("scan_id") or "").strip()
        candidate_id = str(review_state.candidate_id or "").strip()
        if (
            type(publication_generation) is not int
            or publication_generation < 0
            or not scan_id
            or not candidate_id
        ):
            raise PreconditionError(
                "The preserved Data Import review identity is incomplete. "
                "Review the current import again."
            )
        return InterpretationReviewIdentity(
            publication_generation=publication_generation,
            scan_id=scan_id,
            candidate_id=candidate_id,
        )

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

    def _result_failed(self, result, title: str, *, present: bool = True) -> bool:
        if not result.failed:
            return False
        if not present:
            return True
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
