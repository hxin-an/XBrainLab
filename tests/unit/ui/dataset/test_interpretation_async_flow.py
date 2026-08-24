"""Lifecycle tests for non-blocking Data Interpretation command continuations."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, call

import mne
import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMainWindow, QPushButton, QWidget

from XBrainLab.backend.application import (
    ApplicationService,
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
    ValidateInterpretationCommand,
    data_interpretation_internal_events,
)
from XBrainLab.backend.application.capabilities import (
    CommandCapability,
    build_capability_policy,
)
from XBrainLab.backend.application.owned_work import OwnedWorkKind, OwnedWorkRegistry
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    InterpretationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.backend.load_data.raw import Raw
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


def test_interpretation_busy_surface_keeps_visible_cancel_enabled(qtbot) -> None:
    """A cancellable Apply cannot disable its own visible product control."""
    panel = QWidget()
    qtbot.addWidget(panel)
    cancel = QPushButton("Cancel Import", panel)
    import_bids = QPushButton("Import BIDS", panel)
    reset = QPushButton("Reset Session", panel)
    panel.table = QWidget(panel)
    panel.sidebar = SimpleNamespace(
        import_cancel_btn=cancel,
        _action_buttons=(import_bids, cancel, reset),
    )
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation

    coordinator.set_busy(True)

    assert panel.isEnabled()
    assert import_bids.isEnabled() is False
    assert reset.isEnabled() is False
    assert panel.table.isEnabled() is False
    assert cancel.isEnabled() is True

    coordinator.set_busy(False)

    assert import_bids.isEnabled() is True
    assert reset.isEnabled() is True
    assert panel.table.isEnabled() is True
    assert cancel.isEnabled() is True


def test_catalog_scan_publishes_owned_status_before_worker_is_scheduled(
    qtbot,
    monkeypatch,
) -> None:
    """Slow BIDS discovery stays observable from the first scheduler boundary."""
    window = QMainWindow()
    panel = QWidget(window)
    cancel = QPushButton("Cancel Import", panel)
    cast(Any, panel).main_window = window
    cast(Any, panel).sidebar = SimpleNamespace(import_cancel_btn=cancel)
    cast(Any, panel).set_busy = lambda _busy: None
    qtbot.addWidget(window)
    window.show()
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "")
    status.setProperty("stage", "Idle")
    status.setProperty("operationPhase", "idle")

    result = _success_result(
        "scan_source",
        payload_type="source_classification",
        source_kind="bids",
        bids_subject_catalog={
            "eeg_file_count": 1,
            "subjects": [{"subject": "01", "label": "sub-01", "eeg_file_count": 1}],
        },
    )

    class _Service:
        def begin_owned_operation(self, command):
            assert command.catalog_only is True
            assert command.source_hint == "auto"
            return SimpleNamespace(operation_id="catalog-operation-1")

        def get_owned_operation(self, operation_id):
            assert operation_id == "catalog-operation-1"
            return SimpleNamespace(
                phase=SimpleNamespace(value="pending"),
                stage="Queued",
                completed=None,
                total=None,
                indeterminate=True,
                cancel_requested=False,
                cancellable=True,
            )

        def cancel_owned_operation(self, _operation_id):
            return True

        def fail_owned_operation(self, operation_id, *, message):
            raise AssertionError((operation_id, message))

        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
            operation_id=None,
        ):
            assert command.catalog_only is True
            assert expected_publication_generation is None
            assert operation_id == "catalog-operation-1"
            return result

    workers = []
    status_at_schedule: list[tuple[str, str, str]] = []

    class _ThreadPool:
        def start(self, worker):
            status_at_schedule.append(
                (
                    str(status.property("operationId") or ""),
                    str(status.property("stage") or ""),
                    str(status.property("operationPhase") or ""),
                )
            )
            workers.append(worker)

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: _Service(),
    )
    monkeypatch.setattr(
        async_command_runner.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    handler = DatasetActionHandler(panel)

    outcome = handler._data_interpretation._start_source_classification_async(
        "/tmp/bids-root"
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    assert status_at_schedule == [("catalog-operation-1", "Queued", "pending")]
    qtbot.waitUntil(
        lambda: status.currentMessage() == "Queued · Working…",
        timeout=1_500,
    )
    assert status.property("operationId") == "catalog-operation-1"
    assert status.property("stage") == "Queued"
    assert status.property("operationPhase") == "pending"
    presenter = handler._data_interpretation._operation_presenter
    assert presenter is not None
    presenter.abandon()
    workers[0].signals.finished.emit()


def test_cancelled_catalog_scan_closes_without_failure_dialog(monkeypatch) -> None:
    """Cancelling pre-subject discovery is a terminal action, not an error."""
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation
    message_box = MagicMock()
    statuses: list[str] = []
    scheduled = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    subjects = MagicMock()
    coordinator._bindings = replace(
        coordinator._bindings,
        show_warning=message_box.warning,
        show_error=message_box.critical,
        ask_confirmation=lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(handler, "_show_status", statuses.append)
    monkeypatch.setattr(
        coordinator,
        "_execute_interpretation_command_async",
        scheduled,
    )
    monkeypatch.setattr(coordinator, "_present_bids_subject_catalog", subjects)

    started = coordinator._start_source_classification_async("/data/bids")
    result = scheduled.call_args.kwargs["on_result"](_cancelled_result("scan_source"))

    assert started.status is InteractionStatus.ACCEPTED
    assert result.status is InteractionStatus.CANCELLED
    assert statuses == ["Checking EEG source…", "Dataset import cancelled"]
    message_box.critical.assert_not_called()
    message_box.warning.assert_not_called()
    subjects.assert_not_called()


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


def test_label_configuration_merge_preserves_untouched_explicit_run_choices():
    first = "/bids/sub-01_task-p300_run-1_events.tsv"
    second = "/bids/sub-01_task-p300_run-2_events.tsv"
    merged = DataInterpretationActionCoordinator._merge_interpretation_choices(
        {
            "label_carrier": "loaded_label_files",
            "label_carrier_choices": {
                first: {"label_field": "trial_type", "anchor": "onset"},
                second: {"label_field": "value", "anchor": "onset"},
            },
        },
        {
            "label_carrier_choices": {
                first: {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "value_decisions": {
                        "target": {
                            "role": "stimulus",
                            "keep_event": True,
                            "use_as_class": True,
                            "class_name": "Target",
                        }
                    },
                }
            }
        },
    )

    assert merged["label_carrier_choices"][second] == {
        "label_field": "value",
        "anchor": "onset",
    }
    assert "value_decisions" in merged["label_carrier_choices"][first]


def test_label_configuration_merge_deep_merges_sparse_carrier_decision_edit():
    carrier = "/bids/sub-01_task-condition_events.tsv"
    untouched_decision = {
        "role": "stimulus",
        "keep_event": True,
        "use_as_class": True,
        "class_name": "Standard",
    }
    edited_decision = {
        "role": "ignored",
        "keep_event": True,
        "use_as_class": False,
    }
    merged = DataInterpretationActionCoordinator._merge_interpretation_choices(
        {
            "label_carrier": "loaded_label_files",
            "label_carrier_choices": {
                carrier: {
                    "label_field": "value",
                    "target_file": "/bids/sub-01_task-condition_eeg.set",
                    "placement_method": "time_field",
                    "anchor": "onset",
                    "value_decisions": {
                        "standard": untouched_decision,
                        "target": {
                            "role": "stimulus",
                            "keep_event": True,
                            "use_as_class": True,
                            "class_name": "Target",
                        },
                    },
                }
            },
        },
        {
            "label_carrier_choices": {
                carrier: {"value_decisions": {"target": edited_decision}}
            }
        },
    )

    carrier_choice = merged["label_carrier_choices"][carrier]
    assert carrier_choice["label_field"] == "value"
    assert carrier_choice["target_file"] == "/bids/sub-01_task-condition_eeg.set"
    assert carrier_choice["placement_method"] == "time_field"
    assert carrier_choice["anchor"] == "onset"
    assert carrier_choice["value_decisions"]["standard"] == untouched_decision
    assert carrier_choice["value_decisions"]["target"] == edited_decision


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
    monkeypatch.setattr(actions, "show_warning", warning)
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
    monkeypatch.setattr(actions, "show_warning", MagicMock())
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
    monkeypatch.setattr(actions, "show_warning", warning)
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


def _cancelled_result(command_name: str = "apply_interpretation") -> CommandResult:
    return CommandResult.failure_result(
        command_name=command_name,
        message="The operation was cancelled.",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.CANCELLED,
        recoverable=True,
        diagnostics={"state_preserved": True},
    )


def _state_preserved_apply_failure_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CommandResult:
    """Return product diagnostics from a real mixed-placement Apply failure."""
    from scipy.io import savemat

    source_dir = tmp_path / "mixed_label_placement"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    second_eeg_path = source_dir / "B01T.gdf"
    sequence_labels = source_dir / "A01T.mat"
    timed_labels = source_dir / "B01T_events.tsv"
    eeg_path.write_bytes(b"reviewed sequence EEG")
    second_eeg_path.write_bytes(b"reviewed timestamp EEG")
    savemat(sequence_labels, {"classlabel": [[1, 2]]})
    timed_labels.write_text(
        "onset\ttrial_type\n0.5\tleft\n1.5\tright\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda path: (
            {"events": {"768": {"count": 2, "description": "768"}}}
            if Path(path).name == eeg_path.name
            else {"events": {}}
        ),
    )
    raw_by_path: dict[str, Raw] = {}
    for path in (eeg_path, second_eeg_path):
        raw_by_path[str(path)] = Raw(
            str(path),
            mne.io.RawArray(
                np.zeros((1, 500)),
                mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
                verbose="ERROR",
            ),
        )
    service = ApplicationService(Study())
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(
        load=lambda path: raw_by_path[str(path)]
    )
    review = service.execute(
        ReviewInterpretationCommand(
            source_path=str(source_dir),
            choices={
                "label_carrier_choices": {
                    str(sequence_labels): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": {
                            "1": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "Left hand",
                            },
                            "2": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "Right hand",
                            },
                        },
                    },
                    str(timed_labels): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "placement_method": "time_field",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": {
                            "left": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "Left hand",
                            },
                            "right": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "Right hand",
                            },
                        },
                    },
                },
            },
        )
    )
    candidate_id = review.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    result = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )
    assert result.failed
    assert result.error_type is ErrorType.VALIDATION
    assert result.diagnostics["label_apply"]["status"] == "failed"
    assert result.diagnostics["state_preserved"] is True
    return result


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


class _BlockingVisibleApplyRuntime:
    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        self.worker_started = threading.Event()
        self.running_release = threading.Event()
        self.worker_release = threading.Event()
        self.snapshot = SimpleNamespace(
            kind=OwnedWorkKind.IMPORT_APPLY,
            phase=SimpleNamespace(value="pending"),
            stage="Preparing interpretation apply",
            completed=None,
            total=None,
            indeterminate=True,
            cancel_requested=False,
            cancellable=True,
        )

    def begin_owned_operation(self, command):
        assert isinstance(command, ApplyInterpretationCommand)
        return SimpleNamespace(operation_id=self.operation_id)

    def get_owned_operation(self, operation_id):
        assert operation_id == self.operation_id
        return self.snapshot

    def cancel_owned_operation(self, operation_id):
        assert operation_id == self.operation_id
        return True

    def fail_owned_operation(self, operation_id, *, message):
        raise AssertionError((operation_id, message))

    def execute(
        self,
        command,
        *,
        expected_publication_generation=None,
        operation_id=None,
    ):
        assert isinstance(command, ApplyInterpretationCommand)
        assert expected_publication_generation == 17
        assert operation_id == self.operation_id
        self.worker_started.set()
        assert self.running_release.wait(timeout=2.0)
        self.snapshot.phase.value = "running"
        self.snapshot.stage = "Loading reviewed EEG recordings"
        assert self.worker_release.wait(timeout=2.0)
        self.snapshot.phase.value = "completed"
        self.snapshot.stage = "Dataset import complete"
        return _success_result(
            "apply_interpretation",
            applied_interpretation={},
        )


class _FastVisibleApplyRuntime(_BlockingVisibleApplyRuntime):
    def execute(
        self,
        command,
        *,
        expected_publication_generation=None,
        operation_id=None,
    ):
        assert isinstance(command, ApplyInterpretationCommand)
        assert expected_publication_generation == 17
        assert operation_id == self.operation_id
        self.worker_started.set()
        self.snapshot.phase.value = "completed"
        self.snapshot.stage = "Dataset import complete"
        return _success_result(
            "apply_interpretation",
            applied_interpretation={},
        )


def _visible_apply_handler(qtbot):
    window = QMainWindow()
    panel = QWidget(window)
    window.setCentralWidget(panel)
    cancel = QPushButton("Cancel Import", panel)
    cast(Any, panel).main_window = window
    cast(Any, panel).sidebar = SimpleNamespace(
        import_cancel_btn=cancel,
        _action_buttons=(),
    )
    cast(Any, panel).set_busy = lambda _busy: None
    qtbot.addWidget(window)
    window.show()
    status = window.statusBar()
    status.setObjectName("OwnedOperationProgress")
    status.setProperty("operationId", "")
    status.setProperty("operationKind", "")
    status.setProperty("stage", "Idle")
    status.setProperty("operationPhase", "idle")
    return window, DatasetActionHandler(panel), status


def _assert_visible_apply_completes(qtbot, status, runtime) -> None:
    try:
        assert status.property("operationId") == runtime.operation_id
        assert status.property("operationKind") == "import_apply"
        assert status.property("operationPhase") in {"pending", "running"}
        assert "interpretation apply" in str(status.property("stage")).casefold()
        assert status.property("operationDetail") == status.property("stage")
        assert status.currentMessage() == "Importing reviewed EEG data · Working…"

        assert runtime.worker_started.wait(timeout=1.0)
        runtime.running_release.set()
        qtbot.waitUntil(
            lambda: status.property("operationPhase") == "running"
            and status.property("stage") == "Loading reviewed EEG recordings"
            and status.property("operationDetail") == "Loading reviewed EEG recordings"
            and status.currentMessage() == "Importing reviewed EEG data · Working…",
            timeout=1_000,
        )
    finally:
        runtime.running_release.set()
        runtime.worker_release.set()
    qtbot.waitUntil(
        lambda: status.property("operationPhase") == "completed"
        and status.currentMessage() == "ok",
        timeout=1_500,
    )


def test_confirmed_direct_apply_immediately_publishes_owned_status(
    qtbot,
    monkeypatch,
) -> None:
    _window, handler, status = _visible_apply_handler(qtbot)
    runtime = _BlockingVisibleApplyRuntime("direct-apply-operation")

    class _ConfirmedDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": {}, "save_recipe": False}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _ConfirmedDialog)
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: runtime,
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    _assert_visible_apply_completes(qtbot, status, runtime)


def test_confirmed_revalidation_to_apply_immediately_publishes_owned_status(
    qtbot,
    monkeypatch,
) -> None:
    _window, handler, status = _visible_apply_handler(qtbot)
    runtime = _BlockingVisibleApplyRuntime("revalidated-apply-operation")
    revised_choices = {"class_map": {"1": "Target"}}

    class _ConfirmedDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {
                "confirmed": True,
                "choices": revised_choices,
                "save_recipe": False,
            }

    def _complete_revalidation(**kwargs):
        return kwargs["on_validated"](
            _review_state(publication_generation=17),
        )

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _ConfirmedDialog)
    monkeypatch.setattr(
        handler._data_interpretation,
        "_preview_and_validate_interpretation_async",
        _complete_revalidation,
    )
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: runtime,
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    _assert_visible_apply_completes(qtbot, status, runtime)


def test_real_async_revalidation_handoff_keeps_apply_as_visible_owner(
    qtbot,
    monkeypatch,
) -> None:
    """A terminal Validate callback cannot hide the Apply it starts."""
    _window, handler, status = _visible_apply_handler(qtbot)
    snapshots: dict[str, Any] = {}
    operation_ids: dict[type[Any], str] = {
        PreviewInterpretationCommand: "preview-operation",
        ValidateInterpretationCommand: "validate-operation",
        ApplyInterpretationCommand: "apply-operation",
    }

    class _Runtime:
        def begin_owned_operation(self, command):
            operation_id = operation_ids[type(command)]
            kind = (
                OwnedWorkKind.IMPORT_APPLY
                if isinstance(command, ApplyInterpretationCommand)
                else OwnedWorkKind.IMPORT_REVIEW
            )
            snapshots[operation_id] = SimpleNamespace(
                kind=kind,
                phase=SimpleNamespace(value="pending"),
                stage="Queued",
                completed=None,
                total=None,
                indeterminate=True,
                cancel_requested=False,
                cancellable=True,
            )
            return SimpleNamespace(operation_id=operation_id)

        def get_owned_operation(self, operation_id):
            return snapshots[operation_id]

        @staticmethod
        def cancel_owned_operation(_operation_id):
            return True

        @staticmethod
        def fail_owned_operation(operation_id, *, message):
            raise AssertionError((operation_id, message))

        @staticmethod
        def get_view_publication():
            return _review_publication(
                generation=17,
                scan_id="scan-1",
                candidate_id="candidate-1",
            )

        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
            operation_id=None,
        ):
            assert expected_publication_generation == 17
            assert operation_id == operation_ids[type(command)]
            snapshot = snapshots[operation_id]
            snapshot.phase.value = "completed"
            if isinstance(command, PreviewInterpretationCommand):
                snapshot.stage = "Interpretation preview complete"
                return _success_result(
                    "preview_interpretation",
                    preview={"summary": "ready"},
                    candidate={"candidate_id": "candidate-1"},
                )
            if isinstance(command, ValidateInterpretationCommand):
                snapshot.stage = "Interpretation validation complete"
                return _success_result(
                    "validate_interpretation",
                    validation_decision={
                        "candidate_id": "candidate-1",
                        "decision": "safe",
                    },
                )
            assert isinstance(command, ApplyInterpretationCommand)
            snapshot.stage = "Dataset import complete"
            return _success_result(
                "apply_interpretation",
                applied_interpretation={},
            )

    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: _Runtime(),
    )
    terminal = []
    completion = InteractionCompletionSession(
        request_id="revalidation-apply",
        command_name="preview_interpretation",
        on_terminal=terminal.append,
    )

    with bind_interaction_completion(completion):
        outcome = handler._data_interpretation._review_interpretation_for_apply_async(
            source_path="/data/sub-01",
            source_hint="bids",
            choices={"class_map": {"1": "Target"}},
            validated_choices={},
            label_sources=["/data/sub-01/sub-01_events.tsv"],
            review_state=_review_state(publication_generation=17),
            dialog_result={"confirmed": True, "save_recipe": False},
        )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: bool(terminal), timeout=2_000)
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    qtbot.waitUntil(
        lambda: status.property("operationId") == "apply-operation"
        and status.property("operationKind") == "import_apply"
        and status.property("operationPhase") == "completed"
        and status.property("stage") == "Dataset import complete",
        timeout=1_000,
    )


def test_fast_apply_preserves_exact_visible_pending_then_terminal_evidence(
    qtbot,
    monkeypatch,
) -> None:
    _window, handler, status = _visible_apply_handler(qtbot)
    runtime = _FastVisibleApplyRuntime("fast-apply-operation")
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: runtime,
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert status.property("operationId") == runtime.operation_id
    assert status.property("operationKind") == "import_apply"
    assert status.property("operationPhase") == "pending"
    assert status.property("stage") == "Preparing interpretation apply"
    assert status.property("operationDetail") == "Preparing interpretation apply"
    assert status.currentMessage() == "Importing reviewed EEG data · Working…"

    assert runtime.worker_started.wait(timeout=1.0)
    qtbot.waitUntil(
        lambda: status.property("operationId") == runtime.operation_id
        and status.property("operationKind") == "import_apply"
        and status.property("operationPhase") == "completed"
        and status.property("stage") == "Dataset import complete"
        and status.currentMessage() == "ok",
        timeout=1_500,
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


def test_confirm_import_does_not_mask_owned_status_before_async_revalidation(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    revised_choices = {
        "label_carrier_choices": {"/data/sub-01_events.tsv": {"label_field": "value"}}
    }
    statuses: list[tuple[str, int]] = []

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
                "choices": revised_choices,
            }

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )

    def _start_revalidation(**_kwargs):
        assert statuses == []
        return InteractionOutcome.accepted("Import revalidation scheduled.")

    revalidate = MagicMock(side_effect=_start_revalidation)
    monkeypatch.setattr(
        handler._data_interpretation,
        "_review_interpretation_for_apply_async",
        revalidate,
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert statuses == []
    revalidate.assert_called_once()


def test_confirm_import_waits_for_review_dialog_destruction_before_apply(
    qtbot,
    monkeypatch,
) -> None:
    """Accepted review must leave the native modal lifecycle before Apply."""
    panel = QWidget()
    qtbot.addWidget(panel)
    handler = DatasetActionHandler(panel)
    dialog_instances: list[QDialog] = []

    class _Dialog(QDialog):
        def __init__(self, parent, **_kwargs) -> None:
            super().__init__(parent)
            dialog_instances.append(self)

        def exec(self) -> int:
            return 1

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": {}}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    apply_started: list[bool] = []

    def _apply(*_args, **_kwargs) -> InteractionOutcome:
        apply_started.append(sip.isdeleted(dialog_instances[0]))
        return InteractionOutcome.accepted("Apply scheduled.")

    monkeypatch.setattr(
        handler._data_interpretation,
        "_apply_interpretation_async",
        _apply,
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert apply_started == []
    qtbot.waitUntil(lambda: apply_started == [True], timeout=1_500)


def test_confirm_import_revalidation_worker_failure_replaces_preparing_status(
    monkeypatch,
) -> None:
    panel = MagicMock()
    revised_choices = {"class_map": {"1": "Target"}}
    statuses: list[tuple[str, int]] = []
    warning = MagicMock()
    monkeypatch.setattr(actions, "show_warning", warning)
    handler = DatasetActionHandler(panel)

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": revised_choices}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
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

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="file",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )
    execute.call_args.kwargs["on_error"](
        (RuntimeError, RuntimeError("revalidation failed"), None)
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert statuses == [
        ("Dataset import failed · Review the import settings", 7000),
    ]
    warning.assert_called_once()
    warning_text = warning.call_args.args[2]
    assert "revalidation failed" in warning_text
    assert "Reopen Import EEG Data" in warning_text


def test_confirm_import_resource_check_cancel_replaces_preparing_status(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    revised_choices = {"class_map": {"1": "Target"}}
    statuses: list[tuple[str, int]] = []

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": revised_choices}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
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
    monkeypatch.setattr(
        handler._data_interpretation,
        "_preview_resource_preflight_outcome",
        MagicMock(
            return_value=InteractionOutcome.cancelled(
                "Dataset import preview was cancelled during the resource check."
            )
        ),
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="file",
        choices={},
        label_sources=[],
        review_state=_review_state(publication_generation=17),
    )
    terminal = execute.call_args.kwargs["on_result"](MagicMock())

    assert outcome.status is InteractionStatus.ACCEPTED
    assert terminal.status is InteractionStatus.CANCELLED
    assert statuses == [
        ("Dataset import cancelled", 7000),
    ]


@pytest.mark.parametrize("cancelled_command", ["preview", "validation"])
def test_confirm_import_revalidation_cancel_reopens_edited_review_without_failure(
    monkeypatch,
    cancelled_command: str,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation
    review_state = _review_state(publication_generation=17)
    preview_state = replace(
        review_state,
        preview={"summary": "ready"},
        publication_generation=18,
    )
    revised_choices = {"class_map": {"1": "Target"}}
    statuses: list[tuple[str, int]] = []

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": revised_choices}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )
    monkeypatch.setattr(
        coordinator,
        "_review_state_from_parts",
        MagicMock(return_value=preview_state),
    )
    execute = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    warning = MagicMock()
    critical = MagicMock()
    coordinator._bindings = replace(
        coordinator._bindings,
        execute_application_command_async=execute,
        single_shot=lambda _delay, callback: callback(),
        qt_object_deleted=lambda _owner: False,
        reserve_interaction_continuation=lambda: None,
        show_warning=warning,
        show_error=critical,
        ask_confirmation=lambda *_args, **_kwargs: False,
    )

    outcome = coordinator._continue_data_interpretation_import(
        source_path="/data/sub-01",
        source_hint="bids",
        choices={},
        label_sources=["/data/sub-01/sub-01_events.tsv"],
        review_state=review_state,
    )
    assert outcome.status is InteractionStatus.ACCEPTED

    if cancelled_command == "validation":
        preview_terminal = execute.call_args.kwargs["on_result"](
            _success_result(
                "preview_interpretation",
                preview={"summary": "ready"},
                candidate={"candidate_id": "candidate-1"},
            )
        )
        assert preview_terminal.status is InteractionStatus.ACCEPTED

    reopen = MagicMock(return_value=InteractionOutcome.accepted("reopened"))
    monkeypatch.setattr(coordinator, "_continue_data_interpretation_import", reopen)
    terminal = execute.call_args.kwargs["on_result"](
        _cancelled_result(
            "validate_interpretation"
            if cancelled_command == "validation"
            else "preview_interpretation"
        )
    )

    assert terminal.status is InteractionStatus.ACCEPTED
    warning.assert_not_called()
    critical.assert_not_called()
    assert statuses == [
        ("Dataset import cancelled · Review preserved", 7000),
    ]
    reopen.assert_called_once_with(
        source_path="/data/sub-01",
        source_hint="bids",
        choices=revised_choices,
        label_sources=["/data/sub-01/sub-01_events.tsv"],
        review_state=review_state,
        initial_step="Review and Import",
        validated_choices={},
    )


def test_reopened_revalidation_cancel_cannot_apply_unvalidated_edited_choices(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation
    review_state = _review_state(publication_generation=17)
    revised_choices = {"class_map": {"1": "Target"}}

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": revised_choices}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    revalidate = MagicMock(
        return_value=InteractionOutcome.accepted("revalidation scheduled")
    )
    apply_review = MagicMock()
    monkeypatch.setattr(
        coordinator,
        "_review_interpretation_for_apply_async",
        revalidate,
    )
    monkeypatch.setattr(
        coordinator,
        "_apply_interpretation_async",
        apply_review,
    )

    outcome = coordinator._continue_data_interpretation_import(
        source_path="/data/sub-01",
        source_hint="bids",
        choices=revised_choices,
        label_sources=["/data/sub-01/sub-01_events.tsv"],
        review_state=review_state,
        initial_step="Review and Import",
        validated_choices={},
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    revalidate.assert_called_once_with(
        source_path="/data/sub-01",
        source_hint="bids",
        choices=revised_choices,
        validated_choices={},
        label_sources=["/data/sub-01/sub-01_events.tsv"],
        review_state=review_state,
        dialog_result={"confirmed": True, "choices": revised_choices},
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
    present_error = MagicMock(
        return_value=(
            "XBrainLab could not prepare the Data Import review. "
            "Reopen the source and try again."
        )
    )
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        present_unexpected_error=present_error,
    )
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
    present_error.assert_not_called()


def test_choice_repreview_uses_existing_scan_without_rescanning(monkeypatch) -> None:
    handler = DatasetActionHandler(MagicMock())
    loading = MagicMock()
    loading.cancelled_by_user = False
    cast(Any, handler._data_interpretation)._loading_dialog_class = lambda: (
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


def test_repreview_hands_loading_ownership_to_the_visible_preview(
    monkeypatch,
) -> None:
    handler = DatasetActionHandler(MagicMock())
    loading = MagicMock()
    loading.cancelled_by_user = False
    cast(Any, handler._data_interpretation)._loading_dialog_class = lambda: (
        lambda *_args, **_kwargs: loading
    )
    continue_flow = MagicMock(
        return_value=InteractionOutcome.cancelled("Preview closed.")
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_continue_data_interpretation_import",
        continue_flow,
    )

    def validate(*, on_validated, **_kwargs):
        return on_validated(_review_state(publication_generation=17))

    monkeypatch.setattr(
        handler._data_interpretation,
        "_preview_and_validate_interpretation_async",
        validate,
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
    assert outcome.status is InteractionStatus.CANCELLED
    loading.accept.assert_not_called()
    loading_token = continue_flow.call_args.kwargs["loading_token"]
    assert loading_token is handler._data_interpretation._loading_session.token


def test_repreview_cancel_reopens_the_exact_preserved_match_labels_draft(
    monkeypatch,
) -> None:
    """Orange Cancel Import must restore the edited review, not its defaults."""
    handler = DatasetActionHandler(MagicMock())
    coordinator = handler._data_interpretation
    loading = MagicMock()
    loading.cancelled_by_user = False
    cast(Any, coordinator)._loading_dialog_class = lambda: (
        lambda *_args, **_kwargs: loading
    )
    choices = {"label_carrier_choices": {"events.tsv": "trial_type"}}
    review_state = _review_state(publication_generation=17)
    reopened = MagicMock(return_value=InteractionOutcome.accepted("Reopened."))
    continue_flow = MagicMock(return_value=InteractionOutcome.accepted("Review ready."))
    monkeypatch.setattr(coordinator, "_schedule_cancelled_review_reopen", reopened)
    monkeypatch.setattr(
        coordinator, "_continue_data_interpretation_import", continue_flow
    )

    def cancel_preview(*, on_cancelled, **_kwargs):
        return on_cancelled(review_state)

    monkeypatch.setattr(
        coordinator,
        "_preview_and_validate_interpretation_async",
        cancel_preview,
    )

    outcome = coordinator._repreview_interpretation_async(
        source_path="/data",
        source_hint="bids",
        choices=choices,
        label_sources=["events.tsv"],
        review_state=review_state,
        initial_step="Match Labels",
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    retry = reopened.call_args.args[0]
    retry()
    assert continue_flow.call_args.kwargs["choices"] == choices
    assert continue_flow.call_args.kwargs["label_sources"] == ["events.tsv"]
    assert continue_flow.call_args.kwargs["review_state"].scan == review_state.scan
    assert (
        continue_flow.call_args.kwargs["review_state"].decision == review_state.decision
    )
    assert (
        reopened.call_args.kwargs["cancelled_message"] == "The operation was cancelled."
    )


def test_repreview_cancelled_worker_queues_exact_match_labels_reopen(
    qtbot,
    monkeypatch,
) -> None:
    """A real coordinator must reopen its preserved draft after worker cancellation."""
    window = QMainWindow()
    panel = QWidget(window)
    cancel = QPushButton("Cancel Import", panel)
    qtbot.addWidget(window)
    window.show()
    cast(Any, panel).study = Study()
    cast(Any, panel).main_window = window
    cast(Any, panel).sidebar = SimpleNamespace(import_cancel_btn=cancel)
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation
    worker_started = threading.Event()
    worker_release = threading.Event()
    reopened: list[dict[str, Any]] = []
    commands: list[object] = []

    class _LoadingDialog(QDialog):
        retry_requested = pyqtSignal()

        def __init__(self, parent, *, initial_step="") -> None:
            super().__init__(parent)
            self.initial_step = initial_step
            self.cancelled_by_user = False

        def set_stage(self, _title, _detail) -> None:
            return None

        def show_error(self, _message, *, retry_available=True) -> None:
            del retry_available

    class _ReopenedReview:
        def __init__(self, _parent, **kwargs) -> None:
            reopened.append(kwargs)

        @staticmethod
        def exec() -> int:
            return int(QDialog.DialogCode.Rejected)

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {}

    class _Runtime:
        def __init__(self) -> None:
            self.registry = OwnedWorkRegistry()

        def begin_owned_operation(self, command):
            commands.append(command)
            assert isinstance(command, PreviewInterpretationCommand)
            return self.registry.begin(OwnedWorkKind.IMPORT_REVIEW, cancellable=True)

        def cancel_owned_operation(self, operation_id):
            return self.registry.cancel(operation_id)

        def get_owned_operation(self, operation_id):
            return self.registry.snapshot(operation_id)

        def fail_owned_operation(self, operation_id, *, message):
            return self.registry.fail(operation_id, message=message)

        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
            operation_id=None,
        ):
            assert isinstance(command, PreviewInterpretationCommand)
            assert expected_publication_generation == 17
            assert operation_id is not None
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            self.registry.finish_cancelled(operation_id)
            return _cancelled_result("preview_interpretation")

    runtime = _Runtime()
    coordinator._loading_dialog_class = lambda: _LoadingDialog
    coordinator._preview_dialog_class = lambda: _ReopenedReview
    monkeypatch.setattr(
        application_capabilities,
        "application_ui_runtime",
        lambda _context: runtime,
    )
    choices = {
        "label_carrier_choices": {
            "events.tsv": {"label_field": "trial_type", "class_name": "Left"}
        }
    }
    review_state = _review_state(publication_generation=17)
    review_state = replace(
        review_state,
        decision={"candidate_id": "candidate-1", "decision": "safe", "keep": True},
    )

    outcome = coordinator._repreview_interpretation_async(
        source_path="/data/source",
        source_hint="bids",
        choices=choices,
        label_sources=["events.tsv"],
        review_state=review_state,
        initial_step="Match Labels",
    )

    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED
    assert worker_started.wait(timeout=1.0)
    assert coordinator._loading_session is not None
    loading = coordinator._loading_session.dialog
    assert isinstance(loading, _LoadingDialog)
    loading.cancelled_by_user = True
    loading.reject()
    worker_release.set()

    qtbot.waitUntil(lambda: len(reopened) == 1, timeout=2_000)
    assert [type(command) for command in commands] == [PreviewInterpretationCommand]
    assert reopened[0]["initial_step"] == "Match Labels"
    assert reopened[0]["choices"] == choices
    assert reopened[0]["scan_result"] == review_state.scan
    assert reopened[0]["validation_decision"] == review_state.decision


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


def test_apply_leaves_in_flight_status_to_owned_operation_presenter(monkeypatch):
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
    assert statuses == []

    on_result = execute.call_args.kwargs["on_result"]
    completed = _success_result(
        "apply_interpretation",
        applied_interpretation={},
        success_count=6,
    )
    on_result(completed)

    assert statuses[-1] == (completed.message, 7000)


def test_apply_failure_explains_that_existing_data_was_preserved(
    tmp_path,
    monkeypatch,
):
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
    critical = MagicMock()
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        show_error=critical,
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
    )
    terminal = execute.call_args.kwargs["on_result"](
        _state_preserved_apply_failure_result(tmp_path, monkeypatch)
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert terminal.status is InteractionStatus.BLOCKED
    assert "mixed placement modes" in terminal.message
    assert statuses == [
        ("Dataset import failed · Existing data preserved", 7000),
    ]
    critical.assert_called_once()
    assert critical.call_args.args[1] == "Interpretation apply failed"
    assert "mixed placement modes" in critical.call_args.args[2]
    assert "Existing data was preserved." in critical.call_args.args[2]


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
        ("Dataset import failed · Review the import settings", 7000),
    ]
    assert present_error.call_args.kwargs["error_info"] == error


def test_apply_replaces_loading_status_when_dispatch_cannot_start(monkeypatch):
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    statuses: list[tuple[str, int]] = []
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )
    monkeypatch.setattr(
        handler._data_interpretation,
        "_execute_interpretation_command_async",
        MagicMock(return_value=None),
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(),
        {"confirmed": True, "save_recipe": False},
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert statuses == [
        ("Dataset import failed · Review the import settings", 7000),
    ]


def test_apply_owned_cancel_reopens_review_without_presenting_a_failure(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    statuses: list[tuple[str, int]] = []
    monkeypatch.setattr(
        handler,
        "_show_status",
        lambda message, timeout_ms=7000: statuses.append((message, timeout_ms)),
    )
    execute = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    retry = MagicMock(return_value=InteractionOutcome.accepted("retry scheduled"))
    critical = MagicMock()
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        execute_application_command_async=execute,
        single_shot=lambda _delay, callback: callback(),
        qt_object_deleted=lambda _owner: False,
        reserve_interaction_continuation=lambda: None,
        show_error=critical,
    )

    outcome = handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
        retry_cancelled_apply=retry,
    )
    terminal = execute.call_args.kwargs["on_result"](_cancelled_result())

    assert outcome.status is InteractionStatus.ACCEPTED
    assert terminal.status is InteractionStatus.ACCEPTED
    retry.assert_called_once_with()
    critical.assert_not_called()
    assert statuses == [
        ("Dataset import cancelled · Review preserved", 7000),
    ]


def test_apply_owned_cancel_does_not_reopen_after_close_starts(monkeypatch) -> None:
    panel = MagicMock()
    panel.main_window = SimpleNamespace(_closing_in_progress=True)
    handler = DatasetActionHandler(panel)
    scheduled: list[Callable[[], None]] = []
    execute = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    retry = MagicMock(return_value=InteractionOutcome.accepted("retry scheduled"))
    continuation = MagicMock()
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        execute_application_command_async=execute,
        single_shot=lambda _delay, callback: scheduled.append(callback),
        qt_object_deleted=lambda _owner: False,
        reserve_interaction_continuation=lambda: continuation,
    )

    handler._data_interpretation._apply_interpretation_async(
        _review_state(publication_generation=17),
        {"confirmed": True, "save_recipe": False},
        retry_cancelled_apply=retry,
    )
    terminal = execute.call_args.kwargs["on_result"](_cancelled_result())
    assert terminal.status is InteractionStatus.ACCEPTED

    assert len(scheduled) == 1
    scheduled[0]()
    retry.assert_not_called()
    continuation.start.assert_not_called()
    continuation.fail.assert_called_once()


def test_apply_cancel_retry_reopens_the_same_review_without_rescanning(
    monkeypatch,
) -> None:
    panel = MagicMock()
    handler = DatasetActionHandler(panel)
    review_state = _review_state(publication_generation=17)

    class _Dialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec() -> bool:
            return True

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {"confirmed": True, "choices": {}, "save_recipe": False}

    monkeypatch.setattr(actions, "DataInterpretationPreviewDialog", _Dialog)
    apply_review = MagicMock(return_value=InteractionOutcome.accepted("scheduled"))
    monkeypatch.setattr(
        handler._data_interpretation,
        "_apply_interpretation_async",
        apply_review,
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/bids/MNE-BIDS-example",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=review_state,
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    retry = apply_review.call_args.kwargs["retry_cancelled_apply"]
    reopen = MagicMock(return_value=InteractionOutcome.accepted("reopened"))
    monkeypatch.setattr(
        handler._data_interpretation,
        "review_current_import",
        reopen,
    )

    assert retry().status is InteractionStatus.ACCEPTED
    reopen.assert_called_once_with(
        initial_step="Review and Import",
        expected_identity=InterpretationReviewIdentity(
            publication_generation=17,
            scan_id="scan-1",
            candidate_id="candidate-1",
        ),
    )


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
    monkeypatch.setattr(actions, "show_warning", warning)

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
        return True

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
    monkeypatch.setattr(actions, "ask_confirmation", question)
    monkeypatch.setattr(
        actions,
        "show_warning",
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
    present_error = MagicMock(
        return_value=(
            "XBrainLab could not prepare the Data Import review. "
            "Reopen the source and try again."
        )
    )
    handler._data_interpretation._bindings = replace(
        handler._data_interpretation._bindings,
        present_unexpected_error=present_error,
    )

    outcome = handler._data_interpretation._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=MagicMock(),
        error_title="Review failed",
    )
    assert outcome is not None
    assert outcome.status is InteractionStatus.ACCEPTED

    qtbot.waitUntil(lambda: present_error.call_count == 1, timeout=1000)
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel) == 0,
        timeout=1000,
    )
    assert present_error.call_args.args[1].value.title == "Interpretation review failed"
    assert present_error.return_value == (
        "XBrainLab could not prepare the Data Import review. "
        "Reopen the source and try again."
    )
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
    assert statuses == ["Preparing selected EEG data..."]
    assert elapsed < 0.1
    assert len(loading_dialogs) == 1
    assert loading_dialogs[0].visible is True
    assert worker_started.wait(timeout=1.0)
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    loading_token = handler._data_interpretation._loading_session.token
    worker_release.set()
    qtbot.waitUntil(lambda: continue_flow.call_count == 1, timeout=1000)
    assert loading_dialogs[0].closed is False
    assert continue_flow.call_args.kwargs["loading_token"] is loading_token
    assert statuses == ["Preparing selected EEG data...", "Import review ready."]
    handler._data_interpretation._close_loading_dialog(loading_token)


def test_review_keeps_atomic_loading_ownership_across_slow_preview_construction(
    qtbot,
    monkeypatch,
) -> None:
    """A slow constructor must not create a loader-to-preview visibility gap."""
    window = QMainWindow()
    panel = QWidget(window)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    qtbot.addWidget(window)
    window.show()
    handler = DatasetActionHandler(panel)
    preview_results: list[int] = []
    preview_instances: list[QDialog] = []
    release_visibility: list[bool] = []
    original_close_loading = handler._data_interpretation._close_loading_dialog

    def record_loading_release(token=None) -> None:
        if token is not None and preview_instances:
            release_visibility.append(preview_instances[-1].isVisible())
        original_close_loading(token)

    monkeypatch.setattr(
        handler._data_interpretation,
        "_close_loading_dialog",
        record_loading_release,
    )

    class _SlowPreviewDialog(QDialog):
        def __init__(self, parent, **_kwargs) -> None:
            super().__init__(parent)
            preview_instances.append(self)
            loading = handler._data_interpretation._loading_session.dialog
            progress = getattr(loading, "progress_bar", None)
            assert loading is not None and loading.isVisible()
            assert progress is not None
            assert progress.property("operationId") == "review-operation-1"
            time.sleep(5.1)
            assert loading is handler._data_interpretation._loading_session.dialog
            assert loading.isVisible()
            assert progress.property("operationId") == "review-operation-1"

        def exec(self) -> int:
            assert self.isVisible()
            self.reject()
            result = self.result()
            preview_results.append(int(result))
            return result

        @staticmethod
        def get_result() -> dict[str, Any]:
            return {}

    result = _success_result(
        "review_interpretation",
        scan_result={"scan_id": "scan-1"},
        preview={"summary": "ready"},
        candidate={"candidate_id": "candidate-1"},
        validation_decision={"candidate_id": "candidate-1", "decision": "safe"},
    )

    class _Service:
        @staticmethod
        def begin_owned_operation(command):
            assert isinstance(command, ReviewInterpretationCommand)
            return SimpleNamespace(operation_id="review-operation-1")

        @staticmethod
        def get_owned_operation(operation_id):
            assert operation_id == "review-operation-1"
            return SimpleNamespace(
                phase=SimpleNamespace(value="running"),
                stage="Building import review",
                completed=None,
                total=None,
                cancel_requested=False,
                cancellable=True,
            )

        @staticmethod
        def cancel_owned_operation(_operation_id):
            return True

        @staticmethod
        def fail_owned_operation(operation_id, *, message):
            raise AssertionError((operation_id, message))

        @staticmethod
        def execute(
            command,
            *,
            expected_publication_generation=None,
            operation_id=None,
        ):
            assert isinstance(command, ReviewInterpretationCommand)
            assert expected_publication_generation is None
            assert operation_id == "review-operation-1"
            return result

        @staticmethod
        def get_view_publication():
            return _review_publication(candidate_id="candidate-1")

    handler._data_interpretation._preview_dialog_class = lambda: _SlowPreviewDialog
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
    assert outcome.status is InteractionStatus.ACCEPTED
    qtbot.waitUntil(lambda: bool(preview_results), timeout=8_000)
    assert preview_results == [int(QDialog.DialogCode.Rejected)]
    assert release_visibility == [True]
    assert handler._data_interpretation._loading_session is None


def test_loading_dialog_projects_owned_operation_kind(qtbot) -> None:
    window = QMainWindow()
    panel = QWidget(window)
    qtbot.addWidget(window)
    window.show()
    handler = DatasetActionHandler(panel)
    coordinator = handler._data_interpretation
    token = coordinator._open_loading_dialog(
        initial_step="",
        retry=lambda: None,
    )
    assert coordinator._loading_session is not None
    coordinator._loading_session.operation_id = "apply-operation-1"
    coordinator._bindings = replace(
        coordinator._bindings,
        get_application_operation=lambda _owner, _operation_id: SimpleNamespace(
            kind=OwnedWorkKind.IMPORT_APPLY,
            phase=SimpleNamespace(value="running"),
            stage="Loading reviewed EEG recordings",
            completed=1,
            total=3,
            cancel_requested=False,
        ),
    )

    coordinator._present_loading_operation_snapshot(
        "apply-operation-1",
        coordinator._bindings.get_application_operation(panel, "apply-operation-1"),
    )

    assert coordinator._loading_session is not None
    loading = coordinator._loading_session.dialog
    assert loading is not None
    assert loading.progress_bar.property("operationKind") == "import_apply"
    coordinator._close_loading_dialog(token)


def test_preview_constructor_failure_keeps_recoverable_loading_error(
    qtbot,
) -> None:
    window = QMainWindow()
    panel = QWidget(window)
    qtbot.addWidget(window)
    window.show()
    handler = DatasetActionHandler(panel)
    token = handler._data_interpretation._open_loading_dialog(
        initial_step="",
        retry=lambda: None,
    )
    assert handler._data_interpretation._loading_session is not None
    loading = handler._data_interpretation._loading_session.dialog
    assert loading is not None

    class _BrokenPreviewDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("preview fixture failed")

    handler._data_interpretation._preview_dialog_class = lambda: _BrokenPreviewDialog

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(),
        loading_token=token,
    )

    assert outcome.status is InteractionStatus.FAILED
    assert handler._data_interpretation._loading_session is not None
    assert handler._data_interpretation._loading_session.token is token
    assert handler._data_interpretation._loading_session.dialog is loading
    assert loading.isVisible()
    assert loading.status_title.text() == "Import review could not be prepared"
    assert loading.retry_button.isVisible()
    assert not loading.progress_bar.isVisible()
    handler._data_interpretation._close_loading_dialog(token)


@pytest.mark.parametrize("transition", ("cancel", "shutdown"))
def test_preview_does_not_exec_after_transition_context_is_invalidated(
    transition: str,
    qtbot,
) -> None:
    window = QMainWindow()
    panel = QWidget(window)
    qtbot.addWidget(window)
    window.show()
    handler = DatasetActionHandler(panel)
    token = handler._data_interpretation._open_loading_dialog(
        initial_step="",
        retry=lambda: None,
    )
    exec_calls: list[bool] = []

    class _InvalidatingPreviewDialog(QDialog):
        def __init__(self, parent, **_kwargs) -> None:
            super().__init__(parent)
            if transition == "cancel":
                handler._data_interpretation._cancel_loading_dialog(token)
            else:
                window._closing_in_progress = True  # type: ignore[attr-defined]

        def exec(self) -> int:
            exec_calls.append(True)
            return int(QDialog.DialogCode.Rejected)

    handler._data_interpretation._preview_dialog_class = (
        lambda: _InvalidatingPreviewDialog
    )

    outcome = handler._data_interpretation._continue_data_interpretation_import(
        source_path="/data",
        source_hint="bids",
        choices={},
        label_sources=[],
        review_state=_review_state(),
        loading_token=token,
    )

    assert outcome.status is InteractionStatus.CANCELLED
    assert exec_calls == []
    assert handler._data_interpretation._loading_session is None


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
    assert handler._data_interpretation._loading_session is not None
    dialog = handler._data_interpretation._loading_session.dialog
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
    cancelled_operations: list[str] = []

    class _Service:
        def begin_owned_operation(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            return SimpleNamespace(operation_id="review-operation-1")

        def cancel_owned_operation(self, operation_id):
            cancelled_operations.append(operation_id)
            return True

        def get_owned_operation(self, operation_id):
            assert operation_id == "review-operation-1"
            return SimpleNamespace(
                phase=SimpleNamespace(value="running"),
                stage="Reading BIDS events",
                completed=2,
                total=5,
                cancel_requested=False,
            )

        def fail_owned_operation(self, operation_id, *, message):
            raise AssertionError((operation_id, message))

        def execute(
            self,
            command,
            *,
            expected_publication_generation=None,
            operation_id=None,
        ):
            assert isinstance(command, ReviewInterpretationCommand)
            assert expected_publication_generation is None
            assert operation_id == "review-operation-1"
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
            self.stages: list[tuple[str, str]] = []
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
            self.stages.append((_title, _detail))

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
    assert handler._data_interpretation._loading_session is not None
    loading = handler._data_interpretation._loading_session.dialog
    loading.cancelled_by_user = True
    loading.rejected.emit()
    assert cancelled_operations == ["review-operation-1"]
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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
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
    monkeypatch.setattr(actions, "ask_confirmation", question)
    monkeypatch.setattr(actions, "show_error", critical)

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
    monkeypatch.setattr(actions, "ask_confirmation", question)
    monkeypatch.setattr(actions, "show_error", critical)

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
    monkeypatch.setattr(actions, "ask_confirmation", question)
    monkeypatch.setattr(actions, "show_error", critical)

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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: False,
    )
    status = MagicMock()
    monkeypatch.setattr(handler, "_show_status", status)
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
    assert status.call_args_list == [
        call("Dataset import cancelled"),
    ]


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
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
    )
    warning = MagicMock()
    monkeypatch.setattr(actions, "show_warning", warning)
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
    monkeypatch.setattr(actions, "ask_confirmation", question)

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
    monkeypatch.setattr(actions, "show_error", critical)
    monkeypatch.setattr(actions, "ask_confirmation", question)

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
    monkeypatch.setattr(actions, "show_warning", warning)

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
    monkeypatch.setattr(actions, "show_warning", warning)

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
    question = MagicMock(return_value=False)
    monkeypatch.setattr(
        actions,
        "get_command_review_context",
        lambda *_args: _missing_capability_review(),
    )
    monkeypatch.setattr(actions, "ask_confirmation", question)

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
    monkeypatch.setattr(actions, "show_warning", warning)

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
    monkeypatch.setattr(actions, "show_warning", warning)

    handler.open_smart_parser()

    query.assert_not_called()
    dialog.assert_not_called()
    warning.assert_called_once()
