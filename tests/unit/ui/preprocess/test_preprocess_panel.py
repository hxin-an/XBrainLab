from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.application.owned_work import OwnedWorkKind
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderData,
    PreprocessRenderPublication,
    PreprocessRenderRequest,
    PreprocessSignalState,
    SignalSeries,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
)
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


def _render_publication() -> PreprocessRenderPublication:
    return PreprocessRenderPublication(
        request=PreprocessRenderRequest(publication_generation=3),
        generation=3,
        data=PreprocessRenderData(
            state=PreprocessSignalState.RAW,
            channels=("C3", "C4"),
            sampling_frequency=100.0,
            cursor_max_seconds=1.0,
            selected_channel_index=0,
            selected_channel_name="C3",
            current=SignalSeries(
                time_seconds=np.array([0.0, 0.01]),
                values_volts=np.array([0.0, 1e-6]),
                sampling_frequency=100.0,
            ),
        ),
    )


def test_preprocess_panel_renders_only_application_query_publication(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    panel.plotter.plot_sample_data = MagicMock()
    publication = _render_publication()

    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=publication,
    ):
        panel.update_panel()

    panel.plotter.plot_sample_data.assert_called_once_with(publication)
    assert panel.preview_widget.chan_combo.count() == 2


@pytest.mark.parametrize(
    "active_kind, expected", [(OwnedWorkKind.IMPORT_REVIEW, True), (None, False)]
)
def test_preprocess_import_finishing_reads_publication_owned_work(
    qtbot, active_kind: OwnedWorkKind | None, expected: bool
) -> None:
    port = MagicMock()
    port.get_active_owned_operation.side_effect = (
        lambda kind: object() if kind is active_kind else None
    )
    panel = PreprocessPanel(publication_port=port)
    qtbot.addWidget(panel)
    assert panel.import_is_finishing() is expected


def test_preprocess_import_finishing_fails_closed_when_owned_work_is_unavailable(
    qtbot,
) -> None:
    port = MagicMock()
    port.get_active_owned_operation.side_effect = RuntimeError("registry unavailable")
    panel = PreprocessPanel(publication_port=port)
    qtbot.addWidget(panel)
    assert panel.import_is_finishing() is True


def test_preprocess_sidebar_fences_real_import_operations_until_terminal_refresh(
    qtbot, monkeypatch
) -> None:
    study = Study()
    raw = Raw(
        "memory.fif",
        mne.io.RawArray(
            np.zeros((1, 100)), mne.create_info(["Cz"], 100.0, "eeg"), verbose="ERROR"
        ),
    )
    study.loaded_data_list = [raw]
    study.preprocessed_data_list = [raw]
    service = get_application_service(study)
    window = QMainWindow()
    window.study = study
    panel = PreprocessPanel(parent=window)
    qtbot.addWidget(window)
    warning = MagicMock()
    monkeypatch.setattr("XBrainLab.ui.panels.preprocess.sidebar.show_warning", warning)
    try:
        sidebar = panel.sidebar
        sidebar.update_sidebar(publication=service.get_view_publication())
        assert sidebar.btn_filter.isEnabled()
        review = service.owned_work.begin(OwnedWorkKind.IMPORT_REVIEW, cancellable=True)
        sidebar.update_sidebar(publication=service.get_view_publication())
        assert not sidebar.btn_filter.isEnabled()
        sidebar.btn_filter.click()
        assert warning.call_count == 0
        service.owned_work.complete(review.operation_id)
        sidebar.update_sidebar(publication=service.get_view_publication())
        assert sidebar.btn_filter.isEnabled()
    finally:
        panel.close()
        window.close()
        service.close()


def test_preprocess_sidebar_fails_closed_without_publication(
    qtbot, monkeypatch
) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    warning = MagicMock()
    monkeypatch.setattr("XBrainLab.ui.panels.preprocess.sidebar.show_warning", warning)
    panel.sidebar.open_filtering()
    assert warning.called


