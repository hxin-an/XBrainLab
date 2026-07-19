"""Low-mock runtime coverage for terminal training UI publication."""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Event, Thread, get_ident
from typing import Any, cast

import mne
import numpy as np
import pytest
import torch
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ChangedState,
    CommandResult,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
)
from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.controller.training_controller import TrainingLifecycleEvent
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.training_plan import TrainingPlanHolder
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    TrainingOutcomeState,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.ui import refresh_coordinator
from XBrainLab.ui.async_command_runner import (
    AsyncCommandRegistry,
    QtApplicationCommandRunner,
    application_command_registry,
)
from XBrainLab.ui.main_window import MainWindow


def _write_synthetic_raw_fif(tmp_path: Path) -> Path:
    """Write the canonical deterministic four-channel, twelve-event fixture."""
    sfreq = 128
    n_channels = 4
    duration = 26
    ch_names = [f"EEG{i}" for i in range(n_channels)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(42).normal(
        size=(n_channels, sfreq * duration),
    )
    raw = mne.io.RawArray(data, info)
    events = np.array(
        [
            [second * sfreq, 0, 1 if index % 2 == 0 else 2]
            for index, second in enumerate(range(1, 25, 2))
        ],
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        )
    )

    path = tmp_path / "synthetic_raw.fif"
    raw.save(path, overwrite=True)
    return path


def _prepare_training_runtime(tmp_path: Path):
    study = Study()
    service = get_application_service(study)
    assert service is get_application_service(study)
    fif_path = _write_synthetic_raw_fif(tmp_path)
    commands = (
        LoadDataCommand(paths=[str(fif_path)]),
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
        CreateEpochCommand(
            t_min=0.0,
            t_max=1.3,
            event_ids=["left", "right"],
        ),
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(model_name="EEGNet"),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(tmp_path / "training-output"),
            save_checkpoints_every=0,
            evaluation_option="val_acc",
        ),
    )
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message
    return study, service


def _open_runtime_panels(qtbot, study: Study) -> Any:
    window = cast(Any, MainWindow(study))
    qtbot.addWidget(window)
    window.resize(1220, 820)
    window.show()
    qtbot.waitExposed(window)

    for page_index in (2, 3, 4, 2):
        ready_panels = []
        window.switch_page(page_index, on_ready=ready_panels.append)
        qtbot.waitUntil(
            lambda panels=ready_panels: len(panels) == 1,
            timeout=5_000,
        )

    assert window.training_panel.sidebar.btn_start.isEnabled()
    assert window.evaluation_panel.last_application_query is not None
    assert window.visualization_panel.last_application_query is not None
    assert window.visualization_panel.last_saliency_query is not None
    return window


def _cached_gradient_coverage(window: Any):
    publication = window.visualization_panel._application_view_publication
    if publication is None:
        return None
    runs = publication.state.visualization.saliency_coverage
    if len(runs) != 1:
        return None
    return next(
        (item for item in runs[0].methods if item.method == "Gradient"),
        None,
    )


def _terminal_ui_has_refreshed(
    window: Any,
    *,
    initial_evaluation_query: object,
    initial_visualization_query: object,
    initial_saliency_query: object,
) -> bool:
    training = window.training_panel
    evaluation = window.evaluation_panel
    visualization = window.visualization_panel
    return bool(
        training.history_table.rowCount() == 1
        and training.history_table.item(0, 3) is not None
        and evaluation.last_application_query is not initial_evaluation_query
        and visualization.last_application_query is not initial_visualization_query
        and visualization.last_saliency_query is not initial_saliency_query
        and application_command_registry().active_count(training.sidebar) == 0
    )


def _analysis_panels_show_training_state(
    window: Any,
    state: TrainingOutcomeState,
) -> bool:
    evaluation_query = window.evaluation_panel.last_application_query
    visualization_query = window.visualization_panel.last_application_query
    return bool(
        evaluation_query is not None
        and visualization_query is not None
        and evaluation_query.state.training.terminal_outcome.state is state
        and visualization_query.state.training.terminal_outcome.state is state
    )


