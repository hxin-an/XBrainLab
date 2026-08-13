from __future__ import annotations

from types import SimpleNamespace

from PyQt6 import sip
from PyQt6.QtWidgets import QMainWindow, QPushButton, QWidget

from XBrainLab.ui.owned_operation_presenter import OwnedOperationPresenter
from XBrainLab.ui.status import publish_owned_operation_progress, show_status_message


def _snapshot(
    phase: str,
    *,
    stage: str = "Reading EEG files",
    completed: int | None = None,
    total: int | None = None,
    cancel_requested: bool = False,
):
    return SimpleNamespace(
        phase=SimpleNamespace(value=phase),
        stage=stage,
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


def test_owned_progress_does_not_overwrite_higher_priority_transient(qtbot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    assert show_status_message(window, "Training failed · Adjust settings", 5_000)

    assert publish_owned_operation_progress(
        window,
        operation_id="operation-1",
        stage="Computing saliency",
        phase="running",
    )

    assert window.statusBar().currentMessage() == "Training failed · Adjust settings"
    assert window.statusBar().property("stage") == "Computing saliency"

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
