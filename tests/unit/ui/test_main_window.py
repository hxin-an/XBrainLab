from dataclasses import replace
from threading import Thread
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.trainer import Trainer
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingTerminalOutcome,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.product_language import workflow_stage_hint


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, qtbot):
    study = Study()
    window = MainWindow(study)
    assert window._ensure_application_publication_renderer() is not None
    qtbot.addWidget(window)
    return window


def test_mainwindow_launch(main_window, qtbot):
    """Smoke test: Ensure MainWindow launches and is visible."""
    main_window.show()
    qtbot.waitUntil(main_window.isVisible)
    assert main_window.isVisible()
    assert main_window.statusBar().property("operationKind") == ""


def test_mainwindow_owns_publication_renderer_before_assistant_init(main_window):
    assert main_window.agent_manager is None
    renderer = main_window._application_publication_renderer
    assert renderer.parent() is main_window


def test_assistant_first_start_installs_desktop_publication_owner(qapp, qtbot):
    observations = {}

    class RecordingAgentManager(QObject):
        status_message_received = pyqtSignal(str)

        def __init__(
            self,
            main_window,
            study,
            *,
            application_service,
        ):
            super().__init__(main_window)
            observations["renderer_before_manager"] = (
                main_window._application_publication_renderer is not None
            )
            observations["service"] = application_service
            self.chat_dock = None

        def init_ui(self):
            observations["ui_initialized"] = True

        def connect_visualization_monitor(self):
            return None

    study = Study()
    with (
        patch.object(MainWindow, "_schedule_startup_prewarm"),
        patch(
            "XBrainLab.ui.main_window._load_agent_manager_class",
            return_value=RecordingAgentManager,
        ),
        patch.object(MainWindow, "_connect_assistant_cleanup_signal"),
    ):
        window = MainWindow(study)
        qtbot.addWidget(window)
        assert window._application_publication_renderer is None

        window.init_agent()

    renderer = window._application_publication_renderer
    assert renderer is not None
    assert observations == {
        "renderer_before_manager": True,
        "service": renderer.service,
        "ui_initialized": True,
    }


def test_mainwindow_replays_initial_publication_after_deferred_startup(qapp, qtbot):
    from XBrainLab.backend.application.runtime import application_service_initialized

    study = Study()
    with patch.object(MainWindow, "_schedule_startup_prewarm"):
        window = MainWindow(study)
    qtbot.addWidget(window)

    assert window._application_publication_renderer is None
    assert application_service_initialized(study) is False
    assert window._deferred_application_subscriptions
    assert window.dataset_panel.sidebar.import_btn.isEnabled() is False

    renderer = window._ensure_application_publication_renderer()

    assert renderer is not None
    assert application_service_initialized(study) is True
    assert window._deferred_application_subscriptions == []
    publication = renderer.service.get_view_publication()
    qtbot.waitUntil(
        lambda: (
            window.dataset_panel._last_application_revision >= publication.revision
        ),
        timeout=1_000,
    )
    qtbot.waitUntil(
        lambda: renderer.service._view_event_publisher.has_delivered_revision(
            publication.revision
        ),
        timeout=1_000,
    )
    assert window.dataset_panel.sidebar.import_btn.isEnabled() is True


def test_mainwindow_typed_dataset_import_does_not_require_legacy_controller(
    qapp,
    qtbot,
):
    study = Study()
    with patch.object(MainWindow, "_schedule_startup_prewarm"):
        window = MainWindow(study)
    qtbot.addWidget(window)
    assert window._ensure_application_publication_renderer() is not None
    assert window.dataset_panel.controller is None

    handler = window.dataset_panel.action_handler
    expected = InteractionOutcome.accepted("Review started")
    with (
        patch(
            "XBrainLab.ui.panels.dataset.actions.QFileDialog.getOpenFileNames",
            return_value=(["/tmp/example.edf"], "EDF"),
        ),
        patch.object(
            handler._data_interpretation,
            "_run_data_interpretation_import",
            return_value=expected,
        ) as run_interpretation,
    ):
        outcome = handler.import_data()

    assert outcome == expected
    run_interpretation.assert_called_once_with(
        ["/tmp/example.edf"],
        source_hint="file",
    )


def test_mainwindow_typed_preprocess_sidebar_uses_publication_without_controller(
    qapp,
    qtbot,
):
    study = Study()
    with patch.object(MainWindow, "_schedule_startup_prewarm"):
        window = MainWindow(study)
    qtbot.addWidget(window)
    assert window._ensure_application_publication_renderer() is not None

    panel = window._materialize_panel(1)

    assert panel is window.preprocess_panel
    assert panel.controller is None
    panel.sidebar.update_sidebar()
    assert panel.sidebar.btn_filter.isEnabled() is False
    assert panel.sidebar.btn_epoch.isEnabled() is False


