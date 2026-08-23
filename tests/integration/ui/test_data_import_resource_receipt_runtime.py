"""Real Qt coverage for Data Interpretation resource-warning receipts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QWidget

from scripts.dev.fetch_public_eeg_fixtures import resolve_public_fixture_dir
from tests.integration.ui.modal_helpers import visible_modal_dialog
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ErrorType,
    ReviewInterpretationCommand,
    get_application_service,
    resource_guard,
)
from XBrainLab.backend.application.resource_guard import (
    check_import_resource_preflight,
)
from XBrainLab.backend.application.resource_preflight import (
    ResourceConfirmationChallenge,
    ResourcePreflightView,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.components.modal_presentation import ModalAlertDialog
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionEvent,
    InteractionCompletionSession,
    InteractionCompletionStatus,
    InteractionStatus,
    bind_interaction_completion,
)
from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler
from XBrainLab.ui.panels.dataset.data_interpretation_action_coordinator import (
    _InterpretationReviewState,
)

PUBLIC_DATA_DIR = resolve_public_fixture_dir()
MNE_BIDS_ROOT = PUBLIC_DATA_DIR / "mne-bids-tiny-eeg"
MNE_BIDS_EEG_DIR = MNE_BIDS_ROOT / "sub-01" / "ses-eeg" / "eeg"
MNE_BIDS_EEG = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_eeg.vhdr"
MNE_BIDS_EVENTS = MNE_BIDS_EEG_DIR / "sub-01_ses-eeg_task-rest_events.tsv"

pytestmark = [
    pytest.mark.optional_public_fixture,
    pytest.mark.usefixtures("allow_real_modals"),
]
IMPORT_COMPLETION_TIMEOUT_MS = 45_000


class _PassiveRefreshProbe:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.dirty_count = 0

    def update_panel(self) -> None:
        self.refresh_count += 1

    def mark_refresh_dirty(self) -> None:
        self.dirty_count += 1


class _RuntimeHost(QWidget):
    def __init__(self, study: Study) -> None:
        super().__init__()
        self.study = study
        self.stack = object()
        self.info_refresh_count = 0
        self.dataset_panel: _DatasetRefreshProbe | None = None
        self.preprocess_panel = _PassiveRefreshProbe()
        self.training_panel = _PassiveRefreshProbe()
        self.evaluation_panel = _PassiveRefreshProbe()
        self.visualization_panel = _PassiveRefreshProbe()

    def update_info_panel(self) -> None:
        self.info_refresh_count += 1


class _DatasetRefreshProbe(BasePanel):
    def __init__(self, *, parent: _RuntimeHost, controller: Any) -> None:
        self.refresh_count = 0
        self.dirty_count = 0
        super().__init__(parent=parent, controller=controller)
        self._create_refresh_bridge(controller, "data_changed")

    def update_panel(self, *_args: Any, **_kwargs: Any) -> None:
        self.refresh_count += 1

    def mark_refresh_dirty(self) -> None:
        self.dirty_count += 1


@dataclass
class _MessageBoxAnswer:
    timer: QTimer
    observed: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class _ImportRuntime:
    study: Study
    service: ApplicationService
    host: _RuntimeHost
    panel: _DatasetRefreshProbe
    handler: DatasetActionHandler
    review_state: _InterpretationReviewState
    candidate_id: str
    import_events: list[tuple[int, list[str]]]


def _bids_choices() -> dict[str, Any]:
    return {
        "selected_eeg_files": [str(MNE_BIDS_EEG)],
        "label_carrier_choices": {
            str(MNE_BIDS_EVENTS): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "value_decisions": {
                    "show_stimulus": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "show_stimulus",
                    },
                    "start_experiment": {
                        "role": "system",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "start_experiment",
                    },
                },
            }
        },
    }


def _build_runtime(qtbot) -> _ImportRuntime:
    if not MNE_BIDS_EEG.exists():
        pytest.skip(
            "MNE-BIDS tiny fixture not downloaded; run "
            "scripts/dev/fetch_public_eeg_fixtures.py first."
        )

    study = Study()
    service = get_application_service(study)
    assert service is get_application_service(study)

    review_result = service.execute(
        ReviewInterpretationCommand(
            source_path=str(MNE_BIDS_ROOT),
            source_hint="bids",
            choices=_bids_choices(),
        )
    )
    assert review_result.ok, review_result.message

    host = _RuntimeHost(study)
    qtbot.addWidget(host)
    controller = study.get_controller("dataset")
    panel = _DatasetRefreshProbe(parent=host, controller=controller)
    host.dataset_panel = panel
    handler = DatasetActionHandler(panel)
    review_state = handler._data_interpretation._review_state_from_review_result(
        review_result
    )
    candidate_id = review_state.candidate_id
    assert candidate_id

    import_events: list[tuple[int, list[str]]] = []
    controller.subscribe(
        "import_finished",
        lambda count, errors: import_events.append((int(count), list(errors))),
    )
    host.resize(640, 480)
    panel.resize(620, 460)
    host.show()
    panel.show()
    qtbot.wait(0)
    return _ImportRuntime(
        study=study,
        service=service,
        host=host,
        panel=panel,
        handler=handler,
        review_state=review_state,
        candidate_id=candidate_id,
        import_events=import_events,
    )


def _candidate_resource_paths(review_state: _InterpretationReviewState) -> list[str]:
    candidate = review_state.candidate
    identity = candidate.get("content_identity")
    identity_files = identity.get("files", []) if isinstance(identity, dict) else []
    paths = [
        *(str(path) for path in candidate.get("selected_eeg_files", [])),
        *(str(path) for path in candidate.get("label_carriers", [])),
        *(
            str(row.get("path"))
            for row in identity_files
            if isinstance(row, dict) and row.get("path")
        ),
    ]
    return list(dict.fromkeys(paths))


def _force_warning_preflight(
    monkeypatch: pytest.MonkeyPatch,
    review_state: _InterpretationReviewState,
) -> int:
    preflight = check_import_resource_preflight(_candidate_resource_paths(review_state))
    required = int(preflight.diagnostics["estimated_ram_working_set_bytes"])
    assert required > 0
    available = max(required + 1, (required * 10) // 7)
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: available)
    return available


def _issue_apply_challenge(runtime: _ImportRuntime) -> ResourceConfirmationChallenge:
    result = runtime.service.execute(
        ApplyInterpretationCommand(
            candidate_id=runtime.candidate_id,
            confirmed=True,
        )
    )
    preflight = ResourcePreflightView.from_diagnostics(result.diagnostics)
    assert result.failed is True
    assert result.error_type is ErrorType.CONFIRMATION_REQUIRED
    assert preflight is not None
    assert preflight.risk_level == "warning"
    assert preflight.challenge is not None
    assert preflight.challenge.command_name == "apply_interpretation"
    assert runtime.study.loaded_data_list == []
    assert runtime.import_events == []
    assert _pending_receipt(runtime, preflight.challenge) is not None
    return preflight.challenge


def _pending_receipt(
    runtime: _ImportRuntime,
    challenge: ResourceConfirmationChallenge,
) -> Any | None:
    interpretation = runtime.service.interpretation._service()
    return interpretation._import_preflight_receipts.peek(
        challenge.challenge_id,
        scope_fingerprint=challenge.scope_fingerprint,
        candidate_id=challenge.candidate_id,
        preflight_fingerprint=challenge.preflight_fingerprint,
    )


def _answer_next_message_box(
    button: QMessageBox.StandardButton,
    *,
    before_click: Callable[[], None] | None = None,
) -> _MessageBoxAnswer:
    answer = _MessageBoxAnswer(timer=QTimer())
    answer.timer.setInterval(5)

    def _poll() -> None:
        widget = visible_modal_dialog()
        if not isinstance(widget, ModalAlertDialog):
            return
        target = (
            widget.confirm_button
            if button is QMessageBox.StandardButton.Yes
            else widget.cancel_button
        )
        if target is None:
            answer.errors.append(f"Message box did not expose {button!r}.")
            widget.reject()
            answer.timer.stop()
            return
        answer.observed.append((widget.windowTitle(), widget.message_label.text()))
        if before_click is not None:
            before_click()
        target.click()
        answer.timer.stop()

    answer.timer.timeout.connect(_poll)
    answer.timer.start()
    return answer


def _start_apply(
    runtime: _ImportRuntime,
    terminal: list[InteractionCompletionEvent],
) -> None:
    completion = InteractionCompletionSession(
        request_id="data-import-resource-warning",
        command_name="apply_interpretation",
        on_terminal=terminal.append,
    )
    with bind_interaction_completion(completion):
        outcome = runtime.handler._data_interpretation._apply_interpretation_async(
            runtime.review_state,
            {"confirmed": True, "save_recipe": False},
        )
    assert outcome.status is InteractionStatus.ACCEPTED


def _wait_for_commands(qtbot, runtime: _ImportRuntime) -> None:
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(runtime.panel) == 0,
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    qtbot.wait(200)


def test_warning_confirmation_retries_exact_receipt_and_mutates_once(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _build_runtime(qtbot)
    _force_warning_preflight(monkeypatch, runtime.review_state)
    challenge = _issue_apply_challenge(runtime)
    publication_before = runtime.service.get_view_publication()
    answer = _answer_next_message_box(QMessageBox.StandardButton.Yes)
    terminal: list[InteractionCompletionEvent] = []

    _start_apply(runtime, terminal)

    qtbot.waitUntil(
        lambda: len(terminal) == 1,
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    qtbot.waitUntil(
        lambda: len(runtime.study.loaded_data_list) == 1,
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    _wait_for_commands(qtbot, runtime)

    assert answer.errors == []
    assert len(answer.observed) == 1
    assert answer.observed[0][0] == "Dataset Resource Check"
    assert "Continue importing this dataset?" in answer.observed[0][1]
    assert terminal[0].status is InteractionCompletionStatus.COMPLETED
    publication_after = runtime.service.get_view_publication()
    assert publication_after.generation == publication_before.generation + 1
    assert publication_after.state.active_dataset.has_raw_data is True
    # Product imports publish application truth once; legacy controller events
    # must not create a second state-changing refresh path.
    assert runtime.import_events == []
    assert runtime.panel.refresh_count == 0
    assert runtime.panel.dirty_count == 0
    assert Path(runtime.study.loaded_data_list[0].get_filepath()).resolve() == (
        MNE_BIDS_EEG.resolve()
    )
    assert _pending_receipt(runtime, challenge) is None
    assert runtime.import_events == []
    assert len(runtime.study.loaded_data_list) == 1
    assert len(terminal) == 1
    assert runtime.panel.refresh_count == 0


def test_warning_refusal_has_no_mutation_and_one_cancelled_terminal(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _build_runtime(qtbot)
    _force_warning_preflight(monkeypatch, runtime.review_state)
    challenge = _issue_apply_challenge(runtime)
    answer = _answer_next_message_box(QMessageBox.StandardButton.No)
    terminal: list[InteractionCompletionEvent] = []

    _start_apply(runtime, terminal)

    qtbot.waitUntil(
        lambda: len(terminal) == 1,
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    _wait_for_commands(qtbot, runtime)

    assert answer.errors == []
    assert len(answer.observed) == 1
    assert terminal[0].status is InteractionCompletionStatus.CANCELLED
    assert "cancelled" in terminal[0].message.lower()
    assert runtime.study.loaded_data_list == []
    assert runtime.import_events == []
    assert runtime.panel.refresh_count == 0
    assert runtime.panel.dirty_count == 0
    assert _pending_receipt(runtime, challenge) is not None
    assert len(terminal) == 1


def test_owner_deletion_before_confirmed_retry_drops_late_mutation(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _build_runtime(qtbot)
    _force_warning_preflight(monkeypatch, runtime.review_state)
    challenge = _issue_apply_challenge(runtime)
    answer = _answer_next_message_box(
        QMessageBox.StandardButton.Yes,
        before_click=runtime.panel.deleteLater,
    )
    terminal: list[InteractionCompletionEvent] = []

    _start_apply(runtime, terminal)

    qtbot.waitUntil(
        lambda: sip.isdeleted(runtime.panel),
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    qtbot.waitUntil(
        lambda: len(terminal) == 1,
        timeout=IMPORT_COMPLETION_TIMEOUT_MS,
    )
    _wait_for_commands(qtbot, runtime)

    assert answer.errors == []
    assert len(answer.observed) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert runtime.study.loaded_data_list == []
    assert runtime.import_events == []
    assert _pending_receipt(runtime, challenge) is not None
    assert len(terminal) == 1
