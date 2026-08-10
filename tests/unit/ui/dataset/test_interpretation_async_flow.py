"""Lifecycle tests for non-blocking Data Interpretation command continuations."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, call

from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ApplySmartParseCommand,
    ChangedState,
    CommandResult,
    ErrorType,
    LabelImportPlan,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
)
from XBrainLab.backend.application.capabilities import (
    CommandCapability,
    build_capability_policy,
)
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    InterpretationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.backend.services.dataset_state_service import DatasetStateService
from XBrainLab.backend.study import Study
from XBrainLab.ui import application_capabilities, async_command_runner
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionSession,
    InteractionCompletionStatus,
    InteractionOutcome,
    InteractionStatus,
    bind_interaction_completion,
)
from XBrainLab.ui.panels.dataset import actions
from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler
from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
    DataInterpretationActionCoordinator,
    _InterpretationReviewState,
)


class _InterpretationReviewRuntime:
    def __init__(
        self,
        publication: ApplicationViewPublication,
        review: dict[str, Any],
    ) -> None:
        self.publication = publication
        self.review = review
        self.view_reads = 0
        self.review_reads = 0

    def get_view_publication(self) -> ApplicationViewPublication:
        self.view_reads += 1
        return self.publication

    def get_interpretation_review(
        self,
        *,
        expected_identity: InterpretationReviewIdentity | None = None,
    ) -> dict[str, Any]:
        self.review_reads += 1
        if expected_identity is not None:
            assert (
                expected_identity.publication_generation == self.publication.generation
            )
        return self.review


def test_label_configuration_merge_replaces_mutually_exclusive_source_state():
    base = {
        "skip_labels": True,
        "label_carrier": "embedded_events",
        "class_map": {"1": "external-left"},
        "event_roles": {"1": "class label"},
        "internal_event_selection": {"selected_codes": ["1"]},
        "run_event_mappings": {"A01T.gdf": {"1": "left"}},
        "excluded_label_carriers": ["/labels/A01T.mat"],
        "label_carrier_choices": {"/labels/A01T.mat": {"label_field": "classlabel"}},
        "label_carrier_remap": {"/old/A01T.mat": "/labels/A01T.mat"},
        "required_label_carriers": ["/old/A01T.mat"],
        "metadata_overrides": {"A01T.gdf": {"subject": "01"}},
    }

    merged = DataInterpretationActionCoordinator._merge_interpretation_choices(
        base,
        {"label_carrier_choices": {"/labels/A01T.mat": {"label_field": "classlabel"}}},
    )

    assert merged["metadata_overrides"] == base["metadata_overrides"]
    assert merged["required_label_carriers"] == ["/old/A01T.mat"]
    assert merged["label_carrier_choices"] == {
        "/labels/A01T.mat": {"label_field": "classlabel"}
    }
    for stale_key in (
        "skip_labels",
        "label_carrier",
        "class_map",
        "event_roles",
        "internal_event_selection",
        "run_event_mappings",
        "excluded_label_carriers",
        "label_carrier_remap",
    ):
        assert stale_key not in merged


def test_label_configuration_merge_preserves_reviewed_external_choices_when_unchanged():
    reviewed_choices = {
        "/bids/sub-01_task-p300_events.tsv": {
            "label_field": "value",
            "anchor": "onset",
            "placement_method": "time_field",
            "value_decisions": {
                "standard": {
                    "role": "stimulus",
                    "keep_event": True,
                    "use_as_class": True,
                    "class_name": "standard",
                }
            },
        }
    }
    merged = DataInterpretationActionCoordinator._merge_interpretation_choices(
        {
            "selected_eeg_files": ["/bids/sub-01_task-p300_eeg.set"],
            "label_carrier_choices": reviewed_choices,
        },
        {"metadata_overrides": {"sub-01_task-p300_eeg.set": {"task": "p300"}}},
    )

    assert merged["label_carrier_choices"] == reviewed_choices
    assert merged["metadata_overrides"] == {
        "sub-01_task-p300_eeg.set": {"task": "p300"}
    }


def test_label_configuration_merge_clears_external_state_for_embedded_events():
    merged = DataInterpretationActionCoordinator._merge_interpretation_choices(
        {
            "label_carrier_choices": {
                "/labels/A01T.mat": {"label_field": "classlabel"}
            },
            "label_carrier_remap": {"/old/A01T.mat": "/labels/A01T.mat"},
            "required_label_carriers": ["/old/A01T.mat"],
            "excluded_label_carriers": ["/labels/rejected.mat"],
        },
        {
            "label_carrier": "embedded_events",
            "class_map": {"769": "left hand"},
        },
    )

    assert merged == {
        "label_carrier": "embedded_events",
        "class_map": {"769": "left hand"},
    }


def test_label_source_change_invalidates_decisions_from_previous_carrier_set():
    choices = DataInterpretationActionCoordinator._choices_after_label_source_change(
        {
            "selected_eeg_files": ["/eeg/A01T.gdf"],
            "metadata_overrides": {"A01T.gdf": {"subject": "01"}},
            "excluded_label_carriers": ["/labels/rejected.mat"],
            "label_carrier": "embedded_events",
            "internal_event_selection": {"selected_codes": ["769"]},
            "run_event_mappings": {"A01T.gdf": {"769": "left"}},
            "class_map": {"769": "left"},
            "event_roles": {"769": "class label"},
            "required_label_carriers": ["/labels/old.mat"],
            "label_carrier_choices": {"/labels/old.mat": {"label_field": "classlabel"}},
            "label_carrier_remap": {"/labels/old.mat": "/labels/new.mat"},
        }
    )

    assert choices == {
        "selected_eeg_files": ["/eeg/A01T.gdf"],
        "metadata_overrides": {"A01T.gdf": {"subject": "01"}},
        "excluded_label_carriers": ["/labels/rejected.mat"],
    }


def _review_publication(
    *,
    generation: int = 9,
    scan_id: str = "scan-1",
    candidate_id: str = "candidate-2",
) -> ApplicationViewPublication:
    state = replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            has_scan_result=True,
            has_candidate=True,
            has_preview=True,
            has_validation_decision=True,
            latest_scan_id=scan_id,
            latest_candidate_id=candidate_id,
        ),
    )
    return ApplicationViewPublication(
        generation=generation,
        state=state,
        capabilities=build_capability_policy(state),
    )


def test_review_current_import_reopens_published_candidate_at_requested_step(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    publication = {
        "source_path": "/data/sub-01_task-mi_eeg.edf",
        "source_hint": "file",
        "label_sources": ["/labels/sub-01_events.tsv"],
        "choices": {"label_carrier": "/labels/sub-01_events.tsv"},
        "scan_result": {"scan_id": "scan-1"},
        "candidate": {"candidate_id": "candidate-2"},
        "preview": {"preview_id": "preview-3"},
        "validation_decision": {
            "candidate_id": "candidate-2",
            "decision": "needs_confirmation",
        },
    }
    runtime = _InterpretationReviewRuntime(_review_publication(), publication)
    monkeypatch.setattr(actions, "application_ui_runtime", lambda _panel: runtime)
    continue_review = MagicMock(return_value=InteractionOutcome.completed("Applied."))
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_review,
    )

    outcome = handler.review_current_import(initial_step="Match Labels")

    assert outcome.status is InteractionStatus.COMPLETED
    continue_review.assert_called_once()
    kwargs = continue_review.call_args.kwargs
    assert kwargs["source_path"] == publication["source_path"]
    assert kwargs["source_hint"] == publication["source_hint"]
    assert kwargs["choices"] == publication["choices"]
    assert kwargs["label_sources"] == publication["label_sources"]
    assert kwargs["initial_step"] == "Match Labels"
    assert kwargs["review_state"] == _InterpretationReviewState(
        scan=publication["scan_result"],
        preview=publication["preview"],
        candidate=publication["candidate"],
        candidate_id="candidate-2",
        decision=publication["validation_decision"],
        publication_generation=9,
    )


def test_review_current_import_opens_identity_checked_runtime_publication(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    publication = {
        "source_path": "/data/sub-01_task-mi_eeg.edf",
        "source_hint": "file",
        "label_sources": ["/labels/sub-01_events.tsv"],
        "choices": {},
        "scan_result": {"scan_id": "scan-1"},
        "candidate": {"candidate_id": "candidate-2"},
        "preview": {"preview_id": "preview-3"},
        "validation_decision": {
            "candidate_id": "candidate-2",
            "decision": "safe",
        },
    }
    runtime = _InterpretationReviewRuntime(_review_publication(), publication)
    monkeypatch.setattr(actions, "application_ui_runtime", lambda _panel: runtime)
    continue_review = MagicMock(return_value=InteractionOutcome.completed("Applied."))
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_review,
    )
    identity = InterpretationReviewIdentity(
        publication_generation=9,
        scan_id="scan-1",
        candidate_id="candidate-2",
    )

    outcome = handler.review_current_import(
        initial_step="Match Labels",
        expected_identity=identity,
    )

    assert outcome.status is InteractionStatus.COMPLETED
    assert runtime.view_reads == 2
    assert runtime.review_reads == 1
    continue_review.assert_called_once()
    assert (
        continue_review.call_args.kwargs["review_state"].publication_generation
        == identity.publication_generation
    )


def test_review_current_import_identity_mismatch_fails_closed(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    runtime = _InterpretationReviewRuntime(
        _review_publication(generation=10, candidate_id="candidate-new"),
        {
            "scan_result": {"scan_id": "scan-1"},
            "candidate": {"candidate_id": "candidate-new"},
        },
    )
    monkeypatch.setattr(actions, "application_ui_runtime", lambda _panel: runtime)
    warning = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)
    continue_review = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_review,
    )

    outcome = handler.review_current_import(
        expected_identity=InterpretationReviewIdentity(
            publication_generation=9,
            scan_id="scan-1",
            candidate_id="candidate-2",
        )
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert "changed" in outcome.message.lower()
    assert runtime.review_reads == 0
    continue_review.assert_not_called()
    warning.assert_called_once()


def test_review_current_import_rejects_identity_change_during_read(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    matching = _review_publication()
    changed = _review_publication(generation=10, candidate_id="candidate-new")
    review = {
        "source_path": "/data/sub-01_task-mi_eeg.edf",
        "scan_result": {"scan_id": "scan-1"},
        "candidate": {"candidate_id": "candidate-2"},
        "preview": {},
        "validation_decision": {},
    }

    class _ChangingRuntime(_InterpretationReviewRuntime):
        def get_view_publication(self) -> ApplicationViewPublication:
            self.view_reads += 1
            return matching if self.view_reads == 1 else changed

    runtime = _ChangingRuntime(matching, review)
    monkeypatch.setattr(actions, "application_ui_runtime", lambda _panel: runtime)
    monkeypatch.setattr(actions.QMessageBox, "warning", MagicMock())
    continue_review = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_review,
    )

    outcome = handler.review_current_import(
        expected_identity=InterpretationReviewIdentity(
            publication_generation=9,
            scan_id="scan-1",
            candidate_id="candidate-2",
        )
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert runtime.view_reads == 2
    assert runtime.review_reads == 1
    continue_review.assert_not_called()


def test_review_current_import_without_runtime_fails_closed(monkeypatch) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    monkeypatch.setattr(actions, "application_ui_runtime", lambda _panel: None)
    warning = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)
    continue_review = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_review,
    )

    outcome = handler.review_current_import(
        expected_identity=InterpretationReviewIdentity(
            publication_generation=9,
            scan_id="scan-1",
            candidate_id="candidate-2",
        )
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert "unavailable" in outcome.message.lower()
    continue_review.assert_not_called()
    warning.assert_called_once()


def _success_result(command_name: str, **diagnostics: Any) -> CommandResult:
    return CommandResult.success_result(
        command_name=command_name,
        message="ok",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        diagnostics=diagnostics,
    )


def _resource_confirmation_result(token: str) -> CommandResult:
    message = "Estimated RAM requires confirmation."
    return CommandResult.failure_result(
        command_name="apply_interpretation",
        message=message,
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.CONFIRMATION_REQUIRED,
        recoverable=True,
        diagnostics={
            "resource_preflight": {
                "schema_version": 1,
                "risk_level": "warning",
                "requires_confirmation": True,
                "message": message,
                "confirmation_challenge": {
                    "schema_version": 1,
                    "challenge_id": token,
                    "command_name": "apply_interpretation",
                    "scope_fingerprint": "scope-1",
                    "ttl_seconds": 120.0,
                    "candidate_id": "candidate-1",
                    "configuration_fingerprint": None,
                    "preflight_fingerprint": "preflight-1",
                },
            },
        },
    )


def _resource_blocking_result(
    command_name: str = "apply_interpretation",
) -> CommandResult:
    message = "Dataset is too large to load safely."
    return CommandResult.failure_result(
        command_name=command_name,
        message=message,
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={
            "resource_preflight": {
                "risk_level": "blocking",
                "requires_confirmation": False,
                "message": message,
            },
        },
    )


def _review_resource_confirmation_result(
    challenge_id: str = "review-receipt-1",
    *,
    command_name: str = "review_interpretation",
    challenge_command_name: str | None = None,
) -> CommandResult:
    message = "External label preview may use substantial RAM."
    return CommandResult.failure_result(
        command_name=command_name,
        message=message,
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.CONFIRMATION_REQUIRED,
        recoverable=True,
        diagnostics={
            "resource_preflight": {
                "risk_level": "warning",
                "requires_confirmation": True,
                "message": message,
                "confirmation_challenge": {
                    "schema_version": 1,
                    "challenge_id": challenge_id,
                    "command_name": challenge_command_name or command_name,
                    "scope_fingerprint": "scope-1",
                    "ttl_seconds": 120.0,
                    "candidate_id": None,
                    "configuration_fingerprint": "configuration-1",
                    "preflight_fingerprint": "preflight-1",
                },
            },
        },
    )


def _resource_confirmation_without_challenge_result(
    command_name: str,
) -> CommandResult:
    message = "External label preview may use substantial RAM."
    return CommandResult.failure_result(
        command_name=command_name,
        message=message,
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.CONFIRMATION_REQUIRED,
        recoverable=True,
        diagnostics={
            "resource_preflight": {
                "schema_version": 1,
                "risk_level": "warning",
                "requires_confirmation": True,
                "message": message,
            },
        },
    )


def _review_state(
    *,
    publication_generation: int | None = None,
) -> _InterpretationReviewState:
    return _InterpretationReviewState(
        scan={"scan_id": "scan-1"},
        preview={},
        candidate={"candidate_id": "candidate-1"},
        candidate_id="candidate-1",
        decision={"candidate_id": "candidate-1", "decision": "safe"},
        publication_generation=publication_generation,
    )


def test_label_field_repreview_reopens_match_labels_instead_of_applying(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    revised_choices = {
        "label_carrier_choices": {"/data/sub-01_events.tsv": {"label_field": "value"}}
    }

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {
                "confirmed": False,
                "choices": revised_choices,
                "resume_step": "Match Labels",
            }

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    repreview = MagicMock(
        return_value=InteractionOutcome.accepted("Preview refresh scheduled.")
    )
    apply_review = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation, "_repreview_interpretation_async", repreview
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_review_interpretation_for_apply_async",
        apply_review,
    )
    review_state = _review_state()

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=review_state,
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    repreview.assert_called_once_with(
        source_path="/data",
        source_hint="bids",
        choices=revised_choices,
        label_sources=[],
        review_state=review_state,
        initial_step="Match Labels",
    )
    apply_review.assert_not_called()


def test_blocked_review_closes_without_a_second_error_dialog(monkeypatch) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": False, "choices": {}}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)
    review_state = replace(
        _review_state(),
        decision={
            "candidate_id": "candidate-1",
            "decision": "blocked",
            "blocked_reasons": ["EEG data has not been selected."],
        },
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="file",
        choices={},
        label_sources=[],
        review_state=review_state,
    )

    assert outcome.status is InteractionStatus.BLOCKED
    critical.assert_not_called()


def test_choice_repreview_uses_existing_scan_without_rescanning(monkeypatch) -> None:
    handler = DatasetActionHandler(MagicMock())
    loading = MagicMock()
    loading.cancelled_by_user = False
    handler._data_interpretation._loading_dialog_class = lambda: (
        lambda *_args, **_kwargs: loading
    )
    execute = MagicMock(
        return_value=InteractionOutcome.accepted("Preview refresh scheduled.")
    )
    monkeypatch.setattr(
        handler._data_interpretation, "_execute_interpretation_command_async", execute
    )

    outcome = handler._data_interpretation._repreview_interpretation_async(
        source_path="/data",
        source_hint="bids",
        choices={"label_carrier_choices": {}},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
        initial_step="Match Labels",
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    command = execute.call_args.args[0]
    assert isinstance(command, PreviewInterpretationCommand)
    assert command.scan_id == "scan-1"
    assert command.choices == {"label_carrier_choices": {}}
    assert execute.call_args.kwargs["expected_publication_generation"] == 17


def test_apply_uses_the_generation_reviewed_by_the_user(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    observed_generations: list[int | None] = []

    class _Service:
        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
        ):
            assert isinstance(command, ApplyInterpretationCommand)
            observed_generations.append(expected_publication_generation)
            return _success_result(
                "apply_interpretation",
                applied_interpretation={},
            )

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: observed_generations == [17], timeout=1000)


def test_apply_shows_loading_status_before_dataset_payload_is_loaded(monkeypatch):
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    statuses: list[tuple[str, int]] = []
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )
    execute = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    monkeypatch.setattr(
        handler._data_interpretation,
        "_execute_interpretation_command_async",
        execute,
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert statuses == [("Importing EEG data and labels...", 900_000)]

    on_result = execute.call_args.kwargs["on_result"]
    completed = _success_result(
        "apply_interpretation",
        applied_interpretation={},
        success_count=6,
    )
    on_result(completed)

    assert statuses[-1] == (completed.message, 7000)


def test_apply_replaces_loading_status_when_the_worker_fails(monkeypatch):
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    statuses: list[tuple[str, int]] = []
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )
    execute = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    monkeypatch.setattr(
        handler._data_interpretation,
        "_execute_interpretation_command_async",
        execute,
    )
    present_error = MagicMock()
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        present_unexpected_error=present_error,
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(),
        {"confirmed": True, "save_recipe": False},
    )
    error = (RuntimeError, RuntimeError("worker failed"), None)
    execute.call_args.kwargs["on_error"](error)

    assert outcome.status is InteractionStatus.ACCEPTED
    assert statuses == [
        ("Importing EEG data and labels...", 900_000),
        ("Dataset import failed · Review the import settings", 7000),
    ]
    assert present_error.call_args.kwargs["error_info"] == error


def test_smart_parse_binds_the_generation_reviewed_before_the_dialog(
    monkeypatch,
) -> None:
    panel = MagicMock()
    panel.controller = None
    handler = DatasetActionHandler(panel)
    capability = CommandCapability(
        command_name="apply_smart_parse",
        enabled=True,
    )
    review_context = CommandReviewContext(
        capability=capability,
        publication_generation=41,
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: review_context,
    )
    monkeypatch.setattr(
        actions,
        "get_command_capability",
        lambda *_args, **_kwargs: capability,
    )
    observed_filename_generations: list[int | None] = []

    def _filenames(
        *,
        expected_publication_generation: int | None = None,
    ) -> list[str]:
        observed_filename_generations.append(expected_publication_generation)
        return ["sub-01_task-mi_eeg.edf"]

    monkeypatch.setattr(handler, "_smart_parse_filenames", _filenames)
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_result.return_value = {
        "sub-01_task-mi_eeg.edf": ("01", "01"),
    }
    monkeypatch.setattr(actions, "SmartParserDialog", MagicMock(return_value=dialog))
    observed_apply_generations: list[int | None] = []

    def _execute(_panel, _command, **kwargs):
        observed_apply_generations.append(kwargs.get("expected_publication_generation"))
        return _success_result("apply_smart_parse", success_count=1)

    monkeypatch.setattr(actions, "execute_application_command", _execute)

    handler.open_smart_parser()

    assert observed_filename_generations == [41]
    assert observed_apply_generations == [41]


def test_smart_parse_reads_full_paths_from_generation_bound_data_lists(
    monkeypatch,
) -> None:
    panel = MagicMock()
    panel.controller = None
    handler = DatasetActionHandler(panel)
    observed_commands: list[tuple[object, int | None]] = []

    def _execute(_panel, command, **kwargs):
        observed_commands.append(
            (command, kwargs.get("expected_publication_generation")),
        )
        return _success_result(
            "query_state",
            raw_rows=[
                {
                    "filepath": "/data/sub-01_task-mi_run-01_raw.fif",
                    "filename": "sub-01_task-mi_run-01_raw.fif",
                },
                {
                    "filepath": "/data/sub-02_task-mi_run-01_raw.fif",
                    "filename": "sub-02_task-mi_run-01_raw.fif",
                },
            ],
        )

    monkeypatch.setattr(actions, "execute_application_command", _execute)

    result = handler._smart_parse_filenames(
        expected_publication_generation=43,
    )

    assert result == [
        "/data/sub-01_task-mi_run-01_raw.fif",
        "/data/sub-02_task-mi_run-01_raw.fif",
    ]
    assert len(observed_commands) == 1
    command, generation = observed_commands[0]
    assert isinstance(command, QueryStateCommand)
    assert command.query == "data_lists"
    assert generation == 43


def test_smart_parse_distinguishes_same_basename_across_directories_through_apply(
    monkeypatch,
) -> None:
    class MetadataRow:
        def __init__(self, filepath: str) -> None:
            self.filepath = filepath
            self.subject = "old"
            self.session = "old"

        def get_filepath(self) -> str:
            return self.filepath

        def set_subject_name(self, value: str) -> None:
            self.subject = value

        def set_session_name(self, value: str) -> None:
            self.session = value

    class MetadataStudy:
        def __init__(self, rows: list[MetadataRow]) -> None:
            self.loaded_data_list = rows
            self.preprocessed_data_list = list(rows)

        def reset_preprocess(self, *, force_update: bool) -> None:
            assert force_update is True
            self.preprocessed_data_list = list(self.loaded_data_list)

    paths = (
        "/datasets/site-a/sub-01/eeg.edf",
        "/datasets/site-b/sub-01/eeg.edf",
    )
    study = MetadataStudy([MetadataRow(path) for path in paths])
    state = DatasetStateService(study)
    panel = MagicMock()
    panel.controller = None
    handler = DatasetActionHandler(panel)
    capability = CommandCapability(
        command_name="apply_smart_parse",
        enabled=True,
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: CommandReviewContext(
            capability=capability,
            publication_generation=47,
        ),
    )
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_result.return_value = {
        paths[0]: ("site-a", "session-a"),
        paths[1]: ("site-b", "session-b"),
    }
    dialog_factory = MagicMock(return_value=dialog)
    monkeypatch.setattr(actions, "SmartParserDialog", dialog_factory)

    def _execute(_panel, command, **kwargs):
        assert kwargs.get("expected_publication_generation") == 47
        if isinstance(command, QueryStateCommand):
            return _success_result(
                "query_state",
                raw_rows=[{"filepath": path} for path in paths],
            )
        assert isinstance(command, ApplySmartParseCommand)
        return _success_result(
            "apply_smart_parse",
            success_count=state.apply_smart_parse(command.results),
        )

    monkeypatch.setattr(actions, "execute_application_command", _execute)

    handler.open_smart_parser()

    dialog_factory.assert_called_once_with(list(paths), panel)
    assert [(row.subject, row.session) for row in study.loaded_data_list] == [
        ("site-a", "session-a"),
        ("site-b", "session-b"),
    ]


def test_label_import_binds_the_generation_reviewed_before_the_dialog(
    monkeypatch,
) -> None:
    panel = MagicMock()
    panel.controller = MagicMock()
    handler = DatasetActionHandler(panel)
    capability = CommandCapability(
        command_name="import_labels",
        enabled=True,
    )
    review_context = CommandReviewContext(
        capability=capability,
        publication_generation=52,
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: review_context,
    )
    monkeypatch.setattr(
        actions,
        "get_command_capability",
        lambda *_args, **_kwargs: capability,
    )
    target = MagicMock()
    target.get_filepath.return_value = "/data/sub-01_task-mi_eeg.edf"
    monkeypatch.setattr(
        handler._external_label_import,
        "get_target_files_for_import",
        lambda: [target],
    )
    selection = MagicMock()
    selection.mode = "timestamp"
    selection.target_count = 2
    selection.label_paths = ("/labels/sub-01_events.tsv",)
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_result.return_value = (selection, {"trial_type": "label"})
    dialog_factory = MagicMock(return_value=dialog)
    monkeypatch.setattr(actions, "ImportLabelDialog", dialog_factory)
    plan = LabelImportPlan(
        target_indices=[0],
        label_paths=["/labels/sub-01_events.tsv"],
    )
    monkeypatch.setattr(
        handler._external_label_import,
        "build_label_import_plan",
        lambda *_a, **_k: plan,
    )
    execute = MagicMock()
    monkeypatch.setattr(
        handler._external_label_import,
        "execute_label_import_async",
        execute,
    )

    handler.import_label()

    dialog_factory.assert_called_once_with(
        panel,
        target_files=[target],
        expected_publication_generation=52,
    )
    execute.assert_called_once_with(
        plan,
        expected_publication_generation=52,
    )


def test_label_import_real_runtime_fails_closed_without_second_publication_read(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    warning = MagicMock()
    dialog_factory = MagicMock()
    capability_read = MagicMock(
        side_effect=AssertionError("must not read a second publication")
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(actions, "has_real_application_context", lambda _panel: True)
    monkeypatch.setattr(actions, "get_command_capability", capability_read)
    monkeypatch.setattr(actions, "ImportLabelDialog", dialog_factory)
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)

    handler.import_label()

    capability_read.assert_not_called()
    dialog_factory.assert_not_called()
    warning.assert_called_once()
    assert warning.call_args.args[1] == "Label Import Blocked"


def test_recipe_save_uses_generation_reviewed_before_question(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    current_generation = {"value": 31}
    capability = CommandCapability(
        command_name="save_interpretation_recipe",
        enabled=True,
    )
    observed_generations: list[int | None] = []
    warnings: list[tuple[Any, ...]] = []

    def review_context(*_args, **_kwargs):
        return CommandReviewContext(
            capability=capability,
            publication_generation=current_generation["value"],
        )

    def question(*_args, **_kwargs):
        current_generation["value"] = 32
        return actions.QMessageBox.StandardButton.Yes

    def execute_async(
        _command,
        *,
        on_result,
        expected_publication_generation=None,
        **_kwargs,
    ):
        observed_generations.append(expected_publication_generation)
        on_result(
            SimpleNamespace(
                failed=True,
                recoverable=True,
                message="The reviewed recipe changed.",
                diagnostics={"stale_publication": True},
            )
        )
        return InteractionOutcome.accepted("Recipe save scheduled.")

    monkeypatch.setattr(actions, "get_command_review_context", review_context)
    monkeypatch.setattr(
        handler._data_interpretation, "_recipe_save_block_reason", lambda: None
    )
    monkeypatch.setattr(actions.QMessageBox, "question", question)
    monkeypatch.setattr(
        actions.QMessageBox,
        "warning",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: ("/tmp/import_recipe.json", ""),
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_execute_interpretation_command_async",
        execute_async,
    )

    message = handler._offer_label_recipe_save(
        SimpleNamespace(diagnostics={"recipe_updated": True})
    )

    assert message is None
    assert observed_generations == [31]
    assert warnings
    assert warnings[0][1] == "Review Recipe Save Again"


def test_real_study_command_returns_immediately_and_continues_on_result(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    busy_states: list[bool] = []
    cast(Any, panel).set_busy = lambda busy: busy_states.append(bool(busy))
    handler = DatasetActionHandler(panel)
    worker_started = threading.Event()
    worker_release = threading.Event()
    worker_threads: list[int] = []
    results: list[CommandResult] = []
    heartbeat: list[bool] = []
    expected = _success_result("query_state")

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            worker_threads.append(threading.get_ident())
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return expected

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )

    started_at = time.monotonic()
    started = handler._data_interpretation._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=results.append,
        error_title="Review failed",
    )
    elapsed = time.monotonic() - started_at

    assert started is not None
    assert started.status is InteractionStatus.ACCEPTED
    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    assert results == []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: results == [expected], timeout=1000)

    assert worker_threads != [threading.get_ident()]
    assert busy_states == [True, False]
    assert application_command_registry().active_count(panel) == 0


def test_compatibility_context_continues_synchronously(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    handler = DatasetActionHandler(panel)
    expected = _success_result("query_state")
    results = []

    monkeypatch.setattr(
        actions,
        "execute_application_command",
        lambda _panel, command, **_kwargs: expected
        if isinstance(command, QueryStateCommand)
        else None,
    )

    started = handler._data_interpretation._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=results.append,
        error_title="Review failed",
    )

    assert started is not None
    assert started.status is InteractionStatus.COMPLETED
    assert results == [expected]


def test_worker_exception_cleans_up_and_reports_without_nested_wait(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = MagicMock()
    handler = DatasetActionHandler(panel)

    class _Service:
        def execute(self, _command):
            raise RuntimeError("scan failed")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)

    outcome = handler._data_interpretation._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=MagicMock(),
        error_title="Review failed",
    )
    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED

    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=1000)
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=1000,
    )
    assert critical.call_args.args[2] == (
        "XBrainLab could not prepare the Data Import review. "
        "Reopen the source and try again."
    )
    assert "scan failed" not in critical.call_args.args[2]
    assert cast(Any, panel).set_busy.call_args_list == [((True,),), ((False,),)]


def test_save_recipe_returns_before_worker_and_completes_via_callback(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    worker_started = threading.Event()
    worker_release = threading.Event()
    completions: list[str] = []
    heartbeat: list[bool] = []
    expected = _success_result("save_interpretation_recipe")

    class _Service:
        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
        ):
            assert isinstance(command, SaveInterpretationRecipeCommand)
            assert expected_publication_generation == 13
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return expected

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: CommandReviewContext(
            capability=CommandCapability(
                command_name="save_interpretation_recipe",
                enabled=True,
            ),
            publication_generation=13,
        ),
    )
    monkeypatch.setattr(
        handler._data_interpretation, "_recipe_save_block_reason", lambda: None
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getSaveFileName",
        lambda *_args: ("/tmp/import_recipe.json", ""),
    )

    started_at = time.monotonic()
    started = handler._data_interpretation._save_interpretation_recipe(
        on_complete=completions.append
    )
    elapsed = time.monotonic() - started_at

    assert started is True
    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    assert completions == []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: completions == ["Recipe saved."], timeout=1000)


def test_review_flow_uses_slow_worker_without_blocking_gui(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    loading_dialogs: list[Any] = []

    class _LoadingDialog:
        def __init__(self, _parent, *, initial_step=""):
            self.initial_step = initial_step
            self.visible = False
            self.closed = False
            self.cancelled_by_user = False
            self.rejected = SimpleNamespace(connect=lambda _callback: None)
            self.retry_requested = SimpleNamespace(connect=lambda _callback: None)
            loading_dialogs.append(self)

        def show(self):
            self.visible = True

        def close(self):
            self.visible = False
            self.closed = True

        def accept(self):
            self.visible = False
            self.closed = True

        def deleteLater(self):
            return None

        def set_stage(self, _title, _detail):
            return None

        def show_error(self, _message, *, retry_available=True):
            return None

    handler = DatasetActionHandler(panel)
    handler._data_interpretation._loading_dialog_class = lambda: _LoadingDialog
    statuses: list[str] = []
    monkeypatch.setattr(handler, "_show_status", statuses.append)
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )
    worker_started = threading.Event()
    worker_release = threading.Event()
    heartbeat: list[bool] = []
    result = _success_result(
        "review_interpretation",
        scan_result={"scan_id": "scan-1"},
        preview={"summary": "ready"},
        candidate={"candidate_id": "candidate-1"},
        validation_decision={"candidate_id": "candidate-1", "decision": "safe"},
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

        def get_view_publication(self):
            return _review_publication(candidate_id="candidate-1")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )

    started_at = time.monotonic()
    started = handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )
    elapsed = time.monotonic() - started_at

    assert started is not None
    assert started.status is InteractionStatus.ACCEPTED
    assert statuses == ["Preparing import review..."]
    assert elapsed < 0.1
    assert len(loading_dialogs) == 1
    assert loading_dialogs[0].visible is True
    assert worker_started.wait(timeout=1.0)
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: continue_flow.call_count == 1, timeout=1000)
    assert loading_dialogs[0].closed is True
    assert statuses == ["Preparing import review...", "Import review ready."]


def test_loading_dialog_is_not_disabled_with_the_busy_dataset_panel(qtbot):
    top_level = QWidget()
    panel = QWidget(top_level)
    qtbot.addWidget(top_level)
    top_level.show()
    handler = DatasetActionHandler(panel)

    token = handler._data_interpretation._open_loading_dialog(
        initial_step="",
        retry=lambda: None,
    )
    dialog = handler._data_interpretation._active_loading_dialog
    panel.setEnabled(False)

    assert handler._data_interpretation._loading_dialog_is_active(token)
    assert dialog.parentWidget() is top_level
    assert dialog.isEnabled()
    assert dialog.cancel_button.isEnabled()

    handler._data_interpretation._close_loading_dialog(token)


def test_cancelled_review_loading_does_not_reopen_wizard(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )
    worker_started = threading.Event()
    worker_release = threading.Event()
    result = _success_result(
        "review_interpretation",
        scan_result={"scan_id": "scan-1"},
        preview={"summary": "ready"},
        candidate={"candidate_id": "candidate-1"},
        validation_decision={"candidate_id": "candidate-1", "decision": "safe"},
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

        def get_view_publication(self):
            return _review_publication(candidate_id="candidate-1")

    class _Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def emit(self):
            if self.callback is not None:
                self.callback()

    class _LoadingDialog:
        def __init__(self, _parent, *, initial_step=""):
            self.initial_step = initial_step
            self.cancelled_by_user = False
            self.rejected = _Signal()
            self.retry_requested = _Signal()

        def show(self):
            return None

        def close(self):
            return None

        def accept(self):
            return None

        def deleteLater(self):
            return None

        def set_stage(self, _title, _detail):
            return None

        def show_error(self, _message, *, retry_available=True):
            return None

    handler._data_interpretation._loading_dialog_class = lambda: _LoadingDialog
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )

    outcome = handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )

    assert outcome is not None
    assert worker_started.wait(timeout=1.0)
    loading = handler._data_interpretation._active_loading_dialog
    loading.cancelled_by_user = True
    loading.rejected.emit()
    worker_release.set()
    qtbot.waitUntil(lambda: not worker_release.is_set() or True, timeout=100)
    qtbot.wait(100)
    assert continue_flow.call_count == 0


def test_review_warning_confirmation_retries_before_opening_preview(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )
    commands: list[ReviewInterpretationCommand] = []
    expected_receipt = "review-receipt-1"
    success = _success_result(
        "review_interpretation",
        scan_result={"scan_id": "scan-1"},
        preview={"summary": "ready"},
        candidate={"candidate_id": "candidate-1"},
        validation_decision={"candidate_id": "candidate-1", "decision": "safe"},
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            commands.append(command)
            return (
                _review_resource_confirmation_result(expected_receipt)
                if len(commands) == 1
                else success
            )

        def get_view_publication(self):
            return _review_publication(candidate_id="candidate-1")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    single_shot = MagicMock(side_effect=lambda _delay, callback: callback())
    monkeypatch.setattr(actions.QTimer, "singleShot", single_shot)

    outcome = handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        ["/tmp/sub-01_events.tsv"],
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: len(commands) == 2, timeout=2000)
    qtbot.waitUntil(lambda: continue_flow.call_count == 1, timeout=2000)
    assert commands[0].resource_preflight_confirmed is False
    assert commands[1].resource_preflight_confirmed is True
    assert commands[1].resource_preflight_token == expected_receipt
    assert single_shot.call_count == 0
    continue_flow.assert_called_once()
    assert continue_flow.call_args.kwargs["source_path"] == "/tmp/sub-01_raw.fif"
    assert continue_flow.call_args.kwargs["label_sources"] == ["/tmp/sub-01_events.tsv"]


def test_review_warning_without_typed_challenge_never_resubmits(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ReviewInterpretationCommand] = []
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            commands.append(command)
            return _resource_confirmation_without_challenge_result(
                "review_interpretation"
            )

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    question = MagicMock()
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "question", question)
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)

    outcome = handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=2000)
    assert len(commands) == 1
    assert question.call_count == 0
    assert continue_flow.call_count == 0


def test_review_warning_with_mismatched_challenge_command_never_resubmits(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ReviewInterpretationCommand] = []
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            commands.append(command)
            return _review_resource_confirmation_result(
                challenge_command_name="preview_interpretation",
            )

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    question = MagicMock()
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "question", question)
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)

    outcome = handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=2000)
    assert len(commands) == 1
    assert question.call_count == 0
    assert continue_flow.call_count == 0


def test_review_blocking_resource_result_never_resubmits(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ReviewInterpretationCommand] = []
    continue_flow = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            commands.append(command)
            return _resource_blocking_result("review_interpretation")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    question = MagicMock()
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "question", question)
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)

    handler._data_interpretation._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )

    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=2000)
    assert len(commands) == 1
    assert question.call_count == 0
    assert continue_flow.call_count == 0


def test_reload_warning_confirmation_retries_with_receipt_and_same_continuation(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_reload = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation._recipe_reload,
        "_continue_reloaded_interpretation_recipe",
        continue_reload,
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_can_start_interpretation",
        lambda *_args, **_kw: True,
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getOpenFileName",
        lambda *_args: ("/tmp/import_recipe.json", ""),
    )
    expected_receipt = "reload-receipt-1"
    commands: list[ReloadInterpretationRecipeCommand] = []
    success = _success_result("reload_interpretation_recipe")

    class _Service:
        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
        ):
            assert isinstance(command, ReloadInterpretationRecipeCommand)
            assert expected_publication_generation == 21
            commands.append(command)
            return (
                _review_resource_confirmation_result(
                    expected_receipt,
                    command_name="reload_interpretation_recipe",
                )
                if len(commands) == 1
                else success
            )

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: CommandReviewContext(
            capability=CommandCapability(
                command_name="reload_interpretation_recipe",
                enabled=True,
            ),
            publication_generation=21,
        ),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    single_shot = MagicMock(side_effect=lambda _delay, callback: callback())
    monkeypatch.setattr(actions.QTimer, "singleShot", single_shot)

    handler.reload_interpretation_recipe()

    qtbot.waitUntil(lambda: len(commands) == 2, timeout=2000)
    qtbot.waitUntil(lambda: continue_reload.call_count == 1, timeout=2000)
    assert commands[1].resource_preflight_confirmed is True
    assert commands[1].resource_preflight_token == expected_receipt
    assert single_shot.call_count == 0


def test_reloaded_preview_warning_retries_with_receipt_and_same_continuation(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    expected_receipt = "preview-receipt-1"
    commands: list[PreviewInterpretationCommand] = []
    success = _success_result("preview_interpretation")
    continue_preview = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation._recipe_reload,
        "_continue_reloaded_recipe_preview",
        continue_preview,
    )

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {
                "confirmed": True,
                "choices": {"skip_labels": True},
            }

    class _Service:
        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
        ):
            assert isinstance(command, PreviewInterpretationCommand)
            assert expected_publication_generation == 22
            commands.append(command)
            return (
                _review_resource_confirmation_result(
                    expected_receipt,
                    command_name="preview_interpretation",
                )
                if len(commands) == 1
                else success
            )

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_review_state_from_parts",
        lambda **_kwargs: _review_state(publication_generation=22),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    single_shot = MagicMock(side_effect=lambda _delay, callback: callback())
    monkeypatch.setattr(actions.QTimer, "singleShot", single_shot)
    reload_result = _success_result(
        "reload_interpretation_recipe",
        scan_result={"scan_id": "scan-1"},
        preview={},
        candidate={"candidate_id": "candidate-1", "choices": {}},
        validation_decision={"decision": "safe"},
    )

    handler._data_interpretation._recipe_reload._continue_reloaded_interpretation_recipe(
        reload_result
    )

    qtbot.waitUntil(lambda: len(commands) == 2, timeout=2000)
    qtbot.waitUntil(lambda: continue_preview.call_count == 1, timeout=2000)
    assert commands[1].resource_preflight_confirmed is True
    assert commands[1].resource_preflight_token == expected_receipt
    assert single_shot.call_count == 0
    assert continue_preview.call_args.kwargs["scan"] == {"scan_id": "scan-1"}


def test_reload_recipe_uses_slow_worker_without_blocking_gui(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_reload = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation._recipe_reload,
        "_continue_reloaded_interpretation_recipe",
        continue_reload,
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_can_start_interpretation",
        lambda *_args, **_kw: True,
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getOpenFileName",
        lambda *_args: ("/tmp/import_recipe.json", ""),
    )
    worker_started = threading.Event()
    worker_release = threading.Event()
    heartbeat: list[bool] = []
    result = _success_result("reload_interpretation_recipe")

    class _Service:
        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
        ):
            assert isinstance(command, ReloadInterpretationRecipeCommand)
            assert expected_publication_generation == 23
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args, **_kwargs: CommandReviewContext(
            capability=CommandCapability(
                command_name="reload_interpretation_recipe",
                enabled=True,
            ),
            publication_generation=23,
        ),
    )

    started_at = time.monotonic()
    handler.reload_interpretation_recipe()
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: continue_reload.call_count == 1, timeout=1000)


def test_apply_warning_confirmation_resubmits_trusted_receipt_async(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ApplyInterpretationCommand] = []
    applied = _success_result("apply_interpretation", applied_interpretation={})
    expected_receipt = "receipt-1"

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            commands.append(command)
            if len(commands) == 1:
                return _resource_confirmation_result(expected_receipt)
            return applied

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    status = MagicMock()
    monkeypatch.setattr(handler, "_show_status", status)

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: len(commands) == 2, timeout=2000)
    qtbot.wait(50)
    assert status.call_args_list == [
        call("Importing EEG data and labels...", 900_000),
        call("Importing EEG data and labels...", 900_000),
        call("ok"),
    ]
    assert commands[0].resource_preflight_confirmed is False
    assert commands[0].resource_preflight_token is None
    assert commands[1].resource_preflight_confirmed is True
    assert commands[1].resource_preflight_token == expected_receipt


def test_apply_warning_handoff_ack_completes_without_result_refresh(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ApplyInterpretationCommand] = []
    command_result_refresh = MagicMock()
    terminal = []
    applied = _success_result("apply_interpretation", applied_interpretation={})

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            commands.append(command)
            if len(commands) == 1:
                return _resource_confirmation_result("handoff-receipt")
            return applied

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        async_command_runner,
        "refresh_after_command",
        command_result_refresh,
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    status = MagicMock()
    monkeypatch.setattr(handler, "_show_status", status)
    completion = InteractionCompletionSession(
        request_id="handoff-apply",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        outcome = handler._data_interpretation._apply_interpretation_async(
            _review_state(),
            {"confirmed": True, "save_recipe": False},
        )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: len(terminal) == 1, timeout=2000)
    assert status.call_args_list == [
        call("Importing EEG data and labels...", 900_000),
        call("Importing EEG data and labels...", 900_000),
        call("ok"),
    ]

    assert len(commands) == 2
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    assert terminal[0].message == "ok"
    command_result_refresh.assert_not_called()


def test_apply_warning_handoff_refusal_reports_only_cancelled(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ApplyInterpretationCommand] = []
    terminal = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            commands.append(command)
            return _resource_confirmation_result("declined-receipt")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.No,
    )
    completion = InteractionCompletionSession(
        request_id="handoff-declined",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        outcome = handler._data_interpretation._apply_interpretation_async(
            _review_state(),
            {"confirmed": True, "save_recipe": False},
        )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: len(terminal) == 1, timeout=2000)

    assert len(commands) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED
    assert "cancelled" in terminal[0].message.lower()


def test_apply_warning_handoff_retry_start_failure_reports_only_failed(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ApplyInterpretationCommand] = []
    terminal = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            commands.append(command)
            return _resource_confirmation_result("start-failure-receipt")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        actions.QMessageBox,
        "question",
        lambda *_args, **_kwargs: actions.QMessageBox.StandardButton.Yes,
    )
    warning = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)
    real_execute_async = actions.execute_application_command_async

    def _execute_or_reject_retry(context, command, **kwargs):
        if getattr(command, "resource_preflight_confirmed", False):
            return False
        return real_execute_async(context, command, **kwargs)

    monkeypatch.setattr(
        actions,
        "execute_application_command_async",
        _execute_or_reject_retry,
    )
    completion = InteractionCompletionSession(
        request_id="handoff-start-failed",
        command_name="scan_source",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        outcome = handler._data_interpretation._apply_interpretation_async(
            _review_state(),
            {"confirmed": True, "save_recipe": False},
        )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: len(terminal) == 1, timeout=2000)

    assert len(commands) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message
    assert warning.call_count == 1


def test_apply_resource_callback_is_dropped_after_owner_deletion(qtbot, monkeypatch):
    panel = QWidget()
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    worker_started = threading.Event()
    worker_release = threading.Event()
    question = MagicMock()

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return _resource_confirmation_result("receipt-deleted")

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(actions.QMessageBox, "question", question)

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(),
        {"confirmed": True, "save_recipe": False},
    )
    assert outcome.status is InteractionStatus.ACCEPTED
    assert worker_started.wait(timeout=1.0)

    panel.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(panel), timeout=1000)
    worker_release.set()
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=2000,
    )
    assert question.call_count == 0


def test_apply_blocking_resource_result_is_presented_without_resubmit(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    commands: list[ApplyInterpretationCommand] = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, ApplyInterpretationCommand)
            commands.append(command)
            return _resource_blocking_result()

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _study: _Service(),
    )
    critical = MagicMock()
    question = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)
    monkeypatch.setattr(actions.QMessageBox, "question", question)

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=1000)
    assert len(commands) == 1
    assert question.call_count == 0
    assert critical.call_args.args[1] == "Dataset Resource Check"


def _real_study_dataset_handler(qtbot) -> DatasetActionHandler:
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).controller = MagicMock()
    cast(Any, panel).set_busy = lambda _busy: None
    return DatasetActionHandler(panel)


def _missing_capability_review(generation: int = 31) -> SimpleNamespace:
    return SimpleNamespace(
        capability=None,
        publication_generation=generation,
    )


def test_import_label_fails_before_target_or_dialog_when_review_capability_is_missing(
    qtbot,
    monkeypatch,
):
    handler = _real_study_dataset_handler(qtbot)
    target_reader = MagicMock(return_value=[object()])
    dialog = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args: _missing_capability_review(),
    )
    monkeypatch.setattr(
        handler._external_label_import,
        "get_target_files_for_import",
        target_reader,
    )
    monkeypatch.setattr(actions, "ImportLabelDialog", dialog)
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)

    handler.import_label()

    target_reader.assert_not_called()
    dialog.assert_not_called()
    warning.assert_called_once()


def test_recipe_save_fails_before_chooser_when_review_capability_is_missing(
    qtbot,
    monkeypatch,
):
    handler = _real_study_dataset_handler(qtbot)
    chooser = MagicMock(return_value=("", ""))
    execute = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args: _missing_capability_review(),
    )
    monkeypatch.setattr(actions.QFileDialog, "getSaveFileName", chooser)
    monkeypatch.setattr(
        handler._data_interpretation, "_execute_interpretation_command_async", execute
    )
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)

    started = handler._data_interpretation._save_interpretation_recipe()

    assert started is True
    chooser.assert_not_called()
    execute.assert_not_called()
    warning.assert_called_once()


def test_recipe_offer_fails_before_confirmation_when_review_capability_is_missing(
    qtbot,
    monkeypatch,
):
    handler = _real_study_dataset_handler(qtbot)
    question = MagicMock(return_value=actions.QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args: _missing_capability_review(),
    )
    monkeypatch.setattr(actions.QMessageBox, "question", question)

    message = handler._offer_label_recipe_save(
        SimpleNamespace(diagnostics={"recipe_updated": True}),
    )

    question.assert_not_called()
    assert message == "Interpretation recipe trace updated in this session."


def test_recipe_reload_fails_before_chooser_when_product_review_disappears(
    qtbot,
    monkeypatch,
):
    handler = _real_study_dataset_handler(qtbot)
    chooser = MagicMock(return_value=("", ""))
    warning = MagicMock()
    monkeypatch.setattr(
        handler._data_interpretation,
        "_can_start_interpretation",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(actions, "get_command_review_context", lambda *_args: None)
    monkeypatch.setattr(actions.QFileDialog, "getOpenFileName", chooser)
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)

    handler.reload_interpretation_recipe()

    chooser.assert_not_called()
    warning.assert_called_once()


def test_smart_parser_fails_before_query_when_product_review_disappears(
    qtbot,
    monkeypatch,
):
    handler = _real_study_dataset_handler(qtbot)
    enabled = CommandCapability(command_name="apply_smart_parse", enabled=True)
    query = MagicMock(return_value=["sub-01_raw.fif"])
    dialog = MagicMock()
    warning = MagicMock()
    monkeypatch.setattr(actions, "get_command_review_context", lambda *_args: None)
    monkeypatch.setattr(actions, "get_command_capability", lambda *_args: enabled)
    monkeypatch.setattr(handler, "_smart_parse_filenames", query)
    monkeypatch.setattr(actions, "SmartParserDialog", dialog)
    monkeypatch.setattr(actions.QMessageBox, "warning", warning)

    handler.open_smart_parser()

    query.assert_not_called()
    dialog.assert_not_called()
    warning.assert_called_once()
