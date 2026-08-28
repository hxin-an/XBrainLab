from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from scripts.dev.capture_dataset_narrow_walkthrough import (
    MINIMUM_FIXED_SIDEBAR_SHELL_WIDTH,
    _apply_loaded_state,
    _build_shell,
    _dataset_table_evidence,
    _DatasetPublicationFixture,
    _settle,
    _state_truth_evidence,
)


def test_dataset_capture_keeps_visible_state_publication_and_status_consistent(
    qtbot,
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    window, panel, _assistant_dock, _chat_panel = _build_shell(
        app,
        shell_width=MINIMUM_FIXED_SIDEBAR_SHELL_WIDTH,
        shell_height=520,
        logical_scale=1.0,
    )
    qtbot.addWidget(window)

    status_bar = window.statusBar()
    assert status_bar is not None
    publication_port = panel._publication_port
    assert isinstance(publication_port, _DatasetPublicationFixture)
    empty_status = status_bar.currentMessage()
    assert not (
        panel.empty_state_title.isVisibleTo(panel)
        and panel.empty_state_title.text() == "No EEG data loaded"
        and empty_status == "Dataset is ready."
    )
    assert empty_status == "No data loaded"
    empty_publication = panel._read_application_publication()
    assert empty_publication is not None
    assert empty_publication.state.pipeline_stage == "empty"
    assert empty_publication.state.active_dataset.has_raw_data is False
    assert publication_port._loaded_data == []

    _apply_loaded_state(panel)
    _settle(app)

    loaded_publication = panel._read_application_publication()
    assert loaded_publication is not None
    assert loaded_publication.state.pipeline_stage == "data_loaded"
    assert loaded_publication.state.active_dataset.has_preprocessed_data is False
    assert len(publication_port._loaded_data) == 1
    assert panel.table.isVisibleTo(panel)
    assert status_bar.currentMessage() == (
        "EEG data loaded · Ready for preprocessing or epoching"
    )
    assert _dataset_table_evidence(panel)["passed"] is True


def test_dataset_capture_gate_rejects_empty_ready_contradiction(qtbot) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    window, panel, _assistant_dock, _chat_panel = _build_shell(
        app,
        shell_width=MINIMUM_FIXED_SIDEBAR_SHELL_WIDTH,
        shell_height=520,
        logical_scale=1.0,
    )
    qtbot.addWidget(window)
    status_bar = window.statusBar()
    assert status_bar is not None
    status_bar.showMessage("Dataset is ready.")

    evidence = _state_truth_evidence(window, panel, state="empty")

    assert evidence["passed"] is False
    assert evidence["checks"]["status_matches_publication"] is False
    assert evidence["checks"]["no_empty_ready_contradiction"] is False