def _install_panel_update_probes(monkeypatch, window: Any) -> dict[str, int]:
    counts = {"training": 0, "evaluation": 0, "visualization": 0}
    for name, panel in (
        ("training", window.training_panel),
        ("evaluation", window.evaluation_panel),
        ("visualization", window.visualization_panel),
    ):
        original = panel.update_panel

        def counted_update(
            *args,
            _name=name,
            _original=original,
            **kwargs,
        ):
            counts[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(panel, "update_panel", counted_update)
    return counts


def _deliver_pending_qt_events() -> None:
    QCoreApplication.sendPostedEvents()
    QCoreApplication.processEvents()


def _emit_lifecycle_events_from_distinct_threads(
    controller: Any,
    ordered_events: tuple[
        tuple[str, TrainingLifecycleEvent],
        tuple[str, TrainingLifecycleEvent],
    ],
) -> None:
    gates = (Event(), Event())
    ready = (Event(), Event())
    emitted = (Event(), Event())
    release_senders = Event()
    sender_ids: list[int] = []
    errors: list[BaseException] = []

    def sender(index: int) -> None:
        sender_ids.append(get_ident())
        ready[index].set()
        try:
            assert gates[index].wait(timeout=5.0)
            event_name, event = ordered_events[index]
            controller.notify(event_name, event)
        except BaseException as exc:  # pragma: no cover - asserted in caller
            errors.append(exc)
        finally:
            emitted[index].set()
            release_senders.wait(timeout=5.0)

    threads = (
        Thread(target=sender, args=(0,), name="training-started-sender"),
        Thread(target=sender, args=(1,), name="training-terminal-sender"),
    )
    for thread in threads:
        thread.start()
    try:
        assert ready[0].wait(timeout=5.0)
        assert ready[1].wait(timeout=5.0)
        gates[0].set()
        assert emitted[0].wait(timeout=5.0)
        gates[1].set()
        assert emitted[1].wait(timeout=5.0)
    finally:
        release_senders.set()
        for thread in threads:
            thread.join(timeout=5.0)

    assert all(not thread.is_alive() for thread in threads)
    assert len(set(sender_ids)) == 2
    assert errors == []


def test_start_training_click_refreshes_all_runtime_panels_and_saliency(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    evaluation = window.evaluation_panel
    visualization = window.visualization_panel
    initial_evaluation_query = evaluation.last_application_query
    initial_visualization_query = visualization.last_application_query
    initial_saliency_query = visualization.last_saliency_query
    initial_publication = visualization._application_view_publication
    assert initial_publication is not None
    terminal_publications = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_publications.append,
    )
    analysis_publications = []
    service.training.subscribe(
        "training_analysis_published",
        analysis_publications.append,
    )
    saliency_started = Event()
    release_saliency = Event()
    compute_saliency_update = TrainingPlanHolder.compute_saliency_update

    def compute_after_terminal_publication(
        holder,
        plan,
        *,
        should_cancel=None,
    ):
        saliency_started.set()
        assert release_saliency.wait(timeout=30.0)
        return compute_saliency_update(
            holder,
            plan,
            should_cancel=should_cancel,
        )

    monkeypatch.setattr(
        TrainingPlanHolder,
        "compute_saliency_update",
        compute_after_terminal_publication,
    )

    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(saliency_started.is_set, timeout=15_000)

    def training_terminal_rendered() -> bool:
        status_item = training.history_table.item(0, 3)
        return bool(
            status_item is not None
            and status_item.text() == "Completed"
            and training.sidebar.btn_start.isEnabled()
            and not training.sidebar.btn_stop.isEnabled()
            and "All training jobs finished." in training.log_text.toPlainText()
            and application_command_registry().active_count(training.sidebar) == 0
        )

    analysis_update_counts: dict[str, int] | None = None
    terminal_evaluation_query = None
    terminal_visualization_query = None
    try:
        qtbot.waitUntil(training_terminal_rendered, timeout=10_000)
        assert analysis_publications == []
        _deliver_pending_qt_events()
        terminal_evaluation_query = evaluation.last_application_query
        terminal_visualization_query = visualization.last_application_query
        analysis_update_counts = _install_panel_update_probes(monkeypatch, window)
    finally:
        release_saliency.set()

    def assert_terminal_ui() -> None:
        assert _terminal_ui_has_refreshed(
            window,
            initial_evaluation_query=initial_evaluation_query,
            initial_visualization_query=initial_visualization_query,
            initial_saliency_query=initial_saliency_query,
        )
        status_item = training.history_table.item(0, 3)
        assert status_item is not None
        assert status_item.text() == "Completed"
        publication = visualization._application_view_publication
        assert publication is not None
        assert publication.state.visualization.post_training_saliency.phase is (
            PostTrainingSaliencyPhase.SUCCEEDED
        )
        coverage = _cached_gradient_coverage(window)
        assert coverage is not None
        assert coverage.complete

    qtbot.waitUntil(assert_terminal_ui, timeout=20_000)

    history = training.history_table
    assert history.item(0, 3).text() == "Completed"
    assert history.item(0, 4).text() == "1/1"
    assert training.sidebar.btn_start.isEnabled()
    assert not training.sidebar.btn_stop.isEnabled()
    assert training.tab_acc.epochs == [1]
    assert training.tab_loss.epochs == [1]
    assert len(training.tab_acc.train_vals) == 1
    assert len(training.tab_loss.train_vals) == 1
    visible_log = training.log_text.toPlainText()
    assert "All training jobs finished." in visible_log
    assert "Training stopped (event)." in visible_log

    evaluation_query = evaluation.last_application_query
    assert evaluation_query.state.training.terminal_outcome.state is (
        TrainingOutcomeState.COMPLETED
    )
    assert evaluation_query.diagnostics["available"] is True
    assert evaluation_query.diagnostics["finished_run_count"] == 1
    assert evaluation.model_combo.count() == 1
    assert evaluation.run_combo.currentText() == "Repeat 1 (Finished)"

    visualization_query = visualization.last_application_query
    assert visualization_query.diagnostics["trainer_count"] == 1
    assert visualization.plan_combo.currentText().startswith("Fold 1")
    assert visualization.run_combo.currentText() == "Run 1"
    terminal_publication = visualization._application_view_publication
    assert terminal_publication.generation > initial_publication.generation
    terminal_status = terminal_publication.state.visualization.post_training_saliency
    assert terminal_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert set(terminal_status.methods) == {"Gradient", "Gradient * Input"}
    gradient = _cached_gradient_coverage(window)
    assert gradient is not None
    assert gradient.available is True
    assert gradient.complete is True
    assert gradient.classes
    assert all(item.available for item in gradient.classes)
    assert visualization.tab_map._saliency_coverage == gradient
    _deliver_pending_qt_events()
    assert analysis_update_counts == {
        "training": 0,
        "evaluation": 0,
        "visualization": 1,
    }
    assert evaluation.last_application_query is terminal_evaluation_query
    assert visualization.last_application_query is not terminal_visualization_query
    assert len(terminal_publications) == 1
    assert len(analysis_publications) == 1


def test_saliency_completion_replays_once_after_unrelated_nested_commands(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    evaluation = window.evaluation_panel
    visualization = window.visualization_panel
    saliency_started = Event()
    release_saliency = Event()
    analysis_published = Event()
    saliency_published = Event()
    compute_saliency_update = TrainingPlanHolder.compute_saliency_update

    def compute_behind_barrier(
        holder,
        plan,
        *,
        should_cancel=None,
    ):
        saliency_started.set()
        assert release_saliency.wait(timeout=30.0)
        return compute_saliency_update(
            holder,
            plan,
            should_cancel=should_cancel,
        )

    monkeypatch.setattr(
        TrainingPlanHolder,
        "compute_saliency_update",
        compute_behind_barrier,
    )
    service.training.subscribe(
        "training_analysis_published",
        lambda _event: analysis_published.set(),
    )
    service.visualization.subscribe(
        "saliency_changed",
        saliency_published.set,
    )

    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(saliency_started.is_set, timeout=15_000)
    qtbot.waitUntil(
        lambda: (
            training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Completed"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.COMPLETED,
            )
            and application_command_registry().active_count(training.sidebar) == 0
        ),
        timeout=10_000,
    )
    _deliver_pending_qt_events()

    pending_evaluation_query = evaluation.last_application_query
    pending_visualization_query = visualization.last_application_query
    update_counts = _install_panel_update_probes(monkeypatch, window)
    command_registry = AsyncCommandRegistry()
    command_results: list[CommandResult] = []
    command_errors: list[tuple[Any, ...]] = []
    outer_started = Event()
    inner_started = Event()
    release_outer = Event()
    release_inner = Event()

    def blocked_query(started: Event, release: Event) -> CommandResult:
        started.set()
        assert release.wait(timeout=30.0)
        return _query_result()

    outer_runner = QtApplicationCommandRunner(
        context=evaluation,
        command=QueryStateCommand(),
        execute=lambda: blocked_query(outer_started, release_outer),
        on_result=command_results.append,
        on_error=command_errors.append,
        refresh=False,
        busy_target=None,
        allow_during_shutdown=False,
        registry=command_registry,
    )
    inner_runner = QtApplicationCommandRunner(
        context=visualization,
        command=QueryStateCommand(),
        execute=lambda: blocked_query(inner_started, release_inner),
        on_result=command_results.append,
        on_error=command_errors.append,
        refresh=False,
        busy_target=None,
        allow_during_shutdown=False,
        registry=command_registry,
    )

    try:
        assert outer_runner.start() is True
        qtbot.waitUntil(outer_started.is_set, timeout=3_000)
        assert inner_runner.start() is True
        qtbot.waitUntil(inner_started.is_set, timeout=3_000)
        assert refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS[id(window)] == 2

        release_saliency.set()
        qtbot.waitUntil(analysis_published.is_set, timeout=20_000)
        qtbot.waitUntil(saliency_published.is_set, timeout=5_000)
        _deliver_pending_qt_events()
        assert update_counts == {
            "training": 0,
            "evaluation": 0,
            "visualization": 0,
        }
        assert visualization.last_application_query is pending_visualization_query

        release_inner.set()
        qtbot.waitUntil(
            lambda: command_registry.active_count(visualization) == 0,
            timeout=3_000,
        )
        _deliver_pending_qt_events()
        assert refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS[id(window)] == 1
        assert update_counts == {
            "training": 0,
            "evaluation": 0,
            "visualization": 0,
        }

        release_outer.set()
        qtbot.waitUntil(lambda: command_registry.active_count() == 0, timeout=3_000)
        qtbot.waitUntil(
            lambda: update_counts["visualization"] == 1,
            timeout=5_000,
        )
        _deliver_pending_qt_events()
    finally:
        release_saliency.set()
        release_inner.set()
        release_outer.set()

    assert update_counts == {
        "training": 0,
        "evaluation": 0,
        "visualization": 1,
    }
    assert evaluation.last_application_query is pending_evaluation_query
    assert visualization.last_application_query is not pending_visualization_query
    publication = visualization._application_view_publication
    assert publication is not None
    assert publication.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )
    coverage = _cached_gradient_coverage(window)
    assert coverage is not None
    assert coverage.complete
    assert len(command_results) == 2
    assert command_errors == []


