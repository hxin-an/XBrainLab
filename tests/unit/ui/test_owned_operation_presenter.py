from __future__ import annotations

from types import SimpleNamespace

from PyQt6 import sip
from PyQt6.QtWidgets import QMainWindow, QPushButton, QWidget

from XBrainLab.backend.application.owned_work import OwnedWorkKind
from XBrainLab.ui.owned_operation_presenter import OwnedOperationPresenter
from XBrainLab.ui.status import publish_owned_operation_progress, show_status_message


def _snapshot(
    phase: str,
    *,
    kind: OwnedWorkKind = OwnedWorkKind.PREPROCESS,
    stage: str = "Reading EEG files",
    message: str = "",
    completed: int | None = None,
    total: int | None = None,
    cancel_requested: bool = False,
):
    return SimpleNamespace(
        kind=kind,
        phase=SimpleNamespace(value=phase),
        stage=stage,
        message=message,
        completed=completed,
        total=total,
        indeterminate=completed is None or total is None,
        cancel_requested=cancel_requested,
        cancellable=True,
    )


def test_presenter_shows_real_stage_progress_and_nonblocking_cancel(qtbot) -> None:
    window = QMainWindow()
    owner = QWidget(window)
    cancel = QPushButton("Cancel", owner)
    snapshots = {"operation-1": _snapshot("running", completed=2, total=5)}
    cancellations: list[str] = []
    presenter = OwnedOperationPresenter(
        owner,
        cancel_button=cancel,
        snapshot_getter=snapshots.get,
        canceller=lambda operation_id: cancellations.append(operation_id) or True,
        interval_ms=10_000,
    )
    qtbot.addWidget(window)
    window.show()

    presenter.bind("operation-1", stage="Preparing import")
    presenter.refresh()

    status = window.statusBar()
    assert status.currentMessage() == "Reading EEG files · 2/5"
    assert status.property("operationId") == "operation-1"
    assert status.property("operationKind") == "preprocess"
    assert status.property("progress") == "2/5"
    cancel.click()
    assert cancellations == ["operation-1"]

    snapshots["operation-1"] = _snapshot(
        "cancelled",
        cancel_requested=True,
    )
    presenter.refresh()
    assert presenter.active_operation_id is None
    assert status.currentMessage() == ""


def test_import_apply_keeps_stable_status_while_exact_stage_changes(qtbot) -> None:
    window = QMainWindow()
    owner = QWidget(window)
    cancel = QPushButton("Cancel", owner)
    snapshots = {
        "operation-apply": _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_APPLY,
            stage="Binding reviewed import resource scope",
        )
    }
    presenter = OwnedOperationPresenter(
        owner,
        cancel_button=cancel,
        snapshot_getter=snapshots.get,
        canceller=lambda _operation_id: True,
        interval_ms=10_000,
    )
    qtbot.addWidget(window)
    window.show()

    presenter.bind("operation-apply", stage="Preparing import")
    status = window.statusBar()
    expected_message = "Importing reviewed EEG data · Working…"

    for stage in (
        "Estimating reviewed import resources",
        "Inspecting reviewed label resource 1 of 10",
        "Hashing reviewed import content",
        "Loading EEG recording 1 of 10",
        "Applying reviewed label carriers",
    ):
        snapshots["operation-apply"] = _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_APPLY,
            stage=stage,
        )
        presenter.refresh()
        assert status.currentMessage() == expected_message
        assert status.property("stage") == stage
        assert status.property("operationDetail") == stage


def test_import_review_keeps_stable_status_while_exact_stage_changes(qtbot) -> None:
    window = QMainWindow()
    owner = QWidget(window)
    cancel = QPushButton("Cancel", owner)
    snapshots = {
        "operation-review": _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_REVIEW,
            stage="Scanning selected BIDS files",
        )
    }
    presenter = OwnedOperationPresenter(
        owner,
        cancel_button=cancel,
        snapshot_getter=snapshots.get,
        canceller=lambda _operation_id: True,
        interval_ms=10_000,
    )
    qtbot.addWidget(window)
    window.show()

    presenter.bind("operation-review", stage="Preparing review")
    status = window.statusBar()
    expected_message = "Checking selected EEG data · Working…"

    for stage in (
        "Inspecting import resource 1 of 10",
        "Reading BIDS recording metadata 2 of 5",
        "Building reviewed label matches",
    ):
        snapshots["operation-review"] = _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_REVIEW,
            stage=stage,
        )
        presenter.refresh()
        assert status.currentMessage() == expected_message
        assert status.property("stage") == stage
        assert status.property("operationDetail") == stage
        assert status.accessibleDescription() == stage