def test_preprocess_panel_cancels_pending_plot_for_locked_publication(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    panel.plotter.plot_sample_data = MagicMock()
    publication = PreprocessRenderPublication(
        request=PreprocessRenderRequest(publication_generation=3),
        generation=3,
        data=PreprocessRenderData(state=PreprocessSignalState.LOCKED),
    )
    panel.preview_widget.plot_timer.start(1000)
    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=publication,
    ):
        panel.update_panel()
    assert not panel.preview_widget.plot_timer.isActive()
    panel.plotter.plot_sample_data.assert_not_called()


def test_signal_preview_distinguishes_empty_raw_locked_and_unavailable(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    panel.preview_widget.reset_view()
    assert panel.preview_widget.empty_state_title.text() == "No EEG data loaded"
    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=_render_publication(),
    ):
        panel.update_panel()
    assert panel.preview_widget.empty_state.isHidden()
    locked = PreprocessRenderPublication(
        request=PreprocessRenderRequest(publication_generation=3),
        generation=3,
        data=PreprocessRenderData(state=PreprocessSignalState.LOCKED),
    )
    with patch(
        "XBrainLab.ui.panels.preprocess.panel.query_preprocess_render",
        return_value=locked,
    ):
        panel.update_panel()
    assert panel.preview_widget.locked_state_title.text() == "Preprocessing locked"
    panel.preview_widget.show_unavailable_message(
        "Published preprocess objects are stale."
    )
    assert (
        panel.preview_widget.unavailable_state_title.text()
        == "Signal preview unavailable"
    )


def test_preprocess_panel_close_quiesces_native_plots(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.preview_widget.plot_timer.start(1000)
    panel.close()
    qtbot.wait(0)
    preview = panel.preview_widget
    assert preview._native_plot_shutdown is True
    assert preview._native_plot_finalized is True
    assert not preview.plot_timer.isActive()
    assert preview.proxy_time.slot is None
    assert preview.proxy_freq.slot is None


def test_preprocess_history_has_stable_locked_row_layout(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    history = panel.history_widget
    initial_height = history.minimumHeight()
    history.update_history([f"Step {index}" for index in range(12)], True)
    assert history.minimumHeight() == initial_height == history.maximumHeight()
    assert (
        history.history_list.item(12).text()
        == "EEG epochs created. Preprocessing is now locked."
    )


def test_filtering_dialog_uses_lowest_published_sampling_rate(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    panel._query_preprocess_data_rows = lambda: (
        [{"sampling_frequency": 512.0}, {"sampling_frequency": 128.0}],
        [],
    )
    with (
        patch.object(
            panel.sidebar,
            "_begin_preprocess_review",
            return_value=(SimpleNamespace(publication_generation=3), True),
        ),
        patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as dialog,
    ):
        dialog.return_value.exec.return_value = False
        panel.sidebar.open_filtering()
    assert dialog.call_args.kwargs["sampling_rate_hz"] == 128.0


def test_preprocess_async_schedule_failure_never_uses_sync_command(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    with (
        patch.object(
            panel.sidebar,
            "_begin_preprocess_review",
            return_value=(SimpleNamespace(publication_generation=3), True),
        ),
        patch("XBrainLab.ui.panels.preprocess.sidebar.FilteringDialog") as dialog,
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command_async",
            return_value=False,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.execute_application_command"
        ) as sync_command,
        patch("XBrainLab.ui.panels.preprocess.sidebar.show_warning") as warning,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_params.return_value = (1.0, 40.0, [50.0])
        panel.sidebar.open_filtering()
    sync_command.assert_not_called()
    assert warning.call_args.args[2] == CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE


def test_unusable_publication_overrides_stale_epoch_state(qtbot) -> None:
    panel = PreprocessPanel()
    qtbot.addWidget(panel)
    publication = SimpleNamespace(
        usable=False,
        effective_capabilities={},
        state=SimpleNamespace(active_dataset=SimpleNamespace(has_epoch_data=True)),
    )
    panel.sidebar.update_sidebar(publication=publication)
    assert not panel.sidebar.btn_epoch.isEnabled()
    assert panel.sidebar.btn_epoch.text() == "Create EEG Epochs"