def test_start_training_click_publishes_oom_failure_to_all_runtime_panels(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    evaluation = window.evaluation_panel
    visualization = window.visualization_panel
    initial_evaluation_query = evaluation.last_application_query
    initial_visualization_query = visualization.last_application_query
    initial_saliency_query = visualization.last_saliency_query
    terminal_publications = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_publications.append,
    )
    analysis_publications = []
    service.training.subscribe(
        "training_analysis_published",
        analysis_publications.append,
    )

    def raise_oom(_holder, _record) -> None:
        raise torch.cuda.OutOfMemoryError(
            "CUDA out of memory. Tried to allocate 1.00 GiB"
        )

    monkeypatch.setattr(TrainingPlanHolder, "train_one_repeat", raise_oom)

    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)

    def assert_terminal_ui() -> None:
        assert _terminal_ui_has_refreshed(
            window,
            initial_evaluation_query=initial_evaluation_query,
            initial_visualization_query=initial_visualization_query,
            initial_saliency_query=initial_saliency_query,
        )
        status_item = training.history_table.item(0, 3)
        assert status_item is not None
        assert status_item.text() == "Failed"
        assert (
            evaluation.last_application_query.state.training.terminal_outcome.state
            is (TrainingOutcomeState.FAILED)
        )
        assert training.sidebar.btn_start.isEnabled()
        assert not training.sidebar.btn_stop.isEnabled()
        assert "Training failed:" in training.log_text.toPlainText()

    qtbot.waitUntil(assert_terminal_ui, timeout=15_000)

    outcome = evaluation.last_application_query.state.training.terminal_outcome
    assert outcome.state is TrainingOutcomeState.FAILED
    assert outcome.detail is not None
    assert "CUDA out of memory during training" in outcome.detail
    assert evaluation.last_application_query.state.evaluation.finished_runs == 0
    assert evaluation.run_combo.count() == 0

    assert training.history_table.item(0, 3).text() == "Failed"
    assert training.sidebar.btn_start.isEnabled()
    assert not training.sidebar.btn_stop.isEnabled()
    visible_log = training.log_text.toPlainText()
    assert "Training failed:" in visible_log
    assert "batch size" in visible_log.lower()
    assert "input length" in visible_log.lower()

    saliency_query = visualization.last_saliency_query
    assert saliency_query.diagnostics["finished_run_count"] == 0
    publication = visualization._application_view_publication
    assert publication is not None
    assert publication.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.IDLE
    )
    assert _cached_gradient_coverage(window) is None
    assert len(terminal_publications) == 1
    assert analysis_publications == []