def test_mainwindow_renderer_delays_terminal_until_qt_render(main_window, qtbot):
    main_window.show()
    qtbot.waitUntil(main_window.isVisible)
    service = get_application_service(main_window.study)
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    terminal_events = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_events.append,
    )
    results = []
    worker = Thread(
        target=lambda: results.append(service._publish_training_terminal_state()),
    )

    worker.start()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert results == [False]
    assert terminal_events == []
    qtbot.waitUntil(lambda: len(terminal_events) == 1, timeout=1_000)
    publication = service.get_view_publication()
    assert service._view_event_publisher.has_delivered_revision(publication.revision)
    assert main_window.statusBar().currentMessage() == workflow_stage_hint(
        publication.state.pipeline_stage
    )

    assert service._publish_view_changed(publication) is True
    assert len(terminal_events) == 1


def test_mainwindow_failed_render_keeps_terminal_retryable(main_window, qtbot):
    service = get_application_service(main_window.study)
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    terminal_events = []
    service.training.subscribe(
        "training_terminal_published",
        terminal_events.append,
    )
    renderer = main_window._application_publication_renderer
    render = renderer._render_publication
    renderer._render_publication = lambda _publication: False

    assert service._publish_training_terminal_state() is False
    publication = service.get_view_publication()
    assert terminal_events == []
    assert (
        service._view_event_publisher.has_delivered_revision(publication.revision)
        is False
    )

    renderer._render_publication = render
    assert service._publish_view_changed(publication) is False
    qtbot.waitUntil(lambda: len(terminal_events) == 1, timeout=1_000)
    assert len(terminal_events) == 1


def test_mainwindow_failed_training_publication_keeps_actionable_status(
    main_window,
):
    service = get_application_service(main_window.study)
    publication = service.get_view_publication()
    failed = replace(
        publication,
        state=replace(
            publication.state,
            training=replace(
                publication.state.training,
                terminal_outcome=TrainingTerminalOutcome(
                    state=TrainingOutcomeState.FAILED,
                    detail="CUDA out of memory during training.",
                ),
            ),
        ),
    )

    main_window._render_application_view_publication(failed)

    assert main_window.statusBar().currentMessage() == (
        "Training failed · Adjust settings"
    )


def test_mainwindow_application_publication_updates_registered_data_summary(
    main_window,
):
    """A rendered workflow revision must also refresh aggregate sidebars."""
    from XBrainLab.ui.components.info_panel import AggregateInfoPanel

    panel = AggregateInfoPanel(main_window)
    publication = replace(
        get_application_service(main_window.study).get_view_publication(),
        data_summary_rows=(
            {
                "filepath": "/data/sub-01.edf",
                "filename": "sub-01.edf",
                "subject": "01",
                "session": "baseline",
                "n_channels": 22,
                "sampling_frequency": 250.0,
                "epochs_length": 0,
                "is_raw": True,
                "event": {"count": 48, "labels": ["left", "right"]},
                "highpass": 1.0,
                "lowpass": 40.0,
            },
        ),
    )

    assert panel.has_data is False

    main_window._render_application_view_publication(publication)

    assert panel.has_data is True
    assert panel.table.item(panel.row_map["EEG files"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Channels"], 1).text() == "22"


def test_navigation(main_window, qtbot):
    """Test that clicking navigation buttons switches the stacked widget page."""
    # Define expected mapping: Button Text -> Stack Index
    # Based on MainWindow.init_panels:
    # 0: Dataset, 1: Preprocess, 2: Training, 3: Evaluation, 4: Visualization
    nav_map = {
        "Dataset": 0,
        "Preprocess": 1,
        "Training": 2,
        "Evaluation": 3,
        "Visualization": 4,
    }

    for btn_text, expected_index in nav_map.items():
        # Find the button by text
        btn = None
        for b in main_window.nav_btns:
            if b.text() == btn_text:
                btn = b
                break

        assert btn is not None, f"Navigation button '{btn_text}' not found."

        # Click the button
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

        # Verify stack index
        assert main_window.stack.currentIndex() == expected_index, (
            f"Failed to switch to {btn_text} (Index {expected_index})"
        )

        # Verify button is checked
        assert btn.isChecked(), f"Button '{btn_text}' should be checked."