def test_import_apply_bounds_snapshot_detail_and_preserves_cancel_terminal(
    qtbot,
) -> None:
    window = QMainWindow()
    owner = QWidget(window)
    cancel = QPushButton("Cancel", owner)
    stage = "Loading EEG recording 2 of 10 " * 20
    snapshots = {
        "operation-apply": _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_APPLY,
            stage=stage,
            message="separate snapshot message",
            completed=2,
            total=10,
        )
    }
    presenter = OwnedOperationPresenter(
        owner,
        cancel_button=cancel,
        snapshot_getter=snapshots.get,
        canceller=lambda _operation_id: True,
        interval_ms=10_000,
    )
    qtbot.addWidget(window)
    window.show()

    presenter.bind("operation-apply", stage="Preparing import")
    status = window.statusBar()
    assert status.currentMessage() == "Importing reviewed EEG data · 20%"
    assert status.property("stage") == stage
    assert 0 < len(status.property("operationDetail")) <= 240
    assert status.accessibleDescription() == status.property("operationDetail")

    snapshots["operation-apply"] = _snapshot(
        "cancelling",
        kind=OwnedWorkKind.IMPORT_APPLY,
        stage=stage,
        cancel_requested=True,
    )
    presenter.refresh()
    assert status.currentMessage() == "Cancelling · Importing reviewed EEG data"
    assert status.property("stage") == stage
    assert 0 < len(status.property("operationDetail")) <= 240
    assert status.accessibleDescription() == status.property("operationDetail")

    snapshots["operation-apply"] = _snapshot(
        "cancelled",
        kind=OwnedWorkKind.IMPORT_APPLY,
        stage=stage,
        cancel_requested=True,
    )
    presenter.refresh()
    assert presenter.active_operation_id is None
    assert status.currentMessage() == ""
    assert status.accessibleDescription() == ""


def test_typed_import_apply_immediately_replaces_transient_and_stays_visible(
    qtbot,
) -> None:
    window = QMainWindow()
    owner = QWidget(window)
    cancel = QPushButton("Cancel", owner)
    stage = "Hashing reviewed import content"
    snapshots = {
        "operation-apply": _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_APPLY,
            stage=stage,
            completed=1,
            total=4,
        )
    }
    presenter = OwnedOperationPresenter(
        owner,
        cancel_button=cancel,
        snapshot_getter=snapshots.get,
        canceller=lambda _operation_id: True,
        interval_ms=10_000,
    )
    qtbot.addWidget(window)
    window.show()
    status = window.statusBar()
    assert show_status_message(window, "Import review ready", 7_000)

    presenter.bind("operation-apply", stage="Preparing import")

    qtbot.wait(0)
    assert status.currentMessage() == "Importing reviewed EEG data · 25%"
    assert status.property("operationId") == "operation-apply"
    assert status.property("operationKind") == "import_apply"
    assert status.property("stage") == stage
    assert status.property("operationDetail") == stage

    for completed, next_stage in (
        (2, "Loading reviewed EEG recording 2 of 4"),
        (3, "Applying reviewed label carriers"),
    ):
        snapshots["operation-apply"] = _snapshot(
            "running",
            kind=OwnedWorkKind.IMPORT_APPLY,
            stage=next_stage,
            completed=completed,
            total=4,
        )
        presenter.refresh()
        qtbot.wait(0)
        assert status.currentMessage() == (
            f"Importing reviewed EEG data · {completed * 25}%"
        )
        assert status.property("operationId") == "operation-apply"
        assert status.property("stage") == next_stage
        assert status.property("operationDetail") == next_stage


def test_owned_progress_does_not_overwrite_higher_priority_transient(qtbot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    assert show_status_message(window, "Training failed · Adjust settings", 5_000)

    assert publish_owned_operation_progress(
        window,
        operation_id="operation-1",
        kind="saliency",
        stage="Computing saliency",
        phase="running",
    )

    assert window.statusBar().currentMessage() == "Training failed · Adjust settings"
    assert window.statusBar().property("stage") == "Computing saliency"
    assert window.statusBar().property("operationKind") == "saliency"

    qtbot.waitUntil(
        lambda: window.statusBar().currentMessage() == "Computing saliency · Working…",
        timeout=1500,
    )


def test_deferred_owned_progress_ignores_deleted_status_bar(
    qtbot,
    monkeypatch,
) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    status = window.statusBar()
    assert show_status_message(window, "Training failed", 5_000)
    assert publish_owned_operation_progress(
        window,
        operation_id="operation-deleted-status",
        stage="Computing saliency",
        phase="running",
    )

    status.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(status), timeout=1_000)
    # SIP's liveness probe is advisory at the callback boundary: teardown can
    # invalidate the wrapped C++ child between the probe and the first Qt
    # method call.  The deferred callback must still fail closed.
    monkeypatch.setattr(
        "XBrainLab.ui.status.sip.isdeleted",
        lambda _status_bar: False,
    )
    qtbot.wait(1_100)