def test_delayed_oom_refreshes_every_running_panel_once_at_terminal(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    entered_training = Event()
    release_training = Event()
    terminal_publications = []
    analysis_publications = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_publications.append,
    )
    service.training.subscribe(
        "training_analysis_published",
        analysis_publications.append,
    )

    def delayed_oom(_holder, _record) -> None:
        entered_training.set()
        assert release_training.wait(timeout=30.0)
        raise torch.cuda.OutOfMemoryError(
            "CUDA out of memory. Tried to allocate 1.00 GiB"
        )

    monkeypatch.setattr(TrainingPlanHolder, "train_one_repeat", delayed_oom)
    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(entered_training.is_set, timeout=15_000)
    qtbot.waitUntil(
        lambda: (
            application_command_registry().active_count(training.sidebar) == 0
            and training.history_table.rowCount() == 1
            and training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Running"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.RUNNING,
            )
        ),
        timeout=10_000,
    )
    running_evaluation_query = window.evaluation_panel.last_application_query
    running_visualization_query = window.visualization_panel.last_application_query
    update_counts = _install_panel_update_probes(monkeypatch, window)

    release_training.set()

    qtbot.waitUntil(
        lambda: (
            training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Failed"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.FAILED,
            )
            and "Training stopped (event)." in training.log_text.toPlainText()
        ),
        timeout=15_000,
    )
    _deliver_pending_qt_events()

    assert window.evaluation_panel.last_application_query is not (
        running_evaluation_query
    )
    assert window.visualization_panel.last_application_query is not (
        running_visualization_query
    )
    assert update_counts == {
        "training": 1,
        "evaluation": 1,
        "visualization": 1,
    }
    assert len(terminal_publications) == 1
    assert analysis_publications == []
    assert training.sidebar.btn_start.isEnabled()
    assert not training.sidebar.btn_stop.isEnabled()


