from __future__ import annotations

from time import perf_counter
from typing import Any, cast
from unittest.mock import patch

from XBrainLab.backend.application import (
    LoadDataCommand,
    QueryStateCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.main_window import MainWindow


def test_real_gdf_epoching_does_not_block_on_success_modal(qtbot, monkeypatch):
    monkeypatch.setenv("MNE_DONTWRITE_HOME", "true")
    study = Study()
    window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    service = get_application_service(study)

    paths = [
        "tests/fixtures/data/A01T.gdf",
        "tests/fixtures/data/A02T.gdf",
        "tests/fixtures/data/A03T.gdf",
    ]
    load_result = service.execute(LoadDataCommand(paths=paths))
    assert load_result.ok, load_result.message

    window.switch_page(1)
    query_result = service.execute(
        QueryStateCommand(query="data_lists", include_objects=True),
    )
    data_list = query_result.runtime.get("preprocessed_data_list") or []
    selected_events = sorted(
        {
            str(event_name)
            for data in data_list
            for event_name in data.get_event_list()[1]
        },
    )
    assert selected_events

    ui_window = cast(Any, window)

    class FakeEpochingDialog:
        def __init__(self, _parent, _data_list):
            pass

        def exec(self):
            return True

        def get_params(self):
            return ((-0.2, 0.0), selected_events, -0.2, 1.0)

    start = perf_counter()
    with (
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.EpochingDialog",
            FakeEpochingDialog,
        ),
        patch(
            "XBrainLab.ui.panels.preprocess.sidebar.QMessageBox.information",
        ) as success_dialog,
    ):
        ui_window.preprocess_panel.sidebar.open_epoching()
        elapsed = perf_counter() - start

        def _epoch_exists() -> bool:
            state_result = service.execute(QueryStateCommand(query="state"))
            assert state_result.ok, state_result.message
            return bool(state_result.diagnostics["state"]["epoch"]["exists"])

        qtbot.waitUntil(_epoch_exists, timeout=10_000)
        epoch_status_bar = cast(Any, window.statusBar())
        assert epoch_status_bar is not None
        qtbot.waitUntil(
            lambda: "Epoching applied" in epoch_status_bar.currentMessage(),
            timeout=2_000,
        )

    assert elapsed < 10.0
    state_result = service.execute(QueryStateCommand(query="state"))
    assert state_result.ok, state_result.message
    assert state_result.diagnostics["state"]["epoch"]["exists"] is True
    success_dialog.assert_not_called()
    status_bar = cast(Any, window.statusBar())
    assert status_bar is not None
    assert "Epoching applied" in status_bar.currentMessage()

    window.close()