def test_delayed_cancellation_refreshes_every_preterminal_panel_once(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    entered_training = Event()
    release_training = Event()
    train_one_repeat = TrainingPlanHolder.train_one_repeat
    terminal_publications = []
    analysis_publications = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_publications.append,
    )
    service.training.subscribe(
        "training_analysis_published",
        analysis_publications.append,
    )

    def delayed_training(holder, record) -> None:
        entered_training.set()
        assert release_training.wait(timeout=30.0)
        train_one_repeat(holder, record)

    monkeypatch.setattr(
        TrainingPlanHolder,
        "train_one_repeat",
        delayed_training,
    )
    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(entered_training.is_set, timeout=15_000)
    qtbot.waitUntil(
        lambda: (
            application_command_registry().active_count(training.sidebar) == 0
            and training.history_table.rowCount() == 1
            and training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Running"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.RUNNING,
            )
        ),
        timeout=10_000,
    )
    qtbot.mouseClick(training.sidebar.btn_stop, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: _analysis_panels_show_training_state(
            window,
            TrainingOutcomeState.STOP_REQUESTED,
        ),
        timeout=10_000,
    )
    stop_requested_evaluation_query = window.evaluation_panel.last_application_query
    stop_requested_visualization_query = (
        window.visualization_panel.last_application_query
    )
    update_counts = _install_panel_update_probes(monkeypatch, window)

    release_training.set()

    qtbot.waitUntil(
        lambda: _analysis_panels_show_training_state(
            window,
            TrainingOutcomeState.CANCELLED,
        ),
        timeout=15_000,
    )
    _deliver_pending_qt_events()

    assert training.history_table.item(0, 3).text() != "Running"
    assert window.evaluation_panel.last_application_query is not (
        stop_requested_evaluation_query
    )
    assert window.visualization_panel.last_application_query is not (
        stop_requested_visualization_query
    )
    assert update_counts == {
        "training": 1,
        "evaluation": 1,
        "visualization": 1,
    }
    assert len(terminal_publications) == 1
    assert analysis_publications == []
    assert training.sidebar.btn_start.isEnabled()
    assert not training.sidebar.btn_stop.isEnabled()
    assert "Training stopped before completion." in training.log_text.toPlainText()


@pytest.mark.parametrize("terminal_first", [False, True])
def test_cross_sender_started_and_terminal_delivery_remains_terminal(
    qtbot,
    tmp_path: Path,
    monkeypatch,
    terminal_first: bool,
) -> None:
    study, service = _prepare_training_runtime(tmp_path)
    window = _open_runtime_panels(qtbot, study)
    training = window.training_panel
    terminal_publications: list[TrainingLifecycleEvent] = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_publications.append,
    )

    def raise_oom(_holder, _record) -> None:
        raise torch.cuda.OutOfMemoryError("CUDA out of memory")

    monkeypatch.setattr(TrainingPlanHolder, "train_one_repeat", raise_oom)
    qtbot.mouseClick(training.sidebar.btn_start, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            len(terminal_publications) == 1
            and training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Failed"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.FAILED,
            )
            and "Training stopped (event)." in training.log_text.toPlainText()
        ),
        timeout=15_000,
    )

    published = terminal_publications[0]
    run = published.outcome.run
    assert run is not None
    assert published.publication_generation is not None
    started = TrainingLifecycleEvent(
        token=TrainingStateToken(
            generation=published.token.generation + 1,
            stable=True,
        ),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=run,
        ),
    )
    terminal = TrainingLifecycleEvent(
        token=TrainingStateToken(
            generation=published.token.generation + 2,
            stable=True,
        ),
        outcome=published.outcome,
        publication_generation=published.publication_generation + 1,
    )
    terminal_log_count = training.log_text.toPlainText().count(
        "Training stopped (event)."
    )
    if terminal_first:
        ordered_events = (
            ("training_terminal_published", terminal),
            ("training_started_state", started),
        )
    else:
        ordered_events = (
            ("training_started_state", started),
            ("training_terminal_published", terminal),
        )

    _emit_lifecycle_events_from_distinct_threads(
        service.training,
        ordered_events,
    )

    qtbot.waitUntil(
        lambda: (
            training.log_text.toPlainText().count("Training stopped (event).")
            == terminal_log_count + 1
            and training.history_table.item(0, 3) is not None
            and training.history_table.item(0, 3).text() == "Failed"
            and _analysis_panels_show_training_state(
                window,
                TrainingOutcomeState.FAILED,
            )
        ),
        timeout=10_000,
    )
    _deliver_pending_qt_events()

    assert training.history_table.item(0, 3).text() == "Failed"
    assert training.sidebar.btn_start.isEnabled()
    assert not training.sidebar.btn_stop.isEnabled()
    assert window.statusBar().currentMessage() == "Training failed · Adjust settings"
    assert training.log_text.toPlainText().splitlines()[-1] == (
        "Training stopped (event)."
    )


class _BusyTarget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.busy_states: list[bool] = []

    def set_busy(self, busy: bool) -> None:
        self.busy_states.append(bool(busy))
        self.setEnabled(not busy)


def _query_result() -> CommandResult:
    return CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(training_changed=True),
    )


@pytest.mark.parametrize("worker_outcome", ["success", "error"])
def test_deleted_async_owner_drops_callbacks_and_releases_runtime_ownership(
    qtbot,
    monkeypatch,
    worker_outcome: str,
) -> None:
    owner = QWidget()
    busy_target = _BusyTarget()
    cast(Any, owner).main_window = busy_target
    qtbot.addWidget(owner)
    qtbot.addWidget(busy_target)
    owner.show()
    busy_target.show()
    registry = AsyncCommandRegistry()
    worker_started = Event()
    worker_release = Event()
    results: list[CommandResult] = []
    errors: list[tuple[Any, ...]] = []
    uncaught: list[tuple[Any, ...]] = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: uncaught.append(args))

    def execute() -> CommandResult:
        worker_started.set()
        assert worker_release.wait(timeout=3.0)
        if worker_outcome == "error":
            raise RuntimeError("barrier command failed")
        return _query_result()

    runner = QtApplicationCommandRunner(
        context=owner,
        command=QueryStateCommand(),
        execute=execute,
        on_result=results.append,
        on_error=errors.append,
        refresh=True,
        busy_target=busy_target,
        allow_during_shutdown=False,
        registry=registry,
    )

    assert runner.start() is True
    assert worker_started.wait(timeout=1.0)
    assert registry.active_count(owner) == 1
    assert busy_target.busy_states == [True]
    assert not busy_target.isEnabled()
    suppression_key = id(busy_target)
    assert suppression_key in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS

    owner.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(owner), timeout=1_000)
    worker_release.set()
    qtbot.waitUntil(lambda: registry.active_count(owner) == 0, timeout=3_000)
    qtbot.waitUntil(busy_target.isEnabled, timeout=1_000)

    assert results == []
    assert errors == []
    assert registry.active_count(owner) == 0
    assert busy_target.busy_states == [True, False]
    assert suppression_key not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS
    assert uncaught == []
